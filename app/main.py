from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from app.admin_page import ADMIN_PAGE
from app.admin_store import ChatUser
from app.site_page import SITE_PAGE
from app.bot import PokemonGoBot, normalize_room, parse_command
from app.events import KST, EventDataUnavailableError, format_daily_brief
from app.pogo_api import PogoApiClient, format_dex_reply


def _verify_bridge_key(x_bridge_key: str | None = Header(default=None)) -> None:
    # BRIDGE_KEY가 설정된 서버에서는 같은 키를 아는 브리지만 명령을 보낼 수 있다.
    # 로컬 개발처럼 키가 없으면 인증을 건너뛴다.
    bridge_key = os.getenv("BRIDGE_KEY", "").strip()
    if not bridge_key:
        return
    if x_bridge_key != bridge_key:
        raise HTTPException(status_code=403, detail="invalid bridge key")


class AsciiJSONResponse(Response):
    """비ASCII 문자를 \\uXXXX로 이스케이프해서 내려주는 JSON 응답.

    폰 브리지가 응답을 Jsoup으로 읽는데, Jsoup의 텍스트 정리 과정이
    폭 없는 공백(U+200B) 같은 보이지 않는 문자를 지워버린다. 이스케이프
    형태로 보내면 폰의 JSON.parse 단계에서 온전히 복원된다.
    """

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")


app = FastAPI(title="KakaoPoGo Bot", version="0.1.0")
bot = PokemonGoBot()
pogo = PogoApiClient()
CONTROL_MARK_PATH = Path(__file__).resolve().parent.parent / "assets" / "kakaopogo-control-mark.webp"
_iris_logger = logging.getLogger("iris")
# 아침 브리핑을 보낼 시각(KST)과 확인 주기.
BRIEF_HOUR = int(os.getenv("EVENT_BRIEF_HOUR", "9"))
BRIEF_CHECK_SECONDS = int(os.getenv("EVENT_BRIEF_CHECK_SECONDS", "600"))
MODERATION_TRAIN_CHECK_SECONDS = int(
    os.getenv("MODERATION_TRAIN_CHECK_SECONDS", "600")
)
# 일일랭킹 포인트를 주는 시각(23시 몇 분부터). 확인 주기가 10분이라
# 23:40~24:00 사이에 반드시 한 번은 걸린다.
RANK_AWARD_MINUTE = int(os.getenv("RANK_AWARD_MINUTE", "40"))

KAKAO_CHANNEL_ALLOWED_COMMANDS = {
    "help",
    "dex",
    "moves",
    "perfect",
    "weakness",
    "counter",
    "cp",
    "league",
    "events",
    "weather",
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
    (
        "/포켓몬고이벤트",
        "진행 중인 이벤트, 7일간의 예정 이벤트, 현재 레이드를 확인합니다.\n"
        "예시 : /포켓몬고이벤트, /이벤트",
    ),
    (
        "/날씨",
        "오늘 전국 대표 지역의 오전/오후 날씨를 확인합니다.\n"
        "예시 : /날씨, /전국날씨",
    ),
]


class CommandRequest(BaseModel):
    text: str
    room: str = "local"
    sender: str = "local"
    user_key: str | None = None


class IrisMessageRequest(BaseModel):
    # dolidolih/Iris 웹훅 형식. 카톡 DB에서 복호화한 메시지를 그대로 보낸다.
    # msg=메시지, room=방이름, sender=보낸사람 이름,
    # json=chat_logs 원본 행(user_id·chat_id 등 진짜 고유 ID 포함).
    # 1:1 개인톡방은 room·sender가 null 로 오므로 None 을 허용한다.
    msg: str | None = ""
    room: str | None = ""
    sender: str | None = ""
    json: dict[str, Any] = Field(default_factory=dict)


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


@app.post(
    "/command",
    dependencies=[Depends(_verify_bridge_key)],
    response_class=AsciiJSONResponse,
)
async def command(request: CommandRequest) -> dict[str, Any]:
    # 채팅 랭킹 집계. 명령어는 record_chat 안에서 걸러진다.
    moderation_warning = bot.record_chat(
        request.room, request.sender, request.user_key, request.text
    )
    if _is_silent_message(request.text):
        return _reply_response(moderation_warning) if moderation_warning else _silent_response()

    response = await bot.handle(
        request.text,
        room=request.room,
        sender=request.sender,
        user_key=request.user_key,
    )
    if response.silent:
        return _silent_response()
    return _reply_response(response.reply)


@app.get(
    "/command",
    dependencies=[Depends(_verify_bridge_key)],
    response_class=AsciiJSONResponse,
)
async def command_get(
    text: str,
    room: str = "local",
    sender: str = "local",
    user_key: str | None = None,
) -> dict[str, Any]:
    # 채팅 랭킹 집계. 명령어는 record_chat 안에서 걸러진다.
    moderation_warning = bot.record_chat(room, sender, user_key, text)
    if _is_silent_message(text):
        return _reply_response(moderation_warning) if moderation_warning else _silent_response()

    response = await bot.handle(text, room=room, sender=sender, user_key=user_key)
    if response.silent:
        return _silent_response()
    return _reply_response(response.reply)


def _iris_is_own_message(payload: dict[str, Any]) -> bool:
    # chat_logs 의 v 필드(JSON 문자열)에 isMine 이 들어있다. 봇 계정이
    # 직접 보낸 메시지면 true.
    raw = payload.get("v")
    if not raw:
        return False
    try:
        return bool(json.loads(raw).get("isMine"))
    except (ValueError, TypeError):
        return False


def _iris_user_key(payload: dict[str, Any], sender: str) -> str:
    # Iris는 카톡 DB의 진짜 user_id를 준다. 알림봇의 프로필 hash와 달리
    # 방이 달라도 사람마다 유일하고 오귀속이 없다. 이게 이번 전환의 핵심.
    user_id = str(payload.get("user_id") or "").strip()
    if user_id:
        return f"iris:{user_id}"
    return f"sender:{sender}" if sender else "sender:unknown"


def _iris_message_source_key(payload: dict[str, Any]) -> str:
    """Iris 원본 행에서 재전송에도 변하지 않는 메시지 키를 만든다."""
    chat_id = str(payload.get("chat_id") or "").strip()
    log_id = str(payload.get("_id") or payload.get("id") or "").strip()
    if not chat_id or not log_id:
        return ""
    return f"iris:{chat_id}:{log_id}"


