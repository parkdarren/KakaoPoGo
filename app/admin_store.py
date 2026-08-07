from __future__ import annotations

import hashlib
import secrets
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


def _raid_sort_key(name: str) -> list[tuple[int, str, int]]:
    """레이드 명단 정렬 키: 숫자 먼저 -> 영문(aAbBcC 순) -> 기타."""
    key: list[tuple[int, str, int]] = []
    for ch in name:
        if ch.isdigit():
            key.append((0, ch, 0))
        elif ch.isalpha():
            key.append((1, ch.lower(), 0 if ch.islower() else 1))
        else:
            key.append((2, ch, 0))
    return key


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

                CREATE TABLE IF NOT EXISTS room_passwords (
                    room TEXT PRIMARY KEY,
                    salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    recovery_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS raid_sessions (
                    room TEXT NOT NULL,
                    pokemon_key TEXT NOT NULL,
                    host_key TEXT NOT NULL,
                    pokemon_display TEXT NOT NULL,
                    host_display TEXT NOT NULL,
                    friend_code TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room, pokemon_key, host_key)
                );

                CREATE TABLE IF NOT EXISTS raid_signups (
                    room TEXT NOT NULL,
                    pokemon_key TEXT NOT NULL,
                    host_key TEXT NOT NULL,
                    nickname_key TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room, pokemon_key, host_key, nickname_key)
                );

                CREATE TABLE IF NOT EXISTS chat_stats (
                    room TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    chat_date TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (room, user_key, chat_date)
                );

                CREATE TABLE IF NOT EXISTS raid_cancel_stats (
                    room TEXT NOT NULL,
                    nickname_key TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    cancel_count INTEGER NOT NULL DEFAULT 0,
                    last_cancel_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room, nickname_key)
                );

                CREATE TABLE IF NOT EXISTS rooms (
                    chat_id TEXT PRIMARY KEY,
                    room_name TEXT NOT NULL,
                    site_token TEXT NOT NULL UNIQUE,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                -- 경고와 칭찬을 같이 담는다. kind 로 구분한다('warn'/'praise').
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    nickname TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    warned_by TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'warn',
                    warned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS shop_items (
                    room TEXT NOT NULL,
                    item_no INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    created_by TEXT NOT NULL DEFAULT '',
                    created_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room, item_no)
                );

                CREATE TABLE IF NOT EXISTS shop_purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    nickname TEXT NOT NULL DEFAULT '',
                    item_name TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    bought_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                -- 일일랭킹 포인트를 하루에 한 번만 주기 위한 기록.
                CREATE TABLE IF NOT EXISTS rank_rewards (
                    room TEXT NOT NULL,
                    reward_date TEXT NOT NULL,
                    PRIMARY KEY (room, reward_date)
                );

                CREATE TABLE IF NOT EXISTS event_notifications (
                    room TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_sent_date TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS warn_permissions (
                    room TEXT NOT NULL,
                    user_key TEXT NOT NULL,
                    nickname TEXT NOT NULL DEFAULT '',
                    granted_by TEXT NOT NULL DEFAULT '',
                    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room, user_key)
                );

                CREATE TABLE IF NOT EXISTS room_join_counts (
                    room TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    nickname TEXT NOT NULL DEFAULT '',
                    join_count INTEGER NOT NULL DEFAULT 0,
                    present INTEGER NOT NULL DEFAULT 1,
                    pardon_next INTEGER NOT NULL DEFAULT 0,
                    last_join_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room, user_id)
                );
                """
            )
            raid_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(raid_signups)").fetchall()
            }
            if raid_columns and "host_key" not in raid_columns:
                # 모집자 개념 도입 전의 명단은 세션 정보가 없어 이어갈 수 없다.
                conn.execute("DROP TABLE raid_signups")
                conn.execute(
                    """
                    CREATE TABLE raid_signups (
                        room TEXT NOT NULL,
                        pokemon_key TEXT NOT NULL,
                        host_key TEXT NOT NULL,
                        nickname_key TEXT NOT NULL,
                        nickname TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (room, pokemon_key, host_key, nickname_key)
                    )
                    """
                )
            self._ensure_column(conn, "raid_sessions", "friend_code", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "raid_cancel_stats", "daily_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "raid_cancel_stats", "last_cancel_date", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "custom_commands", "display_command", "TEXT")
            self._ensure_column(conn, "custom_commands", "taught_by", "TEXT")
            self._ensure_column(conn, "custom_commands", "taught_at", "TEXT")
            self._ensure_column(conn, "custom_commands", "help_order", "INTEGER")
            self._ensure_column(conn, "room_join_counts", "present", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "room_join_counts", "pardon_next", "INTEGER NOT NULL DEFAULT 0")
            # 칭찬 기능이 생기기 전 기록은 전부 경고다.
            self._ensure_column(conn, "warnings", "kind", "TEXT NOT NULL DEFAULT 'warn'")
            # 등록자를 남기기 전에 올라온 상품은 등록자를 알 수 없다.
            self._ensure_column(conn, "shop_items", "created_by", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "shop_items", "created_name", "TEXT NOT NULL DEFAULT ''")
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

    def has_any_owner(self) -> bool:
        """방과 무관하게 이 봇에 owner가 한 명이라도 등록돼 있는지 본다."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM room_admins WHERE role = 'owner' LIMIT 1"
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

    def add_points(
        self, room: str, user_key: str, display_name: str, amount: int
    ) -> int:
        """포인트를 더하거나(양수) 뺀다(음수). 남은 포인트를 돌려준다.

        출석 포인트와 같은 곳(attendance.points)에 쌓아 하나로 관리한다.
        """
        if not room or not user_key or not amount:
            return self.get_points(room, user_key)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO attendance (room, user_key, display_name, points)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(room, user_key) DO UPDATE SET
                    points = points + excluded.points,
                    display_name = CASE
                        WHEN excluded.display_name != '' THEN excluded.display_name
                        ELSE attendance.display_name
                    END
                """,
                (room, user_key, display_name or "", amount),
            )
            row = conn.execute(
                "SELECT points FROM attendance WHERE room = ? AND user_key = ?",
                (room, user_key),
            ).fetchone()
        return row["points"] if row else 0

    def get_points(self, room: str, user_key: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT points FROM attendance WHERE room = ? AND user_key = ?",
                (room, user_key),
            ).fetchone()
        return row["points"] if row else 0

    def add_shop_item(
        self,
        room: str,
        name: str,
        price: int,
        created_by: str = "",
        created_name: str = "",
    ) -> int:
        """상품을 등록하고 번호를 돌려준다. 번호는 방마다 1부터 이어진다.

        등록자는 닉네임이 아니라 user_key로 남겨서 닉을 바꿔도 추적된다.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(item_no), 0) AS last FROM shop_items WHERE room = ?",
                (room,),
            ).fetchone()
            item_no = row["last"] + 1
            conn.execute(
                """
                INSERT INTO shop_items
                    (room, item_no, name, price, created_by, created_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (room, item_no, name, price, created_by, created_name),
            )
        return item_no

    def list_shop_items(self, room: str) -> list[tuple[int, str, int, str, str]]:
        """(번호, 상품명, 가격, 등록자 user_key, 등록 당시 닉네임)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT item_no, name, price, created_by, created_name
                FROM shop_items WHERE room = ? ORDER BY item_no
                """,
                (room,),
            ).fetchall()
        return [
            (
                row["item_no"],
                row["name"],
                row["price"],
                row["created_by"],
                row["created_name"],
            )
            for row in rows
        ]

    def get_shop_item(self, room: str, item_no: int) -> tuple[str, int] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, price FROM shop_items WHERE room = ? AND item_no = ?",
                (room, item_no),
            ).fetchone()
        return (row["name"], row["price"]) if row else None

    def remove_shop_item(self, room: str, item_no: int) -> tuple[str, int] | None:
        """상품을 지우고 (이름, 남은 개수)를 돌려준다.

        번호가 중간에 비지 않도록 남은 상품을 1번부터 다시 매긴다. 번호를
        작은 쪽으로만 당기므로 순서대로 바꾸면 번호가 겹치지 않는다.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name FROM shop_items WHERE room = ? AND item_no = ?",
                (room, item_no),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "DELETE FROM shop_items WHERE room = ? AND item_no = ?", (room, item_no)
            )
            remaining = conn.execute(
                "SELECT item_no FROM shop_items WHERE room = ? ORDER BY item_no",
                (room,),
            ).fetchall()
            for new_no, item in enumerate(remaining, start=1):
                if item["item_no"] != new_no:
                    conn.execute(
                        "UPDATE shop_items SET item_no = ? WHERE room = ? AND item_no = ?",
                        (new_no, room, item["item_no"]),
                    )
        return (row["name"], len(remaining))

    def record_purchase(
        self, room: str, user_key: str, nickname: str, item_name: str, price: int
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO shop_purchases (room, user_key, nickname, item_name, price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (room, user_key, nickname, item_name, price),
            )

    def list_purchases(
        self, room: str, limit: int = 20
    ) -> list[tuple[int, str, str, int, str]]:
        """최근 구매 내역 (번호, 닉네임, 상품명, 가격, 구매시각)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, nickname, item_name, price, bought_at FROM shop_purchases
                WHERE room = ? ORDER BY id DESC LIMIT ?
                """,
                (room, limit),
            ).fetchall()
        return [
            (
                row["id"],
                row["nickname"],
                row["item_name"],
                row["price"],
                row["bought_at"],
            )
            for row in rows
        ]

    def remove_purchase(self, room: str, purchase_id: int) -> tuple[str, str] | None:
        """구매 내역 하나를 지우고 (닉네임, 상품명)을 돌려준다."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT nickname, item_name FROM shop_purchases WHERE room = ? AND id = ?",
                (room, purchase_id),
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM shop_purchases WHERE id = ?", (purchase_id,))
        return (row["nickname"], row["item_name"])

    def clear_purchases(self, room: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM shop_purchases WHERE room = ?", (room,)
            )
        return cursor.rowcount

    def daily_ranking_with_keys(
        self, room: str, chat_date: str, limit: int = 10
    ) -> list[tuple[str, str, int]]:
        """그날 채팅 순위 (user_key, 닉네임, 채팅수). 포인트 지급에 쓴다."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_key, display_name, message_count AS n
                FROM chat_stats
                WHERE room = ? AND chat_date = ? AND message_count > 0
                ORDER BY n DESC, user_key
                LIMIT ?
                """,
                (room, chat_date, limit),
            ).fetchall()
        return [(row["user_key"], row["display_name"], row["n"]) for row in rows]

    def rooms_with_chat_on(self, chat_date: str) -> list[str]:
        """그날 채팅이 있었던 방 목록(일일랭킹 포인트 지급 대상)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT room FROM chat_stats WHERE chat_date = ? AND message_count > 0",
                (chat_date,),
            ).fetchall()
        return [row["room"] for row in rows]

    def claim_rank_reward(self, room: str, reward_date: str) -> bool:
        """그 방 그날의 랭킹 포인트 지급권을 잡는다. 이미 줬으면 False."""
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO rank_rewards (room, reward_date) VALUES (?, ?)",
                    (room, reward_date),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def open_raid(
        self,
        room: str,
        pokemon_key: str,
        pokemon_display: str,
        host: str,
        friend_code: str,
        created_by: str,
    ) -> None:
        """레이드 모집 세션을 연다. 같은 포켓몬·모집자의 이전 명단은 비운다."""
        host_key = host.lower()
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM raid_signups
                WHERE room = ? AND pokemon_key = ? AND host_key = ?
                """,
                (room, pokemon_key, host_key),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO raid_sessions
                    (room, pokemon_key, host_key, pokemon_display, host_display,
                     friend_code, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (room, pokemon_key, host_key, pokemon_display, host, friend_code, created_by),
            )

    def get_raid_session(
        self,
        room: str,
        pokemon_key: str,
        host_key: str,
    ) -> tuple[str, str, str, str] | None:
        """(포켓몬 표시명, 모집자 표시명, 친구코드, 개설자 user_key)를 돌려준다."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT pokemon_display, host_display, friend_code, created_by
                FROM raid_sessions
                WHERE room = ? AND pokemon_key = ? AND host_key = ?
                """,
                (room, pokemon_key, host_key),
            ).fetchone()
        if row is None:
            return None
        return (
            row["pokemon_display"],
            row["host_display"],
            row["friend_code"],
            row["created_by"],
        )

    def add_raid_signup(
        self,
        room: str,
        pokemon_key: str,
        host_key: str,
        nickname: str,
    ) -> tuple[bool, int]:
        """모집 명단에 닉네임을 올린다. (새로 등록됐는지, 현재 인원)을 돌려준다."""
        nickname_key = nickname.lower()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT 1 FROM raid_signups
                WHERE room = ? AND pokemon_key = ? AND host_key = ? AND nickname_key = ?
                """,
                (room, pokemon_key, host_key, nickname_key),
            ).fetchone()
            if not existing:
                conn.execute(
                    """
                    INSERT INTO raid_signups
                        (room, pokemon_key, host_key, nickname_key, nickname)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (room, pokemon_key, host_key, nickname_key, nickname),
                )
            count = conn.execute(
                """
                SELECT COUNT(*) AS n FROM raid_signups
                WHERE room = ? AND pokemon_key = ? AND host_key = ?
                """,
                (room, pokemon_key, host_key),
            ).fetchone()["n"]
        return existing is None, count

    def remove_raid_signup(
        self,
        room: str,
        pokemon_key: str,
        host_key: str,
        nickname: str,
    ) -> tuple[bool, int]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM raid_signups
                WHERE room = ? AND pokemon_key = ? AND host_key = ? AND nickname_key = ?
                """,
                (room, pokemon_key, host_key, nickname.lower()),
            )
            count = conn.execute(
                """
                SELECT COUNT(*) AS n FROM raid_signups
                WHERE room = ? AND pokemon_key = ? AND host_key = ?
                """,
                (room, pokemon_key, host_key),
            ).fetchone()["n"]
        return cursor.rowcount > 0, count

    def list_raid_signups(
        self,
        room: str,
        pokemon_key: str,
        host_key: str,
    ) -> list[str]:
        """정렬된 닉네임 목록을 돌려준다."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT nickname FROM raid_signups
                WHERE room = ? AND pokemon_key = ? AND host_key = ?
                """,
                (room, pokemon_key, host_key),
            ).fetchall()
        # 숫자 -> 영문 순. 영문은 같은 글자면 소문자 먼저(aAbBcC 순).
        return sorted((row["nickname"] for row in rows), key=_raid_sort_key)

    def refresh_admin_display_name(self, user_key: str, display_name: str) -> None:
        """관리자/오너의 표시 닉네임을 최신으로 갱신한다(바뀌었을 때만)."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE room_admins SET display_name = ?
                WHERE user_key = ? AND display_name != ?
                """,
                (display_name, user_key, display_name),
            )

    def record_chat_message(
        self,
        room: str,
        user_key: str,
        display_name: str,
        today: str,
    ) -> None:
        """방·사람·날짜별 채팅 수를 1 올린다."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_stats (room, user_key, display_name, chat_date, message_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(room, user_key, chat_date)
                DO UPDATE SET message_count = message_count + 1,
                              display_name = excluded.display_name
                """,
                (room, user_key, display_name, today),
            )

    def raffle_pool(self, room: str, today: str) -> list[tuple[str, int]]:
        """추첨 대상: 오늘(today) 채팅이 1회 이상인 사람의 (닉네임, 오늘 활동량).
        오늘 활동이 없는 사람은 제외된다. 봇 자기 메시지는 애초에 집계되지
        않으므로 자연히 제외된다."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT display_name, message_count AS n
                FROM chat_stats
                WHERE room = ? AND chat_date = ? AND message_count > 0
                """,
                (room, today),
            ).fetchall()
        return [(row["display_name"], row["n"]) for row in rows]

    def chat_ranking(
        self,
        room: str,
        today: str | None = None,
        limit: int = 10,
    ) -> list[tuple[str, int]]:
        """(닉네임, 채팅 수) 순위. today를 주면 그날만, 없으면 누적."""
        with self._connect() as conn:
            if today is None:
                rows = conn.execute(
                    """
                    SELECT display_name, SUM(message_count) AS n
                    FROM chat_stats
                    WHERE room = ?
                    GROUP BY user_key
                    ORDER BY n DESC
                    LIMIT ?
                    """,
                    (room, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT display_name, message_count AS n
                    FROM chat_stats
                    WHERE room = ? AND chat_date = ?
                    ORDER BY n DESC
                    LIMIT ?
                    """,
                    (room, today, limit),
                ).fetchall()
        return [(row["display_name"], row["n"]) for row in rows]

    def record_raid_cancel(self, room: str, nickname: str, today: str) -> tuple[int, int]:
        """취소 횟수를 닉네임별로 누적하고 (오늘 횟수, 누적 횟수)를 돌려준다."""
        nickname_key = nickname.lower()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT cancel_count, daily_count, last_cancel_date
                FROM raid_cancel_stats
                WHERE room = ? AND nickname_key = ?
                """,
                (room, nickname_key),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO raid_cancel_stats
                        (room, nickname_key, nickname, cancel_count, daily_count, last_cancel_date)
                    VALUES (?, ?, ?, 1, 1, ?)
                    """,
                    (room, nickname_key, nickname, today),
                )
                return 1, 1

            total = row["cancel_count"] + 1
            daily = row["daily_count"] + 1 if row["last_cancel_date"] == today else 1
            conn.execute(
                """
                UPDATE raid_cancel_stats
                SET cancel_count = ?, daily_count = ?, last_cancel_date = ?,
                    nickname = ?, last_cancel_at = CURRENT_TIMESTAMP
                WHERE room = ? AND nickname_key = ?
                """,
                (total, daily, today, nickname, room, nickname_key),
            )
            return daily, total

    def list_raid_cancel_stats(self, room: str, today: str) -> list[tuple[str, int]]:
        """오늘 취소한 모든 사람을 (닉네임, 오늘 횟수)로, 많은 순서대로."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT nickname, daily_count
                FROM raid_cancel_stats
                WHERE room = ? AND last_cancel_date = ?
                ORDER BY daily_count DESC, last_cancel_at DESC
                """,
                (room, today),
            ).fetchall()
        return [(row["nickname"], row["daily_count"]) for row in rows]

    def list_raid_sessions(self, room: str) -> list[tuple[str, str, int]]:
        """(포켓몬 표시명, 모집자 표시명, 인원) 목록. 개설 순서대로."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.pokemon_display, s.host_display,
                       (SELECT COUNT(*) FROM raid_signups g
                        WHERE g.room = s.room
                          AND g.pokemon_key = s.pokemon_key
                          AND g.host_key = s.host_key) AS n
                FROM raid_sessions s
                WHERE s.room = ?
                ORDER BY s.created_at
                """,
                (room,),
            ).fetchall()
        return [(row["pokemon_display"], row["host_display"], row["n"]) for row in rows]

    def close_raid(self, room: str, pokemon_key: str, host_key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM raid_sessions WHERE room = ? AND pokemon_key = ? AND host_key = ?",
                (room, pokemon_key, host_key),
            )
            conn.execute(
                "DELETE FROM raid_signups WHERE room = ? AND pokemon_key = ? AND host_key = ?",
                (room, pokemon_key, host_key),
            )

    def clear_raids(self, room: str) -> int:
        """방의 모든 모집 세션과 명단을 지우고, 지운 세션 수를 돌려준다."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM raid_sessions WHERE room = ?", (room,)
            )
            conn.execute("DELETE FROM raid_signups WHERE room = ?", (room,))
            return cursor.rowcount

    @staticmethod
    def _hash_secret(salt: str, value: str) -> str:
        return hashlib.sha256((salt + value).encode("utf-8")).hexdigest()

    def has_room_password(self, room: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM room_passwords WHERE room = ?", (room,)
            ).fetchone()
        return row is not None

    def set_room_password(self, room: str, password: str, recovery_word: str) -> bool:
        """방 비밀번호를 처음 설정한다. 이미 있으면 False."""
        if self.has_room_password(room):
            return False
        salt = secrets.token_hex(16)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO room_passwords (room, salt, password_hash, recovery_hash)
                VALUES (?, ?, ?, ?)
                """,
                (
                    room,
                    salt,
                    self._hash_secret(salt, password),
                    self._hash_secret(salt, recovery_word),
                ),
            )
        return True

    def check_room_password(self, room: str, password: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT salt, password_hash FROM room_passwords WHERE room = ?",
                (room,),
            ).fetchone()
        if row is None:
            return False
        return self._hash_secret(row["salt"], password) == row["password_hash"]

    def change_room_password(
        self,
        room: str,
        recovery_word: str,
        new_password: str,
    ) -> str:
        """복구 단어가 맞으면 비밀번호를 바꾼다. 'ok' | 'missing' | 'wrong'."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT salt, recovery_hash FROM room_passwords WHERE room = ?",
                (room,),
            ).fetchone()
            if row is None:
                return "missing"
            if self._hash_secret(row["salt"], recovery_word) != row["recovery_hash"]:
                return "wrong"
            new_salt = secrets.token_hex(16)
            conn.execute(
                """
                UPDATE room_passwords
                SET salt = ?, password_hash = ?, recovery_hash = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE room = ?
                """,
                (
                    new_salt,
                    self._hash_secret(new_salt, new_password),
                    self._hash_secret(new_salt, recovery_word),
                    room,
                ),
            )
        return "ok"

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

    def migrate_room(self, old_room: str, new_room: str) -> dict[str, int]:
        """방 제목이 바뀌었을 때 방 이름 기준으로 저장된 데이터를 새 이름으로 옮긴다.

        새 이름 쪽에 이미 생긴 데이터와 겹치면 명령어/관리자는 새 이름 쪽을
        남기고, 출석은 일수와 포인트를 합산한다.
        """
        moved: dict[str, int] = {}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_key, display_name, last_check_in, total_days, points
                FROM attendance WHERE room = ?
                """,
                (old_room,),
            ).fetchall()
            for row in rows:
                existing = conn.execute(
                    "SELECT total_days, points FROM attendance WHERE room = ? AND user_key = ?",
                    (new_room, row["user_key"]),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE attendance
                        SET total_days = ?, points = ?,
                            last_check_in = MAX(last_check_in, ?)
                        WHERE room = ? AND user_key = ?
                        """,
                        (
                            existing["total_days"] + row["total_days"],
                            existing["points"] + row["points"],
                            row["last_check_in"],
                            new_room,
                            row["user_key"],
                        ),
                    )
                    conn.execute(
                        "DELETE FROM attendance WHERE room = ? AND user_key = ?",
                        (old_room, row["user_key"]),
                    )
                else:
                    conn.execute(
                        "UPDATE attendance SET room = ? WHERE room = ? AND user_key = ?",
                        (new_room, old_room, row["user_key"]),
                    )
            moved["attendance"] = len(rows)

            for table, key_col in (
                ("custom_commands", "command"),
                ("room_admins", "user_key"),
                ("room_join_counts", "user_id"),
                ("warn_permissions", "user_key"),
                ("shop_items", "item_no"),
                ("rank_rewards", "reward_date"),
            ):
                conn.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE room = ? AND {key_col} IN (
                        SELECT {key_col} FROM {table} WHERE room = ?
                    )
                    """,
                    (old_room, new_room),
                )
                cursor = conn.execute(
                    f"UPDATE {table} SET room = ? WHERE room = ?",
                    (new_room, old_room),
                )
                moved[table] = cursor.rowcount

            # 경고·구매 기록은 사람당 여러 건이라 중복 제거 없이 통째로 옮긴다.
            for table in ("warnings", "shop_purchases"):
                cursor = conn.execute(
                    f"UPDATE {table} SET room = ? WHERE room = ?",
                    (new_room, old_room),
                )
                moved[table] = cursor.rowcount

            # 방 단위 설정은 새 이름 쪽을 남기고 옛 이름 것을 옮긴다.
            conn.execute(
                "DELETE FROM event_notifications WHERE room = ? AND EXISTS "
                "(SELECT 1 FROM event_notifications WHERE room = ?)",
                (old_room, new_room),
            )
            conn.execute(
                "UPDATE event_notifications SET room = ? WHERE room = ?",
                (new_room, old_room),
            )

            cursor = conn.execute(
                "UPDATE control_room_targets SET target_room = ? WHERE target_room = ?",
                (new_room, old_room),
            )
            moved["control_room_targets"] = cursor.rowcount
            # 옛 방 자체가 관리방으로 쓰이던 경우도 함께 옮긴다.
            conn.execute(
                """
                DELETE FROM control_room_targets
                WHERE control_room = ? AND user_key IN (
                    SELECT user_key FROM control_room_targets WHERE control_room = ?
                )
                """,
                (old_room, new_room),
            )
            conn.execute(
                "UPDATE control_room_targets SET control_room = ? WHERE control_room = ?",
                (new_room, old_room),
            )
        return moved

    def touch_room(self, chat_id: str, room_name: str) -> dict[str, object]:
        """Iris가 방 메시지를 보낼 때마다 chat_id↔현재 이름을 최신으로 유지한다.

        chat_id는 카톡이 방마다 부여하는 불변 식별자라 방 제목이 바뀌어도
        같은 방으로 이어진다. 이미 아는 chat_id인데 이름이 바뀌었으면
        이름 기준으로 저장된 데이터를 새 이름으로 자동 이전한다.
        반환: {"token": 전용링크토큰, "renamed_from": 옛이름 or None}.
        """
        chat_id = (chat_id or "").strip()
        room_name = (room_name or "").strip()
        if not chat_id or not room_name:
            return {"token": None, "renamed_from": None}
        with self._connect() as conn:
            row = conn.execute(
                "SELECT room_name, site_token FROM rooms WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if row is None:
                token = secrets.token_urlsafe(12)
                conn.execute(
                    "INSERT INTO rooms (chat_id, room_name, site_token) VALUES (?, ?, ?)",
                    (chat_id, room_name, token),
                )
                return {"token": token, "renamed_from": None}
            token = row["site_token"]
            old_name = row["room_name"]
            if old_name == room_name:
                return {"token": token, "renamed_from": None}
        # 이름이 바뀌었다 — 이름 기준 데이터를 옮기고 레지스트리를 갱신한다.
        self.migrate_room(old_name, room_name)
        with self._connect() as conn:
            conn.execute(
                "UPDATE rooms SET room_name = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE chat_id = ?",
                (room_name, chat_id),
            )
        return {"token": token, "renamed_from": old_name}

    def get_room_name_by_token(self, site_token: str) -> str | None:
        """전용 링크 토큰으로 현재 방 이름을 찾는다."""
        token = (site_token or "").strip()
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT room_name FROM rooms WHERE site_token = ?",
                (token,),
            ).fetchone()
        return row["room_name"] if row else None

    def record_member_join(self, room: str, user_id: str, nickname: str) -> tuple[int, bool]:
        """입장 이벤트를 방·사용자별로 센다. (입장횟수, 카운트했는지) 를 준다.

        방(chat_id로 고정된 이름)마다 따로 세므로 다른 방과 합쳐지지 않는다.
        강퇴 후 복귀(pardon_next)는 본인 의사가 아니라 카운트하지 않는다.
        """
        room = (room or "").strip()
        user_id = (user_id or "").strip()
        if not room or not user_id:
            return (0, False)
        nickname = (nickname or "").strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT join_count, pardon_next FROM room_join_counts "
                "WHERE room = ? AND user_id = ?",
                (room, user_id),
            ).fetchone()
            if row and row["pardon_next"]:
                # 강퇴 후 복귀 - 카운트 그대로 두고 방에 있음 표시만 한다.
                conn.execute(
                    "UPDATE room_join_counts SET present = 1, pardon_next = 0, "
                    "nickname = ?, last_join_at = CURRENT_TIMESTAMP "
                    "WHERE room = ? AND user_id = ?",
                    (nickname, room, user_id),
                )
                return (row["join_count"], False)
            new_count = (row["join_count"] if row else 0) + 1
            conn.execute(
                """
                INSERT INTO room_join_counts
                    (room, user_id, nickname, join_count, present, last_join_at)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(room, user_id) DO UPDATE SET
                    join_count = excluded.join_count,
                    nickname = excluded.nickname,
                    present = 1,
                    last_join_at = CURRENT_TIMESTAMP
                """,
                (room, user_id, nickname, new_count),
            )
        return (new_count, True)

    def seed_member_present(self, room: str, user_id: str, nickname: str) -> None:
        """이미 방에 있는 사람을 '입장 1회'로 기준 잡는다. (추적 시작 전 멤버용)

        채팅을 했다는 건 지금 방에 있다는 뜻이라, 기록이 없으면 입장 1회로
        넣어둔다. 그래야 나중에 나갔다 들어오면 자동으로 2회차가 된다.
        이미 기록이 있으면 닉네임만 갱신하고 입장 횟수는 건드리지 않는다.
        """
        room = (room or "").strip()
        user_id = (user_id or "").strip()
        if not room or not user_id:
            return
        nickname = (nickname or "").strip()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO room_join_counts
                    (room, user_id, nickname, join_count, present, pardon_next, last_join_at)
                VALUES (?, ?, ?, 1, 1, 0, CURRENT_TIMESTAMP)
                ON CONFLICT(room, user_id) DO UPDATE SET nickname = excluded.nickname
                """,
                (room, user_id, nickname),
            )

    def mark_member_left(
        self, room: str, user_id: str, nickname: str = "", kicked: bool = False
    ) -> None:
        """방을 떠난 사람은 present=0 으로 둔다.

        기록이 없던 사람(추적 시작 전부터 있던 잠수 유저)도 나가는 순간
        방에 있었다는 게 확인되므로 입장 1회로 기준을 잡는다. 그래야 다시
        들어오면 자동으로 2회차가 된다. 자발적 퇴장은 입장 횟수를 남겨 이어
        세고, 강퇴(kicked)는 다음 입장 한 번을 카운트에서 면제(pardon_next)한다.
        """
        room = (room or "").strip()
        user_id = (user_id or "").strip()
        if not room or not user_id:
            return
        nickname = (nickname or "").strip()
        pardon = 1 if kicked else 0
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO room_join_counts
                    (room, user_id, nickname, join_count, present, pardon_next, last_join_at)
                VALUES (?, ?, ?, 1, 0, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(room, user_id) DO UPDATE SET
                    present = 0,
                    pardon_next = CASE WHEN ? = 1 THEN 1 ELSE pardon_next END,
                    nickname = CASE
                        WHEN excluded.nickname != '' THEN excluded.nickname
                        ELSE room_join_counts.nickname
                    END
                """,
                (room, user_id, nickname, pardon, pardon),
            )

    def join_ranking(self, room: str, min_count: int = 2) -> list[tuple[str, int]]:
        """현재 방에 있는 재입장(들낙) 인원 전원을 횟수 많은 순으로."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT nickname, join_count FROM room_join_counts
                WHERE room = ? AND join_count >= ? AND present = 1
                ORDER BY join_count DESC, last_join_at DESC
                """,
                (room, min_count),
            ).fetchall()
        return [(row["nickname"], row["join_count"]) for row in rows]

    def join_count_for_nickname(self, room: str, nickname: str) -> tuple[str, int] | None:
        """닉네임으로 현재 방에 있는 그 사람의 입장 횟수를 찾는다."""
        nickname = (nickname or "").strip()
        if not nickname:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT nickname, join_count FROM room_join_counts
                WHERE room = ? AND nickname = ? AND present = 1
                ORDER BY last_join_at DESC LIMIT 1
                """,
                (room, nickname),
            ).fetchone()
        return (row["nickname"], row["join_count"]) if row else None

    def resolve_user_key_by_nickname(self, room: str, nickname: str) -> str | None:
        """방에서 그 닉네임을 쓴 사람의 user_key(고정 식별자)를 찾는다.

        경고를 닉네임이 아니라 이 user_key 로 저장해야 나중에 닉네임을 바꿔도
        추적된다. 채팅 기록(chat_stats)을 우선 보고, 없으면 입장 기록을 본다.
        """
        room = (room or "").strip()
        nickname = (nickname or "").strip()
        if not room or not nickname:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_key FROM chat_stats
                WHERE room = ? AND display_name = ?
                ORDER BY chat_date DESC, message_count DESC LIMIT 1
                """,
                (room, nickname),
            ).fetchone()
            if row:
                return row["user_key"]
            row = conn.execute(
                """
                SELECT user_id FROM room_join_counts
                WHERE room = ? AND nickname = ?
                ORDER BY last_join_at DESC LIMIT 1
                """,
                (room, nickname),
            ).fetchone()
        return f"iris:{row['user_id']}" if row else None

    def latest_nickname(self, room: str, user_key: str) -> str | None:
        """user_key 의 가장 최근 닉네임. 닉네임을 바꿨어도 최신 것을 돌려준다."""
        room = (room or "").strip()
        user_key = (user_key or "").strip()
        if not room or not user_key:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT display_name FROM chat_stats
                WHERE room = ? AND user_key = ?
                ORDER BY chat_date DESC LIMIT 1
                """,
                (room, user_key),
            ).fetchone()
        return row["display_name"] if row else None

    def add_warning(
        self,
        room: str,
        user_key: str,
        nickname: str,
        reason: str,
        warned_by: str,
        kind: str = "warn",
    ) -> int:
        """경고/칭찬을 하나 추가하고 그 사람의 누적 횟수를 돌려준다."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO warnings (room, user_key, nickname, reason, warned_by, kind)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (room, user_key, nickname, reason, warned_by, kind),
            )
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM warnings "
                "WHERE room = ? AND user_key = ? AND kind = ?",
                (room, user_key, kind),
            ).fetchone()
        return row["n"]

    def list_warnings(
        self, room: str, kind: str = "warn"
    ) -> list[tuple[str, int, list[str]]]:
        """명단. 사람별로 (user_key, 누적횟수, 사유목록)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_key, reason FROM warnings
                WHERE room = ? AND kind = ? ORDER BY warned_at
                """,
                (room, kind),
            ).fetchall()
        grouped: dict[str, list[str]] = {}
        for row in rows:
            grouped.setdefault(row["user_key"], []).append(row["reason"])
        return [(key, len(reasons), reasons) for key, reasons in grouped.items()]

    def remove_warnings(self, room: str, user_key: str, kind: str = "warn") -> int:
        """그 사람의 기록을 전부 지운다. 지운 개수를 돌려준다."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM warnings WHERE room = ? AND user_key = ? AND kind = ?",
                (room, user_key, kind),
            )
        return cursor.rowcount

    def remove_one_warning(
        self, room: str, user_key: str, reason: str, kind: str = "warn"
    ) -> bool:
        """사유가 같은 기록 하나만 지운다(같은 사유가 여럿이면 최근 것)."""
        reason = (reason or "").strip()
        if not reason:
            return False
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM warnings
                WHERE room = ? AND user_key = ? AND reason = ? AND kind = ?
                ORDER BY id DESC LIMIT 1
                """,
                (room, user_key, reason, kind),
            ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM warnings WHERE id = ?", (row["id"],))
        return True

    def warning_reasons(
        self, room: str, user_key: str, kind: str = "warn"
    ) -> list[str]:
        """그 사람에게 남아 있는 사유 목록."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT reason FROM warnings "
                "WHERE room = ? AND user_key = ? AND kind = ? ORDER BY id",
                (room, user_key, kind),
            ).fetchall()
        return [row["reason"] for row in rows]

    def grant_warn_permission(
        self, room: str, user_key: str, nickname: str, granted_by: str
    ) -> None:
        """그 방에서 경고 명령을 쓸 수 있는 권한을 준다."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO warn_permissions (room, user_key, nickname, granted_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(room, user_key) DO UPDATE SET
                    nickname = excluded.nickname, granted_by = excluded.granted_by
                """,
                (room, user_key, nickname, granted_by),
            )

    def revoke_warn_permission(self, room: str, user_key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM warn_permissions WHERE room = ? AND user_key = ?",
                (room, user_key),
            )
        return cursor.rowcount > 0

    def has_warn_permission(self, room: str, user_key: str) -> bool:
        room = (room or "").strip()
        user_key = (user_key or "").strip()
        if not room or not user_key:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM warn_permissions WHERE room = ? AND user_key = ?",
                (room, user_key),
            ).fetchone()
        return row is not None

    def list_warn_permissions(self, room: str) -> list[str]:
        """경고 권한을 가진 사람들의 user_key 목록."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_key FROM warn_permissions WHERE room = ? ORDER BY granted_at",
                (room,),
            ).fetchall()
        return [row["user_key"] for row in rows]

    def set_event_notify(self, room: str, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO event_notifications (room, enabled) VALUES (?, ?)
                ON CONFLICT(room) DO UPDATE SET enabled = excluded.enabled
                """,
                (room, 1 if enabled else 0),
            )

    def is_event_notify_enabled(self, room: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT enabled FROM event_notifications WHERE room = ?", (room,)
            ).fetchone()
        return bool(row and row["enabled"])

    def event_notify_targets(self, today: str) -> list[str]:
        """오늘 아직 브리핑을 못 받은, 알림 켜진 방 목록."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT room FROM event_notifications
                WHERE enabled = 1 AND last_sent_date != ?
                """,
                (today,),
            ).fetchall()
        return [row["room"] for row in rows]

    def mark_event_notify_sent(self, room: str, today: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE event_notifications SET last_sent_date = ? WHERE room = ?",
                (today, room),
            )

    def get_chat_id_for_room(self, room_name: str) -> str | None:
        """방 이름으로 chat_id를 찾는다. 알림을 보낼 때 필요하다."""
        name = (room_name or "").strip()
        if not name:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT chat_id FROM rooms WHERE room_name = ? "
                "ORDER BY updated_at DESC LIMIT 1",
                (name,),
            ).fetchone()
        return row["chat_id"] if row else None

    def list_rooms(self) -> list[tuple[str, str]]:
        """등록된 방과 각 전용 토큰 목록. (개인톡으로 링크 안내할 때 쓴다)"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT room_name, site_token FROM rooms ORDER BY updated_at DESC"
            ).fetchall()
        return [(row["room_name"], row["site_token"]) for row in rows]

    def get_site_token_for_room_name(self, room_name: str) -> str | None:
        """현재 방 이름으로 전용 링크 토큰을 찾는다(링크 안내용)."""
        name = (room_name or "").strip()
        if not name:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT site_token FROM rooms WHERE room_name = ? "
                "ORDER BY updated_at DESC LIMIT 1",
                (name,),
            ).fetchone()
        return row["site_token"] if row else None

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
