#!/usr/bin/env python3
"""
DOOMWATCH - MARKETS COLLECTOR
Independent of collector.py.
Writes historical market data to data/markets.json.
Uses Python standard library only.
"""

import csv
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_FILE = DATA_DIR / "markets.json"

USER_AGENT = "DoomWatch-Markets/1.0"
TIMEOUT = 25
MAX_HISTORY = 400

YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{}?range=1y&interval=1d"
)

# Financial markets and commodities

MARKETS = {
    "commodities": {
        "gold": ("GC=F", "USD / troy oz"),
        "silver": ("SI=F", "USD / troy oz"),
        "brent": ("BZ=F", "USD / barrel"),
    },

    "indices": {
        "sp500": ("^GSPC", "index points"),
        "nasdaq": ("^IXIC", "index points"),
        "ftse100": ("^FTSE", "index points"),
    },

    "crypto": {
        "bitcoin": ("BTC-USD", "USD"),
    },

    "fx": {
        "GBPUSD": ("GBPUSD=X", "USD per GBP"),
        "GBPEUR": ("GBPEUR=X", "EUR per GBP"),
        "EURUSD": ("EURUSD=X", "USD per EUR"),
    },
}

# Top ten share watchlist

STOCKS = [
    ("Apple", "AAPL"),
    ("Microsoft", "MSFT"),
    ("NVIDIA", "NVDA"),
    ("Amazon", "AMZN"),
    ("Alphabet", "GOOGL"),
    ("Meta", "META"),
    ("Berkshire Hathaway", "BRK-B"),
    ("JPMorgan Chase", "JPM"),
    ("Broadcom", "AVGO"),
    ("Tesla", "TSLA"),
]

# Official source pages

HEATING_OIL_URL = (
    "https://www.consumercouncil.org.uk/"
    "home-heating/price-checker"
)

FUEL_URL = (
    "https://www.gov.uk/government/statistics/"
    "weekly-road-fuel-prices"
)

FOOD_URL = "https://nifoodcompass.com/"

NEWS_FEEDS = [
    (
        "BBC Business",
        "https://feeds.bbci.co.uk/news/business/rss.xml"
    ),
    (
        "BBC World",
        "https://feeds.bbci.co.uk/news/world/rss.xml"
    ),
    (
        "DEFRA",
        "https://www.gov.uk/government/organisations/"
        "department-for-environment-food-rural-affairs.atom"
    ),
]


# --------------------------------------------------
# GENERAL FUNCTIONS
# --------------------------------------------------

def timestamp():
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def fetch(url, accept="*/*"):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=TIMEOUT
    ) as response:
        return response.read()


def load_data():

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if DATA_FILE.exists():
        try:
            data = json.loads(
                DATA_FILE.read_text(encoding="utf-8")
            )

            if isinstance(data, dict):
                return data

        except Exception as error:
            print("Existing markets file unreadable:", error)

    return {
        "schemaVersion": 1,
        "updatedAt": None,
        "generatedAt": None,
        "sources": {},
        "commodities": {},
        "indices": {},
        "crypto": {},
        "fx": {},
        "stocks": [],
        "heatingOil": {"items": []},
        "fuel": {"items": []},
        "householdBasket": {
            "items": [],
            "history": []
        },
        "news": [],
        "supplyNews": [],
    }


def merge_history(old_history, new_history):

    points = {}

    for point in old_history or []:
        if isinstance(point, dict) and point.get("date"):
            points[point["date"]] = point

    for point in new_history or []:
        if isinstance(point, dict) and point.get("date"):
            points[point["date"]] = point

    return [
        points[day]
        for day in sorted(points)
    ][-MAX_HISTORY:]


# --------------------------------------------------
# FINANCIAL MARKET DATA
# --------------------------------------------------

