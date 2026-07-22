from __future__ import annotations

import hashlib
import os
import random
import unicodedata
from dataclasses import dataclass
from datetime import date

from app.admin_store import AdminStore, ChatUser
from app.counters import format_counter_reply
from app.events import EventDataUnavailableError, PokemonGoEventClient
from app.pogo_api import (
    MegaUnavailableError,
    PogoApiClient,
    PogoDataUnavailableError,
    format_custom_cp_reply,
    format_dex_reply,
    format_league_reply,
    format_moves_reply,
    format_perfect_cp_reply,
    format_weakness_reply,
)
from app.weather import KoreaWeatherClient, WeatherDataUnavailableError


DATA_UNAVAILABLE_MESSAGE = (
    "포켓몬 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."
)
# 이 길이를 넘는 커스텀 명령어 응답은 카톡에서 제목만 보이고
# 나머지는 '전체보기' 뒤로 접히게 만든다.
FOLD_THRESHOLD = 400
# 긴 메시지를 전체보기로 접는 카톡의 길이 기준을 넘기기 위한 패딩.
# 폭 없는 공백(U+200B)을 첫 줄 뒤에 채워 넣으면 미리보기에는 첫 줄만 남는다.
# 실측: 500자는 폰 전송과 접힘 모두 동작, 2000자는 폰이 전송하지 못한다.
FOLD_PADDING = "​" * 500


def fold_long_reply(content: str) -> str:
    """긴 내용의 첫 줄만 미리보기로 남기고 나머지를 전체보기 뒤로 접는다."""
    if len(content) <= FOLD_THRESHOLD:
        return content
    first_line, separator, rest = content.partition("\n")
    if not separator:
        return content
    return f"{first_line}{FOLD_PADDING}\n{rest}"
# 이모지 스타일 지정자(U+FE0F 등)와 폭 없는 공백처럼 눈에 안 보이는 문자들.
# 방 이름에 섞이면 겉보기에 같은 이름이 서로 다른 방으로 갈라진다.
_ROOM_INVISIBLE_CHARS = dict.fromkeys([
    0xFE0E,  # 텍스트 스타일 지정자
    0xFE0F,  # 이모지 스타일 지정자
    0x200B,  # 폭 없는 공백
    0x200C,  # 폭 없는 비결합자
    0x200D,  # 폭 없는 결합자
    0xFEFF,  # BOM/폭 없는 줄바꿈 방지 공백
])


def normalize_room(room: str) -> str:
    """방 이름에서 보이지 않는 문자를 제거하고 공백을 정리한다.

    폰 알림·웹 입력·카톡 타이핑 등 어느 경로로 들어와도 같은 방은 같은
    문자열이 되도록 모든 입구에서 이 함수를 거친다.
    """
    cleaned = unicodedata.normalize("NFC", room or "").translate(_ROOM_INVISIBLE_CHARS)
    return " ".join(cleaned.split())


DAILY_CHECK_IN_POINTS = 5
DAILY_FORTUNES = [
    "오늘은 100% 개체값이 뜰 운세!",
    "색이 다른 포켓몬이 스쳐 지나갈 예감이에요.",
    "10km 알에서 좋은 소식이 있겠어요.",
    "레이드 막차가 기다리고 있어요. 놓치지 마세요.",
    "오늘 던진 커브볼은 전부 엑설런트!",
    "포켓스탑에서 귀한 아이템이 나올 것 같아요.",
    "트레이드 운이 좋은 날, 행운의 친구가 될지도!",
    "GBL 연승의 기운이 느껴져요.",
    "산책 나가기 좋은 날이에요. 버디가 사탕을 물어올 거예요.",
    "야생에서 뜻밖의 만남이 기다려요.",
    "오늘은 별의모래가 쏟아지는 날!",
    "로켓단을 만나면 이기는 날이에요.",
]
# 날짜에 따라 하나씩 돌아가며 /도움말 첫 줄에 붙는다.
HELP_GREETINGS = [
    "오늘도 즐거운 포켓몬고 하세요!",
    "레이드 가기 전에 명령어 한번 훑고 가세요.",
    "궁금한 포켓몬은 /도감 으로 바로 확인!",
    "오늘은 100% 개체값 뜨는 날입니다.",
    "색이 다른 포켓몬이 기다리고 있을지도?",
    "알 까기 좋은 날씨네요.",
    "포획운 가득한 하루 되세요!",
]


