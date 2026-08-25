"""웹 관리 페이지 HTML.

폰 브라우저에서 쓰는 단일 페이지라 외부 리소스 없이 전부 인라인으로 담는다.
비밀 값은 절대 이 페이지에 넣지 않는다 — 키는 /admin#key=... 링크로만 전달된다.
"""

ADMIN_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b283d">
<title>포고정보 관리자</title>
<style>
  :root {
    --red: #e3350d;
    --red-deep: #c11f04;
    --ink: #20232b;
    --bg: #f2f4f7;
    --card: #ffffff;
    --field: #f7f8fa;
    --line: #dfe3e9;
    --line-strong: #cfd4dd;
    --muted: #6f7685;
    --label: #4f5665;
    --success: #17724a;
    --accent-soft: #fff3ef;
    --shadow: 0 1px 2px rgba(28, 32, 43, 0.04), 0 7px 20px rgba(28, 32, 43, 0.045);
    --shadow-open: 0 2px 4px rgba(28, 32, 43, 0.045), 0 14px 32px rgba(28, 32, 43, 0.07);
    --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html { background: var(--bg); scroll-behavior: smooth; }
  body {
    font-family: "Apple SD Gothic Neo", "Pretendard", "Noto Sans KR", sans-serif;
    background: var(--bg);
    color: var(--ink);
    max-width: 720px; margin: 0 auto; line-height: 1.45;
    min-height: 100vh; padding: 16px 14px calc(40px + env(safe-area-inset-bottom));
  }

  @keyframes surface-in {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes content-in {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes notice-in {
    from { opacity: 0; transform: translateY(4px) scale(0.99); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .hero {
    background: #252a34;
    border-left: 4px solid var(--red);
    border-radius: 8px; padding: 18px 18px 16px; color: #fff;
    margin-bottom: 12px; box-shadow: var(--shadow-open);
    animation: surface-in 0.42s var(--ease-out) both;
    transition: transform 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
  }
  .hero .badge {
    display: inline-block; color: #ff9a83;
    font-size: 0.68rem; font-weight: 800; letter-spacing: 0; margin-bottom: 8px;
  }
  .hero h1 { margin: 0; font-size: 1.28rem; font-weight: 800; letter-spacing: 0; }
  .hero p { margin: 7px 0 0; font-size: 0.82rem; color: #cdd1da; line-height: 1.45; }
  .hero.selectable { cursor: pointer; }
  .hero.selectable:hover { transform: translateY(-1px); box-shadow: 0 3px 6px rgba(28, 32, 43, 0.08), 0 18px 38px rgba(28, 32, 43, 0.1); }
  .hero.selectable:focus-visible { outline: 3px solid #fff; outline-offset: 3px; }
  .hero .room-line { font-weight: 800; opacity: 1; }

  .room-grid { display: grid; gap: 8px; margin-top: 14px; }
  .room-choice {
    width: 100%; text-align: left; background: #fff; color: var(--ink);
    border: 1px solid var(--line); border-radius: 8px; padding: 12px 13px;
    box-shadow: none; word-break: break-all;
    transition: border-color 0.18s ease, background 0.18s ease, color 0.18s ease, transform 0.18s var(--ease-out);
  }
  .room-choice:hover { border-color: var(--line-strong); background: #fafbfc; transform: translateY(-1px); }
  .room-choice.active { border-color: var(--red); color: var(--red-deep); background: #fff7f5; }

  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    margin-bottom: 10px; box-shadow: var(--shadow);
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s var(--ease-out);
  }
  body > .card { animation: surface-in 0.38s var(--ease-out) both; }
  section.card { padding: 17px; }
  details.card { overflow: hidden; }
  details.card[open] { border-color: #d5dae2; box-shadow: var(--shadow-open); }
  .card h2 {
    display: flex; align-items: center; gap: 9px;
    font-size: 0.98rem; font-weight: 800; margin: 0 0 4px;
  }
  .card h2 .dot {
    width: 4px; height: 18px; border-radius: 2px; flex: none;
    background: var(--red);
  }

  .section-summary {
    min-height: 58px; padding: 16px 17px; cursor: pointer; list-style: none;
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    user-select: none;
  }
  .section-summary::-webkit-details-marker { display: none; }
  .section-summary { transition: background 0.18s ease, color 0.18s ease; }
  .section-summary:hover { background: #f8f9fb; }
  .section-summary:active { background: #f3f5f8; }
  .section-summary::after {
    content: ""; width: 9px; height: 9px; margin: -4px 5px 0 0; flex: none;
    border-right: 2px solid #747b87; border-bottom: 2px solid #747b87;
    transform: rotate(45deg); transition: transform 0.18s ease, border-color 0.18s ease;
  }
  details.card[open] > .section-summary { border-bottom: 1px solid var(--line); }
  details.card[open] > .section-summary::after { margin-top: 4px; border-color: var(--red-deep); transform: rotate(225deg); }
  .section-title {
    display: flex; align-items: center; gap: 10px; min-width: 0;
    font-size: 0.98rem; font-weight: 800; color: var(--ink);
  }
  .section-title .dot {
    width: 4px; height: 18px; border-radius: 2px; flex: none; background: var(--red);
    transition: height 0.2s var(--ease-out), background 0.2s ease;
  }
  details.card[open] > .section-summary .dot { height: 22px; background: var(--red-deep); }
  .section-body { padding: 4px 17px 17px; }
  details.card[open] > .section-body { animation: content-in 0.24s var(--ease-out) both; }

  .setting-group { border-top: 1px solid var(--line); margin-top: 0; overflow: hidden; }
  .setting-group:first-of-type { border-top: 0; }
  .setting-group > summary {
    min-height: 50px; padding: 14px 0; cursor: pointer; list-style: none;
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    font-size: 0.9rem; font-weight: 800; color: var(--ink);
    transition: color 0.18s ease, background 0.18s ease;
  }
  .setting-group > summary:hover { color: var(--red-deep); }
  .setting-group > summary::-webkit-details-marker { display: none; }
  .setting-group > summary::after {
    content: ""; width: 7px; height: 7px; margin: -3px 4px 0 0; flex: none;
    border-right: 2px solid #8a909b; border-bottom: 2px solid #8a909b;
    transform: rotate(45deg); transition: transform 0.18s ease, border-color 0.18s ease;
  }
  .setting-group[open] > summary::after { margin-top: 3px; border-color: var(--red-deep); transform: rotate(225deg); }
  .setting-body { padding: 0 0 17px; }
  .setting-group[open] > .setting-body { animation: content-in 0.22s var(--ease-out) both; }
  .setting-body > .hint:first-child { margin-top: 0; }

  label {
    display: block; margin: 15px 0 6px; font-weight: 700;
    font-size: 0.78rem; color: var(--label); letter-spacing: 0;
  }
  .hint { font-size: 0.78rem; color: var(--muted); margin: 8px 0 0; line-height: 1.5; }
  input, textarea, select {
    width: 100%; min-height: 44px; padding: 11px 12px; font-size: 0.95rem;
    background: var(--field); color: var(--ink);
    border: 1px solid var(--line); border-radius: 7px;
    font-family: inherit; transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
    appearance: none; -webkit-appearance: none;
  }
  select {
    background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%239094a6' stroke-width='2' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 14px center;
    padding-right: 36px;
  }
  input:focus, textarea:focus, select:focus {
    outline: none; background: #fff; border-color: var(--red);
    box-shadow: 0 0 0 3px rgba(227, 53, 13, 0.11), 0 3px 10px rgba(28, 32, 43, 0.04);
  }
  .checkrow {
    display: flex; align-items: center; gap: 11px; margin-top: 15px;
    color: var(--ink); font-size: 0.88rem; cursor: pointer;
  }
  .checkrow input {
    position: relative; width: 42px; min-height: 24px; height: 24px; padding: 0; flex: none;
    border: 0; border-radius: 999px; background: #c7cbd4;
    appearance: none; -webkit-appearance: none; transition: background 0.18s ease, box-shadow 0.18s ease;
  }
  .checkrow input::after {
    content: ""; position: absolute; width: 18px; height: 18px; left: 3px; top: 3px;
    border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.25);
    transition: transform 0.2s var(--ease-out);
  }
  .checkrow input:checked { background: var(--red); }
  .checkrow input:checked::after { transform: translateX(18px); }
  .checkrow input:focus-visible { box-shadow: 0 0 0 3px rgba(227, 53, 13, 0.16); }
  textarea { min-height: 220px; line-height: 1.5; border-radius: 7px; }

  .cmdrow { display: flex; align-items: stretch; gap: 8px; }
  .cmdrow .slash {
    display: flex; align-items: center; flex: none;
    background: var(--ink); color: #fff; border-radius: 7px;
    padding: 0 15px; font-weight: 800; font-size: 1.05rem;
  }

  .btnrow { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
  button {
    min-height: 44px; border: 0; border-radius: 7px; padding: 11px 15px;
    font-size: 0.93rem; font-weight: 800; cursor: pointer;
    font-family: inherit; transition: transform 0.18s var(--ease-out), filter 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
  }
  button:active { transform: scale(0.97); filter: brightness(0.96); }
  button:focus-visible, summary:focus-visible { outline: 3px solid rgba(227, 53, 13, 0.2); outline-offset: 2px; }
  .primary {
    flex: 1; color: #fff;
    background: var(--red);
  }
  .ghost { background: #eceef4; color: #3a3d4d; }
  .danger { background: transparent; color: var(--red-deep); border: 1.5px solid #f3c1b5; }
  @media (hover: hover) {
    button:hover { transform: translateY(-1px); box-shadow: 0 5px 14px rgba(28, 32, 43, 0.1); }
    .primary:hover { background: var(--red-deep); }
    .ghost:hover { background: #e3e6eb; }
    .danger:hover { background: var(--accent-soft); border-color: #e7a899; }
  }
  #cmdToggle { width: 100%; }

  .chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
  .chip {
    display: inline-flex; align-items: center; gap: 5px;
    background: #fff; border: 1px solid var(--line); border-radius: 999px;
    padding: 7px 13px; font-size: 0.82rem; font-weight: 600; color: var(--ink);
    box-shadow: 0 1px 3px rgba(23, 26, 38, 0.05);
    transition: border-color 0.18s ease, background 0.18s ease, color 0.18s ease, transform 0.18s var(--ease-out);
  }
  .chip:hover { border-color: var(--line-strong); transform: translateY(-1px); }
  .chip small { color: var(--muted); font-weight: 500; }
  .chip.active { background: var(--ink); border-color: var(--ink); color: #fff; }
  .chip.active small { color: rgba(255, 255, 255, 0.65); }

  .toast { margin-top: 12px; font-size: 0.87rem; white-space: pre-wrap; border-radius: 7px; }
  .toast.ok { background: #eaf7ee; color: #17724a; padding: 12px 14px; animation: notice-in 0.24s var(--ease-out) both; }
  .toast.err { background: #fdeeec; color: var(--red-deep); padding: 12px 14px; animation: notice-in 0.24s var(--ease-out) both; }

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

  .linkrow {
    border: 1px solid var(--line); border-radius: 7px; padding: 12px 13px;
    margin-bottom: 9px; background: #fff;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s var(--ease-out);
  }
  .linkrow:hover { border-color: var(--line-strong); box-shadow: 0 5px 14px rgba(28, 32, 43, 0.055); transform: translateY(-1px); }
  .linkrow .rname { font-weight: 700; font-size: 0.88rem; word-break: break-all; }
  .linkrow .rurl {
    font-size: 0.76rem; color: var(--label); word-break: break-all;
    margin: 5px 0 9px; font-family: ui-monospace, Menlo, monospace;
  }
  .linkrow .rmeta { display: flex; align-items: center; gap: 8px; }
  .linkrow .tag {
    font-size: 0.7rem; font-weight: 700; border-radius: 999px; padding: 3px 9px;
  }
  .linkrow .tag.on { background: #eaf7ee; color: #17724a; }
  .linkrow .tag.off { background: #fdeeec; color: var(--red-deep); }
  .linkrow button.copy {
    margin-left: auto; background: #eceef4; color: #3a3d4d;
    padding: 8px 14px; font-size: 0.82rem;
  }
  .admin-list { margin-top: 10px; }
  .adminrow {
    display: flex; align-items: center; gap: 10px; padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }
  .adminrow:last-child { border-bottom: 0; }
  .adminrow .admin-name { flex: 1; min-width: 0; font-weight: 700; word-break: break-all; }
  .adminrow .admin-name small { display: block; color: var(--muted); font-weight: 500; margin-top: 2px; }
  .adminrow button { flex: none; padding: 8px 11px; font-size: 0.78rem; }
  .searchrow { display: flex; align-items: stretch; gap: 8px; }
  .searchrow input { flex: 1; min-width: 0; }
  .searchrow button { flex: none; }
  .incident { border-top: 1px solid var(--line); padding: 13px 0; animation: content-in 0.24s var(--ease-out) both; }
  .incident:first-child { border-top: 0; }
  .incident-head { display: flex; align-items: center; gap: 8px; }
  .incident-name { flex: 1; min-width: 0; font-weight: 800; word-break: break-all; }
  .incident-tag { border-radius: 999px; padding: 4px 8px; font-size: 0.7rem; font-weight: 800; background: #fff1ed; color: var(--red-deep); }
  .incident-meta { color: var(--muted); font-size: 0.73rem; margin-top: 5px; }
  .incident-chat { display: flex; gap: 9px; background: #b9cad8; border: 1px solid #a9bdcd; border-radius: 8px; padding: 12px 10px; margin-top: 9px; }
  .chat-profile { display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; flex: none; border-radius: 8px; background: #fff; color: #596977; font-size: 0.9rem; font-weight: 800; }
  .chat-thread { flex: 1; min-width: 0; }
  .chat-sender { margin-bottom: 5px; color: #27333d; font-size: 0.75rem; font-weight: 700; word-break: break-all; }
  .chat-line { display: flex; align-items: flex-end; gap: 5px; margin-top: 4px; }
  .chat-bubble { max-width: calc(100% - 48px); background: #fff; border-radius: 2px 7px 7px 7px; padding: 8px 10px; color: #20242a; font-size: 0.84rem; line-height: 1.42; white-space: pre-wrap; word-break: break-word; box-shadow: 0 1px 1px rgba(20,34,44,0.08); }
  .chat-time { color: #53636f; font-size: 0.62rem; white-space: nowrap; }
  .chat-duration { margin-top: 9px; padding-top: 8px; border-top: 1px solid rgba(72,94,110,0.2); color: #3d4d59; font-size: 0.72rem; font-weight: 700; }
  .incident-question { margin: 11px 0 0; font-size: 0.8rem; font-weight: 700; color: var(--label); }
  .incident-actions { display: flex; gap: 7px; margin-top: 7px; }
  .incident-actions button { flex: 1; padding: 8px 11px; font-size: 0.8rem; }
  @media (max-width: 420px) {
    body { padding-left: 10px; padding-right: 10px; }
    .hero { padding: 17px 15px 15px; }
    section.card { padding: 15px; }
    .section-summary { min-height: 56px; padding: 14px 15px; }
    .section-body { padding: 3px 15px 15px; }
    .btnrow > button { flex: 1 1 120px; }
    .incident-actions > button { flex: 1 1 0; }
    .linkrow .rmeta { flex-wrap: wrap; }
    .linkrow button.copy { margin-left: 0; width: 100%; }
  }
  @media (prefers-reduced-motion: reduce) {
    html { scroll-behavior: auto; }
    *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
  }

  /* Trainer Lab control system */
  :root {
    --navy: #0b283d;
    --navy-2: #123c57;
    --cyan: #11aebd;
    --cyan-deep: #087985;
    --cyan-soft: #e6f7f8;
    --yellow: #f2c84b;
    --coral: #e76352;
    --red: var(--coral);
    --red-deep: #c84b3e;
    --ink: #132936;
    --bg: #edf3f6;
    --card: #ffffff;
    --field: #f4f8fa;
    --line: #d6e2e7;
    --line-strong: #bcd0d8;
    --muted: #6d818c;
    --label: #3f5967;
    --accent-soft: #fff1ee;
    --shadow: 0 1px 2px rgba(11, 40, 61, 0.04), 0 8px 24px rgba(11, 40, 61, 0.055);
    --shadow-open: 0 2px 4px rgba(11, 40, 61, 0.05), 0 16px 38px rgba(11, 40, 61, 0.09);
  }
  html { background: var(--bg); }
  body {
    max-width: 920px;
    padding: 22px 18px calc(44px + env(safe-area-inset-bottom));
    background: var(--bg);
  }
  .hero {
    position: relative;
    overflow: hidden;
    margin-bottom: 0;
    padding: 22px;
    border: 1px solid #17465f;
    border-left: 1px solid #17465f;
    border-radius: 8px;
    background: var(--navy);
    box-shadow: 0 18px 42px rgba(11, 40, 61, 0.16);
    isolation: isolate;
  }
  .hero::after {
    content: "";
    position: absolute;
    z-index: -1;
    right: -52px;
    bottom: -78px;
    width: 154px;
    height: 154px;
    border: 1px solid rgba(17, 174, 189, 0.26);
    border-radius: 50%;
    box-shadow: 0 0 0 24px rgba(17, 174, 189, 0.08), 0 0 0 48px rgba(17, 174, 189, 0.04);
  }
  .hero.selectable:hover {
    transform: translateY(-1px);
    box-shadow: 0 22px 48px rgba(11, 40, 61, 0.2);
  }
  .hero.selectable:focus-visible { outline-color: var(--yellow); }
  .hero-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
  .brand-lockup { display: flex; align-items: center; min-width: 0; gap: 14px; }
  .brand-mark {
    width: 68px;
    height: 68px;
    flex: none;
    object-fit: contain;
    filter: drop-shadow(0 8px 14px rgba(0, 0, 0, 0.24));
  }
  .brand-copy { min-width: 0; }
  .hero .badge {
    display: block;
    margin: 0 0 4px;
    color: #71dce4;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 0;
  }
  .hero h1 { font-size: 1.42rem; line-height: 1.25; }
  .system-status {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    flex: none;
    padding: 7px 9px;
    border: 1px solid rgba(113, 220, 228, 0.28);
    border-radius: 999px;
    color: #d8fbfd;
    background: rgba(17, 174, 189, 0.1);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.62rem;
    font-weight: 800;
  }
  .system-status i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #4fe2c0;
    box-shadow: 0 0 0 4px rgba(79, 226, 192, 0.12);
    animation: status-pulse 2.4s ease-in-out infinite;
  }
  @keyframes status-pulse {
    50% { box-shadow: 0 0 0 7px rgba(79, 226, 192, 0.02); }
  }
  .hero-context {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 4px 18px;
    align-items: end;
    margin-top: 18px;
    padding-top: 15px;
    border-top: 1px solid rgba(216, 251, 253, 0.13);
  }
  .context-label {
    grid-column: 1 / -1;
    color: var(--yellow);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.62rem;
    font-weight: 800;
  }
  .hero .room-line { color: #fff; font-size: 0.92rem; word-break: break-all; }
  .context-action { color: #9db6c3; font-size: 0.72rem; text-align: right; }
  .control-stack { counter-reset: module; }
  .group-label {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 9px;
    margin: 26px 5px 9px;
  }
  .group-label::after { content: ""; grid-column: 2; grid-row: 1; height: 1px; background: var(--line-strong); }
  .group-label span {
    grid-column: 1;
    grid-row: 1;
    color: var(--cyan-deep);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.64rem;
    font-weight: 900;
  }
  .group-label strong { grid-column: 1 / 3; grid-row: 2; font-size: 0.96rem; color: var(--navy); }
  .group-label small { grid-column: 3; grid-row: 2; color: var(--muted); font-size: 0.7rem; text-align: right; }
  .card {
    margin-bottom: 9px;
    border-color: var(--line);
    background: var(--card);
    box-shadow: var(--shadow);
  }
  .control-stack > .card { animation: surface-in 0.38s var(--ease-out) both; }
  details.card { counter-increment: module; }
  details.card[open] { border-color: #bcd6dd; box-shadow: var(--shadow-open); }
  .section-summary { min-height: 76px; padding: 13px 17px; }
  .section-summary:hover { background: #f8fcfc; }
  .section-summary:active { background: #f0f7f8; }
  .section-title { gap: 13px; }
  .section-title .dot { display: none; }
  .section-title::before {
    content: counter(module, decimal-leading-zero);
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    flex: none;
    border: 1px solid #c3e7ea;
    border-radius: 8px;
    background: var(--cyan-soft);
    color: var(--cyan-deep);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.72rem;
    font-weight: 900;
    transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
  }
  details.card[open] > .section-summary .section-title::before {
    border-color: var(--navy);
    color: #fff;
    background: var(--navy);
  }
  .title-copy { display: block; min-width: 0; }
  .title-copy strong { display: block; color: var(--ink); font-size: 0.96rem; line-height: 1.35; }
  .title-copy small { display: block; margin-top: 3px; color: var(--muted); font-size: 0.7rem; font-weight: 600; line-height: 1.35; }
  .section-summary::after { border-color: #7a919b; }
  details.card[open] > .section-summary {
    border-bottom-color: var(--line);
    background: #fbfdfd;
  }
  details.card[open] > .section-summary::after { border-color: var(--cyan-deep); }
  .section-body { padding: 6px 18px 20px; }
  .setting-group { border-top-color: var(--line); }
  .setting-group > summary { position: relative; min-height: 54px; padding: 15px 0 15px 18px; }
  .setting-group > summary::before {
    content: "";
    position: absolute;
    left: 2px;
    width: 6px;
    height: 6px;
    border: 2px solid var(--cyan);
    transform: rotate(45deg);
  }
  .setting-group > summary:hover { color: var(--cyan-deep); }
  .setting-group[open] > summary::after { border-color: var(--cyan-deep); }
  label { color: var(--label); font-size: 0.76rem; }
  input, textarea, select {
    min-height: 48px;
    padding: 12px 13px;
    border-color: var(--line);
    background: var(--field);
  }
  input:focus, textarea:focus, select:focus {
    border-color: var(--cyan);
    box-shadow: 0 0 0 3px rgba(17, 174, 189, 0.13), 0 4px 12px rgba(11, 40, 61, 0.05);
  }
  #response {
    min-height: 380px;
    padding: 16px;
    line-height: 1.65;
    resize: vertical;
  }
  .checkrow input:checked { background: var(--cyan-deep); }
  .checkrow input:focus-visible { box-shadow: 0 0 0 3px rgba(17, 174, 189, 0.15); }
  .cmdrow .slash { background: var(--navy); }
  button:focus-visible, summary:focus-visible { outline-color: rgba(17, 174, 189, 0.28); }
  .primary { background: var(--navy-2); }
  .ghost { background: #e5eef2; color: #264553; }
  .danger { color: var(--red-deep); border-color: #efbeb7; }
  @media (hover: hover) {
    .primary:hover { background: var(--cyan-deep); }
    .ghost:hover { background: #d9e7ec; }
  }
  .room-choice { border-color: var(--line); background: #fff; }
  .room-choice.active { border-color: var(--cyan); color: var(--cyan-deep); background: var(--cyan-soft); }
  .chip.active { border-color: var(--navy); background: var(--navy); }
  .linkrow { border-color: var(--line); background: var(--field); }
  .linkrow .tag.on { background: #e4f7ef; color: #147056; }
  .incident-tag { background: #fff0ed; color: var(--red-deep); }
  .incident-chat { border-color: #aac2ce; background: #c4d5de; }
  footer {
    gap: 8px;
    margin-top: 26px;
    color: #77909c;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-weight: 700;
  }
  footer img { width: 23px; height: 23px; object-fit: contain; }
  @media (min-width: 760px) {
    body { padding-top: 28px; }
    .hero { padding: 25px 27px 23px; }
    .brand-mark { width: 76px; height: 76px; }
    .hero h1 { font-size: 1.58rem; }
    .section-summary { padding-left: 20px; padding-right: 20px; }
    .section-body { padding-left: 21px; padding-right: 21px; }
  }
  @media (max-width: 520px) {
    body { padding: 10px 9px calc(34px + env(safe-area-inset-bottom)); }
    .hero { padding: 16px; }
    .brand-lockup { gap: 10px; }
    .brand-mark { width: 56px; height: 56px; }
    .hero h1 { font-size: 1.18rem; }
    .system-status { padding: 6px 7px; font-size: 0.56rem; }
    .hero-context { grid-template-columns: 1fr; }
    .context-action { text-align: left; }
    .group-label { margin-top: 22px; }
    .group-label small { grid-column: 1 / -1; grid-row: 3; margin-top: 1px; text-align: left; }
    .section-summary { min-height: 70px; padding: 12px 13px; }
    .section-title { gap: 10px; }
    .section-title::before { width: 38px; height: 38px; }
    .title-copy strong { font-size: 0.91rem; }
    #response { min-height: 300px; }
    .title-copy small { font-size: 0.67rem; }
    .section-body { padding: 5px 14px 17px; }
  }
</style>
</head>
<body>
<header class="hero selectable" id="roomHero" role="button" tabindex="0"
  aria-controls="roomPicker" aria-expanded="false" onclick="toggleRoomPicker()">
  <div class="hero-head">
    <div class="brand-lockup">
      <img class="brand-mark" src="/ui-assets/kakaopogo-control-mark.webp" alt="">
      <div class="brand-copy">
        <span class="badge">KAKAOPOGO LAB · OWNER</span>
        <h1>포고정보 운영센터</h1>
      </div>
    </div>
    <span class="system-status"><i></i>ONLINE</span>
  </div>
  <div class="hero-context">
    <span class="context-label">ACTIVE TRAINER ROOM</span>
    <strong class="room-line" id="heroRoom">대상 방을 선택해 주세요</strong>
    <span class="context-action">배너를 눌러 관리할 채팅방을 변경합니다</span>
  </div>
</header>

<main class="control-stack">
<div class="group-label"><span>CONNECTION</span><strong>운영센터 접속</strong><small>관리 키와 대상 방을 확인합니다</small></div>

<details class="card" data-section="access" open>
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>접속 정보</strong><small>운영센터 인증과 대상 방 선택</small></span></span></summary>
  <div class="section-body">
  <label for="key">관리 키</label>
  <input id="key" type="password" placeholder="관리 키를 입력하세요">
  <p class="hint">관리방에 공유된 링크로 들어왔다면 자동으로 채워져 있어요.</p>
  </div>
</details>

<section class="card" id="roomPicker" style="display:none">
  <h2><span class="dot"></span>대상 방 선택</h2>
  <p class="hint">관리할 채팅방을 선택하세요. 아래 모든 관리 기능이 선택한 방에만 적용됩니다.</p>
  <div class="room-grid" id="roomGrid"></div>
</section>

<div class="group-label"><span>PEOPLE & REWARDS</span><strong>구성원 운영</strong><small>관리 권한과 추첨 이력을 관리합니다</small></div>

<details class="card" data-section="room-admins">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>방 관리자</strong><small>운영 권한을 부여하거나 회수합니다</small></span></span></summary>
  <div class="section-body">
  <p class="hint" id="adminRoomHint">먼저 위 배너에서 대상 방을 선택해 주세요.</p>

  <label>현재 관리자</label>
  <div class="admin-list" id="adminList"><p class="hint">선택된 방이 없습니다.</p></div>

  <label for="adminMemberSearch">관리자 닉네임 검색</label>
  <div class="searchrow">
    <input id="adminMemberSearch" placeholder="닉네임 일부를 입력하세요" autocomplete="off">
    <button class="ghost" type="button" onclick="searchRoomAdminCandidates()">검색</button>
  </div>
  <p class="hint">예: ‘박화’를 검색하면 박화영, 박화진처럼 일치하는 사용자가 나옵니다. 봇이 이 방에서 확인한 사용자만 검색됩니다.</p>
  <div class="admin-list" id="adminCandidateList"><p class="hint">닉네임을 검색해 주세요.</p></div>
  <div id="adminStatus" class="toast"></div>
  </div>
</details>

<details class="card" data-section="raffle-recipients">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>추첨 상품 수령자</strong><small>수령 등록과 재추첨 제외 기간 관리</small></span></span></summary>
  <div class="section-body">
  <p class="hint" id="raffleRoomHint">먼저 위 배너에서 대상 방을 선택해 주세요.</p>
  <label for="raffleRecipientSearch">수령자 닉네임 검색</label>
  <div class="searchrow">
    <input id="raffleRecipientSearch" placeholder="닉네임 일부를 입력하세요" autocomplete="off">
    <button class="ghost" type="button" onclick="refreshRaffleRecipients()">검색</button>
  </div>
  <p class="hint">상품을 실제로 전달한 사람만 등록하세요. 등록한 날부터 7일 동안 추첨 대상에서 제외됩니다.</p>
  <div class="admin-list" id="raffleCandidateList"><p class="hint">닉네임을 검색해 주세요.</p></div>
  <label>최근 수령 등록</label>
  <div class="admin-list" id="raffleRecipientList"><p class="hint">선택된 방이 없습니다.</p></div>
  <div id="raffleRecipientStatus" class="toast"></div>
  </div>
</details>

<div class="group-label"><span>AUTOMATION & SAFETY</span><strong>자동화와 안전</strong><small>방 정책, 문체 감지, 학습 데이터를 설정합니다</small></div>

<details class="card" data-section="room-settings">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>방 운영 설정</strong><small>들낙, 포인트 상점, 문체 정책</small></span></span></summary>
  <div class="section-body">
  <p class="hint" id="joinAlertRoomHint">먼저 위 배너에서 대상 방을 선택해 주세요.</p>
  <details class="setting-group" data-section="join-alerts">
    <summary>들낙 관리</summary>
    <div class="setting-body">
    <p class="hint">반복 입장이 많은 사용자의 안내 기준을 설정합니다.</p>
    <label for="joinAlertThreshold">들낙 안내 출력 기준 횟수</label>
    <input id="joinAlertThreshold" type="number" min="2" max="100" step="1" value="5">
    <p class="hint">입장 횟수가 기준 이상일 때만 들낙 의심 안내를 전송합니다. 기본값은 5회입니다.</p>
    </div>
  </details>
  <details class="setting-group" data-section="point-shop">
    <summary>포인트 상점</summary>
    <div class="setting-body">
    <label class="checkrow" for="shopRegistrationAdminOnly">
      <input id="shopRegistrationAdminOnly" type="checkbox" checked onchange="toggleShopRegistrationCosts()">
      <span>상품 등록을 오너와 관리자만 허용</span>
    </label>
    <p class="hint">끄면 일반 사용자도 /상품등록 명령어를 사용할 수 있습니다.</p>
    <div id="shopRegistrationCosts" style="display:none">
      <label for="shopRegistrationFee">일반 사용자 상품 등록 수수료</label>
      <input id="shopRegistrationFee" type="number" min="0" max="1000000" step="1" value="100">
      <p class="hint">등록 즉시 차감되며 판매 여부와 관계없이 반환되지 않습니다. 기본값은 100P입니다.</p>
      <label for="shopRegistrationDeposit">일반 사용자 상품 등록 보증금</label>
      <input id="shopRegistrationDeposit" type="number" min="0" max="1000000" step="1" value="0">
      <p class="hint">상품이 판매되면 등록자에게 반환됩니다. 기본값은 0P입니다.</p>
    </div>
    </div>
  </details>
  <details class="setting-group" data-section="moderation-settings">
    <summary>문체 관찰</summary>
    <div class="setting-body">
    <label class="checkrow" for="moderationObservationEnabled">
      <input id="moderationObservationEnabled" type="checkbox" checked>
      <span>학습용 문체 관찰 및 사례 수집</span>
    </label>
    <p class="hint">감지 사례와 학습용 데이터 수집을 켭니다. 채팅방 경고는 사례 수집이 켜져 있을 때만 사용할 수 있습니다.</p>
    <label class="checkrow" for="moderationFragmentWarningEnabled">
      <input id="moderationFragmentWarningEnabled" type="checkbox" checked>
      <span>단타 감지 시 채팅방 경고 출력</span>
    </label>
    <label class="checkrow" for="moderationEumsWarningEnabled">
      <input id="moderationEumsWarningEnabled" type="checkbox" checked>
      <span>음슴체 감지 시 채팅방 경고 출력</span>
    </label>
    <p class="hint">경고를 끄면 채팅방 문구만 사라지며 감지 사례와 학습 자료는 그대로 저장됩니다.</p>
    <label for="moderationFragmentCount">단타 기준 메시지 수</label>
    <input id="moderationFragmentCount" type="number" min="2" max="10" step="1" value="2">
    <label for="moderationFragmentWindow">단타 관찰 시간(초)</label>
    <input id="moderationFragmentWindow" type="number" min="5" max="60" step="1" value="12">
    <label for="moderationEumsCount">음슴체 관찰 기준 횟수</label>
    <input id="moderationEumsCount" type="number" min="1" max="10" step="1" value="1">
    </div>
  </details>
  <div class="btnrow">
    <button class="primary" type="button" onclick="saveJoinAlertSettings()">설정 저장</button>
  </div>
  <div id="joinAlertStatus" class="toast"></div>
  </div>
</details>

<details class="card" data-section="moderation-model">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>자동 학습 모델</strong><small>학습 현황과 재학습 상태 확인</small></span></span></summary>
  <div class="section-body">
  <p class="hint" id="moderationModelStatus">관리 키를 입력하면 모델 상태를 확인합니다.</p>
  <div class="btnrow">
    <button class="primary" type="button" onclick="trainModerationModel()">지금 재학습</button>
    <button class="ghost" type="button" onclick="rollbackModerationModel()">이전 모델 복구</button>
  </div>
  <div id="moderationModelMessage" class="toast"></div>
  </div>
</details>

<details class="card" data-section="moderation-review">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>문체 관찰 및 학습</strong><small>감지 사례를 검토하고 판정합니다</small></span></span></summary>
  <div class="section-body">
  <p class="hint" id="moderationRoomHint">먼저 위 배너에서 대상 방을 선택해 주세요.</p>
  <p class="hint" id="moderationCounts">정확함 또는 오탐을 선택하면 다음 자동 학습에 반영됩니다.</p>
  <label for="moderationStatus">표시할 사례</label>
  <select id="moderationStatus" onchange="refreshModerationIncidents()">
    <option value="pending">판정 대기</option>
    <option value="all">전체</option>
    <option value="confirmed">정확함</option>
    <option value="dismissed">오탐</option>
  </select>
  <div class="btnrow"><button class="ghost" type="button" onclick="refreshModerationIncidents()">새로고침</button></div>
  <div id="moderationList"><p class="hint">선택된 방이 없습니다.</p></div>
  <div id="moderationStatusMessage" class="toast"></div>
  </div>
</details>

<div class="group-label"><span>BOT TOOLKIT</span><strong>봇 관리 도구</strong><small>명령어, 관리 링크, 방 데이터를 다룹니다</small></div>

<details class="card" data-section="commands">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>명령어 관리</strong><small>방 전용 응답을 등록하고 수정합니다</small></span></span></summary>
  <div class="section-body">
  <label for="roomSelect">방 선택</label>
  <select id="roomSelect">
    <option value="">키를 입력하면 방 목록이 나와요</option>
  </select>
  <input id="room" placeholder="새 방 이름 (봇이 보는 이름과 정확히 같아야 함)"
    style="display:none; margin-top:8px">

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
  </div>
</details>

<details class="card" data-section="room-site">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>전용 명령어 관리 사이트</strong><small>방 운영진에게 공유할 링크를 발급합니다</small></span></span></summary>
  <div class="section-body">
  <p class="hint" id="siteRoomHint">먼저 위 배너에서 대상 방을 선택해 주세요.</p>
  <div id="siteSetupFields" style="display:none">
    <label for="sitePassword">사이트 비밀번호</label>
    <input id="sitePassword" type="password" placeholder="4자 이상">
    <label for="siteRecovery">복구 단어</label>
    <input id="siteRecovery" placeholder="비밀번호를 바꿀 때 사용할 단어">
    <p class="hint">처음 발급할 때만 설정합니다. 전용 사이트를 공유할 때 비밀번호도 따로 전달해 주세요.</p>
  </div>
  <div class="btnrow">
    <button class="primary" id="siteIssueButton" type="button" onclick="issueRoomSite()">전용 사이트 만들기</button>
  </div>
  <div id="siteResult" style="display:none; margin-top:12px">
    <div class="linkrow">
      <div class="rname" id="siteResultRoom"></div>
      <div class="rurl" id="siteUrl"></div>
      <div class="rmeta">
        <span class="tag on">비밀번호 보호</span>
        <button class="copy" type="button" onclick="copyCurrentSite(this)">링크 복사</button>
        <button class="copy" type="button" onclick="openCurrentSite()">열기</button>
      </div>
    </div>
  </div>
  <div id="siteStatus" class="toast"></div>
  </div>
</details>

<details class="card" data-section="room-password">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>방 비밀번호</strong><small>관리 페이지 인증 정보를 설정합니다</small></span></span></summary>
  <div class="section-body">
    <p class="hint">비밀번호를 설정하면 그 방의 명령어는 비밀번호를 아는 사람만
    수정·삭제할 수 있어요. 복구 단어는 비밀번호를 바꿀 때 쓰는 열쇠이니
    잊지 마세요!</p>
    <label for="pwRoom">대상 방</label>
    <input id="pwRoom" list="rooms" placeholder="방 이름 (목록에서 선택)">

    <label>처음 설정 — 비밀번호 / 복구 단어</label>
    <input id="pwNew" type="password" placeholder="비밀번호 (4자 이상)">
    <input id="pwRecovery" placeholder="복구 단어 (변경할 때 필요)" style="margin-top:6px">
    <div class="btnrow">
      <button class="ghost" onclick="setRoomPw()">비밀번호 설정</button>
    </div>

    <label>변경 — 복구 단어 / 새 비밀번호</label>
    <input id="pwRecovery2" placeholder="설정할 때 정한 복구 단어">
    <input id="pwNew2" type="password" placeholder="새 비밀번호 (4자 이상)" style="margin-top:6px">
    <div class="btnrow">
      <button class="ghost" onclick="changeRoomPw()">비밀번호 변경</button>
    </div>
    <div id="pwStatus" class="toast"></div>
  </div>
</details>

<details class="card" data-section="room-rename">
  <summary class="section-summary"><span class="section-title"><span class="dot"></span><span class="title-copy"><strong>방 이름 변경 이전</strong><small>이전 방 데이터를 새 이름으로 연결합니다</small></span></span></summary>
  <div class="section-body">
    <p class="hint">카톡방 제목이 바뀌면 봇이 새로운 방으로 인식해 명령어·관리자·출석이
    끊깁니다. 옛 이름의 데이터를 새 이름으로 옮깁니다.</p>
    <label for="oldRoom">옛 방 이름</label>
    <input id="oldRoom" list="rooms" placeholder="바뀌기 전 방 제목">
    <label for="newRoom">새 방 이름</label>
    <input id="newRoom" placeholder="바뀐 후 방 제목 (정확히)">
    <label for="oldRoomPw">옛 방 비밀번호 (설정된 경우만)</label>
    <input id="oldRoomPw" type="password" placeholder="없으면 비워두세요">
    <div class="btnrow">
      <button class="ghost" onclick="renameRoom()">이전 실행</button>
    </div>
    <div id="renameStatus" class="toast"></div>
  </div>
</details>

<datalist id="rooms"></datalist>
</main>
<footer><img src="/ui-assets/kakaopogo-control-mark.webp" alt="">KakaoPoGo Trainer Operations</footer>

<script>
const $ = (id) => document.getElementById(id);

function initSectionState() {
  const prefix = "kpg-admin-section:";
  document.querySelectorAll("details[data-section]").forEach((panel) => {
    const key = prefix + panel.dataset.section;
    try {
      const saved = localStorage.getItem(key);
      if (saved !== null) panel.open = saved === "open";
      panel.addEventListener("toggle", () => {
        localStorage.setItem(key, panel.open ? "open" : "closed");
      });
    } catch (error) {}
  });
}

function initAccordionMotion() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  document.querySelectorAll("details.card, details.setting-group").forEach((panel) => {
    const summary = panel.querySelector(":scope > summary");
    const content = summary && summary.nextElementSibling;
    if (!summary || !content) return;
    let moving = false;
    summary.addEventListener("click", (event) => {
      event.preventDefault();
      if (moving) return;
      moving = true;

      const opening = !panel.open;
      const startHeight = panel.getBoundingClientRect().height;
      if (opening) panel.open = true;
      const summaryHeight = summary.getBoundingClientRect().height;
      const contentHeight = content.getBoundingClientRect().height;
      const frameHeight = Math.max(0, panel.getBoundingClientRect().height - summaryHeight - contentHeight);
      const endHeight = summaryHeight + frameHeight + (opening ? contentHeight : 0);

      panel.style.height = startHeight + "px";
      panel.style.overflow = "hidden";
      panel.style.transition = "height " + (opening ? 260 : 220) + "ms cubic-bezier(0.22, 1, 0.36, 1)";

      let finished = false;
      const finish = (transitionEvent) => {
        if (transitionEvent && (transitionEvent.target !== panel || transitionEvent.propertyName !== "height")) return;
        if (finished) return;
        finished = true;
        panel.removeEventListener("transitionend", finish);
        if (!opening) panel.open = false;
        panel.style.height = "";
        panel.style.transition = "";
        panel.style.overflow = "";
        moving = false;
      };
      panel.addEventListener("transitionend", finish);
      setTimeout(finish, opening ? 340 : 300);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        panel.style.height = endHeight + "px";
      }));
    });
  });
}

initSectionState();
initAccordionMotion();
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

function roomPw() {
  return $("roomPw").value;
}

function updateHeroRoom() {
  const room = currentRoom();
  $("heroRoom").textContent = room && room !== "__custom__"
    ? "선택된 방 · " + room
    : "대상 방을 선택해 주세요";
}

function toggleRoomPicker() {
  const picker = $("roomPicker");
  const opening = picker.style.display === "none";
  picker.style.display = opening ? "block" : "none";
  $("roomHero").setAttribute("aria-expanded", opening ? "true" : "false");
  if (opening && !$("key").value) {
    $("roomGrid").innerHTML = '<p class="hint">관리 키를 입력하면 봇이 있는 방 목록이 나옵니다.</p>';
  }
}

$("roomHero").addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    toggleRoomPicker();
  }
});

function renderRoomChoices(names) {
  const grid = $("roomGrid");
  grid.innerHTML = "";
  if (!names.length) {
    grid.innerHTML = '<p class="hint">봇이 확인한 채팅방이 아직 없습니다.</p>';
    return;
  }
  names.forEach((room) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "room-choice" + (room === currentRoom() ? " active" : "");
    button.textContent = room;
    button.onclick = () => selectTargetRoom(room);
    grid.appendChild(button);
  });
}

function selectTargetRoom(room) {
  $("roomSelect").value = room;
  $("roomSelect").dispatchEvent(new Event("change"));
  $("roomPicker").style.display = "none";
  $("roomHero").setAttribute("aria-expanded", "false");
  renderRoomChoices(Array.from($("roomSelect").options)
    .map((item) => item.value).filter((value) => value && value !== "__custom__"));
}

$("roomSelect").addEventListener("change", () => {
  $("room").style.display = $("roomSelect").value === "__custom__" ? "block" : "none";
  localStorage.setItem("kpg-room", currentRoom());
  // 방마다 저장해 둔 비밀번호를 불러온다.
  $("roomPw").value = localStorage.getItem("kpg-pw:" + currentRoom()) || "";
  // 방이 바뀌면 목록을 닫는다. 다시 열면 그 방의 명령어가 나온다.
  hideCommands();
  updateHeroRoom();
  refreshRoomAccess();
  refreshRaffleRecipients();
  refreshJoinAlertSettings();
  refreshModerationIncidents();
  refreshRoomSite();
});

$("roomPw").addEventListener("change", () => {
  localStorage.setItem("kpg-pw:" + currentRoom(), $("roomPw").value);
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

let siteRooms = [];
async function refreshRooms() {
  if (!$("key").value) return;
  const res = await fetch("/admin/rooms", { headers: headers() });
  if (!res.ok) return;
  const customRooms = await res.json();
  // 레지스트리(봇이 속한 모든 방)도 합쳐 빈 방까지 고를 수 있게 한다.
  siteRooms = [];
  try {
    const sr = await fetch("/admin/site-rooms", { headers: headers() });
    if (sr.ok) siteRooms = await sr.json();
  } catch (e) {}
  const names = [];
  siteRooms.forEach((r) => { if (!names.includes(r.room)) names.push(r.room); });
  customRooms.forEach((r) => { if (!names.includes(r)) names.push(r); });

  const saved = localStorage.getItem("kpg-room") || "";
  const select = $("roomSelect");
  select.innerHTML = "";
  names.forEach((r) => select.appendChild(option(r, r)));
  select.appendChild(option("__custom__", "＋ 새 방 이름 직접 입력"));
  if (names.includes(saved)) select.value = saved;
  else if (names.length) select.value = names[0];
  $("rooms").innerHTML = "";
  names.forEach((r) => $("rooms").appendChild(option(r, r)));
  $("roomPw").value = localStorage.getItem("kpg-pw:" + currentRoom()) || "";
  renderRoomChoices(names);
  updateHeroRoom();
  refreshRoomAccess();
  refreshRaffleRecipients();
  refreshJoinAlertSettings();
  refreshRoomSite();
  refreshModerationModel();
}
$("key").addEventListener("change", refreshRooms);
refreshRooms();

function adminOut(message, ok) {
  $("adminStatus").textContent = message;
  $("adminStatus").className = "toast " + (ok ? "ok" : "err");
}

async function refreshRoomAccess() {
  const room = currentRoom();
  const list = $("adminList");
  const candidateList = $("adminCandidateList");
  $("adminStatus").textContent = "";
  $("adminStatus").className = "toast";
  $("adminMemberSearch").value = "";

  if (!room || $("roomSelect").value === "__custom__") {
    $("adminRoomHint").textContent = "먼저 위 배너에서 대상 방을 선택해 주세요.";
    list.innerHTML = '<p class="hint">선택된 방이 없습니다.</p>';
    candidateList.innerHTML = '<p class="hint">대상 방을 먼저 선택해 주세요.</p>';
    return;
  }
  $("adminRoomHint").textContent = "대상 방 · " + room;
  list.innerHTML = '<p class="hint">관리자 목록을 불러오는 중입니다.</p>';
  candidateList.innerHTML = '<p class="hint">닉네임을 검색해 주세요.</p>';

  const params = new URLSearchParams({ room: room });
  let adminRes;
  try {
    adminRes = await fetch("/admin/room-admins?" + params, { headers: headers() });
  } catch (error) {
    list.innerHTML = '<p class="hint">서버에 연결하지 못했습니다.</p>';
    return;
  }
  if (adminRes.status === 403) {
    list.innerHTML = '<p class="hint">관리 키가 올바르지 않습니다.</p>';
    return;
  }
  if (!adminRes.ok) {
    list.innerHTML = '<p class="hint">방 정보를 불러오지 못했습니다.</p>';
    return;
  }

  const admins = await adminRes.json();
  renderRoomAdmins(admins);
}

function renderRoomAdmins(admins) {
  const list = $("adminList");
  list.innerHTML = "";
  if (!admins.length) {
    list.innerHTML = '<p class="hint">이 방에 지정된 관리자가 없습니다.</p>';
    return;
  }
  admins.forEach((admin) => {
    const row = document.createElement("div");
    row.className = "adminrow";
    const name = document.createElement("div");
    name.className = "admin-name";
    name.textContent = admin.nickname;
    const role = document.createElement("small");
    role.textContent = "방 관리자";
    name.appendChild(role);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "해제";
    remove.onclick = () => removeRoomAdmin(admin.userKey, admin.nickname);
    row.appendChild(name);
    row.appendChild(remove);
    list.appendChild(row);
  });
}

function renderAdminCandidates(members, query) {
  const list = $("adminCandidateList");
  list.innerHTML = "";
  if (!query) {
    list.innerHTML = '<p class="hint">닉네임 일부를 입력해 주세요.</p>';
    return;
  }
  const candidates = members.filter((member) => !member.isAdmin);
  if (!candidates.length) {
    list.innerHTML = '<p class="hint">추가할 수 있는 일치 사용자가 없습니다.</p>';
    return;
  }
  candidates.forEach((member) => {
    const row = document.createElement("div");
    row.className = "adminrow";
    const name = document.createElement("div");
    name.className = "admin-name";
    name.textContent = member.nickname;
    const add = document.createElement("button");
    add.type = "button";
    add.className = "primary";
    add.textContent = "관리자 추가";
    add.onclick = () => saveRoomAdmin({
      user_key: member.userKey,
      nickname: member.nickname,
    });
    row.appendChild(name);
    row.appendChild(add);
    list.appendChild(row);
  });
}

async function searchRoomAdminCandidates() {
  const room = currentRoom();
  const query = $("adminMemberSearch").value.trim();
  if (!room || $("roomSelect").value === "__custom__") {
    return adminOut("대상 방을 먼저 선택해 주세요.", false);
  }
  if (!query) {
    renderAdminCandidates([], "");
    return;
  }
  const params = new URLSearchParams({ room: room, query: query });
  try {
    const res = await fetch("/admin/room-members?" + params, { headers: headers() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "사용자를 검색하지 못했습니다.");
    renderAdminCandidates(data, query);
    $("adminStatus").className = "toast";
    $("adminStatus").textContent = "";
  } catch (error) {
    adminOut(error.message, false);
  }
}

async function saveRoomAdmin(person) {
  const room = currentRoom();
  if (!room || $("roomSelect").value === "__custom__") {
    return adminOut("대상 방을 먼저 선택해 주세요.", false);
  }
  const res = await fetch("/admin/room-admin", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ room: room, ...person }),
  });
  const data = await res.json();
  if (!res.ok) return adminOut(data.detail || "관리자 추가에 실패했습니다.", false);
  $("adminMemberSearch").value = "";
  adminOut(data.nickname + " 님을 이 방의 관리자로 추가했습니다.", true);
  await refreshRoomAccess();
  adminOut(data.nickname + " 님을 이 방의 관리자로 추가했습니다.", true);
}

async function removeRoomAdmin(userKey, nickname) {
  if (!confirm(nickname + " 님의 방 관리자 권한을 해제할까요?")) return;
  const params = new URLSearchParams({ room: currentRoom(), user_key: userKey });
  const res = await fetch("/admin/room-admin?" + params, {
    method: "DELETE",
    headers: headers(),
  });
  const data = await res.json();
  if (!res.ok) return adminOut(data.detail || "관리자 해제에 실패했습니다.", false);
  await refreshRoomAccess();
  adminOut(data.nickname + " 님의 관리자 권한을 해제했습니다.", true);
}

let adminSearchTimer = null;
$("adminMemberSearch").addEventListener("input", () => {
  clearTimeout(adminSearchTimer);
  adminSearchTimer = setTimeout(searchRoomAdminCandidates, 250);
});

function raffleOut(message, ok) {
  $("raffleRecipientStatus").textContent = message;
  $("raffleRecipientStatus").className = "toast " + (ok ? "ok" : "err");
}

function renderRaffleCandidates(candidates, query) {
  const list = $("raffleCandidateList");
  list.innerHTML = "";
  if (!query) {
    list.innerHTML = '<p class="hint">닉네임 일부를 입력해 주세요.</p>';
    return;
  }
  if (!candidates.length) {
    list.innerHTML = '<p class="hint">일치하는 사용자가 없습니다.</p>';
    return;
  }
  candidates.forEach((candidate) => {
    const row = document.createElement("div");
    row.className = "adminrow";
    const name = document.createElement("div");
    name.className = "admin-name";
    name.textContent = candidate.nickname;
    const add = document.createElement("button");
    add.type = "button";
    add.className = "primary";
    add.textContent = "수령 등록";
    add.onclick = () => registerRaffleRecipient(candidate.userKey, candidate.nickname);
    row.appendChild(name);
    row.appendChild(add);
    list.appendChild(row);
  });
}

function renderRaffleRecipients(recipients) {
  const list = $("raffleRecipientList");
  list.innerHTML = "";
  if (!recipients.length) {
    list.innerHTML = '<p class="hint">아직 등록된 상품 수령자가 없습니다.</p>';
    return;
  }
  recipients.forEach((recipient) => {
    const row = document.createElement("div");
    row.className = "adminrow";
    const name = document.createElement("div");
    name.className = "admin-name";
    name.textContent = recipient.nickname;
    const meta = document.createElement("small");
    meta.textContent = "수령 " + recipient.receivedDate + " · " + recipient.excludedUntil + "부터 다시 추첨 가능";
    name.appendChild(meta);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger";
    remove.textContent = "등록 취소";
    remove.onclick = () => removeRaffleRecipient(recipient.id, recipient.nickname);
    row.appendChild(name);
    row.appendChild(remove);
    list.appendChild(row);
  });
}

async function refreshRaffleRecipients() {
  const room = currentRoom();
  const query = $("raffleRecipientSearch").value.trim();
  $("raffleRecipientStatus").className = "toast";
  $("raffleRecipientStatus").textContent = "";
  if (!room || $("roomSelect").value === "__custom__") {
    $("raffleRoomHint").textContent = "먼저 위 배너에서 대상 방을 선택해 주세요.";
    $("raffleCandidateList").innerHTML = '<p class="hint">닉네임을 검색해 주세요.</p>';
    $("raffleRecipientList").innerHTML = '<p class="hint">선택된 방이 없습니다.</p>';
    return;
  }
  $("raffleRoomHint").textContent = "대상 방 · " + room;
  const params = new URLSearchParams({ room: room, query: query });
  try {
    const res = await fetch("/admin/raffle-recipients?" + params, { headers: headers() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "수령자 정보를 불러오지 못했습니다.");
    renderRaffleCandidates(data.candidates || [], query);
    renderRaffleRecipients(data.recipients || []);
  } catch (error) {
    raffleOut(error.message, false);
  }
}

async function registerRaffleRecipient(userKey, nickname) {
  if (!confirm(nickname + " 님을 상품 수령자로 등록할까요?\\n등록일부터 7일 동안 추첨 대상에서 제외됩니다.")) return;
  const res = await fetch("/admin/raffle-recipient", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ room: currentRoom(), user_key: userKey }),
  });
  const data = await res.json();
  if (!res.ok) return raffleOut(data.detail || "수령자 등록에 실패했습니다.", false);
  $("raffleRecipientSearch").value = "";
  await refreshRaffleRecipients();
  raffleOut(data.nickname + " 님을 상품 수령자로 등록했습니다.", true);
}

async function removeRaffleRecipient(recipientId, nickname) {
  if (!confirm(nickname + " 님의 상품 수령 등록을 취소할까요?")) return;
  const params = new URLSearchParams({ room: currentRoom(), recipient_id: String(recipientId) });
  const res = await fetch("/admin/raffle-recipient?" + params, {
    method: "DELETE",
    headers: headers(),
  });
  const data = await res.json();
  if (!res.ok) return raffleOut(data.detail || "수령 등록 취소에 실패했습니다.", false);
  await refreshRaffleRecipients();
  raffleOut(data.nickname + " 님의 상품 수령 등록을 취소했습니다.", true);
}

let raffleSearchTimer = null;
$("raffleRecipientSearch").addEventListener("input", () => {
  clearTimeout(raffleSearchTimer);
  raffleSearchTimer = setTimeout(refreshRaffleRecipients, 250);
});

function joinAlertOut(message, ok) {
  $("joinAlertStatus").textContent = message;
  $("joinAlertStatus").className = "toast " + (ok ? "ok" : "err");
}

function toggleShopRegistrationCosts() {
  $("shopRegistrationCosts").style.display = $("shopRegistrationAdminOnly").checked
    ? "none"
    : "block";
}

function syncModerationWarningControls() {
  const enabled = $("moderationObservationEnabled").checked;
  ["moderationFragmentWarningEnabled", "moderationEumsWarningEnabled"].forEach((id) => {
    const input = $(id);
    input.disabled = !enabled;
    if (!enabled) input.checked = false;
    input.closest(".checkrow").style.opacity = enabled ? "1" : "0.48";
  });
}

$("moderationObservationEnabled").addEventListener("change", syncModerationWarningControls);

async function refreshJoinAlertSettings() {
  const room = currentRoom();
  $("joinAlertStatus").textContent = "";
  $("joinAlertStatus").className = "toast";
  if (!room || $("roomSelect").value === "__custom__") {
    $("joinAlertRoomHint").textContent = "먼저 위 배너에서 대상 방을 선택해 주세요.";
    $("joinAlertThreshold").value = "5";
    $("shopRegistrationAdminOnly").checked = true;
    $("shopRegistrationFee").value = "100";
    $("shopRegistrationDeposit").value = "0";
    $("moderationObservationEnabled").checked = true;
    $("moderationFragmentWarningEnabled").checked = true;
    $("moderationEumsWarningEnabled").checked = true;
    $("moderationFragmentCount").value = "2";
    $("moderationFragmentWindow").value = "12";
    $("moderationEumsCount").value = "3";
    toggleShopRegistrationCosts();
    syncModerationWarningControls();
    return;
  }
  $("joinAlertRoomHint").textContent = "대상 방 · " + room;
  const params = new URLSearchParams({ room: room });
  try {
    const res = await fetch("/admin/room-settings?" + params, { headers: headers() });
    const data = await res.json();
    if (!res.ok) return joinAlertOut(data.detail || "설정을 불러오지 못했습니다.", false);
    $("joinAlertThreshold").value = String(data.joinAlertThreshold);
    $("shopRegistrationAdminOnly").checked = data.shopRegistrationAdminOnly !== false;
    $("shopRegistrationFee").value = String(data.shopRegistrationFee);
    $("shopRegistrationDeposit").value = String(data.shopRegistrationDeposit);
    $("moderationObservationEnabled").checked = data.moderationObservationEnabled !== false;
    $("moderationFragmentWarningEnabled").checked = data.moderationFragmentWarningEnabled !== false;
    $("moderationEumsWarningEnabled").checked = data.moderationEumsWarningEnabled !== false;
    $("moderationFragmentCount").value = String(data.moderationFragmentCount);
    $("moderationFragmentWindow").value = String(data.moderationFragmentWindow);
    $("moderationEumsCount").value = String(data.moderationEumsCount);
    toggleShopRegistrationCosts();
    syncModerationWarningControls();
  } catch (error) {
    joinAlertOut("설정을 불러오지 못했습니다.", false);
  }
}

async function saveJoinAlertSettings() {
  const room = currentRoom();
  const threshold = Number($("joinAlertThreshold").value);
  const shopAdminOnly = $("shopRegistrationAdminOnly").checked;
  const shopFee = Number($("shopRegistrationFee").value);
  const shopDeposit = Number($("shopRegistrationDeposit").value);
  const moderationEnabled = $("moderationObservationEnabled").checked;
  const fragmentWarningEnabled = moderationEnabled && $("moderationFragmentWarningEnabled").checked;
  const eumsWarningEnabled = moderationEnabled && $("moderationEumsWarningEnabled").checked;
  const fragmentCount = Number($("moderationFragmentCount").value);
  const fragmentWindow = Number($("moderationFragmentWindow").value);
  const eumsCount = Number($("moderationEumsCount").value);
  if (!room || $("roomSelect").value === "__custom__") {
    return joinAlertOut("대상 방을 먼저 선택해 주세요.", false);
  }
  if (!Number.isInteger(threshold) || threshold < 2 || threshold > 100) {
    return joinAlertOut("2회부터 100회 사이의 정수를 입력해 주세요.", false);
  }
  if (!Number.isInteger(shopFee) || shopFee < 0 || shopFee > 1000000) {
    return joinAlertOut("상품 등록 수수료는 0P부터 1,000,000P 사이의 정수로 입력해 주세요.", false);
  }
  if (!Number.isInteger(shopDeposit) || shopDeposit < 0 || shopDeposit > 1000000) {
    return joinAlertOut("상품 등록 보증금은 0P부터 1,000,000P 사이의 정수로 입력해 주세요.", false);
  }
  if (!Number.isInteger(fragmentCount) || fragmentCount < 2 || fragmentCount > 10) {
    return joinAlertOut("단타 기준은 2회부터 10회 사이로 입력해 주세요.", false);
  }
  if (!Number.isInteger(fragmentWindow) || fragmentWindow < 5 || fragmentWindow > 60) {
    return joinAlertOut("단타 관찰 시간은 5초부터 60초 사이로 입력해 주세요.", false);
  }
  if (!Number.isInteger(eumsCount) || eumsCount < 1 || eumsCount > 10) {
    return joinAlertOut("음슴체 기준은 1회부터 10회 사이로 입력해 주세요.", false);
  }
  const res = await fetch("/admin/room-settings", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      room: room,
      join_alert_threshold: threshold,
      shop_registration_admin_only: shopAdminOnly,
      shop_registration_fee: shopFee,
      shop_registration_deposit: shopDeposit,
      moderation_observation_enabled: moderationEnabled,
      moderation_fragment_warning_enabled: fragmentWarningEnabled,
      moderation_eums_warning_enabled: eumsWarningEnabled,
      moderation_fragment_count: fragmentCount,
      moderation_fragment_window: fragmentWindow,
      moderation_eums_count: eumsCount,
    }),
  });
  const data = await res.json();
  if (!res.ok) return joinAlertOut(data.detail || "저장하지 못했습니다.", false);
  $("joinAlertThreshold").value = String(data.joinAlertThreshold);
  $("shopRegistrationAdminOnly").checked = data.shopRegistrationAdminOnly !== false;
  $("shopRegistrationFee").value = String(data.shopRegistrationFee);
  $("shopRegistrationDeposit").value = String(data.shopRegistrationDeposit);
  $("moderationObservationEnabled").checked = data.moderationObservationEnabled !== false;
  $("moderationFragmentWarningEnabled").checked = data.moderationFragmentWarningEnabled !== false;
  $("moderationEumsWarningEnabled").checked = data.moderationEumsWarningEnabled !== false;
  $("moderationFragmentCount").value = String(data.moderationFragmentCount);
  $("moderationFragmentWindow").value = String(data.moderationFragmentWindow);
  $("moderationEumsCount").value = String(data.moderationEumsCount);
  toggleShopRegistrationCosts();
  syncModerationWarningControls();
  joinAlertOut("방 운영 설정을 저장했습니다.", true);
}

function moderationOut(message, ok) {
  $("moderationStatusMessage").textContent = message;
  $("moderationStatusMessage").className = "toast " + (ok ? "ok" : "err");
}

function renderModerationModel(data) {
  const active = data && data.active;
  if (!active) {
    $("moderationModelStatus").textContent =
      "활성 모델이 없습니다. 서버가 잠시 후 기본 모델을 자동으로 준비합니다.";
    return;
  }
  const fragment = (active.metrics && active.metrics.fragment) || {};
  const eums = (active.metrics && active.metrics.eums) || {};
  const reviewed = Number(data.reviewedCount || 0);
  const next = Number(data.retrainAt || 50);
  $("moderationModelStatus").textContent =
    "버전 " + active.version + " · 관리자 판정 " + reviewed + "건 · " +
    "단타 정확도 " + Math.round(Number(fragment.precision || 0) * 100) + "% · " +
    "음슴체 정확도 " + Math.round(Number(eums.precision || 0) * 100) + "% · " +
    "새 판정 " + next + "건마다 자동 재학습";
}

async function refreshModerationModel() {
  if (!$("key").value) return;
  try {
    const res = await fetch("/admin/moderation-model", { headers: headers() });
    const data = await res.json();
    if (res.ok) renderModerationModel(data);
  } catch (error) {}
}

async function trainModerationModel() {
  $("moderationModelMessage").textContent = "새 모델을 학습하고 검증하는 중입니다.";
  $("moderationModelMessage").className = "toast ok";
  try {
    const res = await fetch("/admin/moderation-train", { method: "POST", headers: headers() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "재학습에 실패했습니다.");
    renderModerationModel(data);
    $("moderationModelMessage").textContent = data.accepted === false
      ? "새 모델이 검증 기준을 통과하지 못해 기존 모델을 유지했습니다."
      : "검증을 통과한 새 모델을 적용했습니다.";
    $("moderationModelMessage").className = "toast " + (data.accepted === false ? "err" : "ok");
  } catch (error) {
    $("moderationModelMessage").textContent = error.message || "재학습에 실패했습니다.";
    $("moderationModelMessage").className = "toast err";
  }
}

async function rollbackModerationModel() {
  if (!confirm("현재 모델 대신 직전 모델을 다시 사용할까요?")) return;
  const res = await fetch("/admin/moderation-rollback", { method: "POST", headers: headers() });
  const data = await res.json();
  renderModerationModel(data);
  $("moderationModelMessage").textContent = data.ok
    ? "직전 모델로 복구했습니다."
    : (data.reason || "복구할 이전 모델이 없습니다.");
  $("moderationModelMessage").className = "toast " + (data.ok ? "ok" : "err");
}

function renderModerationCounts(counts, corpus) {
  const confirmed = counts.confirmed || 0;
  const dismissed = counts.dismissed || 0;
  const total = confirmed + dismissed;
  const corpusTotal = (corpus && corpus.total) || 0;
  $("moderationCounts").textContent =
    "누적 학습 원문 " + corpusTotal + "건 · 학습 판정 " + total + "건 · 정확함 " + confirmed + "건 · 오탐 " + dismissed +
    "건 · 대기 " + (counts.pending || 0) + "건 · 판정 50건이 더 쌓이면 자동 재학습합니다.";
}

function moderationMessages(item) {
  const saved = Array.isArray(item.messages)
    ? item.messages.filter((message) => message && String(message.text || "").trim())
    : [];
  if (saved.length) return saved;
  return String(item.preview || "").split(" / ").filter(Boolean).map((text) => ({ text: text, sentAt: "" }));
}

function moderationChatTime(value) {
  if (!value) return "";
  const normalized = value.includes("T") ? value : value.replace(" ", "T") + "Z";
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
}

function moderationDuration(item, messages) {
  const saved = Number(item.features && item.features.duration_seconds);
  if (Number.isFinite(saved) && saved >= 0) return saved;
  const times = messages.map((message) => new Date(message.sentAt).getTime()).filter(Number.isFinite);
  if (times.length < 2) return null;
  return Math.max(0, (times[times.length - 1] - times[0]) / 1000);
}

function renderModerationIncidents(items) {
  const list = $("moderationList");
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = '<p class="hint">해당 조건의 관찰 사례가 없습니다.</p>';
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "incident";
    const head = document.createElement("div");
    head.className = "incident-head";
    const name = document.createElement("div");
    name.className = "incident-name";
    name.textContent = item.displayName || "이름 없음";
    const tag = document.createElement("span");
    tag.className = "incident-tag";
    tag.textContent = item.kind === "fragment" ? "단타 의심" : "음슴체 의심";
    head.appendChild(name);
    head.appendChild(tag);
    const meta = document.createElement("div");
    meta.className = "incident-meta";
    const state = item.status === "confirmed" ? "정확함" : item.status === "dismissed" ? "오탐" : "판정 대기";
    meta.textContent = item.createdAt + " · " + state + " · 신뢰 " + Math.round(item.score * 100) + "%";
    const messages = moderationMessages(item);
    const chat = document.createElement("div");
    chat.className = "incident-chat";
    const profile = document.createElement("div");
    profile.className = "chat-profile";
    profile.textContent = Array.from(item.displayName || "?")[0] || "?";
    const thread = document.createElement("div");
    thread.className = "chat-thread";
    const sender = document.createElement("div");
    sender.className = "chat-sender";
    sender.textContent = item.displayName || "이름 없음";
    thread.appendChild(sender);
    messages.forEach((message, index) => {
      const line = document.createElement("div");
      line.className = "chat-line";
      const bubble = document.createElement("div");
      bubble.className = "chat-bubble";
      bubble.textContent = message.text;
      const time = document.createElement("span");
      time.className = "chat-time";
      time.textContent = moderationChatTime(message.sentAt || (index === messages.length - 1 ? item.createdAt : ""));
      line.appendChild(bubble);
      line.appendChild(time);
      thread.appendChild(line);
    });
    if (item.kind === "fragment") {
      const seconds = moderationDuration(item, messages);
      if (seconds !== null) {
        const duration = document.createElement("div");
        duration.className = "chat-duration";
        const shown = Number.isInteger(seconds) ? String(seconds) : seconds.toFixed(1);
        duration.textContent = "총 " + shown + "초 안에 입력한 단타 대화입니다.";
        thread.appendChild(duration);
      }
    }
    chat.appendChild(profile);
    chat.appendChild(thread);
    row.appendChild(head);
    row.appendChild(meta);
    row.appendChild(chat);
    if (item.status === "pending") {
      const question = document.createElement("p");
      question.className = "incident-question";
      question.textContent = "이 감지 결과가 맞나요?";
      const actions = document.createElement("div");
      actions.className = "incident-actions";
      const yes = document.createElement("button");
      yes.className = "primary";
      yes.textContent = "정확함";
      yes.onclick = () => reviewModerationIncident(item.id, "confirmed");
      const no = document.createElement("button");
      no.className = "ghost";
      no.textContent = "오탐";
      no.onclick = () => reviewModerationIncident(item.id, "dismissed");
      actions.appendChild(yes);
      actions.appendChild(no);
      row.appendChild(question);
      row.appendChild(actions);
    }
    list.appendChild(row);
  });
}

async function refreshModerationIncidents() {
  const room = currentRoom();
  const list = $("moderationList");
  $("moderationStatusMessage").textContent = "";
  $("moderationStatusMessage").className = "toast";
  if (!room || $("roomSelect").value === "__custom__") {
    $("moderationRoomHint").textContent = "먼저 위 배너에서 대상 방을 선택해 주세요.";
    list.innerHTML = '<p class="hint">선택된 방이 없습니다.</p>';
    renderModerationCounts({}, {});
    return;
  }
  $("moderationRoomHint").textContent = "대상 방 · " + room;
  list.innerHTML = '<p class="hint">관찰 사례를 불러오는 중입니다.</p>';
  const params = new URLSearchParams({ room: room, status: $("moderationStatus").value });
  try {
    const res = await fetch("/admin/moderation-incidents?" + params, { headers: headers() });
    const data = await res.json();
    if (!res.ok) return moderationOut(data.detail || "관찰 사례를 불러오지 못했습니다.", false);
    renderModerationCounts(data.counts || {}, data.corpus || {});
    renderModerationIncidents(data.items || []);
  } catch (error) {
    moderationOut("관찰 사례를 불러오지 못했습니다.", false);
  }
}

async function reviewModerationIncident(incidentId, status) {
  const res = await fetch("/admin/moderation-review", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ room: currentRoom(), incident_id: incidentId, status: status }),
  });
  const data = await res.json();
  if (!res.ok) return moderationOut(data.detail || "판정을 저장하지 못했습니다.", false);
  moderationOut(status === "confirmed" ? "정확한 감지로 학습 자료에 반영했습니다." : "오탐으로 학습 자료에 반영했습니다.", true);
  await refreshModerationIncidents();
}

let currentSiteUrl = "";

function siteOut(message, ok) {
  $("siteStatus").textContent = message;
  $("siteStatus").className = "toast " + (ok ? "ok" : "err");
}

function refreshRoomSite() {
  const room = currentRoom();
  const registered = siteRooms.find((item) => item.room === room);
  currentSiteUrl = "";
  $("siteResult").style.display = "none";
  $("siteStatus").textContent = "";
  $("siteStatus").className = "toast";

  if (!room || $("roomSelect").value === "__custom__") {
    $("siteRoomHint").textContent = "먼저 위 배너에서 대상 방을 선택해 주세요.";
    $("siteSetupFields").style.display = "none";
    $("siteIssueButton").textContent = "전용 사이트 만들기";
    return;
  }
  if (!registered) {
    $("siteRoomHint").textContent = "이 방은 아직 봇이 확인하지 못했습니다. 방에서 메시지를 한 번 보낸 뒤 새로고침해 주세요.";
    $("siteSetupFields").style.display = "none";
    $("siteIssueButton").textContent = "전용 사이트 만들기";
    return;
  }

  $("siteRoomHint").textContent = "대상 방 · " + room;
  $("siteSetupFields").style.display = registered.hasPassword ? "none" : "block";
  $("siteIssueButton").textContent = registered.hasPassword
    ? "전용 사이트 확인"
    : "전용 사이트 만들기";
}

async function issueRoomSite() {
  const room = currentRoom();
  const registered = siteRooms.find((item) => item.room === room);
  if (!room || $("roomSelect").value === "__custom__") {
    return siteOut("대상 방을 먼저 선택해 주세요.", false);
  }
  if (!registered) {
    return siteOut("봇이 확인한 채팅방만 전용 사이트를 만들 수 있습니다.", false);
  }

  const body = { room: room };
  if (!registered.hasPassword) {
    body.password = $("sitePassword").value;
    body.recovery_word = $("siteRecovery").value.trim();
  }
  const res = await fetch("/admin/site-room", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) return siteOut(data.detail || "전용 사이트 발급에 실패했습니다.", false);

  registered.hasPassword = true;
  currentSiteUrl = location.origin + data.path;
  $("siteResultRoom").textContent = data.room + " 전용 관리 사이트";
  $("siteUrl").textContent = currentSiteUrl;
  $("siteResult").style.display = "block";
  $("siteSetupFields").style.display = "none";
  $("siteIssueButton").textContent = "전용 사이트 다시 확인";
  $("sitePassword").value = "";
  $("siteRecovery").value = "";
  siteOut("이 방에서만 사용할 수 있는 관리 사이트가 준비되었습니다.", true);
}

function copyCurrentSite(button) {
  if (!currentSiteUrl) return siteOut("먼저 전용 사이트를 확인해 주세요.", false);
  copyText(currentSiteUrl, button);
}

function openCurrentSite() {
  if (!currentSiteUrl) return siteOut("먼저 전용 사이트를 확인해 주세요.", false);
  window.open(currentSiteUrl, "_blank", "noopener");
}

function copyText(text, btn) {
  const done = () => { const t = btn.textContent; btn.textContent = "복사됨!"; setTimeout(() => { btn.textContent = t; }, 1200); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}
function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try { document.execCommand("copy"); done(); } catch (e) {}
  document.body.removeChild(ta);
}

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
      // 이미 선택된 칩을 다시 누르면 선택을 취소하고 입력칸을 비운다.
      if (chip.classList.contains("active")) {
        chip.classList.remove("active");
        $("command").value = "";
        $("response").value = "";
        $("count").textContent = "";
        $("status").textContent = "";
        $("status").className = "toast";
        return;
      }
      document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      $("command").value = item.command;
      load();
      // 선택하면 명령어 이름 칸이 보이도록 내려간다.
      // (smooth는 일부 웹뷰에서 무시되므로 즉시 이동을 쓴다)
      $("command").scrollIntoView({ block: "center" });
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
      room_password: roomPw(),
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
  const params = new URLSearchParams({
    room: currentRoom(),
    command: name,
    password: roomPw(),
  });
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

function pwOut(msg, ok) {
  $("pwStatus").textContent = msg;
  $("pwStatus").className = "toast " + (ok ? "ok" : "err");
}

async function setRoomPw() {
  const room = $("pwRoom").value.trim();
  if (!room) return pwOut("대상 방을 입력해 주세요.", false);
  if (!$("pwNew").value || !$("pwRecovery").value.trim()) {
    return pwOut("비밀번호와 복구 단어를 모두 입력해 주세요.", false);
  }
  const res = await fetch("/admin/room-password", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      room: room,
      password: $("pwNew").value,
      recovery_word: $("pwRecovery").value.trim(),
    }),
  });
  if (res.status === 403) return pwOut("관리 키가 올바르지 않습니다.", false);
  const data = await res.json();
  if (!res.ok) return pwOut(data.detail || "설정에 실패했습니다.", false);
  localStorage.setItem("kpg-pw:" + room, $("pwNew").value);
  pwOut("비밀번호를 설정했습니다. 복구 단어를 꼭 기억해 두세요!", true);
}

async function changeRoomPw() {
  const room = $("pwRoom").value.trim();
  if (!room) return pwOut("대상 방을 입력해 주세요.", false);
  if (!$("pwRecovery2").value.trim() || !$("pwNew2").value) {
    return pwOut("복구 단어와 새 비밀번호를 모두 입력해 주세요.", false);
  }
  const res = await fetch("/admin/room-password/change", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      room: room,
      recovery_word: $("pwRecovery2").value.trim(),
      new_password: $("pwNew2").value,
    }),
  });
  const data = await res.json();
  if (!res.ok) return pwOut(data.detail || "변경에 실패했습니다.", false);
  localStorage.setItem("kpg-pw:" + room, $("pwNew2").value);
  pwOut("비밀번호를 변경했습니다.", true);
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
    body: JSON.stringify({
      old_room: oldRoom,
      new_room: newRoom,
      room_password: $("oldRoomPw").value,
    }),
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