def _parse_iris_feed(payload: dict[str, Any]) -> tuple[int, list[tuple[str, str]]] | None:
    # 입장/퇴장 같은 카톡 시스템 메시지는 type=0 이고 message 가 JSON 이다.
    # 입장(feedType 4)은 members 배열, 퇴장(feedType 2)은 member 하나.
    if str(payload.get("type")) != "0":
        return None
    message = payload.get("message")
    if not message:
        return None
    try:
        data = json.loads(message)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    feed_type = data.get("feedType")
    if feed_type is None:
        return None
    if feed_type == 4:  # 입장
        raw_members = data.get("members") or []
    elif feed_type in (2, 6):  # 2=나감, 6=강퇴
        if data.get("members"):
            raw_members = data.get("members")
        elif data.get("member"):
            raw_members = [data.get("member")]
        else:
            raw_members = []
    else:
        raw_members = []
    members = [
        (str(m.get("userId")), (m.get("nickName") or "").strip())
        for m in raw_members
        if isinstance(m, dict) and m.get("userId") is not None
    ]
    return feed_type, members


# Iris는 웹훅 응답을 답장에 쓰지 않고, 폰의 /reply 를 따로 호출해야 한다.
# VPS는 집 네트워크 뒤의 폰에 직접 닿을 수 없으므로, 답장을 여기에 쌓아두고
# 폰이 바깥으로 폴링해서(GET /iris/outbox) 가져가 자기 /reply 로 보낸다.
_iris_outbox: list[dict[str, str]] = []
_iris_outbox_lock = asyncio.Lock()
_IRIS_OUTBOX_MAX = 500


async def send_daily_briefs(now: datetime | None = None) -> list[str]:
    """알림을 켠 방에 오늘의 이벤트 브리핑을 한 번씩 보낸다.

    이미 오늘 보낸 방은 건너뛴다. 보낸 방 이름 목록을 돌려준다.
    """
    now = now or datetime.now(KST)
    today = now.date().isoformat()
    targets = bot.admin_store.event_notify_targets(today)
    if not targets:
        return []

    try:
        schedule = await bot.event_client.get_schedule()
    except EventDataUnavailableError:
        return []
    brief = format_daily_brief(schedule.events, now=now)

    sent = []
    for room in targets:
        chat_id = bot.admin_store.get_chat_id_for_room(room)
        if not chat_id:
            continue
        # 알릴 내용이 없는 날도 '오늘 보냄'으로 찍어 하루 한 번만 확인한다.
        if brief:
            await _enqueue_iris_reply(chat_id, brief)
            sent.append(room)
        bot.admin_store.mark_event_notify_sent(room, today)
    return sent


async def award_rank_points(now: datetime | None = None) -> list[str]:
    """자정에 일일랭킹이 초기화되기 전에 그날 상위에게 포인트를 준다."""
    now = now or datetime.now(KST)
    today = now.date().isoformat()
    sent = []
    for room in bot.admin_store.rooms_with_chat_on(today):
        if room.startswith("개인톡:"):
            continue
        notice = bot.award_daily_rank_points(room, today)
        if not notice:
            continue
        chat_id = bot.admin_store.get_chat_id_for_room(room)
        if chat_id:
            await _enqueue_iris_reply(chat_id, notice)
        sent.append(room)
    return sent


async def _daily_brief_loop() -> None:
    # 폰이 폴링해 가는 구조라 서버는 정해진 시각 이후에 큐에 넣기만 하면 된다.
    while True:
        try:
            now = datetime.now(KST)
            if now.hour >= BRIEF_HOUR:
                await send_daily_briefs(now)
            # 랭킹 포인트는 날짜가 바뀌기 전에 줘야 그날 순위가 남아 있다.
            if now.hour == 23 and now.minute >= RANK_AWARD_MINUTE:
                await award_rank_points(now)
        except Exception:  # 알림 실패가 봇 전체를 멈추게 두지 않는다.
            _iris_logger.exception("daily brief failed")
        await asyncio.sleep(BRIEF_CHECK_SECONDS)


async def _moderation_learning_loop() -> None:
    while True:
        try:
            if bot.moderation_learning.needs_training():
                await asyncio.to_thread(bot.moderation_learning.train)
        except Exception:
            _iris_logger.exception("moderation training failed")
        await asyncio.sleep(MODERATION_TRAIN_CHECK_SECONDS)


@app.on_event("startup")
async def _start_daily_brief() -> None:
    app.state.daily_brief_task = asyncio.create_task(_daily_brief_loop())
    app.state.moderation_warmup_task = asyncio.create_task(
        asyncio.to_thread(bot.warm_up_chat_analyzer)
    )
    app.state.moderation_learning_task = asyncio.create_task(
        _moderation_learning_loop()
    )


async def _enqueue_iris_reply(chat_id: str, reply: str) -> None:
    if not chat_id or not reply:
        return
    async with _iris_outbox_lock:
        _iris_outbox.append({"type": "text", "room": chat_id, "data": reply})
        # 폰이 오래 죽어 있어도 메모리가 무한정 늘지 않게 오래된 것부터 버린다.
        if len(_iris_outbox) > _IRIS_OUTBOX_MAX:
            del _iris_outbox[: len(_iris_outbox) - _IRIS_OUTBOX_MAX]