OWNER_SETUP_CODE = os.getenv("OWNER_SETUP_CODE", "")
# 저장소에 공개된 예시 값이므로 실제 등록 코드로 인정하지 않는다.
INSECURE_SETUP_CODES = {"", "change-me"}
BUILTIN_HELP_ENTRIES = [
    (
        "/도감 포켓몬이름",
        "포켓몬 타입, 약점, 100% CP를 확인합니다.\n"
        "메가진화, 이름 일부, 도감 번호도 됩니다.\n"
        "예시 : /도감 디아루가, /도감 메가리자몽Y, /도감 디아, /도감 483",
    ),
    (
        "/스킬 포켓몬이름",
        "포켓몬GO 기술을 한글명으로 확인합니다.\n"
        "예시 : /스킬 피카츄, /스킬 블랙큐레무",
    ),
    (
        "/100 포켓몬이름",
        "100% 개체값 CP만 빠르게 확인합니다.\n"
        "예시 : /100 자시안 검왕",
    ),
    (
        "/약점 포켓몬이름",
        "타입, 약점, 저항을 확인합니다.\n"
        "예시 : /약점 기라티나 오리진",
    ),
    (
        "/카운터 포켓몬이름",
        "레이드 상대할 때 좋은 카운터 포켓몬을 추천합니다.\n"
        "예시 : /카운터 뮤츠, /카운터 메가레쿠쟈",
    ),
    (
        "/cp 포켓몬이름 레벨 공격/방어/체력",
        "원하는 레벨과 IV의 CP를 계산합니다.\n"
        "예시 : /cp 피카츄 40 15/15/15",
    ),
    (
        "/리그 포켓몬이름",
        "슈퍼/하이퍼리그 랭크1 개체값을 계산합니다.\n"
        "예시 : /리그 마릴리, /리그 기라티나 어나더",
    ),
    (
        "/포켓몬고이벤트",
        "진행 중인 이벤트와 앞으로 7일간의 예정 이벤트, 현재 레이드를 확인합니다.\n"
        "줄임말 : /이벤트, /일정",
    ),
    (
        "/날씨",
        "오늘 전국 대표 지역의 오전/오후 날씨를 확인합니다.\n"
        "줄임말 : /전국날씨",
    ),
    (
        "/오늘의포켓몬",
        "오늘의 파트너 포켓몬과 운세를 뽑고 출석체크가 됩니다.\n"
        f"하루 1회, 출석마다 {DAILY_CHECK_IN_POINTS}포인트 적립!\n"
        "줄임말 : /ㅊㅊ, /출첵, /출석",
    ),
    (
        "/출석랭킹",
        "이 방의 출석 순위를 상위 10명까지 보여줍니다.",
    ),
    (
        "/추첨",
        "채팅 활동이 있는 사람 중 1명을 추첨합니다.\n"
        "활동이 많을수록 당첨 확률이 높아요!",
    ),
    (
        "/일일랭킹",
        "오늘 이 방에서 채팅을 많이 한 순위 TOP 10을 보여줍니다.\n"
        "누적 순위는 /랭킹",
    ),
    (
        "/모집 포켓몬이름 모집자닉네임 친구코드",
        "레이드 초대 모집을 엽니다. 누구나 열 수 있어요!\n"
        "예시 : /모집 오리진디아루가 RaidMaster 123456789012",
    ),
    (
        "/참가 닉네임 포켓몬이름 모집자",
        "레이드 초대 명단에 등록합니다. 닉네임은 게임 닉네임으로!\n"
        "예시 : /참가 GoTrainer 오리진디아루가 RaidMaster\n"
        "취소 : /취소 닉네임 포켓몬이름 모집자\n"
        "명단 : /현황 (전체) 또는 /현황 포켓몬이름 모집자\n"
        "마감 : /마감 포켓몬이름 모집자\n"
        "자세한 안내 : /가이드",
    ),
]
RAID_PARTY_SIZE = 10
RAID_GUIDE = (
    "🎫 레이드 초대 시스템 사용법\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "📢 레이드 모집하고 싶다면 (누구나!)\n"
    "/모집 포켓몬이름 내닉네임 내친구코드\n"
    "예) /모집 오리진디아루가 RaidMaster 123456789012\n"
    "※ 친구코드는 숫자 12자리\n"
    "\n"
    "✋ 참가하고 싶다면\n"
    "1️⃣ 모집글에서 친구코드 확인 → 친추 먼저!\n"
    "   (예전에 친구였어도 다시 확인! 주기적으로 정리해요)\n"
    "2️⃣ /참가 내게임닉네임 포켓몬이름 모집자\n"
    "예) /참가 GoTrainer 오리진디아루가 RaidMaster\n"
    "\n"
    "⚠️ 신청이 안 될 때\n"
    "· 카톡 닉네임 ❌ → 게임 닉네임 ⭕\n"
    "· 포켓몬 이름·모집자는 모집글과 똑같이\n"
    "· \"✅ 신청 완료!\" 떴으면 성공\n"
    "\n"
    "😅 못 가게 됐다면 (매너!)\n"
    "/취소 내게임닉네임 포켓몬이름 모집자\n"
    "※ 취소 후 모집자와 친구 삭제도 부탁!\n"
    "\n"
    "👀 명단 확인\n"
    "/현황 → 지금 열려있는 모집 전부\n"
    "/현황 포켓몬이름 모집자 → 특정 명단\n"
    "\n"
    "🔒 레이드가 다 끝났다면\n"
    "/마감 포켓몬이름 모집자\n"
    "→ 최종 명단 정리 + 마무리"
)
ADMIN_COMMANDS = [
    "/취소랭킹",
    "/레이드초기화 전체(또는 포켓몬이름 모집자)",
    "/대상방설정 공개방이름",
    "/대상방확인",
    "/명령어등록 공지 내용",
    "/명령어추가 공지 내용",
    "/명령어수정 공지 새내용",
    "/명령어이어쓰기 공지 추가내용",
    "/명령어삭제 공지",
]
OWNER_COMMANDS = [
    "/오너등록 코드",
    "/관리자추가 닉네임",
    "/관리자명단",
    "/관리자삭제 닉네임(또는 번호)",
    "/관리자요청목록",
    "/관리자승인 번호",
    "/관리자거절 번호",
]


@dataclass(frozen=True)
class BotResponse:
    reply: str
    # 미등록 명령어처럼 방에 아무 답도 하지 않아야 할 때 True.
    # 오픈채팅에는 다른 봇의 /명령어도 흘러들어오므로 모르는 명령어에
    # 일일이 대꾸하면 방을 어지럽힌다.
    silent: bool = False


