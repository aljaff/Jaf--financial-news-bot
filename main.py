import os
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FEED = "https://www.federalreserve.gov/feeds/press_monetary.xml"


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/" else 404)
        self.end_headers()


def watch_news(token, chat_id):
    seen = None
    while True:
        try:
            with urlopen(FEED, timeout=20) as response:
                entries = ET.fromstring(response.read()).findall("./channel/item")
            articles = {
                item.findtext("link"): item.findtext("title", "").strip()
                for item in reversed(entries)
                if item.findtext("link") and item.findtext("title")
            }
            if seen is None and articles:
                seen = set(articles)
                print("Federal Reserve feed loaded.", flush=True)
            if seen is not None:
                for link, title in articles.items():
                    if link in seen:
                        continue
                    payload = urlencode({"chat_id": chat_id, "text": f"{title}\n{link}"})
                    request = Request(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        data=payload.encode(),
                    )
                    with urlopen(request, timeout=20):
                        seen.add(link)
        except (OSError, ET.ParseError) as error:
            print(f"News check failed ({type(error).__name__}). Retrying.", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    with ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), HealthHandler) as server:
        threading.Thread(target=watch_news, args=(token, chat_id), daemon=True).start()
        server.serve_forever()
