import json
import pytest
from fastapi.testclient import TestClient

from app.admin_store import AdminStore
from app.bot import DATA_UNAVAILABLE_MESSAGE, parse_command, parse_cp_query
from app.bot import PokemonGoBot
from app.events import EventDataUnavailableError
from app.main import _is_silent_message, _split_kakao_text, app, command_get
from app.pogo_api import MegaUnavailableError, PogoDataUnavailableError
from app.weather import WeatherDataUnavailableError


class UnavailablePogoClient:
    async def get_dex_entry(self, query: str):
        raise PogoDataUnavailableError("pokemon_stats.json")


class MegaUnavailablePogoClient:
    async def get_dex_entry(self, query: str):
        raise MegaUnavailableError(query)


class FakeEventClient:
    async def format_schedule(self, days: int = 7) -> str:
        return f"event schedule for {days} days"


class FailingEventClient:
    async def format_schedule(self, days: int = 7) -> str:
        raise EventDataUnavailableError("boom")


class FakeWeatherClient:
    async def format_today(self) -> str:
        return "today weather"


class FailingWeatherClient:
    async def format_today(self) -> str:
        raise WeatherDataUnavailableError("boom")


def test_parse_new_commands() -> None:
    assert parse_command("/100 자시안 검왕") == ("perfect", "자시안 검왕")
    assert parse_command("/약점 기라티나 오리진") == ("weakness", "기라티나 오리진")
    assert parse_command("/카운터 뮤츠") == ("counter", "뮤츠")
    assert parse_command("/리그 마릴리") == ("league", "마릴리")
    assert parse_command("/pvp") == ("custom_run", "pvp")
    assert parse_command("/신청") == ("raid_apply_guide", "")
    assert parse_command("/관리링크") == ("site_link", "")
    assert parse_command("/방링크") == ("site_link", "")
    assert parse_command("/포켓몬고이벤트") == ("events", "")
    assert parse_command("/이벤트") == ("events", "")
    assert parse_command("/일정") == ("events", "")
    assert parse_command("/날씨") == ("weather", "")
    assert parse_command("/전국날씨") == ("weather", "")
    assert parse_command("/오늘의포켓몬") == ("daily", "")
    assert parse_command("/출첵") == ("daily", "")
    assert parse_command("/ㅊㅊ") == ("daily", "")
    assert parse_command("/출석랭킹") == ("attendance_ranking", "")
    assert parse_command("/포인트순위") == ("point_ranking", "")
    assert parse_command("/포인트랭킹") == ("point_ranking", "")
    assert parse_command("/스킬 피카츄") == ("moves", "피카츄")
    assert parse_command("/기술 디아루가") == ("moves", "디아루가")
    assert parse_command("/cp 피카츄 25 15/15/15") == ("cp", "피카츄 25 15/15/15")
    assert parse_command("/오너등록 test-setup-code") == ("owner_setup", "test-setup-code")
    assert parse_command("/관리자요청") == ("admin_request", "")
    assert parse_command("/권한확인") == ("role_check", "")
    assert parse_command("/관리자승인 1") == ("admin_approve", "1")
    assert parse_command("/명령어등록 공지 내용") == ("custom_upsert", "공지 내용")
    assert parse_command("/명령어추가 공지 내용") == ("custom_upsert", "공지 내용")
    assert parse_command("/명령어이어쓰기 공지 추가내용") == ("custom_append", "공지 추가내용")
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


@pytest.mark.anyio
async def test_unknown_slash_command_stays_silent(tmp_path) -> None:
    # 다른 봇의 명령어(/레이드신청 등)에 끼어들어 방을 어지럽히면 안 된다.
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    for text in ("/타봇명령어", "/좌표", "/뉴비초대 3명이요", "/"):
        response = await bot.handle(text, room="레이드방", sender="일반")
        assert response.silent is True, text
        assert response.reply == ""


@pytest.mark.anyio
async def test_unknown_slash_command_returns_silent_http_response() -> None:
    response = await command_get("/타봇명령어", room="레이드방", sender="일반")

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


def test_admin_web_saves_long_command(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    test_bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "admin-secret")
    client = TestClient(main_module.app)
    auth = {"X-Bridge-Key": "admin-secret"}

    page = client.get("/admin")
    assert page.status_code == 200
    assert "포고정보 운영센터" in page.text
    assert "KAKAOPOGO LAB · OWNER" in page.text
    assert "/ui-assets/kakaopogo-control-mark.webp" in page.text
    assert "Trainer Lab control system" in page.text
    assert '<details class="card" data-section="access" open>' in page.text
    assert 'data-section="commands"' in page.text
    assert '<details class="card" data-section="commands">' in page.text
    assert 'data-section="room-settings"' in page.text
    assert "initSectionState" in page.text
    assert "initAccordionMotion" in page.text
    assert "명령어 관리" in page.text
    assert "방 관리자" in page.text
    assert "관리자 닉네임 검색" in page.text
    assert "닉네임 일부를 입력하세요" in page.text
    assert "방 운영 설정" in page.text
    assert "들낙 안내 출력 기준 횟수" in page.text
    assert "상품 등록을 오너와 관리자만 허용" in page.text
    assert "일반 사용자 상품 등록 수수료" in page.text
    assert "일반 사용자 상품 등록 보증금" in page.text
    assert "전용 명령어 관리 사이트" in page.text
    assert "단타 감지 시 채팅방 경고 출력" in page.text
    assert "음슴체 감지 시 채팅방 경고 출력" in page.text

    mark = client.get("/ui-assets/kakaopogo-control-mark.webp")
    assert mark.status_code == 200
    assert mark.headers["content-type"].startswith("image/webp")
    assert len(mark.content) > 1_000

    test_bot.admin_store.record_chat_message(
        "종합방", "iris:sub", "부방장", "2026-08-11"
    )
    test_bot.admin_store.seed_member_present("종합방", "leader", "방장")

    denied_members = client.get("/admin/room-members", params={"room": "종합방"})
    assert denied_members.status_code == 403

    members = client.get(
        "/admin/room-members", headers=auth, params={"room": "종합방"}
    )
    assert members.status_code == 200
    assert {(item["nickname"], item["userKey"]) for item in members.json()} == {
        ("부방장", "iris:sub"),
        ("방장", "iris:leader"),
    }

    for user_key, nickname in (
        ("iris:park1", "박화영"),
        ("iris:park2", "박화진"),
        ("iris:kim", "김철수"),
    ):
        test_bot.admin_store.record_chat_message(
            "종합방", user_key, nickname, "2026-08-11"
        )
    searched = client.get(
        "/admin/room-members",
        headers=auth,
        params={"room": "종합방", "query": "박화"},
    )
    assert [item["nickname"] for item in searched.json()] == ["박화영", "박화진"]

    added_by_name = client.post(
        "/admin/room-admin",
        headers=auth,
        json={"room": "종합방", "nickname": "부방장"},
    )
    assert added_by_name.status_code == 200
    assert added_by_name.json()["userKey"] == "iris:sub"

    added_from_list = client.post(
        "/admin/room-admin",
        headers=auth,
        json={"room": "종합방", "nickname": "방장", "user_key": "iris:leader"},
    )
    assert added_from_list.status_code == 200

    admins = client.get(
        "/admin/room-admins", headers=auth, params={"room": "종합방"}
    )
    assert {(item["nickname"], item["role"]) for item in admins.json()} == {
        ("부방장", "admin"),
        ("방장", "admin"),
    }

    removed_admin = client.delete(
        "/admin/room-admin",
        headers=auth,
        params={"room": "종합방", "user_key": "iris:sub"},
    )
    assert removed_admin.status_code == 200
    assert removed_admin.json()["nickname"] == "부방장"

    denied_settings = client.get(
        "/admin/room-settings", params={"room": "종합방"}
    )
    assert denied_settings.status_code == 403

    default_settings = client.get(
        "/admin/room-settings", headers=auth, params={"room": "종합방"}
    )
    assert default_settings.json()["joinAlertThreshold"] == 5
    assert default_settings.json()["shopRegistrationAdminOnly"] is True
    assert default_settings.json()["shopRegistrationFee"] == 100
    assert default_settings.json()["shopRegistrationDeposit"] == 0

    invalid_settings = client.post(
        "/admin/room-settings",
        headers=auth,
        json={"room": "종합방", "join_alert_threshold": 1},
    )
    assert invalid_settings.status_code == 400

    saved_settings = client.post(
        "/admin/room-settings",
        headers=auth,
        json={"room": "종합방", "join_alert_threshold": 7},
    )
    assert saved_settings.json()["joinAlertThreshold"] == 7
    assert test_bot.admin_store.get_join_alert_threshold("종합방") == 7

    public_shop_registration = client.post(
        "/admin/room-settings",
        headers=auth,
        json={
            "room": "종합방",
            "shop_registration_admin_only": False,
            "shop_registration_fee": 150,
            "shop_registration_deposit": 500,
        },
    )
    assert public_shop_registration.json()["shopRegistrationAdminOnly"] is False
    assert public_shop_registration.json()["shopRegistrationFee"] == 150
    assert public_shop_registration.json()["shopRegistrationDeposit"] == 500
    assert not test_bot.admin_store.is_shop_registration_admin_only("종합방")
    assert test_bot.admin_store.get_shop_registration_costs("종합방") == (150, 500)

    invalid_shop_cost = client.post(
        "/admin/room-settings",
        headers=auth,
        json={"room": "종합방", "shop_registration_fee": -1},
    )
    assert invalid_shop_cost.status_code == 400

    long_text = "\n".join(f"{index}번째 줄 이벤트 안내" for index in range(120))
    assert len(long_text) > 1000

    denied = client.post(
        "/admin/command",
        json={"room": "종합방", "command": "이벤", "response": long_text},
    )
    assert denied.status_code == 403

    saved = client.post(
        "/admin/command",
        headers=auth,
        json={"room": "종합방", "command": "이벤", "response": long_text},
    )
    assert saved.status_code == 200
    assert saved.json()["length"] == len(long_text)

    fetched = client.get(
        "/admin/command",
        headers=auth,
        params={"room": "종합방", "command": "/이벤"},
    )
    assert fetched.json() == {"found": True, "command": "이벤", "response": long_text}

    rooms = client.get("/admin/rooms", headers=auth)
    assert rooms.json() == ["종합방"]

    reserved = client.post(
        "/admin/command",
        headers=auth,
        json={"room": "종합방", "command": "도감", "response": "x"},
    )
    assert reserved.status_code == 400

    listed = client.get("/admin/commands", headers=auth, params={"room": "종합방"})
    assert listed.json() == [{"command": "이벤", "length": len(long_text)}]

    missing = client.delete(
        "/admin/command",
        headers=auth,
        params={"room": "종합방", "command": "없는거"},
    )
    assert missing.status_code == 404
    assert "삭제할 명령어가 없습니다" in missing.json()["detail"]

    deleted = client.delete(
        "/admin/command",
        headers=auth,
        params={"room": "종합방", "command": "/이벤"},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "command": "이벤"}
    assert test_bot.admin_store.get_custom_command("종합방", "이벤") is None


