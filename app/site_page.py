"""방 전용 관리 페이지 HTML.

한 링크(/r/{token})가 한 방만 담당한다. 토큰이 곧 방 범위라
방 선택도 대상방 설정도 없다. 방 제목이 바뀌어도 서버가 chat_id로
같은 방을 이어주므로 링크는 그대로 쓴다. 비밀 값은 담지 않는다.
"""

SITE_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#c11f04">
<title>포고정보 방 관리</title>
<style>
  :root {
    --red: #e3350d; --red-deep: #c11f04; --ink: #23252f; --bg: #eef0f5;
    --card: #ffffff; --field: #f1f2f7; --line: #e7e9f2; --muted: #9094a6; --label: #6b7080;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html { background: var(--bg); }
  body {
    font-family: "Apple SD Gothic Neo", "Pretendard", "Noto Sans KR", sans-serif;
    background: radial-gradient(circle at 90% -80px, rgba(227,53,13,0.07), transparent 340px), var(--bg);
    color: var(--ink); max-width: 560px; margin: 0 auto;
    padding: 16px 16px calc(44px + env(safe-area-inset-bottom));
  }
  .hero {
    position: relative; overflow: hidden;
    background: linear-gradient(140deg, #ef5533 0%, var(--red-deep) 78%);
    border-radius: 22px; padding: 22px 20px 20px; color: #fff;
    box-shadow: 0 12px 28px rgba(227,53,13,0.28); margin-bottom: 16px;
  }
  .hero::before {
    content: ""; position: absolute; right: -44px; top: -44px;
    width: 164px; height: 164px; border-radius: 50%; border: 16px solid rgba(255,255,255,0.13);
  }
  .hero .badge {
    display: inline-block; background: rgba(255,255,255,0.18); border-radius: 999px;
    padding: 4px 11px; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em; margin-bottom: 10px;
  }
  .hero h1 { margin: 0; font-size: 1.24rem; font-weight: 800; letter-spacing: -0.02em; }
  .hero p { margin: 7px 0 0; font-size: 0.82rem; opacity: 0.9; line-height: 1.45; }
  .hero .roomname { font-weight: 800; }
  .card {
    background: var(--card); border-radius: 20px; padding: 18px; margin-bottom: 14px;
    box-shadow: 0 1px 2px rgba(23,26,38,0.04), 0 10px 26px rgba(23,26,38,0.06);
  }
  .card h2 { display: flex; align-items: center; gap: 9px; font-size: 0.98rem; font-weight: 800; margin: 0 0 4px; }
  .card h2 .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; background: var(--red); box-shadow: 0 0 0 4px rgba(227,53,13,0.12); }
  label { display: block; margin: 15px 0 6px; font-weight: 700; font-size: 0.78rem; color: var(--label); letter-spacing: 0.02em; }
  .hint { font-size: 0.78rem; color: var(--muted); margin: 8px 0 0; line-height: 1.5; }
  input, textarea {
    width: 100%; padding: 12px 14px; font-size: 0.95rem; background: var(--field); color: var(--ink);
    border: 1.5px solid transparent; border-radius: 14px; font-family: inherit;
    transition: border-color 0.15s, background 0.15s; appearance: none; -webkit-appearance: none;
  }
  input:focus, textarea:focus { outline: none; background: #fff; border-color: var(--red); }
  textarea { min-height: 240px; line-height: 1.5; border-radius: 16px; }
  .cmdrow { display: flex; align-items: stretch; gap: 8px; }
  .cmdrow .slash { display: flex; align-items: center; flex: none; background: var(--ink); color: #fff; border-radius: 14px; padding: 0 15px; font-weight: 800; font-size: 1.05rem; }
  .btnrow { display: flex; gap: 8px; margin-top: 16px; }
  button { border: 0; border-radius: 14px; padding: 13px 16px; font-size: 0.93rem; font-weight: 800; cursor: pointer; font-family: inherit; transition: transform 0.06s ease, filter 0.15s; }
  button:active { transform: scale(0.97); filter: brightness(0.96); }
  .primary { flex: 1; color: #fff; background: linear-gradient(135deg, #ef5533, #d92c07); box-shadow: 0 6px 16px rgba(227,53,13,0.3); }
  .ghost { background: #eceef4; color: #3a3d4d; }
  .danger { background: transparent; color: var(--red-deep); border: 1.5px solid #f3c1b5; }
  #cmdToggle { width: 100%; }
  .chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
  .chip { display: inline-flex; align-items: center; gap: 5px; background: #fff; border: 1px solid var(--line); border-radius: 999px; padding: 7px 13px; font-size: 0.82rem; font-weight: 600; color: var(--ink); box-shadow: 0 1px 3px rgba(23,26,38,0.05); }
  .chip small { color: var(--muted); font-weight: 500; }
  .chip.active { background: var(--ink); border-color: var(--ink); color: #fff; }
  .chip.active small { color: rgba(255,255,255,0.65); }
  .toast { margin-top: 12px; font-size: 0.87rem; white-space: pre-wrap; border-radius: 13px; }
  .toast.ok { background: #eaf7ee; color: #17724a; padding: 12px 14px; }
  .toast.err { background: #fdeeec; color: var(--red-deep); padding: 12px 14px; }
  details summary { cursor: pointer; font-weight: 800; font-size: 0.92rem; color: var(--ink); list-style: none; display: flex; align-items: center; gap: 9px; }
  details summary::-webkit-details-marker { display: none; }
  details summary::before { content: ""; width: 10px; height: 10px; border-radius: 50%; flex: none; background: var(--muted); box-shadow: 0 0 0 4px rgba(144,148,166,0.15); }
  details[open] summary::before { background: var(--red); box-shadow: 0 0 0 4px rgba(227,53,13,0.12); }
  footer { display: flex; align-items: center; justify-content: center; gap: 7px; font-size: 0.74rem; color: var(--muted); margin-top: 22px; }
  footer .miniball { width: 13px; height: 13px; border-radius: 50%; flex: none; background: linear-gradient(var(--red) 0 44%, var(--ink) 44% 56%, #fff 56% 100%); border: 1.5px solid var(--ink); }
  #count { font-weight: 500; color: var(--muted); font-size: 0.76rem; }
</style>
</head>
<body>
<header class="hero">
  <span class="badge">KAKAOPOGO</span>
  <h1>방 명령어 관리</h1>
  <p>이 링크는 <span class="roomname" id="roomName">…</span> 전용이에요.<br>카톡 길이 제한 없이 명령어를 등록 · 수정 · 삭제합니다</p>
</header>

<section class="card">
  <h2><span class="dot"></span>명령어 관리</h2>
  <label for="roomPw">방 비밀번호</label>
  <input id="roomPw" type="password" placeholder="비밀번호가 설정된 방만 입력">
  <p class="hint">비밀번호가 설정된 방은 이 비밀번호가 맞아야 저장·삭제할 수 있어요.</p>

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
    <summary>방 비밀번호 설정 / 변경</summary>
    <p class="hint">비밀번호를 설정하면 그 방의 명령어는 비밀번호를 아는 사람만
    수정·삭제할 수 있어요. 복구 단어는 비밀번호를 바꿀 때 쓰는 열쇠이니 잊지 마세요!</p>
    <label>처음 설정 — 비밀번호 / 복구 단어</label>
    <input id="pwNew" type="password" placeholder="비밀번호 (4자 이상)">
    <input id="pwRecovery" placeholder="복구 단어 (변경할 때 필요)" style="margin-top:6px">
    <div class="btnrow"><button class="ghost" onclick="setRoomPw()">비밀번호 설정</button></div>
    <label>변경 — 복구 단어 / 새 비밀번호</label>
    <input id="pwRecovery2" placeholder="설정할 때 정한 복구 단어">
    <input id="pwNew2" type="password" placeholder="새 비밀번호 (4자 이상)" style="margin-top:6px">
    <div class="btnrow"><button class="ghost" onclick="changeRoomPw()">비밀번호 변경</button></div>
    <div id="pwStatus" class="toast"></div>
  </details>
</section>

<footer><span class="miniball"></span>KakaoPoGo · 포고정보 봇 방 관리</footer>

<script>
const $ = (id) => document.getElementById(id);
const TOKEN = location.pathname.replace(/\\/+$/, "").split("/").pop();
const api = (path) => "/r/" + encodeURIComponent(TOKEN) + path;

$("response").addEventListener("input", () => {
  $("count").textContent = "(" + $("response").value.length + "자)";
});
$("roomPw").addEventListener("input", () => {
  localStorage.setItem("kpg-site-pw:" + TOKEN, $("roomPw").value);
});
$("roomPw").value = localStorage.getItem("kpg-site-pw:" + TOKEN) || "";

function roomPw() { return $("roomPw").value; }
function show(el, ok, msg) { el.className = "toast " + (ok ? "ok" : "err"); el.textContent = msg; }

async function req(path, options) {
  const res = await fetch(api(path), options);
  let data = {};
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error(data.detail || ("오류 " + res.status));
  return data;
}

async function loadInfo() {
  try {
    const info = await req("/info", {});
    $("roomName").textContent = info.room;
    document.title = info.room + " · 방 관리";
  } catch (e) {
    $("roomName").textContent = "링크 오류";
    show($("status"), false, "유효하지 않은 링크예요. 방 관리자에게 다시 받아주세요.");
  }
}

let commandsShown = false;
function hideCommands() {
  commandsShown = false;
  $("cmdPanel").style.display = "none";
  $("cmdToggle").textContent = "등록된 명령어 보기";
}
async function toggleCommands() {
  if (commandsShown) { hideCommands(); return; }
  try {
    const list = await req("/commands", {});
    const chips = $("cmdChips");
    chips.innerHTML = "";
    if (!list.length) {
      $("chipsHint").textContent = "아직 등록된 명령어가 없어요.";
    } else {
      $("chipsHint").textContent = "누르면 내용을 불러옵니다.";
      for (const item of list) {
        const chip = document.createElement("button");
        chip.className = "chip";
        chip.innerHTML = "/" + item.command + " <small>" + item.length + "자</small>";
        chip.onclick = () => { $("command").value = item.command; load(); markActive(chip); };
        chips.appendChild(chip);
      }
    }
    commandsShown = true;
    $("cmdPanel").style.display = "block";
    $("cmdToggle").textContent = "명령어 목록 닫기";
  } catch (e) {
    show($("status"), false, e.message);
  }
}
function markActive(chip) {
  document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
  chip.classList.add("active");
}

async function load() {
  const command = $("command").value.trim();
  if (!command) { show($("status"), false, "명령어 이름을 입력해 주세요."); return; }
  try {
    const data = await req("/command?command=" + encodeURIComponent(command), {});
    if (!data.found) { show($("status"), false, "'/" + command + "' — 등록된 내용이 없어요."); return; }
    $("response").value = data.response;
    $("count").textContent = "(" + data.response.length + "자)";
    show($("status"), true, "'/" + command + "' 불러왔어요.");
  } catch (e) { show($("status"), false, e.message); }
}

async function save() {
  const command = $("command").value.trim();
  const response = $("response").value;
  if (!command || !response.trim()) { show($("status"), false, "명령어와 내용을 모두 입력해 주세요."); return; }
  try {
    const data = await req("/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, response, sender: "웹관리", room_password: roomPw() }),
    });
    show($("status"), true, "저장했어요! /" + data.command + " (" + data.length + "자)");
    if (commandsShown) { commandsShown = false; toggleCommands(); }
  } catch (e) { show($("status"), false, e.message); }
}

async function deleteCommand() {
  const command = $("command").value.trim();
  if (!command) { show($("status"), false, "삭제할 명령어 이름을 입력해 주세요."); return; }
  if (!confirm("'/" + command + "' 명령어를 삭제할까요?")) return;
  try {
    await req("/command?command=" + encodeURIComponent(command) + "&password=" + encodeURIComponent(roomPw()), { method: "DELETE" });
    show($("status"), true, "'/" + command + "' 삭제했어요.");
    $("response").value = "";
    if (commandsShown) { commandsShown = false; toggleCommands(); }
  } catch (e) { show($("status"), false, e.message); }
}

async function setRoomPw() {
  const password = $("pwNew").value;
  const recovery_word = $("pwRecovery").value.trim();
  try {
    await req("/room-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password, recovery_word }),
    });
    show($("pwStatus"), true, "비밀번호를 설정했어요.");
  } catch (e) { show($("pwStatus"), false, e.message); }
}

async function changeRoomPw() {
  const recovery_word = $("pwRecovery2").value.trim();
  const new_password = $("pwNew2").value;
  try {
    await req("/room-password/change", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recovery_word, new_password }),
    });
    show($("pwStatus"), true, "비밀번호를 변경했어요.");
  } catch (e) { show($("pwStatus"), false, e.message); }
}

loadInfo();
</script>
</body>
</html>
"""
