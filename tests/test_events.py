from datetime import datetime

from app.events import KST, PokemonGoEvent, RaidBoss, format_event_schedule


def test_event_schedule_shows_upcoming_dates_and_current_raids() -> None:
    now = datetime(2026, 7, 10, 18, 0, tzinfo=KST)
    events = [
        PokemonGoEvent(
            name="Road of Legends",
            event_type="event",
            start=datetime(2026, 7, 10, 10, 0, tzinfo=KST),
            end=datetime(2026, 7, 10, 20, 0, tzinfo=KST),
        ),
        PokemonGoEvent(
            name="Pokemon GO Fest 2026: Global",
            event_type="pokemon-go-fest",
            start=datetime(2026, 7, 11, 10, 0, tzinfo=KST),
            end=datetime(2026, 7, 12, 18, 0, tzinfo=KST),
        ),
        PokemonGoEvent(
            name="Outside Window",
            event_type="event",
            start=datetime(2026, 7, 25, 10, 0, tzinfo=KST),
            end=datetime(2026, 7, 25, 20, 0, tzinfo=KST),
        ),
    ]
    raids = [
        RaidBoss(
            name="Zacian (Crowned Sword)",
            tier="5-Star Raids",
            cp_normal_max=2188,
            cp_boosted_max=2735,
        ),
        RaidBoss(
            name="Mega Gengar",
            tier="Mega Raids",
            cp_normal_max=1644,
            cp_boosted_max=2055,
        ),
    ]

    reply = format_event_schedule(events, raids, now=now, days=7)

    assert "【 포켓몬GO 이벤트 일정 】" in reply
    assert "[진행 중]" in reply
    assert "1. [이벤트] Road of Legends" in reply
    assert "└ 기간: 7/10(금) 10:00~20:00" in reply
    assert "[예정 이벤트]" in reply
    assert "1. [GO Fest] Pokemon GO Fest 2026: Global" in reply
    assert "└ 기간: 7/11(토) 10:00 ~ 7/12(일) 18:00" in reply
    assert "Outside Window" not in reply
    assert "메가: 메가 팬텀(1644/2055)" in reply
    assert "5성: 자시안 검왕(2188/2735)" in reply
    assert "출처: Leek Duck / ScrapedDuck" in reply


def test_event_schedule_handles_empty_window() -> None:
    now = datetime(2026, 7, 10, 18, 0, tzinfo=KST)

    reply = format_event_schedule([], [], now=now, days=7)

    assert "[진행 중]\n표시할 일정이 없습니다." in reply
    assert "[예정 이벤트]\n표시할 일정이 없습니다." in reply
