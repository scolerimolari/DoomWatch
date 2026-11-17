#!/usr/bin/env python3
"""DoomWatch static, route, collector-output and data-integrity audit."""
import json, re, sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT=Path(__file__).resolve().parent
PAGES=("index.html","observatory.html","map.html","markets.html","communications.html","meshcore.html","signals.html","operations.html","correlation.html","incident.html","feed.html","household.html")
FLOWS=("osint","community","fringe","economic","digital","independent")
ROUTES=("./index.html","./observatory.html","./map.html","./markets.html","./communications.html")
CORE=("index.html","observatory.html","doomwatch-ui.js","feeds.json","fringe_sources.json","sources.json","map.html","communications.html","markets.html","meshcore.html")
errors=[]; warnings=[]
def fail(message): errors.append(message)
class Parser(HTMLParser):
 def __init__(self): super().__init__(); self.links=[]; self.ids=set()
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if attrs.get("id"): self.ids.add(attrs["id"])
  for key in ("href","src","action"):
   if attrs.get(key): self.links.append(attrs[key])
def read_json(path):
 try:return json.loads((ROOT/path).read_text(encoding="utf-8"))
 except Exception as exc: fail(f"{path}: invalid JSON ({exc})"); return {}
def parsed_time(value):
 try:
  result=datetime.fromisoformat(str(value).replace("Z","+00:00"))
  return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
 except Exception:return None
def freshness(label,value,limit):
 date=parsed_time(value)
 if not date: warnings.append(label+": timestamp unavailable"); return
 age=(datetime.now(timezone.utc)-date).total_seconds()/3600
 print(f"FRESHNESS {label}: {age:.1f}h")
 if age>limit:warnings.append(f"{label}: {age:.1f}h old")
def audit_pages():
 for page in PAGES:
  path=ROOT/page
  if not path.is_file():fail("Missing page: "+page);continue
  parser=Parser();parser.feed(path.read_text(encoding="utf-8"))
  for raw in parser.links:
   raw=raw.strip()
   if not raw or raw.startswith(("#","mailto:","tel:","javascript:","data:","//")):continue
   parts=urlsplit(raw)
   if parts.scheme or not parts.path:continue
   local=unquote(parts.path)
   if local in (".","./"):continue
   target=(ROOT/local.lstrip("/")) if local.startswith("/") else (path.parent/local)
   try:target.resolve().relative_to(ROOT.resolve())
   except ValueError:fail(f"{page}: local link escapes repository: {raw}");continue
   if not target.is_file():fail(f"{page}: broken local link or asset: {raw}")
 shell=(ROOT/"doomwatch-ui.js").read_text(encoding="utf-8")
 for route in ROUTES:
  if route not in shell:fail("Main navigation route missing: "+route)
 text=(ROOT/"index.html").read_text(encoding="utf-8"); p=Parser();p.feed(text)
 for key in ("latest-intelligence","emerging-signals","metric-records","metric-signals","metric-markets","metric-connectivity","service-summary","economy-summary","dw-updated"):
  if key not in p.ids:fail("Command dashboard missing element: "+key)
 if "start().catch\nstart().catch" in text:fail("Duplicate dashboard startup invocation remains")
 css=(ROOT/"doomwatch.css").read_text(encoding="utf-8")
 if "min-height:44px" not in css or "@media(max-width:760px)" not in css:fail("Mobile touch-target or responsive CSS check failed")
 obs=(ROOT/"observatory.html").read_text(encoding="utf-8")
 declared=set(re.findall(r'data-flow="([^"]+)"',obs))
 if declared!=set(FLOWS):fail("Six observatory tabs do not match expected flows")
 print(f"ROUTES: {len(PAGES)} pages checked; five main destinations present")
def audit_bluesky():
 for name in CORE:
  path=ROOT/name
  if path.is_file() and "bluesky" in path.read_text(encoding="utf-8").lower():fail("Bluesky reference remains in active app/config: "+name)
 print("BLUESKY: no active app or source-register references")
