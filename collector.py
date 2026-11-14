import json
import re
import hashlib
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode, urljoin, urlparse
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
FEEDS_FILE = ROOT / "feeds.json"
DATA_FILE = ROOT / "data" / "intelligence.json"

USER_AGENT = "DoomWatch-OperationContainment/1.0"
TIMEOUT = 20
MAX_ARTICLES = 3000
MAX_FEED_SIZE = 3_000_000

SECTOR_RULES = {
  1: ("National resilience", ("civil contingencies","civil contingency","national resilience","emergency planning","emergency preparedness","continuity planning","business continuity","cabinet office","national risk","resilience forum","emergency response plan","major incident")),
  2: ("Food and agriculture", ("food supply","food shortage","food security","food prices","food imports","food processing","agriculture","farming","farmers","fertiliser","fertilizer","grain","livestock","crop failure","animal disease","avian influenza","poultry","veterinary medicine","agri-food")),
  3: ("Fuel, energy and oil", ("heating oil","home heating oil","kerosene","fuel shortage","fuel supply","fuel prices","petrol","diesel","oil price","natural gas","gas supply","gas storage","refinery","energy security","petrol station","fuel terminal")),
  4: ("Chemicals, medicines and industrial inputs", ("medicine shortage","medicines","medicine recall","drug shortage","pharmaceutical","medical supplies","medical device","personal protective equipment","chemical","chlorine","ammonia","industrial gas","industrial inputs","semiconductor","critical raw material","fertiliser supply")),
  5: ("Electricity, gas and water", ("power outage","electricity outage","blackout","electricity","electricity grid","gas network","gas outage","water supply","water outage","drinking water","boil water","water quality","ni water","wastewater","sewage","substation","electricity network","grid operator")),
  6: ("Transport, ports and logistics", ("trafficwatch","road closure","road disruption","rail disruption","port of belfast","belfast harbour","larne port","port disruption","ports","harbour","harbor","ferry","ferry cancellation","shipping","freight","logistics","airport","freight terminal","border delay","lorry driver")),
  7: ("Healthcare and public health", ("public health","public health agency","pha ni","uk health security agency","ukhsa","nhs","hospital","healthcare","health protection","outbreak","infectious disease","respiratory infection","ambulance","pharmacy","health service disruption","disease surveillance")),
  8: ("Telecommunications, cyber and infrastructure", ("cyber","cyber attack","cyber incident","ransomware","data breach","phishing","telecom","telecommunications","broadband","mobile network","mobile outage","internet outage","data centre","datacenter","undersea cable","subsea cable","critical national infrastructure","digital infrastructure")),
  9: ("Weather, flooding and natural hazards", ("weather warning","met office warning","flood","flood warning","river level","storm","wind warning","snow","ice warning","wildfire","coastal flooding","coastal erosion","drought","heatwave","severe weather")),
  10: ("Civil defence and community preparedness", ("civil defence","community resilience","community emergency plan","emergency shelter","evacuation","evacuation centre","household preparedness","emergency plan","volunteer response","emergency support centre","local resilience forum")),
  11: ("International events with UK/NI impact", ("geopolitical","international conflict","armed conflict","military operation","military escalation","sanctions","blockade","red sea","strait of hormuz","ukraine","russia","iran","israel","gaza","nato","shipping disruption","trade disruption","export controls","energy chokepoint","maritime security"))
}
LOCALITY_POINTS = [
 ("Belfast",54.5973,-5.9301,("belfast","greater belfast")),
 ("Newtownabbey",54.6598,-5.9086,("newtownabbey","glengormley","carnmoney","whiteabbey")),
 ("Ballyclare",54.7515,-6.0014,("ballyclare","doagh","parkgate")),
 ("Antrim",54.7195,-6.2072,("antrim","crumlin")),
 ("Larne",54.8509,-5.8238,("larne","cairncastle")),
 ("Carrickfergus",54.7158,-5.8058,("carrickfergus","greenisland")),
 ("Lisburn",54.5091,-6.0431,("lisburn","hilden","hillsborough")),
 ("Bangor",54.6608,-5.6681,("bangor","donaghadee")),
 ("Newtownards",54.5924,-5.6909,("newtownards","comber")),
 ("Downpatrick",54.3281,-5.7153,("downpatrick","strangford")),
 ("Newry",54.1751,-6.3402,("newry","bessbrook","warrenpoint","crossmaglen")),
 ("Armagh",54.3503,-6.6528,("armagh","markethill","tandragee")),
 ("Portadown",54.4235,-6.4443,("portadown","craigavon","lurgan")),
 ("Dungannon",54.5034,-6.7670,("dungannon","coalisland")),
 ("Cookstown",54.6430,-6.7450,("cookstown","magherafelt")),
 ("Omagh",54.6000,-7.3000,("omagh","strabane")),
 ("Enniskillen",54.3448,-7.6386,("enniskillen","lisnaskea","fermanagh")),
 ("Coleraine",55.1333,-6.6667,("coleraine","portstewart","portrush")),
 ("Ballymena",54.8636,-6.2763,("ballymena","cullybackey","broughshane")),
 ("Limavady",55.0515,-6.9500,("limavady","dungiven")),
 ("Derry/Londonderry",54.9970,-7.3090,("derry","londonderry","waterside")),
 ("Ballycastle",55.2044,-6.2540,("ballycastle","bushmills","cushendall"))
]
def enrich_article(article):
    text = " " + " ".join(str(article.get(field,"") or "") for field in ("title", "description", "summary")).lower() + " "
    keyword_ids = set()
    for sector_id, (_, terms) in SECTOR_RULES.items():
        if any(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) for term in terms):
            keyword_ids.add(sector_id)
    source_ids = set()
    domain = article.get("domain")
    source_type = str(article.get("sourceType") or article.get("type") or "").strip().lower()
    # Broad news publishers are not sector specialists. Their records must earn
    # sector placement through article text, not the feed's default domain.
    broad_publishers = {"mainstream_media", "international_media", "news_media"}
    if isinstance(domain, int) and 1 <= domain <= 11 and source_type not in broad_publishers:
        source_ids.add(domain)
    ids = keyword_ids | source_ids
    article["sectorIds"] = sorted(ids)
    article["sectorKeywordIds"] = sorted(keyword_ids)
    article["sectorSourceIds"] = sorted(source_ids)
    article["sectorLabels"] = [SECTOR_RULES[i][0] for i in sorted(ids)]
    if keyword_ids and source_ids:
        article["sectorClassification"] = "KEYWORD_AND_SOURCE_METADATA"
    elif keyword_ids:
        article["sectorClassification"] = "KEYWORD_MATCH"
    elif source_ids:
        article["sectorClassification"] = "SOURCE_METADATA"
    else:
        article["sectorClassification"] = "UNCLASSIFIED"
    article.pop("locality", None)
    declared_region = str(article.get("region") or "").strip().lower()
    # Do not turn an international story that merely mentions an NI place
    # into a local map incident.
    if declared_region not in ("international", "global", "world", "worldwide"):
        for name, lat, lon, terms in LOCALITY_POINTS:
            if any(re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", text) for term in terms):
                article["locality"] = {"name":name,"latitude":lat,"longitude":lon,"precision":"APPROXIMATE_TOWN_CENTRE"}
                if declared_region in ("unknown", ""):
                    article["region"] = "Northern Ireland"
                break
    article.setdefault("evidenceStatus","UNASSESSED")
    article.setdefault("confidence","UNASSESSED")
    return article



def now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(value):
    if not value:
        return ""

    value = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", str(value), flags=re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(re.sub(r"\s+", " ", value))

    return value.strip()


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
    if isinstance(xml_data, bytes):
        xml_text = xml_data.decode("utf-8-sig", errors="replace")
    else:
        xml_text = str(xml_data)

    xml_text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]",
        "",
        xml_text
    )

    xml_text = re.sub(
        r"<\?xml[^?]*\?>",
        "",
        xml_text,
        count=1,
        flags=re.IGNORECASE
    )

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

    xml_text = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)",
        "&amp;",
        xml_text
    )

    return xml_text


