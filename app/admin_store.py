from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path


DB_PATH = Path("data") / "kakaopogo.sqlite3"


@dataclass(frozen=True)
class ChatUser:
    room: str
    sender: str
    user_key: str


@dataclass(frozen=True)
class AdminRequest:
    id: int
    room: str
    sender: str
    user_key: str
    status: str


@dataclass(frozen=True)
class CustomCommand:
    room: str
    command: str
    display_command: str
    response: str
    created_by: str
    taught_by: str | None
    taught_at: str | None
    help_order: int | None


class AdminStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS room_admins (
                    room TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('owner', 'admin')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room, user_key)
                );

                CREATE TABLE IF NOT EXISTS admin_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'approved', 'rejected')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_admin_requests_room_status
                    ON admin_requests(room, status);

                CREATE TABLE IF NOT EXISTS custom_commands (
                    room TEXT NOT NULL,
                    command TEXT NOT NULL,
                    response TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room, command)
                );

                CREATE TABLE IF NOT EXISTS control_room_targets (
                    control_room TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    target_room TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (control_room, user_key)
                );

                CREATE TABLE IF NOT EXISTS attendance (
                    room TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    last_check_in TEXT,
                    total_days INTEGER NOT NULL DEFAULT 0,
                    points INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (room, user_key)
                );
                """
            )
            self._ensure_column(conn, "custom_commands", "display_command", "TEXT")
            self._ensure_column(conn, "custom_commands", "taught_by", "TEXT")
            self._ensure_column(conn, "custom_commands", "taught_at", "TEXT")
            self._ensure_column(conn, "custom_commands", "help_order", "INTEGER")
            conn.execute(
                """
                UPDATE custom_commands
                SET display_command = COALESCE(display_command, command),
                    taught_by = COALESCE(taught_by, created_by),
                    taught_at = COALESCE(taught_at, updated_at)
                """
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def has_owner(self, room: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM room_admins WHERE room = ? AND role = 'owner' LIMIT 1",
                (room,),
            ).fetchone()
        return row is not None

    def get_role(self, user: ChatUser) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_key, role
                FROM room_admins
                WHERE room = ? AND user_key = ?
                """,
                (user.room, user.user_key),
            ).fetchone()
            if row:
                return row["role"]

            # 닉네임 매칭은 hash 키가 없던 시절의 레코드를 새 키로 옮겨주는
            # 이전 경로로만 쓴다. 이미 hash 키가 붙은 레코드까지 닉네임으로
            # 인정하면 닉네임만 똑같이 바꾼 사칭을 막을 수 없다.
            row = conn.execute(
                """
                SELECT user_key, role
                FROM room_admins
                WHERE room = ? AND display_name = ?
                """,
                (user.room, user.sender),
            ).fetchone()
            if row and row["user_key"].startswith("sender:"):
                self._promote_admin_key(conn, user, row["user_key"])
                return row["role"]
        return None

    def get_effective_role(self, user: ChatUser) -> str | None:
        room_role = self.get_role(user)
        if room_role:
            return room_role
        if self.is_global_owner(user):
            return "owner"
        return None

    def is_global_owner(self, user: ChatUser) -> bool:
        if user.user_key.startswith("sender:"):
            return False
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM room_admins
                WHERE user_key = ? AND role = 'owner'
                LIMIT 1
                """,
                (user.user_key,),
            ).fetchone()
        return row is not None

    @staticmethod
    def _promote_admin_key(
        conn: sqlite3.Connection,
        user: ChatUser,
        previous_user_key: str,
    ) -> None:
        if user.user_key == previous_user_key:
            return
        if user.user_key.startswith("sender:"):
            return
        try:
            conn.execute(
                """
                UPDATE room_admins
                SET user_key = ?, display_name = ?
                WHERE room = ? AND user_key = ?
                """,
                (user.user_key, user.sender, user.room, previous_user_key),
            )
        except sqlite3.IntegrityError:
            pass

    def check_in(
        self,
        user: ChatUser,
        today: str,
        points_per_day: int,
    ) -> tuple[int, int, bool]:
        """출석을 기록하고 (누적일수, 보유포인트, 오늘 새로 출석했는지)를 돌려준다."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT last_check_in, total_days, points
                FROM attendance
                WHERE room = ? AND user_key = ?
                """,
                (user.room, user.user_key),
            ).fetchone()

            if row and row["last_check_in"] == today:
                return row["total_days"], row["points"], False

            total_days = (row["total_days"] if row else 0) + 1
            points = (row["points"] if row else 0) + points_per_day
            conn.execute(
                """
                INSERT INTO attendance (room, user_key, display_name, last_check_in, total_days, points)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(room, user_key)
                DO UPDATE SET display_name = excluded.display_name,
                              last_check_in = excluded.last_check_in,
                              total_days = excluded.total_days,
                              points = excluded.points
                """,
                (user.room, user.user_key, user.sender, today, total_days, points),
            )
            return total_days, points, True

    def get_room_control_target(self, control_room: str) -> str | None:
        """이 방에 설정된 방 단위 관리 대상(가장 최근 설정)을 돌려준다."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT target_room
                FROM control_room_targets
                WHERE control_room = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (control_room,),
            ).fetchone()
        return row["target_room"] if row else None

    def attendance_ranking(
        self,
        room: str,
        limit: int = 10,
    ) -> list[tuple[str, int, int]]:
        """방의 출석 순위를 (닉네임, 누적일수, 포인트)로 돌려준다."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT display_name, total_days, points
                FROM attendance
                WHERE room = ?
                ORDER BY points DESC, total_days DESC, display_name ASC
                LIMIT ?
                """,
                (room, limit),
            ).fetchall()
        return [
            (row["display_name"], row["total_days"], row["points"])
            for row in rows
        ]

    def is_owner(self, user: ChatUser) -> bool:
        return self.get_effective_role(user) == "owner"

    def is_admin_or_owner(self, user: ChatUser) -> bool:
        return self.get_effective_role(user) in {"owner", "admin"}

    def add_owner(self, user: ChatUser) -> None:
        self._upsert_admin(user, "owner")

    def replace_owner(self, user: ChatUser) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM room_admins WHERE room = ? AND role = 'owner'",
                (user.room,),
            )
            conn.execute(
                """
                INSERT INTO room_admins (room, user_key, display_name, role)
                VALUES (?, ?, ?, 'owner')
                ON CONFLICT(room, user_key)
                DO UPDATE SET display_name = excluded.display_name,
                              role = 'owner'
                """,
                (user.room, user.user_key, user.sender),
            )

    def add_admin(self, user: ChatUser) -> None:
        self._upsert_admin(user, "admin")

    def _upsert_admin(self, user: ChatUser, role: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO room_admins (room, user_key, display_name, role)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(room, user_key)
                DO UPDATE SET display_name = excluded.display_name,
                              role = excluded.role
                """,
                (user.room, user.user_key, user.sender, role),
            )

    def add_admin_request(self, user: ChatUser) -> int:
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM admin_requests
                WHERE room = ? AND user_key = ? AND status = 'pending'
                ORDER BY id DESC
                LIMIT 1
                """,
                (user.room, user.user_key),
            ).fetchone()
            if existing:
                return int(existing["id"])

            cursor = conn.execute(
                """
                INSERT INTO admin_requests (room, user_key, display_name)
                VALUES (?, ?, ?)
                """,
                (user.room, user.user_key, user.sender),
            )
            return int(cursor.lastrowid)

    def list_pending_requests(self, room: str) -> list[AdminRequest]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, room, display_name, user_key, status
                FROM admin_requests
                WHERE room = ? AND status = 'pending'
                ORDER BY id
                """,
                (room,),
            ).fetchall()
        return [
            AdminRequest(
                id=int(row["id"]),
                room=row["room"],
                sender=row["display_name"],
                user_key=row["user_key"],
                status=row["status"],
            )
            for row in rows
        ]

    def get_pending_request(self, room: str, request_id: int) -> AdminRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, room, display_name, user_key, status
                FROM admin_requests
                WHERE room = ? AND id = ? AND status = 'pending'
                """,
                (room, request_id),
            ).fetchone()
        if not row:
            return None
        return AdminRequest(
            id=int(row["id"]),
            room=row["room"],
            sender=row["display_name"],
            user_key=row["user_key"],
            status=row["status"],
        )

    def approve_request(self, request: AdminRequest) -> None:
        user = ChatUser(
            room=request.room,
            sender=request.sender,
            user_key=request.user_key,
        )
        with self._connect() as conn:
            conn.execute(
                "UPDATE admin_requests SET status = 'approved' WHERE id = ?",
                (request.id,),
            )
            conn.execute(
                """
                INSERT INTO room_admins (room, user_key, display_name, role)
                VALUES (?, ?, ?, 'admin')
                ON CONFLICT(room, user_key)
                DO UPDATE SET display_name = excluded.display_name,
                              role = 'admin'
                """,
                (user.room, user.user_key, user.sender),
            )

    def reject_request(self, room: str, request_id: int) -> AdminRequest | None:
        request = self.get_pending_request(room, request_id)
        if not request:
            return None
        with self._connect() as conn:
            conn.execute(
                "UPDATE admin_requests SET status = 'rejected' WHERE id = ?",
                (request_id,),
            )
        return request

    def list_admins(self, room: str) -> list[tuple[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT display_name, role
                FROM room_admins
                WHERE room = ?
                ORDER BY CASE role WHEN 'owner' THEN 0 ELSE 1 END, display_name
                """,
                (room,),
            ).fetchall()
        return [(row["display_name"], row["role"]) for row in rows]

    def list_admin_records(self, room: str) -> list[tuple[str, str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT display_name, role, user_key
                FROM room_admins
                WHERE room = ?
                ORDER BY CASE role WHEN 'owner' THEN 0 ELSE 1 END, display_name
                """,
                (room,),
            ).fetchall()
        return [
            (row["display_name"], row["role"], row["user_key"])
            for row in rows
        ]

    def remove_admin_by_key(self, room: str, user_key: str) -> tuple[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT display_name, role
                FROM room_admins
                WHERE room = ? AND user_key = ?
                """,
                (room, user_key),
            ).fetchone()
            if not row:
                return None
            if row["role"] == "owner":
                return (row["display_name"], row["role"])
            conn.execute(
                "DELETE FROM room_admins WHERE room = ? AND user_key = ?",
                (room, user_key),
            )
        return (row["display_name"], row["role"])

    def upsert_custom_command(
        self,
        room: str,
        command: str,
        response: str,
        created_by: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO custom_commands (room, command, response, created_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(room, command)
                DO UPDATE SET response = excluded.response,
                              created_by = excluded.created_by,
                              updated_at = CURRENT_TIMESTAMP,
                              display_command = excluded.command,
                              taught_by = excluded.created_by,
                              taught_at = CURRENT_TIMESTAMP,
                              help_order = NULL
                """,
                (room, command, response, created_by),
            )
            conn.execute(
                """
                UPDATE custom_commands
                SET display_command = COALESCE(display_command, command),
                    taught_by = COALESCE(taught_by, created_by),
                    taught_at = COALESCE(taught_at, updated_at)
                WHERE room = ? AND command = ?
                """,
                (room, command),
            )

    def import_custom_command(
        self,
        room: str,
        command: str,
        display_command: str,
        response: str,
        taught_by: str,
        taught_at: str,
        help_order: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO custom_commands (
                    room,
                    command,
                    display_command,
                    response,
                    created_by,
                    taught_by,
                    taught_at,
                    help_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(room, command)
                DO UPDATE SET display_command = excluded.display_command,
                              response = excluded.response,
                              created_by = excluded.created_by,
                              taught_by = excluded.taught_by,
                              taught_at = excluded.taught_at,
                              help_order = excluded.help_order,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (
                    room,
                    command,
                    display_command,
                    response,
                    taught_by,
                    taught_by,
                    taught_at,
                    help_order,
                ),
            )

    def list_custom_rooms(self) -> list[str]:
        """커스텀 명령어가 하나라도 등록된 방 이름 목록."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT room FROM custom_commands ORDER BY room"
            ).fetchall()
        return [row["room"] for row in rows]

    def delete_custom_command(self, room: str, command: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM custom_commands WHERE room = ? AND command = ?",
                (room, command),
            )
            return cursor.rowcount > 0

    def get_custom_command(self, room: str, command: str) -> CustomCommand | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT room,
                       command,
                       COALESCE(display_command, command) AS display_command,
                       response,
                       created_by,
                       taught_by,
                       taught_at,
                       help_order
                FROM custom_commands
                WHERE room = ? AND command = ?
                """,
                (room, command),
            ).fetchone()
        if not row:
            return None
        return CustomCommand(
            room=row["room"],
            command=row["command"],
            display_command=row["display_command"],
            response=row["response"],
            created_by=row["created_by"],
            taught_by=row["taught_by"],
            taught_at=row["taught_at"],
            help_order=row["help_order"],
        )

    def list_custom_commands(self, room: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT command
                FROM custom_commands
                WHERE room = ?
                ORDER BY command
                """,
                (room,),
            ).fetchall()
        return [row["command"] for row in rows]

    def list_custom_command_records(self, room: str) -> list[CustomCommand]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT room,
                       command,
                       COALESCE(display_command, command) AS display_command,
                       response,
                       created_by,
                       taught_by,
                       taught_at,
                       help_order
                FROM custom_commands
                WHERE room = ?
                ORDER BY CASE WHEN help_order IS NULL THEN 1 ELSE 0 END,
                         help_order,
                         command
                """,
                (room,),
            ).fetchall()
        return [
            CustomCommand(
                room=row["room"],
                command=row["command"],
                display_command=row["display_command"],
                response=row["response"],
                created_by=row["created_by"],
                taught_by=row["taught_by"],
                taught_at=row["taught_at"],
                help_order=row["help_order"],
            )
            for row in rows
        ]

    def set_control_target(
        self,
        control_room: str,
        user_key: str,
        target_room: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO control_room_targets (control_room, user_key, target_room)
                VALUES (?, ?, ?)
                ON CONFLICT(control_room, user_key)
                DO UPDATE SET target_room = excluded.target_room,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (control_room, user_key, target_room),
            )

    def get_control_target(self, control_room: str, user_key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT target_room
                FROM control_room_targets
                WHERE control_room = ? AND user_key = ?
                """,
                (control_room, user_key),
            ).fetchone()
        return row["target_room"] if row else None
