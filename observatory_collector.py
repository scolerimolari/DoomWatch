#!/usr/bin/env python3
"""DoomWatch six-flow intelligence observatory.

Builds a separate, reviewable workspace from the existing 90-day intelligence
archive plus two low-cost public data endpoints. It does not promote a signal
to a verified incident or change the existing intelligence archive.
"""
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARCHIVE = DATA / "intelligence.json"
SOURCES = ROOT / "sources.json"
FRINGE_SOURCES = ROOT / "fringe_sources.json"
FRINGE_ARCHIVE = DATA / "fringe.json"
OUTPUT = DATA / "observatory.json"
UA = "DoomWatch-Observatory/1.0 (+https://github.com/scolerimolari/DoomWatch)"
TIMEOUT = 18
MAX_RECORDS = 180

FLOW_DEFS = {
 "osint": {
  "name":"OSINT Observatory",
  "desc":"Geospatial, satellite, transport, disaster and publicly observable infrastructure indicators. Satellite entries are catalogue metadata only; they are not interpreted imagery.",
  "terms":("satellite","sentinel","copernicus","gdacs","aircraft","aviation","flight","maritime","vessel","shipping","port","harbour","harbor","ais","geospatial","earth observation","river gauge","flood","outage","road closure","infrastructure"),
  "types":("satellite_observation","international_disaster_alert","transport_incidents","transport_roadworks","transport_events","electricity_network_outage","river_level_observation","port_operator","airport_operator")
 },
 "community": {
  "name":"Community Signals",
  "desc":"Public community and social reporting, including local observations. These are leads for review, not proof. Private messages and closed groups are not collected.",
  "terms":("ballyclare","newtownabbey","belfast","antrim","larne","derry","northern ireland","community","local report","resident","neighbourhood","road closed","power cut","water outage","shelter","evacuation","mastodon","lemmy","reddit","telegram"),
  "types":("social_network","community_network","regional_newsroom","community_report")
 },
 "fringe": {
  "name":"Fringe & Emerging Signals",
  "desc":"Alternative commentary, specialist communities and weak signals. Inclusion is for monitoring only; it is not an endorsement of the publisher or its claims.",
  "terms":("alternative media","alternative commentary","fringe narrative","fringe","unconventional","emerging","narrative","rumour","rumor","disinformation","influence operation","civil liberties","surveillance","preparedness","zero hedge","offguardian","daily sceptic","expose","uk column","activist post","statewatch"),
  "types":("alternative_media","alternative_financial_media","independent_commentary","alternative_commentary","preparedness_media","independent_research","curated_alternative","civil_liberties_organisation")
 },
 "economic": {
  "name":"Economic Stress",
  "desc":"Qualitative stress signals across food, fuel, energy, employment, finance, trade, procurement and supply chains. This is not a live market feed or a composite economic forecast.",
  "terms":("inflation","GDP","gross domestic product","labour market","labor market","employment","unemployment","earnings","vacancies","redundancies","house price","house prices","new dwellings","construction output","retail sales","business investment","business activity","economic activity","consumer confidence","mortgages","rental market","private renters","rent increases","credit conditions","bank rate","bank lending","banking","insolvency","bankruptcy","household debt","benefit claims","universal credit","trade deficit","trade surplus","price rises","price inflation","cost of living","food price","food prices","food supply","shortage","scarcity","fuel price","fuel prices","fuel shortage","energy price","energy prices","energy bills","gas price","oil price","redundancy","liquidation","credit","interest rate","trade","imports","exports","supply chain","freight","fertiliser","fertilizer","grain","procurement","contract award","economic stress"),
  "types":("economic_data","financial_data","procurement_data","alternative_financial_media","government_department","independent_investigative")
 },
 "digital": {
  "name":"Digital Infrastructure",
  "desc":"Cyber advisories, exploited vulnerabilities, telecoms, internet routing and local power/water dependencies. A vulnerability listing does not mean a local system is affected.",
  "terms":("cyber","ransomware","malware","vulnerability","cve-","data breach","phishing","ddos","botnet","telecom","broadband","internet outage","mobile network","data centre","datacenter","subsea cable","undersea cable","cloudflare","ripe atlas","power outage","electricity outage","water outage","nie networks","ni water"),
  "types":("cyber_security_advisory","electricity_network_outage","utility_service_update","telecommunications","cyber_security","social_network")
 },
 "independent": {
  "name":"Independent Media",
  "desc":"Investigative, regional, specialist and independent newsroom reporting. Editorial reporting is kept distinct from official notices and social posts.",
  "terms":("investigation","exclusive","investigative","the detail","belfastlive","the ferret","byline times","opendemocracy","declassified","crisis group","responsible statecraft","war on the rocks","statewatch"),
  "types":("independent_media","independent_investigative","investigative_media","regional_newsroom","national_newsroom","independent_research")
 }
}