def regex_tag(block, tag):
    pattern = (
        r"<(?:[A-Za-z0-9_.-]+:)?" + re.escape(tag) + r"\b[^>]*>"
        r"(.*?)"
        r"</(?:[A-Za-z0-9_.-]+:)?" + re.escape(tag) + r"\s*>"
    )

    match = re.search(
        pattern,
        block,
        flags=re.IGNORECASE | re.DOTALL
    )

    if match:
        return clean(match.group(1))

    return ""


def parse_gdacs_fallback(xml_data, source):
    """
    Emergency RSS extraction for GDACS when its XML is malformed.
    Extracts individual RSS items without requiring a valid XML document.
    """

    if isinstance(xml_data, bytes):
        text_data = xml_data.decode("utf-8-sig", errors="replace")
    else:
        text_data = str(xml_data)

    items = re.findall(
        r"<(?:[A-Za-z0-9_.-]+:)?(?:item|entry)\b[^>]*>(.*?)</(?:[A-Za-z0-9_.-]+:)?(?:item|entry)\s*>",
        text_data,
        flags=re.IGNORECASE | re.DOTALL
    )

    print(
        "GDACS fallback candidate entries:",
        len(items),
        "- response preview:",
        clean(text_data[:240])[:180]
    )

    entries = []

    for item in items:
        title = regex_tag(item, "title")
        link = regex_tag(item, "link")

        if not link:
            link_match = re.search(
                r"<(?:[A-Za-z0-9_.-]+:)?link\b[^>]*\bhref=['\"]([^'\"]+)",
                item,
                flags=re.IGNORECASE | re.DOTALL
            )
            if link_match:
                link = clean(link_match.group(1))

        if not link:
            link = regex_tag(item, "guid")

        description = regex_tag(item, "description")

        published = (
            regex_tag(item, "pubDate")
            or regex_tag(item, "published")
            or regex_tag(item, "updated")
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
            "sourceTrust": source.get("trust", "unclassified"),
            "sourceType": source.get("sourceType", source.get("type", "unclassified")),
            "evidenceStatus": "UNASSESSED",
            "confidence": "UNASSESSED"
        })

    return entries


def parse_feed(xml_data, source):
    try:
        root = ET.fromstring(xml_data)

    except ET.ParseError as original_error:
        print(
            "XML repair attempted:",
            source.get("name", "Unknown source"),
            "-",
            str(original_error)
        )

        try:
            repaired = repair_xml(xml_data)
            root = ET.fromstring(repaired)

        except ET.ParseError as repair_error:

            if source.get("id") == "gdacs-global":
                print(
                    "GDACS fallback parser activated:",
                    str(repair_error)
                )

                entries = parse_gdacs_fallback(xml_data, source)

                if entries:
                    print(
                        "GDACS fallback extracted:",
                        len(entries),
                        "articles"
                    )
                    return entries

                raise ValueError(
                    "GDACS XML invalid and fallback found no usable RSS items"
                ) from repair_error

            raise repair_error from original_error

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

        if not link:
            link = child_text(element, {"guid", "id"})

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
            "sourceTrust": source.get("trust", "unclassified"),
            "sourceType": source.get("sourceType", source.get("type", "unclassified")),
            "evidenceStatus": "UNASSESSED",
            "confidence": "UNASSESSED"
        })

    return entries


def fetch_gdacs_api(source):
    """
    Use the official GDACS GeoJSON API instead of the RSS endpoint,
    which is returning an HTML response to the collector.
    """
    today = now().date()
    start_date = today - timedelta(days=7)
    params = urlencode({
        "fromDate": start_date.isoformat(),
        "toDate": today.isoformat(),
        "eventlist": "EQ,TC,FL,VO,DR,WF",
        "alertlevel": "Red;Orange"
    })
    url = source["url"].rstrip("?") + "?" + params
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/geo+json, application/json"
        }
    )

    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(MAX_FEED_SIZE)

    if not body:
        raise ValueError("GDACS API returned an empty response")

    payload = json.loads(body.decode("utf-8-sig", errors="replace"))
    features = payload.get("features", []) if isinstance(payload, dict) else []
    if not isinstance(features, list):
        raise ValueError("GDACS API response has no valid features array")

    articles = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or feature
        if not isinstance(properties, dict):
            continue

        event_type = str(properties.get("eventtype") or "").upper()
        event_id = str(properties.get("eventid") or "")
        episode_id = str(properties.get("episodeid") or "1")
        alert_level = str(properties.get("alertlevel") or "").strip()
        alert_lower = alert_level.lower()
        severity = (
            "high" if alert_lower == "red"
            else "medium" if alert_lower == "orange"
            else "unassessed"
        )
        title = str(
            properties.get("name")
            or (event_type + " event " + event_id).strip()
            or "GDACS disaster alert"
        )
        country = properties.get("country") or ""
        if isinstance(country, list):
            country = ", ".join(str(value) for value in country if value)
        severity_data = properties.get("severitydata") or {}
        severity_text = ""
        if isinstance(severity_data, dict):
            severity_text = str(
                severity_data.get("severitytext")
                or severity_data.get("severity")
                or ""
            )
        details = [
            "GDACS alert level: " + (alert_level or "not specified"),
            "Event type: " + (event_type or "not specified"),
            "Country/area: " + (str(country) or "not specified")
        ]
        if severity_text:
            details.append("Severity detail: " + severity_text)

        url_value = properties.get("url") or ""
        if isinstance(url_value, dict):
            url_value = url_value.get("report") or url_value.get("details") or ""
        link = str(
            properties.get("reportUrl")
            or properties.get("detailsUrl")
            or url_value
            or ""
        )
        if not link and event_type and event_id:
            link = (
                "https://www.gdacs.org/gdacsapi/api/events/geteventdata?"
                + urlencode({"eventtype": event_type, "eventid": event_id})
            )
        published = str(
            properties.get("datemodified")
            or properties.get("todate")
            or properties.get("fromdate")
            or ""
        )

        articles.append({
            "id": source["id"] + ":" + event_id + ":" + episode_id,
            "sourceId": source["id"],
            "source": source["name"],
            "title": title[:300],
            "url": link,
            "publishedAt": published,
            "collectedAt": iso(),
            "description": "; ".join(details)[:1200],
            "domain": source.get("domain"),
            "region": source.get("region", "International"),
            "priority": source.get("priority", "medium"),
            "sourceTrust": source.get("trust", "official_primary_source"),
            "sourceType": source.get("sourceType", "international_disaster_alert"),
            "severity": severity,
            "alertLevel": alert_level,
            "evidenceStatus": "UNASSESSED",
            "confidence": "UNASSESSED"
        })

    return articles, content_type, len(body), "GeoJSON FeatureCollection"



