(()=>{"use strict";
if(window.__doomwatchUiReady)return;window.__doomwatchUiReady=true;
const body=document.body,oldHeader=body.querySelector(":scope > header"),oldNav=body.querySelector(":scope > nav");
const path=location.pathname.toLowerCase(),hash=decodeURIComponent(location.hash.slice(1)).toLowerCase();
if((path==="/"||path.endsWith("/index.html"))&&!hash){location.replace("./map.html");return;}
const routes=[
 ["map","map.html","MAP"],["feed","feed.html","FEED"],["operations","operations.html","OPS"],["communications","communications.html","COMMS"],
 ["command","index.html#overview","COMMAND"],["intelligence","index.html#intelligence","INTEL"],["sectors","index.html#sections","11 SECTORS"],
 ["preparedness","index.html#preparedness","PREP"],["meshcore","index.html#meshcore","MESHCORE"],["markets","markets.html","MARKETS"],
 ["household","household.html","HOUSEHOLD"],
 ["incident","incident.html","CASE FILE"],["backup","index.html#backup-centre","BACKUP"],["sources","index.html#sources","SOURCES"]
];
const active=path.endsWith("/operations.html")?"operations":path.endsWith("/markets.html")?"markets":path.endsWith("/household.html")?"household":path.endsWith("/feed.html")?"feed":path.endsWith("/map.html")?"map":path.endsWith("/communications.html")?"communications":path.endsWith("/incident.html")?"incident":path.endsWith("/meshcore.html")?"meshcore":({intelligence:"intelligence",sections:"sectors",preparedness:"preparedness",meshcore:"meshcore",sources:"sources","backup":"backup"})[hash]||"command";
const mast=document.createElement("header");mast.className="dw-masthead";
mast.innerHTML='<div class="dw-brand"><img class="dw-emblem" src="./containment.svg" alt="DoomWatch red containment unit emblem"><div><div class="dw-wordmark">DOOMWATCH</div><div class="dw-tagline">OPERATION CONTAINMENT // RESILIENCE INTELLIGENCE</div><div class="dw-statusline" id="dw-statusline"></div></div></div><div class="dw-hardware" aria-hidden="true"><div class="dw-statusbox"><strong>CONTAINMENT SYSTEM</strong><span>POWER / FIELD UNIT</span><div class="dw-lamps"><i class="dw-lamp red"></i><i class="dw-lamp amber"></i><i class="dw-lamp green"></i></div></div><div class="dw-valves"><i class="dw-valve red"></i><i class="dw-valve"></i></div><div class="dw-switches"><i class="dw-switch on"></i><i class="dw-switch"></i></div></div>';
body.insertBefore(mast,body.firstChild);
const statusline=mast.querySelector("#dw-statusline");
["clock","connection","updated"].forEach(id=>{const node=document.getElementById(id);if(node){const wrap=document.createElement("span");wrap.appendChild(node);statusline.appendChild(wrap);}});
if(oldHeader)oldHeader.hidden=true;
const nav=document.createElement("nav");nav.className="dw-global-nav";nav.setAttribute("aria-label","All DoomWatch pages and sections");
let areaToggle=null;
routes.forEach(([key,url,label],index)=>{
 if(index===4){
  areaToggle=document.createElement("button");areaToggle.type="button";areaToggle.className="dw-nav-toggle";areaToggle.textContent="ALL AREAS +";areaToggle.setAttribute("aria-expanded","false");areaToggle.setAttribute("aria-controls","dw-route-extras");nav.appendChild(areaToggle);
 }
 const a=document.createElement("a");
 a.href=new URL(url,document.baseURI).href;
 a.textContent=label;
 a.className=index<4?"dw-route-primary":"dw-route-extra";
 if(index>=4)a.dataset.dwExtra="true";
 if(key===active){a.setAttribute("aria-current","page");}
 nav.appendChild(a);
});
const extras=document.createElement("span");extras.id="dw-route-extras";extras.className="dw-route-extras";
[...nav.querySelectorAll(".dw-route-extra")].forEach(a=>extras.appendChild(a));
nav.appendChild(extras);
if(areaToggle){
 const setExpanded=expanded=>{nav.classList.toggle("dw-expanded",expanded);areaToggle.setAttribute("aria-expanded",String(expanded));areaToggle.textContent=expanded?"CLOSE AREAS −":"ALL AREAS +";};
 areaToggle.addEventListener("click",()=>setExpanded(!nav.classList.contains("dw-expanded")));
 if(nav.querySelector('[aria-current="page"].dw-route-extra'))setExpanded(true);
}
const expandAll=document.createElement("button");expandAll.type="button";expandAll.className="dw-nav-action";expandAll.textContent="EXPAND SECTIONS";
const collapseAll=document.createElement("button");collapseAll.type="button";collapseAll.className="dw-nav-action";collapseAll.textContent="COLLAPSE SECTIONS";
nav.append(expandAll,collapseAll);
expandAll.addEventListener("click",()=>document.querySelectorAll("details.dw-fold").forEach(el=>el.open=true));
collapseAll.addEventListener("click",()=>document.querySelectorAll("details.dw-fold").forEach(el=>el.open=false));
const skip=document.createElement("a");skip.className="dw-skip-link";skip.href="#dw-main-content";skip.textContent="SKIP TO CONTENT";
const mainForSkip=document.querySelector("main");if(mainForSkip){mainForSkip.id=mainForSkip.id||"dw-main-content";skip.href="#"+mainForSkip.id;}
body.insertBefore(skip,body.firstChild);
// Every page uses this single shared route bar. Page-local section menus are
// intentionally removed: dashboard partitions and standalone modules are
// reached through the same consistent route list above.
if(oldNav)oldNav.remove();
mast.insertAdjacentElement("afterend",nav);
nav.classList.add("dw-bottom-dock");
const wire=document.createElement("div");wire.className="dw-wire";wire.setAttribute("aria-hidden","true");nav.insertAdjacentElement("afterend",wire);
const top=document.createElement("button");top.type="button";top.className="dw-top";top.textContent="TOP";top.setAttribute("aria-label","Back to top");top.addEventListener("click",()=>window.scrollTo({top:0,behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"}));body.appendChild(top);
function foldSection(section,index){
 if(section.closest("details.dw-fold"))return;
 const heading=section.querySelector(":scope > h1,:scope > h2,:scope > h3,:scope h2,:scope h3");
 const label=(heading?.textContent||section.getAttribute("aria-label")||section.id||"SECTION").replace(/\s+/g," ").trim();
 if(!label)return;
 const details=document.createElement("details");details.className="dw-fold";details.dataset.dwFold="true";
 if(index===0)details.open=true;
 const summary=document.createElement("summary");summary.textContent=label;
 const hint=document.createElement("span");hint.className="dw-fold-hint";hint.textContent="COLLAPSE / EXPAND";summary.appendChild(hint);
 section.parentNode.insertBefore(details,section);details.appendChild(summary);details.appendChild(section);
}
function foldHeadingGroups(container){
 if(!container)return;
 const children=[...container.children];
 let groupIndex=0;
 for(let i=0;i<children.length;i++){
  const heading=children[i];
  if(!/^H[23]$/.test(heading.tagName)||heading.closest("details.dw-fold"))continue;
  const block=[heading];let j=i+1;
  while(j<children.length&&!/^H[23]$/.test(children[j].tagName)){block.push(children[j]);j++;}
  if(block.length===1)continue;
  const label=(heading.textContent||"SECTION").replace(/\s+/g," ").trim();
  const details=document.createElement("details");details.className="dw-fold dw-heading-fold";details.dataset.dwFold="true";
  if(groupIndex===0)details.open=true;
  const summary=document.createElement("summary");summary.textContent=label;
  const hint=document.createElement("span");hint.className="dw-fold-hint";hint.textContent="COLLAPSE / EXPAND";summary.appendChild(hint);
  const content=document.createElement("div");content.className="dw-fold-content";
  heading.parentNode.insertBefore(details,heading);
  details.appendChild(summary);details.appendChild(content);
  block.forEach(node=>content.appendChild(node));
  groupIndex++;i=j-1;
 }
}
const main=document.querySelector("main");
if(main){
 let groups=[...main.children].filter(el=>el.tagName==="SECTION"&&!el.classList.contains("page")&&!el.classList.contains("op-hero")&&!el.classList.contains("op-kpis"));
 groups.forEach((el,i)=>foldSection(el,i));
 document.querySelectorAll(".map-box").forEach((el,i)=>foldSection(el,i));
 foldHeadingGroups(main);
 main.querySelectorAll(":scope > .page").forEach(page=>foldHeadingGroups(page));
 document.querySelectorAll(".brief-card,.case-panel").forEach((el,i)=>foldSection(el,i));
}
function openHashTarget(){const id=decodeURIComponent(location.hash.slice(1));if(!id)return;const target=document.getElementById(id);if(!target)return;let parent=target.parentElement;while(parent){if(parent.matches?.("details.dw-fold"))parent.open=true;parent=parent.parentElement;}if(target.matches?.("details.dw-fold"))target.open=true;}
window.addEventListener("hashchange",openHashTarget);openHashTarget();
body.classList.add("dw-ready");

// MESH INTELLIGENCE CORRELATION — screening aid only; never promotes a match to a verified incident.
(function meshCorrelationModule(){
 "use strict";
 const feedRoot=document.getElementById("mesh-feed-list");
 if(!feedRoot || typeof meshFeed==="undefined") return;
 const host=feedRoot.parentElement;
 const panel=document.createElement("section");
 panel.id="mesh-correlation-panel";
 panel.className="panel";
 panel.style.cssText="margin:12px 0;border:1px solid #68755c;background:linear-gradient(145deg,#1b261f,#101611);padding:13px";
 panel.innerHTML='<div class="panel-title">LIVE CORRELATION // MESH × DOOMWATCH INTELLIGENCE</div>'+
 '<div class="muted" style="font-size:11px;line-height:1.5;margin-bottom:10px">Screens possible topic and regional overlaps between locally captured MeshCore messages and the latest collector snapshot. A match is a lead for human review, not proof of the same event, independent corroboration or a confirmed local impact.</div>'+
 '<div id="mesh-corr-stats" class="grid"></div>'+
 '<div class="controls" style="margin:10px 0"><label for="mesh-corr-filter" class="panel-title">CORRELATION VIEW</label><select id="mesh-corr-filter"><option value="all">ALL MESSAGES</option><option value="matched">POTENTIAL MATCHES</option><option value="unmatched">NO MATCH FOUND</option><option value="infrastructure">INFRASTRUCTURE</option><option value="weather">WEATHER</option><option value="transport">TRANSPORT</option></select></div>'+
 '<div id="mesh-corr-timeline" class="intel-window" style="height:auto;max-height:430px;min-height:90px"></div>'+
 '<div class="meta" style="margin-top:8px">METHOD: keyword + broad region + 72-hour window. Publisher names are counted as records only; syndication and copied reports can create false matches. Weather signals are not forecasts. Check original sources before acting.</div>';
 host.insertBefore(panel,feedRoot);
 const $c=id=>document.getElementById(id);
 const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const terms={
  infrastructure:["power","electric","electricity","nie networks","water","ni water","water supply","telecom","broadband","mobile network","outage","blackout","substation","burst main","service disruption"],
  weather:["weather","rain","wind","storm","flood","flooding","snow","ice","warning","met office","yellow warning","amber warning","red warning"],
  transport:["road","traffic","collision","crash","closure","closed","diversion","rail","train","bus","port","airport"," ferry","roadworks"]
 };
 function regionGroup(v){
  const s=String(v||"").toLowerCase();
  if(/bhd|ulster|northern ireland|belfast|antrim|derry|armagh|tyrone|down|fermanagh/.test(s))return "NI";
  if(/ioi|ireland|roi|republic of ireland|leinster|connacht|munster|dub|noc|snn/.test(s))return "IRELAND";
  if(/sco|scotland/.test(s))return "SCOTLAND";
  if(/iom|isle of man|manx/.test(s))return "IOM";
  if(/yorkshire/.test(s))return "YORKSHIRE";
  if(/uk|united kingdom|england|wales|britain|great britain/.test(s))return "UK";
  return "UNKNOWN";
 }
 function dateValue(v){const n=new Date(v||"").getTime();return Number.isFinite(n)?n:0;}
 function messageClass(x){
  const text=[x.category,x.channel,x.message].join(" ").toLowerCase();
  for(const k of Object.keys(terms))if(terms[k].some(t=>text.includes(t)))return k;
  return "general";
 }
 function articleClass(a){
  const text=[a.title,a.summary,a.category,a.source].join(" ").toLowerCase();
  for(const k of Object.keys(terms))if(terms[k].some(t=>text.includes(t)))return k;
  return "general";
 }
 function matchFor(message){
  const msgText=[message.message,message.category,message.channel].join(" ").toLowerCase();
  const cls=messageClass(message),region=regionGroup(message.region);
  const when=dateValue(message.capturedAt||message.time);
  const pool=(Array.isArray(articles)?articles:[]);
  const candidates=pool.map(a=>{
   const aText=[a.title,a.summary,a.category,a.source].join(" ").toLowerCase();
   const ac=articleClass(a),ar=regionGroup(a.region||a.area);
   const topic=cls==="general" ? (msgText.split(/\W+/).filter(w=>w.length>4).some(w=>aText.includes(w))) : ac===cls;
   const sameRegion=region==="UNKNOWN"||ar==="UNKNOWN"||region===ar||
    (region==="NI"&&ar==="UK")||(region==="IRELAND"&&ar==="NI");
   const at=dateValue(a.date);
   const timely=!when||!at||Math.abs(when-at)<=72*60*60*1000;
   const matched=topic&&sameRegion&&timely;
   return {a,matched,topic,sameRegion,timely,at};
  }).filter(x=>x.matched).sort((a,b)=>b.at-a.at).slice(0,4);
  return {cls,region,candidates};
 }
 function render(){
  const records=(Array.isArray(meshFeed)?meshFeed:[]);
  const results=records.map((x,i)=>({x,i,...matchFor(x)}));
  const matches=results.filter(x=>x.candidates.length);
  const infra=results.filter(x=>x.cls==="infrastructure").length;
  const weather=results.filter(x=>x.cls==="weather").length;
  const transport=results.filter(x=>x.cls==="transport").length;
  $c("mesh-corr-stats").innerHTML=[
   ["CAPTURED MESSAGES",records.length],["POTENTIAL MATCHES",matches.length],
   ["INFRASTRUCTURE LEADS",infra],["WEATHER / TRANSPORT",weather+" / "+transport]
  ].map(([label,value])=>'<div class="panel"><div class="panel-title">'+esc(label)+'</div><div class="big-status yellow">'+esc(value)+'</div></div>').join("");
  const filter=$c("mesh-corr-filter").value;
  const shown=results.filter(r=>{
   if(filter==="matched")return r.candidates.length>0;
   if(filter==="unmatched")return r.candidates.length===0;
   if(["infrastructure","weather","transport"].includes(filter))return r.cls===filter;
   return true;
  }).sort((a,b)=>dateValue(b.x.capturedAt||b.x.time)-dateValue(a.x.capturedAt||a.x.time));
  $c("mesh-corr-timeline").innerHTML=shown.length?shown.map(r=>{
   const x=r.x,match=r.candidates.length,sourceNames=[...new Set(r.candidates.map(c=>c.a.source).filter(Boolean))];
   const state=match?"POTENTIAL CROSS-SOURCE LEAD":"NO MATCH IN CURRENT SNAPSHOT";
   const cls=r.cls==="infrastructure"?"INFRASTRUCTURE":r.cls.toUpperCase();
   const links=r.candidates.map(c=>{
    const url=typeof safeURL==="function"?safeURL(c.a.url):"";
    return '<div class="meta" style="margin-top:7px"><strong>'+esc(c.a.title||"Untitled intelligence record")+'</strong> // '+esc(c.a.source||"Source unspecified")+' // '+esc(c.a.date?new Date(c.a.date).toLocaleString():"Date unavailable")+(url?' // <a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">ORIGINAL SOURCE ↗</a>':"")+'</div>';
   }).join("");
   return '<article class="intel-card '+(match?"medium":"unassessed")+'"><h3>'+esc(cls)+' // '+esc(state)+'</h3><div class="meta">'+esc((x.region||"Region unknown").toUpperCase())+' · '+esc(x.channel||"Channel not recorded")+' · '+esc(x.author||"Unattributed")+' · '+esc(x.capturedAt?new Date(x.capturedAt).toLocaleString():x.time||"Time unavailable")+'</div><p>'+esc(x.message||"")+'</p><div class="meta">SOURCE LABEL: '+esc(x.confidence||"Unverified")+' · POSSIBLE MATCHES: '+match+' · PUBLISHER NAMES: '+esc(sourceNames.length||0)+'</div>'+(match?'<div class="meta"><strong>REVIEW THESE RECORDS — NOT VERIFIED AS THE SAME EVENT</strong></div>'+links:'<div class="meta">No matching record found in the current collector snapshot. This does not mean the report is false.</div>')+'</article>';
  }).join(""):'<div class="mesh-empty">No messages match this view. Import a public-room message to begin correlation.</div>';
 }
 $c("mesh-corr-filter").addEventListener("change",render);
 const previous=meshRenderFeed;
 if(typeof previous==="function")meshRenderFeed=function(){previous();render();};
 const intel=document.getElementById("intel-feed");
 if(intel&&window.MutationObserver)new MutationObserver(()=>render()).observe(intel,{childList:true,subtree:true});
 render();
})();

})();