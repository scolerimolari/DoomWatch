#!/usr/bin/env python3
"""
DOOMWATCH - MARKETS COLLECTOR
Build #83 - Aggregate Grocery Intelligence

Preserves existing market, stock, heating oil, fuel,
inflation and news collection.

Purpose:
- Aggregate weekly supermarket price index
- Official UK food and overall CPIH inflation history
- No individual grocery products, retailer basket totals or product-level records

Python standard library only.
"""

import csv
import html
import io
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


# ==================================================
# CONFIGURATION
# ==================================================

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_FILE = DATA_DIR / "markets.json"

USER_AGENT = (
    "Mozilla/5.0 (compatible; DoomWatch-Markets/2.0; "
    "+https://github.com/scolerimolari/DoomWatch)"
)

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

DEFRA_FOOD_URL = (
    "https://www.gov.uk/government/statistics/"
    "food-statistics-pocketbook/food-statistics-in-your-pocket"
)

DEFRA_FOOD_CSV_URL = (
    "https://assets.publishing.service.gov.uk/media/"
    "6a3cfd9ada47783d87723a5d/"
    "fsp-csv-cpih-inflation-09jul2026.csv"
)

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


# ==================================================
# GENERAL FUNCTIONS
# ==================================================

def timestamp():
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def today():
    return datetime.now(timezone.utc).date().isoformat()


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
        "householdBasket": {},
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


# ==================================================
# HTML EXTRACTION
# ==================================================

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
        return html.unescape("\n".join(self.parts))


def html_to_text(raw):
    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.get_text()


class LinkExtractor(HTMLParser):

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return

        attributes = dict(attrs)
        href = attributes.get("href")

        if href:
            self.links.append(html.unescape(href))


def find_fuel_csv(page):
    parser = LinkExtractor()
    parser.feed(page.decode("utf-8", errors="replace"))

    candidates = []

    for link in parser.links:
        if ".csv" not in link.lower():
            continue

        candidates.append(
            urllib.parse.urljoin(FUEL_URL, link)
        )

    if candidates:
        for candidate in candidates:
            if "2018" in candidate:
                return candidate

        return candidates[0]

    raise ValueError("Could not locate official road fuel CSV")


# ==================================================
# MONEY AND DATE PARSING
# ==================================================

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


def parse_fuel_date(value):
    value = str(value).strip()

    for pattern in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(
                value, pattern
            ).date().isoformat()

        except ValueError:
            pass

    return None


# ==================================================
# FINANCIAL MARKET DATA
# ==================================================

def get_yahoo_data(symbol):
    url = YAHOO_URL.format(
        urllib.parse.quote(symbol, safe="=^.-")
    )

    raw = json.loads(fetch(url, "application/json"))
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
            stamp, timezone.utc
        ).date().isoformat()

        history.append({
            "date": day,
            "value": round(float(close), 6),
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
            3,
        )

    market_time = meta.get(
        "regularMarketTime",
        int(time.time()),
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
            market_time, timezone.utc
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
                    item["history"],
                )

                data[category][name] = item

                print("OK:", category, name, item["price"])

                data["sources"][category + "." + name] = {
                    "status": "ok",
                    "checkedAt": timestamp(),
                }

            except Exception as error:
                print("FAILED:", category, name, str(error)[:200])

                data["sources"][category + "." + name] = {
                    "status": "failed",
                    "error": str(error)[:200],
                    "checkedAt": timestamp(),
                }


# ==================================================
# TOP TEN STOCKS
# ==================================================

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
                item["history"],
            )

            stocks.append(item)
            print("OK STOCK:", symbol)

        except Exception as error:
            print("FAILED STOCK:", symbol, str(error)[:150])

            if symbol in existing:
                stocks.append(existing[symbol])

    data["stocks"] = stocks


# ==================================================
# NORTHERN IRELAND HEATING OIL
# ==================================================

