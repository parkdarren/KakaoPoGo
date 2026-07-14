from datetime import datetime

import pytest

from app.weather import (
    KST,
    CityWeather,
    KoreaWeatherClient,
    NationalWeather,
    PeriodWeather,
    WeatherLocation,
    format_national_weather,
)


def test_format_national_weather_shows_morning_and_afternoon() -> None:
    weather = NationalWeather(
        date=datetime(2026, 7, 14, 9, 0, tzinfo=KST),
        cities=[
            CityWeather(
                "서울",
                morning=PeriodWeather("서울", "맑음", 26, 10),
                afternoon=PeriodWeather("서울", "비", 31, 90),
            ),
            CityWeather(
                "부산",
                morning=PeriodWeather("부산", "흐림", 25, 65),
                afternoon=PeriodWeather("부산", "소나기", 29, 80),
            ),
        ],
    )

    reply = format_national_weather(weather)

    assert "【 오늘 전국 날씨 】" in reply
    assert "기준: 7/14(화) · 전국 대표 2개 지역" in reply
    assert "[오전]" in reply
    assert "기온: 25~26°C" in reply
    assert "비 가능성 높은 곳: 부산 65%" in reply
    assert "[오후]" in reply
    assert "비 가능성 높은 곳: 서울 90%, 부산 80%" in reply
    assert "출처: Open-Meteo" in reply


@pytest.mark.anyio
async def test_weather_client_parses_open_meteo_payload(monkeypatch) -> None:
    client = KoreaWeatherClient(
        locations=[
            WeatherLocation("서울", 37.5665, 126.9780),
            WeatherLocation("부산", 35.1796, 129.0756),
        ],
        cache_ttl_seconds=60,
    )

    def payload(codes: list[int], temps: list[float], probs: list[int]) -> dict:
        return {
            "hourly": {
                "time": [f"2026-07-14T{hour:02d}:00" for hour in range(24)],
                "weather_code": codes,
                "temperature_2m": temps,
                "precipitation_probability": probs,
            }
        }

    async def fake_fetch_forecast():
        return [
            payload([1] * 12 + [63] * 12, [25.0] * 12 + [31.0] * 12, [10] * 12 + [90] * 12),
            payload([3] * 12 + [80] * 12, [24.0] * 12 + [29.0] * 12, [40] * 12 + [75] * 12),
        ]

    monkeypatch.setattr(client, "_fetch_forecast", fake_fetch_forecast)

    weather = await client.get_today(datetime(2026, 7, 14, 10, 0, tzinfo=KST))

    assert [city.location for city in weather.cities] == ["서울", "부산"]
    assert weather.cities[0].morning.condition == "대체로 맑음"
    assert weather.cities[0].afternoon.condition == "비"
    assert weather.cities[1].afternoon.condition == "약한 소나기"