@app.post("/iris/{token}", response_class=AsciiJSONResponse)
async def iris_webhook(token: str, request: IrisMessageRequest) -> dict[str, Any]:
    # Iris는 고정 URL로 POST하고 커스텀 헤더를 붙이기 어려우므로,
    # 인증은 URL 경로에 넣은 토큰(BRIDGE_KEY와 동일)으로 한다.
    bridge_key = os.getenv("BRIDGE_KEY", "").strip()
    if bridge_key and token != bridge_key:
        raise HTTPException(status_code=403, detail="invalid iris token")

    text = request.msg or ""
    chat_id = str(request.json.get("chat_id") or "").strip()

    # 봇 자기 메시지(isMine)는 집계·처리하지 않는다. 그래야 랭킹·추첨에서
    # 봇이 빠지고, 봇 답장이 다시 처리되는 무한루프도 막는다.
    if _iris_is_own_message(request.json):
        return {"reply": "", "silent": True, "chat_id": chat_id}

    # 입장/퇴장 같은 피드(시스템) 메시지는 일반 채팅으로 세지 않는다.
    # 입장(feedType 4)은 방별로 카운팅해서 설정된 기준 이상이면 의심 문구를 낸다.
    feed = _parse_iris_feed(request.json)
    if feed is not None:
        feed_type, members = feed
        group_room = (request.room or "").strip()
        if group_room:
            bot.admin_store.touch_room(chat_id, normalize_room(group_room))
            if feed_type == 4 and members:
                warning = bot.handle_member_joins(group_room, members)
                if warning:
                    await _enqueue_iris_reply(chat_id, warning)
                    return {"reply": warning, "silent": False, "chat_id": chat_id}
            elif feed_type in (2, 6) and members:
                # 나가거나 강퇴당한 사람은 들낙 명단에서 빠진다.
                # 강퇴(feedType 6)는 본인 의사가 아니라 다음 복귀를 카운트 면제한다.
                bot.handle_member_leaves(group_room, members, kicked=(feed_type == 6))
        # (임시) 실제 강퇴 feedType 을 확인하기 위한 캡처. 확인되면 제거.
        if feed_type != 4:
            _iris_logger.warning(
                "IRIS_LEAVE_CAPTURE feedType=%s members=%s raw=%s",
                feed_type,
                members,
                json.dumps(request.json, ensure_ascii=False)[:900],
            )
        return {"reply": "", "silent": True, "chat_id": chat_id}

    # 1:1 개인톡방은 room·sender가 없다. room은 chat_id로 고유하게 잡고,
    # sender는 표시용 대체값을 쓴다(식별은 어차피 user_id로 함).
    room = (request.room or "").strip()
    if not room:
        room = f"개인톡:{chat_id}" if chat_id else "local"
    else:
        # 그룹방은 chat_id로 정체를 고정한다. 방 제목이 바뀌었으면
        # 이름 기준 데이터를 새 이름으로 자동 이전한 뒤 이어서 처리한다.
        # 레지스트리도 봇 저장 규칙과 같은 정규화 이름을 써야 조회가 맞는다.
        bot.admin_store.touch_room(chat_id, normalize_room(room))
    sender = (request.sender or "").strip() or "개인톡사용자"
    user_key = _iris_user_key(request.json, sender)

    # 일반 대화 원문은 학습 자료로 방별 보관한다. 명령어·개인톡·봇 메시지·
    # 시스템 메시지는 제외되며, Iris의 chat_id와 _id로 중복을 막는다.
    if request.room and _is_silent_message(text):
        source_key = _iris_message_source_key(request.json)
        if source_key:
            bot.admin_store.record_moderation_corpus(
                source_key,
                normalize_room(room),
                user_key,
                text,
                str(request.json.get("created_at") or ""),
                "live",
            )

    # 채팅 랭킹 집계. 명령어는 record_chat 안에서 걸러진다.
    moderation_warning = bot.record_chat(room, sender, user_key, text)
    # 이미 방에 있는 사람은 첫 활동 때 '입장 1회'로 기준을 잡아둔다. 그래야
    # 추적 시작 전부터 있던 사람도 나갔다 들어오면 자동으로 2회차가 된다.
    member_id = str(request.json.get("user_id") or "").strip()
    if request.room and member_id and sender != "개인톡사용자":
        bot.admin_store.seed_member_present(normalize_room(room), member_id, sender)
    if _is_silent_message(text):
        if moderation_warning:
            await _enqueue_iris_reply(chat_id, moderation_warning)
            return {
                "reply": moderation_warning,
                "silent": False,
                "chat_id": chat_id,
            }
        return {"reply": "", "silent": True, "chat_id": chat_id}

    response = await bot.handle(text, room=room, sender=sender, user_key=user_key)
    if response.silent:
        return {"reply": "", "silent": True, "chat_id": chat_id}

    # 답장을 outbox에 쌓아 폰이 가져가게 한다.
    await _enqueue_iris_reply(chat_id, response.reply)
    return {"reply": response.reply, "silent": False, "chat_id": chat_id}


@app.get("/iris/outbox/{token}")
async def iris_outbox(token: str) -> Response:
    # 폰이 이 엔드포인트를 폴링해서 대기 중인 답장을 가져간다.
    # 각 줄이 폰의 /reply 로 그대로 POST할 수 있는 완성된 JSON 이다(NDJSON).
    bridge_key = os.getenv("BRIDGE_KEY", "").strip()
    if bridge_key and token != bridge_key:
        raise HTTPException(status_code=403, detail="invalid iris token")

    async with _iris_outbox_lock:
        pending = _iris_outbox[:]
        _iris_outbox.clear()

    lines = [
        json.dumps(item, ensure_ascii=True, separators=(",", ":")) for item in pending
    ]
    body = ("\n".join(lines) + "\n") if lines else ""
    return Response(content=body, media_type="application/x-ndjson")


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


class AdminCommandRequest(BaseModel):
    room: str
    command: str
    response: str
    sender: str = "웹관리"
    room_password: str = ""


class RenameRoomRequest(BaseModel):
    old_room: str
    new_room: str
    room_password: str = ""


class RoomPasswordSetRequest(BaseModel):
    room: str
    password: str
    recovery_word: str


class RoomPasswordChangeRequest(BaseModel):
    room: str
    recovery_word: str
    new_password: str


class RoomAdminRequest(BaseModel):
    room: str
    nickname: str = ""
    user_key: str = ""


class RaffleRecipientRequest(BaseModel):
    room: str
    user_key: str


class TokenRaffleRecipientRequest(BaseModel):
    user_key: str
    room_password: str = ""


class RoomSiteIssueRequest(BaseModel):
    room: str
    password: str = ""
    recovery_word: str = ""


class RoomSettingsRequest(BaseModel):
    room: str
    join_alert_threshold: int | None = None
    raffle_weekly_weight_enabled: bool | None = None
    shop_registration_admin_only: bool | None = None
    shop_registration_fee: int | None = None
    shop_registration_deposit: int | None = None
    moderation_observation_enabled: bool | None = None
    moderation_fragment_count: int | None = None
    moderation_fragment_window: int | None = None
    moderation_eums_count: int | None = None
    moderation_fragment_warning_enabled: bool | None = None
    moderation_eums_warning_enabled: bool | None = None