def parse_daily_oil_archive(text):
    observations = []

    pattern = re.compile(
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})"
        r"\s+£?\s*([\d,]+\.\d{2})"
        r"\s+£?\s*([\d,]+\.\d{2})"
        r"\s+£?\s*([\d,]+\.\d{2})",
        re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        try:
            day = datetime.strptime(
                match.group(1), "%d %B %Y"
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

    unique = {
        item["date"]: item
        for item in observations
    }

    return [unique[day] for day in sorted(unique)]


def parse_ballyclare_prices(text):
    positions = [
        match.start()
        for match in re.finditer(
            "Ballyclare", text, re.IGNORECASE
        )
    ]

    for position in positions:
        section = text[position:position + 2500]

        heading = re.search(
            r"300l\s+Average.*?"
            r"500l\s+Average.*?"
            r"900l\s+Average",
            section,
            re.IGNORECASE | re.DOTALL,
        )

        if not heading:
            continue

        price_section = section[heading.end():]

        values = re.findall(
            r"£\s*([\d,]+\.\d{2})",
            price_section,
        )

        prices = [
            parse_money(value)
            for value in values[:3]
        ]

        if (
            len(prices) == 3
            and all(value is not None for value in prices)
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
    old_item=None,
):
    old_item = old_item or {}

    history = merge_history(
        old_item.get("history", []),
        [{
            "date": day,
            "price": price,
            "source": source,
        }],
    )

    return {
        "id": item_id,
        "name": name,
        "price": price,
        "currency": "GBP",
        "unit": "GBP",
        "volumeLitres": litres,
        "pricePerLitre": round(price / litres, 4),
        "pricePer100Litres": round(price / litres * 100, 2),
        "observedAt": day,
        "date": day,
        "source": source,
        "url": HEATING_OIL_DAILY_URL,
        "history": history,
    }


def collect_heating_oil(data):
    print("HEATING OIL: collecting Consumer Council data")

    try:
        daily_raw = fetch(HEATING_OIL_DAILY_URL, "text/html")
        daily_text = html_to_text(daily_raw)
        archive = parse_daily_oil_archive(daily_text)

        if not archive:
            raise ValueError("No valid dated national oil observations found")

        latest = archive[-1]
        latest_day = latest["date"]

        existing_items = data.get(
            "heatingOil", {}
        ).get("items", [])

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
                historical_points,
            )

            item = oil_item(
                item_id,
                labels[litres],
                litres,
                latest["prices"][index],
                latest_day,
                "Consumer Council Northern Ireland",
                old,
            )

            item["history"] = history
            items.append(item)

            print(
                "OK HEATING OIL:",
                litres,
                "litres",
                latest["prices"][index],
                "history:",
                len(history),
            )

        regional_raw = fetch(HEATING_OIL_URL, "text/html")
        regional_text = html_to_text(regional_raw)

        ballyclare = parse_ballyclare_prices(regional_text)

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
                    old,
                )

                items.append(item)

                print("OK BALLYCLARE:", litres, "litres", ballyclare[index])

        else:
            print("WARNING: Ballyclare regional prices were not extracted")

            present = {item.get("id") for item in items}

            for item_id, old in existing.items():
                if (
                    item_id.startswith("ballyclare-")
                    and item_id not in present
                ):
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
                "Prices include 5% VAT. National and Ballyclare "
                "observations are kept separately."
            ),
        }

        print("HEATING OIL COMPLETE:", len(archive), "observations")

    except Exception as error:
        print("FAILED: Heating oil", str(error)[:250])

        data["sources"]["heatingOil"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": HEATING_OIL_URL,
            "error": str(error)[:250],
        }


# ==================================================
# PETROL AND DIESEL
# ==================================================

