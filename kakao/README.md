# KakaoTalk Runner Setup

This folder contains KakaoTalk bridge scripts for Android notification-based bot
runners. The runner listens to KakaoTalk notifications, sends supported `!` commands
to the KakaoPoGo backend, and replies with the backend response.

## Scripts

- `messengerbotr_console.js`: newer MessengerBotR BotManager/Event API.
- `messengerbotr.js`: classic MessengerBotR `response(...)` API.
- `chat_auto_reply_bot.js`: compatible auto-reply bot runner variant.

Use the script that matches your runner's editor template.

## Configure The Backend URL

Before pasting a script into the runner, update:

```javascript
const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";
```

For local Wi-Fi testing, replace `YOUR_SERVER_IP` with the PC's private IP. For
VPS operation, replace it with the VPS public IP or domain.

## Runner Checklist

1. Install the bot runner on an Android device or emulator.
2. Enable notification access for the runner.
3. Enable KakaoTalk notifications for the target room.
4. Create a new bot script.
5. Paste the matching script from this folder.
6. Save, compile, and turn the bot on.
7. Keep the device awake enough for KakaoTalk and the runner to stay alive.

Slash-prefixed messages are ignored by design.

## Public Test Commands

```text
!도움말
!도감 디아루가
!도감 디아
!도감 alg
!도감 화이트큐레무
!스킬 피카츄
!스킬 블랙큐레무
!100 자시안 검왕
!약점 기라티나 오리진
!cp 피카츄 40 15/15/15
```

## Admin Notes

Owner/admin commands are handled by the backend and are intentionally hidden from
the public `!도움말` response. Use a separate management room if you do not want
regular users to see management messages typed into KakaoTalk.

## Caveat

This is a practical notification-based open-chat integration. It is not an
official Kakao OpenChat bot API.