class TokenRoomSettingsRequest(BaseModel):
    join_alert_threshold: int | None = None
    raffle_weekly_weight_enabled: bool | None = None
    shop_registration_admin_only: bool | None = None
    shop_registration_fee: int | None = None
    shop_registration_deposit: int | None = None
    moderation_observation_enabled: bool | None = None
    moderation_fragment_count: int | None = None
    moderation_fragment_window: int | None = None
    moderation_eums_count: int | None = None
    moderation_fragment_warning_enabled: bool | None = None
    moderation_eums_warning_enabled: bool | None = None
    room_password: str = ""


class ModerationReviewRequest(BaseModel):
    room: str = ""
    incident_id: int
    status: str
    room_password: str = ""


def _require_room_password(room: str, password: str) -> None:
    """방 비밀번호가 설정돼 있으면 일치할 때만 통과시킨다."""
    if not bot.admin_store.has_room_password(room):
        return
    if not password or not bot.admin_store.check_room_password(room, password):
        raise HTTPException(status_code=403, detail="방 비밀번호가 올바르지 않습니다.")


def _validate_join_alert_threshold(value: int) -> int:
    if value < 2 or value > 100:
        raise HTTPException(
            status_code=400,
            detail="들낙 안내 기준 횟수는 2회부터 100회 사이로 설정해 주세요.",
        )
    return value


def _validate_shop_registration_cost(value: int, label: str) -> int:
    if value < 0 or value > 1_000_000:
        raise HTTPException(
            status_code=400,
            detail=f"{label}은 0P부터 1,000,000P 사이로 설정해 주세요.",
        )
    return value


def _validate_moderation_settings(
    fragment_count: int, fragment_window: int, eums_count: int
) -> tuple[int, int, int]:
    if not 2 <= fragment_count <= 10:
        raise HTTPException(status_code=400, detail="단타 기준은 2회부터 10회 사이로 설정해 주세요.")
    if not 5 <= fragment_window <= 60:
        raise HTTPException(status_code=400, detail="단타 관찰 시간은 5초부터 60초 사이로 설정해 주세요.")
    if not 1 <= eums_count <= 10:
        raise HTTPException(status_code=400, detail="음슴체 기준은 1회부터 10회 사이로 설정해 주세요.")
    return fragment_count, fragment_window, eums_count


def _save_moderation_settings(
    room: str, request: RoomSettingsRequest | TokenRoomSettingsRequest
) -> None:
    supplied = any(
        value is not None
        for value in (
            request.moderation_observation_enabled,
            request.moderation_fragment_count,
            request.moderation_fragment_window,
            request.moderation_eums_count,
            request.moderation_fragment_warning_enabled,
            request.moderation_eums_warning_enabled,
        )
    )
    if not supplied:
        return
    current = bot.admin_store.get_moderation_settings(room)
    enabled = (
        request.moderation_observation_enabled
        if request.moderation_observation_enabled is not None
        else bool(current["enabled"])
    )
    fragment_count, fragment_window, eums_count = _validate_moderation_settings(
        request.moderation_fragment_count
        if request.moderation_fragment_count is not None
        else int(current["fragment_count"]),
        request.moderation_fragment_window
        if request.moderation_fragment_window is not None
        else int(current["fragment_window"]),
        request.moderation_eums_count
        if request.moderation_eums_count is not None
        else int(current["eums_count"]),
    )
    bot.admin_store.set_moderation_settings(
        room,
        enabled,
        fragment_count,
        fragment_window,
        eums_count,
        request.moderation_fragment_warning_enabled
        if request.moderation_fragment_warning_enabled is not None
        else bool(current["fragment_warning_enabled"]),
        request.moderation_eums_warning_enabled
        if request.moderation_eums_warning_enabled is not None
        else bool(current["eums_warning_enabled"]),
    )


def _room_settings_payload(room: str) -> dict[str, Any]:
    fee, deposit = bot.admin_store.get_shop_registration_costs(room)
    moderation = bot.admin_store.get_moderation_settings(room)
    return {
        "room": room,
        "joinAlertThreshold": bot.admin_store.get_join_alert_threshold(room),
        "raffleWeeklyWeightEnabled": bot.admin_store.is_raffle_weekly_weight_enabled(room),
        "shopRegistrationAdminOnly": bot.admin_store.is_shop_registration_admin_only(room),
        "shopRegistrationFee": fee,
        "shopRegistrationDeposit": deposit,
        "moderationObservationEnabled": moderation["enabled"],
        "moderationFragmentCount": moderation["fragment_count"],
        "moderationFragmentWindow": moderation["fragment_window"],
        "moderationEumsCount": moderation["eums_count"],
        "moderationFragmentWarningEnabled": moderation[
            "fragment_warning_enabled"
        ],
        "moderationEumsWarningEnabled": moderation["eums_warning_enabled"],
        "moderationTrainingCounts": bot.admin_store.moderation_training_counts(room),
        "moderationCorpusStats": bot.admin_store.moderation_corpus_stats(room),
    }


def _raffle_recipient_payload(room: str, query: str = "") -> dict[str, Any]:
    candidates = bot.admin_store.search_raffle_recipient_candidates(room, query)
    recipients = []
    for record in bot.admin_store.raffle_recipient_history(room, limit=30):
        received_date = datetime.strptime(record["received_date"], "%Y-%m-%d").date()
        recipients.append(
            {
                "id": record["id"],
                "nickname": record["display_name"],
                "receivedDate": record["received_date"],
                "excludedUntil": (
                    received_date + timedelta(days=7)
                ).isoformat(),
            }
        )
    return {
        "room": room,
        "candidates": [
            {"nickname": nickname, "userKey": user_key}
            for nickname, user_key in candidates
        ],
        "recipients": recipients,
    }


def _register_raffle_recipient(room: str, user_key: str) -> dict[str, Any]:
    member_names = {
        known_key: nickname
        for nickname, known_key in bot.admin_store.list_room_members(room)
    }
    nickname = member_names.get((user_key or "").strip())
    if not nickname:
        raise HTTPException(
            status_code=404,
            detail="방에서 확인된 사용자가 아닙니다. 닉네임을 다시 검색해 주세요.",
        )
    received_date = datetime.now(KST).date().isoformat()
    recipient_id = bot.admin_store.register_raffle_recipient(
        room, user_key, nickname, received_date
    )
    return {
        "ok": True,
        "id": recipient_id,
        "nickname": nickname,
        "receivedDate": received_date,
    }


