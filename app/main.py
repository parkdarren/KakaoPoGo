from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
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
    "events",
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
    if response.silent:
        return _silent_response()
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
    if response.silent:
        return _silent_response()
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


class AdminCommandRequest(BaseModel):
    room: str
    command: str
    response: str
    sender: str = "웹관리"


class RenameRoomRequest(BaseModel):
    old_room: str
    new_room: str


ADMIN_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KakaoPoGo 명령어 관리</title>
<style>
  body { font-family: sans-serif; max-width: 560px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 1.2rem; }
  label { display: block; margin-top: 12px; font-weight: bold; font-size: 0.9rem; }
  input, textarea, select { width: 100%; box-sizing: border-box; padding: 8px;
    margin-top: 4px; font-size: 1rem; border: 1px solid #bbb; border-radius: 6px; }
  textarea { min-height: 260px; }
  button { margin-top: 14px; padding: 10px 18px; font-size: 1rem; border: 0;
    border-radius: 6px; background: #3c1e1e; color: #fee500; font-weight: bold; }
  button.secondary { background: #eee; color: #333; margin-left: 8px; }
  #status { margin-top: 12px; white-space: pre-wrap; font-size: 0.95rem; }
  #count { font-weight: normal; color: #666; font-size: 0.85rem; }
</style>
</head>
<body>
<h1>🤖 KakaoPoGo 명령어 관리</h1>
<p>카톡 알림 길이 제한 없이 긴 내용을 한 번에 등록/수정합니다.</p>

<label>관리 키</label>
<input id="key" type="password" placeholder="BRIDGE_KEY 값">

<label>방 이름 (목록에서 선택하세요 — 직접 입력하면 보이지 않는 문자 차이로 다른 방이 될 수 있어요)</label>
<select id="roomSelect">
  <option value="">키를 입력하면 방 목록이 나옵니다</option>
</select>
<input id="room" placeholder="새 방 이름 (봇 로그와 정확히 같아야 함)"
  style="display:none; margin-top:6px">
<datalist id="rooms"></datalist>

<label>명령어 이름 (/ 없이)</label>
<input id="command" placeholder="예: 이벤">

<label>내용 <span id="count"></span></label>
<textarea id="response" placeholder="명령어 응답 내용 전체를 붙여넣으세요"></textarea>

<button onclick="save()">저장</button>
<button class="secondary" onclick="load()">기존 내용 불러오기</button>
<div id="status"></div>

<details style="margin-top:28px">
<summary>🏷️ 방 이름 변경 이전 (방 제목이 바뀌었을 때만 사용)</summary>
<p style="font-size:0.85rem;color:#666">카톡방 제목이 바뀌면 봇이 새로운 방으로
인식해 명령어·관리자·출석이 끊깁니다. 옛 이름의 데이터를 새 이름으로 옮깁니다.</p>
<label>옛 방 이름</label>
<input id="oldRoom" list="rooms" placeholder="바뀌기 전 방 제목">
<label>새 방 이름</label>
<input id="newRoom" placeholder="바뀐 후 방 제목 (정확히)">
<button onclick="renameRoom()">이전 실행</button>
<div id="renameStatus"></div>
</details>

<script>
const $ = (id) => document.getElementById(id);
// 관리방에 공유하는 전용 링크(/admin#key=...)로 열면 키가 자동 입력된다.
// 키를 페이지에 직접 심지 않는 이유: 링크 없이 주소만 아는 외부인에게
// 봇 전체 제어 키가 노출되면 안 되기 때문.
const hashKey = new URLSearchParams(location.hash.slice(1)).get("key");
if (hashKey) {
  localStorage.setItem("kpg-key", hashKey);
  history.replaceState(null, "", location.pathname);
}
$("key").value = localStorage.getItem("kpg-key") || "";
$("response").addEventListener("input", () => {
  $("count").textContent = "(" + $("response").value.length + "자)";
});

function currentRoom() {
  if ($("roomSelect").value === "__custom__") return $("room").value.trim();
  return $("roomSelect").value;
}

$("roomSelect").addEventListener("change", () => {
  $("room").style.display = $("roomSelect").value === "__custom__" ? "block" : "none";
  localStorage.setItem("kpg-room", currentRoom());
});

function headers() {
  localStorage.setItem("kpg-key", $("key").value);
  return { "X-Bridge-Key": $("key").value, "Content-Type": "application/json" };
}

async function refreshRooms() {
  if (!$("key").value) return;
  const res = await fetch("/admin/rooms", { headers: headers() });
  if (!res.ok) return;
  const rooms = await res.json();
  const saved = localStorage.getItem("kpg-room") || "";
  $("roomSelect").innerHTML =
    rooms.map((r) => `<option value="${r}">${r}</option>`).join("") +
    `<option value="__custom__">＋ 새 방 이름 직접 입력</option>`;
  if (rooms.includes(saved)) $("roomSelect").value = saved;
  $("rooms").innerHTML = rooms.map((r) => `<option value="${r}">`).join("");
}
$("key").addEventListener("change", refreshRooms);
refreshRooms();

async function load() {
  if (!currentRoom()) return show("방을 먼저 선택해 주세요.");
  const params = new URLSearchParams({ room: currentRoom(), command: $("command").value });
  const res = await fetch("/admin/command?" + params, { headers: headers() });
  if (res.status === 403) return show("❌ 관리 키가 올바르지 않습니다.");
  const data = await res.json();
  if (!data.found) return show("등록되지 않은 명령어입니다. 저장하면 새로 만듭니다.");
  $("response").value = data.response;
  $("count").textContent = "(" + data.response.length + "자)";
  show("✅ 불러왔습니다. 수정 후 저장하세요.");
}

async function save() {
  if (!currentRoom()) return show("방을 먼저 선택해 주세요.");
  const res = await fetch("/admin/command", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      room: currentRoom(),
      command: $("command").value,
      response: $("response").value,
    }),
  });
  if (res.status === 403) return show("❌ 관리 키가 올바르지 않습니다.");
  const data = await res.json();
  if (!res.ok) return show("❌ " + (data.detail || "저장 실패"));
  show(`✅ /${data.command} 저장 완료 (${data.length}자)`);
  refreshRooms();
}

