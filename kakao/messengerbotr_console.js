const bot = BotManager.getCurrentBot();
const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";

function onMessage(msg) {
  const text = String(msg.content || "").trim();
  if (!isSupportedCommand(text)) {
    return;
  }

  try {
    const url =
      SERVER_URL +
      "?text=" +
      encodeURIComponent(text) +
      "&room=" +
      encodeURIComponent(String(msg.room || "")) +
      "&sender=" +
      encodeURIComponent(String((msg.author && msg.author.name) || ""));

    const body = org.jsoup.Jsoup.connect(url)
      .ignoreContentType(true)
      .ignoreHttpErrors(true)
      .timeout(20000)
      .get()
      .text();

    const data = JSON.parse(body);
    msg.reply(data.reply || "Empty reply from server.");
  } catch (error) {
    msg.reply(
      "KakaoPoGo server connection failed.\n" +
        "Check that the server is running and SERVER_URL is correct."
    );
  }
}

function isSupportedCommand(text) {
  return text.indexOf("!") === 0 || text.indexOf("/") === 0;
}

bot.addListener(Event.MESSAGE, onMessage);
