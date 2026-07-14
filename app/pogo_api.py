from __future__ import annotations

import json
import re
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.cp import FALLBACK_CPM, calculate_cp, perfect_cp_table, rank1_iv
from app.localization import ko_form, ko_move, ko_type, ko_weather
from app.name_map import NameResolver, ResolvedPokemon


BASE_URL = "https://pogoapi.net/api/v1"
CACHE_DIR = Path(".cache") / "pogoapi"
CACHE_TTL_SECONDS = 60 * 60 * 24
# 원본 API 장애로 만료된 캐시를 임시로 계속 쓸 때의 재시도 간격.
STALE_RETRY_SECONDS = 60 * 5


class PogoDataUnavailableError(RuntimeError):
    """pogoapi.net에 접근할 수 없고 쓸 수 있는 캐시도 없을 때."""


class MegaUnavailableError(LookupError):
    """포켓몬은 있지만 해당 메가진화가 포켓몬GO에 아직 없을 때."""


# 포켓몬GO에는 출시됐지만 pogoapi 반영이 늦는 메가를 임시로 보충한다.
# 원본 데이터에 같은 mega_name이 생기면 원본이 우선한다.
# 스탯 출처: pokebase.app (최대 CP 역산으로 검증: X 6910, Y 7267)
MEGA_SUPPLEMENTS = [
    {
        "mega_name": "Mega Mewtwo X",
        "pokemon_id": 150,
        "pokemon_name": "Mewtwo",
        "stats": {"base_attack": 399, "base_defense": 215, "base_stamina": 228},
        "type": ["Psychic", "Fighting"],
    },
    {
        "mega_name": "Mega Mewtwo Y",
        "pokemon_id": 150,
        "pokemon_name": "Mewtwo",
        "stats": {"base_attack": 413, "base_defense": 223, "base_stamina": 228},
        "type": ["Psychic"],
    },
]
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
    # (한글 타입명, 배율) 목록. 배율이 큰 약점(2중 약점)이 먼저 온다.
    weakness_details: list[tuple[str, float]] = field(default_factory=list)
    recommended_fast_move: str | None = None
    recommended_charged_move: str | None = None