TRUST = {
 "official_primary_source":("A","Official / primary"),
 "established_media":("B","Established newsroom"),
 "independent_investigative":("B","Independent investigative"),
 "independent_media":("B","Independent newsroom"),
 "independent_specialist":("C","Specialist publisher"),
 "independent_commentary":("D","Commentary"),
 "alternative_commentary":("D","Alternative commentary"),
 "alternative_media":("D","Alternative media"),
 "alternative_financial_media":("D","Alternative financial commentary"),
 "advocacy_source":("C","Advocacy organisation"),
 "independent_research":("B","Independent research"),
 "third_party_aggregator":("C","Third-party aggregator"),
 "unverified_social":("E","Unverified social"),
 "unverified_community":("E","Unverified community"),
 "mixed_media":("C","Mixed media"),
 "curated_alternative":("D","Curated alternative"),
 "unclassified":("U","Unclassified")
}

SOURCE_DIRECTORY = [
 {"id":"copernicus-stac","flow":"osint","name":"Copernicus Data Space / STAC","url":"https://stac.dataspace.copernicus.eu/v1/","method":"Public STAC catalogue search","access":"No API key for catalogue discovery; imagery processing/download may require account or separate service access.","status":"automated"},
 {"id":"gdacs","flow":"osint","name":"Global Disaster Alert and Coordination System","url":"https://www.gdacs.org/","method":"Public API already collected by the main archive","access":"Event alert metadata; check national/local authorities for ground truth.","status":"existing"},
 {"id":"opensky","flow":"osint","name":"OpenSky Network","url":"https://openskynetwork.github.io/opensky-api/","method":"REST API","access":"OAuth2 client credentials required from 18 March 2026; no anonymous automation configured.","status":"access-limited"},
 {"id":"marinetraffic","flow":"osint","name":"MarineTraffic","url":"https://www.marinetraffic.com/","method":"Commercial AIS platform","access":"Commercial access; no scraping or paid key configured.","status":"commercial"},
 {"id":"reddit","flow":"community","name":"Reddit Data API","url":"https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki","method":"Official API only","access":"Explicit developer approval and OAuth required; not bypassed or scraped.","status":"approval-required"},
 {"id":"telegram","flow":"community","name":"Telegram public channels","url":"https://telegram.org/","method":"Selected public channel review","access":"No private or closed groups; no broad automated collection configured.","status":"manual-review"},
 {"id":"mastodon","flow":"community","name":"Mastodon public instances","url":"https://joinmastodon.org/","method":"Instance-specific public API / RSS","access":"Instance and account list must be selected; not a single global firehose.","status":"connector-required"},
 {"id":"lemmy","flow":"community","name":"Lemmy public communities","url":"https://join-lemmy.org/","method":"Instance-specific community feeds","access":"Community and instance selection required.","status":"connector-required"},
 {"id":"zero-hedge","flow":"fringe","name":"Zero Hedge","url":"https://www.zerohedge.com/","method":"RSS candidate in source register","access":"Commentary; verify factual claims against primary evidence.","status":"candidate"},
 {"id":"offguardian","flow":"fringe","name":"OffGuardian","url":"https://off-guardian.org/","method":"RSS candidate in source register","access":"Alternative commentary; high scrutiny required.","status":"candidate"},
 {"id":"daily-sceptic","flow":"fringe","name":"The Daily Sceptic","url":"https://dailysceptic.org/","method":"RSS candidate in source register","access":"Commentary; distinguish opinion from sourced reporting.","status":"candidate"},
 {"id":"the-expose","flow":"fringe","name":"The Exposé","url":"https://expose-news.com/","method":"Manual review; automated RSS endpoint returned HTTP 403","access":"Publisher retained for manual reading; automated feed polling paused after repeated access denial.","status":"manual-review"},
 {"id":"uk-column","flow":"fringe","name":"UK Column","url":"https://www.ukcolumn.org/","method":"Manual review / source register","access":"No automatic collection unless a stable feed is verified.","status":"manual-review"},
 {"id":"ons","flow":"economic","name":"Office for National Statistics","url":"https://www.ons.gov.uk/releasecalendar","method":"Official published-release RSS in main collector","access":"Release metadata and headlines; numeric series are not imported here.","status":"existing"},
 {"id":"nisra","flow":"economic","name":"NISRA","url":"https://www.nisra.gov.uk/upcoming-releases","method":"Official upcoming-release listing in main collector","access":"NI statistical release metadata; numeric series are not imported here.","status":"existing"},
 {"id":"boe","flow":"economic","name":"Bank of England","url":"https://www.bankofengland.co.uk/boeapps/database/","method":"Official statistical database","access":"Time-series definitions and revisions must be retained; not yet imported as a numeric series.","status":"directory"},
 {"id":"faostat","flow":"economic","name":"FAOSTAT","url":"https://www.fao.org/faostat/","method":"Open statistical database","access":"Global food/agriculture series; release lags mean it is not a live shortage detector.","status":"directory"},
 {"id":"elexon","flow":"economic","name":"Elexon data portal","url":"https://www.elexon.co.uk/operations-settlement/balancing-mechanism-reporting-agent/","method":"Market and balancing data portal","access":"API credentials/terms and field mapping must be checked before automated ingestion.","status":"directory"},
 {"id":"companies-house","flow":"economic","name":"Companies House API","url":"https://developer.company-information.service.gov.uk/","method":"Official API","access":"API key required; company distress indicators need careful interpretation.","status":"access-limited"},
 {"id":"find-a-tender","flow":"economic","name":"Find a Tender / OCDS","url":"https://www.find-tender.service.gov.uk/","method":"Public OCDS release-package API","access":"Public procurement notices; a contract notice is not evidence of supply failure.","status":"directory"},
 {"id":"cisa-kev","flow":"digital","name":"CISA Known Exploited Vulnerabilities","url":"https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json","method":"Public JSON snapshot","access":"No API key; catalogue describes known exploited vulnerabilities globally, not local compromise.","status":"automated"},
 {"id":"ncsc","flow":"digital","name":"UK National Cyber Security Centre","url":"https://www.ncsc.gov.uk/section/keep-up-to-date/reports-advisories","method":"RSS already collected by main archive","access":"Official cyber advisories; does not imply local impact.","status":"existing"},
 {"id":"cloudflare","flow":"digital","name":"Cloudflare Radar","url":"https://radar.cloudflare.com/","method":"Public dashboards / API","access":"API token required for automated API access; public dashboard used as reference only.","status":"directory"},
 {"id":"ripe","flow":"digital","name":"RIPE Atlas","url":"https://atlas.ripe.net/","method":"Public measurement platform / API","access":"Measurement IDs and probe geography are required for meaningful monitoring.","status":"directory"},
 {"id":"nie","flow":"digital","name":"NIE Networks faults","url":"https://nienetworks.opendatasoft.com/explore/dataset/nie-networks-network-faults/","method":"Open data API already collected by main archive","access":"Operator-reported outages; snapshot and geographic scope may lag live operational status.","status":"existing"},
 {"id":"niwater","flow":"digital","name":"Northern Ireland Water service updates","url":"https://www.niwater.com/whats-happening-in-your-area/current-service-updates/","method":"Official service updates already collected by main archive","access":"Operator notices; absence of a notice is not proof of no disruption.","status":"existing"},
 {"id":"detail","flow":"independent","name":"The Detail","url":"https://thedetail.tv/","method":"Publisher website / manual review","access":"Regional investigative reporting; feed endpoint not assumed until verified.","status":"manual-review"},
 {"id":"belfastlive","flow":"independent","name":"Belfast Live","url":"https://www.belfastlive.co.uk/","method":"RSS already in main feed register","access":"Regional reporting; corroborate significant claims.","status":"existing"},
 {"id":"ferret","flow":"independent","name":"The Ferret","url":"https://www.theferret.scot/","method":"Publisher website / feed discovery","access":"Investigative journalism; no unverified RSS endpoint hard-coded.","status":"manual-review"},
 {"id":"byline","flow":"independent","name":"Byline Times","url":"https://bylinetimes.com/","method":"Publisher website / feed discovery","access":"Investigative journalism; no unverified RSS endpoint hard-coded.","status":"manual-review"},
 {"id":"opendemocracy","flow":"independent","name":"openDemocracy","url":"https://www.opendemocracy.net/","method":"RSS candidate in source register","access":"Investigative and accountability reporting; verify claims against documents.","status":"candidate"},
 {"id":"declassified","flow":"independent","name":"Declassified UK","url":"https://declassifieduk.org/","method":"RSS candidate in source register","access":"Defence and foreign-policy investigations; distinguish reporting from analysis.","status":"candidate"},
 {"id":"crisisgroup","flow":"independent","name":"International Crisis Group","url":"https://www.crisisgroup.org/rss.xml","method":"Public RSS","access":"Conflict analysis and reporting; not an operational warning service.","status":"candidate"},
 {"id":"responsible-statecraft","flow":"independent","name":"Responsible Statecraft","url":"https://responsiblestatecraft.org/feed/","method":"Public RSS","access":"Foreign-policy analysis; treat as commentary and compare with primary sources.","status":"candidate"}
]

