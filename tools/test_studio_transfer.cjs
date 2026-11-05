// Run the actual studio client in a small DOM harness. No browser, vault writes or model calls.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const studio=path.join(__dirname,'../create-funny-meme-cards/assets/poster-studio');
const script=fs.readFileSync(path.join(studio,'studio.js'),'utf8'),html=fs.readFileSync(path.join(studio,'index.html'),'utf8'),styles=JSON.parse(fs.readFileSync(path.join(studio,'styles.json'),'utf8'));
const record={id:'selected-entry',title:'选中的完整标题',social_use:{line:'这是一句必须完整保留的文案。'.repeat(18)},editorial:{visual_idea:'这是完整的画面构思。'.repeat(45)}};
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
function boot(search,{storage=new Map(),records=[record],deferred=null}={}){
 const elements=new Map(),styleButtons=[],downloads=[];const ctx={fillRect(){},drawImage(){},fillText(){},measureText:s=>({width:s.length*8})};
 class Element{constructor(tag='div'){this.tagName=tag;this.value='';this.hidden=false;this.disabled=false;this.checked=true;this.children=[];this.dataset={};this.style={};this.events={};this.attributes={};this.textContent='';}append(...nodes){this.children.push(...nodes);if(this===elements.get('#styles'))styleButtons.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}addEventListener(name,fn){(this.events[name]??=[]).push(fn);}setAttribute(k,v){this.attributes[k]=v;}getContext(){return ctx;}click(){this.onclick?.();}select(){} }
 for(const [,id]of html.matchAll(/id="([^"]+)"/g))elements.set('#'+id,new Element());elements.set('header',new Element('header'));
 elements.get('#qr-mode').value='none';elements.get('#provider').value='host_tool';
 const document={querySelector:s=>elements.get(s),querySelectorAll:s=>s==='.style'?styleButtons:[],createElement:t=>new Element(t)};
 class FakeImage{constructor(){this.width=1080;this.height=1440;}set src(value){this.onload();}}
 class FakeURL extends URL{static createObjectURL(blob){downloads.push(blob);return 'blob:test';}static revokeObjectURL(){}}
 const context=vm.createContext({document,window:{MEME_STYLES:styles,MEME_SAMPLE_IMAGES:Object.fromEntries(styles.map(s=>[s.id,'data:sample']))},Image:FakeImage,URL:FakeURL,URLSearchParams,Blob,TextEncoder,location:{pathname:'/studio/index.html',search},sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},setTimeout(){},fetch:deferred?()=>deferred:async()=>({ok:true,json:async()=>({records})})});
 vm.runInContext(script,context);
 return {elements,styleButtons,downloads,storage,read:()=>Object.fromEntries(['title','copy','scene'].map(k=>[k,elements.get('#'+k).value])),clickStyle:id=>styleButtons.find(b=>b.dataset.style===id).onclick(),input:(id,value)=>{const e=elements.get('#'+id);e.value=value;e.events.input.forEach(fn=>fn());}};
}
(async()=>{
 const app=boot('?entry=selected-entry&style=pets');await flush();assert.deepEqual(app.read(),{title:record.title,copy:record.social_use.line,scene:record.editorial.visual_idea});assert.equal(app.elements.get('#canvas').hidden,true);assert.equal(app.elements.get('#export').disabled,true);
 for(const id of ['retro','comic','pets','collection','pets']){app.clickStyle(id);assert.equal(app.read().copy,record.social_use.line);assert.equal(app.read().scene,record.editorial.visual_idea);}
 app.input('copy','这是我手动修改后的包袱。');app.clickStyle('retro');assert.equal(app.read().copy,'这是我手动修改后的包袱。');assert.ok(app.elements.get('#prompt').value.includes('这是我手动修改后的包袱。'));
 app.elements.get('#job-button').onclick();const task=JSON.parse(await app.downloads[0].text());assert.equal(task.copy,app.read().copy);assert.equal(task.source_entry_id,'selected-entry');assert.equal(task.style_id,'retro');
 await app.elements.get('#sample-button').onclick();assert.equal(app.read().copy,'这是我手动修改后的包袱。');assert.ok(app.elements.get('#preview-kind').textContent.includes('图中文字不是当前文案'));
 const restored=boot('',{storage:app.storage});await flush();assert.deepEqual(restored.read(),app.read());assert.equal(restored.styleButtons.find(b=>b.attributes['aria-pressed']==='true').dataset.style,'retro');
 const missing=boot('?entry=missing',{records:[]});await flush();assert.deepEqual(missing.read(),{title:'',copy:'',scene:''});assert.equal(missing.elements.get('#job-button').disabled,true);assert.ok(missing.elements.get('#selection-status').textContent.includes('未套用任何模板'));
 let resolve;const deferred=new Promise(r=>resolve=r);const slow=boot('?entry=selected-entry',{deferred});assert.equal(slow.read().copy,'');assert.equal(slow.elements.get('#title').disabled,true);slow.clickStyle('pets');resolve({ok:true,json:async()=>({records:[record]})});await flush();assert.equal(slow.read().copy,record.social_use.line);assert.equal(slow.styleButtons.find(b=>b.attributes['aria-pressed']==='true').dataset.style,'pets');
 console.log('PASS: complete entry transfer, all styles preserve edits, correct export, sample isolation, navigation restore, missing entry and delayed load');
})().catch(e=>{console.error(e);process.exitCode=1;});
