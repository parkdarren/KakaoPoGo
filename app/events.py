from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.localization import ko_form
from app.name_map import NameResolver


KST = timezone(timedelta(hours=9), "KST")
EVENTS_URL = os.getenv(
    "POGO_EVENTS_URL",
    "https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/events.min.json",
)
RAIDS_URL = os.getenv(
    "POGO_RAIDS_URL",
    "https://raw.githubusercontent.com/bigfoott/ScrapedDuck/data/raids.min.json",
)
SOURCE_CREDIT = "Leek Duck / ScrapedDuck"

EVENT_TYPE_KO = {
    "choose-your-path": "선택형 이벤트",
    "community-day": "커뮤니티 데이",
    "event": "이벤트",
    "go-battle-league": "GO 배틀리그",
    "go-pass": "GO 패스",
    "max-battles": "맥스 배틀",
    "max-mondays": "맥스 먼데이",
    "pokemon-go-fest": "GO Fest",
    "pokemon-spotlight-hour": "스포트라이트 아워",
    "raid-battles": "레이드",
    "raid-day": "레이드 데이",
    "raid-hour": "레이드 아워",
    "season": "시즌",
    "twitch-drops": "Twitch Drops",
}
RAID_TIER_KO = {
    "1-Star Raids": "1성",
    "3-Star Raids": "3성",
    "5-Star Raids": "5성",
    "Mega Raids": "메가",
    "Elite Raids": "엘리트",
}


class EventDataUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class PokemonGoEvent:
    name: str
    event_type: str
    start: datetime
    end: datetime
    link: str = ""
    featured_pokemon: tuple[str, ...] = ()


@dataclass(frozen=True)
class RaidBoss:
    name: str
    tier: str
    cp_normal_max: int | None = None
    cp_boosted_max: int | None = None


@dataclass(frozen=True)
class EventSchedule:
    events: list[PokemonGoEvent]
    raids: list[RaidBoss]


class PokemonGoEventClient:
    def __init__(
        self,
        events_url: str = EVENTS_URL,
        raids_url: str = RAIDS_URL,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        self.events_url = events_url
        self.raids_url = raids_url
        self.cache_ttl_seconds = cache_ttl_seconds or int(
            os.getenv("POGO_EVENT_CACHE_TTL_SECONDS", "900")
        )
        self._cache: EventSchedule | None = None
        self._cache_until = 0.0
        self.name_resolver = NameResolver()

    async def format_schedule(self, days: int = 7) -> str:
        schedule = await self.get_schedule()
        return format_event_schedule(
            schedule.events,
            schedule.raids,
            days=days,
            name_resolver=self.name_resolver,
        )

    async def get_schedule(self) -> EventSchedule:
        now_monotonic = time.monotonic()
        if self._cache and now_monotonic < self._cache_until:
            return self._cache

        try:
            events = await self._fetch_events()
            try:
                raids = await self._fetch_raids()
            except EventDataUnavailableError:
                raids = self._cache.raids if self._cache else []
        except EventDataUnavailableError:
            if self._cache:
                return self._cache
            raise

        self._cache = EventSchedule(events=events, raids=raids)
        self._cache_until = now_monotonic + self.cache_ttl_seconds
        return self._cache

    async def _fetch_events(self) -> list[PokemonGoEvent]:
        raw_events = await self._fetch_json(self.events_url)
        if not isinstance(raw_events, list):
            raise EventDataUnavailableError("events payload is not a list")

        events: list[PokemonGoEvent] = []
        for item in raw_events:
            if not isinstance(item, dict):
                continue
            try:
                name = str(item["name"]).strip()
                event_type = str(item.get("eventType") or item.get("heading") or "event")
                start = _parse_event_time(str(item["start"]))
                end = _parse_event_time(str(item["end"]))
            except (KeyError, ValueError, TypeError):
                continue
            if not name or end < start:
                continue
            events.append(
                PokemonGoEvent(
                    name=name,
                    event_type=event_type,
                    start=start,
                    end=end,
                    link=str(item.get("link") or ""),
                    featured_pokemon=tuple(
                        _extract_featured_pokemon(item, self.name_resolver)
                    ),
                )
            )
        if not events:
            raise EventDataUnavailableError("events payload is empty")
        return events

    async def _fetch_raids(self) -> list[RaidBoss]:
        raw_raids = await self._fetch_json(self.raids_url)
        if not isinstance(raw_raids, list):
            raise EventDataUnavailableError("raids payload is not a list")

        raids: list[RaidBoss] = []
        for item in raw_raids:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            tier = str(item.get("tier") or "").strip()
            if not name or not tier:
                continue

            combat_power = item.get("combatPower") or {}
            normal = combat_power.get("normal") or {}
            boosted = combat_power.get("boosted") or {}
            raids.append(
                RaidBoss(
                    name=name,
                    tier=tier,
                    cp_normal_max=_optional_int(normal.get("max")),
                    cp_boosted_max=_optional_int(boosted.get("max")),
                )
            )
        return raids

    @staticmethod
    async def _fetch_json(url: str) -> object:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers={"User-Agent": "KakaoPoGo"})
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EventDataUnavailableError(str(exc)) from exc