def utc_now():
 return datetime.now(timezone.utc)

def iso(dt=None):
 return (dt or utc_now()).isoformat(timespec="seconds").replace("+00:00","Z")

def load(path, default):
 try:
  return json.loads(path.read_text(encoding="utf-8"))
 except Exception:
  return default

def fetch_json(url, method="GET", payload=None):
 data = json.dumps(payload).encode("utf-8") if payload is not None else None
 req = urllib.request.Request(url, data=data, method=method, headers={
  "User-Agent":UA, "Accept":"application/json",
  "Content-Type":"application/json" if data else "application/json"
 })
 with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
  raw=response.read(4_000_000)
 return json.loads(raw.decode("utf-8-sig", errors="replace"))

def source_grade(article):
 trust=str(article.get("sourceTrust") or article.get("trust") or "unclassified").lower()
 return TRUST.get(trust, TRUST["unclassified"])

def flow_match(article, flow):
 text=" ".join(str(article.get(k) or "") for k in ("title","description","summary","source","sourceType","sourceTrust","domain","region")).lower()
 source_type=str(article.get("sourceType") or "").lower()
 source_trust=str(article.get("sourceTrust") or "").lower()
 if flow=="community":
  if ("social" in source_type or "community" in source_type or source_trust in ("unverified_social","unverified_community")):
   return True
  if source_type in ("regional_newsroom","national_newsroom") and any(x in text for x in ("ballyclare","newtownabbey","belfast","antrim","larne","derry","northern ireland")):
   return True
  return False
 if flow=="fringe":
  if source_trust in ("alternative_commentary","independent_commentary","curated_alternative") or source_type in ("alternative_media","alternative_financial_media","independent_commentary","preparedness_media","curated_alternative"):
   return True
  if source_trust in ("unverified_social","unverified_community") and any(x in text for x in ("rumour","rumor","disinformation","conspiracy","unverified claim","influence operation","emerging narrative","fringe narrative")):
   return True
  return False
 if flow=="independent":
  named_independent=any(x in text for x in ("the detail","the ferret","byline times","opendemocracy","declassified uk","bellingcat","international crisis group","responsible statecraft"))
  if (source_trust in ("independent_investigative","independent_media","independent_research") and any(x in text for x in ("investigation","exclusive","belfast","northern ireland","declassified","opendemocracy","crisis group","ferret","byline","the detail"))) or named_independent:
   return True
  return False
 if flow=="digital" and any(x in text for x in FLOW_DEFS[flow]["terms"]):
  return True
 if flow=="economic" and any(x in text for x in FLOW_DEFS[flow]["terms"]):
  return True
 if flow=="osint" and any(x in text for x in FLOW_DEFS[flow]["terms"]):
  return True
 if any(x in text for x in FLOW_DEFS[flow]["terms"]):
  return True
 return False

