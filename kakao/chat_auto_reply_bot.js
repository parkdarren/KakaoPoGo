const SERVER_URL = "http://YOUR_SERVER_IP:8000/command";

function response(room, msg, sender, isGroupChat, replier, imageDB, packageName) {
  const text = String(msg || "").trim();
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
  return text.indexOf("!") === 0;
}
