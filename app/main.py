from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.bot import PokemonGoBot, parse_command
from app.pogo_api import PogoApiClient, format_dex_reply


def _verify_bridge_key(x_bridge_key: str | None = Header(default=None)) -> None:
    # BRIDGE_KEY가 설정된 서버에서는 같은 키를 아는 브리지만 명령을 보낼 수 있다.
    # 로컬 개발처럼 키가 없으면 인증을 건너뛴다.
    bridge_key = os.getenv("BRIDGE_KEY", "").strip()
    if not bridge_key:
        return
    if x_bridge_key != bridge_key:
        raise HTTPException(status_code=403, detail="invalid bridge key")


app = FastAPI(title="KakaoPoGo Bot", version="0.1.0")
bot = PokemonGoBot()
pogo = PogoApiClient()

KAKAO_CHANNEL_ALLOWED_COMMANDS = {
    "help",
    "dex",
    "moves",
    "perfect",
    "weakness",
    "counter",
    "cp",
    "league",
}
KAKAO_CHANNEL_HELP_ENTRIES = [
    (
        "/도감 포켓몬이름",
        "포켓몬 타입, 약점, 100% CP를 확인합니다.\n"
        "예시 : /도감 디아루가, /도감 화이트큐레무",
    ),
    (
        "/스킬 포켓몬이름",
        "포켓몬GO 기술을 한글명으로 확인합니다.\n"
        "예시 : /스킬 피카츄, /스킬 블랙큐레무",
    ),
    (
        "/100 포켓몬이름",
        "100% 개체값 CP만 빠르게 확인합니다.\n"
        "예시 : /100 자시안 검왕",
    ),
    (
        "/약점 포켓몬이름",
        "타입, 약점, 저항을 확인합니다.\n"
        "예시 : /약점 기라티나 오리진",
    ),
    (
        "/카운터 포켓몬이름",
        "레이드 상대할 때 좋은 카운터 포켓몬을 확인합니다.\n"
        "예시 : /카운터 뮤츠",
    ),
    (
        "/cp 포켓몬이름 레벨 공격/방어/체력",
        "원하는 레벨과 IV의 CP를 계산합니다.\n"
        "예시 : /cp 피카츄 40 15/15/15",
    ),
    (
        "/리그 포켓몬이름",
        "슈퍼/하이퍼리그 랭크1 개체값을 확인합니다.\n"
        "예시 : /리그 마릴리",
    ),
]


class CommandRequest(BaseModel):
    text: str
    room: str = "local"
    sender: str = "local"
    user_key: str | None = None


class KakaoSkillRequest(BaseModel):
    userRequest: dict[str, Any] = Field(default_factory=dict)
    bot: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "KakaoPoGo Bot",
        "try": "POST /command with {'text': '/도감 피카츄'}",
        "kakao_skill": "POST /kakao/skill",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _is_silent_message(text: str) -> bool:
    return not text.strip().startswith("/")


def _silent_response() -> dict[str, Any]:
    return {"reply": "", "silent": True}


def _reply_response(reply: str) -> dict[str, Any]:
    return {"reply": reply, "silent": False}


def _kakao_simple_text_response(reply: str) -> dict[str, Any]:
    chunks = _split_kakao_text(reply)
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": chunk}} for chunk in chunks],
        },
    }


