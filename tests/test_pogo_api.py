import os
import time

import httpx
import pytest

from app.pogo_api import (
    CACHE_TTL_SECONDS,
    MegaUnavailableError,
    PogoApiClient,
    PogoDataUnavailableError,
    PokemonDexEntry,
    format_dex_reply,
    format_moves_reply,
)


MEGA_FIXTURES = {
    "mega_pokemon.json": [
        {
            "mega_name": "Mega Charizard X",
            "pokemon_id": 6,
            "pokemon_name": "Charizard",
            "stats": {"base_attack": 273, "base_defense": 213, "base_stamina": 186},
            "type": ["Fire", "Dragon"],
        },
        {
            "mega_name": "Mega Charizard Y",
            "pokemon_id": 6,
            "pokemon_name": "Charizard",
            "stats": {"base_attack": 319, "base_defense": 212, "base_stamina": 186},
            "type": ["Fire", "Flying"],
        },
        {
            "mega_name": "Primal Kyogre",
            "pokemon_id": 382,
            "pokemon_name": "Kyogre",
            "stats": {"base_attack": 353, "base_defense": 268, "base_stamina": 218},
            "type": ["Water"],
        },
        {
            "mega_name": "Primal Groudon",
            "pokemon_id": 383,
            "pokemon_name": "Groudon",
            "stats": {"base_attack": 353, "base_defense": 268, "base_stamina": 218},
            "type": ["Ground", "Fire"],
        },
    ],
    "current_pokemon_moves.json": [
        {
            "pokemon_name": "Charizard",
            "form": "Normal",
            "fast_moves": ["Fire Spin"],
            "charged_moves": ["Blast Burn"],
            "elite_fast_moves": [],
            "elite_charged_moves": [],
        },
        {
            "pokemon_name": "Mewtwo",
            "form": "Normal",
            "fast_moves": ["Confusion"],
            "charged_moves": ["Psystrike"],
            "elite_fast_moves": [],
            "elite_charged_moves": [],
        },
        {
            "pokemon_name": "Kyogre",
            "form": "Normal",
            "fast_moves": ["Waterfall"],
            "charged_moves": ["Surf"],
            "elite_fast_moves": [],
            "elite_charged_moves": ["Origin Pulse"],
        },
        {
            "pokemon_name": "Groudon",
            "form": "Normal",
            "fast_moves": ["Mud Shot"],
            "charged_moves": ["Earthquake"],
            "elite_fast_moves": [],
            "elite_charged_moves": ["Precipice Blades"],
        },
    ],
    "type_effectiveness.json": {},
    "weather_boosts.json": {},
}


NUMBER_FIXTURES = {
    "pokemon_stats.json": [
        {"pokemon_id": 1, "pokemon_name": "Bulbasaur", "form": "Normal",
         "base_attack": 118, "base_defense": 111, "base_stamina": 128},
        {"pokemon_id": 487, "pokemon_name": "Giratina", "form": "Altered",
         "base_attack": 187, "base_defense": 225, "base_stamina": 284},
        {"pokemon_id": 487, "pokemon_name": "Giratina", "form": "Origin",
         "base_attack": 225, "base_defense": 187, "base_stamina": 284},
    ],
    "pokemon_types.json": [
        {"pokemon_id": 1, "pokemon_name": "Bulbasaur", "form": "Normal",
         "type": ["Grass", "Poison"]},
        {"pokemon_id": 487, "pokemon_name": "Giratina", "form": "Altered",
         "type": ["Ghost", "Dragon"]},
        {"pokemon_id": 487, "pokemon_name": "Giratina", "form": "Origin",
         "type": ["Ghost", "Dragon"]},
    ],
    "current_pokemon_moves.json": [
        {"pokemon_id": 1, "pokemon_name": "Bulbasaur", "form": "Normal",
         "fast_moves": [], "charged_moves": [],
         "elite_fast_moves": [], "elite_charged_moves": []},
        {"pokemon_id": 487, "pokemon_name": "Giratina", "form": "Altered",
         "fast_moves": [], "charged_moves": [],
         "elite_fast_moves": [], "elite_charged_moves": []},
        {"pokemon_id": 487, "pokemon_name": "Giratina", "form": "Origin",
         "fast_moves": [], "charged_moves": [],
         "elite_fast_moves": [], "elite_charged_moves": []},
    ],
    "type_effectiveness.json": {},
    "weather_boosts.json": {},
}


