import os
import re
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
    "Iraqi Dinar", "CBI", "Monetary Policy", "السياسة المالية",
)

IRAQ = r"عراق\w*|كوردستان|كردستان|بغداد|اربيل|بصرة|سليمانية|دهوك|iraq\w*|kurdistan|baghdad|erbil|iqd"
FINANCE = (
    r"دينار\w*|دولار\w*|صرف\w*|صراف\w*|مصرف\w*|بنك\w*|بنوك|حوال\w*|"
    r"مالي\w*|نقدي\w*|موازن\w*|رواتب|دفع|خزان\w*|فيدرال\w*|عقوب\w*|"
    r"dinar|dollar|exchange|bank\w*|financ\w*|monetary|fiscal|treasury|"
    r"federal reserve|sanctions|iqd"
)


def iraqi_financial_news(title):
    # Google News appends the publisher after the headline.
    headline = title.rsplit(" - ", 1)[0].lower()
    headline = re.sub(r"[\u064b-\u065f\u0670ـ]", "", headline)
    headline = headline.translate(str.maketrans("أإآى", "اااي"))
    headline = re.sub(r"\b(?:وال|بال|لل|ال)(?=\w{3})", "", headline)
    other_currency = re.search(
        r"\b(?:ليرة|يورو|ين|زلوتي|ريال|جنيه|lira|euro|yen|zloty|riyal|rial)\b",
        headline,
    )
    if other_currency and not re.search(r"\b(?:دينار|dinar|iqd)\b", headline):
        return False
    return (
        re.search(rf"\b(?:{IRAQ})\b", headline)
        and re.search(rf"\b(?:{FINANCE})\b", headline)
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
                if item.findtext("link") and iraqi_financial_news(item.findtext("title", ""))
            }
            if seen is None:
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


def watch_headlines(token, chat_id):
    seen = set()
    initialized = set()
    groups = [KEYWORDS[start:start + 4] for start in range(0, len(KEYWORDS), 4)]
    while True:
        for index, words in enumerate(groups):
            query = urlencode({
                "q": '("العراق" OR "الدينار العراقي" OR "كوردستان" OR "كردستان" OR "Iraq") ('
                + " OR ".join(f'"{word}"' for word in words) + ") when:2d",
                "hl": "ar", "gl": "IQ", "ceid": "IQ:ar",
            })
            try:
                request = Request(
                    f"https://news.google.com/rss/search?{query}",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urlopen(request, timeout=20) as response:
                    entries = ET.fromstring(response.read()).findall("./channel/item")
                articles = {
                    item.findtext("link"): item.findtext("title", "").strip()
                    for item in reversed(entries)
                    if item.findtext("link") and iraqi_financial_news(item.findtext("title", ""))
                }
                if index not in initialized:
                    seen.update(articles)
                    initialized.add(index)
                    print(f"Arabic news search {index + 1} loaded ({len(articles)} results).", flush=True)
                    continue
                for link, title in articles.items():
                    if link in seen:
                        continue
                    data = urlencode({"chat_id": chat_id, "text": f"{title}\n{link}"})
                    request = Request(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        data=data.encode(),
                    )
                    with urlopen(request, timeout=20):
                        seen.add(link)
            except (OSError, ET.ParseError) as error:
                print(f"Arabic news cycle failed ({type(error).__name__}). Retrying.", flush=True)
        time.sleep(900)

if __name__ == "__main__":
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    with ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), HealthHandler) as server:
        threading.Thread(target=watch_news, args=(token, chat_id), daemon=True).start()
        threading.Thread(target=watch_headlines, args=(token, chat_id), daemon=True).start()
        server.serve_forever()