def _kakao_channel_help() -> str:
    lines = ["【 포켓몬GO 정보 명령어 】", "━━━━━━━━━━━━━━━━"]
    for index, (command, description) in enumerate(KAKAO_CHANNEL_HELP_ENTRIES, start=1):
        lines.append(f"{index}. {command}")
        for line in description.splitlines():
            lines.append(f"└ {line}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _kakao_channel_restricted_reply() -> str:
    return (
        "카카오톡 채널에서는 포켓몬GO 정보 조회만 지원합니다.\n"
        "/도움말 을 입력하면 사용할 수 있는 명령어를 볼 수 있습니다."
    )


def _split_kakao_text(text: str) -> list[str]:
    max_chunk_size = 1000
    max_chunks = 3
    trimmed_notice = "\n\n(응답이 길어 일부만 표시했습니다.)"
    remaining = text.strip() or "응답할 내용이 없습니다."
    chunks: list[str] = []
    while remaining and len(chunks) < max_chunks:
        if len(remaining) <= max_chunk_size:
            chunks.append(remaining)
            remaining = ""
            break
        split_at = remaining.rfind("\n\n", 0, max_chunk_size)
        if split_at < max_chunk_size // 2:
            split_at = remaining.rfind("\n", 0, max_chunk_size)
        if split_at < max_chunk_size // 2:
            split_at = max_chunk_size
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining and chunks:
        chunks[-1] = (chunks[-1][: max_chunk_size - len(trimmed_notice)] + trimmed_notice).rstrip()
    return chunks or ["응답할 내용이 없습니다."]


def _extract_kakao_skill_text(request: KakaoSkillRequest) -> str:
    param_texts: list[str] = []
    detail_params = request.action.get("detailParams") or {}
    for value in detail_params.values():
        if isinstance(value, dict):
            for key in ("origin", "value"):
                text = str(value.get(key) or "").strip()
                if text:
                    param_texts.append(text)

    params = request.action.get("params") or {}
    for value in params.values():
        text = str(value or "").strip()
        if text:
            param_texts.append(text)

    for text in param_texts:
        if text.startswith("/"):
            return text

    utterance = str(request.userRequest.get("utterance") or "").strip()
    if utterance and utterance != "발화 내용":
        return utterance

    if param_texts:
        return param_texts[0]
    return ""


def _extract_kakao_user(request: KakaoSkillRequest) -> tuple[str, str | None]:
    user = request.userRequest.get("user") or {}
    user_id = str(user.get("id") or "kakao-channel-user").strip()
    sender = user_id or "kakao-channel-user"
    return sender, f"kakao:{sender}" if sender else None


def _extract_kakao_room(request: KakaoSkillRequest) -> str:
    bot_info = request.bot or {}
    bot_name = str(bot_info.get("name") or "").strip()
    bot_id = str(bot_info.get("id") or "").strip()
    room_key = bot_id or bot_name or "default"
    return f"kakao-channel:{room_key}"


@app.post("/command", dependencies=[Depends(_verify_bridge_key)])
async def command(request: CommandRequest) -> dict[str, Any]:
    if _is_silent_message(request.text):
        return _silent_response()

    response = await bot.handle(
        request.text,
        room=request.room,
        sender=request.sender,
        user_key=request.user_key,
    )
    return _reply_response(response.reply)


@app.get("/command", dependencies=[Depends(_verify_bridge_key)])
async def command_get(
    text: str,
    room: str = "local",
    sender: str = "local",
    user_key: str | None = None,
) -> dict[str, Any]:
    if _is_silent_message(text):
        return _silent_response()

    response = await bot.handle(text, room=room, sender=sender, user_key=user_key)
    return _reply_response(response.reply)


@app.post("/kakao/skill")
async def kakao_skill(request: KakaoSkillRequest) -> dict[str, Any]:
    text = _extract_kakao_skill_text(request)
    if _is_silent_message(text):
        reply = "명령어는 /로 시작해 주세요.\n예: /도감 피카츄"
        return _kakao_simple_text_response(reply)

    parsed = parse_command(text)
    if parsed is None:
        return _kakao_simple_text_response(_kakao_channel_restricted_reply())

    command, _query = parsed
    if command == "help":
        return _kakao_simple_text_response(_kakao_channel_help())

    if command not in KAKAO_CHANNEL_ALLOWED_COMMANDS:
        return _kakao_simple_text_response(_kakao_channel_restricted_reply())

    sender, user_key = _extract_kakao_user(request)
    response = await bot.handle(
        text,
        room=_extract_kakao_room(request),
        sender=sender,
        user_key=user_key,
    )
    return _kakao_simple_text_response(response.reply)


@app.get("/dex/{name}", dependencies=[Depends(_verify_bridge_key)])
async def dex(name: str) -> dict[str, object]:
    entry = await pogo.get_dex_entry(name)
    return {
        "id": entry.id,
        "name": entry.name,
        "display_name": entry.display_name,
        "form": entry.form,
        "types": entry.types,
        "base_stats": {
            "attack": entry.base_attack,
            "defense": entry.base_defense,
            "stamina": entry.base_stamina,
        },
        "perfect_cps": entry.perfect_cps,
        "weaknesses": entry.weaknesses,
        "resistances": entry.resistances,
        "weather_boosts": entry.weather_boosts,
        "fast_moves": entry.fast_moves,
        "charged_moves": entry.charged_moves,
        "reply": format_dex_reply(entry),
    }
