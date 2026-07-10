from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.bot import PokemonGoBot
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
            "quickReplies": [
                {"label": "도움말", "action": "message", "messageText": "/도움말"},
                {"label": "도감", "action": "message", "messageText": "/도감 피카츄"},
                {"label": "스킬", "action": "message", "messageText": "/스킬 피카츄"},
                {"label": "100 CP", "action": "message", "messageText": "/100 디아루가"},
            ],
        },
    }


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
    utterance = str(request.userRequest.get("utterance") or "").strip()
    if utterance:
        return utterance

    params = request.action.get("params") or {}
    for value in params.values():
        text = str(value or "").strip()
        if text:
            return text
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
