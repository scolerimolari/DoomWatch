#!/usr/bin/env python3
"""DoomWatch communications watch.
Collects independent public network-status signals. These are indicators, not operator-confirmed faults.
"""
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "communications.json"
USER_AGENT = "DoomWatch-CommsWatch/1.0 (+https://github.com/scolerimolari/DoomWatch)"
TIMEOUT = 18
MAX_BYTES = 4_000_000

SOURCES = [
    {
        "id": "signalchecker-mobile",
        "name": "Signalchecker UK mobile network status",
        "url": "https://www.signalchecker.co.uk/network-status",
        "kind": "independent_traffic_signal",
        "scope": "UK-wide network indicators",
    },
    {
        "id": "status-pages-mobile",
        "name": "StatusPages UK mobile networks",
        "url": "https://status-pages.com/mobile",
        "kind": "community_reports",
        "scope": "UK-wide reports and area groupings",
    },
    {
        "id": "updownsignal-mobile",
        "name": "UpDownSignal UK mobile carriers",
        "url": "https://updownsignal.com/en-gb/industries/mobile-carriers/",
        "kind": "independent_traffic_and_reports",
        "scope": "UK-wide carrier indicators",
    },
    {
        "id": "updownsignal-openreach",
        "name": "UpDownSignal Openreach",
        "url": "https://updownsignal.com/en-gb/industries/internet-providers/openreach/",
        "kind": "community_reports",
        "scope": "UK-wide fixed broadband infrastructure reports",
    },
]

PROVIDERS = {
    "EE": ["EE", "BT Mobile", "Plusnet Mobile", "1pMobile"],
    "O2": ["O2", "giffgaff", "Tesco Mobile", "Sky Mobile", "Lyca Mobile"],
    "Vodafone": ["Vodafone", "VOXI", "Lebara", "Talkmobile"],
    "Three": ["Three", "Smarty", "iD Mobile"],
    "Openreach": ["Openreach"],
    "BT Broadband": ["BT Broadband", "BT"],
    "Virgin Media": ["Virgin Media"],
    "Sky Broadband": ["Sky Broadband"],
    "TalkTalk": ["TalkTalk"],
}

ISSUE_WORDS = ("outage", "disruption", "disrupted", "partial outage", "minor issues",
               "major issues", "service issue", "issues detected", "problems detected",
               "degraded", "offline", "down")
CLEAR_WORDS = ("operational", "no issues detected", "no reported issues",
               "no problems detected", "working normally", "all systems operational")
LOCAL_WORDS = ("ballyclare", "antrim", "ballymena", "carrickfergus", "newtownabbey",
               "county antrim", "northern ireland", "ni ")


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.in_script = False
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "script":
            self.in_script = True
        elif tag == "style":
            self.in_style = True
        elif tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.in_script or self.in_style:
            return
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script":
            self.in_script = False
        elif tag == "style":
            self.in_style = False
        elif tag in ("td", "th") and self.cell is not None:
            value = re.sub(r"\s+", " ", " ".join(self.cell)).strip()
            self.row.append(value)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.table:
                self.tables.append(self.table)
            self.table = None


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch(source):
    req = Request(source["url"], headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    })
    with urlopen(req, timeout=TIMEOUT) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Response exceeded size limit")
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def classify_row(row_text):
    value = row_text.lower()
    if any(word in value for word in CLEAR_WORDS):
        return "NO_ISSUE_SIGNAL"
    if any(word in value for word in ISSUE_WORDS):
        return "ISSUE_SIGNAL"
    return None


