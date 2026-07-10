from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

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


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "KakaoPoGo Bot",
        "try": "POST /command with {'text': '/도감 피카츄'}",
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
