from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


KST = timezone(timedelta(hours=9), "KST")
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE_CREDIT = "Open-Meteo"


class WeatherDataUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeatherLocation:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class PeriodWeather:
    label: str
    condition: str
    temperature: int
    precipitation_probability: int


@dataclass(frozen=True)
class CityWeather:
    location: str
    morning: PeriodWeather
    afternoon: PeriodWeather


@dataclass(frozen=True)
class NationalWeather:
    date: datetime
    cities: list[CityWeather]


WEATHER_LOCATIONS = [
    WeatherLocation("서울", 37.5665, 126.9780),
    WeatherLocation("춘천", 37.8813, 127.7298),
    WeatherLocation("강릉", 37.7519, 128.8761),
    WeatherLocation("대전", 36.3504, 127.3845),
    WeatherLocation("광주", 35.1595, 126.8526),
    WeatherLocation("대구", 35.8714, 128.6014),
    WeatherLocation("부산", 35.1796, 129.0756),
    WeatherLocation("제주", 33.4996, 126.5312),
]

WEATHER_CODE_KO = {
    0: "맑음",
    1: "대체로 맑음",
    2: "구름 조금",
    3: "흐림",
    45: "안개",
    48: "안개",
    51: "약한 이슬비",
    53: "이슬비",
    55: "강한 이슬비",
    56: "어는 이슬비",
    57: "강한 어는 이슬비",
    61: "약한 비",
    63: "비",
    65: "강한 비",
    66: "어는 비",
    67: "강한 어는 비",
    71: "약한 눈",
    73: "눈",
    75: "강한 눈",
    77: "눈알",
    80: "약한 소나기",
    81: "소나기",
    82: "강한 소나기",
    85: "약한 눈소나기",
    86: "눈소나기",
    95: "뇌우",
    96: "우박 동반 뇌우",
    99: "강한 우박 동반 뇌우",
}

WEATHER_SEVERITY = {
    0: 0,
    1: 1,
    2: 2,
    3: 3,
    45: 4,
    48: 4,
    51: 5,
    53: 5,
    55: 5,
    56: 6,
    57: 6,
    61: 7,
    63: 7,
    65: 8,
    66: 8,
    67: 8,
    71: 7,
    73: 7,
    75: 8,
    77: 7,
    80: 7,
    81: 7,
    82: 8,
    85: 7,
    86: 8,
    95: 9,
    96: 10,
    99: 10,
}


class KoreaWeatherClient:
    def __init__(
        self,
        locations: list[WeatherLocation] | None = None,
        cache_ttl_seconds: int = 900,
    ) -> None:
        self.locations = locations or WEATHER_LOCATIONS
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: NationalWeather | None = None
        self._cache_until = 0.0

    async def format_today(self) -> str:
        weather = await self.get_today()
        return format_national_weather(weather)

    async def get_today(self, now: datetime | None = None) -> NationalWeather:
        now = _ensure_kst(now or datetime.now(KST))
        monotonic_now = time.monotonic()
        if (
            self._cache
            and self._cache.date.date() == now.date()
            and monotonic_now < self._cache_until
        ):
            return self._cache

        raw = await self._fetch_forecast()
        payloads = raw if isinstance(raw, list) else [raw]
        cities: list[CityWeather] = []
        for location, payload in zip(self.locations, payloads, strict=False):
            if not isinstance(payload, dict):
                continue
            city = _parse_city_weather(location, payload, now)
            if city:
                cities.append(city)

        if not cities:
            raise WeatherDataUnavailableError("no usable weather data")

        weather = NationalWeather(date=now, cities=cities)
        self._cache = weather
        self._cache_until = monotonic_now + self.cache_ttl_seconds
        return weather

    async def _fetch_forecast(self) -> object:
        params = {
            "latitude": ",".join(str(location.latitude) for location in self.locations),
            "longitude": ",".join(str(location.longitude) for location in self.locations),
            "hourly": "weather_code,temperature_2m,precipitation_probability",
            "timezone": "Asia/Seoul",
            "forecast_days": "1",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    OPEN_METEO_URL,
                    params=params,
                    headers={"User-Agent": "KakaoPoGo"},
                )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WeatherDataUnavailableError(str(exc)) from exc


