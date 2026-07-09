from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.cp import FALLBACK_CPM, calculate_cp, perfect_cp_table
from app.localization import ko_form, ko_type, ko_weather
from app.name_map import NameResolver


BASE_URL = "https://pogoapi.net/api/v1"
CACHE_DIR = Path(".cache") / "pogoapi"
CACHE_TTL_SECONDS = 60 * 60 * 24
FORM_PRIORITY = {
    None: 0,
    "Normal": 0,
    "Hero": 1,
    "Altered": 1,
    "Origin": 2,
}


@dataclass(frozen=True)
class PokemonDexEntry:
    id: int
    name: str
    display_name: str
    form: str | None
    types: list[str]
    base_attack: int
    base_defense: int
    base_stamina: int
    fast_moves: list[str]
    charged_moves: list[str]
    elite_fast_moves: list[str]
    elite_charged_moves: list[str]
    perfect_cps: dict[str, int]
    weaknesses: list[str]
    resistances: list[str]
    weather_boosts: list[str]


class PogoApiClient:
    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.name_resolver = NameResolver()

    async def get_dex_entry(self, query: str) -> PokemonDexEntry:
        resolved = self.name_resolver.resolve_query(query)
        stats = await self._find_by_name(
            "pokemon_stats.json",
            resolved.name,
            resolved.form,
        )
        selected_form = stats.get("form") or resolved.form
        types = await self._find_by_name(
            "pokemon_types.json",
            resolved.name,
            selected_form,
        )
        moves = await self._find_by_name(
            "current_pokemon_moves.json",
            resolved.name,
            selected_form,
        )
        cpm_by_level = await self._get_cp_multipliers()
        type_effectiveness = await self._fetch_json("type_effectiveness.json")
        weather_boosts = await self._fetch_json("weather_boosts.json")

        pokemon_types = types.get("type", [])
        weaknesses, resistances = self._calculate_matchups(
            pokemon_types,
            type_effectiveness,
        )

        base_attack = int(stats["base_attack"])
        base_defense = int(stats["base_defense"])
        base_stamina = int(stats["base_stamina"])
        perfect_cps = perfect_cp_table(
            base_attack,
            base_defense,
            base_stamina,
            cpm_by_level,
        )

        return PokemonDexEntry(
            id=int(stats["pokemon_id"] if "pokemon_id" in stats else stats["id"]),
            name=stats["pokemon_name"] if "pokemon_name" in stats else stats["name"],
            display_name=self.name_resolver.display_name(resolved.name),
            form=stats.get("form") or types.get("form") or moves.get("form"),
            types=pokemon_types,
            base_attack=base_attack,
            base_defense=base_defense,
            base_stamina=base_stamina,
            fast_moves=moves.get("fast_moves", []),
            charged_moves=moves.get("charged_moves", []),
            elite_fast_moves=moves.get("elite_fast_moves", []),
            elite_charged_moves=moves.get("elite_charged_moves", []),
            perfect_cps=perfect_cps,
            weaknesses=weaknesses,
            resistances=resistances,
            weather_boosts=self._weather_for_types(pokemon_types, weather_boosts),
        )

    async def _fetch_json(self, endpoint: str) -> Any:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / endpoint
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < CACHE_TTL_SECONDS:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{BASE_URL}/{endpoint}")
            response.raise_for_status()
            data = response.json()

        cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return data

    async def _find_by_name(
        self,
        endpoint: str,
        name: str,
        form: str | None = None,
    ) -> dict[str, Any]:
        records = await self._fetch_json(endpoint)
        matches = [
            item
            for item in records
            if self._record_name(item).lower() == name.lower()
        ]
        if not matches:
            raise LookupError(f"Pokemon not found: {name}")
        if form:
            form_matches = [
                item
                for item in matches
                if self._normalize_form(item.get("form")) == self._normalize_form(form)
            ]
            if form_matches:
                return form_matches[0]
            raise LookupError(f"Pokemon form not found: {name} {form}")
        return sorted(
            matches,
            key=lambda item: FORM_PRIORITY.get(item.get("form"), 100),
        )[0]

    async def _get_cp_multipliers(self) -> dict[float, float]:
        try:
            records = await self._fetch_json("cp_multiplier.json")
        except Exception:
            return FALLBACK_CPM

        cpm = dict(FALLBACK_CPM)
        for item in records:
            cpm[float(item["level"])] = float(item["multiplier"])
        return cpm

    @staticmethod
    def _record_name(item: dict[str, Any]) -> str:
        return item.get("pokemon_name") or item.get("name") or ""

    @staticmethod
    def _normalize_form(form: str | None) -> str:
        return (form or "").lower().replace(" ", "").replace("_", "").replace("-", "")

    @staticmethod
    def _calculate_matchups(
        defender_types: list[str],
        type_effectiveness: dict[str, dict[str, float]],
    ) -> tuple[list[str], list[str]]:
        weaknesses: list[str] = []
        resistances: list[str] = []
        for attack_type, defenders in type_effectiveness.items():
            multiplier = 1.0
            for defender_type in defender_types:
                multiplier *= float(defenders.get(defender_type, 1))
            if multiplier > 1:
                weaknesses.append(ko_type(attack_type))
            elif multiplier < 1:
                resistances.append(ko_type(attack_type))
        return weaknesses, resistances

    @staticmethod
    def _weather_for_types(
        pokemon_types: list[str],
        weather_boosts: dict[str, list[str]],
    ) -> list[str]:
        matched = []
        for weather, boosted_types in weather_boosts.items():
            if any(type_name in boosted_types for type_name in pokemon_types):
                matched.append(ko_weather(weather))
        return matched


