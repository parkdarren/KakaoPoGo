from app.cp import calculate_cp, perfect_cp_table, rank1_iv


def test_pikachu_perfect_cp_table() -> None:
    cps = perfect_cp_table(112, 96, 111)

    assert cps["Lv15 리서치"] == 402
    assert cps["Lv20 레이드/알"] == 536
    assert cps["Lv25 날씨부스트"] == 670
    assert cps["Lv40 최대강화"] == 938
    assert cps["Lv50 XL 최대"] == 1060
    assert cps["Lv51 베스트파트너"] == 1073


def test_cp_minimum_is_ten() -> None:
    assert calculate_cp(1, 1, 1, 1, 0, 0, 0) == 10


def test_azumarill_great_league_rank1() -> None:
    # 마릴리(112/152/225)의 슈퍼리그 랭크1은 XL 시대 기준 0/15/15 Lv45.5다.
    rank = rank1_iv(112, 152, 225, 1500)

    assert (rank.attack_iv, rank.defense_iv, rank.stamina_iv) == (0, 15, 15)
    assert rank.level == 45.5
    assert rank.cp == 1499


def test_rank1_never_exceeds_cap_and_uses_perfect_when_capped() -> None:
    # 피카츄는 만렙 CP가 1500을 못 넘으므로 15/15/15 만렙이 랭크1이다.
    rank = rank1_iv(112, 96, 111, 1500)

    assert rank.cp <= 1500
    assert (rank.attack_iv, rank.defense_iv, rank.stamina_iv) == (15, 15, 15)
    assert rank.level == 51
