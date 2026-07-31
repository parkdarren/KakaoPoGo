from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).parent / "data"
GITHUB_BASE = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data"
RANKINGS_URL = GITHUB_BASE + "/rankings/all/overall/rankings-{cp}.json"
GAMEMASTER_URL = GITHUB_BASE + "/gamemaster.json"

LEAGUES = {
    "great": {"cp": 1500, "title": "🔵 슈퍼리그 TOP 30"},
    "ultra": {"cp": 2500, "title": "🟡 하이퍼리그 TOP 30"},
    "master": {"cp": 10000, "title": "🟣 마스터리그 TOP 30"},
}
FOOTER = "📌 참고: https://pvpoke.com/rankings/"
RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}

# 폼 이름 → (앞에 붙일 말, 뒤에 붙일 말). 없는 폼은 기본 이름만 쓴다.
FORM_MAP = {
    "Alolan": ("알로라 ", ""),
    "Galarian": ("가라르 ", ""),
    "Hisuian": ("히스이 ", ""),
    "Paldean": ("팔데아 ", ""),
    "Mega": ("메가 ", ""),
    "Mega X": ("메가 ", "X"),
    "Mega Y": ("메가 ", "Y"),
    "White": ("화이트", ""),
    "Black": ("블랙", ""),
    "Origin": ("", " (오리진)"),
    "Altered": ("", ""),
    "Complete Forme": ("", " (퍼펙트폼)"),
    "Crowned Sword": ("", " (검왕)"),
    "Crowned Shield": ("", " (방패왕)"),
    "Dawn Wings": ("", " (새벽의 날개)"),
    "Dusk Mane": ("", " (황혼의 갈기)"),
    "Therian": ("", " (영물폼)"),
}
# 겉모습만 다른 폼 라벨은 이름에서 뺀다.
IGNORE_FORMS = {
    "Busted", "Disguised", "Standard", "Incarnate", "Ordinary", "Aria",
    "Male", "Female", "Average", "Full Belly", "Overcast", "Sunny",
    "Plant", "Sandy", "Trash", "West Sea", "East Sea", "Two Segment",
    "Family of Three", "Normal", "Land",
}


class PvpRankingUnavailableError(RuntimeError):
    pass


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _name_ko(species_name: str, names: dict) -> str:
    forms = re.findall(r"\(([^)]+)\)", species_name)
    base = re.sub(r"\s*\([^)]+\)", "", species_name).strip()
    entry = names.get(base)
    korean = entry[0] if entry else base
    prefix = ""
    suffix = ""
    for form in forms:
        if form == "Shadow" or form in IGNORE_FORMS:
            continue
        if form in FORM_MAP:
            pre, suf = FORM_MAP[form]
            prefix += pre
            suffix += suf
    if "Shadow" in forms:
        prefix = "그림자 " + prefix
    return (prefix + korean + suffix).strip()


def _move_ko(move_id: str, moves: dict, legacy: frozenset) -> str:
    title = " ".join(word.capitalize() for word in move_id.split("_"))
    korean = moves.get(title, title)
    if move_id in legacy:
        korean += "*"
    return korean


def format_rankings(
    title: str,
    entries: list,
    elite: dict,
    names: dict,
    moves: dict,
) -> str:
    lines = [f"{title} (*는 레거시 기술)", ""]
    for index, entry in enumerate(entries[:30], 1):
        species_id = entry.get("speciesId", "")
        korean = _name_ko(entry.get("speciesName", species_id), names)
        legacy = elite.get(species_id, frozenset())
        moveset = " / ".join(
            _move_ko(move_id, moves, legacy) for move_id in entry.get("moveset", [])
        )
        tag = RANK_EMOJI.get(index, f"{index}.")
        lines.append(f"{tag} {korean}")
        lines.append(f"   {moveset}")
    lines.append("")
    lines.append(FOOTER)
    return "\n".join(lines)


class PvpRankingClient:
    def __init__(self, cache_ttl_seconds: int | None = None) -> None:
        self.cache_ttl = cache_ttl_seconds or int(
            os.getenv("PVP_RANKING_CACHE_TTL_SECONDS", "21600")
        )
        self._names = _load_json(DATA_DIR / "korean_names.json")
        self._moves = _load_json(DATA_DIR / "korean_moves.json")
        self._rank_cache: dict[str, tuple[float, str]] = {}
        self._elite: dict | None = None
        self._elite_until = 0.0

    async def format_league(self, league_key: str) -> str:
        config = LEAGUES[league_key]
        now = time.monotonic()
        cached = self._rank_cache.get(league_key)
        if cached and now < cached[0]:
            return cached[1]

        elite = await self._get_elite()
        data = await self._fetch_json(RANKINGS_URL.format(cp=config["cp"]))
        if not isinstance(data, list) or not data:
            raise PvpRankingUnavailableError("empty rankings")

        text = format_rankings(config["title"], data, elite, self._names, self._moves)
        self._rank_cache[league_key] = (now + self.cache_ttl, text)
        return text

    async def _get_elite(self) -> dict:
        now = time.monotonic()
        if self._elite is not None and now < self._elite_until:
            return self._elite
        try:
            gamemaster = await self._fetch_json(GAMEMASTER_URL)
        except PvpRankingUnavailableError:
            # 레거시 표시는 부가 정보라 실패해도 순위는 계속 낸다.
            return self._elite if self._elite is not None else {}
        elite: dict[str, frozenset] = {}
        for pokemon in gamemaster.get("pokemon", []):
            marks = set(pokemon.get("eliteMoves") or [])
            marks.update(pokemon.get("legacyMoves") or [])
            if marks:
                elite[pokemon["speciesId"]] = frozenset(marks)
        self._elite = elite
        self._elite_until = now + self.cache_ttl
        return elite

    @staticmethod
    async def _fetch_json(url: str) -> object:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(url, headers={"User-Agent": "KakaoPoGo"})
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PvpRankingUnavailableError(str(exc)) from exc
