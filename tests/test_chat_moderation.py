from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.admin_store import AdminStore
from app.bot import PokemonGoBot
from app.chat_moderation import (
    KoreanChatAnalyzer,
    ModerationSettings,
    ModerationSignal,
)
from app.moderation_learning import ModerationClassifier, ModerationLearningManager


def test_kiwi_distinguishes_eums_ending_from_nouns() -> None:
    analyzer = KoreanChatAnalyzer()

    assert analyzer.is_eums_style("오늘 레이드 끝났음")[0] is True
    assert analyzer.is_eums_style("도움")[0] is False
    assert analyzer.is_eums_style("마음")[0] is False
    assert analyzer.is_eums_style("처음")[0] is False


def test_fragmented_chat_is_detected_in_sliding_window() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(
        enabled=True,
        fragment_count=4,
        fragment_window_seconds=12,
        eums_count=10,
    )
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)

    messages = ["아", "진짜", "이건", "아니지요"]
    signals = []
    for index, message in enumerate(messages):
        signals = analyzer.analyze(
            "방", "iris:1", message, settings, started + timedelta(seconds=index * 2)
        )

    fragment = next(signal for signal in signals if signal.kind == "fragment")
    assert fragment.messages == tuple(messages)
    assert fragment.features["duration_seconds"] == 6.0


def test_two_consecutive_parts_that_form_one_sentence_are_detected() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(
        enabled=True,
        fragment_count=2,
        fragment_window_seconds=12,
        eums_count=10,
    )
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)

    assert analyzer.analyze("테스트방", "iris:1", "아 나도", settings, started) == []
    signals = analyzer.analyze(
        "테스트방",
        "iris:1",
        "그란돈",
        settings,
        started + timedelta(seconds=2),
    )

    fragment = next(signal for signal in signals if signal.kind == "fragment")
    assert fragment.messages == ("아 나도", "그란돈")
    assert fragment.features["duration_seconds"] == 2.0


def test_another_speaker_breaks_the_fragment_run() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(fragment_count=2, eums_count=10)
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)

    analyzer.analyze("테스트방", "iris:1", "오늘", settings, started)
    analyzer.analyze(
        "테스트방", "iris:2", "네", settings, started + timedelta(seconds=1)
    )
    signals = analyzer.analyze(
        "테스트방", "iris:1", "레이드", settings, started + timedelta(seconds=2)
    )

    assert not any(signal.kind == "fragment" for signal in signals)


def test_two_independent_complete_messages_are_not_fragment_spam() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(fragment_count=2, eums_count=10)
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)

    analyzer.analyze("테스트방", "iris:1", "안녕하세요", settings, started)
    signals = analyzer.analyze(
        "테스트방",
        "iris:1",
        "레이드 하실 분?",
        settings,
        started + timedelta(seconds=2),
    )

    assert not any(signal.kind == "fragment" for signal in signals)


def test_fragment_detection_can_be_suppressed_for_one_room() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(fragment_count=2, eums_count=10)
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)
    analyzer.suppress_fragments("추첨방", 15, started)

    for index, message in enumerate(["5", "4", "3", "2", "1"], start=1):
        signals = analyzer.analyze(
            "추첨방",
            "iris:host",
            message,
            settings,
            started + timedelta(seconds=index),
        )
        assert not any(signal.kind == "fragment" for signal in signals)

    analyzer.analyze("다른방", "iris:1", "아 나도", settings, started)
    other_room_signals = analyzer.analyze(
        "다른방", "iris:1", "그란돈", settings, started + timedelta(seconds=2)
    )
    assert any(signal.kind == "fragment" for signal in other_room_signals)

    analyzer.analyze(
        "추첨방", "iris:host", "아 나도", settings, started + timedelta(seconds=16)
    )
    resumed_signals = analyzer.analyze(
        "추첨방", "iris:host", "그란돈", settings, started + timedelta(seconds=18)
    )
    assert any(signal.kind == "fragment" for signal in resumed_signals)


def test_fragmented_chat_keeps_messages_sent_after_first_detection() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(
        enabled=True,
        fragment_count=3,
        fragment_window_seconds=12,
        eums_count=10,
    )
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)

    messages = ["테스트니 경고 주지마셈", "테스트니까", "경고", "주지", "마세요"]
    signals = []
    for index, message in enumerate(messages):
        signals = analyzer.analyze(
            "방", "iris:1", message, settings, started + timedelta(seconds=index * 2)
        )

    fragment = next(signal for signal in signals if signal.kind == "fragment")
    assert fragment.messages == tuple(messages)
    assert len(fragment.sent_at) == len(messages)
    assert fragment.features["continuation"] is True