def format_national_weather(weather: NationalWeather) -> str:
    lines = [
        "【 오늘 전국 날씨 】",
        f"기준: {_format_date(weather.date)} · 전국 대표 {len(weather.cities)}개 지역",
        "",
    ]
    lines.extend(_format_period_section("오전", [city.morning for city in weather.cities]))
    lines.extend(_format_period_section("오후", [city.afternoon for city in weather.cities]))
    lines.append("※ 대표 도시 기준 예보라 실제 동네 날씨와 다를 수 있습니다.")
    lines.append(f"출처: {SOURCE_CREDIT}")
    return "\n".join(lines).rstrip()


def _format_period_section(
    label: str,
    periods: list[PeriodWeather],
) -> list[str]:
    if not periods:
        return [f"[{label}]", "표시할 날씨 정보가 없습니다.", ""]

    conditions = _dominant_conditions(periods)
    temp_min = min(period.temperature for period in periods)
    temp_max = max(period.temperature for period in periods)
    rainy = [
        period
        for period in sorted(
            periods,
            key=lambda item: item.precipitation_probability,
            reverse=True,
        )
        if period.precipitation_probability >= 60
    ][:4]
    rainy_text = (
        ", ".join(
            f"{period.label} {period.precipitation_probability}%"
            for period in rainy
        )
        if rainy
        else "뚜렷하게 높은 곳 없음"
    )
    regional = " / ".join(
        f"{period.label} {period.temperature}° {period.condition} "
        f"{period.precipitation_probability}%"
        for period in periods
    )

    return [
        f"[{label}]",
        f"전반: {conditions}",
        f"기온: {temp_min}~{temp_max}°C",
        f"비 가능성 높은 곳: {rainy_text}",
        f"지역: {regional}",
        "",
    ]


def _parse_city_weather(
    location: WeatherLocation,
    payload: dict[str, Any],
    now: datetime,
) -> CityWeather | None:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        return None

    times = hourly.get("time") or []
    codes = hourly.get("weather_code") or []
    temperatures = hourly.get("temperature_2m") or []
    precipitation = hourly.get("precipitation_probability") or []
    if not all(isinstance(value, list) for value in (times, codes, temperatures, precipitation)):
        return None

    rows: list[tuple[datetime, int, float, int]] = []
    for raw_time, code, temperature, probability in zip(
        times,
        codes,
        temperatures,
        precipitation,
        strict=False,
    ):
        try:
            forecast_time = datetime.fromisoformat(str(raw_time)).replace(tzinfo=KST)
            if forecast_time.date() != now.date():
                continue
            rows.append(
                (
                    forecast_time,
                    int(code),
                    float(temperature),
                    int(probability),
                )
            )
        except (TypeError, ValueError):
            continue

    morning = _period_from_rows(location.name, rows, start_hour=6, end_hour=12)
    afternoon = _period_from_rows(location.name, rows, start_hour=12, end_hour=18)
    if not morning or not afternoon:
        return None
    return CityWeather(location.name, morning, afternoon)


def _period_from_rows(
    location_name: str,
    rows: list[tuple[datetime, int, float, int]],
    *,
    start_hour: int,
    end_hour: int,
) -> PeriodWeather | None:
    selected = [
        row
        for row in rows
        if start_hour <= row[0].hour < end_hour
    ]
    if not selected:
        return None

    codes = [row[1] for row in selected]
    temperatures = [row[2] for row in selected]
    probabilities = [row[3] for row in selected]
    representative_code = _representative_weather_code(codes)
    return PeriodWeather(
        label=location_name,
        condition=WEATHER_CODE_KO.get(representative_code, "날씨 정보"),
        temperature=round(sum(temperatures) / len(temperatures)),
        precipitation_probability=max(probabilities),
    )


def _representative_weather_code(codes: list[int]) -> int:
    if not codes:
        return 3
    serious = [
        code
        for code in codes
        if WEATHER_SEVERITY.get(code, 0) >= 5
    ]
    if serious:
        return max(serious, key=lambda code: WEATHER_SEVERITY.get(code, 0))
    counts = Counter(codes)
    return sorted(
        counts,
        key=lambda code: (counts[code], WEATHER_SEVERITY.get(code, 0)),
        reverse=True,
    )[0]


def _dominant_conditions(periods: list[PeriodWeather]) -> str:
    counts = Counter(period.condition for period in periods)
    conditions = [
        condition
        for condition, _count in counts.most_common(2)
    ]
    return " / ".join(conditions)


def _format_date(value: datetime) -> str:
    value = _ensure_kst(value)
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return f"{value.month}/{value.day}({weekdays[value.weekday()]})"


def _ensure_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)
