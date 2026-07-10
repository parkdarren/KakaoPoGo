import pytest
from fastapi.testclient import TestClient

from app.admin_store import AdminStore
from app.bot import DATA_UNAVAILABLE_MESSAGE, parse_command, parse_cp_query
from app.bot import PokemonGoBot
from app.main import _is_silent_message, app, command_get
from app.pogo_api import MegaUnavailableError, PogoDataUnavailableError


class UnavailablePogoClient:
    async def get_dex_entry(self, query: str):
        raise PogoDataUnavailableError("pokemon_stats.json")


class MegaUnavailablePogoClient:
    async def get_dex_entry(self, query: str):
        raise MegaUnavailableError(query)


def test_parse_new_commands() -> None:
    assert parse_command("/100 자시안 검왕") == ("perfect", "자시안 검왕")
    assert parse_command("/약점 기라티나 오리진") == ("weakness", "기라티나 오리진")
    assert parse_command("/카운터 뮤츠") == ("counter", "뮤츠")
    assert parse_command("/리그 마릴리") == ("league", "마릴리")
    assert parse_command("/오늘의포켓몬") == ("daily", "")
    assert parse_command("/출첵") == ("daily", "")
    assert parse_command("/출석랭킹") == ("attendance_ranking", "")
    assert parse_command("/스킬 피카츄") == ("moves", "피카츄")
    assert parse_command("/기술 디아루가") == ("moves", "디아루가")
    assert parse_command("/cp 피카츄 25 15/15/15") == ("cp", "피카츄 25 15/15/15")
    assert parse_command("/오너등록 test-setup-code") == ("owner_setup", "test-setup-code")
    assert parse_command("/관리자요청") == ("admin_request", "")
    assert parse_command("/권한확인") == ("role_check", "")
    assert parse_command("/관리자승인 1") == ("admin_approve", "1")
    assert parse_command("/명령어등록 공지 내용") == ("custom_upsert", "공지 내용")
    assert parse_command("/명령어추가 공지 내용") == ("custom_upsert", "공지 내용")
    assert parse_command("/공지") == ("custom_run", "공지")
    assert parse_command("/대상방설정 레이드방") == ("target_set", "레이드방")
    assert parse_command("/대상방확인") == ("target_show", "")
    assert parse_command("/도움말") == ("help", "")
    assert parse_command("/명령어") == ("help", "")
    assert parse_command("!도감 피카츄") is None
    assert parse_command("!공지") is None
    assert _is_silent_message("/도감 피카츄") is False
    assert _is_silent_message("!도감 피카츄") is True


@pytest.mark.anyio
async def test_exclamation_command_returns_silent_response() -> None:
    response = await command_get("!도감 피카츄", room="레이드방", sender="일반")

    assert response == {"reply": "", "silent": True}


def test_command_requires_bridge_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("BRIDGE_KEY", "bridge-secret")
    client = TestClient(app)

    denied = client.get("/command", params={"text": "!x"})
    assert denied.status_code == 403

    wrong = client.get(
        "/command", params={"text": "!x"}, headers={"X-Bridge-Key": "nope"}
    )
    assert wrong.status_code == 403

    allowed = client.get(
        "/command", params={"text": "!x"}, headers={"X-Bridge-Key": "bridge-secret"}
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"reply": "", "silent": True}