class ListingLinkParser(HTMLParser):
    """Collect linked text from an official HTML publication listing."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.current = {"href": href, "text": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            self.current["text"] = clean(" ".join(self.current["text"]))
            self.links.append(self.current)
            self.current = None


def fetch_html_listing(source):
    """Fetch a public official publication listing and extract article links."""
    request = urllib.request.Request(
        source["url"],
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml"
        }
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(MAX_FEED_SIZE)

    if not body:
        raise ValueError("Official listing returned an empty response")

    parser = ListingLinkParser()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    articles = []
    seen = set()
    allowed_host = urlparse(source["url"]).hostname or ""

    for item in parser.links:
        href = urljoin(source["url"], item["href"])
        parsed = urlparse(href)
        host = parsed.hostname or ""
        title_text = clean(item["text"])
        if not title_text or len(title_text) < 24:
            continue
        if parsed.scheme != "https" or not (host == allowed_host or host.endswith(".gov.uk") or host.endswith(".ni.gov.uk")):
            continue
        if href in seen or parsed.path.rstrip("/") in ("", "/press-releases"):
            continue
        lower = title_text.lower()
        if lower in ("next", "last", "home", "translate this page"):
            continue
        seen.add(href)

        published = ""
        match = re.search(
            r"Published\\s+(\\d{1,2}\\s+[A-Za-z]+\\s+\\d{4})",
            title_text,
            flags=re.IGNORECASE
        )
        if match:
            try:
                published = datetime.strptime(match.group(1), "%d %B %Y").replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            except ValueError:
                published = ""

        title = re.split(r"\\s+Published\\s+\\d{1,2}\\s+[A-Za-z]+\\s+\\d{4}", title_text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        title = title[:300]
        if len(title) > 240:
            sentence = re.split(r"(?<=[.!?])\\s+", title, maxsplit=1)
            if sentence and len(sentence[0]) >= 20:
                title = sentence[0][:300]

        articles.append({
            "id": source["id"] + ":" + href,
            "sourceId": source["id"],
            "source": source["name"],
            "title": title,
            "url": href,
            "publishedAt": published,
            "collectedAt": iso(),
            "description": title_text[:1200],
            "domain": source.get("domain"),
            "region": source.get("region", "Northern Ireland"),
            "priority": source.get("priority", "medium"),
            "sourceTrust": source.get("trust", "official_primary_source"),
            "sourceType": source.get("sourceType", "devolved_government"),
            "evidenceStatus": "UNASSESSED",
            "confidence": "UNASSESSED"
        })
        if len(articles) >= int(source.get("maxItems", 50)):
            break

    if not articles:
        raise ValueError("No eligible official article links found; listing structure may have changed")

    return articles, content_type, len(body), "HTML_LISTING"





class NIWaterUpdateParser(HTMLParser):
    """Extract area-based service update cards from NI Water's public listing."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards = []
        self.current = None
        self.capture_heading = False
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style", "noscript"):
            self.ignored += 1
            return
        if self.ignored:
            return
        if tag in ("h2", "h3", "h4"):
            self.current = {"heading": [], "body": []}
            self.cards.append(self.current)
            self.capture_heading = True
        elif tag in ("br", "p", "li", "div", "section"):
            if self.current is not None and self.current["body"]:
                self.current["body"].append(" ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style", "noscript") and self.ignored:
            self.ignored -= 1
        if tag in ("h2", "h3", "h4"):
            self.capture_heading = False

    def handle_data(self, data):
        if self.ignored:
            return
        if self.current is None:
            return
        target = self.current["heading"] if self.capture_heading else self.current["body"]
        target.append(data)


