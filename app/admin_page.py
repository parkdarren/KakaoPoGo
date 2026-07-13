"""웹 관리 페이지 HTML.

폰 브라우저에서 쓰는 단일 페이지라 외부 리소스 없이 전부 인라인으로 담는다.
비밀 값은 절대 이 페이지에 넣지 않는다 — 키는 /admin#key=... 링크로만 전달된다.
"""

ADMIN_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#c11f04">
<title>포고정보 관리자</title>
<style>
  :root {
    --red: #e3350d;
    --red-deep: #c11f04;
    --ink: #23252f;
    --bg: #eef0f5;
    --card: #ffffff;
    --field: #f1f2f7;
    --line: #e7e9f2;
    --muted: #9094a6;
    --label: #6b7080;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html { background: var(--bg); }
  body {
    font-family: "Apple SD Gothic Neo", "Pretendard", "Noto Sans KR", sans-serif;
    background:
      radial-gradient(circle at 90% -80px, rgba(227, 53, 13, 0.07), transparent 340px),
      var(--bg);
    color: var(--ink);
    max-width: 560px; margin: 0 auto;
    padding: 16px 16px calc(44px + env(safe-area-inset-bottom));
  }

  .hero {
    position: relative; overflow: hidden;
    background: linear-gradient(140deg, #ef5533 0%, var(--red-deep) 78%);
    border-radius: 22px; padding: 22px 20px 20px; color: #fff;
    box-shadow: 0 12px 28px rgba(227, 53, 13, 0.28);
    margin-bottom: 16px;
  }
  .hero::before {
    content: ""; position: absolute; right: -44px; top: -44px;
    width: 164px; height: 164px; border-radius: 50%;
    border: 16px solid rgba(255, 255, 255, 0.13);
  }
  .hero::after {
    content: ""; position: absolute; right: 24px; top: 24px;
    width: 28px; height: 28px; border-radius: 50%;
    background: rgba(255, 255, 255, 0.16);
    border: 7px solid rgba(255, 255, 255, 0.22);
  }
  .hero .badge {
    display: inline-block; background: rgba(255, 255, 255, 0.18);
    border-radius: 999px; padding: 4px 11px; font-size: 0.7rem;
    font-weight: 700; letter-spacing: 0.06em; margin-bottom: 10px;
  }
  .hero h1 { margin: 0; font-size: 1.34rem; font-weight: 800; letter-spacing: -0.02em; }
  .hero p { margin: 7px 0 0; font-size: 0.82rem; opacity: 0.88; line-height: 1.45; }

  .card {
    background: var(--card); border-radius: 20px; padding: 18px;
    margin-bottom: 14px;
    box-shadow: 0 1px 2px rgba(23, 26, 38, 0.04), 0 10px 26px rgba(23, 26, 38, 0.06);
  }
  .card h2 {
    display: flex; align-items: center; gap: 9px;
    font-size: 0.98rem; font-weight: 800; margin: 0 0 4px;
  }
  .card h2 .dot {
    width: 10px; height: 10px; border-radius: 50%; flex: none;
    background: var(--red); box-shadow: 0 0 0 4px rgba(227, 53, 13, 0.12);
  }

  label {
    display: block; margin: 15px 0 6px; font-weight: 700;
    font-size: 0.78rem; color: var(--label); letter-spacing: 0.02em;
  }
  .hint { font-size: 0.78rem; color: var(--muted); margin: 8px 0 0; line-height: 1.5; }
  input, textarea, select {
    width: 100%; padding: 12px 14px; font-size: 0.95rem;
    background: var(--field); color: var(--ink);
    border: 1.5px solid transparent; border-radius: 14px;
    font-family: inherit; transition: border-color 0.15s, background 0.15s;
    appearance: none; -webkit-appearance: none;
  }
  select {
    background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%239094a6' stroke-width='2' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 14px center;
    padding-right: 36px;
  }
  input:focus, textarea:focus, select:focus {
    outline: none; background: #fff; border-color: var(--red);
  }
  textarea { min-height: 240px; line-height: 1.5; border-radius: 16px; }

  .cmdrow { display: flex; align-items: stretch; gap: 8px; }
  .cmdrow .slash {
    display: flex; align-items: center; flex: none;
    background: var(--ink); color: #fff; border-radius: 14px;
    padding: 0 15px; font-weight: 800; font-size: 1.05rem;
  }

  .btnrow { display: flex; gap: 8px; margin-top: 16px; }
  button {
    border: 0; border-radius: 14px; padding: 13px 16px;
    font-size: 0.93rem; font-weight: 800; cursor: pointer;
    font-family: inherit; transition: transform 0.06s ease, filter 0.15s;
  }
  button:active { transform: scale(0.97); filter: brightness(0.96); }
  .primary {
    flex: 1; color: #fff;
    background: linear-gradient(135deg, #ef5533, #d92c07);
    box-shadow: 0 6px 16px rgba(227, 53, 13, 0.3);
  }
  .ghost { background: #eceef4; color: #3a3d4d; }
  .danger { background: transparent; color: var(--red-deep); border: 1.5px solid #f3c1b5; }
  #cmdToggle { width: 100%; }

  .chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
  .chip {
    display: inline-flex; align-items: center; gap: 5px;
    background: #fff; border: 1px solid var(--line); border-radius: 999px;
    padding: 7px 13px; font-size: 0.82rem; font-weight: 600; color: var(--ink);
    box-shadow: 0 1px 3px rgba(23, 26, 38, 0.05);
  }
  .chip small { color: var(--muted); font-weight: 500; }
  .chip.active { background: var(--ink); border-color: var(--ink); color: #fff; }
  .chip.active small { color: rgba(255, 255, 255, 0.65); }

  .toast { margin-top: 12px; font-size: 0.87rem; white-space: pre-wrap; border-radius: 13px; }
  .toast.ok { background: #eaf7ee; color: #17724a; padding: 12px 14px; }
  .toast.err { background: #fdeeec; color: var(--red-deep); padding: 12px 14px; }

  details summary {
    cursor: pointer; font-weight: 800; font-size: 0.92rem;
    color: var(--ink); list-style: none; display: flex; align-items: center; gap: 9px;
  }
  details summary::-webkit-details-marker { display: none; }
  details summary::before {
    content: ""; width: 10px; height: 10px; border-radius: 50%; flex: none;
    background: var(--muted); box-shadow: 0 0 0 4px rgba(144, 148, 166, 0.15);
  }
  details[open] summary::before { background: var(--red); box-shadow: 0 0 0 4px rgba(227, 53, 13, 0.12); }

  footer {
    display: flex; align-items: center; justify-content: center; gap: 7px;
    font-size: 0.74rem; color: var(--muted); margin-top: 22px;
  }
  footer .miniball {
    width: 13px; height: 13px; border-radius: 50%; flex: none;
    background: linear-gradient(var(--red) 0 44%, var(--ink) 44% 56%, #fff 56% 100%);
    border: 1.5px solid var(--ink);
  }
  #count { font-weight: 500; color: var(--muted); font-size: 0.76rem; }
</style>
</head>
<body>
<header class="hero">
  <span class="badge">KAKAOPOGO ADMIN</span>
  <h1>포고정보 관리자</h1>
  <p>카톡 길이 제한 없이 명령어를<br>등록 · 수정 · 삭제합니다</p>
</header>

<section class="card">
  <h2><span class="dot"></span>접속</h2>
  <label for="key">관리 키</label>
  <input id="key" type="password" placeholder="관리 키를 입력하세요">
  <p class="hint">관리방에 공유된 링크로 들어왔다면 자동으로 채워져 있어요.</p>
</section>

<section class="card">
  <h2><span class="dot"></span>명령어 관리</h2>
  <label for="roomSelect">방 선택</label>
  <select id="roomSelect">
    <option value="">키를 입력하면 방 목록이 나와요</option>
  </select>
  <input id="room" placeholder="새 방 이름 (봇이 보는 이름과 정확히 같아야 함)"
    style="display:none; margin-top:8px">

  <div class="btnrow" style="margin-top:12px">
    <button class="ghost" id="cmdToggle" type="button" onclick="toggleCommands()">등록된 명령어 보기</button>
  </div>
  <div id="cmdPanel" style="display:none">
    <div class="chips" id="cmdChips"></div>
    <p class="hint" id="chipsHint">누르면 내용을 불러옵니다.</p>
  </div>

  <label for="command">명령어 이름</label>
  <div class="cmdrow"><span class="slash">/</span><input id="command" placeholder="예: 이벤"></div>

  <label for="response">내용 <span id="count"></span></label>
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
    <summary>방 이름 변경 이전 (방 제목이 바뀌었을 때만)</summary>
    <p class="hint">카톡방 제목이 바뀌면 봇이 새로운 방으로 인식해 명령어·관리자·출석이
    끊깁니다. 옛 이름의 데이터를 새 이름으로 옮깁니다.</p>
    <label for="oldRoom">옛 방 이름</label>
    <input id="oldRoom" list="rooms" placeholder="바뀌기 전 방 제목">
    <label for="newRoom">새 방 이름</label>
    <input id="newRoom" placeholder="바뀐 후 방 제목 (정확히)">
    <div class="btnrow">
      <button class="ghost" onclick="renameRoom()">이전 실행</button>
    </div>
    <div id="renameStatus" class="toast"></div>
  </details>
</section>

<datalist id="rooms"></datalist>
<footer><span class="miniball"></span>KakaoPoGo · 포고정보 봇 관리자 페이지</footer>

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
  $("cmdToggle").textContent = "등록된 명령어 보기";
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
  $("cmdToggle").textContent = "명령어 목록 접기 (" + commands.length + "개)";
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
