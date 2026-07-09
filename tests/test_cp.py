from app.cp import calculate_cp, perfect_cp_table


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
