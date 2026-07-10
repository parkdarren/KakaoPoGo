import pytest

from app.admin_store import AdminStore
from app.bot import parse_command, parse_cp_query
from app.bot import PokemonGoBot
from app.main import _is_silent_message, command_get


def test_parse_new_commands() -> None:
    assert parse_command("/100 자시안 검왕") == ("perfect", "자시안 검왕")
    assert parse_command("/약점 기라티나 오리진") == ("weakness", "기라티나 오리진")
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