def parse_fuel_csv(raw):
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValueError("Fuel CSV has no column headings")

    fields = {
        str(name).strip().lower(): name
        for name in reader.fieldnames if name
    }

    date_column = fields.get("date")

    petrol_column = next(
        (
            original for lower, original in fields.items()
            if "ulsp" in lower and "pump price" in lower
        ),
        None,
    )

    diesel_column = next(
        (
            original for lower, original in fields.items()
            if "ulsd" in lower and "pump price" in lower
        ),
        None,
    )

    if not all([date_column, petrol_column, diesel_column]):
        raise ValueError("Could not identify fuel CSV columns")

    observations = []

    for row in reader:
        day = parse_fuel_date(row.get(date_column, ""))
        petrol = parse_money(row.get(petrol_column, ""))
        diesel = parse_money(row.get(diesel_column, ""))

        if not day or petrol is None or diesel is None:
            continue

        observations.append({
            "date": day,
            "petrol": petrol,
            "diesel": diesel,
        })

    unique = {
        item["date"]: item
        for item in observations
    }

    result = [unique[day] for day in sorted(unique)]

    if not result:
        raise ValueError("No valid fuel observations in CSV")

    return result


def collect_fuel(data):
    print("ROAD FUEL: collecting official DESNZ CSV")

    try:
        page = fetch(FUEL_URL, "text/html")
        csv_url = find_fuel_csv(page)

        raw_csv = fetch(
            csv_url,
            "text/csv, application/octet-stream, */*",
        )

        observations = parse_fuel_csv(raw_csv)
        latest = observations[-1]
        latest_day = latest["date"]

        old_items = data.get("fuel", {}).get("items", [])

        existing = {
            item.get("id"): item
            for item in old_items
            if isinstance(item, dict) and item.get("id")
        }

        items = []

        definitions = [
            ("petrol", "Unleaded petrol", "petrol", "ULSP"),
            ("diesel", "Diesel", "diesel", "ULSD"),
        ]

        for item_id, name, key, code in definitions:
            old = existing.get(item_id, {})

            history = [
                {
                    "date": observation["date"],
                    "price": observation[key],
                    "value": observation[key],
                }
                for observation in observations
            ]

            history = merge_history(
                old.get("history", []),
                history,
            )

            price = latest[key]
            previous_price = (
                observations[-2][key]
                if len(observations) > 1 else None
            )

            change = None

            if previous_price:
                change = round(price - previous_price, 2)

            items.append({
                "id": item_id,
                "name": name,
                "symbol": code,
                "price": price,
                "unit": "p/litre",
                "currency": "GBP",
                "change": change,
                "changePct": (
                    round((price / previous_price - 1) * 100, 2)
                    if previous_price else None
                ),
                "observedAt": latest_day,
                "date": latest_day,
                "history": history,
                "source": "DESNZ weekly road fuel prices",
                "sourceType": "Official UK average",
                "url": FUEL_URL,
            })

        data["fuel"] = {
            "items": items,
            "updatedAt": timestamp(),
            "source": "DESNZ weekly road fuel prices",
            "sourceUrl": FUEL_URL,
            "csvUrl": csv_url,
            "latestObservation": latest_day,
            "geographicScope": "United Kingdom average",
            "unit": "pence per litre",
        }

        data["sources"]["roadFuel"] = {
            "status": "ok",
            "checkedAt": timestamp(),
            "url": FUEL_URL,
            "csvUrl": csv_url,
            "observationsImported": len(observations),
            "latestObservation": latest_day,
            "note": (
                "Official UK weekly average pump prices. "
                "Not Northern Ireland-only or local forecourt prices."
            ),
        }

        print("ROAD FUEL COMPLETE:", len(observations))

    except Exception as error:
        print("FAILED: Road fuel", str(error)[:250])

        data["sources"]["roadFuel"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": FUEL_URL,
            "error": str(error)[:250],
        }


# ==================================================
# FOOD INFLATION
# ==================================================