def normalize_record(a, flow):
 grade,label=source_grade(a)
 url=str(a.get("url") or "")
 if not url.startswith(("http://","https://")): url=""
 status=str(a.get("evidenceStatus") or "UNASSESSED").upper()
 return {
  "id":str(a.get("id") or (a.get("sourceId","") + ":" + str(a.get("title",""))))[:500],
  "flow":flow,
  "title":str(a.get("title") or "Untitled signal")[:320],
  "summary":str(a.get("description") or a.get("summary") or "")[:1400],
  "source":str(a.get("source") or a.get("sourceId") or "Source not specified")[:180],
  "sourceId":str(a.get("sourceId") or ""),
  "sourceType":str(a.get("sourceType") or "unclassified"),
  "sourcePriority":str(a.get("priority") or "medium").upper(),
  "sourceTrust":str(a.get("sourceTrust") or "unclassified"),
  "reliabilityGrade":grade,
  "reliabilityLabel":label,
  "evidenceStatus":status,
  "claimConfidence":a.get("confidence") if isinstance(a.get("confidence"),(int,float)) else None,
  "region":str(a.get("region") or a.get("area") or "Not stated")[:120],
  "publishedAt":str(a.get("publishedAt") or a.get("collectedAt") or ""),
  "collectedAt":str(a.get("collectedAt") or ""),
  "url":url,
  "recordKind":"ARCHIVE_SIGNAL"
 }