def format_event_schedule(
    events: list[PokemonGoEvent],
    raids: list[RaidBoss] | None = None,
    *,
    days: int = 7,
    now: datetime | None = None,
    name_resolver: NameResolver | None = None,
) -> str:
    now = _ensure_local(now or datetime.now(KST))
    window_end = now + timedelta(days=days)
    visible_events = [
        event
        for event in events
        if event.end >= now and event.start <= window_end
    ]
    visible_events.sort(key=lambda event: (event.start, event.end, event.name))

    ongoing = [event for event in visible_events if event.start <= now <= event.end]
    upcoming = [event for event in visible_events if event.start > now]
    resolver = name_resolver or NameResolver()

    lines = [
        "【 포켓몬GO 이벤트 일정 】",
        f"기준: {_format_datetime(now)}",
        f"범위: {_format_date(now)} ~ {_format_date(window_end)}",
        "",
    ]
    lines.extend(_format_event_section("진행 중", ongoing, limit=7))
    lines.extend(_format_event_section("예정 이벤트", upcoming, limit=8))

    if raids:
        lines.append("[현재 레이드]")
        lines.append("CP는 일반/날씨부스트 100% 최대값입니다.")
        for tier, bosses in _group_raids_by_tier(raids).items():
            boss_texts = [_format_raid_boss(boss, resolver) for boss in bosses]
            lines.append(f"{tier}: {', '.join(boss_texts)}")
        lines.append("")

    lines.append(f"출처: {SOURCE_CREDIT}")
    return "\n".join(lines).rstrip()


def format_daily_brief(
    events: list[PokemonGoEvent],
    *,
    now: datetime | None = None,
) -> str:
    """아침에 방으로 보낼 브리핑. 알릴 게 없으면 빈 문자열을 준다."""
    now = _ensure_local(now or datetime.now(KST))
    today = now.date()
    tomorrow = today + timedelta(days=1)

    starting = [e for e in events if e.start.date() == today]
    ending = [e for e in events if e.end.date() == today and e.start.date() != today]
    upcoming = [e for e in events if e.start.date() == tomorrow]
    if not (starting or ending or upcoming):
        return ""

    def entry(event: PokemonGoEvent) -> str:
        type_name = EVENT_TYPE_KO.get(event.event_type, event.event_type)
        return f"・[{type_name}] {event.name}"

    lines = [f"📅 오늘의 포켓몬GO ({_format_date(now)})", "━━━━━━━━━━━━━━"]
    for title, group in (
        ("🎉 오늘 시작", starting),
        ("⏰ 오늘 종료", ending),
        ("🔜 내일 시작", upcoming),
    ):
        if not group:
            continue
        lines.append(title)
        lines.extend(entry(event) for event in sorted(group, key=lambda e: e.start))
        lines.append("")
    lines.append("자세히 → /포켓몬고이벤트")
    return "\n".join(lines)


def _format_event_section(
    title: str,
    events: list[PokemonGoEvent],
    *,
    limit: int,
) -> list[str]:
    lines = [f"[{title}]"]
    if not events:
        lines.append("표시할 일정이 없습니다.")
        lines.append("")
        return lines

    for index, event in enumerate(events[:limit], start=1):
        type_name = EVENT_TYPE_KO.get(event.event_type, event.event_type)
        lines.append(f"{index}. [{type_name}] {event.name}")
        lines.append(f"└ 기간: {_format_period(event.start, event.end)}")
        if event.featured_pokemon:
            lines.append(f"└ 출현 포켓몬: {', '.join(event.featured_pokemon)}")
    if len(events) > limit:
        lines.append(f"외 {len(events) - limit}개 일정이 더 있습니다.")
    lines.append("")
    return lines