def audit_sources():
 feeds=read_json("feeds.json").get("feeds",[])
 config=read_json("fringe_sources.json"); sources=config.get("sources",[])
 register=read_json("sources.json").get("sources",[])
 for label,items in (("main feeds",feeds),("fringe feeds",sources),("source register",register)):
  ids=[x.get("id") for x in items if x.get("id")]
  if len(ids)!=len(set(ids)):fail(label+": duplicate source IDs")
 categories={x.get("category") for x in sources}
 for cat in ("OCCULT, ESOTERIC & CONSPIRACY","UFO / UAP & UNEXPLAINED","ANCIENT CIVILISATIONS & HIDDEN HISTORY"):
  if cat not in categories:fail("Fringe category missing: "+cat)
 disabled={x.get("id") for x in sources if x.get("enabled") is False}
 for item in sources:
  if not str(item.get("url","")).startswith(("http://","https://")):fail("Invalid fringe source URL: "+str(item.get("id")))
 print(f"SOURCES: {len(feeds)} main feeds; {len(sources)} fringe feeds; {len(disabled)} manual-review only")
def audit_data():
 intel=read_json("data/intelligence.json"); articles=intel.get("articles",[])
 if not isinstance(articles,list):fail("Intelligence articles is not a list");articles=[]
 freshness("intelligence archive",intel.get("collector",{}).get("lastRun") or intel.get("updatedAt"),30)
 obs=read_json("data/observatory.json"); flows=obs.get("flows",{})
 if set(flows)!=set(FLOWS):fail("Observatory must contain exactly six flows")
 total=0
 for key in FLOWS:
  flow=flows.get(key,{}); records=flow.get("records",[])
  if not isinstance(records,list):fail(key+": records is not a list");continue
  if flow.get("recordCount")!=len(records):fail(key+": recordCount mismatch")
  for item in records:
   if not item.get("id") or not item.get("title"):fail(key+": record missing id/title")
  total+=len(records)
 if obs.get("totalFlowRecords")!=total:fail("Observatory totalFlowRecords mismatch")
 freshness("observatory snapshot",obs.get("generatedAt"),30)
 fringe=read_json("data/fringe.json"); articles_fringe=fringe.get("articles",[]); statuses=fringe.get("sources",[])
 if not isinstance(articles_fringe,list) or not isinstance(statuses,list):fail("Fringe output has invalid collections");articles_fringe=[];statuses=[]
 disabled_config={x.get("id") for x in read_json("fringe_sources.json").get("sources",[]) if x.get("enabled") is False}
 disabled_status={x.get("id") for x in statuses if x.get("status")=="DISABLED"}
 if not disabled_config.issubset(disabled_status):fail("A manual-review fringe feed was still polled")
 records=flows.get("fringe",{}).get("records",[])
 if articles_fringe and not any(x.get("recordKind")=="FRINGE_RSS" for x in records):fail("Fringe RSS articles are not integrated into the visible Observatory")
 directory={x.get("id") for x in obs.get("sourceDirectory",[])}
 for item in read_json("fringe_sources.json").get("sources",[]):
  if item.get("id") not in directory:fail("Fringe source absent from source register: "+str(item.get("id")))
 freshness("fringe RSS snapshot",fringe.get("collectorLastRun") or fringe.get("updatedAt"),30)
 failed=[x for x in statuses if x.get("status")=="FAILED"]
 if failed:warnings.append(f"{len(failed)} fringe feeds failed; inspect collector health")
 print(f"DATA: {len(articles)} archive; {total} Observatory; {len(articles_fringe)} fringe RSS; {len(failed)} feed failures")
 markets=read_json("data/markets.json")
 if not (markets.get("updatedAt") or markets.get("generatedAt")):fail("Markets timestamp missing")
 if not isinstance(markets.get("commodities"),dict) or not isinstance(markets.get("indices"),dict):fail("Markets groups missing")
 freshness("markets snapshot",markets.get("updatedAt") or markets.get("generatedAt"),30)
 comms=read_json("data/communications.json")
 if not isinstance(comms.get("providers"),list):fail("Communications provider list missing")
 if not isinstance(comms.get("summary"),dict):fail("Communications summary missing")
 freshness("communications snapshot",comms.get("generatedAt"),4)
def main():
 audit_pages();audit_bluesky();audit_sources();audit_data()
 for warning in warnings:print("WARNING:",warning)
 if errors:
  for error in errors:print("FAIL:",error)
  print(f"AUDIT FAILED: {len(errors)} error(s), {len(warnings)} warning(s)");return 1
 print(f"AUDIT PASSED: all structural and data checks passed; {len(warnings)} warning(s)");return 0
if __name__=="__main__":sys.exit(main())
