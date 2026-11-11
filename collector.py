import json
import re
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from pathlib import Path
from html import unescape

ROOT = Path(__file__).resolve().parent
FEEDS_FILE = ROOT / "feeds.json"
DATA_FILE = ROOT / "data" / "intelligence.json"

USER_AGENT = "DoomWatch-OperationContainment/1.0"
TIMEOUT = 20
MAX_ARTICLES = 1000
MAX_FEED_SIZE = 3_000_000


def now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", str(value))
    return unescape(re.sub(r"\s+", " ", value)).strip()


def local_name(tag):
    return tag.split("}")[-1].lower()


def child_text(element, names):
    for child in element.iter():
        if local_name(child.tag) in names:
            if child.text:
                return clean(child.text)
            href = child.attrib.get("href")
            if href:
                return href
    return ""


def repair_xml(xml_data):
    """Attempt to repair common invalid characters in XML feeds."""

    if isinstance(xml_data, bytes):
        xml_text = xml_data.decode("utf-8-sig", errors="replace")
    else:
        xml_text = str(xml_data)

    # Remove characters forbidden by XML 1.0.
    xml_text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]",
        "",
        xml_text
    )

    # Remove any XML declaration after decoding to text.
    xml_text = re.sub(
        r"<\?xml[^?]*\?>",
        "",
        xml_text,
        count=1,
        flags=re.IGNORECASE
    )

    # Repair common HTML entities.
    replacements = {
        "&nbsp;": " ",
        "&mdash;": "—",
        "&ndash;": "–",
        "&rsquo;": "’",
        "&lsquo;": "‘",
        "&rdquo;": "”",
        "&ldquo;": "“"
    }

    for old, new in replacements.items():
        xml_text = xml_text.replace(old, new)

    # Escape ampersands that are not valid XML entities.
    xml_text = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
        "&amp;",
        xml_text
    )

    return xml_text


def parse_feed(xml_data, source):
    # First try the original feed without modification.
    try:
        root = ET.fromstring(xml_data)

    except ET.ParseError as original_error:
        print(
            "XML repair attempted:",
            source.get("name", "Unknown source"),
            "-",
            str(original_error)
        )

        # Retry after repairing common invalid XML characters.
        repaired = repair_xml(xml_data)
        root = ET.fromstring(repaired)

    entries = []

    for element in root.iter():
        tag = local_name(element.tag)

        if tag not in ("item", "entry"):
            continue

        title = child_text(element, {"title"})
        link = ""

        for child in element:
            if local_name(child.tag) == "link":
                link = child.attrib.get("href") or clean(child.text)

                if child.attrib.get("rel") == "alternate":
                    break

        description = child_text(
            element,
            {"description", "summary", "content", "encoded"}
        )

        published = child_text(
            element,
            {"pubdate", "published", "updated", "date"}
        )

        if not title or not link:
            continue

        entries.append({
            "id": source["id"] + ":" + link,
            "sourceId": source["id"],
            "source": source["name"],
            "title": title,
            "url": link,
            "publishedAt": published,
            "collectedAt": iso(),
            "description": description[:1200],
            "domain": source.get("domain"),
            "region": source.get("region", "Unknown"),
            "priority": source.get("priority", "medium"),
            "evidenceStatus": "UNASSESSED",
            "confidence": "UNASSESSED"
        })

    return entries


def fetch_feed(source):
    request = urllib.request.Request(
        source["url"],
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, "
                "application/atom+xml, "
                "application/xml, "
                "text/xml"
            )
        }
    )

    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(MAX_FEED_SIZE)

    if not body:
        raise ValueError("Empty response")

    articles = parse_feed(body, source)

    return articles, content_type


def load_json(path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    if not FEEDS_FILE.exists():
        raise FileNotFoundError("feeds.json is missing")

    if not DATA_FILE.exists():
        raise FileNotFoundError("data/intelligence.json is missing")

    config = load_json(FEEDS_FILE, {})
    intelligence = load_json(DATA_FILE, {})

    feeds = config.get("feeds", [])
    collected = []
    source_status = []

    print("DOOMWATCH COLLECTOR STARTING")
    print("Configured feeds:", len(feeds))
    print("--------------------------------")

    for source in feeds:
        try:
            articles, content_type = fetch_feed(source)
            collected.extend(articles)

            source_status.append({
                "id": source["id"],
                "name": source["name"],
                "status": "OK",
                "checkedAt": iso(),
                "articleCount": len(articles),
                "contentType": content_type
            })

            print(
                "OK:",
                source["name"],
                "-",
                len(articles),
                "articles"
            )

        except Exception as error:
            source_status.append({
                "id": source.get("id", "unknown"),
                "name": source.get("name", "Unknown source"),
                "status": "FAILED",
                "checkedAt": iso(),
                "error": str(error)[:300],
                "articleCount": 0
            })

            print(
                "FAILED:",
                source.get("name"),
                "-",
                str(error)
            )

    existing = intelligence.get("articles", [])
    combined = {}

    for article in existing + collected:
        url = article.get("url")
        if url:
            combined[url] = article

    cutoff = now() - timedelta(days=90)
    retained = []

    for article in combined.values():
        collected_at = article.get("collectedAt", "")

        try:
            article_date = datetime.fromisoformat(
                collected_at.replace("Z", "+00:00")
            )

            if article_date >= cutoff:
                retained.append(article)

        except (ValueError, TypeError):
            retained.append(article)

    retained.sort(
        key=lambda item: item.get("collectedAt", ""),
        reverse=True
    )

    intelligence["articles"] = retained[:MAX_ARTICLES]
    intelligence["sourceStatus"] = source_status

    intelligence["collector"] = {
        "lastRun": iso(),
        "configuredFeeds": len(feeds),
        "successfulFeeds": sum(
            1 for item in source_status
            if item["status"] == "OK"
        ),
        "failedFeeds": sum(
            1 for item in source_status
            if item["status"] == "FAILED"
        ),
        "newArticles": len(collected),
        "retainedArticles": len(intelligence["articles"]),
        "historyDays": 90
    }

    intelligence["collectorLastRun"] = iso()

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            intelligence,
            file,
            indent=2,
            ensure_ascii=False
        )
        file.write("\n")

    print("--------------------------------")
    print("COLLECTOR COMPLETE")
    print(
        "Successful feeds:",
        intelligence["collector"]["successfulFeeds"]
    )
    print(
        "Failed feeds:",
        intelligence["collector"]["failedFeeds"]
    )
    print("Articles collected:", len(collected))
    print("Articles retained:", len(intelligence["articles"]))
    print("--------------------------------")


if __name__ == "__main__":
    main()