def fetch_niwater_service_updates(source):
    """Collect official NI Water area-level service updates and postcode impacts."""
    request = urllib.request.Request(
        source["url"],
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml"
        }
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(MAX_FEED_SIZE)

    if not body:
        raise ValueError("NI Water service update page returned an empty response")

    parser = NIWaterUpdateParser()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    articles = []
    seen = set()

    for card in parser.cards:
        area = clean(" ".join(card["heading"]))
        detail = clean(" ".join(card["body"]))
        if not area or not detail:
            continue
        if not re.search(r"Last updated\s*:", detail, flags=re.IGNORECASE):
            continue
        if not re.search(r"Postcode areas potentially affected\s*:", detail, flags=re.IGNORECASE):
            continue

        # Keep the update's own status and time fields explicit; do not infer
        # a restoration time when the operator has not supplied one.
        restored = bool(re.search(
            r"\b(supply has been restored|service has been restored|restored in your area)\b",
            detail, flags=re.IGNORECASE
        ))
        planned = bool(re.search(
            r"\b(planned maintenance|planned restriction|planned restrictions)\b",
            detail, flags=re.IGNORECASE
        ))
        status = "RESTORED" if restored else ("PLANNED" if planned else "ACTIVE")

        postcode_match = re.search(
            r"Postcode areas potentially affected\s*:\s*(.*?)(?:$)",
            detail, flags=re.IGNORECASE
        )
        postcodes = ""
        if postcode_match:
            postcodes = ", ".join(re.findall(
                r"\bBT\d{1,2}\s?\d?[A-Z]{2}\b",
                postcode_match.group(1), flags=re.IGNORECASE
            ))
        if not postcodes:
            # NI Water commonly presents postcode areas without an internal space.
            tail = detail[postcode_match.start():] if postcode_match else ""
            postcodes = ", ".join(re.findall(r"\bBT\d{5,6}\b", tail, flags=re.IGNORECASE))

        update_match = re.search(
            r"Last updated\s*:\s*(.*?)(?=Estimated start time\s*:|Estimated restoration time\s*:|$)",
            detail, flags=re.IGNORECASE
        )
        start_match = re.search(
            r"Estimated start time\s*:\s*(.*?)(?=Estimated restoration time\s*:|$)",
            detail, flags=re.IGNORECASE
        )
        restore_match = re.search(
            r"Estimated restoration time\s*:\s*(.*?)(?=\d{1,2}\s+[A-Za-z]+\s+\d{4}\s+\d{1,2}:\d{2}|$)",
            detail, flags=re.IGNORECASE
        )

        update_time = clean(update_match.group(1)) if update_match else ""
        start_time = clean(start_match.group(1)) if start_match else ""
        restoration_time = clean(restore_match.group(1)) if restore_match else ""

        # Stable IDs prevent a refreshed collection timestamp creating duplicates.
        # One current NI Water card per affected area; refreshed timestamps update the same record.
        identity = area.lower()
        digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
        article_id = source["id"] + ":" + digest
        if article_id in seen:
            continue
        seen.add(article_id)

        title = "NI Water service update — " + area[:180]
        description_parts = ["Status: " + status]
        if update_time:
            description_parts.append("Last updated: " + update_time)
        if start_time:
            description_parts.append("Estimated start time: " + start_time)
        if restoration_time:
            description_parts.append("Estimated restoration time: " + restoration_time)
        if postcodes:
            description_parts.append("Postcodes potentially affected: " + postcodes)
        description_parts.append(detail[:2400])

        articles.append({
            "id": article_id,
            "sourceId": source["id"],
            "source": source["name"],
            "title": title,
            "url": source["url"],
            "publishedAt": update_time,
            "collectedAt": iso(),
            "description": " | ".join(description_parts)[:3000],
            "domain": source.get("domain", 5),
            "region": "Northern Ireland",
            "priority": source.get("priority", "high"),
            "sourceTrust": "official_primary_source",
            "sourceType": "utility_service_update",
            "serviceStatus": status,
            "affectedPostcodes": postcodes,
            "estimatedStartTime": start_time,
            "estimatedRestorationTime": restoration_time,
            "evidenceStatus": "OFFICIAL_OPERATOR_UPDATE",
            "confidence": "HIGH"
        })

    if not articles:
        raise ValueError(
            "No NI Water service update cards found; page structure may have changed"
        )

    return articles, content_type, len(body), "NIWATER_SERVICE_UPDATES"



class NIEPowercheckTableParser(HTMLParser):
    """Extract official outage and planned-work rows from NIE Powercheck."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.current_row = None
        self.current_cell = None
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style", "noscript"):
            self.ignored += 1
            return
        if self.ignored:
            return
        if tag == "tr":
            self.current_row = []
        elif tag in ("td", "th") and self.current_row is not None:
            self.current_cell = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style", "noscript") and self.ignored:
            self.ignored -= 1
            return
        if self.ignored:
            return
        if tag in ("td", "th") and self.current_row is not None and self.current_cell is not None:
            self.current_row.append(clean(" ".join(self.current_cell)))
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = None
            self.current_cell = None

    def handle_data(self, data):
        if not self.ignored and self.current_cell is not None:
            self.current_cell.append(data)


def fetch_nie_powercheck(source):
    """Fallback to NIE's own public Powercheck outage table."""
    url = source.get("liveUrl", "https://powercheck.nienetworks.co.uk/TabularFaults.html")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml"
        }
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(MAX_FEED_SIZE)
    if not body:
        raise ValueError("NIE Powercheck returned an empty response")
    html = body.decode("utf-8-sig", errors="replace")
    parser = NIEPowercheckTableParser()
    parser.feed(html)
    articles, seen = [], set()
    for row in parser.rows:
        if len(row) < 5 or "event" in row[0].lower() or "plan number" in row[0].lower():
            continue
        event_id, outage_type, postcodes, start_time, restore_time = row[:5]
        if not event_id or not postcodes:
            continue
        if event_id in seen:
            continue
        seen.add(event_id)
        planned = "plan" in (event_id + " " + outage_type).lower() or "planned" in outage_type.lower()
        status = "PLANNED" if planned else "ACTIVE"
        details = [
            "Status: " + status,
            "Outage type: " + (outage_type or "Not supplied"),
            "Affected postcodes: " + (postcodes or "Not supplied"),
            "Start time: " + (start_time or "Not supplied"),
            "Estimated restoration: " + (restore_time or "Not supplied"),
            "Source: NIE Networks official Powercheck live table"
        ]
        articles.append({
            "id": source["id"] + ":" + event_id,
            "sourceId": source["id"],
            "source": source["name"],
            "title": "NIE Networks " + ("planned outage" if planned else "power fault") + " — " + postcodes,
            "url": url,
            "publishedAt": start_time,
            "collectedAt": iso(),
            "description": " | ".join(details),
            "domain": source.get("domain", 5),
            "region": "Northern Ireland",
            "priority": "high",
            "sourceTrust": "official_primary_source",
            "sourceType": "electricity_network_outage",
            "serviceStatus": status,
            "outageType": outage_type,
            "affectedPostcodes": postcodes,
            "estimatedRestorationTime": restore_time,
            "evidenceStatus": "OFFICIAL_OPERATOR_UPDATE",
            "confidence": "HIGH"
        })
    if not articles and not re.search(r"no active alerts at present", html, flags=re.IGNORECASE):
        raise ValueError("NIE Powercheck page did not expose an outage table or explicit no-alert status")
    return articles, content_type, len(body), "NIE_POWERCHECK_HTML"


