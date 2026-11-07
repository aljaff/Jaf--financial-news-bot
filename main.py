import os
import json
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FEED = "https://www.federalreserve.gov/feeds/press_monetary.xml"
KEYWORDS = (
    "البنك المركزي العراقي", "تعليمات البنك المركزي العراقي", "الفيدرالي الأمريكي",
    "الخزانة الأمريكية", "المصارف العراقية", "شركات الصرافة",
    "شركات الصرافة في اقليم كوردستان", "الحوالات المالية", "سعر الصرف",
    "الدينار العراقي", "الدفع الالكتروني", "بطاقات الدفع الالكتروني",
    "منافذ صرف الرواتب", "السياسة النقدية", "الموازنة العراقية",
    "Iraqi Dinar", "CBI", "Monetary Policy",
)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/" else 404)
        self.end_headers()


def watch_news(token, chat_id):
    seen = None
    while True:
        try:
            request = Request(FEED, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=20) as response:
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


def watch_newsapi(key, token, chat_id):
    query = urlencode({
        "q": " OR ".join(f'"{word}"' for word in KEYWORDS),
        "language": "ar",
        "sortBy": "publishedAt",
        "pageSize": 5,
    })
    seen = None
    while True:
        try:
            request = Request(
                f"https://newsapi.org/v2/everything?{query}",
                headers={"X-Api-Key": key},
            )
            with urlopen(request, timeout=20) as response:
                articles = json.load(response)["articles"]
            latest = {
                article["url"]: article["title"]
                for article in reversed(articles)
                if article.get("url") and article.get("title")
            }
            if seen is None:
                seen = set(latest)
                print("NewsAPI feed loaded.", flush=True)
            for link, title in latest.items():
                if link in seen:
                    continue
                data = urlencode({"chat_id": chat_id, "text": f"{title}\n{link}"})
                request = Request(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=data.encode(),
                )
                with urlopen(request, timeout=20):
                    seen.add(link)
        except (OSError, ValueError, KeyError) as error:
            print(f"NewsAPI cycle failed ({type(error).__name__}). Retrying.", flush=True)
        time.sleep(900)


if __name__ == "__main__":
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    with ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), HealthHandler) as server:
        threading.Thread(target=watch_news, args=(token, chat_id), daemon=True).start()
        news_key = os.getenv("NEWS_API_KEY")
        if news_key:
            threading.Thread(
                target=watch_newsapi, args=(news_key, token, chat_id), daemon=True
            ).start()
        server.serve_forever()