def find_food_index_csv(page):
    parser = LinkExtractor()
    parser.feed(page.decode("utf-8", errors="replace"))

    candidates = []

    for link in parser.links:
        lower = link.lower()

        if (
            ".csv" in lower
            and "cpih" in lower
            and "inflation" in lower
        ):
            absolute = urllib.parse.urljoin(
                DEFRA_FOOD_URL, link
            )

            absolute = re.sub(
                r"/preview/?$",
                "",
                absolute,
                flags=re.IGNORECASE,
            )

            candidates.append(absolute)

    if candidates:
        for candidate in candidates:
            if "cpih-inflation" in candidate.lower():
                return candidate

        return candidates[0]

    return DEFRA_FOOD_CSV_URL


def parse_food_inflation_csv(raw):
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValueError("Food inflation CSV has no headings")

    field_map = {
        str(field).strip().lower(): field
        for field in reader.fieldnames if field
    }

    date_column = field_map.get("date")
    cdid_column = field_map.get("cdid")
    value_column = field_map.get("value")

    if not all([date_column, cdid_column, value_column]):
        raise ValueError("Unexpected food CSV columns")

    food = {}
    overall = {}

    for row in reader:
        raw_date = str(row.get(date_column, "")).strip()
        raw_code = str(row.get(cdid_column, "")).strip()
        raw_value = str(row.get(value_column, "")).strip()

        try:
            day = datetime.strptime(
                raw_date[:10], "%Y-%m-%d"
            ).date().replace(day=1).isoformat()

            value = float(
                raw_value.replace(",", "").replace("%", "")
            )

        except (ValueError, TypeError):
            continue

        code = raw_code.lower()

        point = {
            "date": day,
            "value": round(value, 2),
        }

        if "food inflation" in code and "overall" not in code:
            food[day] = point

        elif "overall inflation" in code:
            overall[day] = point

    food_history = [food[day] for day in sorted(food)]
    overall_history = [overall[day] for day in sorted(overall)]

    if not food_history or not overall_history:
        raise ValueError("Missing CPIH food or overall inflation rows")

    return food_history, overall_history


# ==================================================
# GROCERY PRODUCT EXTRACTION
# ==================================================

def normalise_text(value):
    value = html.unescape(str(value or "")).lower()
    value = re.sub(r"[^a-z0-9.]+", " ", value)
    return " ".join(value.split())


def extract_json_objects(value):
    """
    Recursively find JSON-LD Product objects.
    """

    found = []

    if isinstance(value, dict):
        item_type = value.get("@type", "")

        if isinstance(item_type, list):
            is_product = "Product" in item_type
        else:
            is_product = item_type == "Product"

        if is_product:
            found.append(value)

        for child in value.values():
            found.extend(extract_json_objects(child))

    elif isinstance(value, list):
        for child in value:
            found.extend(extract_json_objects(child))

    return found


class JsonLdExtractor(HTMLParser):

    def __init__(self):
        super().__init__()
        self.active = False
        self.buffer = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return

        attributes = dict(attrs)

        if (
            attributes.get("type", "").lower()
            == "application/ld+json"
        ):
            self.active = True
            self.buffer = []

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.active:
            self.documents.append("".join(self.buffer))
            self.active = False
            self.buffer = []


def extract_products(raw):
    parser = JsonLdExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))

    products = []

    for document in parser.documents:
        try:
            decoded = json.loads(document)

            products.extend(
                extract_json_objects(decoded)
            )

        except Exception:
            continue

    return products


def extract_offer_prices(product):
    offers = product.get("offers", [])

    if isinstance(offers, dict):
        offers = [offers]

    results = []

    for offer in offers:
        if not isinstance(offer, dict):
            continue

        currency = (
            offer.get("priceCurrency")
            or product.get("priceCurrency")
        )

        if currency != "GBP":
            continue

        price = parse_money(offer.get("price"))

        if price is None:
            continue

        results.append({
            "price": price,
            "currency": currency,
            "availability": offer.get("availability"),
        })

    return results


