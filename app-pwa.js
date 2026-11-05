(() => {
'use strict';
const base=new URL('.',document.currentScript.src),url=p=>new URL(p,base).href;
const bar=document.createElement('aside');bar.className='meme-appbar';bar.setAttribute('aria-label','应用状态');
const status=document.createElement('p');status.setAttribute('role','status');status.textContent='正在准备应用…';
const cacheStatus=document.createElement('small');status.append(cacheStatus);
const actions=document.createElement('div');actions.className='meme-app-actions';
function button(text,fn){const b=document.createElement('button');b.type='button';b.textContent=text;b.onclick=fn;actions.append(b);return b;}
let installPrompt=null,registration=null,checking=false,wasControlled=!!navigator.serviceWorker?.controller;
const installed=()=>matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
const dialog=document.createElement('dialog');dialog.className='meme-install-dialog';
const heading=document.createElement('h2');heading.textContent='把夸损有梗装到设备上';
const instructions=document.createElement('p');instructions.textContent='Chrome / Edge：使用地址栏的安装图标或菜单中的“安装应用”。Safari：Mac可在支持的版本中选择“文件→添加到程序坞”；iPhone/iPad可从分享菜单选择“添加到主屏幕”。当前内嵌浏览器可能不提供安装入口，请在系统浏览器打开同一地址。';
const localNote=document.createElement('p');localNote.textContent='本机请使用127.0.0.1:17861；公开访问需要HTTPS。手机上的127.0.0.1不是这台Mac，当前版本尚未提供跨设备同步。';
const close=document.createElement('button');close.textContent='知道了';close.onclick=()=>dialog.close();dialog.append(heading,instructions,localNote,close);
async function install(){if(installed())return; if(installPrompt){const prompt=installPrompt;installPrompt=null;await prompt.prompt();await prompt.userChoice;installButton.textContent=installed()?'已安装':'查看安装方式';}else dialog.showModal();}
const installButton=button(installed()?'应用模式':'安装 / 使用说明',install);installButton.disabled=installed();
const updateButton=button('检查应用更新',async()=>{if(!registration){cacheStatus.textContent='请先从本机HTTP或HTTPS页面打开应用。';return;}if(registration.waiting){registration.waiting.postMessage({type:'SKIP_WAITING'});cacheStatus.textContent='正在启用新版本；不会重载当前页面。';}else{try{await registration.update();cacheStatus.textContent=registration.waiting?'发现新版本，可点击启用。':'已检查应用更新；缓存仅含公开资源。';}catch{cacheStatus.textContent='暂时无法检查更新；可以继续离线使用。';}}});
button('重新连接',()=>checkBackend());
const homeLink=document.createElement('a');homeLink.href=url('预览.html');homeLink.className='meme-home-link';homeLink.textContent='夸损有梗 / 资料首页';bar.append(homeLink,status,actions);
const nav=document.createElement('nav');nav.className='meme-appnav';nav.setAttribute('aria-label','应用导航');
for(const [p,label] of [['预览.html','资料首页'],['create-funny-meme-cards/assets/poster-studio/index.html','海报工坊'],['本地工作台.html','资料维护'],['app.html?view=about','项目说明']]){const a=document.createElement('a');a.href=url(p);a.textContent=label;const current=new URL(location.href);if(decodeURI(current.pathname)===decodeURI(new URL(a.href).pathname)||(p==='预览.html'&&current.pathname===base.pathname))a.setAttribute('aria-current','page');nav.append(a);}
function showStatus(text){status.firstChild?.remove();status.prepend(document.createTextNode(text));}
async function checkBackend(){if(checking)return;checking=true;try{const timeout=new AbortController(),timer=setTimeout(()=>timeout.abort(),2500);let response;try{response=await fetch(url('api/bootstrap'),{cache:'no-store',signal:timeout.signal});}finally{clearTimeout(timer);}if(!response.ok)throw Error();const b=await response.json();if(!b.token||b.storage!=='Obsidian Markdown')throw Error();showStatus('已连接本机Obsidian服务；查询需外网。');window.dispatchEvent(new CustomEvent('meme-backend',{detail:{connected:true}}));}catch{showStatus(location.protocol==='file:'?'文件预览模式：请启动本地服务后使用PWA。':'本机服务未连接：可用上次缓存的资料与海报工具；笔记未写入。');window.dispatchEvent(new CustomEvent('meme-backend',{detail:{connected:false}}));}finally{checking=false;}}
window.memeRefreshPublicCache=async()=>{try{const publicData=['预览.html','create-funny-meme-cards/assets/knowledge/knowledge.json','create-funny-meme-cards/assets/knowledge/index.json','create-funny-meme-cards/assets/knowledge/focus.json'];const snapshots=await Promise.all(publicData.map(async p=>{const href=url(p),r=await fetch(href,{cache:'no-store'});if(!r.ok)throw Error('public refresh');return {href,response:r};}));const names=(await caches.keys()).filter(n=>n.startsWith('meme-pwa:'+base.href+':'));for(const n of names){const c=await caches.open(n);await Promise.all(snapshots.map(s=>c.put(s.href,s.response.clone())));}cacheStatus.textContent='本次保存已刷新离线资料；未缓存私人笔记与接口。';return true;}catch{cacheStatus.textContent='笔记已保存，但离线副本尚未刷新；请保持本机连接后重开资料库。';return false;}};
function waiting(){if(registration?.waiting){updateButton.textContent='启用新版本';cacheStatus.textContent='新版本已准备。启用后不会自动重载，保存或导出后再重新打开页面。';}}
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;installButton.textContent='安装应用';});
window.addEventListener('appinstalled',()=>{installButton.textContent='已安装';installButton.disabled=true;});
window.addEventListener('meme-install-help',()=>dialog.showModal());
window.addEventListener('online',()=>checkBackend());window.addEventListener('offline',()=>checkBackend());
document.addEventListener('DOMContentLoaded',async()=>{document.body.classList.add('meme-app');document.body.prepend(bar);document.body.append(nav,dialog);await checkBackend();if(!('serviceWorker'in navigator)||!window.isSecureContext||!/^https?:$/.test(location.protocol)){cacheStatus.textContent='安装与离线缓存需本机HTTP或HTTPS环境。';return;}try{registration=await navigator.serviceWorker.register(url('sw.js'),{scope:base.href,updateViaCache:'none'});waiting();registration.addEventListener('updatefound',()=>{const worker=registration.installing;worker?.addEventListener('statechange',()=>{if(worker.state==='installed'){if(navigator.serviceWorker.controller)waiting();else cacheStatus.textContent='公开资料与海报工具已缓存，可离线使用。';}});});await navigator.serviceWorker.ready;if(!registration.waiting)cacheStatus.textContent='离线资源已准备；私人内容与写操作不缓存。';navigator.serviceWorker.addEventListener('controllerchange',()=>{updateButton.textContent='检查应用更新';cacheStatus.textContent=wasControlled?'新版本已启用，当前页面内容已保留；保存后重新打开即可。':'离线应用已准备；公开资料与海报工具可离线使用。';wasControlled=true;});}catch{cacheStatus.textContent='离线缓存准备失败，请重新连接本地服务后刷新。';}});
})();