class PogoApiClient:
    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.name_resolver = NameResolver()
        self._client: httpx.AsyncClient | None = None
        # endpoint -> (만료 시각, 파싱된 데이터). 디스크/네트워크는 만료 후에만 접근한다.
        self._memory_cache: dict[str, tuple[float, Any]] = {}
        # endpoint -> 소문자 이름 -> 레코드 목록. 데이터가 갱신되면 버린다.
        self._name_indexes: dict[str, dict[str, list[dict[str, Any]]]] = {}

    async def get_dex_entry(self, query: str) -> PokemonDexEntry:
        resolved = await self._resolve_number_query(query)
        if resolved is None:
            resolved = self.name_resolver.resolve_query(query)
        if resolved.mega or resolved.form == "Primal":
            return await self._get_mega_entry(resolved)
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
        recommended_fast_move, recommended_charged_move = await self._recommend_moves(
            moves,
            pokemon_types,
        )
        weakness_details, resistances = self._calculate_matchups(
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
            weaknesses=[name for name, _ in weakness_details],
            resistances=resistances,
            weather_boosts=self._weather_for_types(pokemon_types, weather_boosts),
            weakness_details=weakness_details,
            recommended_fast_move=recommended_fast_move,
            recommended_charged_move=recommended_charged_move,
        )

    async def _resolve_number_query(self, query: str) -> ResolvedPokemon | None:
        """'42', '002', '487 오리진', '487오리진'처럼 번호로 시작하는 조회를 해석한다."""
        matched = re.match(r"(\d+)\s*(.*)", query.strip())
        if matched is None:
            return None

        dex_id = int(matched.group(1))
        records = await self._fetch_json("pokemon_stats.json")
        names = {
            self._record_name(item)
            for item in records
            if int(item.get("pokemon_id", 0)) == dex_id
        }
        if not names:
            return None

        form = None
        form_text = matched.group(2).strip()
        if form_text:
            form = self.name_resolver.resolve_form(form_text)
            if form is None:
                # 폼 표현을 못 알아들으면 번호 해석을 포기하고
                # 이름 해석 쪽에서 실패 안내가 나가게 한다.
                return None
        return ResolvedPokemon(name=next(iter(names)), form=form)

    async def _get_mega_entry(self, resolved: ResolvedPokemon) -> PokemonDexEntry:
        records = await self._fetch_json("mega_pokemon.json")
        known_names = {item["mega_name"] for item in records}
        records = list(records) + [
            item for item in MEGA_SUPPLEMENTS if item["mega_name"] not in known_names
        ]
        matches = [
            item
            for item in records
            if item["pokemon_name"].lower() == resolved.name.lower()
        ]
        if not matches:
            raise MegaUnavailableError(f"Mega Pokemon not found: {resolved.name}")

        if resolved.form == "Primal":
            matches = [
                item
                for item in matches
                if item["mega_name"].lower().startswith("primal ")
            ]
            if not matches:
                raise MegaUnavailableError(f"Primal Pokemon not found: {resolved.name}")
        else:
            matches = [
                item
                for item in matches
                if item["mega_name"].lower().startswith("mega ")
            ]
            if not matches:
                raise MegaUnavailableError(f"Mega Pokemon not found: {resolved.name}")

        if resolved.mega_variant:
            variant_suffix = f" {resolved.mega_variant.lower()}"
            matches = [
                item
                for item in matches
                if item["mega_name"].lower().endswith(variant_suffix)
            ]
            if not matches:
                raise MegaUnavailableError(
                    f"Mega form not found: {resolved.name} {resolved.mega_variant}"
                )

        # 리자몽/뮤츠처럼 X와 Y가 있는데 변형을 지정하지 않으면 X를 보여준다.
        mega = sorted(matches, key=lambda item: item["mega_name"])[0]
        moves = await self._find_by_name(
            "current_pokemon_moves.json",
            resolved.name,
        )
        cpm_by_level = await self._get_cp_multipliers()
        type_effectiveness = await self._fetch_json("type_effectiveness.json")
        weather_boosts = await self._fetch_json("weather_boosts.json")

        pokemon_types = mega.get("type", [])
        recommended_fast_move, recommended_charged_move = await self._recommend_moves(
            moves,
            pokemon_types,
        )
        weakness_details, resistances = self._calculate_matchups(
            pokemon_types,
            type_effectiveness,
        )
        stats = mega["stats"]
        base_attack = int(stats["base_attack"])
        base_defense = int(stats["base_defense"])
        base_stamina = int(stats["base_stamina"])

        return PokemonDexEntry(
            id=int(mega["pokemon_id"]),
            name=mega["pokemon_name"],
            display_name=self.name_resolver.display_name(resolved.name),
            form=self._mega_form(mega["mega_name"], mega["pokemon_name"]),
            types=pokemon_types,
            base_attack=base_attack,
            base_defense=base_defense,
            base_stamina=base_stamina,
            fast_moves=moves.get("fast_moves", []),
            charged_moves=moves.get("charged_moves", []),
            elite_fast_moves=moves.get("elite_fast_moves", []),
            elite_charged_moves=moves.get("elite_charged_moves", []),
            perfect_cps=perfect_cp_table(
                base_attack,
                base_defense,
                base_stamina,
                cpm_by_level,
            ),
            weaknesses=[name for name, _ in weakness_details],
            resistances=resistances,
            weather_boosts=self._weather_for_types(pokemon_types, weather_boosts),
            weakness_details=weakness_details,
            recommended_fast_move=recommended_fast_move,
            recommended_charged_move=recommended_charged_move,
        )

    @staticmethod
    def _mega_form(mega_name: str, pokemon_name: str) -> str:
        if mega_name.lower().startswith("primal "):
            return "Primal"
        variant = mega_name.replace("Mega", "").replace(pokemon_name, "").strip()
        return f"Mega_{variant.upper()}" if variant else "Mega"

    async def _fetch_json(self, endpoint: str) -> Any:
        now = time.time()
        cached = self._memory_cache.get(endpoint)
        if cached and now < cached[0]:
            return cached[1]

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / endpoint
        disk_mtime: float | None = None
        if cache_path.exists():
            disk_mtime = cache_path.stat().st_mtime
            if now - disk_mtime < CACHE_TTL_SECONDS:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                self._store(endpoint, data, expires_at=disk_mtime + CACHE_TTL_SECONDS)
                return data

        try:
            data = await self._download(endpoint)
        except (httpx.HTTPError, OSError) as error:
            # 원본 API 장애 시에는 만료된 캐시라도 계속 서비스하고,
            # 잠시 후에만 재다운로드를 시도한다.
            stale = cached[1] if cached else None
            if stale is None and disk_mtime is not None:
                stale = json.loads(cache_path.read_text(encoding="utf-8"))
            if stale is not None:
                self._store(endpoint, stale, expires_at=now + STALE_RETRY_SECONDS)
                return stale
            raise PogoDataUnavailableError(endpoint) from error

        cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._store(endpoint, data, expires_at=now + CACHE_TTL_SECONDS)
        return data

    async def _download(self, endpoint: str) -> Any:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20)
        response = await self._client.get(f"{BASE_URL}/{endpoint}")
        response.raise_for_status()
        return response.json()

    def _store(self, endpoint: str, data: Any, expires_at: float) -> None:
        self._memory_cache[endpoint] = (expires_at, data)
        self._name_indexes.pop(endpoint, None)

    def _name_index(self, endpoint: str, records: Any) -> dict[str, list[dict[str, Any]]]:
        index = self._name_indexes.get(endpoint)
        if index is None:
            index = {}
            for item in records:
                index.setdefault(self._record_name(item).lower(), []).append(item)
            self._name_indexes[endpoint] = index
        return index

    async def _find_by_name(
        self,
        endpoint: str,
        name: str,
        form: str | None = None,
    ) -> dict[str, Any]:
        records = await self._fetch_json(endpoint)
        matches = self._name_index(endpoint, records).get(name.lower(), [])
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
    ) -> tuple[list[tuple[str, float]], list[str]]:
        weaknesses: list[tuple[str, float]] = []
        resistances: list[str] = []
        for attack_type, defenders in type_effectiveness.items():
            multiplier = 1.0
            for defender_type in defender_types:
                multiplier *= float(defenders.get(defender_type, 1))
            if multiplier > 1:
                weaknesses.append((ko_type(attack_type), multiplier))
            elif multiplier < 1:
                resistances.append(ko_type(attack_type))
        weaknesses.sort(key=lambda item: item[1], reverse=True)
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

    async def _recommend_moves(
        self,
        moves: dict[str, Any],
        pokemon_types: list[str],
    ) -> tuple[str | None, str | None]:
        fast_names = _unique_moves(
            moves.get("fast_moves", []) + moves.get("elite_fast_moves", [])
        )
        charged_names = _unique_moves(
            moves.get("charged_moves", []) + moves.get("elite_charged_moves", [])
        )
        if not fast_names or not charged_names:
            return None, None

        try:
            fast_stats = _move_index(await self._fetch_json("fast_moves.json"))
            charged_stats = _move_index(await self._fetch_json("charged_moves.json"))
        except Exception:
            return None, None

        best_pair: tuple[str, str] | None = None
        best_score = -1.0
        for fast_name in fast_names:
            fast_move = fast_stats.get(fast_name)
            if not fast_move:
                continue
            for charged_name in charged_names:
                charged_move = charged_stats.get(charged_name)
                if not charged_move:
                    continue
                score = _raid_cycle_score(fast_move, charged_move, pokemon_types)
                if score > best_score:
                    best_pair = (fast_name, charged_name)
                    best_score = score

        return best_pair if best_pair else (None, None)


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
            elite_lines.append(f"노말: {_format_move_list(entry.elite_fast_moves)}")
        if entry.elite_charged_moves:
            elite_lines.append(f"스페셜: {_format_move_list(entry.elite_charged_moves)}")

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


