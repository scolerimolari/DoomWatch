const CACHE_NAME = "doomwatch-v30";
const APP_FILES = ["./","./index.html","./communications.html","./map.html","./feed.html","./markets.html","./household.html","./manifest.json","./containment.svg","./doomwatch.css","./doomwatch-ui.js"];
self.addEventListener("install",event=>{event.waitUntil(caches.open(CACHE_NAME).then(cache=>cache.addAll(APP_FILES)));self.skipWaiting();});
self.addEventListener("activate",event=>{event.waitUntil(caches.keys().then(names=>Promise.all(names.filter(name=>name.startsWith("doomwatch-")&&name!==CACHE_NAME).map(name=>caches.delete(name)))));self.clients.claim();});
self.addEventListener("fetch",event=>{
 const request=event.request;if(request.method!=="GET")return;const url=new URL(request.url);if(url.origin!==self.location.origin)return;
 const isData=url.pathname.includes("/data/"),isNavigation=request.mode==="navigate",isHtml=url.pathname.endsWith(".html"),cacheKey=new Request(url.origin+url.pathname);
 if(isData||isNavigation||isHtml){event.respondWith(fetch(request,{cache:"no-store"}).then(response=>{if(response.ok){const copy=response.clone();caches.open(CACHE_NAME).then(cache=>cache.put(cacheKey,copy));}return response;}).catch(async()=>await caches.match(cacheKey)||(isNavigation?await caches.match("./index.html"):Response.error())));return;}
 event.respondWith(caches.match(cacheKey).then(cached=>cached||fetch(request).then(response=>{if(response.ok){const copy=response.clone();caches.open(CACHE_NAME).then(cache=>cache.put(cacheKey,copy));}return response;})));
});