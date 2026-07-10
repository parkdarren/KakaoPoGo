const scriptName = "KakaoPoGo";
const SCRIPT_VERSION = "kakaopogo-2026-07-10-slash-v1";

// VPS server: http://YOUR_SERVER_IP:8000/command
// If your server IP changes, update this URL.
const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";

function response(room, msg, sender, isGroupChat, replier, imageDB, packageName) {
  const text = String(msg || "").trim();
  if (text === "/스크립트버전" || text === "/봇버전") {
    replier.reply("KakaoPoGo script " + SCRIPT_VERSION);
    return;
  }

  if (!isSupportedCommand(text)) {
    return;
  }

  try {
    const url =
      SERVER_URL +
      "?text=" +
      encodeURIComponent(text) +
      "&room=" +
      encodeURIComponent(String(room || "")) +
      "&sender=" +
      encodeURIComponent(String(sender || ""));

    const body = org.jsoup.Jsoup.connect(url)
      .ignoreContentType(true)
      .ignoreHttpErrors(true)
      .timeout(20000)
      .get()
      .text();

    const data = JSON.parse(body);
    if (!data || data.silent || !data.reply) {
      return;
    }
    replier.reply(String(data.reply));
  } catch (error) {
    replier.reply(
      "KakaoPoGo server connection failed.\n" +
        "Check that the server is running and SERVER_URL is correct."
    );
  }
}

function isSupportedCommand(text) {
  return text.indexOf("/") === 0;
}