def format_moves_reply(entry: PokemonDexEntry) -> str:
    number = f"No.{entry.id:03d}"
    korean_name = entry.display_name if entry.display_name else entry.name
    english_name = entry.name
    form_name = ko_form(entry.form) if not _is_default_form(entry.form) else ""
    if form_name:
        korean_name = f"{korean_name} ({form_name})"
    if entry.form and not _is_default_form(entry.form):
        english_name = f"{english_name} ({entry.form.replace('_', ' ')})"

    lines = [
        f"{number} {korean_name} / {english_name}",
        "[ 기술 ]",
    ]
    if entry.fast_moves:
        lines.append(f"노말: {_format_move_list(entry.fast_moves)}")
    if entry.charged_moves:
        lines.append(f"스페셜: {_format_move_list(entry.charged_moves)}")
    if entry.elite_fast_moves or entry.elite_charged_moves:
        lines.append("")
        lines.append("[ 레거시/대기머 기술 ]")
        if entry.elite_fast_moves:
            lines.append(f"노말: {_format_move_list(entry.elite_fast_moves)}")
        if entry.elite_charged_moves:
            lines.append(f"스페셜: {_format_move_list(entry.elite_charged_moves)}")
    if entry.recommended_fast_move and entry.recommended_charged_move:
        lines.append("")
        lines.append("[ 추천스킬 ]")
        fast_move = _format_recommended_move(entry.recommended_fast_move, entry)
        charged_move = _format_recommended_move(entry.recommended_charged_move, entry)
        lines.append(f"레이드: {fast_move} + {charged_move}")
    return "\n".join(lines)


