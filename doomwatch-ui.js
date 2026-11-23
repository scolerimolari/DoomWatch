(()=>{"use strict";
if(window.__doomwatchShell)return;window.__doomwatchShell=true;
const body=document.body,path=location.pathname.toLowerCase();
const embedMode=new URLSearchParams(location.search).get("embed")==="1";if(embedMode)body.classList.add("dw-embed");
const routes=[
 ["area","./index.html","My Area",["/","/index.html"]],
 ["intelligence","./observatory.html","NI Watch",["/observatory.html","/feed.html","/signals.html","/operations.html"]],
 ["map","./map.html","Map",["/map.html"]],
 ["preparedness","./household.html","Preparedness",["/household.html"]],
 ["economy","./markets.html","Markets",["/markets.html"]],
 ["connectivity","./communications.html","Network",["/communications.html","/meshcore.html"]]
];
const active=routes.find(r=>r[3].some(p=>path.endsWith(p)))||routes[0];
const oldHeader=body.querySelector(":scope > header");if(oldHeader)oldHeader.hidden=true;
document.querySelectorAll(":scope > nav, body > nav").forEach(n=>n.remove());
const mast=document.createElement("header");mast.className="dw-masthead";
mast.innerHTML='<a class="dw-brand" href="./index.html"><img class="dw-emblem" src="./containment.svg" alt=""><span><span class="dw-wordmark">DOOMWATCH NI</span><span class="dw-tagline">LOCAL HAZARDS / INFRASTRUCTURE / INTELLIGENCE</span></span></a><div class="dw-mast-note"><span class="dw-live-dot"></span><span>PUBLIC SOURCES</span><span>/</span><span>FREE-FIRST</span></div>';
const nav=document.createElement("nav");nav.className="dw-global-nav";nav.setAttribute("aria-label","Main navigation");
routes.forEach(r=>{const a=document.createElement("a");a.href=r[1];a.textContent=r[2];if(r===active)a.setAttribute("aria-current","page");nav.appendChild(a);});
body.insertBefore(nav,body.firstChild);body.insertBefore(mast,body.firstChild);body.classList.add("dw-ready");
const main=document.querySelector("main");if(main&&!main.id)main.id="dw-main-content";
const skip=document.createElement("a");skip.className="dw-skip-link";skip.href="#dw-main-content";skip.textContent="Skip to content";body.insertBefore(skip,body.firstChild);
if(active[0]==="connectivity"&&path.endsWith("/communications.html")&&main){const link=document.createElement("a");link.className="dw-shell-shortcut";link.href="./meshcore.html";link.textContent="MeshCore resources & field guide ↗";main.insertBefore(link,main.firstChild);}
if(active[0]==="connectivity"&&path.endsWith("/meshcore.html")&&main){const link=document.createElement("a");link.className="dw-shell-shortcut";link.href="./communications.html";link.textContent="← Back to network monitor";main.insertBefore(link,main.firstChild);}
if(active[0]==="intelligence"&&path.endsWith("/observatory.html")&&main){const p=document.createElement("p");p.className="dw-muted";p.textContent="Northern Ireland / UK / cross-border / global intelligence";main.insertBefore(p,main.firstChild);}
})();