def test_fragmented_chat_accepts_medium_length_sentence_parts() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(
        enabled=True,
        fragment_count=4,
        fragment_window_seconds=12,
        eums_count=10,
    )
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)
    messages = [
        "안녕하세요 오늘 레이드 같이 하실 분",
        "오후 다섯시에 시작하려고 합니다",
        "늦으시는 분은 미리 말씀 부탁드려요",
        "참여 가능하시면 댓글 남겨 주세요",
    ]

    signals = []
    for index, message in enumerate(messages):
        signals = analyzer.analyze(
            "테스트방",
            "iris:1",
            message,
            settings,
            started + timedelta(seconds=index * 2),
        )

    fragment = next(signal for signal in signals if signal.kind == "fragment")
    assert fragment.messages == tuple(messages)
    assert fragment.features["average_length"] > 8
    assert fragment.features["max_length"] > 12


def test_fragmented_chat_still_requires_configured_message_count() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(
        enabled=True,
        fragment_count=4,
        fragment_window_seconds=12,
        eums_count=10,
    )
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)

    signals = []
    for index, message in enumerate(["안녕하세요", "오늘 레이드", "같이 가실까요"]):
        signals = analyzer.analyze(
            "테스트방",
            "iris:1",
            message,
            settings,
            started + timedelta(seconds=index * 2),
        )

    assert not any(signal.kind == "fragment" for signal in signals)


def test_fragmented_chat_ignores_messages_outside_time_window() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(
        enabled=True,
        fragment_count=4,
        fragment_window_seconds=12,
        eums_count=10,
    )
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)

    signals = []
    for index, message in enumerate(["안녕하세요", "오늘 레이드", "같이 가실", "분 계신가요"]):
        signals = analyzer.analyze(
            "테스트방",
            "iris:1",
            message,
            settings,
            started + timedelta(seconds=index * 5),
        )

    assert not any(signal.kind == "fragment" for signal in signals)


def test_eums_style_warns_on_the_first_message() -> None:
    analyzer = KoreanChatAnalyzer()
    settings = ModerationSettings(fragment_count=10, eums_count=1)
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)

    signals = analyzer.analyze("방", "iris:2", "지금 가는 중임", settings, started)

    assert any(signal.kind == "eums" for signal in signals)


