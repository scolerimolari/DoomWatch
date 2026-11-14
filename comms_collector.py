#!/usr/bin/env python3
"""DoomWatch communications watch.
Five-minute best-effort collection of public provider status and independent outage signals.
"""
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "communications.json"
USER_AGENT = "DoomWatch-CommsWatch/1.1 (+https://github.com/scolerimolari/DoomWatch)"
TIMEOUT = 18
MAX_BYTES = 4_000_000
STALE_AFTER_MINUTES = 120

SOURCES = [
    {
        "id": "statuspages-mobile",
        "name": "StatusPages UK mobile networks data",
        "url": "https://status-pages.com/mobile/data.json",
        "displayUrl": "https://status-pages.com/mobile",
        "kind": "provider_status_and_community_reports",
        "scope": "UK mobile networks",
        "format": "json",
    },
    {
        "id": "statuspages-broadband",
        "name": "StatusPages UK broadband data",
        "url": "https://status-pages.com/broadband/data.json",
        "displayUrl": "https://status-pages.com/broadband",
        "kind": "provider_status_and_community_reports",
        "scope": "UK fixed broadband providers",
        "format": "json",
    },
    {
        "id": "updownsignal-mobile",
        "name": "UpDownSignal UK mobile carriers",
        "url": "https://updownsignal.com/en-gb/industries/mobile-carriers/",
        "displayUrl": "https://updownsignal.com/en-gb/industries/mobile-carriers/",
        "kind": "independent_traffic_and_reports",
        "scope": "UK-wide carrier indicators",
        "format": "html",
    },
    {
        "id": "updownsignal-openreach",
        "name": "UpDownSignal Openreach",
        "url": "https://updownsignal.com/en-gb/industries/internet-providers/openreach/",
        "displayUrl": "https://updownsignal.com/en-gb/industries/internet-providers/openreach/",
        "kind": "community_reports",
        "scope": "UK-wide fixed broadband infrastructure reports",
        "format": "html",
    },
]

PROVIDERS = {
    "EE": ["ee", "bt mobile", "plusnet mobile", "1pmobile"],
    "O2": ["o2", "giffgaff", "tesco mobile", "sky mobile", "lyca mobile"],
    "Vodafone": ["vodafone", "voxi", "lebara", "talkmobile"],
    "Three": ["three", "smarty", "id mobile"],
    "Openreach": ["openreach"],
    "BT Broadband": ["bt broadband", "bt"],
    "Virgin Media": ["virgin media"],
    "Sky Broadband": ["sky broadband", "sky"],
    "TalkTalk": ["talktalk"],
    "Plusnet": ["plusnet"],
    "Zen Internet": ["zen internet"],
}

ISSUE_WORDS = ("outage", "disruption", "disrupted", "minor issues", "major issues",
               "partial outage", "service issue", "degraded", "offline", "down",
               "service degradation", "service disruption")
CLEAR_WORDS = ("operational", "no issues detected", "no reported issues",
               "no problems detected", "working normally", "all systems operational")
MAINTENANCE_WORDS = ("maintenance", "scheduled work", "planned work")


class TextAndTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.text_parts = []
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
        cleaned = re.sub(r"\s+", " ", data).strip()
        if cleaned:
            self.text_parts.append(cleaned)
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


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d %b %Y, %H:%M UTC",
                "%d %B %Y, %H:%M UTC"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def fetch(source):
    req = Request(source["url"], headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    })
    with urlopen(req, timeout=TIMEOUT) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Response exceeded size limit")
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def canonical_provider(name):
    lower = str(name or "").lower().strip()
    if not lower:
        return None
    for canonical, aliases in PROVIDERS.items():
        for alias in aliases:
            if alias == "ee":
                if re.search(r"(?<![a-z0-9])ee(?![a-z0-9])", lower):
                    return canonical
            elif alias == "o2":
                if re.search(r"(?<![a-z0-9])o2(?![a-z0-9])", lower):
                    return canonical
            elif alias == "bt":
                if "bt" in lower:
                    return canonical
            elif alias == "sky":
                if "sky" in lower:
                    return canonical
            elif alias in lower:
                return canonical
    return str(name).strip()[:80]


def classify_indicator(value):
    text = str(value or "").lower().replace("_", " ").replace("-", " ")
    if any(word in text for word in MAINTENANCE_WORDS):
        return "MAINTENANCE_SIGNAL"
    if any(word in text for word in CLEAR_WORDS):
        return "NO_ISSUE_SIGNAL"
    if any(word in text for word in ISSUE_WORDS):
        return "ISSUE_SIGNAL"
    if text in ("degraded", "major outage", "partial outage", "minor issues"):
        return "ISSUE_SIGNAL"
    return "STATUS_UNCLEAR"