@pytest.mark.anyio
async def test_dex_lookup_by_pokedex_number(tmp_path, monkeypatch) -> None:
    client = PogoApiClient(cache_dir=tmp_path)

    async def fake_fetch(endpoint: str):
        return NUMBER_FIXTURES[endpoint]

    monkeypatch.setattr(client, "_fetch_json", fake_fetch)

    plain = await client.get_dex_entry("1")
    assert plain.name == "Bulbasaur"

    padded = await client.get_dex_entry("001")
    assert padded.name == "Bulbasaur"

    with_form = await client.get_dex_entry("487 오리진")
    assert with_form.name == "Giratina"
    assert with_form.form == "Origin"

    no_space = await client.get_dex_entry("487오리진")
    assert no_space.form == "Origin"

    default_form = await client.get_dex_entry("487")
    assert default_form.form == "Altered"  # 기본 폼 우선순위

    with pytest.raises(LookupError):
        await client.get_dex_entry("9999")


@pytest.mark.anyio
async def test_mega_dex_entry_uses_mega_stats_and_types(tmp_path, monkeypatch) -> None:
    client = PogoApiClient(cache_dir=tmp_path)

    async def fake_fetch(endpoint: str):
        return MEGA_FIXTURES[endpoint]

    monkeypatch.setattr(client, "_fetch_json", fake_fetch)

    mega_y = await client.get_dex_entry("메가리자몽Y")
    assert mega_y.form == "Mega_Y"
    assert mega_y.types == ["Fire", "Flying"]
    assert mega_y.base_attack == 319
    assert mega_y.fast_moves == ["Fire Spin"]

    default_variant = await client.get_dex_entry("메가리자몽")
    assert default_variant.form == "Mega_X"

    # 메가진화가 없는 포켓몬은 여전히 안내가 나간다.
    with pytest.raises(MegaUnavailableError):
        await client.get_dex_entry("메가피카츄")

    # pogoapi에 아직 없는 메가뮤츠는 보충 데이터로 조회된다.
    mewtwo_y = await client.get_dex_entry("메가뮤츠Y")
    assert mewtwo_y.base_attack == 413
    assert mewtwo_y.types == ["Psychic"]

    mewtwo_default = await client.get_dex_entry("메가뮤츠")
    assert mewtwo_default.form == "Mega_X"
    assert mewtwo_default.types == ["Psychic", "Fighting"]


@pytest.mark.anyio
async def test_primal_dex_entry_uses_primal_stats_and_types(
    tmp_path, monkeypatch
) -> None:
    client = PogoApiClient(cache_dir=tmp_path)

    async def fake_fetch(endpoint: str):
        return MEGA_FIXTURES[endpoint]

    monkeypatch.setattr(client, "_fetch_json", fake_fetch)

    primal_groudon = await client.get_dex_entry("원시그란돈")
    assert primal_groudon.form == "Primal"
    assert primal_groudon.types == ["Ground", "Fire"]
    assert primal_groudon.base_attack == 353
    assert primal_groudon.fast_moves == ["Mud Shot"]
    assert primal_groudon.elite_charged_moves == ["Precipice Blades"]

    primal_kyogre = await client.get_dex_entry("primal kyogre")
    assert primal_kyogre.form == "Primal"
    assert primal_kyogre.types == ["Water"]
    assert primal_kyogre.elite_charged_moves == ["Origin Pulse"]

    with pytest.raises(MegaUnavailableError):
        await client.get_dex_entry("메가그란돈")