@app.get("/ui-assets/kakaopogo-control-mark.webp", include_in_schema=False)
async def control_mark() -> FileResponse:
    return FileResponse(
        CONTROL_MARK_PATH,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page() -> str:
    return ADMIN_PAGE


@app.get("/admin/rooms", dependencies=[Depends(_verify_bridge_key)])
async def admin_rooms() -> list[str]:
    return bot.admin_store.list_custom_rooms()


@app.get("/admin/site-rooms", dependencies=[Depends(_verify_bridge_key)])
async def admin_site_rooms() -> list[dict[str, Any]]:
    # 봇이 속한 모든 방(레지스트리 기준)과 각 방의 구독자용 전용 토큰.
    return [
        {
            "room": name,
            "token": token,
            "hasPassword": bot.admin_store.has_room_password(name),
        }
        for name, token in bot.admin_store.list_rooms()
    ]


@app.post("/admin/site-room", dependencies=[Depends(_verify_bridge_key)])
async def admin_issue_room_site(request: RoomSiteIssueRequest) -> dict[str, Any]:
    room = normalize_room(request.room)
    if not room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")

    token = bot.admin_store.get_site_token_for_room_name(room)
    if not token:
        raise HTTPException(
            status_code=404,
            detail="봇이 확인한 채팅방이 아닙니다. 방에서 메시지를 한 번 보낸 뒤 다시 시도해 주세요.",
        )

    if not bot.admin_store.has_room_password(room):
        password = request.password.strip()
        recovery_word = request.recovery_word.strip()
        if not password or not recovery_word:
            raise HTTPException(
                status_code=400,
                detail="처음 발급할 때는 사이트 비밀번호와 복구 단어를 입력해 주세요.",
            )
        if len(password) < 4:
            raise HTTPException(status_code=400, detail="비밀번호는 4자 이상으로 해주세요.")
        if not bot.admin_store.set_room_password(room, password, recovery_word):
            raise HTTPException(status_code=409, detail="방 비밀번호 설정 상태가 변경되었습니다. 다시 시도해 주세요.")

    return {
        "ok": True,
        "room": room,
        "path": f"/r/{token}",
        "hasPassword": True,
    }


@app.get("/admin/room-members", dependencies=[Depends(_verify_bridge_key)])
async def admin_room_members(room: str, query: str = "") -> list[dict[str, Any]]:
    clean_room = normalize_room(room)
    if not clean_room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")

    admin_keys = {
        user_key
        for _display_name, role, user_key in bot.admin_store.list_admin_records(clean_room)
        if role == "admin"
    }
    members = (
        bot.admin_store.search_room_members(clean_room, query, limit=50)
        if query.strip()
        else bot.admin_store.list_room_members(clean_room)
    )
    return [
        {
            "nickname": nickname,
            "userKey": user_key,
            "isAdmin": user_key in admin_keys,
        }
        for nickname, user_key in members
    ]


@app.get("/admin/raffle-recipients", dependencies=[Depends(_verify_bridge_key)])
async def admin_raffle_recipients(room: str, query: str = "") -> dict[str, Any]:
    clean_room = normalize_room(room)
    if not clean_room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")
    return _raffle_recipient_payload(clean_room, query)


@app.post("/admin/raffle-recipient", dependencies=[Depends(_verify_bridge_key)])
async def admin_register_raffle_recipient(
    request: RaffleRecipientRequest,
) -> dict[str, Any]:
    room = normalize_room(request.room)
    if not room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")
    return _register_raffle_recipient(room, request.user_key)


@app.delete("/admin/raffle-recipient", dependencies=[Depends(_verify_bridge_key)])
async def admin_remove_raffle_recipient(
    room: str, recipient_id: int
) -> dict[str, Any]:
    clean_room = normalize_room(room)
    if not clean_room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")
    removed = bot.admin_store.remove_raffle_recipient(clean_room, recipient_id)
    if not removed:
        raise HTTPException(status_code=404, detail="상품 수령 기록을 찾지 못했습니다.")
    nickname, received_date = removed
    return {"ok": True, "nickname": nickname, "receivedDate": received_date}


@app.get("/admin/room-settings", dependencies=[Depends(_verify_bridge_key)])
async def admin_room_settings(room: str) -> dict[str, Any]:
    clean_room = normalize_room(room)
    if not clean_room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")
    return _room_settings_payload(clean_room)


@app.post("/admin/room-settings", dependencies=[Depends(_verify_bridge_key)])
async def admin_save_room_settings(
    request: RoomSettingsRequest,
) -> dict[str, Any]:
    room = normalize_room(request.room)
    if not room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")
    if (
        request.join_alert_threshold is None
        and request.raffle_weekly_weight_enabled is None
        and request.shop_registration_admin_only is None
        and request.shop_registration_fee is None
        and request.shop_registration_deposit is None
        and request.moderation_observation_enabled is None
        and request.moderation_fragment_count is None
        and request.moderation_fragment_window is None
        and request.moderation_eums_count is None
        and request.moderation_fragment_warning_enabled is None
        and request.moderation_eums_warning_enabled is None
    ):
        raise HTTPException(status_code=400, detail="저장할 설정을 선택해 주세요.")
    if request.join_alert_threshold is not None:
        threshold = _validate_join_alert_threshold(request.join_alert_threshold)
        bot.admin_store.set_join_alert_threshold(room, threshold)
    if request.raffle_weekly_weight_enabled is not None:
        bot.admin_store.set_raffle_weekly_weight_enabled(
            room, request.raffle_weekly_weight_enabled
        )
    if request.shop_registration_admin_only is not None:
        bot.admin_store.set_shop_registration_admin_only(
            room, request.shop_registration_admin_only
        )
    if (
        request.shop_registration_fee is not None
        or request.shop_registration_deposit is not None
    ):
        current_fee, current_deposit = bot.admin_store.get_shop_registration_costs(room)
        fee = _validate_shop_registration_cost(
            request.shop_registration_fee
            if request.shop_registration_fee is not None
            else current_fee,
            "상품 등록 수수료",
        )
        deposit = _validate_shop_registration_cost(
            request.shop_registration_deposit
            if request.shop_registration_deposit is not None
            else current_deposit,
            "상품 등록 보증금",
        )
        bot.admin_store.set_shop_registration_costs(room, fee, deposit)
    _save_moderation_settings(room, request)
    return {"ok": True, **_room_settings_payload(room)}


@app.get("/admin/moderation-incidents", dependencies=[Depends(_verify_bridge_key)])
async def admin_moderation_incidents(
    room: str, status: str = "all"
) -> dict[str, Any]:
    clean_room = normalize_room(room)
    if not clean_room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")
    return {
        "items": bot.admin_store.list_moderation_incidents(clean_room, status),
        "counts": bot.admin_store.moderation_training_counts(clean_room),
        "corpus": bot.admin_store.moderation_corpus_stats(clean_room),
    }


@app.post("/admin/moderation-review", dependencies=[Depends(_verify_bridge_key)])
async def admin_moderation_review(request: ModerationReviewRequest) -> dict[str, Any]:
    room = normalize_room(request.room)
    if not room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")
    if request.status not in {"pending", "confirmed", "dismissed"}:
        raise HTTPException(status_code=400, detail="올바른 판정 상태가 아닙니다.")
    if not bot.admin_store.review_moderation_incident(
        room, request.incident_id, request.status
    ):
        raise HTTPException(status_code=404, detail="관찰 사례를 찾지 못했습니다.")
    if bot.moderation_learning.needs_training():
        asyncio.create_task(asyncio.to_thread(bot.moderation_learning.train))
    return {
        "ok": True,
        "counts": bot.admin_store.moderation_training_counts(room),
        "corpus": bot.admin_store.moderation_corpus_stats(room),
    }


@app.get("/admin/moderation-model", dependencies=[Depends(_verify_bridge_key)])
async def admin_moderation_model() -> dict[str, Any]:
    return bot.moderation_learning.status()


@app.post("/admin/moderation-train", dependencies=[Depends(_verify_bridge_key)])
async def admin_moderation_train() -> dict[str, Any]:
    return await asyncio.to_thread(bot.moderation_learning.train, True)


@app.post("/admin/moderation-rollback", dependencies=[Depends(_verify_bridge_key)])
async def admin_moderation_rollback() -> dict[str, Any]:
    return await asyncio.to_thread(bot.moderation_learning.rollback)


@app.get("/admin/room-admins", dependencies=[Depends(_verify_bridge_key)])
async def admin_room_admins(room: str) -> list[dict[str, Any]]:
    clean_room = normalize_room(room)
    if not clean_room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")

    records = bot.admin_store.list_admin_records(clean_room)
    return [
        {
            "nickname": bot.admin_store.latest_nickname(clean_room, user_key)
            or display_name,
            "userKey": user_key,
            "role": role,
        }
        for display_name, role, user_key in records
        if role == "admin"
    ]


@app.post("/admin/room-admin", dependencies=[Depends(_verify_bridge_key)])
async def admin_add_room_admin(request: RoomAdminRequest) -> dict[str, Any]:
    room = normalize_room(request.room)
    nickname = request.nickname.strip()
    user_key = request.user_key.strip()
    if not room:
        raise HTTPException(status_code=400, detail="대상 방을 선택해 주세요.")

    if not user_key:
        if not nickname:
            raise HTTPException(status_code=400, detail="관리자 닉네임을 입력해 주세요.")
        user_key = bot.admin_store.resolve_user_key_by_nickname(room, nickname) or ""
        if not user_key:
            raise HTTPException(
                status_code=404,
                detail="이 방에서 해당 닉네임을 찾지 못했습니다. 그 사용자가 방에서 채팅한 뒤 다시 시도해 주세요.",
            )

    known_members = {
        known_key: known_name
        for known_name, known_key in bot.admin_store.list_room_members(room)
    }
    nickname = known_members.get(user_key) or nickname
    if not nickname:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾지 못했습니다.")

    existing_role = next(
        (
            role
            for _display_name, role, known_key in bot.admin_store.list_admin_records(room)
            if known_key == user_key
        ),
        None,
    )
    if existing_role == "owner":
        raise HTTPException(status_code=409, detail="owner는 admin으로 변경할 수 없습니다.")

    bot.admin_store.add_admin(
        ChatUser(room=room, sender=nickname, user_key=user_key)
    )
    notification_queued = False
    if existing_role != "admin":
        chat_id = bot.admin_store.get_chat_id_for_room(room)
        if chat_id:
            await _enqueue_iris_reply(
                chat_id, f"{nickname}님이 관리자로 등록되셨습니다."
            )
            notification_queued = True
    return {
        "ok": True,
        "nickname": nickname,
        "userKey": user_key,
        "notificationQueued": notification_queued,
    }


@app.delete("/admin/room-admin", dependencies=[Depends(_verify_bridge_key)])
async def admin_remove_room_admin(room: str, user_key: str) -> dict[str, Any]:
    clean_room = normalize_room(room)
    clean_key = user_key.strip()
    if not clean_room or not clean_key:
        raise HTTPException(status_code=400, detail="대상 방과 관리자를 선택해 주세요.")

    removed = bot.admin_store.remove_admin_by_key(clean_room, clean_key)
    if removed is None:
        raise HTTPException(status_code=404, detail="등록된 관리자가 아닙니다.")
    nickname, role = removed
    if role == "owner":
        raise HTTPException(status_code=409, detail="owner 권한은 이 화면에서 해제할 수 없습니다.")
    return {"ok": True, "nickname": nickname}


@app.get("/admin/commands", dependencies=[Depends(_verify_bridge_key)])
async def admin_list_commands(room: str) -> list[dict[str, Any]]:
    records = bot.admin_store.list_custom_command_records(normalize_room(room))
    return [
        {"command": record.display_command, "length": len(record.response)}
        for record in records
    ]


@app.delete("/admin/command", dependencies=[Depends(_verify_bridge_key)])
async def admin_delete_command(
    room: str,
    command: str,
    password: str = "",
) -> dict[str, Any]:
    normalized = PokemonGoBot._normalize_custom_command(command)
    clean_room = normalize_room(room)
    if not clean_room or not normalized:
        raise HTTPException(status_code=400, detail="방과 명령어 이름을 입력해 주세요.")

    _require_room_password(clean_room, password)
    deleted = bot.admin_store.delete_custom_command(clean_room, normalized)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"'/{normalized}' — 삭제할 명령어가 없습니다. 이름을 확인해 주세요.",
        )
    return {"ok": True, "command": normalized}