def product_match_score(title, search):
    title_words = set(normalise_text(title).split())
    search_words = set(normalise_text(search).split())

    if not title_words or not search_words:
        return 0

    important = {
        word for word in search_words
        if len(word) > 2
    }

    if not important:
        return 0

    matched = important.intersection(title_words)

    return len(matched) / len(important)


def extract_pack_quantity(title, target_unit):
    """
    Extract a measurable pack size from the product title.

    Returns a quantity in the requested unit.
    Does not guess missing pack sizes.
    """

    text = normalise_text(title)

    if target_unit == "gram":
        matches = re.findall(
            r"(\d+(?:\.\d+)?)\s*(kg|g)\b",
            text,
        )

        if not matches:
            return None

        value, unit = matches[0]
        value = float(value)

        return value * 1000 if unit == "kg" else value

    if target_unit == "litre":
        matches = re.findall(
            r"(\d+(?:\.\d+)?)\s*(litres?|liters?|l|ml)\b",
            text,
        )

        if not matches:
            return None

        value, unit = matches[0]
        value = float(value)

        if unit == "ml":
            return value / 1000

        return value

    if target_unit == "each":
        matches = re.findall(
            r"(\d+)\s*(?:pack|pk|eggs?|bags?|rolls?)\b",
            text,
        )

        if matches:
            return float(matches[0])

        return None

    return None


def get_product_price(product, expected_search, expected_unit):
    title = product.get("name") or ""

    if not title:
        return None

    score = product_match_score(
        title,
        expected_search,
    )

    if score < 0.60:
        return None

    offers = extract_offer_prices(product)

    if not offers:
        return None

    # Do not use aggregate low/high prices.
    # Only accept a specific GBP offer.

    offer = offers[0]

    quantity = extract_pack_quantity(
        title,
        expected_unit,
    )

    if quantity is None or quantity <= 0:
        return None

    unit_price = round(
        offer["price"] / quantity,
        4,
    )

    return {
        "title": title,
        "price": offer["price"],
        "currency": "GBP",
        "packQuantity": quantity,
        "unit": expected_unit,
        "unitPrice": unit_price,
        "matchScore": round(score, 3),
        "availability": offer.get("availability"),
    }


# ==================================================
# FREE UK SUPERMARKET SHELF-PRICE INDEX
# ==================================================

def collect_supermarket_index(data):
    """
    Import the public Yappman UK Online Shelf-Price Index.
    This is a weekly aggregate index, not individual product prices.
    Dataset is public and licensed CC BY 4.0.
    """

    url = (
        "https://api.apify.com/v2/datasets/"
        "AvRCWqFinCiNjx3sP/items?format=json"
    )

    basket = data.setdefault("householdBasket", {})
    basket.setdefault("items", [])
    basket.setdefault("history", [])

    print("SUPERMARKET INDEX: importing public weekly dataset")

    try:
        raw = fetch(url, "application/json")
        payload = json.loads(raw.decode("utf-8"))

        if isinstance(payload, dict):
            payload = payload.get("rows", [])
        if not isinstance(payload, list):
            raise ValueError("Dataset response did not contain a rows list")

        records = []

        for row in payload:
            if not isinstance(row, dict):
                continue

            if not row.get("vintage"):
                continue

            try:
                level = float(row.get("level"))
            except (TypeError, ValueError):
                continue

            record = dict(row)
            record["level"] = level
            records.append(record)

        if not records:
            raise ValueError("No valid dated index records were returned")

        records.sort(
            key=lambda row: (
                str(row.get("vintage", "")),
                str(row.get("recordType", "")),
                str(row.get("retailer", "")),
                str(row.get("class", "")),
            )
        )

        headlines = [
            row for row in records
            if row.get("recordType") == "headline"
        ]

        if not headlines:
            raise ValueError("Dataset contains no headline index records")

        latest = headlines[-1]

        basket["supermarketIndexHistory"] = records
        basket["supermarketIndexUpdatedAt"] = timestamp()
        basket["supermarketIndex"] = latest

        data.setdefault("sources", {})["supermarketPriceIndex"] = {
            "status": "ok",
            "checkedAt": timestamp(),
            "url": "https://data.yappman.com/shelf-price-index/",
            "datasetUrl": url,
            "licence": "CC BY 4.0",
            "latestVintage": latest.get("vintage"),
            "recordsImported": len(records),
            "note": (
                "Weekly UK online shelf-price index for Tesco, "
                "Sainsbury's, Asda and Aldi. Aggregate index only; "
                "not individual product prices, household spending "
                "or ONS CPI. Credit Yappman Data, CC BY 4.0."
            ),
        }

        print(
            "OK SUPERMARKET INDEX:",
            latest.get("vintage"),
            latest.get("level"),
            "records:",
            len(records),
        )

    except Exception as error:
        print("FAILED: Supermarket shelf-price index", str(error)[:250])

        data.setdefault("sources", {})["supermarketPriceIndex"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": "https://data.yappman.com/shelf-price-index/",
            "error": str(error)[:250],
            "note": "No supermarket index values were added or estimated.",
        }