def parse_command(text: str) -> tuple[str, str] | None:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return None

    raw_command = parts[0].strip()
    if not raw_command.startswith("/") or len(raw_command) == 1:
        return None

    command = raw_command[1:].lower()
    query = parts[1].strip() if len(parts) > 1 else ""
    if command in ("도감", "dex"):
        return "dex", query
    if command in ("100", "백"):
        return "perfect", query
    if command in ("약점", "weak"):
        return "weakness", query
    if command in ("카운터", "counter"):
        return "counter", query
    if command in ("스킬", "기술", "skill", "moves"):
        return "moves", query
    if command in ("cp",):
        return "cp", query
    if command in ("리그", "league", "pvp"):
        return "league", query
    if command in ("포켓몬고이벤트", "이벤트", "일정", "events"):
        return "events", query
    if command in ("날씨", "전국날씨", "weather"):
        return "weather", query
    if command in ("오늘의포켓몬", "출첵", "출석", "ㅊㅊ"):
        return "daily", query
    if command in ("출석랭킹", "출첵랭킹"):
        return "attendance_ranking", query
    if command in ("추첨", "랜덤추첨"):
        return "raffle", query
    if command in ("일일랭킹", "오늘랭킹"):
        return "chat_ranking_daily", query
    if command in ("랭킹", "누적랭킹", "채팅랭킹"):
        return "chat_ranking_total", query
    if command in ("접기테스트",):
        return "fold_test", query
    if command in ("가이드", "레이드하는법", "레이드신청", "레이드방법", "레이드안내"):
        return "raid_guide", query
    if command in ("취소랭킹", "레이드취소랭킹"):
        return "raid_cancel_stats", query
    if command in ("모집", "레이드모집"):
        return "raid_open", query
    if command in ("참가", "레이드참가"):
        return "raid_join", query
    if command in ("취소", "레이드취소", "레이드참가취소", "레이드빠짐"):
        return "raid_leave", query
    if command in ("현황", "레이드현황", "레이드명단", "레이드목록"):
        return "raid_list", query
    if command in ("마감", "레이드마감"):
        return "raid_close", query
    if command in ("레이드초기화",):
        return "raid_clear", query
    if command in ("오너등록", "owner"):
        return "owner_setup", query
    if command in ("관리자요청",):
        return "admin_request", query
    if command in ("권한확인", "role"):
        return "role_check", query
    if command in ("관리자요청목록",):
        return "admin_request_list", query
    if command in ("관리자승인",):
        return "admin_approve", query
    if command in ("관리자거절",):
        return "admin_reject", query
    if command in ("관리자목록", "관리자명단"):
        return "admin_list", query
    if command in ("관리자추가",):
        return "admin_add", query
    if command in ("관리자삭제",):
        return "admin_remove", query
    if command in ("대상방설정",):
        return "target_set", query
    if command in ("대상방확인",):
        return "target_show", query
    if command in ("명령어등록", "명령어추가", "명령어수정"):
        return "custom_upsert", query
    if command in ("명령어이어쓰기", "명령어이어붙이기"):
        return "custom_append", query
    if command in ("명령어삭제",):
        return "custom_delete", query
    if command in ("명령어목록",):
        return "custom_list", query
    if command in ("help", "도움말", "명령어"):
        return "help", ""
    if len(command) > 0:
        return "custom_run", command
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
        event_client: PokemonGoEventClient | None = None,
        weather_client: KoreaWeatherClient | None = None,
        admin_store: AdminStore | None = None,
        owner_setup_code: str | None = None,
    ) -> None:
        self.pogo_client = pogo_client or PogoApiClient()
        self.event_client = event_client or PokemonGoEventClient()
        self.weather_client = weather_client or KoreaWeatherClient()
        self.admin_store = admin_store or AdminStore()
        self.owner_setup_code = (
            OWNER_SETUP_CODE if owner_setup_code is None else owner_setup_code
        )

    async def handle(
        self,
        text: str,
        room: str = "local",
        sender: str = "local",
        user_key: str | None = None,
    ) -> BotResponse:
        parsed = parse_command(text)
        if parsed is None:
            return BotResponse("", silent=True)

        command, query = parsed
        user = self._chat_user(room, sender, user_key)
        target_user = self._target_user(user)
        if command == "help":
            return BotResponse(self._handle_public_help(target_user))

        if command == "daily":
            return BotResponse(self._handle_daily(user))

        if command == "attendance_ranking":
            return BotResponse(self._handle_attendance_ranking(user))

        if command == "raffle":
            return BotResponse(self._handle_raffle(user))

        if command == "chat_ranking_daily":
            return BotResponse(self._handle_chat_ranking(user, daily=True))

        if command == "chat_ranking_total":
            return BotResponse(self._handle_chat_ranking(user, daily=False))

        if command == "fold_test":
            return BotResponse(self._handle_fold_test(query))

        if command == "raid_guide":
            return BotResponse(fold_long_reply(RAID_GUIDE))

        if command == "raid_cancel_stats":
            return BotResponse(self._handle_raid_cancel_stats(user))

        if command == "raid_open":
            return BotResponse(self._handle_raid_open(user, query))

        if command == "raid_join":
            return BotResponse(self._handle_raid_join(user, query))

        if command == "raid_close":
            return BotResponse(self._handle_raid_close(user, query))

        if command == "raid_leave":
            return BotResponse(self._handle_raid_leave(user, query))

        if command == "raid_list":
            return BotResponse(self._handle_raid_list(user, query))

        if command == "raid_clear":
            return BotResponse(self._handle_raid_clear(user, query))

        if command == "events":
            try:
                return BotResponse(await self.event_client.format_schedule(days=7))
            except EventDataUnavailableError:
                return BotResponse(
                    "포켓몬GO 이벤트 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."
                )

        if command == "weather":
            try:
                return BotResponse(await self.weather_client.format_today())
            except WeatherDataUnavailableError:
                return BotResponse(
                    "날씨 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."
                )

        if command == "owner_setup":
            return BotResponse(self._handle_owner_setup(user, query))

        if command == "admin_request":
            return BotResponse(self._handle_admin_request(user))

        if command == "role_check":
            return BotResponse(self._handle_role_check(user))

        if command == "admin_request_list":
            return BotResponse(self._handle_admin_request_list(target_user))

        if command == "admin_approve":
            return BotResponse(self._handle_admin_approve(target_user, query))

        if command == "admin_reject":
            return BotResponse(self._handle_admin_reject(target_user, query))

        if command == "admin_list":
            return BotResponse(self._handle_admin_list(target_user))

        if command == "admin_add":
            return BotResponse(self._handle_admin_add(target_user, query))

        if command == "admin_remove":
            return BotResponse(self._handle_admin_remove(target_user, query))

        if command == "target_set":
            return BotResponse(self._handle_target_set(user, query))

        if command == "target_show":
            return BotResponse(self._handle_target_show(user))

        if command == "custom_upsert":
            return BotResponse(self._handle_custom_upsert(user, target_user.room, query))

        if command == "custom_append":
            return BotResponse(self._handle_custom_append(user, target_user.room, query))

        if command == "custom_delete":
            return BotResponse(self._handle_custom_delete(user, target_user.room, query))

        if command == "custom_list":
            return BotResponse(self._handle_custom_list(user, target_user.room))

        if command == "custom_run":
            normalized = self._normalize_custom_command(query)
            # 명령을 친 방 자체에 등록된 것을 먼저 찾고, 없으면 관리
            # 대상방의 것을 찾는다. 관리방 전용 명령어(/사이트 등)가
            # 대상방 조회에 가려지지 않게 하기 위함이다.
            custom = self.admin_store.get_custom_command(user.room, normalized)
            if custom is None and target_user.room != user.room:
                custom = self.admin_store.get_custom_command(
                    target_user.room,
                    normalized,
                )
            if custom:
                return BotResponse(fold_long_reply(custom.response))
            # 이 방에 등록되지 않은 명령어는 다른 봇의 것일 수 있으니 침묵한다.
            return BotResponse("", silent=True)

        if command == "dex":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: /도감 피카츄")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except MegaUnavailableError:
                return BotResponse(f"'{query}' 메가진화는 아직 포켓몬GO에 없습니다.")
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다. 한글명 매핑을 추가해야 할 수도 있습니다.")
            except PogoDataUnavailableError:
                return BotResponse(DATA_UNAVAILABLE_MESSAGE)
            return BotResponse(format_dex_reply(entry))

        if command == "perfect":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: /100 자시안")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except MegaUnavailableError:
                return BotResponse(f"'{query}' 메가진화는 아직 포켓몬GO에 없습니다.")
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다.")
            except PogoDataUnavailableError:
                return BotResponse(DATA_UNAVAILABLE_MESSAGE)
            return BotResponse(format_perfect_cp_reply(entry))

        if command == "weakness":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: /약점 기라티나 오리진")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except MegaUnavailableError:
                return BotResponse(f"'{query}' 메가진화는 아직 포켓몬GO에 없습니다.")
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다.")
            except PogoDataUnavailableError:
                return BotResponse(DATA_UNAVAILABLE_MESSAGE)
            return BotResponse(format_weakness_reply(entry))

        if command == "counter":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: /카운터 뮤츠")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except MegaUnavailableError:
                return BotResponse(f"'{query}' 메가진화는 아직 포켓몬GO에 없습니다.")
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다.")
            except PogoDataUnavailableError:
                return BotResponse(DATA_UNAVAILABLE_MESSAGE)
            return BotResponse(format_counter_reply(entry))

        if command == "league":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: /리그 마릴리")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except MegaUnavailableError:
                return BotResponse(f"'{query}' 메가진화는 아직 포켓몬GO에 없습니다.")
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다.")
            except PogoDataUnavailableError:
                return BotResponse(DATA_UNAVAILABLE_MESSAGE)
            return BotResponse(format_league_reply(entry))

        if command == "moves":
            if not query:
                return BotResponse("포켓몬 이름을 같이 입력해 주세요. 예: /스킬 피카츄")
            try:
                entry = await self.pogo_client.get_dex_entry(query)
            except MegaUnavailableError:
                return BotResponse(f"'{query}' 메가진화는 아직 포켓몬GO에 없습니다.")
            except LookupError:
                return BotResponse(f"'{query}' 포켓몬을 찾지 못했습니다.")
            except PogoDataUnavailableError:
                return BotResponse(DATA_UNAVAILABLE_MESSAGE)
            return BotResponse(format_moves_reply(entry))

        if command == "cp":
            try:
                pokemon_query, level, ivs = parse_cp_query(query)
            except ValueError:
                return BotResponse("형식은 이렇게 입력해 주세요. 예: /cp 피카츄 25 15/15/15")
            try:
                entry = await self.pogo_client.get_dex_entry(pokemon_query)
            except MegaUnavailableError:
                return BotResponse(f"'{pokemon_query}' 메가진화는 아직 포켓몬GO에 없습니다.")
            except LookupError:
                return BotResponse(f"'{pokemon_query}' 포켓몬을 찾지 못했습니다.")
            except PogoDataUnavailableError:
                return BotResponse(DATA_UNAVAILABLE_MESSAGE)
            return BotResponse(format_custom_cp_reply(entry, level, *ivs))

        return BotResponse(self._handle_command_list(target_user))

    @staticmethod
    def _chat_user(room: str, sender: str, user_key: str | None) -> ChatUser:
        clean_room = normalize_room(room) or "local"
        clean_sender = sender.strip() or "unknown"
        clean_key = (user_key or "").strip() or f"sender:{clean_sender}"
        return ChatUser(room=clean_room, sender=clean_sender, user_key=clean_key)

    def _target_user(self, user: ChatUser) -> ChatUser:
        target_room = self.admin_store.get_control_target(user.room, user.user_key)
        if not target_room and not user.user_key.startswith("sender:"):
            legacy_key = f"sender:{user.sender}"
            target_room = self.admin_store.get_control_target(user.room, legacy_key)
            if target_room:
                self.admin_store.set_control_target(user.room, user.user_key, target_room)
        if not target_room:
            # 개인 설정이 없으면 이 방에 설정된 방 단위 대상을 따른다.
            # 관리방 하나를 만들어 두면 구성원 전원이 같은 대상방을 관리한다.
            target_room = self.admin_store.get_room_control_target(user.room)
        if not target_room:
            return user
        return ChatUser(room=target_room, sender=user.sender, user_key=user.user_key)

    def _can_manage_room(self, user: ChatUser, target_room: str) -> bool:
        # 명령을 친 방 기준 권한 또는 관리 대상방 기준 권한 중 하나면 충분하다.
        # 종합방 admin이 조용한 관리방에서 명령을 칠 수 있게 하기 위함이다.
        if self.admin_store.is_admin_or_owner(user):
            return True
        if target_room != user.room:
            return self.admin_store.is_admin_or_owner(
                ChatUser(room=target_room, sender=user.sender, user_key=user.user_key)
            )
        return False

    def _handle_target_set(self, user: ChatUser, target_room: str) -> str:
        clean_target = normalize_room(target_room)
        if not clean_target:
            return "대상 공개방 이름을 입력해 주세요. 예: /대상방설정 포켓몬고 레이드방"

        if not self._can_manage_room(user, clean_target):
            return "owner 또는 admin만 대상방을 설정할 수 있습니다."

        self.admin_store.set_control_target(
            user.room,
            user.user_key,
            clean_target,
        )
        return f"이 방의 관리 대상이 '{clean_target}' 방으로 설정되었습니다."

    def _handle_target_show(self, user: ChatUser) -> str:
        target_room = self.admin_store.get_control_target(user.room, user.user_key)
        if not target_room:
            target_room = self.admin_store.get_room_control_target(user.room)
        if not target_room:
            return "설정된 대상방이 없습니다."
        return f"현재 대상방: {target_room}"

    def _handle_owner_setup(self, user: ChatUser, code: str) -> str:
        if self.owner_setup_code in INSECURE_SETUP_CODES:
            return (
                "오너 등록이 잠겨 있습니다. 서버 관리자가 OWNER_SETUP_CODE를 "
                "기본값이 아닌 비밀 값으로 설정해야 합니다."
            )
        if code.strip() != self.owner_setup_code:
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

    def _handle_daily(self, user: ChatUser, today: date | None = None) -> str:
        today = today or date.today()
        date_key = today.isoformat()
        partner = self._daily_pick(
            f"{user.user_key}:{date_key}:partner",
            self._partner_names(),
        )
        fortune = self._daily_pick(
            f"{user.user_key}:{date_key}:fortune",
            DAILY_FORTUNES,
        )
        total_days, points, checked_in = self.admin_store.check_in(
            user,
            date_key,
            DAILY_CHECK_IN_POINTS,
        )

        lines = [
            f"[오늘의 포켓몬] {user.sender} 님",
            f"오늘의 파트너: {partner}",
            f"오늘의 운세: {fortune}",
        ]
        if checked_in:
            lines.append(f"출석 완료! +{DAILY_CHECK_IN_POINTS}P (누적 {total_days}일)")
        else:
            lines.append(f"오늘은 이미 출석했어요. (누적 {total_days}일)")
        lines.append(f"보유 포인트: {points}P")
        return "\n".join(lines)

    @staticmethod
    def _raid_key(text: str) -> str:
        return text.lower().replace(" ", "")

    @staticmethod
    def _parse_pokemon_and_host(query: str) -> tuple[str, str] | None:
        """'포켓몬이름... 모집자'를 (포켓몬 표시명, 모집자)로 나눈다.

        포켓몬 이름에는 띄어쓰기가 있을 수 있으므로 마지막 낱말을 모집자로 본다.
        """
        parts = query.strip().split()
        if len(parts) < 2:
            return None
        return " ".join(parts[:-1]), parts[-1]

    @staticmethod
    def _party_lines(nicknames: list[str]) -> list[str]:
        lines = []
        for start in range(0, len(nicknames), RAID_PARTY_SIZE):
            party = nicknames[start : start + RAID_PARTY_SIZE]
            party_number = start // RAID_PARTY_SIZE + 1
            lines.append(f"{party_number}팟({len(party)}명): {', '.join(party)}")
        return lines

    def _handle_raid_open(self, user: ChatUser, query: str) -> str:
        usage = (
            "형식은 이렇게 입력해 주세요.\n"
            "/모집 포켓몬이름 모집자닉네임 친구코드\n"
            "예: /모집 오리진디아루가 RaidMaster 123456789012"
        )
        parts = query.strip().split()
        if len(parts) < 3:
            return usage
        friend_code = parts[-1].replace("-", "")
        host = parts[-2]
        pokemon_display = " ".join(parts[:-2])
        if not friend_code.isdigit() or len(friend_code) != 12:
            return "친구코드는 숫자 12자리로 입력해 주세요.\n" + usage

        self.admin_store.open_raid(
            user.room,
            self._raid_key(pokemon_display),
            pokemon_display,
            host,
            friend_code,
            user.user_key,
        )
        return (
            "🔥 레이드 모집 오픈!\n"
            "━━━━━━━━━━━━━━\n"
            f"🎯 포켓몬 : {pokemon_display}\n"
            f"👑 모집자 : {host}\n"
            f"🤝 친구코드 : {friend_code}\n"
            "━━━━━━━━━━━━━━\n"
            f"✋ 참가 → /참가 게임닉네임 {pokemon_display} {host}\n"
            f"😅 취소 → /취소 게임닉네임 {pokemon_display} {host}\n"
            f"👀 명단 → /현황 {pokemon_display} {host}\n"
            "\n"
            f"⚠️ {friend_code} 친추가 되어 있어야\n"
            "초대를 받을 수 있어요!"
        )

    def _handle_raid_join(self, user: ChatUser, query: str) -> str:
        parts = query.strip().split()
        if len(parts) < 3:
            return (
                "형식은 이렇게 입력해 주세요.\n"
                "/참가 게임닉네임 포켓몬이름 모집자\n"
                "예: /참가 GoTrainer 오리진디아루가 RaidMaster"
            )
        nickname, host = parts[0], parts[-1]
        pokemon_display = " ".join(parts[1:-1])
        pokemon_key = self._raid_key(pokemon_display)
        host_key = host.lower()

        session = self.admin_store.get_raid_session(user.room, pokemon_key, host_key)
        if session is None:
            return (
                f"❌ '{pokemon_display}({host})' 모집을 찾지 못했어요.\n"
                "포켓몬 이름과 모집자를 모집글과\n"
                "똑같이 적어주세요.\n"
                "👀 진행 중인 모집 보기: /현황"
            )
        session_pokemon, session_host, friend_code, _ = session
        added, count = self.admin_store.add_raid_signup(
            user.room, pokemon_key, host_key, nickname
        )
        if not added:
            return (
                "이미 명단에 있어요!\n"
                f"🎯 {session_pokemon} (모집: {session_host}) · 현재 {count}명"
            )
        return (
            "✅ 신청 완료!\n"
            f"🎯 {session_pokemon} (모집: {session_host})\n"
            f"🙋 {nickname} 님 · 현재 {count}명\n"
            f"🤝 친추 필수 → {friend_code}"
        )

    def _handle_raid_leave(self, user: ChatUser, query: str) -> str:
        parts = query.strip().split()
        if len(parts) < 3:
            return (
                "형식은 이렇게 입력해 주세요.\n"
                "/취소 게임닉네임 포켓몬이름 모집자"
            )
        nickname, host = parts[0], parts[-1]
        pokemon_display = " ".join(parts[1:-1])
        removed, count = self.admin_store.remove_raid_signup(
            user.room, self._raid_key(pokemon_display), host.lower(), nickname
        )
        if not removed:
            return f"'{nickname}' 님은 {pokemon_display}({host}) 명단에 없어요."
        daily, total = self.admin_store.record_raid_cancel(
            user.room, nickname, date.today().isoformat()
        )
        return (
            "✂️ 취소 완료\n"
            f"🎯 {pokemon_display} (모집: {host}) · 현재 {count}명\n"
            f"'{nickname}' 님을 명단에서 뺐어요.\n"
            f"취소 횟수 : 오늘 {daily}회 · 누적 {total}회\n"
            f"👋 모집자 '{host}' 님과 친구 삭제도 부탁드려요!"
        )

    @staticmethod
    def _raid_join_notice(pokemon_display: str, host: str, friend_code: str) -> list[str]:
        """/현황 하단에 붙는 참가·취소·친추 안내."""
        lines = [
            "━━━━━━━━━━━━━━",
            f"✋ 참가 : /참가 게임닉네임 {pokemon_display} {host}",
            f"😅 취소 : /취소 게임닉네임 {pokemon_display} {host}",
        ]
        if friend_code:
            lines.append(f"🤝 친추코드 : {friend_code}")
        lines.append("⚠️ 모집자 친추가 되어 있어야 초대를 받아요!")
        lines.append("※ 예전에 친구였어도 다시 한번 확인하세요")
        lines.append("   (주기적으로 친구를 정리해요)")
        return lines

    def _handle_raid_list(self, user: ChatUser, query: str) -> str:
        stripped = query.strip()
        if not stripped:
            sessions = self.admin_store.list_raid_sessions(user.room)
            if not sessions:
                return (
                    "진행 중인 레이드 모집이 없어요.\n"
                    "/모집 포켓몬이름 모집자닉네임 친구코드 로 시작!"
                )
            lines = ["📋 진행 중인 레이드 모집", "━━━━━━━━━━━━━━"]
            for index, (pokemon_display, host_display, count) in enumerate(sessions, 1):
                lines.append(f"{index}. {pokemon_display} · 모집 {host_display} · {count}명")
            # 모집이 하나면 그 모집자의 친추코드까지 바로 안내한다.
            if len(sessions) == 1:
                pokemon_display, host_display, _ = sessions[0]
                session = self.admin_store.get_raid_session(
                    user.room, self._raid_key(pokemon_display), host_display.lower()
                )
                friend_code = session[2] if session else ""
                lines.extend(self._raid_join_notice(pokemon_display, host_display, friend_code))
            else:
                lines.append("━━━━━━━━━━━━━━")
                lines.append("상세보기: /현황 포켓몬이름 모집자")
            return "\n".join(lines)

        parsed = self._parse_pokemon_and_host(stripped)
        if parsed is None:
            return "특정 명단은 /현황 포켓몬이름 모집자, 전체는 /현황 으로 확인해요."
        pokemon_display, host = parsed
        pokemon_key = self._raid_key(pokemon_display)
        host_key = host.lower()

        session = self.admin_store.get_raid_session(user.room, pokemon_key, host_key)
        if session is None:
            return f"'{pokemon_display}({host})' 모집을 찾지 못했어요. 전체 확인: /현황"
        session_pokemon, session_host, friend_code, _ = session
        nicknames = self.admin_store.list_raid_signups(user.room, pokemon_key, host_key)

        lines = [
            f"📋 {session_pokemon} 레이드 명단",
            f"👑 모집자 {session_host} · 총 {len(nicknames)}명",
            "━━━━━━━━━━━━━━",
        ]
        if nicknames:
            lines.extend(self._party_lines(nicknames))
        else:
            lines.append("아직 신청자가 없어요.")
        lines.extend(self._raid_join_notice(session_pokemon, session_host, friend_code))
        return "\n".join(lines)

    def _handle_raid_close(self, user: ChatUser, query: str) -> str:
        parsed = self._parse_pokemon_and_host(query)
        if parsed is None:
            return "형식은 이렇게 입력해 주세요. 예: /마감 오리진디아루가 놋"
        pokemon_display, host = parsed
        pokemon_key = self._raid_key(pokemon_display)
        host_key = host.lower()

        session = self.admin_store.get_raid_session(user.room, pokemon_key, host_key)
        if session is None:
            return f"'{pokemon_display}({host})' 모집을 찾지 못했어요. 전체 확인: /현황"
        # 활발한 방에서는 알림 오귀속 때문에 모집자 본인 확인이 불가능해서
        # 마감은 누구나 할 수 있게 열어둔다.
        session_pokemon, session_host, _friend_code, _created_by = session

        nicknames = self.admin_store.list_raid_signups(user.room, pokemon_key, host_key)
        self.admin_store.close_raid(user.room, pokemon_key, host_key)
        if not nicknames:
            return f"🔒 {session_pokemon}({session_host}) 모집을 마감했어요. (신청자 없음)"

        lines = [
            "🔒 레이드 종료!",
            "━━━━━━━━━━━━━━",
            f"🎯 {session_pokemon} · 👑 {session_host}",
            f"🧑‍🤝‍🧑 최종 참여 {len(nicknames)}명",
        ]
        lines.extend(self._party_lines(nicknames))
        lines.append("━━━━━━━━━━━━━━")
        lines.append("참여해 주신 분들 고생하셨어요! 🎉")
        return "\n".join(lines)

    def _handle_raid_cancel_stats(self, user: ChatUser) -> str:
        if not self.admin_store.is_admin_or_owner(user):
            return "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

        stats = self.admin_store.list_raid_cancel_stats(
            user.room, date.today().isoformat()
        )
        if not stats:
            return "오늘 레이드 취소 기록이 없어요."

        lines = [f"✂️ 오늘의 레이드 취소 — 총 {len(stats)}명", "━━━━━━━━━━━━━━"]
        for rank, (nickname, count) in enumerate(stats, start=1):
            lines.append(f"{rank}. {nickname} - {count}회")
        return fold_long_reply("\n".join(lines))

    def _handle_raid_clear(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_admin_or_owner(user):
            return "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

        target = query.strip()
        if not target:
            return (
                "초기화할 대상을 입력해 주세요.\n"
                "전체: /레이드초기화 전체\n"
                "특정 모집: /레이드초기화 포켓몬이름 모집자"
            )
        if target == "전체":
            cleared = self.admin_store.clear_raids(user.room)
            return f"레이드 모집 {cleared}건을 모두 초기화했어요."

        parsed = self._parse_pokemon_and_host(target)
        if parsed is None:
            return "특정 모집 초기화는 /레이드초기화 포켓몬이름 모집자 형식이에요."
        pokemon_display, host = parsed
        pokemon_key = self._raid_key(pokemon_display)
        host_key = host.lower()
        if self.admin_store.get_raid_session(user.room, pokemon_key, host_key) is None:
            return f"'{pokemon_display}({host})' 모집을 찾지 못했어요."
        self.admin_store.close_raid(user.room, pokemon_key, host_key)
        return f"{pokemon_display}({host}) 모집을 초기화했어요."

    @staticmethod
    def _handle_fold_test(query: str) -> str:
        """접힘 유도 설정을 실험하는 숨은 명령. /접기테스트 [패딩수]"""
        try:
            padding_count = int(query.strip()) if query.strip() else 500
        except ValueError:
            padding_count = 500
        padding_count = max(0, min(padding_count, 4000))
        body = "\n".join(f"{index}번째 줄입니다." for index in range(1, 41))
        return (
            f"[접기테스트] 패딩 {padding_count}자 — 이 줄만 보이면 성공!"
            + "​" * padding_count
            + "\n"
            + body
        )

    def record_chat(self, room: str, sender: str, user_key: str | None) -> None:
        """랭킹 집계용으로 채팅 1건을 기록한다. 명령어든 일반 채팅이든 센다."""
        clean = self._chat_user(room, sender, user_key)
        if clean.room == "local" or clean.sender == "unknown":
            return
        self.admin_store.record_chat_message(
            clean.room, clean.user_key, clean.sender, date.today().isoformat()
        )
        # 닉네임 자동 갱신: 관리자목록 표시 이름도 최신으로.
        # 개인톡방 placeholder는 진짜 닉네임이 아니므로 제외한다.
        if clean.sender != "개인톡사용자":
            self.admin_store.refresh_admin_display_name(clean.user_key, clean.sender)

    def _handle_raffle(self, user: ChatUser) -> str:
        pool = self.admin_store.raffle_pool(user.room)
        if not pool:
            return "추첨할 대상이 없어요. (채팅 활동이 있어야 추첨 대상이 됩니다)"
        names = [name for name, _ in pool]
        weights = [weight for _, weight in pool]
        # 활동량이 많을수록 당첨 확률이 높다. 활동량 숫자는 표시하지 않는다.
        winner = random.choices(names, weights=weights, k=1)[0]
        return (
            "🎉 추첨 결과 🎉\n"
            "━━━━━━━━━━━━━━\n"
            f"🎊 당첨 : {winner} 님!\n"
            "━━━━━━━━━━━━━━\n"
            f"축하합니다! (총 {len(names)}명 중 추첨)"
        )

    def _handle_chat_ranking(self, user: ChatUser, daily: bool) -> str:
        today = date.today().isoformat() if daily else None
        ranking = self.admin_store.chat_ranking(user.room, today=today, limit=10)
        if not ranking:
            if daily:
                return "오늘 집계된 채팅이 아직 없어요."
            return "집계된 채팅 기록이 아직 없어요."

        title = "💬 오늘의 채팅 랭킹 TOP 10" if daily else "💬 누적 채팅 랭킹 TOP 10"
        lines = [title, "━━━━━━━━━━━━━━"]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for rank, (display_name, count) in enumerate(ranking, start=1):
            marker = medals.get(rank, f"{rank}.")
            lines.append(f"{marker} {display_name} - {count:,}회")
        return "\n".join(lines)

    def _handle_attendance_ranking(self, user: ChatUser) -> str:
        ranking = self.admin_store.attendance_ranking(user.room, limit=10)
        if not ranking:
            return "아직 출석한 사람이 없어요. /오늘의포켓몬 으로 첫 출석을 해보세요!"

        lines = ["[출석 랭킹 TOP 10]"]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for rank, (display_name, total_days, points) in enumerate(ranking, start=1):
            marker = medals.get(rank, f"{rank}.")
            lines.append(f"{marker} {display_name} - {total_days}일 / {points}P")
        return "\n".join(lines)

    @staticmethod
    def _daily_pick(seed: str, options: list[str]) -> str:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return options[int(digest, 16) % len(options)]

    def _partner_names(self) -> list[str]:
        return sorted(self.pogo_client.name_resolver.display_names.values())

    def _handle_role_check(self, user: ChatUser) -> str:
        role = self.admin_store.get_effective_role(user) or "없음"
        return "\n".join(
            [
                "권한 확인",
                f"방: {user.room}",
                f"권한: {role}",
            ]
        )

    def _handle_admin_request_list(self, user: ChatUser) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        requests = self.admin_store.list_pending_requests(user.room)
        if not requests:
            return "대기 중인 관리자 요청이 없습니다."

        lines = ["관리자 요청 목록"]
        for request in requests:
            lines.append(f"{request.id}. {request.sender}")
        lines.append("승인: /관리자승인 번호")
        lines.append("거절: /관리자거절 번호")
        return "\n".join(lines)

    def _handle_admin_approve(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        request_id = self._parse_request_id(query)
        if request_id is None:
            return "승인할 요청번호를 입력해 주세요. 예: /관리자승인 3"

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
            return "거절할 요청번호를 입력해 주세요. 예: /관리자거절 3"

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

    def _handle_admin_add(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        nickname = query.strip()
        if not nickname:
            return "추가할 닉네임을 입력해 주세요. 예: /관리자추가 박화영"

        for display_name, role, _user_key in self.admin_store.list_admin_records(user.room):
            if display_name == nickname:
                if role == "owner":
                    return f"{nickname} 님은 이미 owner입니다."
                return f"{nickname} 님은 이미 admin입니다."

        # 닉네임만으로는 프로필 hash를 알 수 없으므로 우선 닉네임 키로
        # 등록한다. 본인이 해당 방에서 처음 활동하면 hash 키로 자동 승격된다.
        self.admin_store.add_admin(
            ChatUser(
                room=user.room,
                sender=nickname,
                user_key=f"sender:{nickname}",
            )
        )
        return (
            f"{nickname} 님을 admin으로 등록했습니다.\n"
            f"'{user.room}' 방에서 {nickname} 닉네임으로 관리자 명령을 처음 사용하면"
            " 프로필에 자동 연결됩니다."
        )

    def _handle_admin_remove(self, user: ChatUser, query: str) -> str:
        if not self.admin_store.is_owner(user):
            return "이 명령어는 owner만 사용할 수 있습니다."

        token = query.strip()
        if not token:
            return "삭제할 관리자 닉네임이나 번호를 입력해 주세요. 예: /관리자삭제 박화영"

        admins = self.admin_store.list_admin_records(user.room)
        admin_index = self._parse_request_id(token)
        if admin_index is not None:
            if admin_index < 1 or admin_index > len(admins):
                return "해당 관리자 번호를 찾지 못했습니다."
            display_name, role, user_key = admins[admin_index - 1]
        else:
            matches = [record for record in admins if record[0] == token]
            if not matches:
                return f"'{token}' 닉네임의 관리자를 찾지 못했습니다."
            display_name, role, user_key = matches[0]

        if role == "owner":
            return "owner는 관리자삭제로 삭제할 수 없습니다."

        removed = self.admin_store.remove_admin_by_key(user.room, user_key)
        if not removed:
            return "해당 관리자를 찾지 못했습니다."
        return f"{display_name} 님의 admin 권한을 삭제했습니다."

    def _handle_custom_upsert(self, user: ChatUser, target_room: str, query: str) -> str:
        if not self._can_manage_room(user, target_room):
            return "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

        parsed = self._parse_custom_upsert(query)
        if parsed is None:
            return "형식은 이렇게 입력해 주세요. 예: /명령어등록 공지 오늘 레이드 8시"

        command, response = parsed
        self.admin_store.upsert_custom_command(
            target_room,
            command,
            response,
            user.sender,
        )
        return f"/{command} 명령어를 저장했습니다."

    def _handle_custom_append(self, user: ChatUser, target_room: str, query: str) -> str:
        if not self._can_manage_room(user, target_room):
            return "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

        parsed = self._parse_custom_upsert(query)
        if parsed is None:
            return "형식은 이렇게 입력해 주세요. 예: /명령어이어쓰기 공지 추가할 내용"

        command, extra = parsed
        custom = self.admin_store.get_custom_command(target_room, command)
        if custom is None:
            return f"/{command} 명령어가 없습니다. 먼저 /명령어등록 으로 만들어 주세요."

        combined = f"{custom.response}\n{extra}"
        self.admin_store.upsert_custom_command(
            target_room,
            command,
            combined,
            user.sender,
        )
        return f"/{command} 명령어에 내용을 이어붙였습니다. (현재 {len(combined)}자)"

    def _handle_custom_delete(self, user: ChatUser, target_room: str, query: str) -> str:
        if not self._can_manage_room(user, target_room):
            return "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

        command = self._normalize_custom_command(query)
        if not command:
            return "삭제할 명령어 이름을 입력해 주세요. 예: /명령어삭제 공지"

        deleted = self.admin_store.delete_custom_command(target_room, command)
        if not deleted:
            return f"/{command} 명령어를 찾지 못했습니다."
        return f"/{command} 명령어를 삭제했습니다."

    def _handle_custom_list(self, user: ChatUser, target_room: str) -> str:
        return self._handle_command_list(user, target_room)

    def _handle_public_help(self, user: ChatUser) -> str:
        greeting = HELP_GREETINGS[date.today().toordinal() % len(HELP_GREETINGS)]
        lines = [greeting, "", "【 가르치기 목록 】", "━━━━━━━━━━━━━━━━"]
        index = 1
        for custom in self.admin_store.list_custom_command_records(user.room):
            lines.extend(
                self._format_help_entry(
                    index,
                    f"/{custom.display_command}",
                    custom.response,
                    custom.taught_by or custom.created_by,
                    custom.taught_at or "등록일자 알 수 없음",
                )
            )
            index += 1

        for command, response in BUILTIN_HELP_ENTRIES:
            lines.extend(
                self._format_help_entry(
                    index,
                    command,
                    response,
                    "KakaoPoGo",
                    "기본 기능",
                )
            )
            index += 1
        return "\n".join(lines)

    def _handle_command_list(self, user: ChatUser, custom_room: str | None = None) -> str:
        role = self.admin_store.get_role(user)
        lines = ["사용 가능한 명령어", *(command for command, _ in BUILTIN_HELP_ENTRIES), "/도움말", "/명령어"]

        custom_commands = self.admin_store.list_custom_commands(custom_room or user.room)
        if custom_commands:
            lines.append("")
            lines.append("방 명령어")
            lines.extend(f"/{command}" for command in custom_commands)

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
            "카운터",
            "counter",
            "스킬",
            "기술",
            "skill",
            "moves",
            "cp",
            "리그",
            "league",
            "pvp",
            "포켓몬고이벤트",
            "이벤트",
            "일정",
            "events",
            "날씨",
            "전국날씨",
            "weather",
            "오늘의포켓몬",
            "출첵",
            "출석",
            "ㅊㅊ",
            "출석랭킹",
            "출첵랭킹",
            "추첨",
            "랜덤추첨",
            "일일랭킹",
            "오늘랭킹",
            "랭킹",
            "누적랭킹",
            "채팅랭킹",
            "접기테스트",
            "가이드",
            "레이드하는법",
            "레이드신청",
            "레이드방법",
            "레이드안내",
            "모집",
            "취소랭킹",
            "레이드취소랭킹",
            "레이드모집",
            "참가",
            "레이드참가",
            "취소",
            "레이드참가취소",
            "레이드취소",
            "레이드빠짐",
            "현황",
            "레이드명단",
            "레이드목록",
            "레이드현황",
            "마감",
            "레이드마감",
            "레이드초기화",
            "오너등록",
            "owner",
            "관리자요청",
            "권한확인",
            "role",
            "관리자요청목록",
            "관리자승인",
            "관리자거절",
            "관리자목록",
            "관리자명단",
            "관리자추가",
            "관리자삭제",
            "대상방설정",
            "대상방확인",
            "명령어추가",
            "명령어등록",
            "명령어수정",
            "명령어이어쓰기",
            "명령어이어붙이기",
            "명령어삭제",
            "명령어목록",
            "help",
            "도움말",
            "명령어",
        }

    @staticmethod
    def _format_help_entry(
        index: int,
        command: str,
        response: str,
        taught_by: str,
        taught_at: str,
    ) -> list[str]:
        lines = [
            f"{index}. {command}",
            f"└ 가르친사람 : {taught_by}",
            f"└ 가르친일자 : {taught_at}",
            f"└ 명령어 : {command}",
        ]
        if response:
            lines.append(f"《답변1》{response}")
        lines.append("")
        return lines

    @staticmethod
    def _parse_request_id(query: str) -> int | None:
        try:
            return int(query.strip())
        except ValueError:
            return None
