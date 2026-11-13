#!/usr/bin/env python3
"""
DOOMWATCH - MARKETS COLLECTOR
Build #82 - Grocery Intelligence

Preserves existing market, stock, heating oil, fuel,
inflation and news collection.

Adds:
- Tesco, Asda, Sainsbury's and Lidl grocery monitoring
- Fixed 25-product household basket
- JSON-LD product price extraction
- Pack-size and unit-price normalisation
- Separate loyalty and standard prices where supplied
- Dated product price observations
- Historical basket totals
- Retailer collection status

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
# GROCERY INTELLIGENCE CONFIGURATION
# ==================================================

GROCERY_RETAILERS = {
    "tesco": {
        "name": "Tesco",
        "search": (
            "https://www.tesco.com/groceries/en-GB/search"
            "?query={query}"
        ),
    },
    "asda": {
        "name": "Asda",
        "search": (
            "https://groceries.asda.com/search/{query}"
        ),
    },
    "sainsburys": {
        "name": "Sainsbury's",
        "search": (
            "https://www.sainsburys.co.uk/gol-ui/SearchResults/"
            "?query={query}"
        ),
    },
    "lidl": {
        "name": "Lidl",
        "search": (
            "https://www.lidl.co.uk/q/search?q={query}"
        ),
    },
}

# Fixed basket specifications.
# Quantities are the target comparison sizes.
# A retailer product must expose a recognisable matching
# pack quantity before it is included in the comparison.

GROCERY_PRODUCTS = [
    ("milk", "Semi-skimmed milk", "2.27L", 2.27, "litre",
     "semi skimmed milk 2.27 litre"),

    ("whole_milk", "Whole milk", "2.27L", 2.27, "litre",
     "whole milk 2.27 litre"),

    ("bread", "White sliced bread", "800g", 800, "gram",
     "white sliced loaf 800g"),

    ("wholemeal_bread", "Wholemeal bread", "800g", 800, "gram",
     "wholemeal sliced loaf 800g"),

    ("eggs", "Free range eggs", "12 eggs", 12, "each",
     "12 free range eggs"),

    ("butter", "Salted butter", "250g", 250, "gram",
     "salted butter 250g"),

    ("cheese", "Mature cheddar", "400g", 400, "gram",
     "mature cheddar 400g"),

    ("chicken", "Chicken breast", "1kg", 1000, "gram",
     "chicken breast 1kg"),

    ("mince", "Beef mince", "500g", 500, "gram",
     "beef mince 500g"),

    ("sausages", "Pork sausages", "8 pack", 8, "each",
     "pork sausages 8 pack"),

    ("potatoes", "White potatoes", "2.5kg", 2500, "gram",
     "white potatoes 2.5kg"),

    ("carrots", "Carrots", "1kg", 1000, "gram",
     "carrots 1kg"),

    ("onions", "Brown onions", "1kg", 1000, "gram",
     "brown onions 1kg"),

    ("bananas", "Bananas", "1kg", 1000, "gram",
     "bananas 1kg"),

    ("apples", "Apples", "6 pack", 6, "each",
     "apples 6 pack"),

    ("broccoli", "Broccoli", "1 head", 1, "each",
     "broccoli 1 head"),

    ("rice", "Long grain rice", "1kg", 1000, "gram",
     "long grain rice 1kg"),

    ("pasta", "Dried pasta", "500g", 500, "gram",
     "dried pasta 500g"),

    ("flour", "Plain flour", "1.5kg", 1500, "gram",
     "plain flour 1.5kg"),

    ("sugar", "Granulated sugar", "1kg", 1000, "gram",
     "granulated sugar 1kg"),

    ("cooking_oil", "Vegetable oil", "1L", 1, "litre",
     "vegetable oil 1 litre"),

    ("tea", "Tea bags", "160 pack", 160, "each",
     "160 tea bags"),

    ("coffee", "Instant coffee", "200g", 200, "gram",
     "instant coffee 200g"),

    ("toilet_roll", "Toilet roll", "9 pack", 9, "each",
     "toilet rolls 9 pack"),

    ("washing_liquid", "Laundry detergent", "1.5L", 1.5, "litre",
     "laundry detergent 1.5 litre"),
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
        "householdBasket": {
            "items": [],
            "history": [],
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
# GROCERY RETAILER COLLECTION
# ==================================================

def retailer_search_url(retailer, query):
    template = GROCERY_RETAILERS[retailer]["search"]

    return template.format(
        query=urllib.parse.quote(query)
    )


def collect_retailer_product(retailer, product):
    url = retailer_search_url(
        retailer,
        product["search"],
    )

    raw = fetch(
        url,
        "text/html,application/xhtml+xml",
    )

    candidates = extract_products(raw)

    matches = []

    for candidate in candidates:
        result = get_product_price(
            candidate,
            product["search"],
            product["unit"],
        )

        if result:
            matches.append(result)

    if not matches:
        raise ValueError(
            "No verifiable matching GBP product offer"
        )

    matches.sort(
        key=lambda item: (
            item["matchScore"],
            -item["price"],
        ),
        reverse=True,
    )

    selected = matches[0]

    return {
        "retailer": retailer,
        "retailerName": GROCERY_RETAILERS[retailer]["name"],
        "productId": product["id"],
        "productName": product["name"],
        "matchedProduct": selected["title"],
        "price": selected["price"],
        "currency": "GBP",
        "packQuantity": selected["packQuantity"],
        "packUnit": selected["unit"],
        "unitPrice": selected["unitPrice"],
        "unitPriceLabel": (
            "GBP per " + selected["unit"]
        ),
        "loyaltyPrice": None,
        "standardPrice": selected["price"],
        "loyaltyStatus": "not separately verified",
        "matchScore": selected["matchScore"],
        "availability": selected["availability"],
        "observedAt": timestamp(),
        "date": today(),
        "source": "Retailer product structured data",
        "sourceUrl": url,
        "verification": "structured product offer",
    }


def collect_grocery_retailer(retailer, old_items):
    observations = []
    failures = []

    for product in GROCERY_PRODUCTS:
        try:
            observation = collect_retailer_product(
                retailer,
                {
                    "id": product[0],
                    "name": product[1],
                    "pack": product[2],
                    "quantity": product[3],
                    "unit": product[4],
                    "search": product[5],
                },
            )

            observations.append(observation)

            print(
                "OK GROCERY:",
                retailer,
                product[0],
                observation["price"],
            )

            # Avoid aggressive requests.
            time.sleep(1)

        except Exception as error:
            failures.append({
                "productId": product[0],
                "error": str(error)[:180],
            })

            print(
                "UNAVAILABLE:",
                retailer,
                product[0],
                str(error)[:100],
            )

    return observations, failures


# ==================================================
# GROCERY HISTORY AND BASKET TOTALS
# ==================================================

def grocery_observation_key(item):
    return (
        item.get("date"),
        item.get("retailer"),
        item.get("productId"),
    )


def merge_grocery_observations(old, new):
    """
    Preserve historic observations.

    One observation per retailer/product/date.
    A new observation for the same date replaces that date's
    previous observation.
    """

    records = {}

    for item in old or []:
        if isinstance(item, dict):
            key = grocery_observation_key(item)

            if all(key):
                records[key] = item

    for item in new or []:
        if isinstance(item, dict):
            key = grocery_observation_key(item)

            if all(key):
                records[key] = item

    result = sorted(
        records.values(),
        key=lambda item: (
            item.get("date", ""),
            item.get("retailer", ""),
            item.get("productId", ""),
        ),
    )

    return result[-MAX_HISTORY * 100:]


def calculate_grocery_baskets(observations):
    """
    Basket totals are calculated only when all 25 products
    have verified observations for the retailer on that date.

    Missing products are not treated as zero.
    """

    grouped = {}

    for item in observations:
        key = (
            item.get("date"),
            item.get("retailer"),
        )

        grouped.setdefault(key, {})
        grouped[key][item.get("productId")] = item

    expected = {
        product[0] for product in GROCERY_PRODUCTS
    }

    baskets = []

    for (day, retailer), products in grouped.items():
        present = set(products.keys())

        missing = sorted(expected - present)

        total = None

        if not missing and len(products) == len(expected):
            total = round(
                sum(
                    item["price"]
                    for item in products.values()
                ),
                2,
            )

        baskets.append({
            "date": day,
            "retailer": retailer,
            "retailerName": GROCERY_RETAILERS[retailer]["name"],
            "total": total,
            "currency": "GBP",
            "productsFound": len(present),
            "productsExpected": len(expected),
            "missingProducts": missing,
            "complete": len(missing) == 0,
            "source": "DoomWatch verified product observations",
        })

    return sorted(
        baskets,
        key=lambda item: (
            item["date"],
            item["retailer"],
        ),
    )


def collect_retailer_basket(data):
    print("================================")
    print("GROCERY INTELLIGENCE COLLECTION")
    print("================================")

    basket = data.setdefault(
        "householdBasket",
        {
            "items": [],
            "history": [],
        },
    )

    basket.setdefault("items", [])
    basket.setdefault("history", [])

    old_observations = basket.get(
        "observations", []
    )

    if not isinstance(old_observations, list):
        old_observations = []

    new_observations = []

    retailer_status = {}

    for retailer in GROCERY_RETAILERS:
        print("GROCERY RETAILER:", retailer)

        try:
            observations, failures = collect_grocery_retailer(
                retailer,
                old_observations,
            )

            new_observations.extend(observations)

            retailer_status[retailer] = {
                "status": (
                    "ok" if observations else "unavailable"
                ),
                "checkedAt": timestamp(),
                "productsFound": len(observations),
                "productsExpected": len(GROCERY_PRODUCTS),
                "failures": failures,
            }

        except Exception as error:
            print(
                "RETAILER FAILED:",
                retailer,
                str(error)[:180],
            )

            retailer_status[retailer] = {
                "status": "failed",
                "checkedAt": timestamp(),
                "error": str(error)[:180],
            }

    observations = merge_grocery_observations(
        old_observations,
        new_observations,
    )

    basket_history = calculate_grocery_baskets(
        observations
    )

    # Preserve previous historical basket totals.
    old_history = basket.get("history", [])

    combined_history = {}

    for item in old_history:
        if not isinstance(item, dict):
            continue

        key = (
            item.get("date"),
            item.get("retailer"),
        )

        if all(key):
            combined_history[key] = item

    for item in basket_history:
        key = (
            item.get("date"),
            item.get("retailer"),
        )

        combined_history[key] = item

    final_history = sorted(
        combined_history.values(),
        key=lambda item: (
            item.get("date", ""),
            item.get("retailer", ""),
        ),
    )[-MAX_HISTORY * 4:]

    # Preserve the existing householdBasket structure.
    # Product observations and inflation data remain separate.

    basket["observations"] = observations
    basket["history"] = final_history

    basket["items"] = [
        {
            "id": product[0],
            "name": product[1],
            "targetPack": product[2],
            "targetQuantity": product[3],
            "unit": product[4],
        }
        for product in GROCERY_PRODUCTS
    ]

    basket["retailers"] = retailer_status
    basket["updatedAt"] = timestamp()

    basket["retailerCount"] = len(GROCERY_RETAILERS)
    basket["productCount"] = len(GROCERY_PRODUCTS)

    basket["latestDate"] = today()

    basket["comparisonNote"] = (
        "Only verified structured product offers are recorded. "
        "Prices are not invented. Incomplete retailer baskets "
        "are not given a complete basket total. Loyalty prices "
        "are not inferred from standard prices."
    )

    data["sources"]["groceryBasket"] = {
        "status": (
            "ok"
            if any(
                value.get("status") == "ok"
                for value in retailer_status.values()
            )
            else "unavailable"
        ),
        "checkedAt": timestamp(),
        "retailers": retailer_status,
        "productsExpected": len(GROCERY_PRODUCTS),
        "observationsStored": len(observations),
        "basketSnapshots": len(final_history),
        "note": (
            "Retailer prices require structured product data. "
            "A failed extraction is not evidence that a product "
            "is unavailable or has a zero price."
        ),
    }

    print("GROCERY COLLECTION COMPLETE")
    print("Observations:", len(observations))
    print("Basket snapshots:", len(final_history))

    for retailer, status in retailer_status.items():
        print(
            retailer,
            status.get("status"),
            status.get("productsFound", 0),
            "/",
            len(GROCERY_PRODUCTS),
        )


# ==================================================
# FREE UK DAILY 212-ITEM GROCERY BASKET
# ==================================================

def collect_daily_grocery_basket(data):
    """
    Import Yappman Data's public UK daily 212-item basket.
    Keep price fields and retailer identifiers only; do not
    copy retailer names, descriptions, images or other content.
    Dataset is public and licensed CC BY 4.0.
    """

    url = (
        "https://api.apify.com/v2/datasets/"
        "ynAT9NPps2EdjMOJa/items?format=json&limit=100000"
    )

    basket = data.setdefault("householdBasket", {})
    old = basket.get("dailyProductPriceHistory", [])
    if not isinstance(old, list):
        old = []

    print("DAILY GROCERY BASKET: importing public 212-item dataset")

    try:
        raw = fetch(url, "application/json")
        payload = json.loads(raw.decode("utf-8"))

        if isinstance(payload, dict):
            payload = payload.get("items", payload.get("rows", []))
        if not isinstance(payload, list):
            raise ValueError("Dataset response did not contain a rows list")

        records = {}

        def numeric(value):
            if value is None or value == "":
                return None
            try:
                result = float(str(value).replace(",", "").replace("£", "").strip())
                return round(result, 4) if result >= 0 else None
            except (TypeError, ValueError):
                return None

        def normalise(row):
            if not isinstance(row, dict):
                return None

            scraped = row.get("scrapedAt") or row.get("scraped_at")
            retailer = str(row.get("retailer") or "").strip().lower()
            product_id = str(
                row.get("retailerProductId")
                or row.get("retailer_product_id")
                or ""
            ).strip()
            price = numeric(row.get("price"))

            if not scraped or not retailer or not product_id or price is None:
                return None

            ean = row.get("ean")
            if isinstance(ean, str):
                ean = [ean] if ean else []
            elif not isinstance(ean, list):
                ean = []

            loyalty = numeric(row.get("loyaltyPrice"))
            was_price = numeric(row.get("wasPrice"))
            unit_price = numeric(row.get("unitPrice"))

            return {
                "scrapedAt": str(scraped),
                "date": str(scraped)[:10],
                "retailer": retailer,
                "retailerProductId": product_id,
                "ean": [str(code) for code in ean if code],
                "matchKey": str(row.get("matchKey") or "")[:240],
                "matchKeyV1": str(row.get("matchKeyV1") or "")[:240],
                "matchBasis": str(row.get("matchBasis") or "")[:40],
                "matchConfidence": numeric(row.get("matchConfidence")),
                "price": price,
                "wasPrice": was_price,
                "loyaltyPrice": loyalty,
                "unitPrice": unit_price,
                "unitMeasure": str(
                    row.get("unitMeasure") or row.get("unit") or ""
                )[:40],
                "packSize": str(row.get("packSize") or "")[:60],
                "stock": row.get("stock"),
                "source": "Yappman Data daily 212-item basket",
            }

        for row in old:
            clean = normalise(row)
            if clean:
                key = (
                    clean["scrapedAt"], clean["retailer"],
                    clean["retailerProductId"]
                )
                records[key] = clean

        imported = 0
        for row in payload:
            clean = normalise(row)
            if not clean:
                continue
            key = (
                clean["scrapedAt"], clean["retailer"],
                clean["retailerProductId"]
            )
            records[key] = clean
            imported += 1

        if not imported:
            raise ValueError("No valid dated product price rows were returned")

        history = sorted(
            records.values(),
            key=lambda item: (
                item["scrapedAt"], item["retailer"],
                item["retailerProductId"]
            )
        )[-40000:]

        latest_date = max(item["date"] for item in history)
        latest_rows = [
            item for item in history
            if item["date"] == latest_date
        ]

        basket["dailyProductPriceHistory"] = history
        basket["dailyProductPriceUpdatedAt"] = timestamp()
        basket["dailyProductPriceLatestDate"] = latest_date
        basket["dailyProductPriceLatestCount"] = len(latest_rows)

        data.setdefault("sources", {})["dailyGroceryBasket"] = {
            "status": "ok",
            "checkedAt": timestamp(),
            "url": "https://dev.to/yappman/comparing-uk-supermarket-prices-programmatically-tesco-sainsburys-asda-and-aldi-in-one-schema-4epi",
            "datasetUrl": url,
            "licence": "CC BY 4.0",
            "latestDate": latest_date,
            "recordsImported": imported,
            "recordsStored": len(history),
            "latestSnapshotRows": len(latest_rows),
            "retailers": ["Tesco", "Sainsbury's", "Asda", "Aldi"],
            "note": (
                "Daily 212-item UK staple basket. Prices are online "
                "shelf snapshots, not live store prices or a complete "
                "household bill. Product names, descriptions, images "
                "and retailer content are not reproduced. Credit "
                "Yappman Data, CC BY 4.0."
            ),
        }

        print(
            "OK DAILY GROCERY BASKET:",
            latest_date,
            "latest rows:", len(latest_rows),
            "stored:", len(history),
        )

    except Exception as error:
        print("FAILED: Daily grocery basket", str(error)[:250])

        data.setdefault("sources", {})["dailyGroceryBasket"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": "https://data.yappman.com/mcp/",
            "error": str(error)[:250],
            "note": "Existing daily product price history was preserved.",
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

    Retailer basket collection is deliberately separate.
    """

    basket = data.setdefault(
        "householdBasket",
        {
            "items": [],
            "history": [],
        },
    )

    basket.setdefault("items", [])
    basket.setdefault("history", [])

    data.setdefault("sources", {}).pop(
        "foodCompass", None
    )

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
    print("BUILD 82 - GROCERY INTELLIGENCE")
    print("================================")

    data = load_data()
    data.setdefault("sources", {})

    # Existing collection systems.
    collect_markets(data)
    collect_stocks(data)
    collect_heating_oil(data)
    collect_fuel(data)
    collect_groceries(data)

    # New retailer price collection.
    collect_retailer_basket(data)
    collect_supermarket_index(data)
    collect_daily_grocery_basket(data)

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