def get_yahoo_data(symbol):

    url = YAHOO_URL.format(
        urllib.parse.quote(symbol, safe="=^.-")
    )

    raw = json.loads(
        fetch(url, "application/json")
    )

    result = raw["chart"]["result"][0]

    meta = result.get("meta", {})

    timestamps = result.get("timestamp", [])

    closes = (
        result.get("indicators", {})
        .get("quote", [{}])[0]
        .get("close", [])
    )

    history = []

    for stamp, close in zip(timestamps, closes):

        if close is None:
            continue

        day = datetime.fromtimestamp(
            stamp,
            timezone.utc
        ).date().isoformat()

        history.append({
            "date": day,
            "value": round(float(close), 6)
        })

    price = meta.get("regularMarketPrice")

    if price is None and history:
        price = history[-1]["value"]

    previous = (
        meta.get("chartPreviousClose")
        or meta.get("previousClose")
    )

    change = None

    if price is not None and previous:
        change = round(
            (float(price) / float(previous) - 1) * 100,
            3
        )

    market_time = meta.get(
        "regularMarketTime",
        int(time.time())
    )

    return {
        "symbol": symbol,
        "price": (
            round(float(price), 6)
            if price is not None else None
        ),
        "changePct": change,
        "currency": meta.get("currency"),
        "observedAt": datetime.fromtimestamp(
            market_time,
            timezone.utc
        ).isoformat(),
        "history": history[-MAX_HISTORY:],
        "source": "Yahoo Finance chart data",
        "sourceType": "Unofficial market data endpoint",
        "url": (
            "https://finance.yahoo.com/quote/"
            + urllib.parse.quote(symbol, safe="=^.-")
        ),
    }


def collect_markets(data):

    for category, instruments in MARKETS.items():

        data.setdefault(category, {})

        for name, details in instruments.items():

            symbol, unit = details

            try:

                item = get_yahoo_data(symbol)

                item["unit"] = unit

                previous = data[category].get(
                    name, {}
                )

                item["history"] = merge_history(
                    previous.get("history", []),
                    item["history"]
                )

                data[category][name] = item

                print(
                    "OK:",
                    category,
                    name,
                    item["price"]
                )

                data["sources"][
                    category + "." + name
                ] = {
                    "status": "ok",
                    "checkedAt": timestamp(),
                }

            except Exception as error:

                print(
                    "FAILED:",
                    category,
                    name,
                    str(error)[:200]
                )

                data["sources"][
                    category + "." + name
                ] = {
                    "status": "failed",
                    "error": str(error)[:200],
                    "checkedAt": timestamp(),
                }


# --------------------------------------------------
# TOP TEN STOCKS
# --------------------------------------------------

def collect_stocks(data):

    existing = {
        item.get("symbol"): item
        for item in data.get("stocks", [])
        if isinstance(item, dict)
    }

    stocks = []

    for name, symbol in STOCKS:

        try:

            item = get_yahoo_data(symbol)

            item["name"] = name

            old = existing.get(symbol, {})

            item["history"] = merge_history(
                old.get("history", []),
                item["history"]
            )

            stocks.append(item)

            print("OK STOCK:", symbol)

        except Exception as error:

            print(
                "FAILED STOCK:",
                symbol,
                str(error)[:150]
            )

            if symbol in existing:
                stocks.append(existing[symbol])

    data["stocks"] = stocks


# --------------------------------------------------
# HEATING OIL SOURCE MONITOR
# --------------------------------------------------

def collect_heating_oil(data):

    try:

        fetch(HEATING_OIL_URL, "text/html")

        existing = data.get(
            "heatingOil",
            {}
        ).get("items", [])

        data["heatingOil"] = {
            "items": existing
        }

        data["sources"]["heatingOil"] = {
            "status": "source_checked",
            "checkedAt": timestamp(),
            "url": HEATING_OIL_URL,
            "note": (
                "Consumer Council NI source checked. "
                "No new price is added unless a dated "
                "published observation can be verified."
            ),
        }

        print("OK: Heating oil source checked")

    except Exception as error:

        print(
            "FAILED: Heating oil",
            str(error)[:200]
        )


# --------------------------------------------------
# PETROL AND DIESEL SOURCE MONITOR
# --------------------------------------------------

def collect_fuel(data):

    try:

        fetch(FUEL_URL, "text/html")

        existing = data.get(
            "fuel",
            {}
        ).get("items", [])

        data["fuel"] = {
            "items": existing
        }

        data["sources"]["roadFuel"] = {
            "status": "source_checked",
            "checkedAt": timestamp(),
            "url": FUEL_URL,
            "note": (
                "Official DESNZ weekly road-fuel "
                "statistics. UK averages are not "
                "Northern Ireland-only prices."
            ),
        }

        print("OK: Official road fuel source checked")

    except Exception as error:

        print(
            "FAILED: Road fuel",
            str(error)[:200]
        )


