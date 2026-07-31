from __future__ import annotations

from app.counters import TYPE_COUNTERS
from app.weather import NationalWeather

# 포켓몬GO 게임 내 날씨와 부스트되는 타입.
POGO_BOOST = {
    "화창": ("☀️", ["풀", "땅", "불꽃"]),
    "비": ("🌧️", ["물", "전기", "벌레"]),
    "구름 조금": ("⛅", ["노말", "바위"]),
    "흐림": ("☁️", ["페어리", "격투", "독"]),
    "바람": ("🌬️", ["드래곤", "에스퍼", "비행"]),
    "눈": ("❄️", ["얼음", "강철"]),
    "안개": ("🌫️", ["악", "고스트"]),
}

# 예보 표현(WEATHER_CODE_KO 값)을 게임 날씨로 옮긴다. 예보에 없는 '바람'은
# 판별할 수 없어 빠진다(게임에서 직접 확인해야 함).
CONDITION_TO_POGO = {
    "맑음": "화창",
    "대체로 맑음": "화창",
    "구름 조금": "구름 조금",
    "흐림": "흐림",
    "안개": "안개",
    "약한 이슬비": "비",
    "이슬비": "비",
    "강한 이슬비": "비",
    "어는 이슬비": "비",
    "강한 어는 이슬비": "비",
    "약한 비": "비",
    "비": "비",
    "강한 비": "비",
    "어는 비": "비",
    "강한 어는 비": "비",
    "약한 소나기": "비",
    "소나기": "비",
    "강한 소나기": "비",
    "뇌우": "비",
    "우박 동반 뇌우": "비",
    "강한 우박 동반 뇌우": "비",
    "약한 눈": "눈",
    "눈": "눈",
    "강한 눈": "눈",
    "눈알": "눈",
    "약한 눈소나기": "눈",
    "눈소나기": "눈",
}


def pogo_weather(condition: str) -> str | None:
    return CONDITION_TO_POGO.get((condition or "").strip())


def format_boost(weather: NationalWeather, city: str = "") -> str:
    """도시별 부스트 타입. 도시를 지정하면 추천 어태커까지 붙인다."""
    city = (city or "").strip()
    if city:
        for entry in weather.cities:
            if entry.location == city:
                return _format_city_detail(entry)
        names = " ".join(entry.location for entry in weather.cities)
        return f"'{city}' 지역은 없어요.\n가능한 지역: {names}"

    lines = ["🌤️ 오늘 날씨 부스트", "━━━━━━━━━━━━━━"]
    for entry in weather.cities:
        period = entry.afternoon or entry.morning
        game = pogo_weather(period.condition)
        if game is None:
            lines.append(f"{entry.location} · {period.condition}")
            continue
        emoji, types = POGO_BOOST[game]
        lines.append(f"{emoji} {entry.location} · {game} → {' '.join(types)}")
    lines.append("")
    lines.append("자세히 → /부스트 서울")
    lines.append("※ 바람은 예보로 알 수 없어 게임에서 확인하세요.")
    return "\n".join(lines)


def _format_city_detail(entry) -> str:
    # PeriodWeather.label 은 도시명이라 시간대 이름은 여기서 붙인다.
    periods = [
        (label, period)
        for label, period in (("오전", entry.morning), ("오후", entry.afternoon))
        if period is not None
    ]
    games = [(label, pogo_weather(period.condition), period) for label, period in periods]
    # 오전·오후가 같은 날씨면 한 번만 보여준다.
    if len(games) == 2 and games[0][1] == games[1][1] and games[0][1] is not None:
        games = [("종일", games[0][1], games[0][2])]

    lines = [f"🌤️ {entry.location} 날씨 부스트", "━━━━━━━━━━━━━━"]
    for label, game, period in games:
        if game is None:
            lines.append(f"[{label}] {period.condition} · 부스트 정보 없음")
            continue
        emoji, types = POGO_BOOST[game]
        lines.append(f"[{label}] {emoji} {game} → {' '.join(types)}")
        for type_name in types:
            attackers = TYPE_COUNTERS.get(type_name)
            if attackers:
                lines.append(f"   {type_name} : {', '.join(attackers)}")
        lines.append("")
    lines.append("부스트되면 그 타입 기술 위력이 오르고")
    lines.append("야생·레이드 포켓몬 레벨도 올라가요.")
    return "\n".join(lines)