@app.get("/admin/command", dependencies=[Depends(_verify_bridge_key)])
async def admin_get_command(room: str, command: str) -> dict[str, Any]:
    normalized = PokemonGoBot._normalize_custom_command(command)
    custom = bot.admin_store.get_custom_command(normalize_room(room), normalized)
    if custom is None:
        return {"found": False}
    return {"found": True, "command": normalized, "response": custom.response}


@app.post("/admin/command", dependencies=[Depends(_verify_bridge_key)])
async def admin_save_command(request: AdminCommandRequest) -> dict[str, Any]:
    room = normalize_room(request.room)
    normalized = PokemonGoBot._normalize_custom_command(request.command)
    response = request.response.strip()
    if not room or not normalized or not response:
        raise HTTPException(status_code=400, detail="방 이름, 명령어, 내용을 모두 입력해 주세요.")
    if normalized in PokemonGoBot._reserved_custom_commands():
        raise HTTPException(status_code=400, detail=f"'{normalized}'는 봇 기본 명령어라 사용할 수 없습니다.")

    _require_room_password(room, request.room_password)
    bot.admin_store.upsert_custom_command(room, normalized, response, request.sender)
    return {"ok": True, "command": normalized, "length": len(response)}


@app.post("/admin/room-password", dependencies=[Depends(_verify_bridge_key)])
async def admin_set_room_password(request: RoomPasswordSetRequest) -> dict[str, Any]:
    room = normalize_room(request.room)
    password = request.password.strip()
    recovery_word = request.recovery_word.strip()
    if not room or not password or not recovery_word:
        raise HTTPException(status_code=400, detail="방, 비밀번호, 복구 단어를 모두 입력해 주세요.")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="비밀번호는 4자 이상으로 해주세요.")

    if not bot.admin_store.set_room_password(room, password, recovery_word):
        raise HTTPException(
            status_code=409,
            detail="이미 비밀번호가 설정된 방입니다. 변경은 복구 단어로 해주세요.",
        )
    return {"ok": True}


