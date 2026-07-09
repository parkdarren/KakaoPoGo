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
    "Altered": "어나더",
    "Origin": "오리진",
    "Alola": "알로라",
    "Galarian": "가라르",
    "Hisuian": "히스이",
    "Paldea": "팔데아",
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
}


def ko_type(type_name: str) -> str:
    return TYPE_KO.get(type_name, type_name)


def ko_weather(weather_name: str) -> str:
    return WEATHER_KO.get(weather_name, weather_name)


def ko_form(form_name: str | None) -> str:
    if not form_name:
        return ""
    return FORM_KO.get(form_name, form_name)
