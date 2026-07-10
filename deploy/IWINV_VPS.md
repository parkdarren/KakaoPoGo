# iwinv / Ubuntu VPS Deployment

This guide deploys KakaoPoGo on a small Ubuntu VPS such as iwinv.

## Recommended Server

For this bot, a small Linux VPS is enough:

```text
OS: Ubuntu 22.04 or 24.04
CPU: 1 vCPU
Memory: 1 GB or more
Storage: 20 GB or more
Public IP: required
```

iwinv's low-cost 1 vCPU / 1 GB RAM class should be enough for early operation.

## 1. Create The Server

In iwinv, create a Linux VPS with Ubuntu. After creation, note:

```text
Public IP
SSH username
SSH password or private key
```

The username might be `root`, `ubuntu`, or another account depending on the image
and iwinv setup.

## 2. Open Port 8000

Open inbound TCP port `8000` in the iwinv firewall/security settings.

If Ubuntu firewall is enabled, also run:

```bash
sudo ufw allow 8000/tcp || true
```

## 3. Upload The Project

From PowerShell, move into this project folder first, then copy the project:

```powershell
scp -r . USERNAME@YOUR_SERVER_IP:/home/USERNAME/kakaopogo
```

SSH into the server:

```powershell
ssh USERNAME@YOUR_SERVER_IP
```

Move the project into `/opt`:

```bash
sudo mv /home/USERNAME/kakaopogo /opt/kakaopogo
sudo chown -R USERNAME:USERNAME /opt/kakaopogo
```

Replace `USERNAME` with your actual server user.

## 4. Install And Start

```bash
cd /opt/kakaopogo
chmod +x deploy/vps_setup.sh
APP_USER=USERNAME OWNER_SETUP_CODE=YOUR_PRIVATE_OWNER_CODE ./deploy/vps_setup.sh
```

Replace `USERNAME` with your actual server user and choose a private
`OWNER_SETUP_CODE` value before running the setup script.

Check:

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/command?text=/dex%20Pikachu"
```

From your PC or phone browser:

```text
http://YOUR_SERVER_IP:8000/health
```

## 5. Update Kakao Bridge URL

In `kakao/messengerbotr.js`, change:

```javascript
const SERVER_URL = "http://YOUR_LOCAL_IP:8000/command";
```

to:

```javascript
const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";
```

Paste the updated script into MessengerBotR.

## 6. Useful Service Commands

```bash
sudo systemctl status kakaopogo
sudo systemctl restart kakaopogo
sudo journalctl -u kakaopogo -f
```

## 7. Optional Discord Bot

Create an application and bot in the Discord Developer Portal, copy the bot
token, then install the Discord service on the same VPS:

```bash
cd /opt/kakaopogo
APP_USER=USERNAME \
OWNER_SETUP_CODE=YOUR_PRIVATE_OWNER_CODE \
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN \
DISCORD_GUILD_ID=YOUR_TEST_SERVER_ID \
./deploy/vps_setup.sh
```

`DISCORD_GUILD_ID` is optional, but useful while testing because guild commands
sync much faster than global commands.

Invite the bot with these scopes:

```text
bot
applications.commands
```

Recommended bot permissions:

```text
Send Messages
Use Slash Commands
Read Message History
```

Useful commands:

```bash
sudo systemctl status kakaopogo-discord
sudo systemctl restart kakaopogo-discord
sudo journalctl -u kakaopogo-discord -f
```

If you want free-form text commands such as `/공지` to work in addition to
Discord slash commands, enable Message Content Intent in the Discord Developer
Portal and set:

```bash
DISCORD_ENABLE_PREFIX=true
```

## 8. Backup

The bot stores owner/admin/custom-command data in:

```text
/opt/kakaopogo/data/kakaopogo.sqlite3
```

Back it up before reinstalling or deleting the server:

```bash
mkdir -p ~/kakaopogo-backups
cp /opt/kakaopogo/data/kakaopogo.sqlite3 ~/kakaopogo-backups/kakaopogo-$(date +%Y%m%d-%H%M%S).sqlite3
```

## Notes

- A domain is optional. A domain only points to this VPS.
- HTTP on port 8000 is enough for initial Kakao bot testing.
- For long-term public use, add HTTPS through Caddy, Nginx, or Cloudflare.
