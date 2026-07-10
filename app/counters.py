from __future__ import annotations

from app.localization import ko_form
from app.pogo_api import PokemonDexEntry


# 타입별 대표 레이드 어태커. 순서는 추천 순위이며 방에서 실제로 많이 쓰는
# 조합 위주로 고른 수동 관리 목록이다. 메타가 바뀌면 여기를 고치면 된다.
TYPE_COUNTERS: dict[str, list[str]] = {
    "불꽃": ["메가리자몽Y", "레시라무", "리자몽"],
    "물": ["가이오가", "메가갸라도스", "대짱이"],
    "전기": ["제크로무", "메가전룡", "라이코"],
    "풀": ["메가이상해꽃", "로즈레이드", "토대부기"],
    "얼음": ["메가눈설왕", "블랙큐레무", "맘모꾸리"],
    "격투": ["테라키온", "루카리오", "괴력몬"],
    "독": ["메가독침붕", "텅비드", "로즈레이드"],
    "땅": ["그란돈", "메가한카리아스", "한카리아스"],
    "비행": ["메가레쿠쟈", "메가보만다", "레쿠쟈"],
    "에스퍼": ["뮤츠", "메가후딘", "라티오스"],
    "벌레": ["메가쁘사이저", "게노세크트", "페로코체"],
    "바위": ["램펄드", "메가디안시", "테라키온"],
    "고스트": ["메가팬텀", "오리진 기라티나", "팬텀"],
    "드래곤": ["메가레쿠쟈", "오리진 디아루가", "보만다"],
    "악": ["메가마기라스", "다크라이", "메가헬가"],
    "강철": ["검왕 자시안", "메타그로스", "디아루가"],
    "페어리": ["제르네아스", "메가디안시", "토게키스"],
}

# pogoapi 상성 배율은 1.6이라 2중 약점이면 1.6 * 1.6 = 2.56이 된다.
DOUBLE_WEAKNESS_THRESHOLD = 2.0


def format_counter_reply(entry: PokemonDexEntry) -> str:
    korean_name = entry.display_name if entry.display_name else entry.name
    form_name = ko_form(entry.form) if (entry.form or "").lower() not in ("", "normal") else ""
    if form_name:
        korean_name = f"{korean_name} ({form_name})"

    details = entry.weakness_details or [(name, 0.0) for name in entry.weaknesses]
    if not details:
        return f"No.{entry.id:03d} {korean_name}\n약점이 없는 포켓몬입니다."

    lines = [
        f"No.{entry.id:03d} {korean_name} 카운터",
        f"약점: {' / '.join(name for name, _ in details)}",
        "",
        "[ 추천 카운터 ]",
    ]
    for type_name, multiplier in details:
        picks = TYPE_COUNTERS.get(type_name)
        if not picks:
            continue
        label = f"{type_name}(x2)" if multiplier >= DOUBLE_WEAKNESS_THRESHOLD else type_name
        lines.append(f"{label}: {' / '.join(picks)}")
    return "\n".join(lines)