def _parse_event_time(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(KST)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _format_period(start: datetime, end: datetime) -> str:
    start = _ensure_local(start)
    end = _ensure_local(end)
    if start.date() == end.date():
        return f"{_format_date(start)} {_format_time(start)}~{_format_time(end)}"
    return f"{_format_datetime(start)} ~ {_format_datetime(end)}"


def _format_datetime(value: datetime) -> str:
    value = _ensure_local(value)
    return f"{_format_date(value)} {_format_time(value)}"


def _format_date(value: datetime) -> str:
    value = _ensure_local(value)
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return f"{value.month}/{value.day}({weekdays[value.weekday()]})"


def _format_time(value: datetime) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def _ensure_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def _group_raids_by_tier(raids: list[RaidBoss]) -> dict[str, list[RaidBoss]]:
    grouped: dict[str, list[RaidBoss]] = {}
    for raid in sorted(raids, key=lambda item: (_tier_order(item.tier), item.name)):
        grouped.setdefault(RAID_TIER_KO.get(raid.tier, raid.tier), []).append(raid)
    return grouped


def _tier_order(tier: str) -> int:
    order = {
        "Mega Raids": 0,
        "5-Star Raids": 1,
        "3-Star Raids": 2,
        "1-Star Raids": 3,
        "Elite Raids": 4,
    }
    return order.get(tier, 99)


def _format_raid_boss(boss: RaidBoss, resolver: NameResolver) -> str:
    name = _translate_pokemon_name(boss.name, resolver)
    if boss.cp_normal_max and boss.cp_boosted_max:
        return f"{name}({boss.cp_normal_max}/{boss.cp_boosted_max})"
    if boss.cp_normal_max:
        return f"{name}({boss.cp_normal_max})"
    return name


def _extract_featured_pokemon(item: dict[str, object], resolver: NameResolver) -> list[str]:
    extra = item.get("extraData")
    if not isinstance(extra, dict):
        return []

    names: list[str] = []
    community_day = extra.get("communityday")
    if isinstance(community_day, dict):
        _append_named_entries(names, community_day.get("spawns"), resolver)

    spotlight = extra.get("spotlight")
    if isinstance(spotlight, dict):
        before_spotlight = len(names)
        _append_named_entries(names, spotlight.get("list"), resolver)
        if len(names) == before_spotlight:
            _append_named_entries(names, [spotlight], resolver)

    raid_battles = extra.get("raidbattles")
    if isinstance(raid_battles, dict):
        event_name = str(item.get("name") or "")
        raid_names = _entry_names(raid_battles.get("bosses"))
        for raid_name in raid_names:
            if "shadow" in event_name.lower() and not raid_name.lower().startswith("shadow "):
                raid_name = f"Shadow {raid_name}"
            _append_unique(names, _translate_pokemon_name(raid_name, resolver))

    if not names:
        names.extend(_extract_featured_from_title(str(item.get("name") or ""), resolver))

    return names[:8]


def _append_named_entries(
    target: list[str],
    value: object,
    resolver: NameResolver,
) -> None:
    for name in _entry_names(value):
        _append_unique(target, _translate_pokemon_name(name, resolver))


def _entry_names(value: object) -> list[str]:
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        return [name] if name else []
    if not isinstance(value, list):
        return []

    names: list[str] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


def _extract_featured_from_title(name: str, resolver: NameResolver) -> list[str]:
    rules = [
        (r"^Dynamax (?P<name>.+?) during Max Monday$", "다이맥스 "),
        (r"^(?P<name>.+?) Raid Hour$", ""),
        (r"^(?P<name>.+?) Spotlight Hour$", ""),
        (r"^(?P<name>.+?) Community Day$", ""),
    ]
    for pattern, prefix in rules:
        matched = re.match(pattern, name.strip(), flags=re.IGNORECASE)
        if not matched:
            continue
        pokemon_name = matched.group("name").strip()
        if not pokemon_name:
            return []
        return [f"{prefix}{_translate_pokemon_name(pokemon_name, resolver)}"]
    return []


def _translate_pokemon_name(name: str, resolver: NameResolver) -> str:
    clean = name.strip()
    shadow_prefix = ""
    if clean.lower().startswith("shadow "):
        shadow_prefix = "그림자 "
        clean = clean[7:].strip()

    clean = re.sub(r"\(([^)]+)\)", r" \1", clean).strip()
    resolved = resolver.resolve_query(clean)
    display_name = resolver.display_name(resolved.name)
    parts: list[str] = []
    if shadow_prefix:
        parts.append(shadow_prefix.strip())
    if resolved.mega:
        parts.append("메가")
    parts.append(display_name)
    if resolved.form:
        parts.append(ko_form(resolved.form))
    return " ".join(part for part in parts if part)


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
