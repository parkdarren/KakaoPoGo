from app.pogo_api import PokemonDexEntry, format_dex_reply, format_moves_reply


def test_dex_reply_uses_compact_cp_format_without_regular_moves() -> None:
    entry = PokemonDexEntry(
        id=483,
        name="Dialga",
        display_name="디아루가",
        form=None,
        types=["Steel", "Dragon"],
        base_attack=275,
        base_defense=211,
        base_stamina=205,
        fast_moves=["Dragon Breath", "Metal Claw"],
        charged_moves=["Draco Meteor", "Iron Head", "Thunder"],
        elite_fast_moves=[],
        elite_charged_moves=[],
        perfect_cps={
            "Lv15 리서치": 1731,
            "Lv20 레이드/알": 2307,
            "Lv25 날씨부스트": 2884,
            "Lv40 최대강화": 4038,
            "Lv50 XL 최대": 4565,
            "Lv51 베스트파트너": 4620,
        },
        weaknesses=["격투", "땅"],
        resistances=[],
        weather_boosts=["눈", "강풍"],
    )

    assert format_dex_reply(entry) == (
        "No.483 디아루가 / Dialga\n"
        "타입: 강철 / 드래곤\n"
        "약점: 격투 / 땅\n"
        "\n"
        "[ 100% CP 계산 ]\n"
        "리서치 Lv15: 1731 CP\n"
        "레이드/알 Lv20: 2307 CP\n"
        "날씨부스트 Lv25: 2884 CP\n"
        "최대 Lv50: 4565 CP"
    )


def test_dex_reply_shows_only_elite_moves_when_available() -> None:
    entry = PokemonDexEntry(
        id=25,
        name="Pikachu",
        display_name="피카츄",
        form=None,
        types=["Electric"],
        base_attack=112,
        base_defense=96,
        base_stamina=111,
        fast_moves=["Thunder Shock"],
        charged_moves=["Thunderbolt"],
        elite_fast_moves=["Present"],
        elite_charged_moves=["Surf"],
        perfect_cps={
            "Lv15 리서치": 402,
            "Lv20 레이드/알": 536,
            "Lv25 날씨부스트": 670,
            "Lv50 XL 최대": 1060,
        },
        weaknesses=["땅"],
        resistances=[],
        weather_boosts=["비"],
    )
    reply = format_dex_reply(entry)

    assert "Thunder Shock" not in reply
    assert "Thunderbolt" not in reply
    assert "[ 레거시/대기머 기술 ]" in reply
    assert "노말: 프레젠트" in reply
    assert "스페셜: 파도타기" in reply


def test_moves_reply_uses_korean_move_names() -> None:
    entry = PokemonDexEntry(
        id=25,
        name="Pikachu",
        display_name="피카츄",
        form=None,
        types=["Electric"],
        base_attack=112,
        base_defense=96,
        base_stamina=111,
        fast_moves=["Thunder Shock", "Quick Attack"],
        charged_moves=["Discharge", "Thunderbolt", "Wild Charge"],
        elite_fast_moves=["Present"],
        elite_charged_moves=["Surf", "Thunder"],
        perfect_cps={},
        weaknesses=["땅"],
        resistances=[],
        weather_boosts=["비"],
    )

    assert format_moves_reply(entry) == (
        "No.025 피카츄 / Pikachu\n"
        "[ 기술 ]\n"
        "노말: 전기쇼크 / 전광석화\n"
        "스페셜: 방전 / 10만볼트 / 와일드볼트\n"
        "\n"
        "[ 레거시/대기머 기술 ]\n"
        "노말: 프레젠트\n"
        "스페셜: 파도타기 / 번개"
    )


def test_dex_reply_translates_elite_moves_to_korean() -> None:
    entry = PokemonDexEntry(
        id=646,
        name="Kyurem",
        display_name="큐레무",
        form=None,
        types=["Dragon", "Ice"],
        base_attack=246,
        base_defense=170,
        base_stamina=245,
        fast_moves=["Dragon Breath", "Steel Wing"],
        charged_moves=["Dragon Claw", "Blizzard", "Draco Meteor"],
        elite_fast_moves=[],
        elite_charged_moves=["Glaciate"],
        perfect_cps={
            "Lv15 리서치": 1531,
            "Lv20 레이드/알": 2041,
            "Lv25 날씨부스트": 2552,
            "Lv50 XL 최대": 4041,
        },
        weaknesses=["격투", "바위", "강철", "드래곤", "페어리"],
        resistances=[],
        weather_boosts=["눈", "강풍"],
    )

    reply = format_dex_reply(entry)

    assert "Glaciate" not in reply
    assert "스페셜: 얼어붙은세계" in reply
