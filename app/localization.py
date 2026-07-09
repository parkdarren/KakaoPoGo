from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data"

TYPE_KO = {
    "Normal": "노말",
    "Fire": "불꽃",
    "Water": "물",
    "Electric": "전기",
    "Grass": "풀",
    "Ice": "얼음",
    "Fighting": "격투",
    "Poison": "독",
    "Ground": "땅",
    "Flying": "비행",
    "Psychic": "에스퍼",
    "Bug": "벌레",
    "Rock": "바위",
    "Ghost": "고스트",
    "Dragon": "드래곤",
    "Dark": "악",
    "Steel": "강철",
    "Fairy": "페어리",
}

WEATHER_KO = {
    "Clear": "맑음",
    "Rainy": "비",
    "Partly Cloudy": "약간구름",
    "Cloudy": "흐림",
    "Windy": "강풍",
    "Snow": "눈",
    "Fog": "안개",
}

FORM_KO = {
    "Normal": "",
    "Hero": "역전의용사",
    "Crowned_sword": "검왕",
    "Crowned_shield": "방패왕",
    "Black": "블랙",
    "White": "화이트",
    "Altered": "어나더",
    "Origin": "오리진",
    "Dawn_wings": "새벽의날개",
    "Dusk_mane": "황혼의갈기",
    "Ice_rider": "백마",
    "Shadow_rider": "흑마",
    "Midday": "한낮",
    "Midnight": "한밤중",
    "Dusk": "황혼",
    "Land": "랜드",
    "Sky": "스카이",
    "Confined": "굴레에빠진",
    "Unbound": "굴레를벗어난",
    "Alola": "알로라",
    "Galarian": "가라르",
    "Hisuian": "히스이",
    "Paldea": "팔데아",
    "Paldea_aqua": "팔데아 워터",
    "Paldea_blaze": "팔데아 블레이즈",
    "Paldea_combat": "팔데아 컴뱃",
    "Therian": "영물",
    "Incarnate": "화신",
    "Armored": "아머드",
    "Defense": "디펜스",
    "Attack": "어택",
    "Speed": "스피드",
    "Plant": "초목",
    "Sandy": "모래땅",
    "Trash": "슈레",
    "Overcast": "포지",
    "Sunshine": "체리",
    "Baile": "이글이글",
    "Pompom": "파칙파칙",
    "Pau": "훌라훌라",
    "Sensu": "하늘하늘",
    "Douse": "워시",
    "Frost": "프로스트",
    "Heat": "히트",
    "Mow": "커트",
    "Wash": "워시",
    "East_sea": "동쪽바다",
    "West_sea": "서쪽바다",
    "Red_striped": "적색근",
    "Blue_striped": "청색근",
    "Single_strike": "일격",
    "Rapid_strike": "연격",
    "Amped": "하이한",
    "Low_key": "로우한",
    "Full_belly": "만복",
    "Hangry": "꼬르륵",
}


def ko_type(type_name: str) -> str:
    return TYPE_KO.get(type_name, type_name)


def ko_weather(weather_name: str) -> str:
    return WEATHER_KO.get(weather_name, weather_name)


def ko_form(form_name: str | None) -> str:
    if not form_name:
        return ""
    return FORM_KO.get(form_name, form_name)


@lru_cache(maxsize=1)
def _load_move_names() -> dict[str, str]:
    path = DATA_DIR / "korean_moves.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ko_move(move_name: str) -> str:
    return _load_move_names().get(move_name, move_name)