def normalize_fringe_record(article):
    trust = str(article.get("sourceTrust") or article.get("trust") or "").strip().upper()
    if "CLAIM-LED" in trust or "UNVERIFIED" in trust or "ALTERNATIVE HISTORY" in trust:
        grade, label = "D", "Claim-led / alternative commentary"
    elif "AGGREGATED" in trust:
        grade, label = "C", "News search aggregator"
    elif "DOCUMENT-LED" in trust:
        grade, label = "B", "Document-led specialist archive"
    elif any(term in trust for term in ("SPECIALIST", "SCEPTICAL", "INDEPENDENT", "MAINSTREAM", "PUBLIC BROADCASTER", "REGIONAL NEWS", "NEWSPAPER")):
        grade, label = "B", "Specialist / established publisher"
    else:
        grade, label = "U", "Unclassified"
    url = str(article.get("url") or "")
    if not url.startswith(("http://", "https://")):
        url = ""
    source_id = str(article.get("sourceId") or "")
    return {
        "id": "fringe-rss:" + str(article.get("id") or (source_id + ":" + url))[:480],
        "flow": "fringe", "title": str(article.get("title") or "Untitled fringe feed item")[:320],
        "summary": str(article.get("description") or article.get("summary") or "")[:1400],
        "source": str(article.get("source") or article.get("publisher") or source_id or "Source not specified")[:180],
        "sourceId": source_id, "sourceType": str(article.get("sourceClass") or "fringe RSS"),
        "sourcePriority": "MEDIUM", "sourceTrust": trust or "UNCLASSIFIED",
        "reliabilityGrade": grade, "reliabilityLabel": label,
        "evidenceStatus": "UNASSESSED", "claimConfidence": None,
        "region": str(article.get("region") or "GLOBAL")[:120],
        "publishedAt": str(article.get("publishedAt") or article.get("collectedAt") or ""),
        "collectedAt": str(article.get("collectedAt") or ""), "url": url,
        "recordKind": "FRINGE_RSS", "category": str(article.get("category") or "")
    }


