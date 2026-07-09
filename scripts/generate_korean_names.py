from __future__ import annotations

import csv
import json
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Any

import httpx


POGO_STATS_URL = "https://pogoapi.net/api/v1/pokemon_stats.json"
POKEAPI_NAMES_URL = (
    "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
    "pokemon_species_names.csv"
)

OUTPUT_PATH = Path("app/data/korean_names.json")


def normalize_alias(value: str) -> str:
    return value.strip()


def merge_aliases(existing: list[str], additions: list[str]) -> list[str]:
    seen = set()
    merged: list[str] = []
    for alias in [*existing, *additions]:
        normalized = normalize_alias(alias)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


def load_pogo_species() -> dict[int, str]:
    response = httpx.get(POGO_STATS_URL, timeout=30)
    response.raise_for_status()
    records: list[dict[str, Any]] = response.json()

    species: dict[int, str] = {}
    for record in records:
        pokemon_id = int(record.get("pokemon_id") or record["id"])
        name = record.get("pokemon_name") or record["name"]
        species.setdefault(pokemon_id, name)
    return dict(sorted(species.items()))


def load_korean_species_names() -> dict[int, str]:
    response = httpx.get(POKEAPI_NAMES_URL, timeout=30)
    response.raise_for_status()

    names: dict[int, str] = {}
    reader = csv.DictReader(StringIO(response.text))
    for row in reader:
        if row["local_language_id"] == "3":
            names[int(row["pokemon_species_id"])] = row["name"]
    return names


def build_mapping() -> dict[str, list[str]]:
    pogo_species = load_pogo_species()
    korean_names = load_korean_species_names()
    mapping: dict[str, list[str]] = {}

    for pokemon_id, english_name in pogo_species.items():
        aliases: list[str] = []
        korean_name = korean_names.get(pokemon_id)
        if korean_name:
            aliases.append(normalize_alias(korean_name))

        mapping[english_name] = merge_aliases([], aliases)

    manual_aliases: dict[str, list[str]] = {
        "Pikachu": ["피카"],
        "Rayquaza": ["레쿠자"],
        "Giratina": ["기라티나 어나더", "기라티나 오리진"],
    }
    for english_name, aliases in manual_aliases.items():
        if english_name not in mapping:
            continue
        mapping[english_name] = merge_aliases(mapping[english_name], aliases)

    return mapping


def find_duplicate_aliases(mapping: dict[str, list[str]]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = defaultdict(list)
    for english_name, aliases in mapping.items():
        for alias in aliases:
            owners[alias].append(english_name)
    return {
        alias: names
        for alias, names in sorted(owners.items())
        if len(names) > 1
    }


def main() -> None:
    mapping = build_mapping()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    duplicates = find_duplicate_aliases(mapping)
    print(f"Wrote {OUTPUT_PATH} with {len(mapping)} Pokemon names.")
    if duplicates:
        print(f"Found {len(duplicates)} duplicate Korean aliases:")
        for alias, names in list(duplicates.items())[:20]:
            print(f"- {alias}: {', '.join(names)}")


if __name__ == "__main__":
    main()
