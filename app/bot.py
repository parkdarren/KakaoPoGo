from __future__ import annotations

import os
from dataclasses import dataclass

from app.admin_store import AdminStore, ChatUser
from app.pogo_api import (
    PogoApiClient,
    format_custom_cp_reply,
    format_dex_reply,
    format_perfect_cp_reply,
    format_weakness_reply,
)


OWNER_SETUP_CODE = os.getenv("OWNER_SETUP_CODE", "change-me")
PUBLIC_COMMANDS = [
    "!도감 피카츄",
    "!100 자시안 검왕",
    "!약점 기라티나 오리진",
    "!cp 피카츄 25 15/15/15",
    "!관리자요청",
    "!도움말",
]
ADMIN_COMMANDS = [
    "!대상방설정 공개방이름",
    "!대상방확인",
    "!명령어추가 공지 내용",
    "!명령어수정 공지 새내용",
    "!명령어삭제 공지",
]
OWNER_COMMANDS = [
    "!오너등록 코드",
    "!관리자요청목록",
    "!관리자승인 번호",
    "!관리자거절 번호",
    "!관리자삭제 번호",
    "!관리자목록",
]


@dataclass(frozen=True)
class BotResponse:
    reply: str


def parse_command(text: str) -> tuple[str, str] | None:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None

    command = parts[0].lower()
    query = parts[1].strip() if len(parts) > 1 else ""
    if command in ("!도감", "!dex"):
        return "dex", query
    if command in ("!100", "!백"):
        return "perfect", query
    if command in ("!약점", "!weak"):
        return "weakness", query
    if command in ("!cp",):
        return "cp", query
    if command in ("!오너등록", "!owner"):
        return "owner_setup", query
    if command in ("!관리자요청",):
        return "admin_request", query
    if command in ("!관리자요청목록",):
        return "admin_request_list", query
    if command in ("!관리자승인",):
        return "admin_approve", query
    if command in ("!관리자거절",):
        return "admin_reject", query
    if command in ("!관리자목록",):
        return "admin_list", query
    if command in ("!관리자삭제",):
        return "admin_remove", query
    if command in ("!대상방설정",):
        return "target_set", query
    if command in ("!대상방확인",):
        return "target_show", query
    if command in ("!명령어추가", "!명령어수정"):
        return "custom_upsert", query
    if command in ("!명령어삭제",):
        return "custom_delete", query
    if command in ("!명령어목록",):
        return "custom_list", query
    if command in ("!help", "!도움말"):
        return "help", ""
    if command.startswith("!") and len(command) > 1:
        return "custom_run", command[1:]
    return None


def parse_cp_query(query: str) -> tuple[str, float, tuple[int, int, int]]:
    parts = query.rsplit(maxsplit=2)
    if len(parts) != 3:
        raise ValueError("CP_QUERY_FORMAT")

    pokemon_query, level_text, iv_text = parts
    level = float(level_text)
    if level < 1 or level > 51 or level * 2 != int(level * 2):
        raise ValueError("CP_LEVEL_RANGE")

    iv_parts = iv_text.replace("-", "/").split("/")
    if len(iv_parts) != 3:
        raise ValueError("CP_IV_FORMAT")
    ivs = tuple(int(part) for part in iv_parts)
    if any(iv < 0 or iv > 15 for iv in ivs):
        raise ValueError("CP_IV_RANGE")

    return pokemon_query, level, ivs


