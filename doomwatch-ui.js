(() => {
"use strict";
if (window.__doomwatchUiReady) return;
window.__doomwatchUiReady = true;

const body = document.body;
const oldHeader = body.querySelector(":scope > header");
const oldNav = body.querySelector(":scope > nav");
const path = location.pathname.toLowerCase();
const active = path.endsWith("/markets.html") ? "markets"
  : path.endsWith("/household.html") ? "household"
  : path.endsWith("/feed.html") ? "feed"
  : path.endsWith("/map.html") ? "map" : "command";

const destinations = [
  ["command", "index.html", "COMMAND"],
  ["markets", "markets.html", "MARKETS"],
  ["household", "household.html", "HOUSEHOLD"],
  ["feed", "feed.html", "FEED"],
  ["map", "map.html", "MAP"]
];

const mast = document.createElement("header");
mast.className = "dw-masthead";
mast.innerHTML = '<div class="dw-brand"><img class="dw-emblem" src="./containment.svg" alt="DoomWatch red containment unit emblem"><div><div class="dw-wordmark">DOOMWATCH</div><div class="dw-tagline">OPERATION CONTAINMENT // RESILIENCE INTELLIGENCE</div><div class="dw-statusline" id="dw-statusline"></div></div></div><div class="dw-hardware" aria-hidden="true"><div class="dw-statusbox"><strong>CONTAINMENT SYSTEM</strong><span>POWER / FIELD UNIT</span><div class="dw-lamps"><i class="dw-lamp red"></i><i class="dw-lamp amber"></i><i class="dw-lamp green"></i></div></div><div class="dw-valves"><i class="dw-valve red"></i><i class="dw-valve"></i></div><div class="dw-switches"><i class="dw-switch on"></i><i class="dw-switch"></i></div></div>';
body.insertBefore(mast, body.firstChild);

const statusline = mast.querySelector("#dw-statusline");
["clock", "connection", "updated"].forEach(id => {
  const node = document.getElementById(id);
  if (node) { const wrap = document.createElement("span"); wrap.appendChild(node); statusline.appendChild(wrap); }
});
if (oldHeader) oldHeader.hidden = true;

const nav = document.createElement("nav");
nav.className = "dw-global-nav";
nav.setAttribute("aria-label", "DoomWatch main navigation");
destinations.forEach(([key, file, label]) => {
  const a = document.createElement("a");
  a.href = new URL(file, document.baseURI).href;
  a.textContent = label;
  a.dataset.dwDestination = key;
  if (key === active) { a.setAttribute("aria-current", "page"); a.setAttribute("aria-label", label + " (current page)"); }
  nav.appendChild(a);
});
mast.insertAdjacentElement("afterend", nav);

if (oldNav) {
  oldNav.classList.add("dw-local-nav");
  oldNav.setAttribute("aria-label", "Page sections");
  nav.insertAdjacentElement("afterend", oldNav);
}
const wire = document.createElement("div");
wire.className = "dw-wire";
wire.setAttribute("aria-hidden", "true");
(oldNav || nav).insertAdjacentElement("afterend", wire);

nav.addEventListener("click", event => {
  const link = event.target.closest("a[data-dw-destination]");
  if (!link) return;
  event.preventDefault();
  window.location.assign(link.href);
});

const top = document.createElement("button");
top.type = "button";
top.className = "dw-top";
top.textContent = "TOP";
top.setAttribute("aria-label", "Back to top");
top.addEventListener("click", () => window.scrollTo({top: 0, behavior: "smooth"}));
body.appendChild(top);
body.classList.add("dw-ready");
})();