def fetch_nie_network_outages(source):
    """Collect official live NIE Networks faults from its open-data API."""
    endpoints = [
        source["url"],
        "https://nienetworks.huwise.com/api/explore/v2.1/catalog/datasets/nie-networks-network-faults/records?limit=100",
        "https://nienetworks.opendatasoft.com/api/records/1.0/search/?dataset=nie-networks-network-faults&rows=100"
    ]
    body = None
    content_type = ""
    last_error = None
    for endpoint in endpoints:
        request = urllib.request.Request(
            endpoint,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; DoomWatch/1.0; +https://scolerimolari.github.io/DoomWatch/)",
                "Accept": "application/json,text/csv,*/*",
                "Referer": source.get("articleUrl", "https://nienetworks.opendatasoft.com/")
            }
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read(MAX_FEED_SIZE)
            if body:
                break
        except Exception as error:
            last_error = error
    if not body:
        print("NIE OPEN DATA API UNAVAILABLE:", str(last_error)[:200], "- using official Powercheck table")
        return fetch_nie_powercheck(source)
    if "csv" in content_type.lower() or body[:100].count(b",") > 3 and not body.lstrip().startswith(b"{"):
        import csv
        import io
        rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig", errors="replace"))))
        payload = {}
    else:
        payload = json.loads(body.decode("utf-8-sig", errors="replace"))
        rows = payload.get("results") or payload.get("records") or []
        if not rows and isinstance(payload.get("records"), list):
            rows = payload["records"]
    
    articles, seen = [], set()
    for row in rows:
        fields = row.get("fields", row) if isinstance(row, dict) else {}
        if not isinstance(fields, dict):
            continue
        outage_id = clean(fields.get("outageid") or fields.get("event_id") or fields.get("id"))
        if not outage_id or outage_id in seen:
            continue
        seen.add(outage_id)
        outage_type = clean(fields.get("outagetype"))
        start_time = clean(fields.get("starttime"))
        restore_time = clean(fields.get("estrestorefulldatetime"))
        postcode = clean(fields.get("postcode"))
        customers = clean(fields.get("numcustaffected"))
        status_message = clean(fields.get("statusmessage"))
        updated = clean(fields.get("updatedtimestamp"))
        title = "NIE Networks power fault" + (" — " + postcode if postcode else "")
        details = ["Status: ACTIVE (listed in NIE Networks live outage dataset)", "Outage type: " + (outage_type or "Not supplied"), "Affected postcode: " + (postcode or "Not supplied"), "Customers affected: " + (customers or "Not supplied"), "Start time: " + (start_time or "Not supplied"), "Estimated restoration: " + (restore_time or "Not supplied"), "Last updated: " + (updated or "Not supplied"), "Operator message: " + (status_message or "Not supplied")]
        articles.append({"id": source["id"] + ":" + outage_id, "sourceId": source["id"], "source": source["name"], "title": title, "url": source.get("articleUrl", "https://nienetworks.opendatasoft.com/explore/dataset/nie-networks-network-faults/"), "publishedAt": start_time or updated, "collectedAt": iso(), "description": " | ".join(details), "domain": source.get("domain", 5), "region": "Northern Ireland", "priority": "high", "sourceTrust": "official_primary_source", "sourceType": "electricity_network_outage", "serviceStatus": "ACTIVE", "outageType": outage_type, "affectedPostcodes": postcode, "customersAffected": customers, "estimatedRestorationTime": restore_time, "lastOperatorUpdate": updated, "operatorStatusMessage": status_message, "evidenceStatus": "OFFICIAL_OPERATOR_UPDATE", "confidence": "HIGH"})
    return articles, content_type, len(body), "NIE_NETWORK_OUTAGES"



