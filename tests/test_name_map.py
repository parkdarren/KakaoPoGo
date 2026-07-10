from app.name_map import NameResolver


def test_korean_name_resolution_for_common_pokemon() -> None:
    resolver = NameResolver()

    assert resolver.resolve("피카츄") == "Pikachu"
    assert resolver.resolve("리자몽") == "Charizard"
    assert resolver.resolve("뮤츠") == "Mewtwo"
    assert resolver.resolve("자시안") == "Zacian"
    assert resolver.resolve("자마젠타") == "Zamazenta"
    assert resolver.resolve("레쿠자") == "Rayquaza"


def test_korean_form_resolution() -> None:
    resolver = NameResolver()

    zacian = resolver.resolve_query("자시안 검왕")
    assert zacian.name == "Zacian"
    assert zacian.form == "Crowned_sword"

    prefixed_zacian = resolver.resolve_query("검왕 자시안")
    assert prefixed_zacian.name == "Zacian"
    assert prefixed_zacian.form == "Crowned_sword"

    zamazenta = resolver.resolve_query("자마젠타 방패왕")
    assert zamazenta.name == "Zamazenta"
    assert zamazenta.form == "Crowned_shield"

    giratina = resolver.resolve_query("기라티나 오리진")
    assert giratina.name == "Giratina"
    assert giratina.form == "Origin"

    white_kyurem = resolver.resolve_query("화이트큐레무")
    assert white_kyurem.name == "Kyurem"
    assert white_kyurem.form == "White"

    black_kyurem = resolver.resolve_query("블랙 큐레무")
    assert black_kyurem.name == "Kyurem"
    assert black_kyurem.form == "Black"

    dusk_mane = resolver.resolve_query("황혼의갈기 네크로즈마")
    assert dusk_mane.name == "Necrozma"
    assert dusk_mane.form == "Dusk_mane"

    moltres = resolver.resolve_query("가라르 파이어")
    assert moltres.name == "Moltres"
    assert moltres.form == "Galarian"


def test_dialga_short_aliases() -> None:
    resolver = NameResolver()

    assert resolver.resolve("디아") == "Dialga"
    assert resolver.resolve("alg") == "Dialga"
    assert resolver.resolve("루가") == "Dialga"


def test_partial_name_picks_first_by_dex_order() -> None:
    resolver = NameResolver()

    # 앞글자 일치 중 도감 번호가 가장 앞선 포켓몬을 고른다.
    assert resolver.resolve("메") == "Ditto"  # 메타몽
    assert resolver.resolve("가디") == "Growlithe"
    # 앞글자 일치(리자몽 계열)가 부분 포함보다 우선한다.
    assert resolver.resolve("리자") == "Charmeleon"  # 리자드


def test_mega_prefix_resolution() -> None:
    resolver = NameResolver()

    mewtwo = resolver.resolve_query("메가뮤츠")
    assert mewtwo.name == "Mewtwo"
    assert mewtwo.mega is True
    assert mewtwo.mega_variant is None

    charizard_y = resolver.resolve_query("메가리자몽Y")
    assert charizard_y.name == "Charizard"
    assert charizard_y.mega is True
    assert charizard_y.mega_variant == "Y"

    # 이름 자체가 '메가'로 시작하는 포켓몬은 메가진화로 오해하지 않는다.
    meganium = resolver.resolve_query("메가니움")
    assert meganium.name == "Meganium"
    assert meganium.mega is False