class PokemonGoBot:
    def __init__(
        self,
        pogo_client: PogoApiClient | None = None,
        admin_store: AdminStore | None = None,
    ) -> None:
        self.pogo_client = pogo_client or PogoApiClient()
        self.admin_store = admin_store or AdminStore()

    async def handle(
        self,
        text: str,
        room: str = "local",
        sender: str = "local",
        user_key: str | None = None,
    ) -> BotResponse:
        parsed = parse_command(text)
        if parsed is None:
            return BotResponse("알 수 없는 명령어입니다. !도움말 을 입력해 주세요.")

        command, query = parsed
        user = self._chat_user(room, sender, user_key)
        target_user = self._target_user(user)
        if command == "help":
            return BotResponse(self._handle_public_help(target_user))

        if command == "owner_setup":
            return BotResponse(self._handle_owner_setup(user, query))

        if command == "admin_request":
            return BotResponse(self._handle_admin_request(user))

        if command == "admin_request_list":
            return BotResponse(self._handle_admin_request_list(target_user))

        if command == "admin_approve":
            return BotResponse(self._handle_admin_approve(target_user, query))

        if command == "admin_reject":
            return BotResponse(self._handle_admin_reject(target_user, query))

        if command == "admin_list":
            return BotResponse(self._handle_admin_list(target_user))

        if command == "admin_remove":
            return BotResponse(self._handle_admin_remove(target_user, query))

        if command == "target_set":
            return BotResponse(self._handle_target_set(user, query))

        if command == "target_show":
            return BotResponse(self._handle_target_show(user))

        if command == "custom_upsert":
            return BotResponse(self._handle_custom_upsert(target_user, query))

        if command == "custom_delete":
            return BotResponse(self._handle_custom_delete(target_user, query))

        if command == "custom_list":
            return BotResponse(self._handle_custom_list(target_user))

        if command == "custom_run":
            custom = self.admin_store.get_custom_command(
                target_user.room,
                self._normalize_custom_command(query),
            )
            if custom:
                return BotResponse(custom.response)
            return BotResponse("알 수 없는 명령어입니다. !도움말 을 입력해 주세요.")

        if command == "dex":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: !도감 피카츄")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다. 한글명 매핑을 추가해야 할 수도 있습니다.")
            return BotResponse(format_dex_reply(entry))

        if command == "perfect":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: !100 자시안")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다.")
            return BotResponse(format_perfect_cp_reply(entry))

        if command == "weakness":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: !약점 기라티나 오리진")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다.")
            return BotResponse(format_weakness_reply(entry))

        if command == "cp":
            try:
                pokemon_query, level, ivs = parse_cp_query(query)
            except ValueError:
                return BotResponse("형식은 이렇게 입력해 주세요. 예: !cp 피카츄 25 15/15/15")
            try:
                entry = await self.pogo_client.get_dex_entry(pokemon_query)
            except LookupError:
                return BotResponse(f"'{pokemon_query}' 포켓몬을 찾지 못했습니다.")
            return BotResponse(format_custom_cp_reply(entry, level, *ivs))

        return BotResponse(self._handle_command_list(target_user))

    @staticmethod
    def _chat_user(room: str, sender: str, user_key: str | None) -> ChatUser:
        clean_room = room.strip() or "local"
        clean_sender = sender.strip() or "unknown"
        clean_key = (user_key or "").strip() or f"sender:{clean_sender}"
        return ChatUser(room=clean_room, sender=clean_sender, user_key=clean_key)

    def _target_user(self, user: ChatUser) -> ChatUser:
        target_room = self.admin_store.get_control_target(user.room, user.user_key)
        if not target_room:
            return user
        return ChatUser(room=target_room, sender=user.sender, user_key=user.user_key)

    def _handle_target_set(self, user: ChatUser, target_room: str) -> str:
        clean_target = target_room.strip()
        if not clean_target:
            return "대상 공개방 이름을 입력해 주세요. 예: !대상방설정 포켓몬고 레이드방"

        target_user = ChatUser(
            room=clean_target,
            sender=user.sender,
            user_key=user.user_key,
        )
        if not self.admin_store.is_admin_or_owner(target_user):
            return "그 방의 owner 또는 admin으로 등록된 사람만 대상방을 설정할 수 있습니다."

        self.admin_store.set_control_target(
            user.room,
            user.user_key,
            clean_target,
        )
        return f"이 방의 관리 대상이 '{clean_target}' 방으로 설정되었습니다."

    def _handle_target_show(self, user: ChatUser) -> str:
        target_room = self.admin_store.get_control_target(user.room, user.user_key)
        if not target_room:
            return "설정된 대상방이 없습니다."
        return f"현재 대상방: {target_room}"

    def _handle_owner_setup(self, user: ChatUser, code: str) -> str:
        if code.strip() != OWNER_SETUP_CODE:
            return "오너 등록 코드가 맞지 않습니다."
        if self.admin_store.has_owner(user.room):
            if self.admin_store.is_owner(user):
                self.admin_store.replace_owner(user)
                return "이미 이 방의 owner로 등록되어 있습니다."
            return "이 방에는 이미 owner가 등록되어 있습니다."

        self.admin_store.add_owner(user)
        return "이 방의 owner로 등록되었습니다."

    def _handle_admin_request(self, user: ChatUser) -> str:
        if self.admin_store.is_admin_or_owner(user):
            return "이미 관리자 권한이 있습니다."

        request_id = self.admin_store.add_admin_request(user)
        return f"관리자 요청을 받았습니다. owner 승인을 기다려 주세요. 요청번호: {request_id}"

    def _handle_admin_request_list(self, user: ChatUser) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        requests = self.admin_store.list_pending_requests(user.room)
        if not requests:
            return "대기 중인 관리자 요청이 없습니다."

        lines = ["관리자 요청 목록"]
        for request in requests:
            lines.append(f"{request.id}. {request.sender}")
        lines.append("승인: !관리자승인 번호")
        lines.append("거절: !관리자거절 번호")
        return "\n".join(lines)

    def _handle_admin_approve(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        request_id = self._parse_request_id(query)
        if request_id is None:
            return "승인할 요청번호를 입력해 주세요. 예: !관리자승인 3"

        request = self.admin_store.get_pending_request(user.room, request_id)
        if not request:
            return "해당 요청번호를 찾지 못했습니다."

        self.admin_store.approve_request(request)
        return f"{request.sender} 님을 admin으로 등록했습니다."

    def _handle_admin_reject(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        request_id = self._parse_request_id(query)
        if request_id is None:
            return "거절할 요청번호를 입력해 주세요. 예: !관리자거절 3"

        request = self.admin_store.reject_request(user.room, request_id)
        if not request:
            return "해당 요청번호를 찾지 못했습니다."
        return f"{request.sender} 님의 관리자 요청을 거절했습니다."

    def _handle_admin_list(self, user: ChatUser) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        admins = self.admin_store.list_admin_records(user.room)
        if not admins:
            return "등록된 관리자가 없습니다."

        lines = ["관리자 목록"]
        for index, (display_name, role, _user_key) in enumerate(admins, start=1):
            lines.append(f"{index}. {display_name}: {role}")
        return "\n".join(lines)

    def _handle_admin_remove(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        admin_index = self._parse_request_id(query)
        if admin_index is None:
            return "삭제할 관리자 번호를 입력해 주세요. 예: !관리자삭제 2"

        admins = self.admin_store.list_admin_records(user.room)
        if admin_index < 1 or admin_index > len(admins):
            return "해당 관리자 번호를 찾지 못했습니다."

        display_name, role, user_key = admins[admin_index - 1]
        if role == "owner":
            return "owner는 관리자삭제로 삭제할 수 없습니다."

        removed = self.admin_store.remove_admin_by_key(user.room, user_key)
        if not removed:
            return "해당 관리자 번호를 찾지 못했습니다."
        return f"{display_name} 님의 admin 권한을 삭제했습니다."

    def _handle_custom_upsert(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_admin_or_owner(user):
            return "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

        parsed = self._parse_custom_upsert(query)
        if parsed is None:
            return "형식은 이렇게 입력해 주세요. 예: !명령어추가 공지 오늘 레이드 8시"

        command, response = parsed
        self.admin_store.upsert_custom_command(
            user.room,
            command,
            response,
            user.sender,
        )
        return f"!{command} 명령어를 저장했습니다."

    def _handle_custom_delete(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_admin_or_owner(user):
            return "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

        command = self._normalize_custom_command(query)
        if not command:
            return "삭제할 명령어 이름을 입력해 주세요. 예: !명령어삭제 공지"

        deleted = self.admin_store.delete_custom_command(user.room, command)
        if not deleted:
            return f"!{command} 명령어를 찾지 못했습니다."
        return f"!{command} 명령어를 삭제했습니다."

    def _handle_custom_list(self, user: ChatUser) -> str:
        return self._handle_command_list(user)

    def _handle_public_help(self, user: ChatUser) -> str:
        lines = [
            "[ 포켓몬GO 도감 봇 사용법 ]",
            "명령어는 앞에 ! 를 붙여서 사용해 주세요.",
            "",
            "1. 포켓몬 도감 보기",
            "!도감 포켓몬이름",
            "예: !도감 피카츄 / !도감 디아루가 / !도감 자시안 검왕",
            "",
            "2. 100% 개체값 CP 보기",
            "!100 포켓몬이름",
            "예: !100 디아루가 / !100 자시안 검왕",
            "",
            "3. 약점 보기",
            "!약점 포켓몬이름",
            "예: !약점 디아루가 / !약점 기라티나 오리진",
            "",
            "4. 원하는 레벨/개체값 CP 계산",
            "!cp 포켓몬이름 레벨 공격/방어/체력",
            "예: !cp 피카츄 40 15/15/15",
        ]

        custom_commands = self.admin_store.list_custom_commands(user.room)
        if custom_commands:
            lines.append("")
            lines.append("방에서 추가된 명령어")
            lines.extend(f"!{command}" for command in custom_commands)

        return "\n".join(lines)

    def _handle_command_list(self, user: ChatUser) -> str:
        role = self.admin_store.get_role(user)
        lines = ["사용 가능한 명령어", *PUBLIC_COMMANDS]

        custom_commands = self.admin_store.list_custom_commands(user.room)
        if custom_commands:
            lines.append("")
            lines.append("방 명령어")
            lines.extend(f"!{command}" for command in custom_commands)

        if role in {"owner", "admin"}:
            lines.append("")
            lines.append("관리 명령어")
            lines.extend(ADMIN_COMMANDS)

        if role == "owner":
            lines.append("")
            lines.append("오너 명령어")
            lines.extend(OWNER_COMMANDS)

        return "\n".join(lines)

    @staticmethod
    def _parse_custom_upsert(query: str) -> tuple[str, str] | None:
        parts = query.strip().split(maxsplit=1)
        if len(parts) != 2:
            return None
        command = PokemonGoBot._normalize_custom_command(parts[0])
        response = parts[1].strip()
        if not command or not response:
            return None
        if command in PokemonGoBot._reserved_custom_commands():
            return None
        return command, response

    @staticmethod
    def _normalize_custom_command(command: str) -> str:
        return command.strip().lower().removeprefix("!").removeprefix("/")

    @staticmethod
    def _reserved_custom_commands() -> set[str]:
        return {
            "도감",
            "dex",
            "100",
            "백",
            "약점",
            "weak",
            "cp",
            "오너등록",
            "owner",
            "관리자요청",
            "관리자요청목록",
            "관리자승인",
            "관리자거절",
            "관리자목록",
            "관리자삭제",
            "대상방설정",
            "대상방확인",
            "명령어추가",
            "명령어수정",
            "명령어삭제",
            "명령어목록",
            "help",
            "도움말",
        }

    @staticmethod
    def _parse_request_id(query: str) -> int | None:
        try:
            return int(query.strip())
        except ValueError:
            return None