class ConditionsViewRiverParser(HTMLParser):
    """Read station cards from ConditionsView's consolidated DfI station table."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.in_anchor = False

    def _finish(self):
        if self.current:
            self.current["name"] = clean(" ".join(self.current["name"]))
            self.current["context"] = clean(" ".join(self.current["context"]))
            if self.current["name"] and self.current["href"]:
                self.items.append(self.current)
        self.current = None
        self.in_anchor = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href", "")
            if "/en/water/" in href and "/country/" not in href:
                self._finish()
                self.current = {"href": href, "name": [], "context": []}
                self.in_anchor = True
            elif self.current:
                self.in_anchor = False
        elif self.current and not self.in_anchor and tag.lower() in ("br", "p", "div", "li", "span"):
            self.current["context"].append(" ")

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.in_anchor:
            self.in_anchor = False

    def handle_data(self, data):
        if self.current:
            (self.current["name"] if self.in_anchor else self.current["context"]).append(data)

    def close(self):
        super().close()
        self._finish()


RIVER_STATION_TOWNS = {
    "203012": "Cookstown", "203010": "Dungannon", "235006": "Armagh",
    "203027": "Ballymena", "201007": "Derry/Londonderry",
    "236005": "Enniskillen", "234039": "Omagh", "202002": "Derry/Londonderry",
    "205004": "Lisburn", "203040": "Coleraine", "203011": "Antrim",
    "201010": "Omagh", "203020": "Cookstown", "202001": "Limavady",
    "236007": "Enniskillen", "203018": "Antrim", "203017": "Portadown",
    "203033": "Portadown"
}


def fetch_dfi_river_levels(source):
    """Collect provisional DfI readings and station coordinates from station detail pages."""
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(MAX_FEED_SIZE)
    if not body:
        raise ValueError("Northern Ireland river-level page returned an empty response")

    parser = ConditionsViewRiverParser()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    parser.close()

    def fetch_station_detail(item):
        href = urljoin(source["url"], item["href"])
        try:
            station_request = urllib.request.Request(
                href,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
            )
            with urllib.request.urlopen(station_request, timeout=TIMEOUT) as station_response:
                station_body = station_response.read(MAX_FEED_SIZE).decode("utf-8-sig", errors="replace")
            return href, station_body, ""
        except Exception as exc:
            return href, "", clean(str(exc))[:180]

    # Fetch station metadata concurrently so a slow station page does not stall the full collector.
    with ThreadPoolExecutor(max_workers=8) as executor:
        station_details = {href: (station_body, error) for href, station_body, error in executor.map(fetch_station_detail, parser.items)}

    articles = []
    seen = set()
    for item in parser.items:
        href = urljoin(source["url"], item["href"])
        if href in seen:
            continue
        seen.add(href)
        name = clean(item["name"])
        context = clean(item["context"])
        level_match = re.search(r"(-?\d+(?:\.\d+)?)\s*m\b", context, re.IGNORECASE)
        if not level_match:
            continue
        level = level_match.group(1)
        code_match = re.search(r"\b(\d{6})\b", context)
        station_code = code_match.group(1) if code_match else ""
        trend_match = re.search(r"(▲|▼|→)", context)
        trend = {"▲": "RISING", "▼": "FALLING", "→": "STEADY"}.get(trend_match.group(1) if trend_match else "", "NOT REPORTED")
        age_match = re.search(r"\b(\d+\s*(?:min|mins|minutes|h|hr|hrs|hour|hours)\s+ago|just now)\b", context, re.IGNORECASE)
        reading_age = age_match.group(1) if age_match else "age not supplied"

        station_body, station_error = station_details.get(href, ("", "station detail page not fetched"))
        station_text = clean(station_body)
        station_code_match = re.search(r"Station code\s+(\d{6})", station_text, re.IGNORECASE)
        if station_code_match:
            station_code = station_code_match.group(1)
        coordinate_match = re.search(
            r"Coordinates\s+(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)",
            station_text,
            re.IGNORECASE
        )
        latitude = float(coordinate_match.group(1)) if coordinate_match else None
        longitude = float(coordinate_match.group(2)) if coordinate_match else None
        has_current_reading = not bool(re.search(
            r"No reading since\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}",
            station_text,
            re.IGNORECASE
        ))
        status = "CURRENT_READING" if has_current_reading else "STALE_OR_NO_CURRENT_READING"
        town = RIVER_STATION_TOWNS.get(station_code, "")
        if not town:
            lower = name.lower()
            town = next((t for t in ("Antrim", "Ballymena", "Belfast", "Coleraine", "Cookstown", "Derry/Londonderry", "Dungannon", "Enniskillen", "Limavady", "Lisburn", "Omagh", "Portadown") if t.lower() in lower), "")
        location_text = (
            "Verified station coordinates: " + str(latitude) + ", " + str(longitude) + "."
            if latitude is not None and longitude is not None
            else "Station coordinates unavailable; do not plot this record as an exact location."
        )
        title = "RIVER GAUGE // " + name + " — " + level + " m"
        description = (
            "DfI Rivers water-level observation relayed by ConditionsView. "
            + "Latest published level: " + level + " m. Trend: " + trend + ". "
            + "Provider reports this reading was updated " + reading_age + ". "
            + "Station status: " + status + ". " + location_text + " "
            + "Each gauge has its own reference zero; do not compare levels between stations. "
            + "This is a provisional measurement, not a flood warning or a prediction."
        )
        articles.append({
            "id": source["id"] + ":" + (station_code or hashlib.sha1(href.encode("utf-8")).hexdigest()[:12]),
            "sourceId": source["id"],
            "source": source["name"],
            "title": title,
            "url": href,
            "publishedAt": iso(),
            "collectedAt": iso(),
            "description": description,
            "domain": source.get("domain", 9),
            "region": "Northern Ireland",
            "priority": "high",
            "sourceTrust": "third_party_aggregator",
            "sourceType": "river_level_observation",
            "stationName": name,
            "stationCode": station_code,
            "readingLevelMetres": level,
            "readingTrend": trend,
            "readingAge": reading_age,
            "stationStatus": status,
            "stationLatitude": latitude,
            "stationLongitude": longitude,
            "stationCoordinatesVerified": latitude is not None and longitude is not None,
            "mapTownApproximation": town,
            "stationPageError": station_error,
            "evidenceStatus": "PROVISIONAL_DFI_READING_VIA_AGGREGATOR",
            "confidence": "PROVISIONAL"
        })

    if not articles:
        raise ValueError("No DfI river gauge readings parsed; upstream page structure may have changed")
    verified = sum(1 for item in articles if item.get("stationCoordinatesVerified"))
    stale = sum(1 for item in articles if item.get("stationStatus") == "STALE_OR_NO_CURRENT_READING")
    print("DfI station detail pages with verified coordinates:", verified, "/", len(articles))
    print("DfI gauges with stale or no current reading:", stale, "/", len(articles))
    return articles, content_type, len(body), "CONDITIONSVIEW_DFI_RIVER_TABLE_WITH_STATION_COORDINATES"


def fetch_feed(source):
    if source.get("method") == "dfi_river_levels":
        return fetch_dfi_river_levels(source)

    if source.get("method") == "html_listing":
        return fetch_html_listing(source)

    if source.get("method") == "niwater_service_updates":
        return fetch_niwater_service_updates(source)

    if source.get("method") == "nie_network_outages":
        return fetch_nie_network_outages(source)

    if source.get("id") == "gdacs-global":
        return fetch_gdacs_api(source)

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

    if not articles:
        try:
            diagnostic_root = ET.fromstring(repair_xml(body))
            candidates = [
                element for element in diagnostic_root.iter()
                if local_name(element.tag) in ("item", "entry")
            ]
            first = candidates[0] if candidates else None
            print(
                "EMPTY PARSER DETAILS:",
                source.get("id"),
                "- entries:",
                len(candidates),
                "- first child tags:",
                ",".join(local_name(child.tag) for child in list(first)[:12]) if first is not None else "none",
                "- first title:",
                child_text(first, {"title"})[:100] if first is not None else "none",
                "- first link:",
                child_text(first, {"link", "guid", "id"})[:160] if first is not None else "none"
            )
        except ET.ParseError:
            pass

    root_match = re.search(
        rb"<([A-Za-z][A-Za-z0-9_.:-]*)",
        body
    )
    root_tag = (
        root_match.group(1).decode("ascii", errors="replace")
        if root_match else "UNKNOWN"
    )

    return articles, content_type, len(body), root_tag


def collect_bluesky_searches():
    """Collect public Bluesky search posts as explicitly unverified signals."""
    searches = [
        ("cyber", "ransomware cyber attack data breach"),
        ("supply-chain", "supply chain"),
        ("belfast-local", "Belfast"),
        ("northern-ireland", "Northern Ireland"),
        ("conflict-shipping", "war conflict shipping disruption"),
        ("fuel-food", "fuel shortage food supply shortage"),
        ("culture-war", "culture war"),
        ("civil-liberties", "civil liberties"),
        ("newtownabbey-local", "Newtownabbey"),
        ("ballyclare-local", "Ballyclare"),
        ("ni-utilities", "Northern Ireland power outage water disruption"),
        ("ni-supply-chain", "Northern Ireland fuel food supply shortage"),
        ("belfast-ports", "Belfast port ferry freight disruption"),
        ("ni-cyber", "Northern Ireland cyber attack ransomware")
    ]
    endpoints = [
        "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
        "https://api.bsky.app/xrpc/app.bsky.feed.SEARCHPOSTS",
        "https://public.api.bsky.app/xrpc/app.bsky.feed.SEARCHPOSTS"
    ]
    results, statuses = [], []

    for search_id, query in searches:
        try:
            payload = None
            last_http_error = None
            for endpoint in endpoints:
                url = endpoint + "?" + urlencode({
                    "q": query, "limit": 20, "sort": "latest", "lang": "en"
                })
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
                )
                try:
                    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                        payload = json.loads(
                            response.read(2_000_000).decode("utf-8-sig", errors="replace")
                        )
                    break
                except HTTPError as error:
                    if error.code != 403:
                        raise
                    last_http_error = error

            if payload is None:
                raise last_http_error or RuntimeError("All Bluesky search endpoints failed")

            posts = payload.get("posts", []) if isinstance(payload, dict) else []
            added = 0
            for item in posts:
                if not isinstance(item, dict):
                    continue
                record = item.get("record") or {}
                author = item.get("author") or {}
                post_text = clean(record.get("text", ""))[:1200]
                uri = str(item.get("uri", ""))
                if not post_text or not uri:
                    continue

                parts = uri.split("/")
                rkey = parts[-1] if parts else ""
                handle = str(author.get("handle", ""))
                link = (
                    "https://bsky.app/profile/" + handle + "/post/" + rkey
                    if handle and rkey else ""
                )
                published = str(item.get("indexedAt") or record.get("createdAt") or "")
                lower = post_text.lower()
                region = (
                    "Northern Ireland"
                    if any(term in lower for term in (
                        "northern ireland", "belfast", "derry", "londonderry",
                        "newtownabbey", "ballyclare", "antrim", "armagh",
                        "omagh", "coleraine", "ballymena", "newry", "larne"
                    ))
                    else "Global"
                )
                results.append({
                    "id": "bluesky:" + uri,
                    "sourceId": "bluesky-" + search_id,
                    "source": "Bluesky public search",
                    "title": post_text.splitlines()[0][:240],
                    "url": link,
                    "publishedAt": published,
                    "collectedAt": iso(),
                    "description": post_text,
                    "domain": "open_social_signals",
                    "region": region,
                    "priority": "low",
                    "sourceTrust": "unverified_social",
                    "sourceType": "social_network",
                    "platform": "Bluesky",
                    "searchQuery": query,
                    "evidenceStatus": "UNASSESSED",
                    "confidence": "UNASSESSED"
                })
                added += 1

            statuses.append({
                "id": "bluesky-" + search_id,
                "name": "Bluesky public search: " + query,
                "status": "OK" if added else "EMPTY",
                "checkedAt": iso(),
                "articleCount": added,
                "sourceTrust": "unverified_social",
                "sourceType": "social_network"
            })
            print("BLUESKY:", search_id, "-", added, "public posts")

        except Exception as error:
            statuses.append({
                "id": "bluesky-" + search_id,
                "name": "Bluesky public search: " + query,
                "status": "FAILED",
                "checkedAt": iso(),
                "error": str(error)[:300],
                "articleCount": 0,
                "sourceTrust": "unverified_social",
                "sourceType": "social_network"
            })
            print("BLUESKY FAILED:", search_id, "-", str(error)[:200])

    return results, statuses


def load_json(path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def matches_ballyclare_traffic(article):
    source_id = str(article.get("sourceId", "")).lower()
    if not source_id.startswith("trafficwatch-"):
        return False
    if not any(kind in source_id for kind in ("incident", "roadwork")):
        return False
    text = " ".join(str(article.get(field, "") or "") for field in ("title", "description", "summary")).upper()
    normalized = re.sub(r"\b([AB])0+(\d+)\b", r"\1\2", text)
    place_terms = ("BALLYCLARE", "DOAGH", "PARKGATE", "BALLYNURE", "TEMPLEPATRICK", "HILLHEAD ROAD", "BALLYEASTON", "BALLYCORR", "BALLYBOLEY")
    if any(re.search(r"(?<![A-Z0-9])" + re.escape(term) + r"(?![A-Z0-9])", normalized) for term in place_terms):
        return True
    if any(re.search(r"(?<![A-Z0-9])" + road + r"(?![A-Z0-9])", normalized) for road in ("A57", "A8", "B94", "B59")):
        return True
    return bool(re.search(r"(?<![A-Z0-9])M2(?![A-Z0-9])", normalized) and re.search(r"SANDYKNOWES|GREENCASTLE|TEMPLEPATRICK|BALLYCLARE|JUNCTION 2|JUNCTION 4|(?<![A-Z0-9])J2(?![A-Z0-9])|(?<![A-Z0-9])J4(?![A-Z0-9])", normalized))


def update_ballyclare_history(current_records):
    history_path = ROOT / "data" / "ballyclare-history.json"
    history = load_json(history_path, {"records": []})
    existing_records = history.get("records", []) if isinstance(history, dict) else []
    combined = {}
    for item in existing_records + current_records:
        key = str(item.get("id") or item.get("url") or "")
        if key:
            combined[key] = item
    records = sorted(combined.values(), key=lambda item: str(item.get("publishedAt") or item.get("collectedAt") or ""), reverse=True)[:10000]
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("w", encoding="utf-8") as file:
        json.dump({"updatedAt": iso(), "retention": "Persistent archive, capped at 10,000 unique source records", "recordCount": len(records), "records": records}, file, indent=2, ensure_ascii=False)
        file.write("\n")
    print("BALLYCLARE HISTORY RECORDS:", len(records))


def main():
    if not FEEDS_FILE.exists():
        raise FileNotFoundError("feeds.json is missing")

    if not DATA_FILE.exists():
        raise FileNotFoundError("data/intelligence.json is missing")

    config = load_json(FEEDS_FILE, {})
    intelligence = load_json(DATA_FILE, {})

    
    feeds = config.get("feeds", [])

    # ADDITIVE SOURCE REGISTER SUPPORT
    # Existing feeds always take priority. New eligible RSS
    # sources are appended without changing the existing feed list.

    SOURCES_FILE = ROOT / "sources.json"
    additional_count = 0

    if SOURCES_FILE.exists():
        source_register = load_json(SOURCES_FILE, {})
        registered_sources = source_register.get("sources", [])

        existing_ids = {
            item.get("id") for item in feeds
        }

        existing_urls = {
            item.get("url") for item in feeds
        }

        for item in registered_sources:
            endpoint = item.get("endpoint")
            source_id = item.get("id")

            if item.get("status") != "candidate":
                continue

            if item.get("method") != "rss":
                continue

            if not endpoint or not endpoint.startswith("https://"):
                continue

            if not source_id or source_id in existing_ids:
                continue

            if endpoint in existing_urls:
                continue

            sectors = item.get("sectors", [])

            feeds.append({
                "id": source_id,
                "name": item.get("name", source_id),
                "url": endpoint,
                "domain": sectors[0] if sectors else None,
                "region": item.get("region", "Unknown"),
                "priority": "medium",
                "tier": 3,
                "trust": item.get("trust", "unclassified"),
                "sourceType": item.get("type", "unclassified")
            })

            existing_ids.add(source_id)
            existing_urls.add(endpoint)
            additional_count += 1

    print("Additional RSS sources enabled:", additional_count)

    collected = []
    source_status = []

    print("DOOMWATCH COLLECTOR STARTING")
    print("Configured feeds:", len(feeds))
    print("--------------------------------")

    for source in feeds:
        try:
            articles, content_type, response_bytes, root_tag = fetch_feed(source)
            collected.extend(articles)

            feed_state = "OK" if articles else "EMPTY"
            source_status.append({
                "id": source["id"],
                "name": source["name"],
                "sourceTrust": source.get("trust", "unclassified"),
                "status": feed_state,
                "checkedAt": iso(),
                "articleCount": len(articles),
                "contentType": content_type,
                "responseBytes": response_bytes,
                "rootTag": root_tag
            })

            print(
                feed_state + ":",
                source["name"],
                "-",
                len(articles),
                "articles"
            )

            if not articles:
                print(
                    "EMPTY DETAILS:",
                    source["id"],
                    "-",
                    content_type,
                    "-",
                    response_bytes,
                    "bytes - root:",
                    root_tag
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

    # Public social listening layer. Posts remain explicitly unverified.
    social_posts, social_status = collect_bluesky_searches()
    collected.extend(social_posts)
    source_status.extend(social_status)

    existing = intelligence.get("articles", [])
    combined = {}

    for article in existing + collected:
        key = article.get("id") or article.get("url")

        if key:
            combined[key] = article

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

    # Backfill publisher metadata before classification so historical records
    # from broad news feeds are treated consistently with newly collected ones.
    feed_metadata = {
        str(item.get("id")): item
        for item in feeds
        if item.get("id")
    }
    for article in retained:
        metadata = feed_metadata.get(str(article.get("sourceId", "")), {})
        if not article.get("sourceTrust"):
            article["sourceTrust"] = metadata.get("trust", "unclassified")
        if not article.get("sourceType"):
            article["sourceType"] = metadata.get(
                "sourceType",
                metadata.get("type", "unclassified")
            )

    # Maintain a separate long-lived local traffic archive before the rolling
    # 90-day intelligence window is written back to the main archive.
    ballyclare_records = []
    for article in retained:
        if matches_ballyclare_traffic(article):
            ballyclare_records.append({
                field: article.get(field)
                for field in ("id", "sourceId", "source", "title", "url", "publishedAt", "collectedAt", "description", "summary", "region", "sourceTrust", "sourceType", "evidenceStatus", "confidence")
                if article.get(field) is not None
            })
    update_ballyclare_history(ballyclare_records)

    # Add transparent sector tags and approximate town-level map metadata.
    for article in retained:
        enrich_article(article)

    intelligence["articles"] = retained[:MAX_ARTICLES]
    intelligence["sourceStatus"] = source_status

    intelligence["sectorCoverage"] = [
        {
            "id": sector_id,
            "name": label,
            "recordCount": sum(1 for article in intelligence["articles"] if sector_id in article.get("sectorIds", [])),
            "keywordRecordCount": sum(1 for article in intelligence["articles"] if sector_id in article.get("sectorKeywordIds", [])),
            "sourceTaggedRecordCount": sum(1 for article in intelligence["articles"] if sector_id in article.get("sectorSourceIds", [])),
            "sourceCount": len(set(str(article.get("sourceId") or article.get("source") or "") for article in intelligence["articles"] if sector_id in article.get("sectorIds", []))),
            "classification": "KEYWORD_AND_SOURCE_METADATA",
            "disclaimer": "Coverage is not a measure of risk, severity or completeness."
        }
        for sector_id, (label, terms) in SECTOR_RULES.items()
    ]

    intelligence["collector"] = {
        "lastRun": iso(),
        "configuredFeeds": len(feeds) + len(social_status),
        "successfulFeeds": sum(
            1 for item in source_status
            if item["status"] in ("OK", "EMPTY")
        ),
        "emptyFeeds": sum(
            1 for item in source_status
            if item["status"] == "EMPTY"
        ),
        "failedFeeds": sum(
            1 for item in source_status
            if item["status"] == "FAILED"
        ),
        "newArticles": len(collected),
        "retainedArticles": len(intelligence["articles"]),
        "historyDays": 90
    }

    intelligence["collectorLastRun"] = intelligence["collector"]["lastRun"]

    report_lines = [
        "COLLECTION SUMMARY // FACTUAL STATUS ONLY",
        "Last collection: " + intelligence["collector"]["lastRun"],
        "Sources reporting successfully: " + str(intelligence["collector"]["successfulFeeds"]) + " of " + str(intelligence["collector"]["configuredFeeds"]),
        "Sources reporting empty feeds: " + str(intelligence["collector"]["emptyFeeds"]),
        "Sources reporting failure: " + str(intelligence["collector"]["failedFeeds"]),
        "New feed records collected this run: " + str(intelligence["collector"]["newArticles"]),
        "Records retained in the 90-day intelligence window: " + str(intelligence["collector"]["retainedArticles"]),
    ]

    failed_names = [
        item.get("name", item.get("id", "Unknown source"))
        for item in source_status
        if item.get("status") == "FAILED"
    ]

    if failed_names:
        report_lines.append("Feeds requiring attention: " + ", ".join(failed_names[:12]))
    else:
        report_lines.append("All configured feeds reported a successful response.")

    report_lines.append(
        "This is a collection-health summary, not an automated threat assessment. "
        "Review individual reports and official advisories before taking action."
    )

    intelligence["report"] = "\n".join(report_lines)

    # Factual daily snapshot: only records published or collected in the last 48 hours.
    # Official/high-priority source feeds are surfaced first, without implying incident severity.
    def brief_region(article):
        region = str(article.get("region", "")).strip().lower()
        if "northern ireland" in region or region == "ni":
            return "NI"
        if region in ("international", "global", "world"):
            return "INTERNATIONAL"
        if region in ("uk", "united kingdom", "great britain", "britain"):
            return "UK"
        if region in ("england", "scotland", "wales"):
            return "UK"
        return "UNKNOWN"

    def brief_date(article):
        for field in ("publishedAt", "collectedAt"):
            value = article.get(field)
            if not value:
                continue
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                try:
                    parsed = parsedate_to_datetime(str(value))
                except (ValueError, TypeError, OverflowError):
                    continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        return None

    brief_cutoff = now() - timedelta(hours=48)
    grouped = {"NI": [], "UK": [], "INTERNATIONAL": [], "UNKNOWN": []}
    for article in intelligence["articles"]:
        article_date = brief_date(article)
        if article_date is None or article_date < brief_cutoff:
            continue
        region = brief_region(article)
        grouped[region].append((article, article_date))

    def brief_sort_key(record):
        article, article_date = record
        priority = str(article.get("priority", "medium")).lower()
        priority_rank = {"high": 0, "medium": 1, "low": 2}.get(priority, 3)
        return (priority_rank, -article_date.timestamp())

    brief_sections = []
    for region in ("NI", "UK", "INTERNATIONAL", "UNKNOWN"):
        ranked_records = sorted(grouped[region], key=brief_sort_key)
        records = []
        source_counts = {}
        for record in ranked_records:
            article = record[0]
            source_key = str(
                article.get("sourceId")
                or article.get("source")
                or "unknown"
            )
            if source_counts.get(source_key, 0) >= 2:
                continue
            records.append(record)
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
            if len(records) >= 6:
                break

        brief_sections.append({
            "region": region,
            "recordCount": len(grouped[region]),
            "entries": [
                {
                    "title": str(article.get("title", "Untitled record"))[:300],
                    "source": str(article.get("source", "Source not specified"))[:160],
                    "sourceTrust": str(article.get("sourceTrust", "unclassified")),
                    "url": str(article.get("url", "")),
                    "publishedAt": article.get("publishedAt") or article.get("collectedAt", ""),
                    "sector": article.get("domain"),
                    "sourcePriority": str(article.get("priority", "medium")).upper(),
                    "evidenceStatus": article.get("evidenceStatus", "UNASSESSED")
                }
                for article, article_date in records
            ]
        })

    intelligence["dailyBrief"] = {
        "generatedAt": iso(),
        "type": "FACTUAL_SOURCE_SNAPSHOT",
        "windowHours": 48,
        "disclaimer": "Records published or collected within the last 48 hours, grouped by the region declared by each source. Source class describes publisher type, not truth or verification; higher-priority feeds are listed first. Inclusion is not confirmation of an incident, severity or local impact. Open original sources and official advisories.",
        "totalRecords": sum(len(items) for items in grouped.values()),
        "regions": brief_sections
    }

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