def test_moderation_settings_and_review_labels_are_room_scoped(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    assert store.get_moderation_settings("A방") == {
        "enabled": True,
        "fragment_count": 2,
        "fragment_window": 12,
        "eums_count": 1,
        "fragment_warning_enabled": True,
        "eums_warning_enabled": True,
    }
    store.set_moderation_settings("A방", False, 5, 20, 4)
    disabled_settings = store.get_moderation_settings("A방")
    assert disabled_settings["fragment_count"] == 5
    assert disabled_settings["fragment_warning_enabled"] is False
    assert disabled_settings["eums_warning_enabled"] is False
    assert store.get_moderation_settings("B방")["fragment_count"] == 2

    incident_id = store.record_moderation_incident(
        "A방",
        "iris:1",
        "테스터",
        "fragment",
        0.82,
        4,
        "아 / 진짜 / 이건 / 아니지요",
        {"duration_seconds": 6.0},
    )
    assert store.moderation_training_counts("A방")["pending"] == 1
    assert store.moderation_training_counts("B방")["pending"] == 0
    assert store.review_moderation_incident("A방", incident_id, "confirmed")
    assert store.moderation_training_counts("A방")["confirmed"] == 1
    assert store.list_moderation_incidents("A방", "confirmed")[0]["preview"].startswith("아 /")


def test_moderation_corpus_is_room_scoped_anonymized_and_deduplicated(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")

    assert store.record_moderation_corpus(
        "iris:99:1", "A방", "iris:123", "안녕하세요", "1723600000000"
    )
    assert not store.record_moderation_corpus(
        "iris:99:1", "A방", "iris:123", "안녕하세요", "1723600000000"
    )
    assert store.record_moderation_corpus(
        "iris:100:1", "B방", "iris:123", "반갑습니다", "1723600001000"
    )

    assert store.moderation_corpus_stats("A방")["total"] == 1
    assert store.moderation_corpus_stats("B방")["total"] == 1
    with store._connect() as conn:
        row = conn.execute(
            "SELECT subject_hash, text FROM moderation_corpus WHERE room = ?", ("A방",)
        ).fetchone()
    assert row["subject_hash"] != "iris:123"
    assert row["text"] == "안녕하세요"


def test_moderation_models_train_activate_and_score_examples(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    classifier = ModerationClassifier(store)
    learning = ModerationLearningManager(store, classifier)

    result = learning.train(force=True)

    assert result["accepted"] is True
    split_score, split_used = classifier.predict_fragment(("아 나도", "그란돈"))
    normal_score, normal_used = classifier.predict_fragment(
        ("안녕하세요", "레이드 하실 분?")
    )
    eums_score, eums_used = classifier.predict_eums("확인했음")
    polite_score, polite_used = classifier.predict_eums("좋은 마음")
    assert split_used and normal_used and eums_used and polite_used
    assert split_score > normal_score
    assert eums_score > polite_score
    assert store.active_moderation_model()["version"] == result["version"]

    analyzer = KoreanChatAnalyzer(classifier)
    settings = ModerationSettings(fragment_count=2, eums_count=10)
    started = datetime(2026, 8, 14, tzinfo=timezone.utc)
    analyzer.analyze("학습방", "iris:1", "아 나도", settings, started)
    signals = analyzer.analyze(
        "학습방", "iris:1", "그란돈", settings, started + timedelta(seconds=2)
    )
    assert any(signal.kind == "fragment" for signal in signals)
    assert next(signal for signal in signals if signal.kind == "fragment").features[
        "model_used"
    ] is True

    eums_analyzer = KoreanChatAnalyzer(classifier)
    eums_settings = ModerationSettings(fragment_count=10, eums_count=3)
    eums_analyzer.analyze("학습방", "iris:2", "확인했음", eums_settings, started)
    eums_analyzer.analyze(
        "학습방", "iris:2", "참가 가능함", eums_settings, started + timedelta(seconds=2)
    )
    eums_signals = eums_analyzer.analyze(
        "학습방", "iris:2", "레이드 끝남", eums_settings, started + timedelta(seconds=4)
    )
    assert any(signal.kind == "eums" for signal in eums_signals)


def test_continued_messages_update_one_pending_incident(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    first_id = store.record_moderation_incident(
        "A방",
        "iris:1",
        "테스터",
        "fragment",
        0.82,
        3,
        "테스트니까 / 경고 / 주지",
        {"duration_seconds": 4.0},
        ("테스트니까", "경고", "주지"),
        ("2026-08-14T10:00:00+00:00", "", ""),
    )
    updated_id = store.record_moderation_incident(
        "A방",
        "iris:1",
        "테스터",
        "fragment",
        0.9,
        4,
        "테스트니까 / 경고 / 주지 / 마세요",
        {"duration_seconds": 6.0, "continuation": True},
        ("테스트니까", "경고", "주지", "마세요"),
        ("2026-08-14T10:00:00+00:00", "", "", ""),
    )

    items = store.list_moderation_incidents("A방")
    assert updated_id == first_id
    assert len(items) == 1
    assert [message["text"] for message in items[0]["messages"]] == [
        "테스트니까",
        "경고",
        "주지",
        "마세요",
    ]


class _StubAnalyzer:
    def warm_up(self) -> bool:
        return True

    def analyze(self, *_args, **_kwargs) -> list[ModerationSignal]:
        return [
            ModerationSignal(
                kind="fragment",
                score=0.9,
                messages=("아", "진짜", "이건", "아니지요"),
                features={"message_count": 4},
            )
        ]


def test_bot_records_observation_and_returns_fragment_warning(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, chat_analyzer=_StubAnalyzer())

    result = bot.record_chat("테스트방", "사용자", "iris:5", "아니지요")

    assert result == "사용자님 단타 주의해 주세요."
    items = store.list_moderation_incidents("테스트방")
    assert len(items) == 1
    assert items[0]["displayName"] == "사용자"


def test_bot_keeps_full_fragment_sequence_after_detection(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    store.set_moderation_settings("테스트방", True, 3, 12, 10)
    bot = PokemonGoBot(admin_store=store)
    messages = ["테스트니 경고 주지마셈", "테스트니까", "경고", "주지", "마세요"]

    warnings = []
    for message in messages:
        warning = bot.record_chat("테스트방", "사용자", "iris:5", message)
        if warning:
            warnings.append(warning)

    items = store.list_moderation_incidents("테스트방")
    assert len(items) == 1
    assert [message["text"] for message in items[0]["messages"]] == messages
    assert warnings == ["사용자님 단타 주의해 주세요."]


class _EumsStubAnalyzer:
    def warm_up(self) -> bool:
        return True

    def analyze(self, *_args, **_kwargs) -> list[ModerationSignal]:
        return [
            ModerationSignal(
                kind="eums",
                score=0.9,
                messages=("확인했음", "참가 가능함", "레이드 끝남"),
                features={"message_count": 3},
            )
        ]


def test_bot_returns_eums_warning(tmp_path) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    bot = PokemonGoBot(admin_store=store, chat_analyzer=_EumsStubAnalyzer())

    warning = bot.record_chat("테스트방", "박화영", "iris:5", "레이드 끝남")

    assert warning == "박화영님 음슴체 주의해 주세요."


def test_warning_output_can_be_disabled_without_losing_learning_incidents(
    tmp_path,
) -> None:
    store = AdminStore(tmp_path / "test.sqlite3")
    store.set_moderation_settings("학습방", True, 2, 12, 1, False, False)
    bot = PokemonGoBot(admin_store=store, chat_analyzer=_StubAnalyzer())

    warning = bot.record_chat("학습방", "사용자", "iris:5", "아니지요")

    assert warning == ""
    items = store.list_moderation_incidents("학습방")
    assert len(items) == 1
    assert items[0]["kind"] == "fragment"
    settings = store.get_moderation_settings("학습방")
    assert settings["enabled"] is True
    assert settings["fragment_warning_enabled"] is False
    assert settings["eums_warning_enabled"] is False


def test_owner_api_saves_settings_and_reviews_incident(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    store = AdminStore(tmp_path / "test.sqlite3")
    test_bot = PokemonGoBot(admin_store=store, chat_analyzer=_StubAnalyzer())
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "owner-key")
    headers = {"X-Bridge-Key": "owner-key"}
    client = TestClient(main_module.app)

    saved = client.post(
        "/admin/room-settings",
        headers=headers,
        json={
            "room": "관찰방",
            "moderation_observation_enabled": True,
            "moderation_fragment_count": 5,
            "moderation_fragment_window": 20,
            "moderation_eums_count": 1,
            "moderation_fragment_warning_enabled": False,
            "moderation_eums_warning_enabled": True,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["moderationFragmentCount"] == 5
    assert saved.json()["moderationEumsCount"] == 1
    assert saved.json()["moderationFragmentWarningEnabled"] is False
    assert saved.json()["moderationEumsWarningEnabled"] is True

    collection_disabled = client.post(
        "/admin/room-settings",
        headers=headers,
        json={
            "room": "수집중지방",
            "moderation_observation_enabled": False,
            "moderation_fragment_warning_enabled": True,
            "moderation_eums_warning_enabled": True,
        },
    )
    assert collection_disabled.status_code == 200
    assert collection_disabled.json()["moderationObservationEnabled"] is False
    assert collection_disabled.json()["moderationFragmentWarningEnabled"] is False
    assert collection_disabled.json()["moderationEumsWarningEnabled"] is False

    warned = client.post(
        "/command",
        headers=headers,
        json={
            "text": "아니지요",
            "room": "관찰방",
            "sender": "사용자",
            "user_key": "iris:5",
        },
    )
    assert warned.json() == {"reply": "", "silent": True}
    listed = client.get(
        "/admin/moderation-incidents",
        headers=headers,
        params={"room": "관찰방", "status": "pending"},
    )
    assert listed.json()["items"][0]["messages"][0]["text"] == "아"
    incident_id = listed.json()["items"][0]["id"]
    reviewed = client.post(
        "/admin/moderation-review",
        headers=headers,
        json={
            "room": "관찰방",
            "incident_id": incident_id,
            "status": "dismissed",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["counts"]["dismissed"] == 1


def test_iris_webhook_collects_only_unique_plain_group_chat(tmp_path, monkeypatch) -> None:
    import app.main as main_module

    store = AdminStore(tmp_path / "test.sqlite3")
    test_bot = PokemonGoBot(admin_store=store)
    monkeypatch.setattr(main_module, "bot", test_bot)
    monkeypatch.setenv("BRIDGE_KEY", "iris-secret")
    client = TestClient(main_module.app)

    def payload(message: str, log_id: str, *, mine: bool = False):
        return {
            "msg": message,
            "room": "학습방",
            "sender": "사용자",
            "json": {
                "_id": log_id,
                "chat_id": "999",
                "user_id": "123",
                "created_at": "1723600000000",
                "message": message,
                "v": '{"isMine":true}' if mine else '{"isMine":false}',
            },
        }

    client.post("/iris/iris-secret", json=payload("안녕하세요", "1"))
    client.post("/iris/iris-secret", json=payload("안녕하세요", "1"))
    client.post("/iris/iris-secret", json=payload("/도움말", "2"))
    client.post("/iris/iris-secret", json=payload("봇이 보낸 말", "3", mine=True))

    stats = store.moderation_corpus_stats("학습방")
    assert stats["total"] == 1
    assert stats["firstAt"] == "1723600000000"