# ==================================================
# OFFICIAL CPIH FOOD AND OVERALL INFLATION
# ==================================================

def collect_groceries(data):
    """
    Collect official inflation statistics.

    Only aggregate official inflation and index series are retained.
    """

    basket = data.setdefault(
        "householdBasket",
        {
            "items": [],
            "history": [],
        },
    )

    # Remove legacy product-level grocery data from previous builds.
    for key in ("items", "history", "observations", "retailers", "dailyProductPriceHistory", "dailyProductPriceLatestDate", "dailyProductPriceLatestCount", "productCount", "retailerCount", "latestDate", "comparisonNote"):
        basket.pop(key, None)

    data.setdefault("sources", {}).pop("foodCompass", None)
    data["sources"].pop("groceryBasket", None)
    data["sources"].pop("dailyGroceryBasket", None)

    print("GROCERIES: collecting official CPIH inflation")

    try:
        page = fetch(DEFRA_FOOD_URL, "text/html")
        csv_url = find_food_index_csv(page)

        raw = fetch(
            csv_url,
            "text/csv, application/octet-stream, */*",
        )

        food_history, overall_history = (
            parse_food_inflation_csv(raw)
        )

        food_history = merge_history(
            data.get("foodInflationHistory", []),
            food_history,
        )

        overall_history = merge_history(
            data.get("overallInflationHistory", []),
            overall_history,
        )

        latest_food = food_history[-1]
        latest_overall = overall_history[-1]

        data["foodInflationHistory"] = food_history
        data["overallInflationHistory"] = overall_history

        data["foodInflation"] = {
            "name": "CPIH food inflation",
            "value": latest_food["value"],
            "date": latest_food["date"],
            "unit": "% year-on-year",
            "source": "ONS / Defra CPIH",
            "url": DEFRA_FOOD_URL,
        }

        data["overallInflation"] = {
            "name": "CPIH overall inflation",
            "value": latest_overall["value"],
            "date": latest_overall["date"],
            "unit": "% year-on-year",
            "source": "ONS / Defra CPIH",
            "url": DEFRA_FOOD_URL,
        }

        basket["foodInflationHistory"] = food_history
        basket["overallInflationHistory"] = overall_history
        basket["foodInflation"] = data["foodInflation"]
        basket["overallInflation"] = data["overallInflation"]
        basket["updatedAt"] = timestamp()

        basket.pop("priceIndexHistory", None)
        basket.pop("inflationHistory", None)
        basket.pop("foodPriceIndex", None)

        data["sources"]["foodInflation"] = {
            "status": "ok",
            "checkedAt": timestamp(),
            "url": DEFRA_FOOD_URL,
            "csvUrl": csv_url,
            "observationsImported": len(food_history),
            "latestObservation": latest_food["date"],
            "note": (
                "Official UK-wide CPIH food inflation. "
                "This is not a local supermarket basket."
            ),
        }

        data["sources"]["overallInflation"] = {
            "status": "ok",
            "checkedAt": timestamp(),
            "url": DEFRA_FOOD_URL,
            "csvUrl": csv_url,
            "observationsImported": len(overall_history),
            "latestObservation": latest_overall["date"],
            "note": (
                "Official UK-wide CPIH overall inflation."
            ),
        }

        print(
            "OK FOOD INFLATION:",
            latest_food["date"],
            latest_food["value"],
        )

        print(
            "OK OVERALL INFLATION:",
            latest_overall["date"],
            latest_overall["value"],
        )

    except Exception as error:
        print(
            "FAILED: Official food inflation",
            str(error)[:250],
        )

        data["sources"]["foodInflation"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": DEFRA_FOOD_URL,
            "error": str(error)[:250],
        }