@app.post("/admin/room-password/change", dependencies=[Depends(_verify_bridge_key)])
async def admin_change_room_password(
    request: RoomPasswordChangeRequest,
) -> dict[str, Any]:
    room = normalize_room(request.room)
    recovery_word = request.recovery_word.strip()
    new_password = request.new_password.strip()
    if not room or not recovery_word or not new_password:
        raise HTTPException(status_code=400, detail="방, 복구 단어, 새 비밀번호를 모두 입력해 주세요.")
    if len(new_password) < 4:
        raise HTTPException(status_code=400, detail="비밀번호는 4자 이상으로 해주세요.")

    result = bot.admin_store.change_room_password(room, recovery_word, new_password)
    if result == "missing":
        raise HTTPException(status_code=404, detail="이 방에는 설정된 비밀번호가 없습니다. 먼저 설정해 주세요.")
    if result == "wrong":
        raise HTTPException(status_code=403, detail="복구 단어가 올바르지 않습니다.")
    return {"ok": True}


@app.post("/admin/rename-room", dependencies=[Depends(_verify_bridge_key)])
async def admin_rename_room(request: RenameRoomRequest) -> dict[str, Any]:
    old_room = normalize_room(request.old_room)
    new_room = normalize_room(request.new_room)
    if not old_room or not new_room:
        raise HTTPException(status_code=400, detail="옛 이름과 새 이름을 모두 입력해 주세요.")
    if old_room == new_room:
        raise HTTPException(status_code=400, detail="두 이름이 같습니다.")

    _require_room_password(old_room, request.room_password)
    moved = bot.admin_store.migrate_room(old_room, new_room)
    return {"ok": True, **moved}


# ── 방 전용 사이트 (한 링크 = 한 방) ───────────────────────────────
# 토큰이 곧 방 범위다. 토큰으로 chat_id↔현재 방 이름을 서버가 해석하므로
# 방 선택도, 대상방 설정도 없다. 방 제목이 바뀌어도 같은 토큰이 유지된다.
class TokenCommandRequest(BaseModel):
    command: str
    response: str
    sender: str = "웹관리"
    room_password: str = ""


class TokenPasswordSetRequest(BaseModel):
    password: str
    recovery_word: str


class TokenPasswordChangeRequest(BaseModel):
    recovery_word: str
    new_password: str


def _room_for_token(token: str) -> str:
    room = bot.admin_store.get_room_name_by_token(token)
    if not room:
        raise HTTPException(status_code=404, detail="유효하지 않은 링크입니다.")
    return room


@app.get("/r/{token}", response_class=HTMLResponse)
async def site_page(token: str) -> str:
    return SITE_PAGE


@app.get("/r/{token}/info")
async def site_info(token: str) -> dict[str, Any]:
    room = _room_for_token(token)
    return {"room": room, "hasPassword": bot.admin_store.has_room_password(room)}


@app.get("/r/{token}/commands")
async def site_commands(token: str) -> list[dict[str, Any]]:
    room = _room_for_token(token)
    records = bot.admin_store.list_custom_command_records(room)
    return [
        {"command": record.display_command, "length": len(record.response)}
        for record in records
    ]


@app.get("/r/{token}/room-settings")
async def site_room_settings(token: str) -> dict[str, Any]:
    room = _room_for_token(token)
    return _room_settings_payload(room)


