/* Generated from explicit public resources; never add private API data to this cache. */
'use strict';
const VERSION=__PWA_VERSION__;
const RESOURCES=__PWA_ASSETS__;
const SCOPE=self.registration.scope;
const PREFIX='meme-pwa:'+SCOPE+':';
const CACHE=PREFIX+VERSION;
const urls=new Set(RESOURCES.map(p=>new URL(p,SCOPE).href));
const home=new URL('预览.html',SCOPE).href;
const fallback=new URL('offline.html',SCOPE).href;
async function fromCache(key){return (await caches.open(CACHE)).match(key);}
function cacheKey(request){if(request.method!=='GET')return null;const u=new URL(request.url);if(u.origin!==new URL(SCOPE).origin)return null;u.search='';u.hash='';if(u.href===SCOPE)return home;return urls.has(u.href)?u.href:null;}
self.addEventListener('install',event=>{event.waitUntil((async()=>{const cache=await caches.open(CACHE);try{await cache.addAll([...urls]);}catch(error){await caches.delete(CACHE);throw error;}})());});
self.addEventListener('activate',event=>{event.waitUntil((async()=>{const keys=await caches.keys();await Promise.all(keys.filter(k=>k.startsWith(PREFIX)&&k!==CACHE).map(k=>caches.delete(k)));await self.clients.claim();})());});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING'&&event.source?.url?.startsWith(SCOPE))self.skipWaiting();});
self.addEventListener('fetch',event=>{
 const key=cacheKey(event.request);
 // API endpoints, editor history, original notes, user files and all POSTs stay network-only.
 if(!key){const u=new URL(event.request.url);if(event.request.method==='GET'&&event.request.mode==='navigate'&&u.origin===new URL(SCOPE).origin&&u.href.startsWith(SCOPE)&&!u.pathname.includes('/api/'))event.respondWith(fetch(event.request).catch(async()=>await fromCache(fallback)||new Response('离线页面尚未准备',{status:503})));return;}
 event.respondWith((async()=>{const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),3500);try{const response=await fetch(event.request,{signal:abort.signal});if(response.ok){const cache=await caches.open(CACHE);await cache.put(key,response.clone());}return response;}catch{const cached=await fromCache(key);if(cached)return cached;if(event.request.mode==='navigate')return await fromCache(fallback)||new Response('应用尚未完成离线缓存',{status:503});return new Response('该公开资源尚未缓存',{status:503});}finally{clearTimeout(timer);}})());
});