# ==================================================
# FINANCIAL AND SUPPLY NEWS
# ==================================================

def collect_news(data):
    finance = []
    supply = []

    for source, url in NEWS_FEEDS:
        try:
            root = ET.fromstring(
                fetch(
                    url,
                    "application/rss+xml, application/atom+xml",
                )
            )

            for item in root.findall(".//item"):
                title = item.findtext("title") or "Untitled"
                link = item.findtext("link") or ""
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
                ".//a:entry", namespace
            ):
                title = item.findtext(
                    "a:title",
                    default="",
                    namespaces=namespace,
                )

                link_node = item.find("a:link", namespace)

                link = (
                    link_node.attrib.get("href", "")
                    if link_node is not None else ""
                )

                published = (
                    item.findtext(
                        "a:published",
                        default="",
                        namespaces=namespace,
                    )
                    or item.findtext(
                        "a:updated",
                        default="",
                        namespaces=namespace,
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
            print("FAILED NEWS:", source, str(error)[:150])

    def unique(items):
        seen = set()
        output = []

        items.sort(
            key=lambda item: item.get("publishedAt") or "",
            reverse=True,
        )

        for item in items:
            link = item.get("url")

            if link and link not in seen:
                seen.add(link)
                output.append(item)

        return output[:30]

    data["news"] = unique(finance)
    data["supplyNews"] = unique(supply)


# ==================================================
# MAIN RUN
# ==================================================

def main():
    print("================================")
    print("DOOMWATCH MARKETS COLLECTION")
    print("BUILD 83 - AGGREGATE GROCERY INTELLIGENCE")
    print("================================")

    data = load_data()
    data.setdefault("sources", {})

    # Existing collection systems.
    collect_markets(data)
    collect_stocks(data)
    collect_heating_oil(data)
    collect_fuel(data)
    collect_groceries(data)

    # Aggregate weekly supermarket index only; no product-level data.
    collect_supermarket_index(data)

    # Enforce an aggregate-only grocery schema after all collectors have run.
    # Older builds and the index importer may recreate empty legacy basket keys.
    basket = data.setdefault("householdBasket", {})
    allowed_grocery_fields = {
        "foodInflationHistory",
        "overallInflationHistory",
        "foodInflation",
        "overallInflation",
        "supermarketIndexHistory",
        "supermarketIndexUpdatedAt",
        "supermarketIndex",
    }
    for key in list(basket):
        if key not in allowed_grocery_fields:
            basket.pop(key, None)

    # Remove retired product-level source metadata.
    for key in ("foodCompass", "groceryBasket", "dailyGroceryBasket"):
        data.setdefault("sources", {}).pop(key, None)

    # Existing news collection.
    collect_news(data)

    data["schemaVersion"] = 1
    data["updatedAt"] = timestamp()
    data["generatedAt"] = data["updatedAt"]

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    DATA_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("================================")
    print("MARKETS COLLECTION COMPLETE")
    print("================================")
    print("Output:", DATA_FILE)


if __name__ == "__main__":
    main()
