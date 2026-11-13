#!/usr/bin/env python3
"""Validate DoomWatch market data before it is committed or published.

The supermarket dataset is intentionally aggregate-only. This check rejects
individual product records or product-level price fields.
"""

import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path("data/markets.json")
ALLOWED_BASKET_FIELDS = {
    "foodInflationHistory",
    "overallInflationHistory",
    "foodInflation",
    "overallInflation",
    "supermarketIndexHistory",
    "supermarketIndexUpdatedAt",
    "supermarketIndex",
}
ALLOWED_INDEX_RECORD_TYPES = {
    "headline",
    "subtotal",
    "class",
    "retailer_subtotal",
    "retailer",
    "retailer_class",
}
FORBIDDEN_PRODUCT_FIELDS = {
    "sku", "gtin", "ean", "barcode", "productid", "product_id",
    "productname", "product_name", "producttitle", "product_title",
    "unitprice", "unit_price", "producturl", "product_url",
}


def fail(message):
    raise ValueError(message)


def parse_time(value, label):
    if not isinstance(value, str) or not value:
        fail(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"{label} is not a valid ISO timestamp")
    if parsed.tzinfo is None:
        fail(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def inspect_for_product_fields(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            normalised = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalised in FORBIDDEN_PRODUCT_FIELDS:
                fail(f"Product-level field found at {path}.{key}")
            inspect_for_product_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            inspect_for_product_fields(child, f"{path}[{index}]")


def main():
    if not DATA_FILE.exists():
        fail("data/markets.json does not exist")

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("Top-level market data must be an object")

    now = datetime.now(timezone.utc)
    updated = parse_time(data.get("updatedAt"), "updatedAt")
    age_hours = (now - updated).total_seconds() / 3600
    if age_hours < -1:
        fail("updatedAt is more than one hour in the future")
    if age_hours > 24:
        fail(f"Market data is stale ({age_hours:.1f} hours old)")

    basket = data.get("householdBasket")
    if not isinstance(basket, dict):
        fail("householdBasket is missing or invalid")

    unexpected = sorted(set(basket) - ALLOWED_BASKET_FIELDS)
    if unexpected:
        fail("Unexpected householdBasket fields: " + ", ".join(unexpected))

    history = basket.get("supermarketIndexHistory")
    if not isinstance(history, list) or not history:
        fail("Aggregate supermarket index history is missing")

    seen_headlines = set()
    for index, record in enumerate(history):
        if not isinstance(record, dict):
            fail(f"Supermarket record {index} is not an object")
        record_type = record.get("recordType")
        if record_type not in ALLOWED_INDEX_RECORD_TYPES:
            fail(f"Unsupported supermarket recordType at row {index}: {record_type!r}")
        vintage = record.get("vintage")
        if not isinstance(vintage, str) or not re.fullmatch(r"20\d{2}-W\d{2}", vintage):
            fail(f"Invalid supermarket vintage at row {index}")
        level = record.get("level")
        if isinstance(level, bool) or not isinstance(level, (int, float)) or not math.isfinite(level):
            fail(f"Invalid aggregate index level at row {index}")
        if record_type == "headline":
            if vintage in seen_headlines:
                fail(f"Duplicate headline record for {vintage}")
            seen_headlines.add(vintage)

    latest = basket.get("supermarketIndex")
    if not isinstance(latest, dict) or latest.get("recordType") != "headline":
        fail("Latest supermarket index must be an aggregate headline record")
    if latest.get("vintage") not in seen_headlines:
        fail("Latest headline vintage is not present in history")

    source = (data.get("sources") or {}).get("supermarketPriceIndex") or {}
    if source.get("status") != "ok":
        fail("Supermarket index source status is not ok")
    if source.get("latestVintage") != latest.get("vintage"):
        fail("Supermarket source vintage does not match latest headline")
    if source.get("recordsImported") != len(history):
        fail("Supermarket source record count does not match history")
    checked = parse_time(source.get("checkedAt"), "supermarketPriceIndex.checkedAt")
    if (now - checked).total_seconds() > 24 * 3600:
        fail("Supermarket index source check is more than 24 hours old")

    # Block identifiable product rows and product-level prices anywhere in
    # the grocery/index payload, while allowing aggregate counts and indices.
    inspect_for_product_fields(basket, "$.householdBasket")
    inspect_for_product_fields(history, "$.householdBasket.supermarketIndexHistory")

    print(
        "PASS: market JSON valid; data fresh; "
        f"{len(history)} aggregate supermarket records across "
        f"{len(seen_headlines)} headline vintages; no product-level fields."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