function show(msg) { $("status").textContent = msg; }

async function renameRoom() {
  const oldRoom = $("oldRoom").value.trim();
  const newRoom = $("newRoom").value.trim();
  const out = (msg) => { $("renameStatus").textContent = msg; };
  if (!oldRoom || !newRoom) return out("옛 이름과 새 이름을 모두 입력해 주세요.");
  if (oldRoom === newRoom) return out("두 이름이 같습니다.");
  if (!confirm(`'${oldRoom}'\\n→ '${newRoom}'\\n\\n이 방의 명령어·관리자·출석 기록을 모두 옮길까요?`)) return;
  const res = await fetch("/admin/rename-room", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ old_room: oldRoom, new_room: newRoom }),
  });
  if (res.status === 403) return out("❌ 관리 키가 올바르지 않습니다.");
  const data = await res.json();
  if (!res.ok) return out("❌ " + (data.detail || "이전 실패"));
  out(`✅ 이전 완료 — 명령어 ${data.custom_commands}개, 관리자 ${data.room_admins}명, 출석 ${data.attendance}건`);
  refreshRooms();
}
</script>
</body>
</html>"""


@app.get("/admin", response_class=HTMLResponse)
async def admin_page() -> str:
    return ADMIN_PAGE


@app.get("/admin/rooms", dependencies=[Depends(_verify_bridge_key)])
async def admin_rooms() -> list[str]:
    return bot.admin_store.list_custom_rooms()


@app.get("/admin/command", dependencies=[Depends(_verify_bridge_key)])
async def admin_get_command(room: str, command: str) -> dict[str, Any]:
    normalized = PokemonGoBot._normalize_custom_command(command)
    custom = bot.admin_store.get_custom_command(room.strip(), normalized)
    if custom is None:
        return {"found": False}
    return {"found": True, "command": normalized, "response": custom.response}


@app.post("/admin/command", dependencies=[Depends(_verify_bridge_key)])
async def admin_save_command(request: AdminCommandRequest) -> dict[str, Any]:
    room = request.room.strip()
    normalized = PokemonGoBot._normalize_custom_command(request.command)
    response = request.response.strip()
    if not room or not normalized or not response:
        raise HTTPException(status_code=400, detail="방 이름, 명령어, 내용을 모두 입력해 주세요.")
    if normalized in PokemonGoBot._reserved_custom_commands():
        raise HTTPException(status_code=400, detail=f"'{normalized}'는 봇 기본 명령어라 사용할 수 없습니다.")

    bot.admin_store.upsert_custom_command(room, normalized, response, request.sender)
    return {"ok": True, "command": normalized, "length": len(response)}


@app.post("/admin/rename-room", dependencies=[Depends(_verify_bridge_key)])
async def admin_rename_room(request: RenameRoomRequest) -> dict[str, Any]:
    old_room = request.old_room.strip()
    new_room = request.new_room.strip()
    if not old_room or not new_room:
        raise HTTPException(status_code=400, detail="옛 이름과 새 이름을 모두 입력해 주세요.")
    if old_room == new_room:
        raise HTTPException(status_code=400, detail="두 이름이 같습니다.")

    moved = bot.admin_store.migrate_room(old_room, new_room)
    return {"ok": True, **moved}


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