@app.post("/r/{token}/room-settings")
async def site_save_room_settings(
    token: str, request: TokenRoomSettingsRequest
) -> dict[str, Any]:
    room = _room_for_token(token)
    _require_room_password(room, request.room_password)
    if (
        request.join_alert_threshold is None
        and request.raffle_weekly_weight_enabled is None
        and request.shop_registration_admin_only is None
        and request.shop_registration_fee is None
        and request.shop_registration_deposit is None
        and request.moderation_observation_enabled is None
        and request.moderation_fragment_count is None
        and request.moderation_fragment_window is None
        and request.moderation_eums_count is None
        and request.moderation_fragment_warning_enabled is None
        and request.moderation_eums_warning_enabled is None
    ):
        raise HTTPException(status_code=400, detail="저장할 설정을 선택해 주세요.")
    if request.join_alert_threshold is not None:
        threshold = _validate_join_alert_threshold(request.join_alert_threshold)
        bot.admin_store.set_join_alert_threshold(room, threshold)
    if request.raffle_weekly_weight_enabled is not None:
        bot.admin_store.set_raffle_weekly_weight_enabled(
            room, request.raffle_weekly_weight_enabled
        )
    if request.shop_registration_admin_only is not None:
        bot.admin_store.set_shop_registration_admin_only(
            room, request.shop_registration_admin_only
        )
    if (
        request.shop_registration_fee is not None
        or request.shop_registration_deposit is not None
    ):
        current_fee, current_deposit = bot.admin_store.get_shop_registration_costs(room)
        fee = _validate_shop_registration_cost(
            request.shop_registration_fee
            if request.shop_registration_fee is not None
            else current_fee,
            "상품 등록 수수료",
        )
        deposit = _validate_shop_registration_cost(
            request.shop_registration_deposit
            if request.shop_registration_deposit is not None
            else current_deposit,
            "상품 등록 보증금",
        )
        bot.admin_store.set_shop_registration_costs(room, fee, deposit)
    _save_moderation_settings(room, request)
    return {"ok": True, **_room_settings_payload(room)}


@app.get("/r/{token}/raffle-recipients")
async def site_raffle_recipients(
    token: str, query: str = "", password: str = ""
) -> dict[str, Any]:
    room = _room_for_token(token)
    _require_room_password(room, password)
    return _raffle_recipient_payload(room, query)


@app.post("/r/{token}/raffle-recipient")
async def site_register_raffle_recipient(
    token: str, request: TokenRaffleRecipientRequest
) -> dict[str, Any]:
    room = _room_for_token(token)
    _require_room_password(room, request.room_password)
    return _register_raffle_recipient(room, request.user_key)


@app.delete("/r/{token}/raffle-recipient")
async def site_remove_raffle_recipient(
    token: str, recipient_id: int, password: str = ""
) -> dict[str, Any]:
    room = _room_for_token(token)
    _require_room_password(room, password)
    removed = bot.admin_store.remove_raffle_recipient(room, recipient_id)
    if not removed:
        raise HTTPException(status_code=404, detail="상품 수령 기록을 찾지 못했습니다.")
    nickname, received_date = removed
    return {"ok": True, "nickname": nickname, "receivedDate": received_date}


@app.get("/r/{token}/moderation-incidents")
async def site_moderation_incidents(
    token: str, password: str = "", status: str = "all"
) -> dict[str, Any]:
    room = _room_for_token(token)
    _require_room_password(room, password)
    return {
        "items": bot.admin_store.list_moderation_incidents(room, status),
        "counts": bot.admin_store.moderation_training_counts(room),
        "corpus": bot.admin_store.moderation_corpus_stats(room),
    }


@app.post("/r/{token}/moderation-review")
async def site_moderation_review(
    token: str, request: ModerationReviewRequest
) -> dict[str, Any]:
    room = _room_for_token(token)
    _require_room_password(room, request.room_password)
    if request.status not in {"pending", "confirmed", "dismissed"}:
        raise HTTPException(status_code=400, detail="올바른 판정 상태가 아닙니다.")
    if not bot.admin_store.review_moderation_incident(
        room, request.incident_id, request.status
    ):
        raise HTTPException(status_code=404, detail="관찰 사례를 찾지 못했습니다.")
    return {
        "ok": True,
        "counts": bot.admin_store.moderation_training_counts(room),
        "corpus": bot.admin_store.moderation_corpus_stats(room),
    }


@app.get("/r/{token}/command")
async def site_get_command(token: str, command: str) -> dict[str, Any]:
    room = _room_for_token(token)
    normalized = PokemonGoBot._normalize_custom_command(command)
    custom = bot.admin_store.get_custom_command(room, normalized)
    if custom is None:
        return {"found": False}
    return {"found": True, "command": normalized, "response": custom.response}


@app.post("/r/{token}/command")
async def site_save_command(token: str, request: TokenCommandRequest) -> dict[str, Any]:
    room = _room_for_token(token)
    normalized = PokemonGoBot._normalize_custom_command(request.command)
    response = request.response.strip()
    if not normalized or not response:
        raise HTTPException(status_code=400, detail="명령어와 내용을 입력해 주세요.")
    if normalized in PokemonGoBot._reserved_custom_commands():
        raise HTTPException(status_code=400, detail=f"'{normalized}'는 봇 기본 명령어라 사용할 수 없습니다.")
    _require_room_password(room, request.room_password)
    bot.admin_store.upsert_custom_command(room, normalized, response, request.sender)
    return {"ok": True, "command": normalized, "length": len(response)}


@app.delete("/r/{token}/command")
async def site_delete_command(token: str, command: str, password: str = "") -> dict[str, Any]:
    room = _room_for_token(token)
    normalized = PokemonGoBot._normalize_custom_command(command)
    if not normalized:
        raise HTTPException(status_code=400, detail="명령어 이름을 입력해 주세요.")
    _require_room_password(room, password)
    deleted = bot.admin_store.delete_custom_command(room, normalized)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"'/{normalized}' — 삭제할 명령어가 없습니다. 이름을 확인해 주세요.",
        )
    return {"ok": True, "command": normalized}


@app.post("/r/{token}/room-password")
async def site_set_password(token: str, request: TokenPasswordSetRequest) -> dict[str, Any]:
    room = _room_for_token(token)
    password = request.password.strip()
    recovery_word = request.recovery_word.strip()
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="비밀번호는 4자 이상이어야 합니다.")
    if not recovery_word:
        raise HTTPException(status_code=400, detail="복구 단어를 입력해 주세요.")
    if not bot.admin_store.set_room_password(room, password, recovery_word):
        raise HTTPException(status_code=400, detail="이미 비밀번호가 설정된 방입니다.")
    return {"ok": True}


@app.post("/r/{token}/room-password/change")
async def site_change_password(token: str, request: TokenPasswordChangeRequest) -> dict[str, Any]:
    room = _room_for_token(token)
    new_password = request.new_password.strip()
    recovery_word = request.recovery_word.strip()
    if len(new_password) < 4:
        raise HTTPException(status_code=400, detail="새 비밀번호는 4자 이상이어야 합니다.")
    if not bot.admin_store.change_room_password(room, recovery_word, new_password):
        raise HTTPException(status_code=403, detail="복구 단어가 올바르지 않습니다.")
    return {"ok": True}


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
