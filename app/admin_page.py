"""웹 관리 페이지 HTML.

폰 브라우저에서 쓰는 단일 페이지라 외부 리소스 없이 전부 인라인으로 담는다.
비밀 값은 절대 이 페이지에 넣지 않는다 — 키는 /admin#key=... 링크로만 전달된다.
"""

ADMIN_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>포고정보 관리자</title>
<style>
  :root {
    --red: #ee4035;
    --red-dark: #c62828;
    --yellow: #ffcb05;
    --blue: #3b4cca;
    --ink: #26262a;
    --paper: #f6f7fb;
    --card: #ffffff;
    --line: #e6e8f0;
    --muted: #8a8f9e;
  }
  * { box-sizing: border-box; }
  body {
    font-family: "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
    background: var(--paper); color: var(--ink);
    max-width: 560px; margin: 0 auto; padding: 14px 14px 40px;
  }
  header { display: flex; align-items: center; gap: 12px; padding: 10px 4px 16px; }
  .pokeball {
    width: 40px; height: 40px; border-radius: 50%; flex: none;
    background: linear-gradient(var(--red) 0 44%, var(--ink) 44% 56%, #fff 56% 100%);
    border: 2px solid var(--ink); position: relative;
    animation: wiggle 4s ease-in-out infinite;
  }
  .pokeball::after {
    content: ""; position: absolute; top: 50%; left: 50%;
    width: 12px; height: 12px; border-radius: 50%;
    background: #fff; border: 3px solid var(--ink);
    transform: translate(-50%, -50%);
  }
  @keyframes wiggle {
    0%, 88%, 100% { transform: rotate(0); }
    90% { transform: rotate(-12deg); }
    94% { transform: rotate(10deg); }
    97% { transform: rotate(-6deg); }
  }
  header h1 { font-size: 1.15rem; margin: 0; }
  header p { font-size: 0.8rem; color: var(--muted); margin: 2px 0 0; }
  .card {
    background: var(--card); border: 1px solid var(--line);
    border-radius: 16px; padding: 16px; margin-bottom: 14px;
    box-shadow: 0 2px 10px rgba(38, 38, 42, 0.05);
  }
  .card h2 { font-size: 0.95rem; margin: 0 0 10px; }
  label { display: block; margin-top: 12px; font-weight: 600; font-size: 0.85rem; }
  label:first-of-type { margin-top: 0; }
  .hint { font-size: 0.78rem; color: var(--muted); margin: 6px 0 0; }
  input, textarea, select {
    width: 100%; padding: 10px 12px; margin-top: 6px; font-size: 0.95rem;
    border: 1.5px solid var(--line); border-radius: 10px; background: #fff;
    font-family: inherit;
  }
  input:focus, textarea:focus, select:focus {
    outline: none; border-color: var(--blue);
  }
  textarea { min-height: 220px; line-height: 1.45; }
  .cmdrow { display: flex; align-items: center; gap: 6px; margin-top: 6px; }
  .cmdrow .slash {
    font-weight: 800; font-size: 1.1rem; color: var(--red);
    background: #fdecea; border-radius: 8px; padding: 8px 12px;
  }
  .cmdrow input { margin-top: 0; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
  .chip {
    border: 1.5px solid var(--line); background: #fff; border-radius: 999px;
    padding: 6px 12px; font-size: 0.82rem; cursor: pointer; color: var(--ink);
  }
  .chip small { color: var(--muted); margin-left: 4px; }
  .chip.active { border-color: var(--red); background: #fdecea; font-weight: 700; }
  .btnrow { display: flex; gap: 8px; margin-top: 14px; }
  button {
    border: 0; border-radius: 10px; padding: 11px 14px; font-size: 0.92rem;
    font-weight: 700; cursor: pointer; font-family: inherit;
  }
  .primary { background: var(--red); color: #fff; flex: 1; }
  .primary:active { background: var(--red-dark); }
  .ghost { background: #eef0f6; color: var(--ink); }
  .danger { background: #fff; color: var(--red); border: 1.5px solid var(--red); }
  .toast {
    margin-top: 12px; padding: 0; border-radius: 10px; font-size: 0.88rem;
    white-space: pre-wrap;
  }
  .toast.ok { background: #e8f5e9; color: #1b5e20; padding: 10px 12px; }
  .toast.err { background: #fdecea; color: var(--red-dark); padding: 10px 12px; }
  details summary {
    cursor: pointer; font-weight: 700; font-size: 0.9rem; color: var(--muted);
  }
  footer { text-align: center; font-size: 0.75rem; color: var(--muted); margin-top: 18px; }
  #count { font-weight: 400; color: var(--muted); font-size: 0.8rem; }
</style>
</head>
<body>
<header>
  <div class="pokeball"></div>
  <div>
    <h1>포고정보 관리자</h1>
    <p>카톡 길이 제한 없이 명령어를 등록·수정·삭제합니다</p>
  </div>
</header>

<section class="card">
  <h2>🔑 접속</h2>
  <input id="key" type="password" placeholder="관리 키">
  <p class="hint">관리방에 공유된 링크로 들어왔다면 자동으로 채워져 있어요.</p>
</section>

<section class="card">
  <h2>📋 명령어 관리</h2>
  <label>방 선택</label>
  <select id="roomSelect">
    <option value="">키를 입력하면 방 목록이 나와요</option>
  </select>
  <input id="room" placeholder="새 방 이름 (봇이 보는 이름과 정확히 같아야 함)"
    style="display:none">

  <div class="btnrow" style="margin-top:10px">
    <button class="ghost" id="cmdToggle" type="button" onclick="toggleCommands()">📋 등록된 명령어 보기</button>
  </div>
  <div id="cmdPanel" style="display:none">
    <div class="chips" id="cmdChips"></div>
    <p class="hint" id="chipsHint">누르면 내용을 불러옵니다.</p>
  </div>

  <label>명령어 이름</label>
  <div class="cmdrow"><span class="slash">/</span><input id="command" placeholder="예: 이벤"></div>

  <label>내용 <span id="count"></span></label>
  <textarea id="response" placeholder="명령어 응답 내용을 붙여넣으세요 (길이 제한 없음)"></textarea>

  <div class="btnrow">
    <button class="primary" onclick="save()">저장</button>
    <button class="ghost" onclick="load()">불러오기</button>
    <button class="danger" onclick="deleteCommand()">삭제</button>
  </div>
  <div id="status" class="toast"></div>
</section>

<section class="card">
  <details>
    <summary>🏷️ 방 이름 변경 이전 (방 제목이 바뀌었을 때만)</summary>
    <p class="hint">카톡방 제목이 바뀌면 봇이 새로운 방으로 인식해 명령어·관리자·출석이
    끊깁니다. 옛 이름의 데이터를 새 이름으로 옮깁니다.</p>
    <label>옛 방 이름</label>
    <input id="oldRoom" list="rooms" placeholder="바뀌기 전 방 제목">
    <label>새 방 이름</label>
    <input id="newRoom" placeholder="바뀐 후 방 제목 (정확히)">
    <div class="btnrow">
      <button class="ghost" onclick="renameRoom()">이전 실행</button>
    </div>
    <div id="renameStatus" class="toast"></div>
  </details>
</section>

<datalist id="rooms"></datalist>
<footer>KakaoPoGo · 포고정보 봇 관리자 페이지</footer>

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
  // 방이 바뀌면 목록을 닫는다. 다시 열면 그 방의 명령어가 나온다.
  hideCommands();
});

function headers() {
  localStorage.setItem("kpg-key", $("key").value);
  return { "X-Bridge-Key": $("key").value, "Content-Type": "application/json" };
}

function option(value, text) {
  const el = document.createElement("option");
  el.value = value;
  el.textContent = text;
  return el;
}

async function refreshRooms() {
  if (!$("key").value) return;
  const res = await fetch("/admin/rooms", { headers: headers() });
  if (!res.ok) return;
  const rooms = await res.json();
  const saved = localStorage.getItem("kpg-room") || "";
  const select = $("roomSelect");
  select.innerHTML = "";
  rooms.forEach((r) => select.appendChild(option(r, r)));
  select.appendChild(option("__custom__", "＋ 새 방 이름 직접 입력"));
  if (rooms.includes(saved)) select.value = saved;
  $("rooms").innerHTML = "";
  rooms.forEach((r) => $("rooms").appendChild(option(r, r)));
}
$("key").addEventListener("change", refreshRooms);
refreshRooms();

function hideCommands() {
  $("cmdPanel").style.display = "none";
  $("cmdChips").innerHTML = "";
  $("cmdToggle").textContent = "📋 등록된 명령어 보기";
}

async function toggleCommands() {
  if ($("cmdPanel").style.display !== "none") return hideCommands();
  if (!currentRoom() || $("roomSelect").value === "__custom__") {
    return show("방을 먼저 선택해 주세요.", false);
  }
  await refreshCommands();
}

async function refreshCommands() {
  const box = $("cmdChips");
  box.innerHTML = "";
  const params = new URLSearchParams({ room: currentRoom() });
  const res = await fetch("/admin/commands?" + params, { headers: headers() });
  if (res.status === 403) return show("관리 키가 올바르지 않습니다.", false);
  if (!res.ok) return;
  const commands = await res.json();
  $("cmdPanel").style.display = "block";
  $("cmdToggle").textContent = "📋 명령어 목록 접기 (" + commands.length + "개)";
  if (!commands.length) {
    $("chipsHint").textContent = "이 방에 등록된 명령어가 아직 없어요.";
    return;
  }
  $("chipsHint").textContent = "누르면 내용을 불러옵니다.";
  commands.forEach((item) => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.type = "button";
    chip.textContent = "/" + item.command;
    const size = document.createElement("small");
    size.textContent = item.length + "자";
    chip.appendChild(size);
    chip.onclick = () => {
      document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      $("command").value = item.command;
      load();
    };
    box.appendChild(chip);
  });
}

function show(msg, ok) {
  $("status").textContent = msg;
  $("status").className = "toast " + (ok ? "ok" : "err");
}

async function load() {
  if (!currentRoom()) return show("방을 먼저 선택해 주세요.", false);
  if (!$("command").value.trim()) return show("명령어 이름을 입력해 주세요.", false);
  const params = new URLSearchParams({ room: currentRoom(), command: $("command").value });
  const res = await fetch("/admin/command?" + params, { headers: headers() });
  if (res.status === 403) return show("관리 키가 올바르지 않습니다.", false);
  const data = await res.json();
  if (!data.found) return show("등록되지 않은 명령어예요. 저장하면 새로 만들어요.", true);
  $("response").value = data.response;
  $("count").textContent = "(" + data.response.length + "자)";
  show("불러왔습니다. 수정 후 저장하세요.", true);
}

async function save() {
  if (!currentRoom()) return show("방을 먼저 선택해 주세요.", false);
  const res = await fetch("/admin/command", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      room: currentRoom(),
      command: $("command").value,
      response: $("response").value,
    }),
  });
  if (res.status === 403) return show("관리 키가 올바르지 않습니다.", false);
  const data = await res.json();
  if (!res.ok) return show(data.detail || "저장에 실패했습니다.", false);
  show("/" + data.command + " 저장 완료! (" + data.length + "자)", true);
  if ($("cmdPanel").style.display !== "none") refreshCommands();
}

async function deleteCommand() {
  if (!currentRoom()) return show("방을 먼저 선택해 주세요.", false);
  const name = $("command").value.trim().replace(/^\\//, "");
  if (!name) return show("삭제할 명령어 이름을 입력해 주세요.", false);
  if (!confirm("'/" + name + "' 명령어를 정말 삭제할까요?")) return;
  const params = new URLSearchParams({ room: currentRoom(), command: name });
  const res = await fetch("/admin/command?" + params, {
    method: "DELETE",
    headers: headers(),
  });
  if (res.status === 403) return show("관리 키가 올바르지 않습니다.", false);
  const data = await res.json();
  if (!res.ok) return show(data.detail || "삭제에 실패했습니다.", false);
  $("response").value = "";
  $("count").textContent = "";
  show("/" + data.command + " 명령어를 삭제했습니다.", true);
  if ($("cmdPanel").style.display !== "none") refreshCommands();
}

async function renameRoom() {
  const oldRoom = $("oldRoom").value.trim();
  const newRoom = $("newRoom").value.trim();
  const out = (msg, ok) => {
    $("renameStatus").textContent = msg;
    $("renameStatus").className = "toast " + (ok ? "ok" : "err");
  };
  if (!oldRoom || !newRoom) return out("옛 이름과 새 이름을 모두 입력해 주세요.", false);
  if (oldRoom === newRoom) return out("두 이름이 같습니다.", false);
  if (!confirm(oldRoom + "\\n→ " + newRoom + "\\n\\n이 방의 명령어·관리자·출석 기록을 모두 옮길까요?")) return;
  const res = await fetch("/admin/rename-room", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ old_room: oldRoom, new_room: newRoom }),
  });
  if (res.status === 403) return out("관리 키가 올바르지 않습니다.", false);
  const data = await res.json();
  if (!res.ok) return out(data.detail || "이전에 실패했습니다.", false);
  out("이전 완료 — 명령어 " + data.custom_commands + "개, 관리자 " + data.room_admins + "명, 출석 " + data.attendance + "건", true);
  refreshRooms();
}
</script>
</body>
</html>"""
