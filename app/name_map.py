from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DATA_PATH = Path(__file__).parent / "data" / "korean_names.json"
EXTRA_ALIASES = {
    "디아": "Dialga",
    "디아루": "Dialga",
    "루가": "Dialga",
    "alg": "Dialga",
    "dialg": "Dialga",
}
FORM_ALIASES = {
    "Normal": ["노말", "일반", "기본", "normal"],
    "Hero": ["역전의용사", "히어로", "hero"],
    "Crowned_sword": ["검왕", "왕의검", "검왕폼", "crownedsword", "crowned sword"],
    "Crowned_shield": ["방패왕", "왕의방패", "방패왕폼", "crownedshield", "crowned shield"],
    "Black": ["블랙", "흑", "black"],
    "White": ["화이트", "백", "white"],
    "Altered": ["어나더", "어나더폼", "altered"],
    "Origin": ["오리진", "오리진폼", "origin"],
    "Dawn_wings": ["새벽의날개", "새벽의 날개", "dawnwings", "dawn wings"],
    "Dusk_mane": ["황혼의갈기", "황혼의 갈기", "duskmane", "dusk mane"],
    "Ice_rider": ["백마", "백마 탄 모습", "아이스라이더", "ice rider"],
    "Shadow_rider": ["흑마", "흑마 탄 모습", "섀도라이더", "shadow rider"],
    "Midday": ["한낮", "한낮의모습", "midday"],
    "Midnight": ["한밤중", "한밤중의모습", "midnight"],
    "Dusk": ["황혼", "황혼의모습", "dusk"],
    "Land": ["랜드", "랜드폼", "land"],
    "Sky": ["스카이", "스카이폼", "sky"],
    "Confined": ["굴레에빠진", "굴레", "confined"],
    "Unbound": ["굴레를벗어난", "굴레벗어난", "unbound"],
    "Alola": ["알로라", "알로라폼", "alola"],
    "Galarian": ["가라르", "가라르폼", "galar", "galarian"],
    "Hisuian": ["히스이", "히스이폼", "hisui", "hisuian"],
    "Paldea": ["팔데아", "팔데아폼", "paldea"],
    "Paldea_aqua": ["팔데아 워터", "팔데아 물", "paldea aqua"],
    "Paldea_blaze": ["팔데아 블레이즈", "팔데아 불꽃", "paldea blaze"],
    "Paldea_combat": ["팔데아 컴뱃", "팔데아 격투", "paldea combat"],
    "Therian": ["영물", "영물폼", "therian"],
    "Incarnate": ["화신", "화신폼", "incarnate"],
    "Armored": ["아머드", "armored"],
    "Defense": ["디펜스", "방어", "defense"],
    "Attack": ["어택", "공격", "attack"],
    "Speed": ["스피드", "speed"],
    "Plant": ["초목", "plant"],
    "Sandy": ["모래땅", "sandy"],
    "Trash": ["슈레", "쓰레기", "trash"],
    "Overcast": ["포지", "overcast"],
    "Sunshine": ["체리", "sunshine"],
    "Baile": ["이글이글", "baile"],
    "Pompom": ["파칙파칙", "pompom", "pom pom"],
    "Pau": ["훌라훌라", "pau"],
    "Sensu": ["하늘하늘", "sensu"],
    "Douse": ["워시", "세탁기", "douse"],
    "Frost": ["프로스트", "냉장고", "frost"],
    "Heat": ["히트", "오븐", "heat"],
    "Mow": ["커트", "잔디깎이", "mow"],
    "Wash": ["워시", "세탁기", "wash"],
    "East_sea": ["동쪽바다", "동쪽 바다", "east sea"],
    "West_sea": ["서쪽바다", "서쪽 바다", "west sea"],
    "Red_striped": ["적색근", "빨간줄무늬", "red striped"],
    "Blue_striped": ["청색근", "파란줄무늬", "blue striped"],
    "Single_strike": ["일격", "일격의태세", "single strike"],
    "Rapid_strike": ["연격", "연격의태세", "rapid strike"],
    "Amped": ["하이한", "amped"],
    "Low_key": ["로우한", "low key"],
    "Full_belly": ["만복", "만복모양", "full belly"],
    "Hangry": ["꼬르륵", "꼬르륵모양", "hangry"],
}


def _normalize(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )


@dataclass(frozen=True)
class ResolvedPokemon:
    name: str
    form: str | None = None


class NameResolver:
    def __init__(self, path: Path = DATA_PATH) -> None:
        self.path = path
        self.display_names: dict[str, str] = {}
        self.aliases = self._load_aliases()
        for alias, canonical in EXTRA_ALIASES.items():
            self.aliases[_normalize(alias)] = canonical
        self.form_aliases = self._load_form_aliases()

    def _load_aliases(self) -> dict[str, str]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        aliases: dict[str, str] = {}
        for canonical, values in raw.items():
            self.display_names[canonical] = values[0] if values else canonical
            aliases[_normalize(canonical)] = canonical
            for value in values:
                aliases[_normalize(value)] = canonical
        return aliases

    def resolve(self, query: str) -> str:
        return self.resolve_query(query).name

    def display_name(self, canonical_name: str) -> str:
        return self.display_names.get(canonical_name, canonical_name)

    def resolve_query(self, query: str) -> ResolvedPokemon:
        normalized = _normalize(query)
        by_name = self._resolve_name_then_form(normalized)
        if by_name:
            return by_name

        by_form = self._resolve_form_then_name(normalized)
        if by_form:
            return by_form

        exact_name = self.aliases.get(normalized)
        if exact_name:
            return ResolvedPokemon(exact_name)

        partial_name = self._resolve_partial_name(normalized)
        if partial_name:
            return ResolvedPokemon(partial_name)

        return ResolvedPokemon(query.strip())

    @staticmethod
    def _load_form_aliases() -> dict[str, str]:
        aliases: dict[str, str] = {}
        for form, values in FORM_ALIASES.items():
            aliases[_normalize(form)] = form
            for value in values:
                aliases[_normalize(value)] = form
        return aliases

    def _resolve_name_then_form(self, normalized_query: str) -> ResolvedPokemon | None:
        for alias, name in self._aliases_by_length():
            if not normalized_query.startswith(alias):
                continue
            form_text = normalized_query[len(alias) :]
            form = self.form_aliases.get(form_text)
            if form:
                return ResolvedPokemon(name=name, form=form)
        return None

    def _resolve_form_then_name(self, normalized_query: str) -> ResolvedPokemon | None:
        for form_alias, form in sorted(
            self.form_aliases.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if not normalized_query.startswith(form_alias):
                continue
            name_text = normalized_query[len(form_alias) :]
            name = self.aliases.get(name_text)
            if name:
                return ResolvedPokemon(name=name, form=form)
        return None

    def _aliases_by_length(self) -> list[tuple[str, str]]:
        return sorted(
            self.aliases.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    def _resolve_partial_name(self, normalized_query: str) -> str | None:
        if len(normalized_query) < 2:
            return None

        matched_names = {
            name
            for alias, name in self.aliases.items()
            if alias.startswith(normalized_query) or normalized_query in alias
        }
        if len(matched_names) == 1:
            return next(iter(matched_names))
        return None