def test_admin_web_add_announces_new_manager_to_target_room(
    tmp_path, monkeypatch
) -> None:
    import app.main as main_module

    test_bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "admin-secret")
    main_module._iris_outbox.clear()
    test_bot.admin_store.touch_room("CHAT-ADMIN", "종합방")
    test_bot.admin_store.record_chat_message(
        "종합방", "iris:sub", "부방장", "2026-08-18"
    )
    client = TestClient(main_module.app)
    auth = {"X-Bridge-Key": "admin-secret"}

    added = client.post(
        "/admin/room-admin",
        headers=auth,
        json={
            "room": "종합방",
            "nickname": "부방장",
            "user_key": "iris:sub",
        },
    )

    assert added.status_code == 200
    assert added.json()["notificationQueued"] is True
    assert main_module._iris_outbox == [
        {
            "type": "text",
            "room": "CHAT-ADMIN",
            "data": "부방장님이 관리자로 등록되셨습니다.",
        }
    ]

    duplicate = client.post(
        "/admin/room-admin",
        headers=auth,
        json={
            "room": "종합방",
            "nickname": "부방장",
            "user_key": "iris:sub",
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["notificationQueued"] is False
    assert len(main_module._iris_outbox) == 1
    main_module._iris_outbox.clear()


def test_latest_nickname_updates_on_commands_and_stays_room_scoped(tmp_path) -> None:
    from datetime import date

    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")
    user_key = "iris:42"

    store.add_admin(ChatUser(room="첫방", sender="예전닉", user_key=user_key))
    store.add_admin(ChatUser(room="둘째방", sender="둘째방닉", user_key=user_key))
    store.add_points("첫방", user_key, "예전닉", 10)
    store.seed_member_present("첫방", "42", "입장기록닉")
    store.register_raffle_recipient(
        "첫방", user_key, "예전닉", date.today().isoformat()
    )

    # 명령어는 채팅 수에 포함되지 않지만 최신 닉네임은 즉시 반영돼야 한다.
    assert bot.record_chat("첫방", "새닉네임", user_key, "/포인트") == ""
    assert store.raffle_pool("첫방", date.today().isoformat()) == []
    assert store.latest_nickname("첫방", user_key) == "새닉네임"
    assert store.list_room_members("첫방") == [("새닉네임", user_key)]
    assert store.attendance_ranking("첫방") == [("새닉네임", 0, 10)]
    assert store.raffle_recipient_history("첫방")[0]["display_name"] == "새닉네임"
    assert store.join_count_for_nickname("첫방", "새닉네임") == ("새닉네임", 1)

    first_room_admin = store.list_admin_records("첫방")[0]
    second_room_admin = store.list_admin_records("둘째방")[0]
    assert first_room_admin[0] == "새닉네임"
    assert second_room_admin[0] == "둘째방닉"


def test_owner_can_issue_room_management_site(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    test_bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "admin-secret")
    client = TestClient(main_module.app)
    auth = {"X-Bridge-Key": "admin-secret"}

    room = test_bot.admin_store.touch_room("CHAT-SITE", "사이트방")
    token = room["token"]

    denied = client.post("/admin/site-room", json={"room": "사이트방"})
    assert denied.status_code == 403

    unknown = client.post(
        "/admin/site-room", headers=auth, json={"room": "없는방"}
    )
    assert unknown.status_code == 404

    missing_password = client.post(
        "/admin/site-room", headers=auth, json={"room": "사이트방"}
    )
    assert missing_password.status_code == 400
    assert "비밀번호와 복구 단어" in missing_password.json()["detail"]

    issued = client.post(
        "/admin/site-room",
        headers=auth,
        json={
            "room": "사이트방",
            "password": "room-secret",
            "recovery_word": "복구단어",
        },
    )
    assert issued.status_code == 200
    assert issued.json() == {
        "ok": True,
        "room": "사이트방",
        "path": f"/r/{token}",
        "hasPassword": True,
    }
    assert test_bot.admin_store.check_room_password("사이트방", "room-secret")
    site_page = client.get(f"/r/{token}")
    assert "트레이너룸 콘솔" in site_page.text
    assert "KAKAOPOGO LAB · ROOM" in site_page.text
    assert "/ui-assets/kakaopogo-control-mark.webp" in site_page.text
    assert "방 운영 설정" in site_page.text
    assert 'data-section="commands"' in site_page.text
    assert '<details class="card" data-section="commands">' in site_page.text
    assert 'data-section="room-settings"' in site_page.text
    assert "initSectionState" in site_page.text
    assert "initAccordionMotion" in site_page.text
    assert "상품 등록을 오너와 관리자만 허용" in site_page.text
    assert "일반 사용자 상품 등록 수수료" in site_page.text
    assert "일반 사용자 상품 등록 보증금" in site_page.text

    token_settings = client.get(f"/r/{token}/room-settings")
    assert token_settings.json()["joinAlertThreshold"] == 5
    assert token_settings.json()["shopRegistrationAdminOnly"] is True
    assert token_settings.json()["shopRegistrationFee"] == 100
    assert token_settings.json()["shopRegistrationDeposit"] == 0

    wrong_settings = client.post(
        f"/r/{token}/room-settings",
        json={"join_alert_threshold": 8, "room_password": "wrong"},
    )
    assert wrong_settings.status_code == 403

    token_saved = client.post(
        f"/r/{token}/room-settings",
        json={
            "join_alert_threshold": 8,
            "shop_registration_admin_only": False,
            "shop_registration_fee": 200,
            "shop_registration_deposit": 700,
            "room_password": "room-secret",
        },
    )
    assert token_saved.json()["joinAlertThreshold"] == 8
    assert token_saved.json()["shopRegistrationAdminOnly"] is False
    assert token_saved.json()["shopRegistrationFee"] == 200
    assert token_saved.json()["shopRegistrationDeposit"] == 700
    assert test_bot.admin_store.get_join_alert_threshold("사이트방") == 8
    assert not test_bot.admin_store.is_shop_registration_admin_only("사이트방")
    assert test_bot.admin_store.get_shop_registration_costs("사이트방") == (200, 700)

    # 다시 확인해도 기존 고정 링크를 그대로 돌려준다.
    reissued = client.post(
        "/admin/site-room", headers=auth, json={"room": "사이트방"}
    )
    assert reissued.status_code == 200
    assert reissued.json()["path"] == f"/r/{token}"
    assert client.get(f"/r/{token}/info").json()["room"] == "사이트방"


def test_raffle_recipient_search_register_and_cancel(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    from datetime import date, timedelta

    store = AdminStore(tmp_path / "test.sqlite3")
    test_bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "admin-secret")
    client = TestClient(main_module.app)
    auth = {"X-Bridge-Key": "admin-secret"}

    room = store.touch_room("CHAT-RAFFLE", "수령방")
    token = room["token"]
    assert store.set_room_password("수령방", "room-secret", "복구단어")
    today = date.today().isoformat()
    for user_key, nickname in (
        ("iris:1", "박화영"),
        ("iris:2", "박화진"),
        ("iris:3", "박화명"),
        ("iris:4", "김철수"),
    ):
        store.record_chat_message("수령방", user_key, nickname, today)

    searched = client.get(
        "/admin/raffle-recipients",
        headers=auth,
        params={"room": "수령방", "query": "박화"},
    )
    assert searched.status_code == 200
    assert [item["nickname"] for item in searched.json()["candidates"]] == [
        "박화명",
        "박화영",
        "박화진",
    ]

    registered = client.post(
        "/admin/raffle-recipient",
        headers=auth,
        json={"room": "수령방", "user_key": "iris:1"},
    )
    assert registered.status_code == 200
    recipient_id = registered.json()["id"]
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    assert "iris:1" not in {
        user_key
        for user_key, _nickname, _count in store.raffle_candidates(
            "수령방", today, excluded_after=cutoff
        )
    }

    # 같은 날 같은 사람을 다시 눌러도 기록은 한 건만 유지한다.
    duplicate = client.post(
        "/admin/raffle-recipient",
        headers=auth,
        json={"room": "수령방", "user_key": "iris:1"},
    )
    assert duplicate.json()["id"] == recipient_id
    assert len(store.raffle_recipient_history("수령방")) == 1

    wrong_password = client.get(
        f"/r/{token}/raffle-recipients",
        params={"query": "박화", "password": "wrong"},
    )
    assert wrong_password.status_code == 403

    site_registered = client.post(
        f"/r/{token}/raffle-recipient",
        json={"user_key": "iris:2", "room_password": "room-secret"},
    )
    assert site_registered.status_code == 200
    assert site_registered.json()["nickname"] == "박화진"

    removed = client.delete(
        "/admin/raffle-recipient",
        headers=auth,
        params={"room": "수령방", "recipient_id": recipient_id},
    )
    assert removed.status_code == 200
    assert "iris:1" in {
        user_key
        for user_key, _nickname, _count in store.raffle_candidates(
            "수령방", today, excluded_after=cutoff
        )
    }

    site_page = client.get(f"/r/{token}")
    assert "추첨 상품 수령자" in site_page.text
    owner_page = client.get("/admin")
    assert "추첨 상품 수령자" in owner_page.text


def test_migrate_room_moves_and_merges_data(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    old, new = "옛방", "새방"

    store.add_admin(ChatUser(room=old, sender="부방장", user_key="hash:sub"))
    store.upsert_custom_command(old, "공지", "옛 공지", "오너")
    store.upsert_custom_command(old, "규칙", "규칙 내용", "오너")
    # 새 이름으로 이미 같은 명령어가 생긴 경우: 새 이름 쪽을 남긴다.
    store.upsert_custom_command(new, "공지", "새 공지", "오너")
    # 출석: 안 겹치는 사람은 이동, 겹치는 사람은 합산.
    store.check_in(ChatUser(room=old, sender="지우", user_key="hash:ash"), "2026-07-10", 5)
    store.check_in(ChatUser(room=old, sender="웅이", user_key="hash:brock"), "2026-07-10", 5)
    store.check_in(ChatUser(room=new, sender="지우", user_key="hash:ash"), "2026-07-12", 5)
    store.set_join_alert_threshold(old, 9)
    store.set_shop_registration_admin_only(old, False)
    store.set_shop_registration_costs(old, 250, 800)

    moved = store.migrate_room(old, new)

    assert moved["custom_commands"] == 1  # '규칙'만 이동 ('공지'는 새쪽 유지)
    assert moved["room_admins"] == 1
    assert moved["room_settings"] == 1
    assert store.get_join_alert_threshold(new) == 9
    assert store.get_join_alert_threshold(old) == 5
    assert not store.is_shop_registration_admin_only(new)
    assert store.is_shop_registration_admin_only(old)
    assert store.get_shop_registration_costs(new) == (250, 800)
    assert store.get_shop_registration_costs(old) == (100, 0)
    assert store.get_custom_command(new, "공지").response == "새 공지"
    assert store.get_custom_command(new, "규칙").response == "규칙 내용"
    assert store.get_custom_command(old, "규칙") is None
    assert ("부방장", "admin", "hash:sub") in store.list_admin_records(new)

    ranking = dict(
        (name, (days, points)) for name, days, points in store.attendance_ranking(new)
    )
    assert ranking["지우"] == (2, 10)  # 옛방 1일 + 새방 1일 합산
    assert ranking["웅이"] == (1, 5)
    assert store.attendance_ranking(old) == []


def test_room_registry_token_survives_rename(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")

    first = store.touch_room("CHAT-A", "처음이름방")
    token = first["token"]
    assert token
    assert first["renamed_from"] is None
    store.upsert_custom_command("처음이름방", "공지", "안녕", "오너")

    # 토큰으로 방 이름과 명령어를 찾을 수 있다.
    assert store.get_room_name_by_token(token) == "처음이름방"
    assert store.get_site_token_for_room_name("처음이름방") == token

    # 같은 chat_id로 이름만 바뀌면 토큰은 그대로, 데이터는 새 이름으로 이전된다.
    second = store.touch_room("CHAT-A", "바뀐이름방")
    assert second["token"] == token
    assert second["renamed_from"] == "처음이름방"
    assert store.get_room_name_by_token(token) == "바뀐이름방"
    assert store.get_custom_command("바뀐이름방", "공지").response == "안녕"
    assert store.get_custom_command("처음이름방", "공지") is None

    # 다른 방은 다른 토큰을 받는다.
    other = store.touch_room("CHAT-B", "다른방")
    assert other["token"] != token
    store.upsert_custom_command("다른방", "공지", "다른 방 공지", "다른방장")
    assert store.get_room_name_by_token(other["token"]) == "다른방"
    assert store.get_custom_command("바뀐이름방", "공지").response == "안녕"
    assert store.get_custom_command("다른방", "공지").response == "다른 방 공지"


def test_site_link_never_leaks_in_group_room(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    store.touch_room("CHAT-A", "우리방")
    bot = PokemonGoBot(admin_store=store)
    owner = ChatUser(room="개인톡:owner", sender="박정우", user_key="iris:owner")
    store.add_owner(owner)
    token = store.get_site_token_for_room_name("우리방")

    # 공개 채팅방에서는 오너가 쳐도 링크가 절대 안 나온다(개인톡으로 안내만).
    in_group = bot._handle_site_link(
        ChatUser(room="우리방", sender="박정우", user_key="iris:owner"), ""
    )
    assert f"/r/{token}" not in in_group.reply
    assert "개인톡" in in_group.reply

    # 공개 채팅방에서 일반 사용자가 치면 조용히 무시한다(존재 자체를 안 흘림).
    stranger = bot._handle_site_link(
        ChatUser(room="우리방", sender="행인", user_key="iris:stranger"), ""
    )
    assert stranger.silent is True


def test_site_link_shown_only_in_owner_dm(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    store.touch_room("CHAT-A", "우리방")
    bot = PokemonGoBot(admin_store=store)
    owner = ChatUser(room="개인톡:owner", sender="박정우", user_key="iris:owner")
    store.add_owner(owner)
    token = store.get_site_token_for_room_name("우리방")

    # 개인톡에서 오너는 방 목록과 링크를 받는다.
    listing = bot._handle_site_link(owner, "")
    assert f"/r/{token}" in listing.reply
    assert "우리방" in listing.reply

    # 방 이름을 지정하면 그 방 링크만 준다.
    one = bot._handle_site_link(owner, "우리방")
    assert f"/r/{token}" in one.reply

    # 오너가 아닌 사람은 개인톡에서도 링크를 못 본다.
    stranger = ChatUser(room="개인톡:x", sender="행인", user_key="iris:stranger")
    denied = bot._handle_site_link(stranger, "")
    assert f"/r/{token}" not in denied.reply
    assert "오너" in denied.reply


@pytest.mark.anyio
async def test_member_join_counting_is_per_room(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    admin = ChatUser(room="A방", sender="관리자", user_key="iris:x")
    store.add_admin(admin)
    store.add_admin(ChatUser(room="B방", sender="관리자", user_key="iris:x"))

    # 기본 설정은 5회라 4회까지 조용하고 5회부터 안내한다.
    for _ in range(4):
        assert bot.handle_member_joins("A방", [("u1", "들낙이")]) == ""
    fifth = bot.handle_member_joins("A방", [("u1", "들낙이")])
    assert "들낙 유저 의심" in fifth
    assert "입장 5회차" in fifth

    # 다른 방 카운트와 섞이지 않는다.
    other = bot.handle_member_joins("B방", [("u1", "들낙이")])
    assert other == ""

    # 일반 사용자는 /들낙을 조회할 수 없다.
    denied = await bot.handle("/들낙", room="A방", sender="일반", user_key="iris:no")
    assert denied.reply == "이 명령어는 해당 방의 owner 또는 admin만 사용할 수 있습니다."

    # 관리자의 /들낙 랭킹은 그 방 기준이고 조회 내용은 그대로다.
    ranking = await bot.handle("/들낙", room="A방", sender="관리자", user_key="iris:x")
    assert "들낙이" in ranking.reply and "5회" in ranking.reply
    empty_b = await bot.handle("/들낙", room="B방", sender="관리자", user_key="iris:x")
    assert "없어요" in empty_b.reply and "들낙이" not in empty_b.reply

    # /들낙 닉네임은 특정 사람 조회.
    named = await bot.handle("/들낙 들낙이", room="A방", sender="관리자", user_key="iris:x")
    assert "들낙이" in named.reply and "5회차" in named.reply

    # 내보내면(퇴장·강퇴) 현재 인원에서 빠져 명단에 안 나온다.
    bot.handle_member_leaves("A방", [("u1", "들낙이")])
    after_kick = await bot.handle("/들낙", room="A방", sender="관리자", user_key="iris:x")
    assert "들낙이" not in after_kick.reply

    # 다시 들어오면 카운트를 이어받아 다시 명단에 뜬다.
    bot.handle_member_joins("A방", [("u1", "들낙이")])
    rejoined = await bot.handle("/들낙", room="A방", sender="관리자", user_key="iris:x")
    assert "들낙이" in rejoined.reply and "6회" in rejoined.reply

    # 방마다 기준을 다르게 저장할 수 있다.
    store.set_join_alert_threshold("B방", 3)
    assert bot.handle_member_joins("B방", [("u1", "들낙이")]) == ""
    third = bot.handle_member_joins("B방", [("u1", "들낙이")])
    assert "입장 3회차" in third


@pytest.mark.anyio
async def test_kicked_member_rejoin_is_not_counted(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.set_join_alert_threshold("방", 2)
    store.add_admin(ChatUser(room="방", sender="관리자", user_key="iris:y"))

    # 정상 입장 1회.
    assert bot.handle_member_joins("방", [("k1", "내풀이")]) == ""

    # 관리자가 내보내기(강퇴) 후 차단을 풀어 다시 들어온 경우는 카운트 제외.
    bot.handle_member_leaves("방", [("k1", "내풀이")], kicked=True)
    after = bot.handle_member_joins("방", [("k1", "내풀이")])
    assert after == ""  # 의심 문구 없음

    # 그래서 들낙 명단에도 안 뜬다(여전히 입장 1회로 취급).
    listing = await bot.handle("/들낙", room="방", sender="관리자", user_key="iris:y")
    assert "내풀이" not in listing.reply

    # 이후 스스로 나갔다가 다시 들어오면 그때는 카운트된다.
    bot.handle_member_leaves("방", [("k1", "내풀이")], kicked=False)
    warn = bot.handle_member_joins("방", [("k1", "내풀이")])
    assert "입장 2회차" in warn


@pytest.mark.anyio
async def test_existing_member_rejoin_becomes_second_entry(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.set_join_alert_threshold("방", 2)
    store.add_admin(ChatUser(room="방", sender="관리자", user_key="iris:z"))

    # 추적 시작 전부터 있던 사람이 채팅을 하면 '입장 1회'로 기준이 잡힌다.
    store.seed_member_present("방", "old1", "터줏대감")
    # 아직 재입장 전이라 들낙 명단엔 없다.
    before = await bot.handle("/들낙", room="방", sender="관리자", user_key="iris:z")
    assert "터줏대감" not in before.reply

    # 나갔다가 다시 들어오면 곧바로 입장 2회차.
    bot.handle_member_leaves("방", [("old1", "터줏대감")])
    warn = bot.handle_member_joins("방", [("old1", "터줏대감")])
    assert "입장 2회차" in warn

    # seed 는 이미 있는 기록의 입장 횟수를 덮어쓰지 않는다.
    store.seed_member_present("방", "old1", "터줏대감")
    listing = await bot.handle("/들낙", room="방", sender="관리자", user_key="iris:z")
    assert "터줏대감" in listing.reply and "2회" in listing.reply


def test_daily_brief_groups_today_and_tomorrow() -> None:
    from datetime import datetime, timedelta

    from app.events import KST, PokemonGoEvent, format_daily_brief

    now = datetime(2026, 8, 1, 9, 0, tzinfo=KST)

    def event(name, start, end, kind="event"):
        return PokemonGoEvent(name=name, event_type=kind, start=start, end=end)

    events = [
        event("오늘시작", now, now + timedelta(days=3), "community-day"),
        event("오늘종료", now - timedelta(days=2), now + timedelta(hours=6)),
        event("내일시작", now + timedelta(days=1), now + timedelta(days=2)),
        event("한참뒤", now + timedelta(days=9), now + timedelta(days=10)),
        event("진행중", now - timedelta(days=3), now + timedelta(days=3)),
    ]

    brief = format_daily_brief(events, now=now)
    assert "🎉 오늘 시작" in brief and "오늘시작" in brief
    assert "커뮤니티 데이" in brief  # 이벤트 종류는 한글로
    assert "⏰ 오늘 종료" in brief and "오늘종료" in brief
    assert "🔜 내일 시작" in brief and "내일시작" in brief
    # 오늘과 무관한 일정은 브리핑에 넣지 않는다.
    assert "한참뒤" not in brief and "진행중" not in brief

    # 알릴 게 없으면 빈 문자열이라 아무것도 보내지 않는다.
    assert format_daily_brief([events[3]], now=now) == ""


@pytest.mark.anyio
async def test_daily_brief_sends_once_per_day(tmp_path, monkeypatch) -> None:
    from datetime import datetime, timedelta

    import app.main as main_module
    from app.events import KST, EventSchedule, PokemonGoEvent

    test_bot = PokemonGoBot(admin_store=AdminStore(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(main_module, "bot", test_bot)
    now = datetime(2026, 8, 1, 9, 0, tzinfo=KST)

    class StubEvents:
        async def get_schedule(self):
            return EventSchedule(
                events=[
                    PokemonGoEvent(
                        name="오늘시작",
                        event_type="event",
                        start=now,
                        end=now + timedelta(days=1),
                    )
                ],
                raids=[],
            )

    test_bot.event_client = StubEvents()
    test_bot.admin_store.touch_room("CHAT-1", "우리방")
    test_bot.admin_store.set_event_notify("우리방", True)
    main_module._iris_outbox.clear()

    sent = await main_module.send_daily_briefs(now)
    assert sent == ["우리방"]
    assert len(main_module._iris_outbox) == 1
    assert main_module._iris_outbox[0]["room"] == "CHAT-1"
    assert "오늘시작" in main_module._iris_outbox[0]["data"]

    # 같은 날 다시 돌아도 중복 발송하지 않는다.
    assert await main_module.send_daily_briefs(now) == []
    assert len(main_module._iris_outbox) == 1

    # 날이 바뀌면 그날 몫을 다시 보낸다(이 이벤트는 이튿날 종료).
    assert await main_module.send_daily_briefs(now + timedelta(days=1)) == ["우리방"]
    assert len(main_module._iris_outbox) == 2
    assert "오늘 종료" in main_module._iris_outbox[1]["data"]
    # 알림을 끈 방은 대상에서 빠진다.
    test_bot.admin_store.set_event_notify("우리방", False)
    assert test_bot.admin_store.event_notify_targets("2026-08-03") == []
    main_module._iris_outbox.clear()


def test_weather_boost_formatting() -> None:
    from datetime import datetime

    from app.boost import format_boost, pogo_weather
    from app.weather import CityWeather, NationalWeather, PeriodWeather

    assert pogo_weather("강한 소나기") == "비"
    assert pogo_weather("대체로 맑음") == "화창"
    assert pogo_weather("눈소나기") == "눈"

    def city(name, morning, afternoon):
        return CityWeather(
            location=name,
            morning=PeriodWeather(name, morning, 20, 0),
            afternoon=PeriodWeather(name, afternoon, 25, 0),
        )

    weather = NationalWeather(
        date=datetime(2026, 8, 1),
        cities=[city("서울", "비", "비"), city("부산", "맑음", "눈")],
    )

    summary = format_boost(weather)
    assert "서울 · 비 → 물 전기 벌레" in summary
    assert "부산 · 눈 → 얼음 강철" in summary  # 오후 기준

    # 하루 종일 같은 날씨면 한 번만, 어태커 추천이 붙는다.
    seoul = format_boost(weather, "서울")
    assert seoul.count("→ 물 전기 벌레") == 1
    assert "[종일]" in seoul
    assert "가이오가" in seoul

    # 오전·오후가 다르면 따로 보여준다.
    busan = format_boost(weather, "부산")
    assert "[오전]" in busan and "[오후]" in busan

    assert "지역은 없어요" in format_boost(weather, "평양")


def test_parse_warning_commands() -> None:
    assert parse_command("/경고추가 홍길동 도배") == ("warn_add", "홍길동 도배")
    assert parse_command("/경고") == ("warn_list", "")
    assert parse_command("/경고삭제 홍길동") == ("warn_remove", "홍길동")
    assert parse_command("/관리자명령어") == ("admin_help", "")


@pytest.mark.anyio
async def test_admin_command_guide_is_for_admin_role_only(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(
        ChatUser(room="개인톡:owner", sender="오너", user_key="iris:owner")
    )
    store.add_admin(
        ChatUser(room="레이드방", sender="부방장", user_key="iris:admin")
    )

    admin = await bot.handle(
        "/관리자명령어",
        room="레이드방",
        sender="부방장",
        user_key="iris:admin",
    )
    owner = await bot.handle(
        "/관리자명령어",
        room="레이드방",
        sender="오너",
        user_key="iris:owner",
    )
    member = await bot.handle(
        "/관리자명령어",
        room="레이드방",
        sender="일반",
        user_key="iris:member",
    )

    assert "【 관리자 명령어 】" in admin.reply
    for command in (
        "/경고추가",
        "/들낙",
        "/상품삭제",
        "/레이드초기화",
        "/명령어등록",
    ):
        assert command in admin.reply
    for owner_command in (
        "/오너등록",
        "/관리자추가",
        "/관리자승인",
        "/경고권한부여",
    ):
        assert owner_command not in admin.reply
    assert owner.reply == "이 명령어는 해당 방의 admin만 사용할 수 있습니다."
    assert member.reply == "이 명령어는 해당 방의 admin만 사용할 수 있습니다."

    command_list = await bot.handle(
        "/명령어목록",
        room="레이드방",
        sender="부방장",
        user_key="iris:admin",
    )
    assert "/관리자명령어" in command_list.reply


@pytest.mark.anyio
async def test_warning_tracks_by_id_across_nickname_change(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    admin = ChatUser(room="방", sender="관리자", user_key="iris:boss")
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:boss"))

    # 대상이 채팅을 해서 닉네임->ID 매핑이 생긴다.
    store.record_chat_message("방", "iris:9999", "홍길동", "2026-07-30")

    added = await bot.handle("/경고추가 홍길동 도배", room="방", sender="관리자", user_key="iris:boss")
    assert "경고 등록" in added.reply and "1회" in added.reply

    # 대상이 닉네임을 바꾸고 채팅하면 최신 닉네임이 잡힌다.
    store.record_chat_message("방", "iris:9999", "김철수", "2026-07-31")
    listed = await bot.handle("/경고", room="방", sender="관리자", user_key="iris:boss")
    assert "김철수" in listed.reply  # 바뀐 닉네임으로 표시
    assert "도배" in listed.reply

    # 권한 없는 사용자는 경고를 못 넣는다.
    denied = await bot.handle("/경고추가 홍길동 사유", room="방", sender="행인", user_key="iris:rando")
    assert "경고 권한" in denied.reply


@pytest.mark.anyio
async def test_room_admin_automatically_gets_warning_and_join_lookup_permissions(
    tmp_path,
) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    manager = ChatUser(room="관리방", sender="부방장", user_key="iris:manager")
    store.add_admin(manager)
    store.record_chat_message("관리방", "iris:target", "대상자", "2026-08-18")
    for _ in range(2):
        bot.handle_member_joins("관리방", [("target", "대상자")])

    assert not store.has_warn_permission("관리방", manager.user_key)

    added = await bot.handle(
        "/경고추가 대상자 도배", room="관리방", sender="부방장", user_key=manager.user_key
    )
    warnings = await bot.handle(
        "/경고", room="관리방", sender="부방장", user_key=manager.user_key
    )
    joins = await bot.handle(
        "/들낙", room="관리방", sender="부방장", user_key=manager.user_key
    )

    assert "경고 등록" in added.reply
    assert "대상자" in warnings.reply and "도배" in warnings.reply
    assert "대상자" in joins.reply and "2회" in joins.reply

    denied_warning = await bot.handle(
        "/경고", room="다른방", sender="부방장", user_key=manager.user_key
    )
    denied_joins = await bot.handle(
        "/들낙", room="다른방", sender="부방장", user_key=manager.user_key
    )
    assert "경고 권한" in denied_warning.reply
    assert "owner 또는 admin" in denied_joins.reply


@pytest.mark.anyio
async def test_chat_earns_points_shared_with_attendance(tmp_path) -> None:
    from datetime import date

    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)

    # 채팅 1회당 1포인트.
    for _ in range(3):
        bot.record_chat("방", "지우", "iris:ash", "안녕하세요")
    assert store.get_points("방", "iris:ash") == 3

    # 명령어는 포인트도 랭킹도 올리지 않는다(등록 안 된 명령어 포함).
    bot.record_chat("방", "지우", "iris:ash", "/포인트")
    bot.record_chat("방", "지우", "iris:ash", "/상품")
    bot.record_chat("방", "지우", "iris:ash", "/아무거나없는명령")
    assert store.get_points("방", "iris:ash") == 3
    assert store.chat_ranking("방", today=date.today().isoformat()) == [("지우", 3)]

    # 출석 포인트와 같은 지갑에 쌓인다.
    store.check_in(ChatUser(room="방", sender="지우", user_key="iris:ash"), "2026-08-01", 5)
    assert store.get_points("방", "iris:ash") == 8

    mine = await bot.handle("/포인트", room="방", sender="지우", user_key="iris:ash")
    assert "8P" in mine.reply

    # 같은 사용자가 다른 방에서 활동해도 포인트와 출석은 별도 지갑이다.
    bot.record_chat("다른방", "지우", "iris:ash", "반가워요")
    assert store.get_points("다른방", "iris:ash") == 1
    assert store.get_points("방", "iris:ash") == 8
    other_room = await bot.handle(
        "/포인트", room="다른방", sender="지우", user_key="iris:ash"
    )
    assert "1P" in other_room.reply
    assert store.attendance_ranking("다른방") == [("지우", 0, 1)]


@pytest.mark.anyio
async def test_shop_purchase_and_insufficient_points(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))
    owner = {"room": "방", "sender": "오너", "user_key": "iris:owner"}
    buyer = {"room": "방", "sender": "지우", "user_key": "iris:ash"}

    # 상품은 등록 순서대로 번호가 붙는다.
    first = await bot.handle("/상품등록 전설몬 1마리 500", **owner)
    assert "1번" in first.reply and "500P" in first.reply
    second = await bot.handle("/상품등록 레이드 초대권 100", **owner)
    assert "2번" in second.reply

    # 상품도 방별로 분리되어 다른 방 상점에는 나타나지 않는다.
    other_room = await bot.handle(
        "/상품", room="다른방", sender="지우", user_key="iris:ash"
    )
    assert "등록된 상품이 없어요" in other_room.reply

    # 기본값은 owner/admin 전용이며, 방 설정으로 일반 사용자 등록을 열 수 있다.
    denied_add = await bot.handle("/상품등록 임시상품 10", **buyer)
    assert denied_add.reply == (
        "상품 등록은 해당 방의 owner 또는 admin만 사용할 수 있습니다.\n"
        "상품 등록이 필요하면 방 관리자에게 문의해 주세요."
    )
    store.set_shop_registration_admin_only("방", False)
    store.set_shop_registration_costs("방", 0, 0)
    by_member = await bot.handle("/상품등록 임시상품 10", **buyer)
    assert "3번" in by_member.reply
    denied_remove = await bot.handle("/상품삭제 3", **buyer)
    assert denied_remove.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."
    assert "뺐어요" in (await bot.handle("/상품삭제 3", **owner)).reply

    # 포인트가 모자라면 안내만 하고 차감하지 않는다.
    store.add_points("방", "iris:ash", "지우", 60)
    poor = await bot.handle("/구매 2", **buyer)
    assert "포인트가 부족해요" in poor.reply and "40P 더" in poor.reply
    assert store.get_points("방", "iris:ash") == 60

    # 충분하면 구매되고 포인트가 줄어든다.
    store.add_points("방", "iris:ash", "지우", 40)
    bought = await bot.handle("/구매 2", **buyer)
    assert "구매 완료" in bought.reply and "레이드 초대권" in bought.reply
    assert store.get_points("방", "iris:ash") == 0

    # 팔린 상품은 목록에서 사라져 다시 살 수 없다.
    assert "레이드 초대권" not in (await bot.handle("/상품", **buyer)).reply
    assert "없어요" in (await bot.handle("/구매 2", **buyer)).reply

    # 목록과 구매 내역에 반영된다.
    listing = await bot.handle("/상품", **buyer)
    assert "1. 전설몬 1마리 · 500P" in listing.reply
    assert "상품 등록자 : 오너" in listing.reply

    # 등록자가 닉네임을 바꾸면 목록도 최신 닉으로 따라간다.
    store.record_chat_message("방", "iris:owner", "새오너닉", "2026-08-02")
    renamed = await bot.handle("/상품", **buyer)
    assert "상품 등록자 : 새오너닉" in renamed.reply

    # 구매 내역은 누구나 볼 수 있고 번호·등록자가 붙는다.
    history = await bot.handle("/구매내역", **buyer)
    assert "지우" in history.reply and "레이드 초대권" in history.reply
    assert "1. " in history.reply
    # 상품이 팔려 사라진 뒤에도 등록자는 남고, 닉을 바꾸면 최신 닉으로 나온다.
    assert "상품 등록자 : 새오너닉" in history.reply

    # 구매내역 정리도 owner/admin만 할 수 있다.
    denied_clear = await bot.handle("/구매내역삭제 1", **buyer)
    assert denied_clear.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."
    cleared = await bot.handle("/구매내역삭제 1", **owner)
    assert "전달 완료" in cleared.reply and "레이드 초대권" in cleared.reply
    assert "구매 내역이 없어요" in (await bot.handle("/구매내역", **buyer)).reply
    assert "없어요" in (await bot.handle("/구매내역삭제 1", **owner)).reply

    # 먼저 산 것이 1번으로 위에 오고, 번호는 1부터 이어진다.
    store.record_purchase("방", "iris:ash", "지우", "먼저산것", 10)
    store.record_purchase("방", "iris:b", "링딩", "나중산것", 10)
    listing = await bot.handle("/구매내역", **buyer)
    assert listing.reply.index("1. ") < listing.reply.index("2. ")
    assert listing.reply.index("먼저산것") < listing.reply.index("나중산것")

    # 화면 번호로 지우면 그 줄이 지워지고 남은 건 번호가 당겨진다.
    picked = await bot.handle("/구매내역삭제 1", **owner)
    assert "먼저산것" in picked.reply
    after = await bot.handle("/구매내역", **buyer)
    assert "1. " in after.reply and "나중산것" in after.reply

    # 전체 삭제도 된다.
    store.record_purchase("방", "iris:ash", "지우", "간식", 10)
    assert "2건을 모두 지웠어요" in (await bot.handle("/구매내역삭제 전체", **owner)).reply

    # 없는 번호는 막는다.
    assert "없어요" in (await bot.handle("/구매 99", **buyer)).reply


@pytest.mark.anyio
async def test_shop_registration_can_override_registrant_nickname(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))
    owner = {"room": "방", "sender": "관리자", "user_key": "iris:owner"}

    own_item = await bot.handle("/상품등록 관리자 상품 100", **owner)
    assert "등록자 : 관리자" in own_item.reply
    assert store.get_shop_item("방", 1) == ("관리자 상품", 100, "iris:owner", "관리자")

    store.record_chat_message("방", "iris:donor", "나눔 왕", "2026-08-14")
    named_item = await bot.handle(
        "/상품등록 리모트패스 3장 500 나눔 왕", **owner
    )
    assert "2번 · 리모트패스 3장 · 500P" in named_item.reply
    assert "등록자 : 나눔 왕" in named_item.reply
    assert store.get_shop_item("방", 2) == (
        "리모트패스 3장",
        500,
        "iris:donor",
        "나눔 왕",
    )

    unknown_item = await bot.handle(
        "/상품등록 특별 선물 250 익명 기부자", **owner
    )
    assert "등록자 : 익명 기부자" in unknown_item.reply
    assert store.get_shop_item("방", 3) == (
        "특별 선물",
        250,
        "",
        "익명 기부자",
    )

    listing = await bot.handle("/상품", room="방", sender="구매자", user_key="iris:buyer")
    assert "상품 등록자 : 관리자" in listing.reply
    assert "상품 등록자 : 나눔 왕" in listing.reply
    assert "상품 등록자 : 익명 기부자" in listing.reply


@pytest.mark.anyio
async def test_shop_guides_are_split_by_permission(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))

    denied = await bot.handle("/상품기능가이드", room="방", sender="일반 사용자")
    assert denied.reply == "이 명령어는 해당 방의 owner 또는 admin만 사용할 수 있습니다."

    guide = await bot.handle(
        "/상품기능가이드", room="방", sender="오너", user_key="iris:owner"
    )
    assert "【 포인트 상점 기능 가이드 】" in guide.reply
    assert "/상품등록 상품명 포인트 닉네임" in guide.reply
    assert "/구매내역삭제 전체" in guide.reply

    public_commands = await bot.handle(
        "/상품명령어", room="방", sender="일반 사용자"
    )
    assert "【 포인트 상점 명령어 】" in public_commands.reply
    assert "/상품" in public_commands.reply
    assert "/구매 상품번호" in public_commands.reply
    assert "/구매내역" in public_commands.reply
    assert "/상품등록" not in public_commands.reply
    assert "/상품삭제" not in public_commands.reply
    assert "/구매내역삭제" not in public_commands.reply

    assert "상품기능가이드" in PokemonGoBot._reserved_custom_commands()
    assert "상품명령어" in PokemonGoBot._reserved_custom_commands()

    help_reply = await bot.handle("/도움말", room="방", sender="일반 사용자")
    command_reply = await bot.handle("/명령어", room="방", sender="일반 사용자")
    assert "/상품명령어" in help_reply.reply
    assert "/상품명령어" in command_reply.reply
    assert "/상품기능가이드" not in help_reply.reply
    assert "/상품기능가이드" not in command_reply.reply

    store.set_shop_registration_admin_only("방", False)
    store.set_shop_registration_costs("방", 100, 500)
    public_with_registration = await bot.handle(
        "/상품명령어", room="방", sender="일반 사용자"
    )
    assert "/상품등록 상품명 포인트" in public_with_registration.reply
    assert "등록 수수료 : 100P" in public_with_registration.reply
    assert "보증금 : 500P" in public_with_registration.reply
    assert "총 600P" in public_with_registration.reply


@pytest.mark.anyio
async def test_public_shop_registration_charges_fee_and_refunds_deposit(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.set_shop_registration_admin_only("방", False)
    seller = {"room": "방", "sender": "판매자", "user_key": "iris:seller"}
    buyer = {"room": "방", "sender": "구매자", "user_key": "iris:buyer"}

    # 일반 사용자 등록을 열면 기본 수수료 100P, 보증금 0P가 적용된다.
    assert store.get_shop_registration_costs("방") == (100, 0)
    store.add_points("방", "iris:seller", "판매자", 99)
    insufficient = await bot.handle("/상품등록 기본상품 300", **seller)
    assert "필요 포인트 : 100P" in insufficient.reply
    assert store.list_shop_items("방") == []
    assert store.get_points("방", "iris:seller") == 99

    store.add_points("방", "iris:seller", "판매자", 1)
    charged_fee = await bot.handle("/상품등록 기본상품 300", **seller)
    assert "차감 : 100P (수수료 100P + 보증금 0P)" in charged_fee.reply
    assert store.get_points("방", "iris:seller") == 0

    store.add_points("방", "iris:buyer", "구매자", 300)
    await bot.handle("/구매 1", **buyer)
    assert store.get_points("방", "iris:seller") == 0  # 수수료는 반환되지 않는다.

    # 수수료 100P + 보증금 500P면 등록 시 600P가 빠지고 판매 시 500P만 돌아온다.
    store.set_shop_registration_costs("방", 100, 500)
    store.add_points("방", "iris:seller", "판매자", 600)
    charged_deposit = await bot.handle("/상품등록 보증상품 200", **seller)
    assert "차감 : 600P (수수료 100P + 보증금 500P)" in charged_deposit.reply
    assert "보증금 500P는 상품이 판매되면 반환됩니다" in charged_deposit.reply
    assert store.get_points("방", "iris:seller") == 0

    store.add_points("방", "iris:buyer", "구매자", 200)
    bought = await bot.handle("/구매 1", **buyer)
    assert "판매자 님에게 보증금 500P 반환" in bought.reply
    assert store.get_points("방", "iris:seller") == 500

    # 일반 사용자는 다른 사람을 등록자로 지정할 수 없다.
    store.add_points("방", "iris:seller", "판매자", 600)
    impersonation = await bot.handle("/상품등록 다른상품 100 다른사람", **seller)
    assert "등록자 닉네임을 따로 지정할 수 없습니다" in impersonation.reply
    assert store.get_points("방", "iris:seller") == 1100

    # owner/admin이 직접 등록할 때는 수수료와 보증금이 차감되지 않는다.
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))
    manager = {"room": "방", "sender": "오너", "user_key": "iris:owner"}
    manager_item = await bot.handle("/상품등록 관리자상품 100 지정등록자", **manager)
    assert "등록자 : 지정등록자" in manager_item.reply
    assert "차감" not in manager_item.reply
    assert store.get_points("방", "iris:owner") == 0


@pytest.mark.anyio
async def test_shop_renumbers_after_delete(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    who = {"room": "방", "sender": "링딩", "user_key": "iris:a"}
    store.add_admin(ChatUser(room="방", sender="링딩", user_key="iris:a"))

    for name in ("상품하나", "상품둘", "상품셋"):
        await bot.handle(f"/상품등록 {name} 10", **who)

    # 1번을 지우면 뒤 상품이 앞으로 당겨진다.
    removed = await bot.handle("/상품삭제 1", **who)
    assert "다시 매겼어요" in removed.reply
    assert [(no, name) for no, name, *_ in store.list_shop_items("방")] == [
        (1, "상품둘"),
        (2, "상품셋"),
    ]

    # 다음 등록은 3번으로 이어진다(4번으로 건너뛰지 않는다).
    added = await bot.handle("/상품등록 상품넷 10", **who)
    assert "3번" in added.reply

    # 당겨진 번호로 바로 살 수 있고, 팔린 상품은 목록에서 빠진다.
    store.add_points("방", "iris:a", "링딩", 10)
    bought = await bot.handle("/구매 1", **who)
    assert "상품둘" in bought.reply
    assert [(no, name) for no, name, *_ in store.list_shop_items("방")] == [
        (1, "상품셋"),
        (2, "상품넷"),
    ]

    # 마지막 하나만 남기고 지워도 번호가 어긋나지 않는다.
    await bot.handle("/상품삭제 1", **who)
    assert [(no, name) for no, name, *_ in store.list_shop_items("방")] == [(1, "상품넷")]


@pytest.mark.anyio
async def test_shop_delete_permission_is_room_scoped(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    admin = {"sender": "부방장", "user_key": "iris:sub"}
    store.add_admin(ChatUser(room="A방", **admin))

    await bot.handle("/상품등록 A상품 10", room="A방", **admin)
    store.add_shop_item("B방", "B상품", 10, "iris:shop", "등록자")

    allowed = await bot.handle("/상품삭제 1", room="A방", **admin)
    denied = await bot.handle("/상품삭제 1", room="B방", **admin)

    assert "뺐어요" in allowed.reply
    assert denied.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."
    assert [item[1] for item in store.list_shop_items("B방")] == ["B상품"]


@pytest.mark.anyio
async def test_daily_rank_points_awarded_once(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    today = "2026-08-01"
    # 1~6위를 만든다(6위는 5위와 같은 20P를 받아야 한다).
    for index, (key, name) in enumerate(
        [("a", "일등"), ("b", "이등"), ("c", "삼등"), ("d", "사등"), ("e", "오등"), ("f", "육등")]
    ):
        for _ in range(10 - index):
            store.record_chat_message("방", f"iris:{key}", name, today)

    notice = bot.award_daily_rank_points("방", today)
    assert "일등 · 10회 → +100P" in notice
    assert "+80P" in notice and "+60P" in notice and "+40P" in notice
    assert store.get_points("방", "iris:a") == 100
    assert store.get_points("방", "iris:e") == 20
    assert store.get_points("방", "iris:f") == 20  # 5위부터는 동일

    # 같은 날 다시 돌려도 중복 지급하지 않는다.
    assert bot.award_daily_rank_points("방", today) == ""
    assert store.get_points("방", "iris:a") == 100


def test_parse_praise_commands() -> None:
    assert parse_command("/칭찬추가 홍길동 레이드 도움") == ("praise_add", "홍길동 레이드 도움")
    assert parse_command("/칭찬") == ("praise_list", "")
    assert parse_command("/칭찬삭제 홍길동") == ("praise_remove", "홍길동")


@pytest.mark.anyio
async def test_praise_is_separate_from_warning(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))
    store.record_chat_message("방", "iris:t", "착한이", "2026-08-01")
    owner = {"room": "방", "sender": "오너", "user_key": "iris:owner"}

    added = await bot.handle("/칭찬추가 착한이 레이드 많이 열어줌", **owner)
    assert "👏 칭찬 등록" in added.reply and "1회" in added.reply

    listed = await bot.handle("/칭찬", **owner)
    assert "착한이" in listed.reply and "레이드 많이 열어줌" in listed.reply

    # 경고와 칭찬은 서로 섞이지 않는다.
    assert "착한이" not in (await bot.handle("/경고", **owner)).reply
    await bot.handle("/경고추가 착한이 지각", **owner)
    warn_list = await bot.handle("/경고", **owner)
    assert "지각" in warn_list.reply and "레이드 많이 열어줌" not in warn_list.reply
    praise_list = await bot.handle("/칭찬", **owner)
    assert "지각" not in praise_list.reply

    # 내용을 지정하면 그 1건만, 닉네임만 주면 칭찬 전부 삭제(경고는 남는다).
    await bot.handle("/칭찬추가 착한이 친절함", **owner)
    one = await bot.handle("/칭찬삭제 착한이 친절함", **owner)
    assert "1건을 지웠어요" in one.reply and "남은 칭찬 1회" in one.reply
    every = await bot.handle("/칭찬삭제 착한이", **owner)
    assert "1건을 모두 지웠어요" in every.reply
    assert store.warning_reasons("방", "iris:t", kind="praise") == []
    assert store.warning_reasons("방", "iris:t", kind="warn") == ["지각"]

    # 칭찬은 권한 없이 누구나 쓸 수 있다(경고와 다른 점).
    passerby = {"room": "방", "sender": "행인", "user_key": "iris:x"}
    open_add = await bot.handle("/칭찬추가 착한이 도움 많이 줌", **passerby)
    assert "👏 칭찬 등록" in open_add.reply
    assert "착한이" in (await bot.handle("/칭찬", **passerby)).reply
    # 경고는 여전히 권한자만.
    assert "경고 권한" in (await bot.handle("/경고추가 착한이 사유", **passerby)).reply
    assert "경고 권한" in (await bot.handle("/경고", **passerby)).reply


@pytest.mark.anyio
async def test_warn_permission_grant_flow(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))
    # 대상 모더레이터와 경고 대상이 종합방에서 채팅한 적 있다.
    store.record_chat_message("종합방", "iris:mod", "모더", "2026-07-31")
    store.record_chat_message("종합방", "iris:target", "말썽꾼", "2026-07-31")

    # 권한 없는 모더는 아직 경고 못 씀.
    before = await bot.handle("/경고추가 말썽꾼 도배", room="종합방", sender="모더", user_key="iris:mod")
    assert "경고 권한" in before.reply

    # 오너가 개인톡에서 대상방 지정 후 권한 부여.
    await bot.handle("/대상방설정 종합방", room="개인톡:o", sender="오너", user_key="iris:owner")
    granted = await bot.handle("/경고권한부여 모더", room="개인톡:o", sender="오너", user_key="iris:owner")
    assert "경고 권한 부여" in granted.reply

    # 이제 모더가 종합방에서 경고를 쓸 수 있다.
    after = await bot.handle("/경고추가 말썽꾼 도배", room="종합방", sender="모더", user_key="iris:mod")
    assert "경고 등록" in after.reply

    # 오너가 권한을 해제하면 다시 막힌다.
    await bot.handle("/경고권한해제 모더", room="개인톡:o", sender="오너", user_key="iris:owner")
    blocked = await bot.handle("/경고 ", room="종합방", sender="모더", user_key="iris:mod")
    assert "경고 권한" in blocked.reply


@pytest.mark.anyio
async def test_warning_add_needs_known_nickname(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:boss"))

    # 채팅 기록이 없는 닉네임은 등록 불가(ID 매핑이 없어서).
    unknown = await bot.handle("/경고추가 없는사람 사유", room="방", sender="관리자", user_key="iris:boss")
    assert "찾지 못했" in unknown.reply

    # 공백이 있는 닉네임도 가장 긴 것부터 맞춰 처리한다.
    store.record_chat_message("방", "iris:7", "링딩 임시", "2026-07-31")
    ok = await bot.handle("/경고추가 링딩 임시 도배심함", room="방", sender="관리자", user_key="iris:boss")
    assert "경고 등록" in ok.reply
    listing = await bot.handle("/경고", room="방", sender="관리자", user_key="iris:boss")
    assert "링딩 임시" in listing.reply and "도배심함" in listing.reply


@pytest.mark.anyio
async def test_record_add_supports_space_nickname_with_reason_separator(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))
    store.record_chat_message("방", "iris:space", "아 아", "2026-08-11")
    owner = {"room": "방", "sender": "오너", "user_key": "iris:owner"}

    warned = await bot.handle("/경고추가 아 아 사유 들낙", **owner)
    praised = await bot.handle("/칭찬추가 아 아 사유 레이드 도움", **owner)

    assert "경고 등록: 아 아" in warned.reply
    assert "사유: 들낙" in warned.reply
    assert "칭찬 등록: 아 아" in praised.reply
    assert "내용: 레이드 도움" in praised.reply
    assert store.warning_reasons("방", "iris:space", kind="warn") == ["들낙"]
    assert store.warning_reasons("방", "iris:space", kind="praise") == ["레이드 도움"]


@pytest.mark.anyio
async def test_warn_remove_single_reason_or_all(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))
    store.record_chat_message("방", "iris:t", "말썽꾼", "2026-07-31")
    owner = {"room": "방", "sender": "오너", "user_key": "iris:owner"}

    await bot.handle("/경고추가 말썽꾼 도배", **owner)
    await bot.handle("/경고추가 말썽꾼 욕설", **owner)
    await bot.handle("/경고추가 말썽꾼 광고", **owner)

    # 사유를 주면 그 1건만 지운다.
    one = await bot.handle("/경고삭제 말썽꾼 욕설", **owner)
    assert "1건을 지웠어요" in one.reply and "남은 경고 2회" in one.reply
    listed = await bot.handle("/경고", **owner)
    assert "욕설" not in listed.reply
    assert "도배" in listed.reply and "광고" in listed.reply

    # 없는 사유를 주면 지우지 않고 남은 사유를 알려준다.
    missing = await bot.handle("/경고삭제 말썽꾼 없는사유", **owner)
    assert "경고가 없어요" in missing.reply and "도배" in missing.reply
    assert len(store.warning_reasons("방", "iris:t")) == 2

    # 닉네임만 주면 전부 지운다.
    every = await bot.handle("/경고삭제 말썽꾼", **owner)
    assert "2건을 모두 지웠어요" in every.reply
    assert store.warning_reasons("방", "iris:t") == []


@pytest.mark.anyio
async def test_warn_permission_grant_multiple_at_once(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.add_owner(ChatUser(room="개인톡:o", sender="오너", user_key="iris:owner"))
    for key, nick in [("iris:a", "에이"), ("iris:b", "비"), ("iris:c", "링딩 임시")]:
        store.record_chat_message("종합방", key, nick, "2026-07-31")
    await bot.handle("/대상방설정 종합방", room="개인톡:o", sender="오너", user_key="iris:owner")

    # 쉼표로 여러 명 한 번에. 공백 있는 닉네임과 못 찾는 닉네임도 섞어서.
    reply = await bot.handle(
        "/경고권한부여 에이, 비, 링딩 임시, 없는사람",
        room="개인톡:o",
        sender="오너",
        user_key="iris:owner",
    )
    assert "부여 (3명)" in reply.reply
    assert "링딩 임시" in reply.reply
    assert "못 찾음 (1명)" in reply.reply and "없는사람" in reply.reply

    # 셋 다 실제로 권한을 가졌는지 확인.
    for key in ("iris:a", "iris:b", "iris:c"):
        assert store.has_warn_permission("종합방", key)


@pytest.mark.anyio
async def test_leave_baselines_untracked_member(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store)
    store.set_join_alert_threshold("방", 2)

    # 채팅 한 번 없던 잠수 유저라도 스스로 나가면(퇴장 피드) 입장 1회로 잡힌다.
    bot.handle_member_leaves("방", [("ghost", "유령")])
    # 그래서 다시 들어오면 곧바로 2회차.
    warn = bot.handle_member_joins("방", [("ghost", "유령")])
    assert "입장 2회차" in warn


def test_parse_iris_feed_formats() -> None:
    from app.main import _parse_iris_feed

    join = {
        "type": "0",
        "message": '{"feedType":4,"members":[{"userId":123,"nickName":"링딩"}]}',
    }
    assert _parse_iris_feed(join) == (4, [("123", "링딩")])

    leave = {
        "type": "0",
        "message": '{"feedType":2,"member":{"userId":456,"nickName":"jace"}}',
    }
    assert _parse_iris_feed(leave) == (2, [("456", "jace")])

    # 일반 텍스트(type 1)나 이모티콘(type 20)은 피드가 아니다.
    assert _parse_iris_feed({"type": "1", "message": "안녕"}) is None
    assert _parse_iris_feed({"type": "20", "message": ""}) is None


def test_parse_league_ranking_commands() -> None:
    assert parse_command("/슈리") == ("pvp_great", "")
    assert parse_command("/하리") == ("pvp_ultra", "")
    assert parse_command("/마리") == ("pvp_master", "")


class _StubPvp:
    def __init__(self, text=None, fail=False) -> None:
        self.text = text
        self.fail = fail

    async def format_league(self, league_key):
        from app.pvp_rankings import PvpRankingUnavailableError

        if self.fail:
            raise PvpRankingUnavailableError("down")
        return f"{league_key}::{self.text}"


@pytest.mark.anyio
async def test_league_ranking_uses_live_pvp_data(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        pvp_client=_StubPvp(text="랭킹본문"),
    )
    reply = await bot.handle("/마리", room="방", sender="유저", user_key="iris:1")
    assert "master::랭킹본문" in reply.reply


@pytest.mark.anyio
async def test_league_ranking_falls_back_to_base_when_offline(tmp_path) -> None:
    from app.bot import BASE_ROOM

    store = AdminStore(tmp_path / "test.sqlite3")
    store.upsert_custom_command(BASE_ROOM, "슈리", "저장된 슈퍼리그 순위", "시스템")
    bot = PokemonGoBot(admin_store=store, pvp_client=_StubPvp(fail=True))

    reply = await bot.handle("/슈리", room="방", sender="유저", user_key="iris:1")
    assert reply.reply == "저장된 슈퍼리그 순위"


@pytest.mark.anyio
async def test_custom_commands_do_not_leak_between_rooms(tmp_path) -> None:
    from app.bot import BASE_ROOM

    store = AdminStore(tmp_path / "test.sqlite3")
    store.upsert_custom_command("A방", "공지", "A방 공지", "A방장")
    store.upsert_custom_command("B방", "공지", "B방 공지", "B방장")
    store.upsert_custom_command(BASE_ROOM, "세꿀", "시스템 내부 백업", "시스템")
    bot = PokemonGoBot(admin_store=store)

    assert (await bot.handle("/공지", room="A방", sender="유저", user_key="iris:1")).reply == "A방 공지"
    assert (await bot.handle("/공지", room="B방", sender="유저", user_key="iris:1")).reply == "B방 공지"

    missing = await bot.handle("/공지", room="C방", sender="유저", user_key="iris:1")
    assert missing.silent is True
    assert missing.reply == ""

    # 시스템 백업 공간에 있는 임의 명령어도 일반 방으로 새어 나오지 않는다.
    internal = await bot.handle("/세꿀", room="A방", sender="유저", user_key="iris:1")
    assert internal.silent is True
    assert internal.reply == ""


def test_admin_web_rename_room(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    test_bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "admin-secret")
    client = TestClient(main_module.app)
    auth = {"X-Bridge-Key": "admin-secret"}

    test_bot.admin_store.upsert_custom_command("옛방", "공지", "내용", "오너")

    denied = client.post(
        "/admin/rename-room", json={"old_room": "옛방", "new_room": "새방"}
    )
    assert denied.status_code == 403

    same = client.post(
        "/admin/rename-room",
        headers=auth,
        json={"old_room": "옛방", "new_room": "옛방"},
    )
    assert same.status_code == 400

    moved = client.post(
        "/admin/rename-room",
        headers=auth,
        json={"old_room": "옛방", "new_room": "새방"},
    )
    assert moved.status_code == 200
    assert moved.json()["custom_commands"] == 1
    assert test_bot.admin_store.get_custom_command("새방", "공지").response == "내용"


def test_room_password_gates_web_edits(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    test_bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "admin-secret")
    client = TestClient(main_module.app)
    auth = {"X-Bridge-Key": "admin-secret"}

    # 비밀번호가 없는 방은 기존처럼 자유롭게 저장된다.
    free = client.post(
        "/admin/command",
        headers=auth,
        json={"room": "자유방", "command": "공지", "response": "내용"},
    )
    assert free.status_code == 200

    # 비밀번호 설정 (4자 미만 거절, 정상 설정, 중복 설정 거절)
    short = client.post(
        "/admin/room-password",
        headers=auth,
        json={"room": "보호방", "password": "12", "recovery_word": "포켓몬"},
    )
    assert short.status_code == 400

    ok = client.post(
        "/admin/room-password",
        headers=auth,
        json={"room": "보호방", "password": "네자리비번", "recovery_word": "피카츄최고"},
    )
    assert ok.status_code == 200

    dup = client.post(
        "/admin/room-password",
        headers=auth,
        json={"room": "보호방", "password": "다른비번", "recovery_word": "다른단어"},
    )
    assert dup.status_code == 409

    # 비밀번호 없이/틀리게 저장하면 403
    blocked = client.post(
        "/admin/command",
        headers=auth,
        json={"room": "보호방", "command": "공지", "response": "내용"},
    )
    assert blocked.status_code == 403
    assert "방 비밀번호" in blocked.json()["detail"]

    wrong = client.post(
        "/admin/command",
        headers=auth,
        json={"room": "보호방", "command": "공지", "response": "내용", "room_password": "틀림"},
    )
    assert wrong.status_code == 403

    saved = client.post(
        "/admin/command",
        headers=auth,
        json={"room": "보호방", "command": "공지", "response": "내용", "room_password": "네자리비번"},
    )
    assert saved.status_code == 200

    # 삭제도 비밀번호가 필요하다.
    del_blocked = client.delete(
        "/admin/command",
        headers=auth,
        params={"room": "보호방", "command": "공지"},
    )
    assert del_blocked.status_code == 403

    # 복구 단어가 틀리면 변경 불가, 맞으면 변경된다.
    bad_change = client.post(
        "/admin/room-password/change",
        headers=auth,
        json={"room": "보호방", "recovery_word": "엉뚱단어", "new_password": "새비번1234"},
    )
    assert bad_change.status_code == 403

    changed = client.post(
        "/admin/room-password/change",
        headers=auth,
        json={"room": "보호방", "recovery_word": "피카츄최고", "new_password": "새비번1234"},
    )
    assert changed.status_code == 200

    del_ok = client.delete(
        "/admin/command",
        headers=auth,
        params={"room": "보호방", "command": "공지", "password": "새비번1234"},
    )
    assert del_ok.status_code == 200

    # 설정된 적 없는 방의 변경 시도는 404
    no_pw = client.post(
        "/admin/room-password/change",
        headers=auth,
        json={"room": "자유방", "recovery_word": "x", "new_password": "새비번1234"},
    )
    assert no_pw.status_code == 404


def test_iris_webhook_processes_message(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    test_bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "iris-secret")
    client = TestClient(main_module.app)

    def iris_payload(msg):
        return {
            "msg": msg,
            "room": "레이드방",
            "sender": "박화영",
            "json": {"user_id": "12345", "chat_id": "999", "message": msg},
        }

    # 잘못된 토큰은 거절된다.
    denied = client.post("/iris/wrong", json=iris_payload("/도감 피카츄"))
    assert denied.status_code == 403

    # 일반 채팅은 조용히 무시되지만 랭킹 집계에는 들어간다.
    chat = client.post("/iris/iris-secret", json=iris_payload("안녕하세요")).json()
    assert chat == {"reply": "", "silent": True, "chat_id": "999"}

    # 명령어는 정상 처리되고 chat_id가 실려 온다.
    reply = client.post("/iris/iris-secret", json=iris_payload("/도감 피카츄")).json()
    assert reply["silent"] is False
    assert reply["chat_id"] == "999"
    assert "피카츄" in reply["reply"]

    # user_id 기반 user_key로 오너 등록이 되고, 같은 user_id면 권한이 유지된다.
    client.post("/iris/iris-secret", json=iris_payload("/오너등록 test-setup-code"))
    saved = client.post(
        "/iris/iris-secret", json=iris_payload("/명령어등록 공지 오늘 레이드 8시")
    ).json()
    assert saved["reply"] == "/공지 명령어를 저장했습니다."

    record = test_bot.admin_store.list_admin_records("레이드방")
    assert ("박화영", "owner", "iris:12345") in record

    # 답장은 outbox에 쌓이고, 폰이 폴링하면 /reply 로 보낼 JSON 줄로 나온다.
    dex = client.post("/iris/iris-secret", json=iris_payload("/도감 피카츄")).json()
    assert dex["silent"] is False
    outbox = client.get("/iris/outbox/iris-secret")
    assert outbox.status_code == 200
    lines = [l for l in outbox.text.split("\n") if l]
    # 마지막 줄이 방금 도감 답장 (room=chat_id "999")
    last = json.loads(lines[-1])
    assert last["type"] == "text"
    assert last["room"] == "999"
    assert "피카츄" in last["data"]
    # 가져간 뒤에는 비워진다.
    assert client.get("/iris/outbox/iris-secret").text.strip() == ""
    # 잘못된 토큰은 거절.
    assert client.get("/iris/outbox/wrong").status_code == 403

    # 1:1 개인톡방: room·sender 가 null 로 와도 처리된다 (chat_id로 방 식별).
    dm = client.post(
        "/iris/iris-secret",
        json={
            "msg": "/오너등록 test-setup-code",
            "room": None,
            "sender": None,
            "json": {"user_id": "77", "chat_id": "555"},
        },
    ).json()
    assert dm["silent"] is False
    assert dm["chat_id"] == "555"
    # 개인톡방(room·sender null)은 chat_id로 처리되지만, owner는 봇 전체에
    # 단 한 명이라 이미 owner가 있으면 두 번째 등록은 차단된다.
    assert dm["reply"] == "이미 이 봇에 owner가 등록되어 있습니다."
    assert test_bot.admin_store.list_admin_records("개인톡:555") == []


def test_command_stays_open_without_bridge_key(monkeypatch) -> None:
    monkeypatch.delenv("BRIDGE_KEY", raising=False)
    client = TestClient(app)

    response = client.get("/command", params={"text": "!x"})
    assert response.status_code == 200


def test_kakao_skill_returns_simple_text_response() -> None:
    client = TestClient(app)

    response = client.post(
        "/kakao/skill",
        json={
            "userRequest": {
                "utterance": "/도움말",
                "user": {"id": "channel-user-1"},
            },
            "bot": {"id": "pogo-channel", "name": "KakaoPoGo"},
            "action": {"params": {}},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "2.0"
    outputs = body["template"]["outputs"]
    assert 1 <= len(outputs) <= 3
    assert "【 포켓몬GO 정보 명령어 】" in outputs[0]["simpleText"]["text"]
    assert "/도감 포켓몬이름" in outputs[0]["simpleText"]["text"]
    assert "/포켓몬고이벤트" in outputs[0]["simpleText"]["text"]
    assert "/날씨" in outputs[0]["simpleText"]["text"]
    assert "/관리자요청" not in outputs[0]["simpleText"]["text"]
    assert "/명령어등록" not in outputs[0]["simpleText"]["text"]
    assert "quickReplies" not in body["template"]


def test_kakao_skill_uses_action_params_when_utterance_is_missing() -> None:
    client = TestClient(app)

    response = client.post(
        "/kakao/skill",
        json={
            "userRequest": {"user": {"id": "channel-user-1"}},
            "bot": {"id": "pogo-channel"},
            "action": {"params": {"command": "/도움말"}},
        },
    )

    assert response.status_code == 200
    text = response.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "/스킬 포켓몬이름" in text
    assert "가르친사람" not in text


def test_kakao_skill_test_payload_prefers_command_param() -> None:
    client = TestClient(app)

    response = client.post(
        "/kakao/skill",
        json={
            "userRequest": {
                "utterance": "발화 내용",
                "user": {"id": "channel-user-1"},
            },
            "bot": {"id": "pogo-channel"},
            "action": {"params": {"command": "/도움말"}, "detailParams": {}},
        },
    )

    assert response.status_code == 200
    text = response.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "/도감 포켓몬이름" in text
    assert "/권한확인" not in text


def test_kakao_skill_reads_detail_param_origin() -> None:
    client = TestClient(app)

    response = client.post(
        "/kakao/skill",
        json={
            "userRequest": {
                "utterance": "발화 내용",
                "user": {"id": "channel-user-1"},
            },
            "bot": {"id": "pogo-channel"},
            "action": {
                "params": {},
                "detailParams": {"command": {"origin": "/도움말", "value": "/도움말"}},
            },
        },
    )

    assert response.status_code == 200
    text = response.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "/스킬 포켓몬이름" in text


def test_kakao_skill_blocks_openchat_admin_commands() -> None:
    client = TestClient(app)

    response = client.post(
        "/kakao/skill",
        json={
            "userRequest": {
                "utterance": "/권한확인",
                "user": {"id": "channel-user-1"},
            },
            "bot": {"id": "pogo-channel"},
            "action": {"params": {}},
        },
    )

    assert response.status_code == 200
    text = response.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "포켓몬GO 정보 조회만 지원합니다" in text
    assert "권한 확인" not in text


def test_kakao_skill_blocks_openchat_custom_commands() -> None:
    client = TestClient(app)

    response = client.post(
        "/kakao/skill",
        json={
            "userRequest": {
                "utterance": "/공지",
                "user": {"id": "channel-user-1"},
            },
            "bot": {"id": "pogo-channel"},
            "action": {"params": {}},
        },
    )

    assert response.status_code == 200
    text = response.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "포켓몬GO 정보 조회만 지원합니다" in text


def test_kakao_skill_guides_non_slash_messages() -> None:
    client = TestClient(app)

    response = client.post(
        "/kakao/skill",
        json={
            "userRequest": {"utterance": "안녕하세요", "user": {"id": "channel-user-1"}},
            "bot": {"id": "pogo-channel"},
            "action": {"params": {}},
        },
    )

    assert response.status_code == 200
    text = response.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert text == "명령어는 /로 시작해 주세요.\n예: /도감 피카츄"


def test_kakao_text_split_keeps_response_inside_kakao_limits() -> None:
    chunks = _split_kakao_text("가" * 3500)

    assert len(chunks) == 3
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert "일부만 표시했습니다" in chunks[-1]


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
async def test_event_command_uses_event_client(tmp_path) -> None:
    bot = PokemonGoBot(
        event_client=FakeEventClient(),
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    reply = await bot.handle("/포켓몬고이벤트", room="레이드방", sender="일반")

    assert reply.reply == "event schedule for 7 days"


@pytest.mark.anyio
async def test_event_command_reports_data_unavailable(tmp_path) -> None:
    bot = PokemonGoBot(
        event_client=FailingEventClient(),
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    reply = await bot.handle("/이벤트", room="레이드방", sender="일반")

    assert reply.reply == "포켓몬GO 이벤트 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."


@pytest.mark.anyio
async def test_weather_command_uses_weather_client(tmp_path) -> None:
    bot = PokemonGoBot(
        weather_client=FakeWeatherClient(),
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    reply = await bot.handle("/날씨", room="레이드방", sender="일반")

    assert reply.reply == "today weather"


@pytest.mark.anyio
async def test_weather_command_reports_data_unavailable(tmp_path) -> None:
    bot = PokemonGoBot(
        weather_client=FailingWeatherClient(),
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    reply = await bot.handle("/전국날씨", room="레이드방", sender="일반")

    assert reply.reply == "날씨 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."


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


def test_chat_ranking_daily_and_total(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    test_bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "chat-secret")
    client = TestClient(main_module.app)
    auth = {"X-Bridge-Key": "chat-secret"}

    def send(text, sender, key):
        return client.get(
            "/command",
            headers=auth,
            params={"text": text, "room": "수다방", "sender": sender, "user_key": key},
        )

    # 일반 채팅은 조용히 무시되지만 집계에는 포함된다.
    for _ in range(3):
        assert send("안녕하세요~", "수다왕", "hash:talker").json()["silent"] is True
    send("점심 뭐 먹지", "조용한사람", "hash:quiet")
    # 봇에게 거는 명령어는 대화가 아니라 집계에서 빠진다.
    send("/도움말", "수다왕", "hash:talker")
    send("/등록안된명령", "수다왕", "hash:talker")

    daily = send("/일일랭킹", "수다왕", "hash:talker").json()["reply"]
    lines = daily.split("\\n") if "\\n" in daily else daily.split("\n")
    assert lines[0] == "💬 오늘의 채팅 랭킹 TOP 10"
    assert "🥇 수다왕 - 3회" in daily  # 명령어 3건은 빠지고 실제 채팅만
    assert "🥈 조용한사람 - 1회" in daily

    total = send("/랭킹", "조용한사람", "hash:quiet").json()["reply"]
    assert total.startswith("💬 누적 채팅 랭킹 TOP 10")
    assert "수다왕" in total

    # 명령어만 오간 방은 집계가 비어 있다.
    empty = client.get(
        "/command",
        headers=auth,
        params={"text": "/일일랭킹", "room": "새방", "sender": "아무개", "user_key": "hash:new"},
    ).json()["reply"]
    assert "아무개" not in empty


@pytest.mark.anyio
async def test_raffle_draws_from_active_members_only(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    from datetime import date, timedelta

    today = date.today().isoformat()

    # 오늘 활동이 없는 방은 추첨 불가.
    empty = await bot.handle("/추첨", room="빈방", sender="일반")
    assert "오늘 추첨할 대상이 없어요" in empty.reply

    # 오늘 1회 이상 활동한 사람만 풀에 들어간다.
    for _ in range(5):
        bot.record_chat("추첨방", "활발이", "iris:1")
    bot.record_chat("추첨방", "가끔이", "iris:2")

    pool = dict(bot.admin_store.raffle_pool("추첨방", today))
    assert pool == {"활발이": 5, "가끔이": 1}  # 오늘 활동량

    # 어제 활동뿐인 사람은 오늘 추첨에서 빠진다.
    bot.admin_store.record_chat_message(
        "추첨방", "iris:3", "어제만", (date.today() - timedelta(days=1)).isoformat()
    )
    assert "어제만" not in dict(bot.admin_store.raffle_pool("추첨방", today))

    result = await bot.handle("/추첨", room="추첨방", sender="일반")
    assert "🎉 추첨 결과" in result.reply
    assert ("활발이" in result.reply) or ("가끔이" in result.reply)
    # 활동량 숫자는 노출하지 않는다.
    assert "5회" not in result.reply and " - " not in result.reply
    assert "오늘 활동자 2명" in result.reply


@pytest.mark.anyio
async def test_raffle_temporarily_ignores_countdown_fragments(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    await bot.handle("/추첨", room="추첨방", sender="진행자", user_key="iris:host")
    for message in ("5", "4", "3", "2", "1"):
        assert bot.record_chat("추첨방", "진행자", "iris:host", message) == ""

    assert store.list_moderation_incidents("추첨방") == []


@pytest.mark.anyio
async def test_raffle_excludes_registered_recipients_and_resets_when_exhausted(
    tmp_path, monkeypatch
) -> None:
    from datetime import date, timedelta

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")
    today = date.today()
    today_text = today.isoformat()

    for user_key, nickname in (
        ("iris:1", "첫째"),
        ("iris:2", "둘째"),
        ("iris:3", "셋째"),
    ):
        bot.record_chat("추첨방", nickname, user_key)

    store.record_raffle_winner("추첨방", "iris:1", "옛첫째닉", today_text)
    store.record_raffle_winner(
        "추첨방", "iris:2", "둘째", (today - timedelta(days=3)).isoformat()
    )
    # 다른 방 당첨 기록은 이 방 추첨에 영향을 주지 않는다.
    store.record_raffle_winner("다른방", "iris:3", "셋째", today_text)

    cutoff = (today - timedelta(days=7)).isoformat()
    eligible = store.raffle_candidates(
        "추첨방", today_text, excluded_after=cutoff
    )
    assert eligible == [("iris:3", "셋째", 1)]

    monkeypatch.setattr(
        "app.bot.random.choices",
        lambda population, weights, k: [population[0]],
    )
    first = await bot.handle("/추첨", room="추첨방", sender="진행자")
    assert "당첨 : 셋째 님" in first.reply
    assert "추첨 대상 1명" in first.reply
    assert "전체 활동자로 다시" not in first.reply
    assert "관리 사이트에서 수령자로 등록" in first.reply
    # 추첨만으로는 제외 기록이 생기지 않는다. 실제 상품 수령을 등록해야 한다.
    assert store.raffle_winner_history("추첨방", limit=1)[0][0] == "iris:2"
    store.register_raffle_recipient("추첨방", "iris:3", "셋째", today_text)

    # 세 활동자가 모두 최근 수령 등록자가 됐으므로 제한을 풀고 전체에서 추첨한다.
    reset = await bot.handle("/추첨", room="추첨방", sender="진행자")
    assert "전체 활동자로 다시 추첨했습니다" in reset.reply
    assert "오늘 활동자 3명 / 추첨 대상 3명" in reset.reply


def test_raffle_cooldown_ends_after_seven_days(tmp_path) -> None:
    from datetime import date, timedelta

    store = AdminStore(tmp_path / "test.sqlite3")
    today = date.today()
    today_text = today.isoformat()
    cutoff = (today - timedelta(days=7)).isoformat()
    store.record_chat_message("방", "iris:old", "지난당첨자", today_text)
    store.record_raffle_winner("방", "iris:old", "지난당첨자", cutoff)

    # 정확히 7일 전 수령 등록자는 오늘부터 다시 후보가 된다.
    assert store.raffle_candidates("방", today_text, excluded_after=cutoff) == [
        ("iris:old", "지난당첨자", 1)
    ]


def test_iris_skips_bot_own_messages(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    test_bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "iris-secret")
    client = TestClient(main_module.app)

    # 봇 자기 메시지(isMine=true)는 집계에서 제외 → 추첨 풀에 안 들어감.
    client.post("/iris/iris-secret", json={
        "msg": "봇이 보낸 답장", "room": "방", "sender": "봇",
        "json": {"user_id": "444", "chat_id": "1", "v": json.dumps({"isMine": True})},
    })
    # 일반 유저 메시지는 집계됨.
    client.post("/iris/iris-secret", json={
        "msg": "안녕", "room": "방", "sender": "유저", "isMine": False,
        "json": {"user_id": "77", "chat_id": "1", "v": json.dumps({"isMine": False})},
    })
    from datetime import date

    pool = dict(test_bot.admin_store.raffle_pool("방", date.today().isoformat()))
    assert "유저" in pool
    assert "봇" not in pool  # 봇 제외됨


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

    other_room = await bot.handle("/출석랭킹", room="다른방", sender="지우")
    assert "아직 출석한 사람이 없어요" in other_room.reply


@pytest.mark.anyio
async def test_point_ranking_shows_room_top_twenty(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    empty = await bot.handle("/포인트순위", room="레이드방", sender="지우")
    assert "포인트를 보유한 사람이 없어요" in empty.reply

    for index in range(22):
        store.add_points(
            "레이드방",
            f"hash:user{index:02d}",
            f"유저{index:02d}",
            (index + 1) * 10,
        )
    store.add_points("다른방", "hash:outsider", "다른방1등", 9999)

    ranking = await bot.handle("/포인트순위", room="레이드방", sender="지우")
    lines = ranking.reply.split("\n")

    assert lines[0] == "💰 포인트 순위 TOP 20"
    assert len(lines) == 22  # 제목과 구분선 + 20명
    assert lines[2] == "🥇 유저21 - 220P"
    assert lines[3] == "🥈 유저20 - 210P"
    assert lines[4] == "🥉 유저19 - 200P"
    assert lines[5] == "4. 유저18 - 190P"
    assert "유저01" not in ranking.reply
    assert "유저00" not in ranking.reply
    assert "다른방1등" not in ranking.reply


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
    assert owner.reply == "이 봇의 owner로 등록되었습니다."

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
    assert "/들낙 [닉네임]" in owner_listed.reply

    owner_help = await bot.handle("/도움말", room="레이드방", sender="오너")
    assert "/공지" in owner_help.reply
    assert "/도감 포켓몬이름" in owner_help.reply
    assert "/부스트 [지역]" in owner_help.reply
    assert "/포인트" in owner_help.reply
    assert "/포인트순위" in owner_help.reply
    assert "/상품" in owner_help.reply
    assert "/칭찬추가 닉네임 사유 내용" in owner_help.reply
    assert "/들낙" not in owner_help.reply
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
    assert missing.silent is True
    assert missing.reply == ""


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
    assert blocked.reply == "이미 이 봇에 owner가 등록되어 있습니다."
    assert admins == [("이전오너", "owner", "hash:previous-owner")]


@pytest.mark.anyio
async def test_owner_is_global_single_owner_across_rooms(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    first = await bot.handle(
        "/오너등록 test-setup-code",
        room="개인톡:dm",
        sender="박정우",
        user_key="iris:owner",
    )
    assert first.reply == "이 봇의 owner로 등록되었습니다."

    # 다른 방(자기 개인톡 등)에서 코드를 알아도 두 번째 owner는 못 만든다.
    intruder = await bot.handle(
        "/오너등록 test-setup-code",
        room="개인톡:다른사람",
        sender="침입자",
        user_key="iris:intruder",
    )
    assert intruder.reply == "이미 이 봇에 owner가 등록되어 있습니다."
    assert store.has_any_owner() is True
    assert store.is_owner(ChatUser(room="아무방", sender="침입자", user_key="iris:intruder")) is False
    # 진짜 owner는 어느 방에서든 owner로 인식된다.
    assert store.is_owner(ChatUser(room="아무방", sender="박정우", user_key="iris:owner")) is True


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
    assert blocked.reply == "이미 이 봇에 owner가 등록되어 있습니다."
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
async def test_admin_display_name_auto_updates_on_activity(tmp_path) -> None:
    from app.admin_store import ChatUser

    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    # 관리자를 옛 닉네임으로 등록.
    store.add_admin(ChatUser(room="레이드방", sender="옛닉네임", user_key="iris:42"))
    assert ("옛닉네임", "admin", "iris:42") in store.list_admin_records("레이드방")

    # 그 사람이 새 닉네임으로 채팅하면(record_chat) 관리자목록 표시도 자동 갱신된다.
    bot.record_chat("레이드방", "새닉네임", "iris:42")
    assert ("새닉네임", "admin", "iris:42") in store.list_admin_records("레이드방")
    assert not any(n == "옛닉네임" for n, _, _ in store.list_admin_records("레이드방"))


@pytest.mark.anyio
async def test_owner_adds_and_removes_admin_by_nickname(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    # 개인방에서 오너 등록 후 공개방을 대상방으로 잡는다.
    await bot.handle(
        "/오너등록 test-setup-code",
        room="개인방",
        sender="오너",
        user_key="hash:owner",
    )
    await bot.handle("/대상방설정 공개방", room="개인방", sender="오너", user_key="hash:owner")

    added = await bot.handle(
        "/관리자추가 박화영",
        room="개인방",
        sender="오너",
        user_key="hash:owner",
    )
    assert "박화영 님을 admin으로 등록했습니다." in added.reply
    assert ("박화영", "admin", "sender:박화영") in store.list_admin_records("공개방")

    duplicate = await bot.handle(
        "/관리자추가 박화영",
        room="개인방",
        sender="오너",
        user_key="hash:owner",
    )
    assert duplicate.reply == "박화영 님은 이미 admin입니다."

    # 박화영이 공개방에서 관리자 명령을 쓰면 hash 키로 자동 승격된다.
    saved = await bot.handle(
        "/명령어등록 공지 오늘 레이드 8시",
        room="공개방",
        sender="박화영",
        user_key="hash:hwayoung",
    )
    assert saved.reply == "/공지 명령어를 저장했습니다."
    assert ("박화영", "admin", "hash:hwayoung") in store.list_admin_records("공개방")

    # 관리자 관리 명령은 admin에게는 열리지 않는다 (오너 전용).
    denied_list = await bot.handle(
        "/관리자명단",
        room="공개방",
        sender="박화영",
        user_key="hash:hwayoung",
    )
    assert denied_list.reply == "이 명령어는 owner만 사용할 수 있습니다."

    denied_add = await bot.handle(
        "/관리자추가 다른사람",
        room="공개방",
        sender="박화영",
        user_key="hash:hwayoung",
    )
    assert denied_add.reply == "이 명령어는 owner만 사용할 수 있습니다."

    # 오너는 /관리자명단 별칭으로도 목록을 볼 수 있다.
    listed = await bot.handle(
        "/관리자명단",
        room="개인방",
        sender="오너",
        user_key="hash:owner",
    )
    assert "박화영: admin" in listed.reply

    removed = await bot.handle(
        "/관리자삭제 박화영",
        room="개인방",
        sender="오너",
        user_key="hash:owner",
    )
    assert removed.reply == "박화영 님의 admin 권한을 삭제했습니다."
    assert store.list_admin_records("공개방") == []

    # owner 레코드가 있는 방(개인방 자신)에서는 닉네임으로도 owner를 못 지운다.
    solo_bot_user_room = "개인방"
    await bot.handle("/대상방설정 개인방", room=solo_bot_user_room, sender="오너", user_key="hash:owner")
    blocked = await bot.handle(
        "/관리자삭제 오너",
        room=solo_bot_user_room,
        sender="오너",
        user_key="hash:owner",
    )
    assert blocked.reply == "owner는 관리자삭제로 삭제할 수 없습니다."


@pytest.mark.anyio
async def test_long_custom_reply_is_folded_and_fold_test_pads(tmp_path) -> None:
    from app.bot import FOLD_PADDING

    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="오너")

    short_body = "짧은 공지입니다."
    await bot.handle(f"/명령어등록 공지 {short_body}", room="레이드방", sender="오너")
    short = await bot.handle("/공지", room="레이드방", sender="일반")
    assert short.reply == short_body  # 짧은 응답은 그대로

    # 긴 응답은 첫 줄 뒤에 접힘 유도 패딩이 붙는다.
    long_body = "💜600명 이벤트\n" + "\n".join(f"{i}번째 줄" for i in range(100))
    bot.admin_store.upsert_custom_command("레이드방", "이벤", long_body, "오너")
    folded = await bot.handle("/이벤", room="레이드방", sender="일반")
    assert folded.reply.startswith("💜600명 이벤트" + FOLD_PADDING[:10])
    assert folded.reply.endswith("99번째 줄")
    assert folded.reply.replace(FOLD_PADDING, "") == long_body

    # 접기 실험용 숨은 명령: 패딩 수를 조절할 수 있다.
    default_test = await bot.handle("/접기테스트", room="레이드방", sender="일반")
    assert default_test.reply.startswith("[접기테스트] 패딩 500자")
    assert default_test.reply.count("​") == 500
    assert default_test.reply.endswith("40번째 줄입니다.")

    custom_count = await bot.handle("/접기테스트 1200", room="레이드방", sender="일반")
    assert "패딩 1200자" in custom_count.reply
    assert custom_count.reply.count("​") == 1200


@pytest.mark.anyio
async def test_room_names_are_normalized_across_entrances(tmp_path) -> None:
    from app.bot import normalize_room

    # 이모지 스타일 지정자(U+FE0F)와 폭 없는 공백이 지워지고 공백이 정리된다.
    assert normalize_room("✨️포켓몬고  레이드 ") == "✨포켓몬고 레이드"
    assert normalize_room("✨포켓몬고 레이드") == "✨포켓몬고 레이드"

    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    # 폰이 보내는 깨끗한 이름으로 오너 등록·명령어 등록
    await bot.handle("/오너등록 test-setup-code", room="✨레이드방", sender="오너")
    await bot.handle("/명령어등록 공지 정규화 테스트", room="✨레이드방", sender="오너")

    # 손으로 타이핑한 U+FE0F 붙은 이름으로 대상방을 설정해도 같은 방을 가리킨다.
    await bot.handle(
        "/대상방설정 ✨️레이드방", room="개인방", sender="오너", user_key="sender:오너"
    )
    shown = await bot.handle("/대상방확인", room="개인방", sender="오너", user_key="sender:오너")
    assert shown.reply == "현재 대상방: ✨레이드방"

    # 유령 이름의 방에서 온 메시지도 진짜 방으로 정규화된다.
    reply = await bot.handle("/공지", room="✨️레이드방 ", sender="일반")
    assert reply.reply == "정규화 테스트"


@pytest.mark.anyio
async def test_raid_session_flow_with_host(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="회장")

    # 모집 전에는 참가가 거절된다.
    early = await bot.handle(
        "/참가 DongDoro 오리진디아루가 놋", room="레이드방", sender="일반"
    )
    assert "모집을 찾지 못했어요" in early.reply

    # 친구코드가 없거나 숫자 12자리가 아니면 모집이 열리지 않는다.
    no_code = await bot.handle("/레이드모집 오리진디아루가 놋", room="레이드방", sender="일반")
    assert "형식은 이렇게" in no_code.reply
    bad_code = await bot.handle(
        "/레이드모집 오리진디아루가 놋 12345", room="레이드방", sender="일반"
    )
    assert "친구코드는 숫자 12자리" in bad_code.reply

    # 모집은 관리자가 아니어도 누구나 열 수 있다. 코드는 하이픈도 허용.
    opened = await bot.handle(
        "/레이드모집 오리진 디아루가 놋 1234-5678-9012",
        room="레이드방",
        sender="일반유저",
        user_key="hash:host-not",
    )
    assert opened.reply.startswith("🔥 레이드 모집 오픈!")
    assert "🎯 포켓몬 : 오리진 디아루가" in opened.reply
    assert "👑 모집자 : 놋" in opened.reply
    assert "/참가 게임닉네임 오리진 디아루가 놋" in opened.reply
    assert "친구코드 : 123456789012" in opened.reply

    bad = await bot.handle("/참가 닉네임만", room="레이드방", sender="일반")
    assert "형식은 이렇게" in bad.reply

    # 모집 중인 포켓몬 이름과 다르면(오리진 != 오리진디아루가) 등록되지 않는다.
    wrong = await bot.handle("/참가 DongDoro 오리진 놋", room="레이드방", sender="일반")
    assert "모집을 찾지 못했어요" in wrong.reply
    # 모집자가 다르면 역시 등록되지 않는다.
    wrong_host = await bot.handle(
        "/참가 DongDoro 오리진디아루가 회장", room="레이드방", sender="일반"
    )
    assert "모집을 찾지 못했어요" in wrong_host.reply

    first = await bot.handle(
        "/참가 DongDoro 오리진 디아루가 놋", room="레이드방", sender="일반"
    )
    expected_first = chr(10).join(
        [
            "✅ 신청 완료!",
            "🎯 오리진 디아루가 (모집: 놋)",
            "🙋 DongDoro 님 · 현재 1명",
            "🤝 친추 필수 → 123456789012",
        ]
    )
    assert first.reply == expected_first

    duplicate = await bot.handle(
        "/참가 dongdoro 오리진디아루가 놋", room="레이드방", sender="일반"
    )
    assert "이미" in duplicate.reply  # 대소문자/띄어쓰기 달라도 같은 사람

    for index in range(11):
        await bot.handle(
            f"/참가 user{index:02d} 오리진디아루가 놋", room="레이드방", sender="일반"
        )

    roster = await bot.handle("/현황 오리진디아루가 놋", room="레이드방", sender="회장")
    lines = roster.reply.split(chr(10))
    assert lines[0] == "📋 오리진 디아루가 레이드 명단"
    assert lines[1] == "👑 모집자 놋 · 총 12명"
    assert lines[3].startswith("1팟(10명): DongDoro, user00")
    assert lines[4].startswith("2팟(2명): user09, user10")

    # 정렬: 숫자 먼저 -> 영문(aAbBcC 순)
    await bot.handle("/레이드모집 잠만보 놋 123456789012", room="레이드방", sender="놋")
    await bot.handle("/참가 zeta 잠만보 놋", room="레이드방", sender="일반")
    await bot.handle("/참가 Abc 잠만보 놋", room="레이드방", sender="일반")
    await bot.handle("/참가 abcMember 잠만보 놋", room="레이드방", sender="일반")
    await bot.handle("/참가 7lucky 잠만보 놋", room="레이드방", sender="일반")
    order = await bot.handle("/현황 잠만보 놋", room="레이드방", sender="회장")
    # 7lucky(숫자시작) -> abcMember(소문자 a) -> Abc(대문자 A) -> zeta
    assert "1팟(4명): 7lucky, abcMember, Abc, zeta" in order.reply

    # 같은 포켓몬이라도 모집자가 다르면 별도 명단이다.
    await bot.handle(
        "/레이드모집 오리진디아루가 부방장 111122223333", room="레이드방", sender="부방장"
    )
    await bot.handle("/참가 solo 오리진디아루가 부방장", room="레이드방", sender="일반")
    summary = await bot.handle("/현황", room="레이드방", sender="회장")
    assert "오리진 디아루가 · 모집 놋 · 12명" in summary.reply
    assert "오리진디아루가 · 모집 부방장 · 1명" in summary.reply

    left = await bot.handle(
        "/취소 DongDoro 오리진디아루가 놋", room="레이드방", sender="일반"
    )
    assert left.reply.startswith("✂️ 취소 완료")
    assert "'DongDoro' 님을 명단에서 뺐어요." in left.reply
    assert "현재 11명" in left.reply


@pytest.mark.anyio
async def test_raid_guide_and_cancel_ranking(tmp_path) -> None:
    from app.bot import FOLD_PADDING, RAID_GUIDE

    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="회장")

    # /레이드신청은 기본 안내문이고, 길어서 첫 줄만 보이게 접힌다.
    guide = await bot.handle("/레이드신청", room="레이드방", sender="일반")
    assert guide.reply.startswith("🎫 레이드 초대 시스템 사용법")
    assert FOLD_PADDING in guide.reply
    assert guide.reply.replace(FOLD_PADDING, "") == RAID_GUIDE

    # 취소할 때마다 입력한 게임 닉네임 기준으로 누적되고,
    # 응답 맨 아래에 오늘 몇 번째 취소인지 나온다.
    await bot.handle("/레이드모집 잠만보 host 123456789012", room="레이드방", sender="회장")
    await bot.handle("/참가 flaky 잠만보 host", room="레이드방", sender="일반")
    first_cancel = await bot.handle("/취소 flaky 잠만보 host", room="레이드방", sender="일반")
    assert "취소 횟수 : 오늘 1회 · 누적 1회" in first_cancel.reply
    await bot.handle("/참가 flaky 잠만보 host", room="레이드방", sender="일반")
    second_cancel = await bot.handle("/취소 flaky 잠만보 host", room="레이드방", sender="일반")
    assert "취소 횟수 : 오늘 2회 · 누적 2회" in second_cancel.reply

    await bot.handle("/참가 steady 잠만보 host", room="레이드방", sender="일반")
    await bot.handle("/취소 steady 잠만보 host", room="레이드방", sender="일반")

    # 12명이 더 취소해도 랭킹은 자르지 않고 전원 보여준다.
    for index in range(12):
        await bot.handle(f"/참가 extra{index:02d} 잠만보 host", room="레이드방", sender="일반")
        await bot.handle(f"/취소 extra{index:02d} 잠만보 host", room="레이드방", sender="일반")

    denied = await bot.handle("/취소랭킹", room="레이드방", sender="일반")
    assert denied.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

    ranking = await bot.handle("/취소랭킹", room="레이드방", sender="회장")
    lines = [
        line for line in ranking.reply.replace(FOLD_PADDING, "").split(chr(10)) if line
    ]
    assert lines[0] == "✂️ 오늘의 레이드 취소 — 총 14명"
    assert lines[2] == "1. flaky - 2회"  # 오늘 횟수 많은 순
    assert lines[-1] == "14. steady - 1회"  # 동률은 최근 취소가 위로
    assert len(lines) == 2 + 14  # 제목/구분선 + 전원 (자르지 않음)

    # 하루가 지나면 랭킹은 비워진다 (누적 기록은 유지).
    from datetime import date, timedelta

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert bot.admin_store.list_raid_cancel_stats("레이드방", tomorrow) == []


@pytest.mark.anyio
async def test_raid_close_is_open_to_everyone(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="회장")

    await bot.handle(
        "/레이드모집 화이트큐레무 놋 123456789012",
        room="레이드방",
        sender="놋",
        user_key="hash:host-not",
    )
    await bot.handle("/참가 alpha 화이트큐레무 놋", room="레이드방", sender="일반")
    await bot.handle("/참가 bravo 화이트큐레무 놋", room="레이드방", sender="일반")
    await bot.handle("/취소 bravo 화이트큐레무 놋", room="레이드방", sender="일반")

    # 알림 오귀속 때문에 모집자 확인이 불가능해서 마감은 누구나 할 수 있다.
    closed = await bot.handle(
        "/마감 화이트큐레무 놋", room="레이드방", sender="지나가던사람", user_key="hash:x"
    )
    assert closed.reply.startswith("🔒 레이드 종료!")
    assert "🎯 화이트큐레무 · 👑 놋" in closed.reply
    assert "최종 참여 1명" in closed.reply
    assert "1팟(1명): alpha" in closed.reply
    assert "고생하셨어요" in closed.reply

    # 마감하면 모집 자체가 사라진다.
    after = await bot.handle("/현황 화이트큐레무 놋", room="레이드방", sender="회장")
    assert "모집을 찾지 못했어요" in after.reply

    # 초기화는 여전히 관리자 전용이다.
    await bot.handle(
        "/레이드모집 잠만보 놋 123456789012", room="레이드방", sender="놋", user_key="hash:host-not"
    )
    denied_clear = await bot.handle("/레이드초기화 전체", room="레이드방", sender="일반")
    assert denied_clear.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."
    cleared = await bot.handle("/레이드초기화 전체", room="레이드방", sender="회장")
    assert "1건을 모두 초기화" in cleared.reply
    empty = await bot.handle("/현황", room="레이드방", sender="회장")
    assert "진행 중인 레이드 모집이 없어요" in empty.reply


@pytest.mark.anyio
async def test_custom_append_extends_existing_command(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )
    await bot.handle("/오너등록 test-setup-code", room="레이드방", sender="오너")

    missing = await bot.handle(
        "/명령어이어쓰기 공지 둘째 줄",
        room="레이드방",
        sender="오너",
    )
    assert "먼저 /명령어등록" in missing.reply

    await bot.handle("/명령어등록 공지 첫째 줄", room="레이드방", sender="오너")
    appended = await bot.handle(
        "/명령어이어쓰기 공지 둘째 줄",
        room="레이드방",
        sender="오너",
    )
    assert "이어붙였습니다" in appended.reply

    await bot.handle("/명령어이어쓰기 공지 셋째 줄", room="레이드방", sender="오너")
    reply = await bot.handle("/공지", room="레이드방", sender="일반")
    assert reply.reply == "첫째 줄\n둘째 줄\n셋째 줄"

    denied = await bot.handle(
        "/명령어이어쓰기 공지 해킹",
        room="레이드방",
        sender="일반",
    )
    assert denied.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."


@pytest.mark.anyio
async def test_shared_admin_room_manages_target_room(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, owner_setup_code="test-setup-code")

    # 오너 등록 후 종합방에 관리자(부방장)를 추가하고 hash로 승격시킨다.
    await bot.handle("/오너등록 test-setup-code", room="개인방", sender="오너", user_key="hash:owner")
    await bot.handle("/대상방설정 종합방", room="개인방", sender="오너", user_key="hash:owner")
    await bot.handle("/관리자추가 부방장", room="개인방", sender="오너", user_key="hash:owner")
    await bot.handle(
        "/명령어등록 공지 승격용",
        room="종합방",
        sender="부방장",
        user_key="hash:sub",
    )
    assert ("부방장", "admin", "hash:sub") in store.list_admin_records("종합방")

    # 오너가 관리방에 방 단위 대상을 한 번 설정한다.
    linked = await bot.handle(
        "/대상방설정 종합방",
        room="관리방",
        sender="오너",
        user_key="hash:owner",
    )
    assert "종합방" in linked.reply

    # 부방장은 개인 대상방 설정 없이도 관리방에서 종합방을 관리할 수 있다.
    shown = await bot.handle("/대상방확인", room="관리방", sender="부방장", user_key="hash:sub")
    assert shown.reply == "현재 대상방: 종합방"

    saved = await bot.handle(
        "/명령어등록 공지 오늘 레이드 9시",
        room="관리방",
        sender="부방장",
        user_key="hash:sub",
    )
    assert saved.reply == "/공지 명령어를 저장했습니다."

    public_reply = await bot.handle("/공지", room="종합방", sender="일반")
    assert public_reply.reply == "오늘 레이드 9시"

    # 관리방에 흘러들어온 일반 유저는 여전히 거절된다.
    denied = await bot.handle(
        "/명령어등록 공지 해킹시도",
        room="관리방",
        sender="일반인",
        user_key="hash:nobody",
    )
    assert denied.reply == "이 명령어는 owner 또는 admin만 사용할 수 있습니다."

    # 관리방 자체 명령어만 관리방에서 실행된다. 대상방 명령어는 원격으로
    # 관리할 수 있어도 관리방에서 실행되거나 노출되지는 않는다.
    store.upsert_custom_command("관리방", "사이트", "관리 페이지 링크", "오너")
    own_room = await bot.handle("/사이트", room="관리방", sender="부방장", user_key="hash:sub")
    assert own_room.reply == "관리 페이지 링크"
    target_command = await bot.handle(
        "/공지", room="관리방", sender="부방장", user_key="hash:sub"
    )
    assert target_command.silent is True
    assert target_command.reply == ""
    hidden = await bot.handle("/사이트", room="종합방", sender="일반")
    assert hidden.silent is True


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