def _format_move_list(moves: list[str]) -> str:
    return " / ".join(ko_move(move) for move in moves)


def _format_recommended_move(move: str, entry: PokemonDexEntry) -> str:
    label = ko_move(move)
    elite_moves = set(entry.elite_fast_moves + entry.elite_charged_moves)
    if move in elite_moves:
        label = f"{label}(대기머)"
    return label


def _unique_moves(moves: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for move in moves:
        if move and move not in seen:
            seen.add(move)
            unique.append(move)
    return unique


def _move_index(records: Any) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("name")): item
        for item in records
        if isinstance(item, dict) and item.get("name")
    }


def _raid_cycle_score(
    fast_move: dict[str, Any],
    charged_move: dict[str, Any],
    pokemon_types: list[str],
) -> float:
    fast_energy = max(int(fast_move.get("energy_delta") or 0), 1)
    charged_cost = abs(int(charged_move.get("energy_delta") or 0)) or 50
    fast_count = max(math.ceil(charged_cost / fast_energy), 1)

    fast_duration = max(float(fast_move.get("duration") or 0) / 1000, 0.5)
    charged_duration = max(float(charged_move.get("duration") or 0) / 1000, 0.5)
    total_duration = fast_count * fast_duration + charged_duration
    if total_duration <= 0:
        return 0

    fast_power = float(fast_move.get("power") or 0)
    charged_power = float(charged_move.get("power") or 0)
    fast_damage = fast_count * fast_power * _stab_multiplier(fast_move, pokemon_types)
    charged_damage = charged_power * _stab_multiplier(charged_move, pokemon_types)
    score = (fast_damage + charged_damage) / total_duration

    fast_type = fast_move.get("type")
    charged_type = charged_move.get("type")
    if fast_type == charged_type and fast_type in pokemon_types:
        score *= 1.15
    elif charged_type in pokemon_types:
        score *= 1.05
    return score


def _stab_multiplier(move: dict[str, Any], pokemon_types: list[str]) -> float:
    return 1.2 if move.get("type") in pokemon_types else 1.0


def format_weakness_reply(entry: PokemonDexEntry) -> str:
    form_name = ko_form(entry.form) if not _is_default_form(entry.form) else ""
    form = f" ({form_name})" if form_name else ""
    return (
        f"[{entry.display_name}] #{entry.id:03d}{form}\n"
        f"타입: {', '.join(ko_type(type_name) for type_name in entry.types)}\n"
        f"약점: {', '.join(entry.weaknesses) or '없음'}\n"
        f"저항: {', '.join(entry.resistances) or '없음'}"
    )


LEAGUE_CAPS = [("슈퍼리그", 1500), ("하이퍼리그", 2500)]


def format_league_reply(entry: PokemonDexEntry) -> str:
    form_name = ko_form(entry.form) if not _is_default_form(entry.form) else ""
    form = f" ({form_name})" if form_name else ""
    lines = [f"[{entry.display_name}] #{entry.id:03d}{form} 리그 랭크1"]
    for league, cap in LEAGUE_CAPS:
        rank = rank1_iv(
            entry.base_attack,
            entry.base_defense,
            entry.base_stamina,
            cap,
        )
        lines.append(
            f"{league}: {rank.attack_iv}/{rank.defense_iv}/{rank.stamina_iv}"
            f" Lv{rank.level:g} CP {rank.cp}"
        )
    master_cp = calculate_cp(
        entry.base_attack,
        entry.base_defense,
        entry.base_stamina,
        50,
    )
    lines.append(f"마스터리그: 15/15/15 Lv50 CP {master_cp}")
    return "\n".join(lines)


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
