const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";
// 서버의 BRIDGE_KEY 환경변수와 같은 값으로 맞춰야 합니다.
const BRIDGE_KEY = "YOUR_BRIDGE_KEY";
const SCRIPT_VERSION = "kakaopogo-2026-07-14-chat-stats-v3";

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
    replier.reply(String(data.reply));
  } catch (error) {
    // 일반 채팅 집계 실패는 조용히 넘기고, 명령어일 때만 오류를 알린다.
    if (text.indexOf("/") === 0) {
      replier.reply(
        "KakaoPoGo server connection failed.\n" +
          "Check that the server is running and SERVER_URL is correct."
      );
    }
  }
}

function isSupportedCommand(text) {
  // 채팅량 랭킹 집계를 위해 모든 메시지를 서버로 보낸다.
  return text.length > 0;
}