def collect_cisa():
 url="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
 payload=fetch_json(url)
 rows=payload.get("vulnerabilities",[]) if isinstance(payload,dict) else []
 cutoff=(utc_now()-timedelta(days=21)).date().isoformat()
 out=[]
 for v in rows:
  if not isinstance(v,dict) or str(v.get("dateAdded",""))<cutoff: continue
  cve=str(v.get("cveID","")).strip()
  if not cve: continue
  out.append({
   "id":"cisa-kev:"+cve,"flow":"digital",
   "title":cve+" — "+str(v.get("vulnerabilityName") or v.get("product") or "Known exploited vulnerability"),
   "summary":str(v.get("shortDescription") or "")[:1200]+" Required action: "+str(v.get("requiredAction") or "")[:500],
   "source":"CISA Known Exploited Vulnerabilities",
   "sourceId":"cisa-kev","sourceType":"cyber_security_advisory","sourceTrust":"official_primary_source",
   "reliabilityGrade":"A","reliabilityLabel":"Official / primary",
   "evidenceStatus":"OFFICIAL_CATALOGUE_ENTRY","claimConfidence":None,
   "region":"Global — applicability must be assessed locally",
   "publishedAt":str(v.get("dateAdded") or ""),
   "collectedAt":iso(),
   "url":"https://nvd.nist.gov/vuln/detail/"+cve,
   "recordKind":"CISA_KEV",
   "cve":cve,"vendor":str(v.get("vendorProject") or ""),
   "product":str(v.get("product") or ""),
   "dueDate":str(v.get("dueDate") or ""),
   "ransomwareUse":str(v.get("knownRansomwareCampaignUse") or "Unknown")
  })
 return out,{"id":"cisa-kev","name":"CISA KEV catalogue","status":"OK","checkedAt":iso(),"articleCount":len(out),"catalogVersion":payload.get("catalogVersion"),"dateReleased":payload.get("dateReleased")}

