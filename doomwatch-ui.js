(() => {
"use strict";
if(window.__doomwatchUiReady)return;window.__doomwatchUiReady=true;
const body=document.body,oldHeader=body.querySelector(":scope > header"),oldNav=body.querySelector(":scope > nav"),path=location.pathname.toLowerCase();
const isMarkets=path.endsWith("/markets.html"),isHousehold=path.endsWith("/household.html"),active=isMarkets?"markets":isHousehold?"household":"command";
const mast=document.createElement("header");mast.className="dw-masthead";
mast.innerHTML='<div class="dw-brand"><img class="dw-emblem" src="./containment.svg" alt="DoomWatch red containment unit emblem"><div><div class="dw-wordmark">DOOMWATCH</div><div class="dw-tagline">OPERATION CONTAINMENT // RESILIENCE INTELLIGENCE</div><div class="dw-statusline" id="dw-statusline"></div></div></div><div class="dw-hardware" aria-hidden="true"><div class="dw-statusbox"><strong>CONTAINMENT SYSTEM</strong><span>POWER / FIELD UNIT</span><div class="dw-lamps"><i class="dw-lamp red"></i><i class="dw-lamp amber"></i><i class="dw-lamp green"></i></div></div><div class="dw-valves"><i class="dw-valve red"></i><i class="dw-valve"></i></div></div>';
body.insertBefore(mast,body.firstChild);
const statusline=mast.querySelector("#dw-statusline");
["clock","connection","updated"].forEach(id=>{const node=document.getElementById(id);if(node){const wrap=document.createElement("span");wrap.appendChild(node);statusline.appendChild(wrap);}});
if(oldHeader)oldHeader.hidden=true;
const globalNav=document.createElement("nav");globalNav.className="dw-global-nav";globalNav.setAttribute("aria-label","DoomWatch main navigation");
[["command","./index.html","COMMAND"],["markets","./markets.html","MARKETS"],["household","./household.html","HOUSEHOLD"]].forEach(([key,href,label])=>{const a=document.createElement("a");a.href=href;a.textContent=label;if(key===active)a.setAttribute("aria-current","page");globalNav.appendChild(a);});
mast.insertAdjacentElement("afterend",globalNav);
if(oldNav){if(isHousehold)oldNav.remove();else{oldNav.classList.add("dw-local-nav");oldNav.setAttribute("aria-label",isMarkets?"Markets sections":"Command sections");globalNav.insertAdjacentElement("afterend",oldNav);}}
const wire=document.createElement("div");wire.className="dw-wire";wire.setAttribute("aria-hidden","true");globalNav.insertAdjacentElement("afterend",wire);
const top=document.createElement("button");top.type="button";top.className="dw-top";top.textContent="TOP";top.setAttribute("aria-label","Back to top");top.addEventListener("click",()=>window.scrollTo({top:0,behavior:"smooth"}));body.appendChild(top);
body.classList.add("dw-ready");
})();