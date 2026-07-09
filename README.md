# KakaoPoGo

Pokemon GO information bot for KakaoTalk open-chat communities.

KakaoPoGo provides a FastAPI backend that receives chat-style commands and
returns concise Korean replies for Pokemon GO lookups, perfect-IV CP tables,
weaknesses, forms, aliases, and room-specific custom commands.

## Highlights

- Pokemon GO dex lookup with Korean names and common form names.
- Compact 100% IV CP output for research, raid, weather-boosted raid, and Lv50.
- Type and weakness lookup for raid preparation.
- Custom CP calculator by level and IV spread.
- Short aliases such as `디아`, `alg`, and `루가` for frequent room searches.
- Role-based owner/admin management for room custom commands.
- Public `!도움말` output that excludes owner/admin-only commands.
- KakaoTalk bridge scripts for MessengerBotR-style notification bot runners.
- Optional Android notification bridge project.

## Command Examples

```text
!도감 디아루가
!도감 디아
!도감 alg
!도감 자시안 검왕
!100 기라티나 오리진
!약점 뮤츠
!cp 피카츄 40 15/15/15
!도움말
```

Example dex reply:

```text
No.483 디아루가 / Dialga
타입: 강철 / 드래곤
약점: 격투 / 땅

[ 100% CP 계산 ]
리서치 Lv15: 1731 CP
레이드/알 Lv20: 2307 CP
날씨부스트 Lv25: 2884 CP
최대 Lv50: 4565 CP
```

If a Pokemon has legacy or Elite TM moves, only those special moves are shown in
the dex reply. Regular moves are intentionally omitted to keep chat output short.

## Architecture

```text
KakaoTalk room
    -> Android bot runner notification hook
    -> KakaoPoGo FastAPI backend
    -> PoGo API data + local Korean name map + SQLite admin/custom-command store
    -> plain-text KakaoTalk reply
```

The backend is responsible for all command parsing, Pokemon data lookup, CP
calculation, permission checks, and response formatting. The KakaoTalk runner is
kept thin: it forwards messages to `/command` and posts the returned reply.

## Tech Stack

- Python 3
- FastAPI
- httpx
- SQLite
- pytest
- PoGo API community dataset
- MessengerBotR-compatible JavaScript bridge
- Optional native Android bridge app

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the backend:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For owner/admin setup, configure a private `OWNER_SETUP_CODE`. See
`.env.example` for the expected variable name.

Open:

```text
http://127.0.0.1:8000/docs
```

Test a command:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/command?text=!dex%20Dialga&room=local&sender=test"
```

## KakaoTalk Bridge

Use one of the scripts in `kakao/` with a MessengerBotR-style runner:

- `kakao/messengerbotr_console.js` for the newer BotManager/Event API.
- `kakao/messengerbotr.js` for the classic `response(...)` API.
- `kakao/chat_auto_reply_bot.js` for compatible auto-reply bot runners.

Before pasting a script into the runner, set:

```javascript
const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";
```

For Android runner setup notes, see `kakao/README.md`.

## Deployment

An Ubuntu VPS is enough for early operation. The recommended deployment path is:

1. Create a small Ubuntu VPS.
2. Open inbound TCP `8000`.
3. Upload the project.
4. Set `OWNER_SETUP_CODE` to a private value.
5. Run the setup script in `deploy/vps_setup.sh`.
6. Point the KakaoTalk bridge script to the VPS command endpoint.

Detailed notes are in `deploy/IWINV_VPS.md`.

## Data

Pokemon GO data is fetched from the community PoGo API and cached under
`.cache/pogoapi`. Korean Pokemon names are stored in:

```text
app/data/korean_names.json
```

Regenerate the Korean name map:

```powershell
python scripts/generate_korean_names.py
```

## Tests

```powershell
python -m pytest
```

The test suite covers command parsing, CP calculation, Korean name/form
resolution, compact dex formatting, and owner/admin command behavior.

## Notes

- KakaoTalk open-chat automation is not an official Kakao OpenChat API flow.
- Keep the runner account and room behavior conservative to avoid spam-like use.
- Do not commit real server IPs, owner setup codes, database files, APKs, or
  Android local build files.