def extract_provider_rows(source, html):
    parser = TableParser()
    parser.feed(html)
    found = {}
    # The first tables are current-status tables on the monitored services.
    # Later tables often contain historic incidents, so deliberately ignore them.
    for table_index, table in enumerate(parser.tables[:4]):
        for row in table[:80]:
            joined = " | ".join(cell for cell in row if cell).strip()
            if not joined:
                continue
            status = classify_row(joined)
            if not status:
                continue
            lower = joined.lower()
            for canonical, aliases in PROVIDERS.items():
                if canonical in found:
                    continue
                alias = next((a for a in aliases if re.search(
                    r"(?<![a-z0-9])" + re.escape(a.lower()) + r"(?![a-z0-9])", lower
                )), None)
                if alias:
                    found[canonical] = {
                        "provider": canonical,
                        "reportedStatus": status,
                        "sourceRow": joined[:500],
                        "scope": "UK-wide; not a Ballyclare-specific confirmation",
                        "evidenceClass": source["kind"],
                    }
    return list(found.values())


def collect_one(source):
    checked = utc_now()
    try:
        html = fetch(source)
        providers = extract_provider_rows(source, html)
        return {
            **source,
            "status": "OK" if providers else "NO_STRUCTURED_STATUS",
            "checkedAt": checked,
            "providerSignals": providers,
            "note": ("Rows are third-party status indicators, not operator confirmation."
                     if providers else
                     "Page was reachable, but no recognised current-status rows were extracted."),
        }
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return {
            **source,
            "status": "SOURCE_UNAVAILABLE",
            "checkedAt": checked,
            "providerSignals": [],
            "note": (type(exc).__name__ + ": " + str(exc))[:240],
        }


def main():
    results = [collect_one(source) for source in SOURCES]
    signals = {}
    for result in results:
        for signal in result["providerSignals"]:
            key = signal["provider"]
            signals.setdefault(key, []).append({
                "sourceId": result["id"],
                "source": result["name"],
                "url": result["url"],
                "status": signal["reportedStatus"],
                "sourceRow": signal["sourceRow"],
                "evidenceClass": signal["evidenceClass"],
            })

    providers = []
    for provider, observations in sorted(signals.items()):
        issue_count = sum(1 for item in observations if item["status"] == "ISSUE_SIGNAL")
        clear_count = sum(1 for item in observations if item["status"] == "NO_ISSUE_SIGNAL")
        if issue_count:
            status = "ISSUE_SIGNAL"
        elif clear_count:
            status = "NO_ISSUE_SIGNAL"
        else:
            status = "NO_DATA"
        providers.append({
            "provider": provider,
            "status": status,
            "issueSignals": issue_count,
            "noIssueSignals": clear_count,
            "observations": observations,
        })

    payload = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "collectionIntervalMinutes": 5,
        "displayRefreshSeconds": 60,
        "overallStatus": "SIGNALS_PRESENT" if any(p["status"] == "ISSUE_SIGNAL" for p in providers) else "NO_ISSUE_SIGNAL_DETECTED",
        "sources": results,
        "providers": providers,
        "officialCheckers": [
            {"name": "EE service status", "url": "https://ee.co.uk/help/service-status/broadband/confirm-mobile-number"},
            {"name": "Vodafone network status", "url": "https://www.vodafone.co.uk/network/status-checker"},
            {"name": "Ofcom coverage and broadband information", "url": "https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/"},
            {"name": "Openreach service support", "url": "https://www.openreach.com/help-and-support/service-stopped-working"},
        ],
        "limitations": [
            "This is a five-minute best-effort collector, not a carrier-operated monitoring feed.",
            "Independent traffic and community reports can indicate an emerging problem but do not prove an outage.",
            "No recognised signal does not prove that a network is working.",
            "The monitored public pages do not provide reliable postcode-level confirmation for Ballyclare.",
            "Operator account and postcode checkers remain the authoritative route for an individual line or mobile connection.",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("DOOMWATCH COMMUNICATIONS WATCH")
    print("Sources:", len(results), "reachable:", sum(1 for x in results if x["status"] == "OK"))
    print("Provider rows:", len(providers))
    print("Issue signals:", sum(1 for x in providers if x["status"] == "ISSUE_SIGNAL"))
    print("Written:", OUT)


if __name__ == "__main__":
    main()
