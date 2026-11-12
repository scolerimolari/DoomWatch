#!/usr/bin/env python3
"""
DOOMWATCH - MARKETS COLLECTOR
Independent of collector.py.
Writes historical market data to data/markets.json.
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

DEFRA_FOOD_URL = (
    "https://www.gov.uk/government/statistics/"
    "food-statistics-pocketbook/food-statistics-in-your-pocket"
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

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if DATA_FILE.exists():

        try:

            data = json.loads(
                DATA_FILE.read_text(encoding="utf-8")
            )

            if isinstance(data, dict):
                return data

        except Exception as error:

            print(
                "Existing markets file unreadable:",
                error
            )

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
# HTML TEXT AND LINK EXTRACTION
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
            self.links.append(
                html.unescape(href)
            )


def find_fuel_csv(page):

    parser = LinkExtractor()

    parser.feed(
        page.decode("utf-8", errors="replace")
    )

    candidates = []

    for link in parser.links:

        lower = link.lower()

        if ".csv" not in lower:
            continue

        if (
            "2018" in lower
            or "weekly" in lower
            or "csv" in lower
        ):

            absolute = urllib.parse.urljoin(
                FUEL_URL,
                link
            )

            candidates.append(absolute)

    if candidates:

        for candidate in candidates:

            if "2018" in candidate or "2018_-" in candidate:
                return candidate

        return candidates[0]

    text = page.decode(
        "utf-8",
        errors="replace"
    )

    match = re.search(
        r"""href=["']([^"']+\.csv[^"']*)["']""",
        text,
        re.IGNORECASE
    )

    if match:

        return urllib.parse.urljoin(
            FUEL_URL,
            html.unescape(match.group(1))
        )

    raise ValueError(
        "Could not locate the official road fuel CSV link"
    )


# --------------------------------------------------
# MONEY AND DATE PARSING
# --------------------------------------------------

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
                value,
                pattern
            ).date().isoformat()

        except ValueError:
            pass

    return None


# --------------------------------------------------
# FINANCIAL MARKET DATA
# --------------------------------------------------

