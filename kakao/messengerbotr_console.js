const bot = BotManager.getCurrentBot();
const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";
// 서버의 BRIDGE_KEY 환경변수와 같은 값으로 맞춰야 합니다.
const BRIDGE_KEY = "YOUR_BRIDGE_KEY";
const SCRIPT_VERSION = "kakaopogo-2026-07-10-bridge-key-v2";

function onMessage(msg) {
  const text = String(msg.content || "").trim();
  if (text === "/스크립트버전" || text === "/봇버전") {
    msg.reply("KakaoPoGo script " + SCRIPT_VERSION);
    return;
  }

  if (!isSupportedCommand(text)) {
    return;
  }

  try {
    const author = msg.author || {};
    const sender = String(author.name || "");
    const userKey = author.hash ? "hash:" + String(author.hash) : "";
    const url =
      SERVER_URL +
      "?text=" +
      encodeURIComponent(text) +
      "&room=" +
      encodeURIComponent(String(msg.room || "")) +
      "&sender=" +
      encodeURIComponent(sender) +
      "&user_key=" +
      encodeURIComponent(userKey);

    const body = org.jsoup.Jsoup.connect(url)
      .header("X-Bridge-Key", BRIDGE_KEY)
      .ignoreContentType(true)
      .ignoreHttpErrors(true)
      .timeout(20000)
      .get()
      .text();

    const data = JSON.parse(body);
    if (!data || data.silent || !data.reply) {
      return;
    }
    msg.reply(String(data.reply));
  } catch (error) {
    msg.reply(
      "KakaoPoGo server connection failed.\n" +
        "Check that the server is running and SERVER_URL is correct."
    );
  }
}

function isSupportedCommand(text) {
  return text.indexOf("/") === 0;
}

bot.addListener(Event.MESSAGE, onMessage);
