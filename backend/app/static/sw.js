const CACHE = "ke-box-calc-v080-dev-2";
const ASSETS = ["/","/static/app.css","/static/app.js","/manifest.webmanifest"];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener("activate", event => event.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))
));
self.addEventListener("fetch", event => {
  if(event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if(url.origin !== self.location.origin || url.pathname.startsWith("/api/") || url.pathname === "/health") return;
  event.respondWith(fetch(event.request).then(r=>{
    if(r.ok){
      const copy=r.clone();
      event.waitUntil(caches.open(CACHE).then(c=>c.put(event.request,copy)));
    }
    return r;
  }).catch(()=>caches.match(event.request)));
});
