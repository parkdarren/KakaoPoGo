from datetime import datetime

from app.events import (
    KST,
    PokemonGoEvent,
    RaidBoss,
    _extract_featured_pokemon,
    format_event_schedule,
)
from app.name_map import NameResolver


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
            featured_pokemon=("뮤츠", "주뱃"),
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
    assert "└ 출현 포켓몬: 뮤츠, 주뱃" in reply
    assert "Outside Window" not in reply
    assert "메가: 메가 팬텀(1644/2055)" in reply
    assert "5성: 자시안 검왕(2188/2735)" in reply
    assert "출처: Leek Duck / ScrapedDuck" in reply


def test_event_schedule_handles_empty_window() -> None:
    now = datetime(2026, 7, 10, 18, 0, tzinfo=KST)

    reply = format_event_schedule([], [], now=now, days=7)

    assert "[진행 중]\n표시할 일정이 없습니다." in reply
    assert "[예정 이벤트]\n표시할 일정이 없습니다." in reply


def test_extract_featured_pokemon_translates_event_data() -> None:
    resolver = NameResolver()
    event = {
        "name": "Shadow Palkia in Shadow Raids",
        "extraData": {
            "communityday": {"spawns": [{"name": "Nickit"}]},
            "spotlight": {"list": [{"name": "Zubat"}]},
            "raidbattles": {"bosses": [{"name": "Palkia"}]},
        },
    }

    names = _extract_featured_pokemon(event, resolver)

    assert names == ["훔처우", "주뱃", "그림자 펄기아"]


def test_extract_featured_pokemon_from_event_title() -> None:
    resolver = NameResolver()

    max_monday = _extract_featured_pokemon(
        {"name": "Dynamax Deino during Max Monday", "extraData": {"generic": {}}},
        resolver,
    )
    raid_hour = _extract_featured_pokemon(
        {"name": "Kyogre Raid Hour", "extraData": {"generic": {}}},
        resolver,
    )

    assert max_monday == ["다이맥스 모노두"]
    assert raid_hour == ["가이오가"]
