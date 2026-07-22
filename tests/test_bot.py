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
    assert parse_command("/포켓몬고이벤트") == ("events", "")
    assert parse_command("/이벤트") == ("events", "")
    assert parse_command("/일정") == ("events", "")
    assert parse_command("/날씨") == ("weather", "")
    assert parse_command("/전국날씨") == ("weather", "")
    assert parse_command("/오늘의포켓몬") == ("daily", "")
    assert parse_command("/출첵") == ("daily", "")
    assert parse_command("/ㅊㅊ") == ("daily", "")
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
    assert "명령어 관리" in page.text

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

    moved = store.migrate_room(old, new)

    assert moved["custom_commands"] == 1  # '규칙'만 이동 ('공지'는 새쪽 유지)
    assert moved["room_admins"] == 1
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
    # user_id 로 개인톡방(chat_id 기반)의 오너로 등록된다.
    assert ("개인톡사용자", "owner", "iris:77") in test_bot.admin_store.list_admin_records(
        "개인톡:555"
    )


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
    # 명령어도 채팅 1건으로 센다.
    send("/도움말", "수다왕", "hash:talker")

    daily = send("/일일랭킹", "수다왕", "hash:talker").json()["reply"]
    lines = daily.split("\\n") if "\\n" in daily else daily.split("\n")
    assert lines[0] == "💬 오늘의 채팅 랭킹 TOP 10"
    assert "🥇 수다왕 - 5회" in daily  # 채팅 3 + /도움말 + /일일랭킹 자신
    assert "🥈 조용한사람 - 1회" in daily

    total = send("/랭킹", "조용한사람", "hash:quiet").json()["reply"]
    assert total.startswith("💬 누적 채팅 랭킹 TOP 10")
    assert "수다왕" in total

    # 새 방에서는 방금 친 명령 자신만 1회로 잡힌다.
    empty = client.get(
        "/command",
        headers=auth,
        params={"text": "/일일랭킹", "room": "새방", "sender": "아무개", "user_key": "hash:new"},
    ).json()["reply"]
    assert "🥇 아무개 - 1회" in empty


@pytest.mark.anyio
async def test_raffle_draws_from_active_members_only(tmp_path) -> None:
    bot = PokemonGoBot(
        admin_store=AdminStore(tmp_path / "test.sqlite3"),
        owner_setup_code="test-setup-code",
    )

    # 활동 없는 방은 추첨 불가.
    empty = await bot.handle("/추첨", room="빈방", sender="일반")
    assert "추첨할 대상이 없어요" in empty.reply

    # 활동한 사람만 풀에 들어간다.
    for _ in range(5):
        bot.record_chat("추첨방", "활발이", "iris:1")
    bot.record_chat("추첨방", "가끔이", "iris:2")

    pool = dict(bot.admin_store.raffle_pool("추첨방"))
    assert pool == {"활발이": 5, "가끔이": 1}  # 가중치 = 활동량

    result = await bot.handle("/추첨", room="추첨방", sender="일반")
    assert "🎉 추첨 결과" in result.reply
    assert ("활발이" in result.reply) or ("가끔이" in result.reply)
    # 활동량 숫자는 노출하지 않는다.
    assert "5회" not in result.reply and " - " not in result.reply
    assert "총 2명" in result.reply


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
    pool = dict(test_bot.admin_store.raffle_pool("방"))
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

    # 정렬: 영문 먼저, 숫자는 그 뒤 (포켓몬고 닉네임은 영문/숫자만 가능)
    await bot.handle("/레이드모집 잠만보 놋 123456789012", room="레이드방", sender="놋")
    await bot.handle("/참가 zeta 잠만보 놋", room="레이드방", sender="일반")
    await bot.handle("/참가 Abc 잠만보 놋", room="레이드방", sender="일반")
    await bot.handle("/참가 7lucky 잠만보 놋", room="레이드방", sender="일반")
    order = await bot.handle("/현황 잠만보 놋", room="레이드방", sender="회장")
    assert "1팟(3명): Abc, zeta, 7lucky" in order.reply

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

    # 관리방 자체에 등록된 명령어는 관리방에서 실행되고(대상방보다 우선),
    # 대상방(종합방)에는 노출되지 않는다.
    store.upsert_custom_command("관리방", "사이트", "관리 페이지 링크", "오너")
    own_room = await bot.handle("/사이트", room="관리방", sender="부방장", user_key="hash:sub")
    assert own_room.reply == "관리 페이지 링크"
    fallback = await bot.handle("/공지", room="관리방", sender="부방장", user_key="hash:sub")
    assert fallback.reply == "오늘 레이드 9시"  # 대상방 명령어는 여전히 동작
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
