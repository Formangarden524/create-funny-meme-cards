// Test reconnect logic with controlled responses; no network or vault mutations.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'..','workbench.js'),'utf8');
const api=source.slice(source.indexOf('async function api('),source.indexOf('function button('));
function client(responses){const calls=[];let cacheSync=0;const context=vm.createContext({window:{memeRefreshPublicCache:async()=>{cacheSync++;return true;}},fetch:async(url,options)=>{calls.push({url,options});const r=responses.shift();assert.ok(r,'unexpected retry');return {ok:r.status>=200&&r.status<300,status:r.status,json:async()=>r.body};}});vm.runInContext("let token='old-token';"+api,context);return {call:(data)=>context.api('/api/edit',data),calls,cacheSync:()=>cacheSync};}
(async()=>{
 const data={id:'example',revision:'unchanged',markdown:'example'};
 const first=client([{status:403,body:{error:'token'}},{status:200,body:{token:'new-token'}},{status:200,body:{saved:true}}]);
 assert.equal((await first.call(data)).saved,true);assert.equal(first.calls.length,3);assert.equal(first.cacheSync(),1);assert.equal(first.calls[1].url,'/api/bootstrap');assert.equal(first.calls[2].options.headers['X-Workbench-Token'],'new-token');assert.equal(first.calls[0].options.body,first.calls[2].options.body);
 const denied=client([{status:403,body:{error:'denied'}},{status:200,body:{token:'new-token'}},{status:403,body:{error:'still denied'}}]);await assert.rejects(denied.call(data),/still denied/);assert.equal(denied.calls.length,3);
 const conflict=client([{status:409,body:{error:'conflict'}}]);await assert.rejects(conflict.call(data),/conflict/);assert.equal(conflict.calls.length,1);assert.equal(conflict.cacheSync(),0);
 console.log('PASS: refresh expired token once, preserve edit revision/body, stop after repeated denial, never retry edit conflicts');
})().catch(e=>{console.error(e);process.exitCode=1;});
