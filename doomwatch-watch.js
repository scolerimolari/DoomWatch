(()=>{"use strict";
const KEY="doomwatch-watchlist-v1";
const page=location.pathname.toLowerCase().endsWith("/map.html")?"map":"feed";
const read=()=>{try{const v=JSON.parse(localStorage.getItem(KEY)||"[]");return Array.isArray(v)?v.filter(x=>x&&typeof x.term==="string"&&["feed","map"].includes(x.target)):[];}catch(_){return[];}};
const write=items=>{try{localStorage.setItem(KEY,JSON.stringify(items));return true;}catch(_){return false;}};
const style=document.createElement("style");
style.textContent=".dw-watch-launch{position:fixed;z-index:1200;left:12px;bottom:14px;background:#8f302b;color:#fff;border:1px solid #e17b67;padding:10px 13px;font:700 11px monospace;letter-spacing:.08em;box-shadow:0 3px 16px #0009;border-radius:3px}.dw-watch-panel{position:fixed;z-index:1201;left:12px;bottom:58px;width:min(390px,calc(100vw - 24px));max-height:min(68vh,560px);overflow:auto;background:#151d18;color:#e8eddf;border:1px solid #75836b;border-top:4px solid #bd4b3d;box-shadow:0 8px 30px #000b;padding:12px;font:12px/1.45 monospace}.dw-watch-panel[hidden]{display:none}.dw-watch-head{display:flex;justify-content:space-between;align-items:center;gap:8px}.dw-watch-panel h3{margin:0;color:#f0d28e;font-size:13px}.dw-watch-panel p{color:#b9c4b5;font-size:10px}.dw-watch-actions,.dw-watch-item{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.dw-watch-panel button,.dw-watch-panel a{background:#273329;color:#e6ebdf;border:1px solid #69775e;padding:6px 8px;font:10px monospace;text-decoration:none}.dw-watch-panel button:disabled{opacity:.45}.dw-watch-panel input{width:100%;box-sizing:border-box;background:#0e1510;color:#fff;border:1px solid #69775e;padding:9px;font:12px monospace;margin:8px 0}.dw-watch-item{justify-content:space-between;border-top:1px solid #3c493d;padding:8px 0}.dw-watch-term{flex:1;min-width:130px;overflow-wrap:anywhere;color:#f0d28e}.dw-watch-empty{padding:10px 0;color:#aeb9a8}.dw-watch-count{color:#f0d28e}";
document.head.appendChild(style);
const launch=document.createElement("button");launch.type="button";launch.className="dw-watch-launch";launch.textContent="WATCHLIST // 0";launch.setAttribute("aria-expanded","false");
const panel=document.createElement("section");panel.className="dw-watch-panel";panel.hidden=true;panel.setAttribute("aria-label","Shared local watchlist");
panel.innerHTML='<div class="dw-watch-head"><h3>LOCAL WATCHLIST // DEVICE ONLY</h3><button type="button" data-close>CLOSE</button></div><p>Save searches from FEED or MAP, then reopen them from any DoomWatch page. This is a saved-search list, not an alert service.</p><label for="dw-watch-input">CURRENT SEARCH</label><input id="dw-watch-input" type="search" placeholder="Enter a topic, town, route or phrase"><div class="dw-watch-actions"><button type="button" data-save>SAVE SEARCH</button><span class="dw-watch-count" id="dw-watch-message" aria-live="polite"></span></div><div id="dw-watch-items" style="margin-top:8px"></div>';
document.body.append(launch,panel);
const input=panel.querySelector("#dw-watch-input"),itemsNode=panel.querySelector("#dw-watch-items"),message=panel.querySelector("#dw-watch-message");
const sourceInput=document.getElementById(page==="map"?"map-search":"feed-search");
if(sourceInput)input.value=sourceInput.value||"";
const urlFor=item=>item.target==="map"?"./map.html?search="+encodeURIComponent(item.term):"./feed.html?q="+encodeURIComponent(item.term);
function render(){
 const items=read();launch.textContent="WATCHLIST // "+items.length;
 itemsNode.replaceChildren();
 if(!items.length){const empty=document.createElement("div");empty.className="dw-watch-empty";empty.textContent="No saved searches yet. Search in FEED or MAP, then save it here.";itemsNode.append(empty);return;}
 items.forEach((item,index)=>{
  const row=document.createElement("div");row.className="dw-watch-item";
  const term=document.createElement("span");term.className="dw-watch-term";term.textContent=item.term+" // "+item.target.toUpperCase();
  const open=document.createElement("a");open.href=urlFor(item);open.textContent="OPEN";
  const remove=document.createElement("button");remove.type="button";remove.textContent="REMOVE";remove.addEventListener("click",()=>{const next=read();next.splice(index,1);if(write(next)){message.textContent="REMOVED";render();}else message.textContent="STORAGE UNAVAILABLE";});
  row.append(term,open,remove);itemsNode.append(row);
 });
}
launch.addEventListener("click",()=>{panel.hidden=!panel.hidden;launch.setAttribute("aria-expanded",String(!panel.hidden));if(!panel.hidden){if(sourceInput)input.value=sourceInput.value||input.value;input.focus();}});
panel.querySelector("[data-close]").addEventListener("click",()=>{panel.hidden=true;launch.setAttribute("aria-expanded","false");});
panel.querySelector("[data-save]").addEventListener("click",()=>{
 const term=input.value.trim();if(!term){message.textContent="ENTER A SEARCH FIRST";return;}
 const items=read();if(items.some(x=>x.term.toLowerCase()===term.toLowerCase()&&x.target===page)){message.textContent="ALREADY SAVED";return;}
 items.unshift({term,target:page,savedAt:new Date().toISOString()});
 if(write(items)){message.textContent="SEARCH SAVED";render();}else message.textContent="STORAGE UNAVAILABLE";
});
if(sourceInput)sourceInput.addEventListener("input",()=>{input.value=sourceInput.value;});
render();
})();