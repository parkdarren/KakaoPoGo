from app.counters import TYPE_COUNTERS, format_counter_reply
from app.name_map import NameResolver
from app.pogo_api import PokemonDexEntry


def test_every_counter_pick_resolves_to_a_real_pokemon() -> None:
    resolver = NameResolver()

    for type_name, picks in TYPE_COUNTERS.items():
        for pick in picks:
            resolved = resolver.resolve_query(pick)
            assert resolved.name.isascii(), (
                f"카운터 추천 '{pick}' ({type_name})이 포켓몬으로 해석되지 않습니다."
            )


def test_counter_reply_orders_double_weakness_first() -> None:
    entry = PokemonDexEntry(
        id=6,
        name="Charizard",
        display_name="리자몽",
        form="Mega_Y",
        types=["Fire", "Flying"],
        base_attack=319,
        base_defense=212,
        base_stamina=186,
        fast_moves=[],
        charged_moves=[],
        elite_fast_moves=[],
        elite_charged_moves=[],
        perfect_cps={},
        weaknesses=["바위", "전기", "물"],
        resistances=[],
        weather_boosts=[],
        weakness_details=[("바위", 2.56), ("전기", 1.6), ("물", 1.6)],
    )

    reply = format_counter_reply(entry)
    lines = reply.split("\n")

    assert lines[0] == "No.006 리자몽 (메가 Y) 카운터"
    assert lines[1] == "약점: 바위 / 전기 / 물"
    assert "바위(x2): 램펄드 / 메가디안시 / 테라키온" in reply
    assert "전기: 제크로무" in reply
    assert reply.index("바위(x2)") < reply.index("전기:")


def test_counter_reply_without_weakness() -> None:
    entry = PokemonDexEntry(
        id=999,
        name="Test",
        display_name="테스트몬",
        form=None,
        types=["Normal"],
        base_attack=1,
        base_defense=1,
        base_stamina=1,
        fast_moves=[],
        charged_moves=[],
        elite_fast_moves=[],
        elite_charged_moves=[],
        perfect_cps={},
        weaknesses=[],
        resistances=[],
        weather_boosts=[],
    )

    assert "약점이 없는 포켓몬입니다." in format_counter_reply(entry)