@pytest.mark.anyio
async def test_fetch_json_serves_from_memory_after_first_load(tmp_path) -> None:
    client = PogoApiClient(cache_dir=tmp_path)
    cache_file = tmp_path / "pokemon_stats.json"
    cache_file.write_text('[{"pokemon_name": "Pikachu"}]', encoding="utf-8")

    first = await client._fetch_json("pokemon_stats.json")
    cache_file.unlink()
    second = await client._fetch_json("pokemon_stats.json")

    assert first == second == [{"pokemon_name": "Pikachu"}]


@pytest.mark.anyio
async def test_fetch_json_falls_back_to_stale_cache_when_api_is_down(
    tmp_path, monkeypatch
) -> None:
    client = PogoApiClient(cache_dir=tmp_path)
    cache_file = tmp_path / "pokemon_stats.json"
    cache_file.write_text('[{"pokemon_name": "Pikachu"}]', encoding="utf-8")
    expired = time.time() - CACHE_TTL_SECONDS - 100
    os.utime(cache_file, (expired, expired))

    async def failing_download(endpoint: str):
        raise httpx.ConnectError("api down")

    monkeypatch.setattr(client, "_download", failing_download)

    data = await client._fetch_json("pokemon_stats.json")

    assert data == [{"pokemon_name": "Pikachu"}]


@pytest.mark.anyio
async def test_fetch_json_raises_when_api_is_down_and_no_cache(
    tmp_path, monkeypatch
) -> None:
    client = PogoApiClient(cache_dir=tmp_path)

    async def failing_download(endpoint: str):
        raise httpx.ConnectError("api down")

    monkeypatch.setattr(client, "_download", failing_download)

    with pytest.raises(PogoDataUnavailableError):
        await client._fetch_json("pokemon_stats.json")


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


def test_moves_reply_shows_recommended_moves() -> None:
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
        charged_moves=["Discharge", "Thunderbolt"],
        elite_fast_moves=[],
        elite_charged_moves=["Surf"],
        perfect_cps={},
        weaknesses=["땅"],
        resistances=[],
        weather_boosts=["비"],
        recommended_fast_move="Thunder Shock",
        recommended_charged_move="Surf",
    )

    assert format_moves_reply(entry).endswith(
        "\n\n[ 추천스킬 ]\n"
        "레이드: 전기쇼크 + 파도타기(대기머)"
    )


@pytest.mark.anyio
async def test_recommend_moves_uses_raid_cycle_score(tmp_path, monkeypatch) -> None:
    client = PogoApiClient(cache_dir=tmp_path)

    async def fake_fetch(endpoint: str):
        return {
            "fast_moves.json": [
                {
                    "name": "Thunder Shock",
                    "power": 5,
                    "duration": 600,
                    "energy_delta": 8,
                    "type": "Electric",
                },
                {
                    "name": "Quick Attack",
                    "power": 5,
                    "duration": 1000,
                    "energy_delta": 7,
                    "type": "Normal",
                },
            ],
            "charged_moves.json": [
                {
                    "name": "Thunderbolt",
                    "power": 80,
                    "duration": 2500,
                    "energy_delta": -50,
                    "type": "Electric",
                },
                {
                    "name": "Wild Charge",
                    "power": 90,
                    "duration": 2600,
                    "energy_delta": -50,
                    "type": "Electric",
                },
            ],
        }[endpoint]

    monkeypatch.setattr(client, "_fetch_json", fake_fetch)

    recommended = await client._recommend_moves(
        {
            "fast_moves": ["Thunder Shock", "Quick Attack"],
            "charged_moves": ["Thunderbolt", "Wild Charge"],
        },
        ["Electric"],
    )

    assert recommended == ("Thunder Shock", "Wild Charge")


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
