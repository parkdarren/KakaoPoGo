from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

import httpx


POGO_MOVES_URL = "https://pogoapi.net/api/v1/current_pokemon_moves.json"
POKEAPI_CSV_BASE = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv"
OUTPUT_PATH = Path("app/data/korean_moves.json")

MOVE_IDENTIFIER_OVERRIDES = {
    "Aura Wheel Electric": "aura-wheel",
    "Aura Wheel Dark": "aura-wheel",
    "Futuresight": "future-sight",
    "Super Power": "superpower",
}

MOVE_NAME_OVERRIDES = {
    "Aura Wheel Electric": "오라휠(전기)",
    "Aura Wheel Dark": "오라휠(악)",
    "Techno Blast Burn": "테크노버스터(불꽃)",
    "Techno Blast Chill": "테크노버스터(얼음)",
    "Techno Blast Normal": "테크노버스터(노말)",
    "Techno Blast Shock": "테크노버스터(전기)",
    "Techno Blast Water": "테크노버스터(물)",
    "Weather Ball Fire": "웨더볼(불꽃)",
    "Weather Ball Ice": "웨더볼(얼음)",
    "Weather Ball Normal": "웨더볼(노말)",
    "Weather Ball Rock": "웨더볼(바위)",
    "Weather Ball Water": "웨더볼(물)",
}


def move_identifier(move_name: str) -> str:
    if move_name in MOVE_IDENTIFIER_OVERRIDES:
        return MOVE_IDENTIFIER_OVERRIDES[move_name]
    return (
        move_name.lower()
        .replace(" ", "-")
        .replace(".", "")
        .replace("'", "")
        .replace(":", "")
    )


def load_pogo_move_names() -> list[str]:
    response = httpx.get(POGO_MOVES_URL, timeout=30)
    response.raise_for_status()
    records: list[dict[str, Any]] = response.json()

    moves: set[str] = set()
    for record in records:
        for key in (
            "fast_moves",
            "charged_moves",
            "elite_fast_moves",
            "elite_charged_moves",
        ):
            moves.update(record.get(key) or [])
    return sorted(moves)


def load_pokeapi_move_ids() -> dict[str, int]:
    response = httpx.get(f"{POKEAPI_CSV_BASE}/moves.csv", timeout=30)
    response.raise_for_status()
    reader = csv.DictReader(StringIO(response.text))
    return {row["identifier"]: int(row["id"]) for row in reader}


def load_pokeapi_korean_names() -> dict[int, str]:
    response = httpx.get(f"{POKEAPI_CSV_BASE}/move_names.csv", timeout=30)
    response.raise_for_status()
    reader = csv.DictReader(StringIO(response.text))
    return {
        int(row["move_id"]): row["name"]
        for row in reader
        if row["local_language_id"] == "3"
    }


def build_mapping() -> dict[str, str]:
    move_names = load_pogo_move_names()
    id_by_identifier = load_pokeapi_move_ids()
    korean_by_id = load_pokeapi_korean_names()

    mapping: dict[str, str] = {}
    missing: list[str] = []
    for move_name in move_names:
        if move_name in MOVE_NAME_OVERRIDES:
            mapping[move_name] = MOVE_NAME_OVERRIDES[move_name]
            continue

        identifier = move_identifier(move_name)
        move_id = id_by_identifier.get(identifier)
        korean_name = korean_by_id.get(move_id) if move_id else None
        if korean_name:
            mapping[move_name] = korean_name
        else:
            missing.append(move_name)

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing Korean move names: {joined}")
    return mapping


def main() -> None:
    mapping = build_mapping()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH} with {len(mapping)} Korean move names.")


if __name__ == "__main__":
    main()