def walk_provider_objects(value):
    if isinstance(value, dict):
        keys = {str(k).lower() for k in value}
        if keys.intersection({"name", "provider", "title", "displayname"}) and keys.intersection(
            {"indicator", "status", "summary", "overallstatus"}
        ):
            yield value
        for child in value.values():
            yield from walk_provider_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_provider_objects(child)


def extract_json_signals(source, payload):
    observations = []
    checked_at = payload.get("checkedAt") or payload.get("lastChecked") or payload.get("updatedAt") or payload.get("generatedAt")
    category_name = payload.get("name") or payload.get("category") or source["scope"]
    seen = set()
    for item in walk_provider_objects(payload):
        name = item.get("name") or item.get("provider") or item.get("title") or item.get("displayName")
        provider = canonical_provider(name)
        if not provider or provider in seen:
            continue
        seen.add(provider)
        indicator = item.get("indicator") or item.get("status") or item.get("overallStatus") or item.get("summary")
        status = classify_indicator(indicator)
        via = str(item.get("via") or "").lower()
        user_reports = item.get("userReports") or {}
        report_level = str((user_reports.get("level") if isinstance(user_reports, dict) else user_reports) or "").lower()
        if via == "crowd" or report_level in ("elevated", "spike"):
            if status == "NO_ISSUE_SIGNAL":
                status = "UNCONFIRMED_REPORT_SIGNAL"
        incidents = item.get("activeIncidents") or []
        incident_titles = []
        for incident in incidents[:5] if isinstance(incidents, list) else []:
            if isinstance(incident, dict):
                incident_titles.append(str(incident.get("name") or incident.get("title") or incident.get("summary") or "Active incident")[:180])
            else:
                incident_titles.append(str(incident)[:180])
        areas = user_reports.get("areas", []) if isinstance(user_reports, dict) else []
        area_names = []
        if isinstance(areas, list):
            for area in areas[:8]:
                if isinstance(area, dict):
                    area_names.append(str(area.get("name") or area.get("area") or area.get("postcode") or "")[:40])
                else:
                    area_names.append(str(area)[:40])
        observations.append({
            "provider": provider,
            "reportedStatus": status,
            "rawIndicator": str(indicator or "not supplied")[:160],
            "summary": str(item.get("summary") or "")[:240],
            "activeIncidents": incident_titles,
            "reportedAreas": area_names,
            "via": via or "provider_status",
            "sourceUpdatedAt": item.get("checkedAt") or checked_at,
            "evidenceClass": source["kind"],
        })
    return observations, checked_at, str(category_name)


def extract_html_signals(source, html):
    parser = TextAndTableParser()
    parser.feed(html)
    text = " ".join(parser.text_parts)
    source_updated = None
    match = re.search(r"Last updated:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", text, re.I)
    if match:
        source_updated = match.group(1)
    observations = []
    # Read the current provider status strip only. Do not mistake the historical
    # incident table further down the page for a currently active outage.
    current_text = re.split(r"Recent UK Network Outages|Recent Outages|Recent Incidents", text, maxsplit=1, flags=re.I)[0]
    for canonical, aliases in PROVIDERS.items():
        for alias in aliases:
            if alias in ("ee", "o2"):
                pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])\s+(Operational|Minor Issues|Major Issues|Service Disruption|Partial Outage|Degraded|Outage)"
            else:
                pattern = re.escape(alias) + r"\s+(Operational|Minor Issues|Major Issues|Service Disruption|Partial Outage|Degraded|Outage)"
            found = re.search(pattern, current_text, re.I)
            if found:
                observations.append({
                    "provider": canonical,
                    "reportedStatus": classify_indicator(found.group(1)),
                    "rawIndicator": found.group(1),
                    "summary": "",
                    "activeIncidents": [],
                    "reportedAreas": [],
                    "via": "independent_status_indicator",
                    "sourceUpdatedAt": source_updated,
                    "evidenceClass": source["kind"],
                })
                break
    return observations, source_updated, source["scope"]


def is_stale(timestamp, now):
    parsed = parse_date(timestamp)
    return parsed is None or (now - parsed).total_seconds() > STALE_AFTER_MINUTES * 60


def collect_one(source):
    checked = utc_now()
    try:
        raw = fetch(source)
        if source["format"] == "json":
            payload = json.loads(raw)
            observations, updated, title = extract_json_signals(source, payload)
        else:
            observations, updated, title = extract_html_signals(source, raw)
        return {
            **source,
            "status": "OK" if observations else "NO_STRUCTURED_STATUS",
            "checkedAt": checked,
            "sourceUpdatedAt": updated,
            "providerSignals": observations,
            "note": ("Source data is independent/provider-status aggregation; read evidence class and source timestamp."
                     if observations else
                     "Page was reachable, but no recognised current provider-status rows were extracted."),
        }
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as exc:
        return {
            **source,
            "status": "SOURCE_UNAVAILABLE",
            "checkedAt": checked,
            "sourceUpdatedAt": None,
            "providerSignals": [],
            "note": (type(exc).__name__ + ": " + str(exc))[:240],
        }