def get_yahoo_data(symbol):

    url = YAHOO_URL.format(
        urllib.parse.quote(
            symbol,
            safe="=^.-"
        )
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
            (
                float(price) / float(previous) - 1
            ) * 100,
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
            + urllib.parse.quote(
                symbol,
                safe="=^.-"
            )
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
                    name,
                    {}
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

            if any(
                value is None for value in prices
            ):
                continue

            observations.append({
                "date": day,
                "prices": prices,
            })

        except ValueError:
            continue

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
        "pricePerLitre": round(
            price / litres,
            4
        ),
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

    print(
        "HEATING OIL: collecting Consumer Council data"
    )

    try:

        daily_raw = fetch(
            HEATING_OIL_DAILY_URL,
            "text/html"
        )

        daily_text = html_to_text(daily_raw)

        archive = parse_daily_oil_archive(
            daily_text
        )

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

        for index, litres in enumerate(volumes):

            item_id = f"ni-{litres}l"
            old = existing.get(item_id, {})

            historical_points = [
                {
                    "date": observation["date"],
                    "price": observation["prices"][index],
                    "source": (
                        "Consumer Council NI daily archive"
                    ),
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

        regional_raw = fetch(
            HEATING_OIL_URL,
            "text/html"
        )

        regional_text = html_to_text(
            regional_raw
        )

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

            for item_id, old in existing.items():

                if item_id.startswith("ballyclare-"):

                    if item_id not in {
                        item.get("id")
                        for item in items
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
# PETROL AND DIESEL - OFFICIAL DESNZ HISTORY
# --------------------------------------------------

def parse_fuel_csv(raw):

    text = raw.decode(
        "utf-8-sig",
        errors="replace"
    )

    reader = csv.DictReader(
        io.StringIO(text)
    )

    if not reader.fieldnames:

        raise ValueError(
            "Fuel CSV has no column headings"
        )

    fields = {
        str(name).strip().lower(): name
        for name in reader.fieldnames
        if name
    }

    date_column = next(
        (
            original
            for lower, original in fields.items()
            if lower == "date"
        ),
        None
    )

    petrol_column = next(
        (
            original
            for lower, original in fields.items()
            if "ulsp" in lower and "pump price" in lower
        ),
        None
    )

    diesel_column = next(
        (
            original
            for lower, original in fields.items()
            if "ulsd" in lower and "pump price" in lower
        ),
        None
    )

    if not all([
        date_column,
        petrol_column,
        diesel_column
    ]):

        raise ValueError(
            "Could not identify date, petrol and diesel columns "
            + str(reader.fieldnames)
        )

    observations = []

    for row in reader:

        day = parse_fuel_date(
            row.get(date_column, "")
        )

        petrol = parse_money(
            row.get(petrol_column, "")
        )

        diesel = parse_money(
            row.get(diesel_column, "")
        )

        if (
            not day
            or petrol is None
            or diesel is None
        ):
            continue

        observations.append({
            "date": day,
            "petrol": petrol,
            "diesel": diesel,
        })

    unique = {}

    for observation in observations:
        unique[observation["date"]] = observation

    result = [
        unique[day]
        for day in sorted(unique)
    ]

    if not result:

        raise ValueError(
            "No valid dated petrol and diesel prices in CSV"
        )

    return result


def collect_fuel(data):

    print(
        "ROAD FUEL: collecting official DESNZ CSV"
    )

    try:

        page = fetch(
            FUEL_URL,
            "text/html"
        )

        csv_url = find_fuel_csv(page)

        print("FUEL CSV:", csv_url)

        raw_csv = fetch(
            csv_url,
            "text/csv, application/octet-stream, */*"
        )

        observations = parse_fuel_csv(
            raw_csv
        )

        latest = observations[-1]
        latest_day = latest["date"]

        old_items = (
            data.get("fuel", {})
            .get("items", [])
        )

        existing = {
            item.get("id"): item
            for item in old_items
            if isinstance(item, dict) and item.get("id")
        }

        items = []

        definitions = [
            (
                "petrol",
                "Unleaded petrol",
                "petrol",
                "ULSP"
            ),
            (
                "diesel",
                "Diesel",
                "diesel",
                "ULSD"
            ),
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
                history
            )

            price = latest[key]

            previous_price = None

            if len(observations) > 1:
                previous_price = observations[-2][key]

            change = None

            if previous_price:

                change = round(
                    price - previous_price,
                    2
                )

            item = {
                "id": item_id,
                "name": name,
                "symbol": code,
                "price": price,
                "unit": "p/litre",
                "currency": "GBP",
                "change": change,
                "changePct": (
                    round(
                        (
                            price / previous_price - 1
                        ) * 100,
                        2
                    )
                    if previous_price else None
                ),
                "observedAt": latest_day,
                "date": latest_day,
                "history": history,
                "source": (
                    "DESNZ weekly road fuel prices"
                ),
                "sourceType": "Official UK average",
                "url": FUEL_URL,
            }

            items.append(item)

            print(
                "OK FUEL:",
                name,
                price,
                "p/litre",
                "history:",
                len(history)
            )

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
                "Not Northern Ireland-only or local forecourt prices. "
                "Prices are in pence per litre."
            ),
        }

        print(
            "ROAD FUEL COMPLETE:",
            len(observations),
            "weekly observations"
        )

    except Exception as error:

        print(
            "FAILED: Road fuel",
            str(error)[:250]
        )

        data["sources"]["roadFuel"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": FUEL_URL,
            "error": str(error)[:250],
        }


# --------------------------------------------------
# OFFICIAL FOOD PRICE INDEX
# --------------------------------------------------

def find_food_index_csv(page):

    parser = LinkExtractor()

    parser.feed(
        page.decode("utf-8", errors="replace")
    )

    candidates = []

    for link in parser.links:

        lower = link.lower()

        if (
            ".csv" in lower
            and "cpih" in lower
            and "inflation" in lower
        ):

            absolute = urllib.parse.urljoin(
                DEFRA_FOOD_URL,
                link
            )

            candidates.append(absolute)

    if not candidates:

        raise ValueError(
            "Could not find the official Defra CPIH food CSV"
        )

    # Prefer the link specifically for the food-price chart.
    for candidate in candidates:

        if "cpih-inflation" in candidate.lower():
            return candidate

    return candidates[0]


def parse_food_month(value):

    value = str(value).strip()

    if not value:
        return None

    patterns = [
        "%Y-%m",
        "%Y/%m",
        "%Y %b",
        "%Y %B",
        "%b %Y",
        "%B %Y",
        "%b-%y",
        "%B-%y",
        "%Y-%b",
        "%Y-%B",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]

    for pattern in patterns:

        try:

            parsed = datetime.strptime(
                value,
                pattern
            )

            return (
                f"{parsed.year:04d}-"
                f"{parsed.month:02d}-01"
            )

        except ValueError:
            pass

    # Handle month names and year embedded in other text.
    month_names = {
        name.lower(): number
        for number, name in enumerate(
            [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ],
            1
        )
    }

    match = re.search(
        r"\b([A-Za-z]+)\s+(20\d{2})\b",
        value
    )

    if match:

        month = month_names.get(
            match.group(1).lower()
        )

        if month:

            return (
                f"{match.group(2)}-"
                f"{month:02d}-01"
            )

    match = re.search(
        r"\b(20\d{2})\s+([A-Za-z]+)\b",
        value
    )

    if match:

        month = month_names.get(
            match.group(2).lower()
        )

        if month:

            return (
                f"{match.group(1)}-"
                f"{month:02d}-01"
            )

    return None


def parse_food_index_csv(raw):

    text = raw.decode(
        "utf-8-sig",
        errors="replace"
    )

    reader = csv.reader(
        io.StringIO(text)
    )

    observations = []

    for row in reader:

        if not row:
            continue

        date_index = None
        day = None

        for index, cell in enumerate(row):

            parsed_day = parse_food_month(cell)

            if parsed_day:

                day = parsed_day
                date_index = index
                break

        if not day:
            continue

        # Find the first valid numeric value after the date.
        value = None

        for cell in row[date_index + 1:]:

            candidate = (
                str(cell)
                .strip()
                .replace(",", "")
                .replace("%", "")
            )

            try:

                number = float(candidate)

                if 0 < number < 1000:

                    value = number
                    break

            except ValueError:
                continue

        if value is None:
            continue

        observations.append({
            "date": day,
            "value": round(value, 3),
        })

    unique = {}

    for observation in observations:
        unique[observation["date"]] = observation

    result = [
        unique[day]
        for day in sorted(unique)
    ]

    if not result:

        raise ValueError(
            "No valid monthly food-price observations found "
            "in the Defra CSV"
        )

    return result


def build_food_inflation_history(index_history):

    by_date = {
        point["date"][:7]: point["value"]
        for point in index_history
    }

    output = []

    for point in index_history:

        year, month = map(
            int,
            point["date"][:7].split("-")
        )

        previous_year = (
            f"{year - 1:04d}-{month:02d}"
        )

        previous = by_date.get(previous_year)

        if previous is None or previous == 0:
            continue

        rate = (
            point["value"] / previous - 1
        ) * 100

        output.append({
            "date": point["date"],
            "value": round(rate, 2),
        })

    return output


# --------------------------------------------------
# GROCERY PRICE COLLECTION
# --------------------------------------------------

def collect_groceries(data):

    basket = data.setdefault(
        "householdBasket",
        {
            "items": [],
            "history": [],
        }
    )

    basket.setdefault("items", [])
    basket.setdefault("history", [])

    # ----------------------------------------------
    # OFFICIAL DEFRA FOOD PRICE INDEX
    # ----------------------------------------------

    try:

        print(
            "GROCERIES: collecting official food price index"
        )

        page = fetch(
            DEFRA_FOOD_URL,
            "text/html"
        )

        csv_url = find_food_index_csv(page)

        print(
            "FOOD INDEX CSV:",
            csv_url
        )

        raw = fetch(
            csv_url,
            "text/csv, application/octet-stream, */*"
        )

        observations = parse_food_index_csv(raw)

        old_index = basket.get(
            "priceIndexHistory",
            []
        )

        index_history = merge_history(
            old_index,
            observations
        )

        inflation_history = (
            build_food_inflation_history(
                index_history
            )
        )

        latest = index_history[-1]

        basket["priceIndexHistory"] = index_history

        basket["inflationHistory"] = (
            inflation_history
        )

        basket["foodPriceIndex"] = {
            "name": (
                "UK food and non-alcoholic "
                "beverage price index"
            ),
            "value": latest["value"],
            "date": latest["date"],
            "baseYear": 2015,
            "unit": "Index, 2015=100",
            "source": "ONS / Defra CPIH",
            "url": DEFRA_FOOD_URL,
        }

        basket["foodInflation"] = (
            inflation_history[-1]
            if inflation_history else None
        )

        basket["updatedAt"] = timestamp()

        data["sources"]["foodInflation"] = {
            "status": "ok",
            "checkedAt": timestamp(),
            "url": DEFRA_FOOD_URL,
            "csvUrl": csv_url,
            "observationsImported": len(index_history),
            "latestObservation": latest["date"],
            "note": (
                "Official UK-wide food and non-alcoholic "
                "beverage CPIH index. Annual inflation "
                "is calculated from the index. "
                "This is not a local supermarket basket."
            ),
        }

        print(
            "OK FOOD INDEX:",
            latest["date"],
            latest["value"],
            "annual inflation:",
            (
                inflation_history[-1]["value"]
                if inflation_history
                else "not available"
            )
        )

    except Exception as error:

        print(
            "FAILED: Official food index",
            str(error)[:250]
        )

        data["sources"]["foodInflation"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": DEFRA_FOOD_URL,
            "error": str(error)[:250],
        }

    # ----------------------------------------------
    # NI FOOD COMPASS SOURCE CHECK
    # ----------------------------------------------

    try:

        fetch(
            FOOD_URL,
            "text/html"
        )

        data["sources"]["foodCompass"] = {
            "status": "source_checked",
            "checkedAt": timestamp(),
            "url": FOOD_URL,
            "note": (
                "NI product comparison source checked. "
                "Product prices are not treated as live "
                "or current without their capture dates."
            ),
        }

        print(
            "OK: NI Food Compass source checked"
        )

    except Exception as error:

        print(
            "FAILED: NI Food Compass",
            str(error)[:200]
        )

        data["sources"]["foodCompass"] = {
            "status": "failed",
            "checkedAt": timestamp(),
            "url": FOOD_URL,
            "error": str(error)[:200],
        }


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

            # RSS
            for item in root.findall(".//item"):

                title = (
                    item.findtext("title")
                    or "Untitled"
                )

                link = (
                    item.findtext("link")
                    or ""
                )

                pub = (
                    item.findtext("pubDate")
                    or ""
                )

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

            # ATOM
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

            print(
                "OK NEWS:",
                source
            )

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

    data.setdefault(
        "sources",
        {}
    )

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
    print(
        "Output:",
        DATA_FILE
    )


if __name__ == "__main__":
    main()
