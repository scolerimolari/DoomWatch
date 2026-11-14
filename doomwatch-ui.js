(()=>{"use strict";
if(window.__doomwatchUiReady)return;window.__doomwatchUiReady=true;
const body=document.body,oldHeader=body.querySelector(":scope > header"),oldNav=body.querySelector(":scope > nav");
const path=location.pathname.toLowerCase(),hash=decodeURIComponent(location.hash.slice(1)).toLowerCase();
const routes=[
 ["command","index.html#overview","COMMAND"],["operations","operations.html","OPS ROOM"],
 ["intelligence","index.html#intelligence","INTEL"],["sectors","index.html#sections","11 SECTORS"],
 ["preparedness","index.html#preparedness","PREP"],["markets","markets.html","MARKETS"],
 ["household","household.html","HOUSEHOLD"],["feed","feed.html","FEED"],
 ["map","map.html","MAP"],["communications","communications.html","COMMS"],
 ["incident","incident.html","CASE FILE"],["sources","index.html#sources","SOURCES"]
];
const active=path.endsWith("/operations.html")?"operations":path.endsWith("/markets.html")?"markets":path.endsWith("/household.html")?"household":path.endsWith("/feed.html")?"feed":path.endsWith("/map.html")?"map":path.endsWith("/communications.html")?"communications":path.endsWith("/incident.html")?"incident":({intelligence:"intelligence",sections:"sectors",preparedness:"preparedness",sources:"sources"})[hash]||"command";
const mast=document.createElement("header");mast.className="dw-masthead";
mast.innerHTML='<div class="dw-brand"><img class="dw-emblem" src="./containment.svg" alt="DoomWatch red containment unit emblem"><div><div class="dw-wordmark">DOOMWATCH</div><div class="dw-tagline">OPERATION CONTAINMENT // RESILIENCE INTELLIGENCE</div><div class="dw-statusline" id="dw-statusline"></div></div></div><div class="dw-hardware" aria-hidden="true"><div class="dw-statusbox"><strong>CONTAINMENT SYSTEM</strong><span>POWER / FIELD UNIT</span><div class="dw-lamps"><i class="dw-lamp red"></i><i class="dw-lamp amber"></i><i class="dw-lamp green"></i></div></div><div class="dw-valves"><i class="dw-valve red"></i><i class="dw-valve"></i></div><div class="dw-switches"><i class="dw-switch on"></i><i class="dw-switch"></i></div></div>';
body.insertBefore(mast,body.firstChild);
const statusline=mast.querySelector("#dw-statusline");
["clock","connection","updated"].forEach(id=>{const node=document.getElementById(id);if(node){const wrap=document.createElement("span");wrap.appendChild(node);statusline.appendChild(wrap);}});
if(oldHeader)oldHeader.hidden=true;
const nav=document.createElement("nav");nav.className="dw-global-nav";nav.setAttribute("aria-label","All DoomWatch pages and sections");
routes.forEach(([key,url,label])=>{
 const a=document.createElement("a");
 a.href=new URL(url,document.baseURI).href;
 a.textContent=label;
 if(key===active){a.setAttribute("aria-current","page");}
 nav.appendChild(a);
});
// Every page uses this single shared route bar. Page-local section menus are
// intentionally removed: dashboard partitions and standalone modules are
// reached through the same consistent route list above.
if(oldNav)oldNav.remove();
mast.insertAdjacentElement("afterend",nav);
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
function openHashTarget(){const id=decodeURIComponent(location.hash.slice(1));if(!id)return;const target=document.getElementById(id);const fold=target?.closest("details.dw-fold");if(fold)fold.open=true;}
window.addEventListener("hashchange",openHashTarget);openHashTarget();
body.classList.add("dw-ready");
})();