def main():
    results = [collect_one(source) for source in SOURCES]
    now = datetime.now(timezone.utc)
    grouped = {}
    for result in results:
        for signal in result["providerSignals"]:
            item = {
                "sourceId": result["id"],
                "source": result["name"],
                "url": result.get("displayUrl", result["url"]),
                "status": signal["reportedStatus"],
                "rawIndicator": signal.get("rawIndicator", ""),
                "summary": signal.get("summary", ""),
                "activeIncidents": signal.get("activeIncidents", []),
                "reportedAreas": signal.get("reportedAreas", []),
                "sourceUpdatedAt": signal.get("sourceUpdatedAt") or result.get("sourceUpdatedAt"),
                "checkedAt": result["checkedAt"],
                "evidenceClass": signal.get("evidenceClass", result["kind"]),
                "via": signal.get("via", ""),
            }
            item["stale"] = is_stale(item["sourceUpdatedAt"], now)
            grouped.setdefault(signal["provider"], []).append(item)

    providers = []
    for provider, observations in sorted(grouped.items()):
        current_issues = [x for x in observations if x["status"] == "ISSUE_SIGNAL" and not x["stale"]]
        stale_issues = [x for x in observations if x["status"] == "ISSUE_SIGNAL" and x["stale"]]
        current_clear = [x for x in observations if x["status"] == "NO_ISSUE_SIGNAL" and not x["stale"]]
        unconfirmed = [x for x in observations if x["status"] == "UNCONFIRMED_REPORT_SIGNAL" and not x["stale"]]
        maintenance = [x for x in observations if x["status"] == "MAINTENANCE_SIGNAL" and not x["stale"]]
        if current_issues:
            status = "ISSUE_SIGNAL"
        elif unconfirmed:
            status = "UNCONFIRMED_REPORT_SIGNAL"
        elif maintenance:
            status = "MAINTENANCE_SIGNAL"
        elif current_clear:
            status = "NO_ISSUE_SIGNAL"
        elif stale_issues:
            status = "STALE_ISSUE_SIGNAL"
        else:
            status = "STALE_OR_UNKNOWN"
        providers.append({
            "provider": provider,
            "status": status,
            "issueSignals": len(current_issues),
            "staleIssueSignals": len(stale_issues),
            "noIssueSignals": len(current_clear),
            "unconfirmedSignals": len(unconfirmed),
            "observations": observations,
        })

    issue_count = sum(1 for p in providers if p["status"] == "ISSUE_SIGNAL")
    unconfirmed_count = sum(1 for p in providers if p["status"] == "UNCONFIRMED_REPORT_SIGNAL")
    stale_count = sum(1 for p in providers if p["status"] == "STALE_ISSUE_SIGNAL")
    payload = {
        "schemaVersion": 2,
        "generatedAt": utc_now(),
        "collectionIntervalMinutes": 5,
        "displayRefreshSeconds": 60,
        "staleAfterMinutes": STALE_AFTER_MINUTES,
        "overallStatus": "CURRENT_ISSUE_SIGNALS" if issue_count else
                         "UNCONFIRMED_REPORTS" if unconfirmed_count else
                         "STALE_REPORTS_ONLY" if stale_count else "NO_CURRENT_ISSUE_SIGNAL_DETECTED",
        "summary": {
            "currentIssueProviders": issue_count,
            "unconfirmedReportProviders": unconfirmed_count,
            "staleIssueProviders": stale_count,
        },
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
            "StatusPages aggregates provider status pages and user reports; user reports are unverified.",
            "Independent traffic and community reports can indicate an emerging problem but do not prove an outage.",
            "Old source data is labelled stale and is not presented as a current fault.",
            "No recognised signal does not prove that a network is working.",
            "The monitored public sources do not guarantee postcode-level confirmation for Ballyclare.",
            "Operator account and postcode checkers remain the authoritative route for an individual line or mobile connection.",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("DOOMWATCH COMMUNICATIONS WATCH")
    print("Sources:", len(results), "with structured observations:", sum(1 for x in results if x["status"] == "OK"))
    print("Providers:", len(providers), "current issue signals:", issue_count,
          "unconfirmed reports:", unconfirmed_count, "stale issue signals:", stale_count)
    print("Written:", OUT)


if __name__ == "__main__":
    main()
