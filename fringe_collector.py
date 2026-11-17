#!/usr/bin/env python3
"""Collect public RSS/Atom feeds for DoomWatch regional and thematic news desk."""
from __future__ import annotations
import json, re, time, hashlib
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE_FILE = ROOT / "fringe_sources.json"
DATA_FILE = ROOT / "data" / "fringe.json"
USER_AGENT = "DoomWatch-NewsCollector/2.0 (+https://github.com/scolerimolari/DoomWatch)"
TIMEOUT = 14
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
    return re.sub(r"\s+", " ", value).strip()

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
        title, link, publisher = child_value(item, {"title"}), "", ""
        for child in item:
            tag = local(child.tag)
            if tag == "link":
                rel = child.attrib.get("rel", "alternate")
                if rel == "alternate" or not link:
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
            "description": summary[:1800], "region": source["region"],
            "category": source["category"], "sourceClass": source["class"],
            "sourceTrust": source["trust"], "feedUrl": source["url"],
            "evidenceStatus": "UNASSESSED", "confidence": "UNASSESSED",
            "editorialNote": source["description"]
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
            pass
    source_map = {s["id"]: s for s in config.get("sources", [])}
    for article in old.values():
        src = source_map.get(article.get("sourceId"), {})
        article.setdefault("region", src.get("region", "GLOBAL"))
        article.setdefault("category", src.get("category", "UNCATEGORISED"))
    statuses, fresh = [], {}
    for source in config.get("sources", []):
        started = time.monotonic()
        if source.get("enabled", True) is False:
            statuses.append({"id": source["id"], "name": source["name"], "region": source["region"], "category": source["category"], "trust": source["trust"], "url": source["url"], "status": "DISABLED", "checkedAt": iso(), "articleCount": 0, "reason": source.get("disabledReason", "Manual review; automated polling is disabled.")})
            print("FEED DISABLED", source["name"], source.get("disabledReason", "Manual review"))
            continue
        try:
            for attempt in range(2):
                try:
                    req = Request(source["url"], headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"})
                    with urlopen(req, timeout=TIMEOUT) as response:
                        payload = response.read(MAX_BYTES)
                        content_type = response.headers.get("Content-Type", "")
                    if not payload:
                        raise ValueError("Empty feed response")
                    items = parse_feed(payload, source)
                    break
                except Exception as error:
                    retryable = getattr(error, "code", None) in (429, 500, 502, 503, 504) or isinstance(error, TimeoutError)
                    if attempt == 0 and retryable:
                        print("FEED RETRY", source["name"], str(error)[:120])
                        time.sleep(2)
                        continue
                    raise
            for item in items:
                fresh[item["id"]] = item
            statuses.append({"id": source["id"], "name": source["name"],
                "region": source["region"], "category": source["category"],
                "trust": source["trust"], "url": source["url"],
                "status": "OK" if items else "EMPTY", "checkedAt": iso(),
                "articleCount": len(items), "durationSeconds": round(time.monotonic()-started,2),
                "contentType": content_type[:120]})
            print("FEED", source["region"], source["name"], len(items))
        except Exception as error:
            statuses.append({"id": source["id"], "name": source["name"],
                "region": source["region"], "category": source["category"],
                "trust": source["trust"], "url": source["url"],
                "status": "FAILED", "checkedAt": iso(), "articleCount": 0,
                "error": str(error)[:260]})
            print("FEED FAILED", source["name"], str(error)[:180])
    combined = dict(old)
    combined.update(fresh)
    cutoff = now() - timedelta(days=RETENTION_DAYS)
    retained = []
    for article in combined.values():
        value = article.get("publishedAt") or article.get("collectedAt")
        try:
            try: dt = datetime.fromisoformat(str(value).replace("Z","+00:00"))
            except ValueError: dt = parsedate_to_datetime(str(value))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        except Exception: dt = now()
        if dt >= cutoff: retained.append(article)
    retained.sort(key=lambda a: str(a.get("publishedAt") or a.get("collectedAt") or ""), reverse=True)
    output = {"schemaVersion":2,"collectorLastRun":iso(),"updatedAt":iso(),
        "configuredFeeds":len(config.get("sources",[])),
        "activeFeeds":sum(s["status"]!="DISABLED" for s in statuses),
        "successfulFeeds":sum(s["status"]=="OK" for s in statuses),
        "emptyFeeds":sum(s["status"]=="EMPTY" for s in statuses),
        "failedFeeds":sum(s["status"]=="FAILED" for s in statuses),
        "disabledFeeds":sum(s["status"]=="DISABLED" for s in statuses),
        "newRecords":len(fresh),"recordCount":len(retained),
        "sectionOrder":config.get("sectionOrder",[]),"sources":statuses,
        "articles":retained[:1400],
        "editorialPolicy":"A news feed is a discovery and reading service, not an endorsement. Source type is context, not a truth score."}
    DATA_FILE.parent.mkdir(parents=True,exist_ok=True)
    DATA_FILE.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("NEWS COLLECTION COMPLETE:",len(fresh),"new;",len(retained),"retained")
if __name__=="__main__": main()