def format_dex_reply(entry: PokemonDexEntry) -> str:
    number = f"No.{entry.id:03d}"
    korean_name = entry.display_name if entry.display_name else entry.name
    english_name = entry.name
    form_name = ko_form(entry.form) if not _is_default_form(entry.form) else ""
    if form_name:
        korean_name = f"{korean_name} ({form_name})"
    if entry.form and not _is_default_form(entry.form):
        english_name = f"{english_name} ({entry.form.replace('_', ' ')})"

    cp_keys = [
        ("리서치 Lv15", "Lv15 리서치"),
        ("레이드/알 Lv20", "Lv20 레이드/알"),
        ("날씨부스트 Lv25", "Lv25 날씨부스트"),
        ("최대 Lv50", "Lv50 XL 최대"),
    ]
    cp_lines = "\n".join(
        f"{label}: {entry.perfect_cps[source_key]} CP"
        for label, source_key in cp_keys
        if source_key in entry.perfect_cps
    )

    elite = entry.elite_fast_moves + entry.elite_charged_moves
    elite_lines: list[str] = []
    if elite:
        elite_lines.extend(["", "[ 레거시/대기머 기술 ]"])
        if entry.elite_fast_moves:
            elite_lines.append(f"노말: {' / '.join(entry.elite_fast_moves)}")
        if entry.elite_charged_moves:
            elite_lines.append(f"스페셜: {' / '.join(entry.elite_charged_moves)}")

    lines = [
        f"{number} {korean_name} / {english_name}",
        f"타입: {' / '.join(ko_type(type_name) for type_name in entry.types)}",
        f"약점: {' / '.join(entry.weaknesses) or '없음'}",
        "",
        "[ 100% CP 계산 ]",
        cp_lines,
    ]
    lines.extend(elite_lines)
    return "\n".join(lines)


def _is_default_form(form: str | None) -> bool:
    return (form or "").lower() in {"", "normal"}


def format_perfect_cp_reply(entry: PokemonDexEntry) -> str:
    form_name = ko_form(entry.form) if not _is_default_form(entry.form) else ""
    form = f" ({form_name})" if form_name else ""
    cp_lines = "\n".join(
        f"{label}: {cp}" for label, cp in entry.perfect_cps.items()
    )
    return (
        f"[{entry.display_name}] #{entry.id:03d}{form}\n"
        "100% IV CP\n"
        f"{cp_lines}"
    )


def format_weakness_reply(entry: PokemonDexEntry) -> str:
    form_name = ko_form(entry.form) if not _is_default_form(entry.form) else ""
    form = f" ({form_name})" if form_name else ""
    return (
        f"[{entry.display_name}] #{entry.id:03d}{form}\n"
        f"타입: {', '.join(ko_type(type_name) for type_name in entry.types)}\n"
        f"약점: {', '.join(entry.weaknesses) or '없음'}\n"
        f"저항: {', '.join(entry.resistances) or '없음'}"
    )


def format_custom_cp_reply(
    entry: PokemonDexEntry,
    level: float,
    attack_iv: int,
    defense_iv: int,
    stamina_iv: int,
) -> str:
    cp = calculate_cp(
        entry.base_attack,
        entry.base_defense,
        entry.base_stamina,
        level,
        attack_iv,
        defense_iv,
        stamina_iv,
    )
    form_name = ko_form(entry.form) if not _is_default_form(entry.form) else ""
    form = f" ({form_name})" if form_name else ""
    return (
        f"[{entry.display_name}] #{entry.id:03d}{form}\n"
        f"Lv{level:g} {attack_iv}/{defense_iv}/{stamina_iv} CP: {cp}"
    )