def collect_copernicus():
 now=utc_now()
 start=(now-timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
 end=now.strftime("%Y-%m-%dT%H:%M:%SZ")
 url="https://stac.dataspace.copernicus.eu/v1/search?"+urlencode({
  "collections":"sentinel-1-grd",
  "bbox":"-8,49,2,61",
  "datetime":start+"/"+end,
  "limit":"18"
 })
 payload=fetch_json(url)
 features=payload.get("features",[]) if isinstance(payload,dict) else []
 out=[]
 for f in features:
  props=f.get("properties") or {}
  ident=str(f.get("id") or "")
  if not ident: continue
  geom=f.get("geometry") or {}
  coords=geom.get("coordinates") or []
  out.append({
   "id":"copernicus:"+ident,"flow":"osint",
   "title":"Sentinel-1 catalogue item — "+ident[:180],
   "summary":"Earth-observation catalogue metadata only. Collection: "+str(f.get("collection") or "sentinel-1-grd")+". Acquired: "+str(props.get("datetime") or props.get("start_datetime") or "not stated")+". This record does not interpret the image or establish an incident.",
   "source":"Copernicus Data Space Ecosystem / Sentinel-1",
   "sourceId":"copernicus-stac","sourceType":"satellite_observation","sourceTrust":"official_primary_source",
   "reliabilityGrade":"A","reliabilityLabel":"Official catalogue metadata",
   "evidenceStatus":"OBSERVATION_CATALOGUE_METADATA","claimConfidence":None,
   "region":"UK / Ireland bounding box — item geometry must be checked",
   "publishedAt":str(props.get("datetime") or props.get("start_datetime") or ""),
   "collectedAt":iso(),
   "url":"https://browser.stac.dataspace.copernicus.eu/collections/sentinel-1-grd/items/"+ident,
   "recordKind":"SATELLITE_CATALOGUE",
   "collection":str(f.get("collection") or "sentinel-1-grd"),
   "bbox":f.get("bbox")
  })
 return out,{"id":"copernicus-stac","name":"Copernicus STAC Sentinel-1 catalogue","status":"OK","checkedAt":iso(),"articleCount":len(out),"windowDays":5,"note":"Metadata only; no imagery interpretation."}

def build():
 archive=load(ARCHIVE,{})
 source_register=load(SOURCES,{"sources":[]})
 fringe_archive=load(FRINGE_ARCHIVE,{})
 fringe_source_register=load(FRINGE_SOURCES,{"sources":[]})
 articles=archive.get("articles",[]) if isinstance(archive,dict) else []
 fringe_articles=fringe_archive.get("articles",[]) if isinstance(fringe_archive,dict) else []
 statuses=[]
 api_records=[]
 try:
  records,status=collect_cisa();api_records.extend(records);statuses.append(status)
 except Exception as e:
  statuses.append({"id":"cisa-kev","name":"CISA KEV catalogue","status":"FAILED","checkedAt":iso(),"error":str(e)[:260],"articleCount":0})
 try:
  records,status=collect_copernicus();api_records.extend(records);statuses.append(status)
 except Exception as e:
  statuses.append({"id":"copernicus-stac","name":"Copernicus STAC Sentinel-1 catalogue","status":"FAILED","checkedAt":iso(),"error":str(e)[:260],"articleCount":0})
 flows={}
 all_records=[]
 fringe_directory=[]
 for source in fringe_source_register.get("sources",[]):
  enabled=source.get("enabled",True) is not False
  fringe_directory.append({"id":source.get("id"),"flow":"fringe","name":source.get("name"),"url":source.get("url"),"method":"RSS feed" if enabled else "Manual review / automation paused","access":source.get("description") or source.get("disabledReason") or "See publisher website.","status":"automated" if enabled else "manual-review"})
 source_directory=SOURCE_DIRECTORY+fringe_directory
 for key,definition in FLOW_DEFS.items():
  archive_selected=[normalize_record(a,key) for a in articles if isinstance(a,dict) and flow_match(a,key)]
  api_selected=[r for r in api_records if r.get("flow")==key]
  fringe_selected=[normalize_fringe_record(a) for a in fringe_articles if isinstance(a,dict)] if key=="fringe" else []
  unique={}
  for r in archive_selected+api_selected+fringe_selected:
   unique[r.get("url") or r["id"]]=r
  api_kept=[r for r in unique.values() if r.get("recordKind") in ("CISA_KEV","SATELLITE_CATALOGUE")]
  fringe_kept=[r for r in unique.values() if r.get("recordKind")=="FRINGE_RSS"]
  archive_kept=[r for r in unique.values() if r.get("recordKind") not in ("CISA_KEV","SATELLITE_CATALOGUE","FRINGE_RSS")]
  archive_kept.sort(key=lambda x:x.get("publishedAt") or x.get("collectedAt") or "",reverse=True)
  fringe_kept.sort(key=lambda x:x.get("publishedAt") or x.get("collectedAt") or "",reverse=True)
  if key=="fringe":
   records=api_kept+fringe_kept[:max(0,MAX_RECORDS-len(api_kept))]
   records+=archive_kept[:max(0,MAX_RECORDS-len(records))]
  else:
   records=api_kept+archive_kept[:max(0,MAX_RECORDS-len(api_kept))]
  records.sort(key=lambda x:x.get("publishedAt") or x.get("collectedAt") or "",reverse=True)
  source_ids=set(r["sourceId"] for r in records if r.get("sourceId"))
  directory=[s for s in source_directory if s["flow"]==key]
  registry=[s for s in source_register.get("sources",[]) if isinstance(s,dict) and (
   s.get("id") in source_ids or
   (key=="community" and ("social" in str(s.get("type","")) or "community" in str(s.get("type","")))) or
   (key=="fringe" and ("alternative" in str(s.get("type","")) or "alternative" in str(s.get("trust","")))) or
   (key=="independent" and ("independent" in str(s.get("trust","")) or "investigative" in str(s.get("type",""))))
  )]
  flows[key]={
   "id":key,"name":definition["name"],"description":definition["desc"],
   "recordCount":len(records),"sourceCount":len(source_ids),
   "feedRecordCount":sum(1 for r in records if r.get("recordKind")=="FRINGE_RSS"),
   "records":records,"directory":directory,
   "registeredSources":[{"id":s.get("id"),"name":s.get("name"),"url":s.get("url"),"endpoint":s.get("endpoint"),"method":s.get("method"),"status":s.get("status"),"trust":s.get("trust"),"notes":s.get("notes")} for s in registry[:50]]
  }
  all_records.extend(records)
 total_sources=len({r.get("sourceId") for r in all_records if r.get("sourceId")})
 statuses.extend([s for s in archive.get("sourceStatus",[]) if isinstance(s,dict)])
 for source in fringe_archive.get("sources",[]):
  if isinstance(source,dict): statuses.append({**source,"id":"fringe:"+str(source.get("id") or "unknown"),"name":source.get("name") or source.get("id"),"status":source.get("status","UNKNOWN")})
 data={
  "schemaVersion":1,
  "generatedAt":iso(),
  "archiveLastRun":archive.get("collector",{}).get("lastRun") or archive.get("collectorLastRun"),
  "fringeLastRun":fringe_archive.get("collectorLastRun") or fringe_archive.get("updatedAt"),
  "archiveRecordCount":len(articles),
  "flowCount":len(flows),
  "totalFlowRecords":sum(x["recordCount"] for x in flows.values()),
  "uniqueSourceCount":total_sources,
  "collectorStatus":statuses,
  "flows":flows,
  "sourceDirectory":source_directory,
  "methodology":{
   "reliability":"A official primary source/catalogue; B established newsroom or independent research; C specialist, advocacy or aggregator; D alternative commentary; E unverified social/community; U unclassified. Grade describes source class, not the truth of a specific claim.",
   "confidence":"Claim confidence is left unassessed unless an upstream collector supplies a numeric value. Source grade is not claim confidence.",
   "corroboration":"The six views reuse the existing archive. Similar stories, repeated posts, syndicated copy or multiple outlets quoting one origin are not independent corroboration. A human must inspect provenance.",
   "geolocation":"Location is shown only when supplied by the source or upstream archive. No location is inferred from a headline.",
   "limits":"This is open-source situational awareness, not intelligence agency coverage, an emergency warning service, a live market terminal or a verified threat assessment."
  }
 }
 DATA.mkdir(parents=True,exist_ok=True)
 OUTPUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Observatory snapshot written:",OUTPUT)
 print("Flows:",len(flows),"records:",data["totalFlowRecords"],"unique sources:",total_sources)
 for key,flow in flows.items(): print(key,flow["recordCount"],"records",flow["sourceCount"],"sources")
 for status in statuses: print(status["id"],status["status"],status["articleCount"])

if __name__=="__main__":
 build()
