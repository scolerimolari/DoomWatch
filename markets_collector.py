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

HEATING_OIL_URL = (
    "https://www.consumercouncil.org.uk/"
    "home-heating/price-checker"
)

HEATING_OIL_DAILY_URL = (
    "https://www.consumercouncil.org.uk/"
    "home-heating/price-checker/daily"
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
# HTML TEXT EXTRACTION
# --------------------------------------------------

class TextExtractor(HTMLParser):

    BLOCK_TAGS = {
        "p", "div", "br", "tr", "td", "th",
        "li", "h1", "h2", "h3", "h4",
        "section", "article"
    }

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return html.unescape(
            "\n".join(self.parts)
        )


def html_to_text(raw):

    parser = TextExtractor()

    parser.feed(
        raw.decode("utf-8", errors="replace")
    )

    return parser.get_text()


def parse_money(value):

    try:
        cleaned = (
            str(value)
            .replace("£", "")
            .replace(",", "")
            .strip()
        )

        number = float(cleaned)

        if number <= 0 or number > 100000:
            return None

        return round(number, 2)

    except (TypeError, ValueError):
        return None


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

                previous = data[category].get(name, {})

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

                data["sources"][category + "." + name] = {
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

                data["sources"][category + "." + name] = {
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
# NORTHERN IRELAND HEATING OIL
# --------------------------------------------------

def parse_daily_oil_archive(text):

    observations = []

    pattern = re.compile(
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})"
        r"\s+£?\s*([\d,]+\.\d{2})"
        r"\s+£?\s*([\d,]+\.\d{2})"
        r"\s+£?\s*([\d,]+\.\d{2})",
        re.IGNORECASE
    )

    for match in pattern.finditer(text):

        try:
            day = datetime.strptime(
                match.group(1),
                "%d %B %Y"
            ).date().isoformat()

            prices = [
                parse_money(match.group(i))
                for i in (2, 3, 4)
            ]

            if any(value is None for value in prices):
                continue

            observations.append({
                "date": day,
                "prices": prices,
            })

        except ValueError:
            continue

    # Remove duplicate dates while retaining valid records.

    unique = {}

    for observation in observations:
        unique[observation["date"]] = observation

    return [
        unique[day]
        for day in sorted(unique)
    ]


def parse_ballyclare_prices(text):

    positions = [
        match.start()
        for match in re.finditer(
            "Ballyclare",
            text,
            re.IGNORECASE
        )
    ]

    for position in positions:

        section = text[position:position + 2500]

        heading = re.search(
            r"300l\s+Average.*?"
            r"500l\s+Average.*?"
            r"900l\s+Average",
            section,
            re.IGNORECASE | re.DOTALL
        )

        if not heading:
            continue

        price_section = section[heading.end():]

        values = re.findall(
            r"£\s*([\d,]+\.\d{2})",
            price_section
        )

        prices = [
            parse_money(value)
            for value in values[:3]
        ]

        if len(prices) == 3 and all(
            value is not None for value in prices
        ):
            return prices

    return None


def oil_item(
    item_id,
    name,
    litres,
    price,
    day,
    source,
    old_item=None
):

    old_item = old_item or {}

    history = merge_history(
        old_item.get("history", []),
        [{
            "date": day,
            "price": price,
            "source": source,
        }]
    )

    return {
        "id": item_id,
        "name": name,
        "price": price,
        "currency": "GBP",
        "unit": "GBP",
        "volumeLitres": litres,
        "pricePerLitre": round(price / litres, 4),
        "pricePer100Litres": round(
            price / litres * 100,
            2
        ),
        "observedAt": day,
        "date": day,
        "source": source,
        "url": HEATING_OIL_DAILY_URL,
        "history": history,
    }


def collect_heating_oil(data):

    print("HEATING OIL: collecting Consumer Council data")

    try:

        # Daily archive provides national historical prices.

        daily_raw = fetch(
            HEATING_OIL_DAILY_URL,
            "text/html"
        )

        daily_text = html_to_text(daily_raw)

        archive = parse_daily_oil_archive(daily_text)

        if not archive:
            raise ValueError(
                "No valid dated national oil observations found"
            )

        latest = archive[-1]
        latest_day = latest["date"]

        existing_items = (
            data.get("heatingOil", {})
            .get("items", [])
        )

        existing = {
            item.get("id"): item
            for item in existing_items
            if isinstance(item, dict) and item.get("id")
        }

        items = []

        volumes = [300, 500, 900]

        labels = {
            300: "NI average 300 litres",
            500: "NI average 500 litres",
            900: "NI average 900 litres",
        }

        # Import the full dated national archive.

        for index, litres in enumerate(volumes):

            item_id = f"ni-{litres}l"

            old = existing.get(item_id, {})

            historical_points = [
                {
                    "date": observation["date"],
                    "price": observation["prices"][index],
                    "source": "Consumer Council NI daily archive",
                }
                for observation in archive
            ]

            history = merge_history(
                old.get("history", []),
                historical_points
            )

            price = latest["prices"][index]

            item = oil_item(
                item_id,
                labels[litres],
                litres,
                price,
                latest_day,
                "Consumer Council Northern Ireland",
                old
            )

            item["history"] = history

            items.append(item)

            print(
                "OK HEATING OIL:",
                litres,
                "litres",
                price,
                "history:",
                len(history)
            )

        # Regional comparison: Ballyclare.

        regional_raw = fetch(
            HEATING_OIL_URL,
            "text/html"
        )

        regional_text = html_to_text(regional_raw)

        ballyclare = parse_ballyclare_prices(
            regional_text
        )

        if ballyclare:

            for index, litres in enumerate(volumes):

                item_id = f"ballyclare-{litres}l"
                old = existing.get(item_id, {})

                item = oil_item(
                    item_id,
                    f"Ballyclare {litres} litres",
                    litres,
                    ballyclare[index],
                    latest_day,
                    "Consumer Council NI — Ballyclare",
                    old
                )

                items.append(item)

                print(
                    "OK BALLYCLARE:",
                    litres,
                    "litres",
                    ballyclare[index]
                )

        else:

            print(
                "WARNING: Ballyclare regional prices "
                "were not extracted"
            )

            # Retain existing Ballyclare records if source layout changes.

            for item_id, old in existing.items():
                if item_id.startswith("ballyclare-"):
                    if item_id not in {
                        item.get("id") for item in items
                    }:
                        items.append(old)

        data["heatingOil"] = {
            "items": items,
            "updatedAt": timestamp(),
            "source": "Consumer Council Northern Ireland",
            "sourceUrl": HEATING_OIL_URL,
            "dailyArchiveUrl": HEATING_OIL_DAILY_URL,
            "vatIncluded": True,
            "vatRate": 5,
        }

        data["sources"]["heatingOil"] = {
            "status": "ok",
            "checkedAt": timestamp(),
            "url": HEATING_OIL_URL,
            "dailyArchiveUrl": HEATING_OIL_DAILY_URL,
            "observationsImported": len(archive),
            "latestObservation": latest_day,
            "note": (
                "Consumer Council NI published averages. "
                "Prices include 5% VAT. "
                "National and Ballyclare observations "
                "are kept separately."
            ),
        }

        print(
            "HEATING OIL COMPLETE:",
            len(archive),
            "dated national observations"
        )

    except Exception as error:

        print(
            "FAILED: Heating oil",
            str(error)[:250]
        )

        data["sources"]["heatingOil"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": HEATING_OIL_URL,
            "error": str(error)[:250],
        }


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