def test_command_stays_open_without_bridge_key(monkeypatch) -> None:
    monkeypatch.delenv("BRIDGE_KEY", raising=False)
    client = TestClient(app)

    response = client.get("/command", params={"text": "!x"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_dex_reports_friendly_message_when_data_unavailable(tmp_path) -> None:
    bot = PokemonGoBot(
        pogo_client=UnavailablePogoClient(),
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    reply = await bot.handle("/도감 피카츄", room="레이드방", sender="일반")

    assert reply.reply == DATA_UNAVAILABLE_MESSAGE


@pytest.mark.anyio
async def test_daily_pokemon_checks_in_once_per_day(tmp_path) -> None:
    from datetime import date

    from app.admin_store import ChatUser
    from app.bot import DAILY_CHECK_IN_POINTS

    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    user = ChatUser(room="레이드방", sender="지우", user_key="hash:ash")

    first = bot._handle_daily(user, today=date(2026, 7, 10))
    assert "오늘의 파트너:" in first
    assert "오늘의 운세:" in first
    assert f"출석 완료! +{DAILY_CHECK_IN_POINTS}P (누적 1일)" in first
    assert f"보유 포인트: {DAILY_CHECK_IN_POINTS}P" in first

    same_day = bot._handle_daily(user, today=date(2026, 7, 10))
    assert "오늘은 이미 출석했어요. (누적 1일)" in same_day
    assert f"보유 포인트: {DAILY_CHECK_IN_POINTS}P" in same_day
    # 같은 날에는 파트너와 운세도 동일하다.
    assert first.split("\n")[1] == same_day.split("\n")[1]

    next_day = bot._handle_daily(user, today=date(2026, 7, 11))
    assert "출석 완료!" in next_day
    assert "(누적 2일)" in next_day
    assert f"보유 포인트: {DAILY_CHECK_IN_POINTS * 2}P" in next_day

    other_user = ChatUser(room="레이드방", sender="웅이", user_key="hash:brock")
    other = bot._handle_daily(other_user, today=date(2026, 7, 11))
    assert "(누적 1일)" in other


@pytest.mark.anyio
async def test_attendance_ranking_shows_top_ten(tmp_path) -> None:
    from datetime import date

    from app.admin_store import ChatUser

    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    empty = await bot.handle("/출석랭킹", room="레이드방", sender="지우")
    assert "아직 출석한 사람이 없어요" in empty.reply

    # 12명이 서로 다른 누적 일수로 출석한 상황을 만든다.
    for index in range(12):
        user = ChatUser(
            room="레이드방",
            sender=f"유저{index:02d}",
            user_key=f"hash:user{index}",
        )
        for day in range(index + 1):
            bot._handle_daily(user, today=date(2026, 7, 1 + day))

    ranking = await bot.handle("/출석랭킹", room="레이드방", sender="지우")
    lines = ranking.reply.split("\n")

    assert lines[0] == "[출석 랭킹 TOP 10]"
    assert len(lines) == 11  # 제목 + 10명
    assert lines[1] == "🥇 유저11 - 12일 / 60P"
    assert lines[2] == "🥈 유저10 - 11일 / 55P"
    assert lines[3] == "🥉 유저09 - 10일 / 50P"
    assert lines[4] == "4. 유저08 - 9일 / 45P"
    assert "유저00" not in ranking.reply
    assert "유저01" not in ranking.reply

    other_room = await bot.handle("/출석랭킹", room="다른방", sender="지우")
    assert "아직 출석한 사람이 없어요" in other_room.reply


@pytest.mark.anyio
async def test_dex_explains_unreleased_mega(tmp_path) -> None:
    bot = PokemonGoBot(
        pogo_client=MegaUnavailablePogoClient(),
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    reply = await bot.handle("/도감 메가뮤츠", room="레이드방", sender="일반")

    assert reply.reply == "'메가뮤츠' 메가진화는 아직 포켓몬GO에 없습니다."


def test_parse_cp_query_with_form_name() -> None:
    pokemon, level, ivs = parse_cp_query("기라티나 오리진 20 15/14/13")

    assert pokemon == "기라티나 오리진"
    assert level == 20
    assert ivs == (15, 14, 13)


@pytest.mark.parametrize(
    "query",
    [
        "피카츄",
        "피카츄 20",
        "피카츄 52 15/15/15",
        "피카츄 20 16/15/15",
        "피카츄 20 15/15",
    ],
)
def test_parse_cp_query_rejects_bad_input(query: str) -> None:
    with pytest.raises(ValueError):
        parse_cp_query(query)


@pytest.mark.anyio
async def test_owner_approves_admin_request(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    owner = await bot.handle(
        "/오너등록 test-setup-code",
        room="레이드방",
        sender="오너",
    )
    assert owner.reply == "이 방의 owner로 등록되었습니다."

    requester = await bot.handle(
        "/관리자요청",
        room="레이드방",
        sender="관리자후보",
    )
    assert "요청번호:" in requester.reply
    request_id = int(requester.reply.rsplit(":", maxsplit=1)[1].strip())

    denied = await bot.handle(
        "/관리자요청목록",
        room="레이드방",
        sender="관리자후보",
    )
    assert denied.reply == "이 명령어는 owner만 사용할 수 있습니다."

    pending = await bot.handle(
        "/관리자요청목록",
        room="레이드방",
        sender="오너",
    )
    assert f"{request_id}. 관리자후보" in pending.reply

    approved = await bot.handle(
        f"/관리자승인 {request_id}",
        room="레이드방",
        sender="오너",
    )
    assert approved.reply == "관리자후보 님을 admin으로 등록했습니다."

    listed = await bot.handle("/관리자목록", room="레이드방", sender="오너")
    assert "1. 오너: owner" in listed.reply
    assert "2. 관리자후보: admin" in listed.reply

    cannot_remove_owner = await bot.handle("/관리자삭제 1", room="레이드방", sender="오너")
    assert cannot_remove_owner.reply == "owner는 관리자삭제로 삭제할 수 없습니다."

    removed = await bot.handle("/관리자삭제 2", room="레이드방", sender="오너")
    assert removed.reply == "관리자후보 님의 admin 권한을 삭제했습니다."

    duplicate = await bot.handle(
        "/관리자요청",
        room="레이드방",
        sender="관리자후보",
    )
    assert "관리자 요청을 받았습니다." in duplicate.reply


@pytest.mark.anyio
async def test_custom_commands_are_managed_by_admins(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    denied = await bot.handle(
        "/명령어추가 공지 오늘 레이드 8시",
        room="레이드방",
        sender="일반",
    )
    assert denied.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

    await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="오너")
    saved = await bot.handle(
        "/명령어등록 공지 오늘 레이드 8시",
        room="레이드방",
        sender="오너",
    )
    assert saved.reply == "/공지 명령어를 저장했습니다."

    reply = await bot.handle("/공지", room="레이드방", sender="일반")
    assert reply.reply == "오늘 레이드 8시"

    listed = await bot.handle("/명령어목록", room="레이드방", sender="일반")
    assert "/공지" in listed.reply
    assert "/명령어목록" not in listed.reply
    assert "/명령어추가" not in listed.reply
    assert "/관리자승인" not in listed.reply
    assert "/권한확인" not in listed.reply
    assert "/관리자요청" not in listed.reply

    owner_listed = await bot.handle("/명령어목록", room="레이드방", sender="오너")
    assert "/공지" in owner_listed.reply
    assert "/명령어등록 공지 내용" in owner_listed.reply
    assert "/명령어추가 공지 내용" in owner_listed.reply
    assert "/관리자승인 번호" in owner_listed.reply

    owner_help = await bot.handle("/도움말", room="레이드방", sender="오너")
    assert "/공지" in owner_help.reply
    assert "/도감 포켓몬이름" in owner_help.reply
    assert "【 가르치기 목록 】" in owner_help.reply
    assert "1. /공지" in owner_help.reply
    assert "└ 가르친사람 : 오너" in owner_help.reply
    assert "《답변1》오늘 레이드 8시" in owner_help.reply
    assert "/명령어목록" not in owner_help.reply
    assert "/명령어추가" not in owner_help.reply
    assert "/관리자승인" not in owner_help.reply
    assert "/오너등록" not in owner_help.reply
    assert "/권한확인" not in owner_help.reply
    assert "/관리자요청" not in owner_help.reply

    alias_help = await bot.handle("/명령어", room="레이드방", sender="일반")
    assert alias_help.reply == owner_help.reply

    deleted = await bot.handle("/명령어삭제 공지", room="레이드방", sender="오너")
    assert deleted.reply == "/공지 명령어를 삭제했습니다."

    missing = await bot.handle("/공지", room="레이드방", sender="일반")
    assert missing.reply == "알 수 없는 명령어입니다. /도움말 을 입력해 주세요."


@pytest.mark.anyio
async def test_owner_role_survives_user_key_upgrade(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="오너")
    saved = await bot.handle(
        "/명령어추가 공지 오늘 레이드 8시",
        room="레이드방",
        sender="오너",
        user_key="hash:stable-owner",
    )

    assert saved.reply == "/공지 명령어를 저장했습니다."


@pytest.mark.anyio
@pytest.mark.parametrize("insecure_code", ["", "change-me"])
async def test_owner_setup_is_locked_with_default_code(tmp_path, insecure_code) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code=insecure_code)

    blocked = await bot.handle(
        f"/오너등록 {insecure_code}".strip(),
        room="레이드방",
        sender="선점시도",
    )

    assert "오너 등록이 잠겨 있습니다" in blocked.reply
    assert store.list_admin_records("레이드방") == []


@pytest.mark.anyio
async def test_owner_setup_does_not_replace_existing_owner(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    await bot.handle(
        "/오너등록 test-setup-code",
        room="레이드방",
        sender="이전오너",
        user_key="hash:previous-owner",
    )
    blocked = await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="현재오너")

    admins = store.list_admin_records("레이드방")
    assert blocked.reply == "이 방에는 이미 owner가 등록되어 있습니다."
    assert admins == [("이전오너", "owner", "hash:previous-owner")]


@pytest.mark.anyio
async def test_owner_setup_does_not_upgrade_different_legacy_owner(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="예전오너")
    blocked = await bot.handle(
        "/오너등록 test-setup-code",
        room="레이드방",
        sender="현재오너",
        user_key="hash:stable-owner",
    )

    admins = store.list_admin_records("레이드방")
    assert blocked.reply == "이 방에는 이미 owner가 등록되어 있습니다."
    assert admins == [("예전오너", "owner", "sender:예전오너")]


@pytest.mark.anyio
async def test_hash_owner_is_recognized_globally(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    await bot.handle(
        "/오너등록 test-setup-code",
        room="개인방",
        sender="오너",
        user_key="hash:owner",
    )
    saved = await bot.handle(
        "/명령어등록 공지 전역 오너 테스트",
        room="공개방",
        sender="오너",
        user_key="hash:owner",
    )
    role = await bot.handle(
        "/권한확인",
        room="공개방",
        sender="오너",
        user_key="hash:owner",
    )

    assert saved.reply == "/공지 명령어를 저장했습니다."
    assert "권한: owner" in role.reply
    assert "식별 방식" not in role.reply
    assert "프로필:" not in role.reply


@pytest.mark.anyio
async def test_nickname_impersonation_of_hash_owner_is_denied(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    await bot.handle(
        "/오너등록 test-setup-code",
        room="레이드방",
        sender="오너",
        user_key="hash:real-owner",
    )

    denied = await bot.handle(
        "/명령어등록 공지 사칭 시도",
        room="레이드방",
        sender="오너",
        user_key="hash:attacker",
    )

    assert denied.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."
    assert store.list_admin_records("레이드방") == [("오너", "owner", "hash:real-owner")]


@pytest.mark.anyio
async def test_admin_can_manage_target_room_from_control_room(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    await bot.handle("/오너등록 test-setup-code", room="관리자방", sender="오너")

    denied = await bot.handle(
        "/대상방설정 공개방",
        room="관리자방",
        sender="일반",
    )
    assert denied.reply == "owner 또는 admin만 대상방을 설정할 수 있습니다."

    linked = await bot.handle(
        "/대상방설정 공개방",
        room="관리자방",
        sender="오너",
    )
    assert linked.reply == "이 방의 관리 대상이 '공개방' 방으로 설정되었습니다."

    saved = await bot.handle(
        "/명령어추가 공지 공개방 공지입니다",
        room="관리자방",
        sender="오너",
    )
    assert saved.reply == "/공지 명령어를 저장했습니다."

    public_reply = await bot.handle("/공지", room="공개방", sender="일반")
    assert public_reply.reply == "공개방 공지입니다"

    control_list = await bot.handle("/명령어목록", room="관리자방", sender="오너")
    assert "/공지" in control_list.reply
    assert "/명령어추가 공지 내용" in control_list.reply


@pytest.mark.anyio
async def test_control_room_target_survives_user_key_upgrade(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    await bot.handle("/오너등록 test-setup-code", room="관리자방", sender="오너")
    await bot.handle("/대상방설정 공개방", room="관리자방", sender="오너")
    await bot.handle(
        "/명령어추가 공지 공개방 공지입니다",
        room="관리자방",
        sender="오너",
        user_key="hash:owner",
    )

    help_reply = await bot.handle(
        "/도움말",
        room="관리자방",
        sender="오너",
        user_key="hash:owner",
    )
    public_reply = await bot.handle("/공지", room="공개방", sender="일반")

    assert "/공지" in help_reply.reply
    assert public_reply.reply == "공개방 공지입니다"
