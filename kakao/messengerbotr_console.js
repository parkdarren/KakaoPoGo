const bot = BotManager.getCurrentBot();
const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";

function onMessage(msg) {
  const text = String(msg.content || "").trim();
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
  return text.indexOf("!") === 0;
}

bot.addListener(Event.MESSAGE, onMessage);
