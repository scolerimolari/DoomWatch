#!/usr/bin/env python3
"""Collect public RSS/Atom sources for DoomWatch's Fringe & Unexplained desk.
Uses only the Python standard library; no accounts, social APIs or paid services.
"""
from __future__ import annotations
import json, re, time, hashlib
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE_FILE = ROOT / "fringe_sources.json"
DATA_FILE = ROOT / "data" / "fringe.json"
USER_AGENT = "DoomWatch-FringeCollector/1.0 (+https://github.com/scolerimolari/DoomWatch)"
TIMEOUT = 18
MAX_BYTES = 2_000_000
RETENTION_DAYS = 120

def now():
    return datetime.now(timezone.utc)

def iso(value=None):
    return (value or now()).isoformat(timespec="seconds").replace("+00:00", "Z")

def local(tag):
    return tag.split("}")[-1].lower()

def clean(value):
    value = unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\\s+", " ", value).strip()

def child_value(element, names):
    for child in element.iter():
        if local(child.tag) in names:
            if child.text:
                return clean(child.text)
            href = child.attrib.get("href")
            if href:
                return href
    return ""

def parse_feed(payload, source):
    root = ET.fromstring(payload)
    records = []
    for item in root.iter():
        if local(item.tag) not in ("item", "entry"):
            continue
        title = child_value(item, {"title"})
        link = ""
        publisher = ""
        for child in item:
            tag = local(child.tag)
            if tag == "link":
                link = child.attrib.get("href") or clean(child.text)
            elif tag == "source" and child.text:
                publisher = clean(child.text)
        if not link:
            link = child_value(item, {"guid", "id"})
        summary = child_value(item, {"description", "summary", "content", "encoded"})
        published = child_value(item, {"pubdate", "published", "updated", "date"})
        if not title or not link or not link.startswith(("http://", "https://")):
            continue
        identity = source["id"] + "|" + link
        records.append({
            "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
            "sourceId": source["id"], "source": source["name"],
            "publisher": publisher or source["name"], "title": title[:360],
            "url": link, "publishedAt": published[:120], "collectedAt": iso(),
            "description": summary[:1800], "category": source["category"],
            "sourceClass": source["class"], "sourceTrust": source["trust"],
            "feedUrl": source["url"], "evidenceStatus": "UNASSESSED",
            "confidence": "UNASSESSED", "editorialNote": source["description"]
        })
    return records

def main():
    config = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    old = {}
    if DATA_FILE.exists():
        try:
            previous = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            old = {a.get("id"): a for a in previous.get("articles", []) if a.get("id")}
        except Exception:
            old = {}
    statuses, fresh = [], {}
    for source in config.get("sources", []):
        started = time.monotonic()
        try:
            req = Request(source["url"], headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"
            })
            with urlopen(req, timeout=TIMEOUT) as response:
                payload = response.read(MAX_BYTES)
                content_type = response.headers.get("Content-Type", "")
            if not payload:
                raise ValueError("Empty feed response")
            items = parse_feed(payload, source)
            for item in items:
                fresh[item["id"]] = item
            statuses.append({
                "id": source["id"], "name": source["name"],
                "status": "OK" if items else "EMPTY", "checkedAt": iso(),
                "articleCount": len(items), "durationSeconds": round(time.monotonic() - started, 2),
                "contentType": content_type[:120]
            })
            print("FRINGE:", source["name"], len(items))
        except Exception as error:
            statuses.append({
                "id": source["id"], "name": source["name"], "status": "FAILED",
                "checkedAt": iso(), "articleCount": 0, "error": str(error)[:260]
            })
            print("FRINGE FAILED:", source["name"], str(error)[:180])

    combined = dict(old)
    combined.update(fresh)
    cutoff = now() - timedelta(days=RETENTION_DAYS)
    retained = []
    for article in combined.values():
        value = article.get("publishedAt") or article.get("collectedAt")
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = now()
        if dt >= cutoff:
            retained.append(article)
    retained.sort(key=lambda a: str(a.get("publishedAt") or a.get("collectedAt") or ""), reverse=True)
    output = {
        "schemaVersion": 1, "collectorLastRun": iso(), "updatedAt": iso(),
        "configuredFeeds": len(config.get("sources", [])),
        "successfulFeeds": sum(1 for s in statuses if s["status"] == "OK"),
        "emptyFeeds": sum(1 for s in statuses if s["status"] == "EMPTY"),
        "failedFeeds": sum(1 for s in statuses if s["status"] == "FAILED"),
        "newRecords": len(fresh), "recordCount": len(retained),
        "sources": statuses, "articles": retained[:900],
        "editorialPolicy": "Fringe and extraordinary claims are discovery leads. Publisher class is not proof. Each claim remains UNASSESSED until independently examined."
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    print("FRINGE COLLECTION COMPLETE:", len(fresh), "new records;", len(retained), "retained")

if __name__ == "__main__":
    main()