# --------------------------------------------------
# GROCERY PRICE SOURCE MONITOR
# --------------------------------------------------

def collect_groceries(data):

    try:

        fetch(FOOD_URL, "text/html")

        basket = data.setdefault(
            "householdBasket",
            {
                "items": [],
                "history": [],
            }
        )

        basket.setdefault("items", [])
        basket.setdefault("history", [])

        data["sources"]["foodCompass"] = {
            "status": "source_checked",
            "checkedAt": timestamp(),
            "url": FOOD_URL,
            "note": (
                "NI Food Compass source checked. "
                "No grocery price is invented. "
                "Dated product observations will "
                "be added when a stable public "
                "data export is confirmed."
            ),
        }

        print("OK: NI grocery source checked")

    except Exception as error:

        print(
            "FAILED: Grocery source",
            str(error)[:200]
        )


# --------------------------------------------------
# FINANCIAL AND SUPPLY NEWS
# --------------------------------------------------

def collect_news(data):

    finance = []
    supply = []

    for source, url in NEWS_FEEDS:

        try:

            root = ET.fromstring(
                fetch(
                    url,
                    "application/rss+xml, application/atom+xml"
                )
            )

            # RSS feeds

            for item in root.findall(".//item"):

                title = (
                    item.findtext("title")
                    or "Untitled"
                )

                link = (
                    item.findtext("link")
                    or ""
                )

                pub = item.findtext("pubDate") or ""

                try:
                    published = (
                        parsedate_to_datetime(pub)
                        .astimezone(timezone.utc)
                        .isoformat()
                    )
                except Exception:
                    published = None

                article = {
                    "title": html.unescape(title),
                    "url": link,
                    "source": source,
                    "publishedAt": published,
                }

                finance.append(article)

                if source == "DEFRA":
                    supply.append(article)

            # Atom feeds

            namespace = {
                "a": "http://www.w3.org/2005/Atom"
            }

            for item in root.findall(
                ".//a:entry",
                namespace
            ):

                title = item.findtext(
                    "a:title",
                    default="",
                    namespaces=namespace
                )

                link_node = item.find(
                    "a:link",
                    namespace
                )

                link = (
                    link_node.attrib.get("href", "")
                    if link_node is not None
                    else ""
                )

                published = (
                    item.findtext(
                        "a:published",
                        default="",
                        namespaces=namespace
                    )
                    or item.findtext(
                        "a:updated",
                        default="",
                        namespaces=namespace
                    )
                )

                article = {
                    "title": html.unescape(title),
                    "url": link,
                    "source": source,
                    "publishedAt": published or None,
                }

                finance.append(article)

                if source == "DEFRA":
                    supply.append(article)

            print("OK NEWS:", source)

        except Exception as error:

            print(
                "FAILED NEWS:",
                source,
                str(error)[:150]
            )

    def unique(items):

        seen = set()
        output = []

        items.sort(
            key=lambda x: x.get("publishedAt") or "",
            reverse=True
        )

        for item in items:

            link = item.get("url")

            if link and link not in seen:
                seen.add(link)
                output.append(item)

        return output[:30]

    data["news"] = unique(finance)
    data["supplyNews"] = unique(supply)


# --------------------------------------------------
# MAIN RUN
# --------------------------------------------------

def main():

    print("================================")
    print("DOOMWATCH MARKETS COLLECTION")
    print("================================")

    data = load_data()

    data.setdefault("sources", {})

    collect_markets(data)

    collect_stocks(data)

    collect_heating_oil(data)

    collect_fuel(data)

    collect_groceries(data)

    collect_news(data)

    data["schemaVersion"] = 1

    data["updatedAt"] = timestamp()

    data["generatedAt"] = data["updatedAt"]

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    DATA_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )

    print("================================")
    print("MARKETS COLLECTION COMPLETE")
    print("================================")
    print("Output:", DATA_FILE)


if __name__ == "__main__":
    main()
