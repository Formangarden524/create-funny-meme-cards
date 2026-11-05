(() => {
'use strict';
const $=s=>document.querySelector(s), styles=window.MEME_STYLES;
const canvas=$('#canvas'),ctx=canvas.getContext('2d');
let selected=styles[0],poster=null,qr=null,qrPayload=null,qrVerified=false,loadVersion=0,qrVersion=0;
const say=s=>{$('#message').textContent=s;};
function image(src){return new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(Error('图片读取失败，请换用PNG/JPEG/WebP。'));im.src=src;});}
function readFile(file){return new Promise((resolve,reject)=>{if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type))return reject(Error('请选择PNG/JPEG/WebP图片。'));if(file.size>20*1024*1024)return reject(Error('图片超过20MB，请先缩小。'));const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('文件读取失败。'));reader.readAsDataURL(file);});}
function decode(c){const cctx=c.getContext('2d'), pixels=cctx.getImageData(0,0,c.width,c.height);const found=window.jsQR(pixels.data,c.width,c.height);return found?.data??null;}
function imageCanvas(im,limit=1400){const c=document.createElement('canvas'),scale=Math.min(1,limit/Math.max(im.width,im.height));c.width=Math.round(im.width*scale);c.height=Math.round(im.height*scale);const x=c.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,c.width,c.height);x.drawImage(im,0,0,c.width,c.height);return c;}
function fitText(text,x,y,max,size,color){ctx.fillStyle=color;let fontSize=size;do{ctx.font=`700 ${fontSize}px "PingFang SC","Microsoft YaHei",sans-serif`;if(ctx.measureText(text).width<=max)break;fontSize--;}while(fontSize>16);ctx.fillText(text,x,y);}
function draw(){
 if(!poster)return;const w=1080,artH=Math.round(w*poster.height/poster.width),footH=300;
 canvas.width=w;canvas.height=artH+footH;ctx.fillStyle='#fff';ctx.fillRect(0,0,w,canvas.height);ctx.drawImage(poster,0,0,w,artH);
 ctx.fillStyle='#d7ddd8';ctx.fillRect(44,artH+8,992,2);
 const name=$('#nickname').value.trim(),sig=$('#signature').value.trim(),hasQr=$('#qr-mode').value!=='none'&&qr;
 const available=hasQr?690:980;
 if(name)fitText('@'+name,48,artH+88,available,46,selected.accent);
 if(sig)fitText(sig,48,artH+145,available,28,'#333');
 if(hasQr){const size=248,x=784,y=artH+22;ctx.fillStyle='#fff';ctx.fillRect(x,y,size,size);ctx.imageSmoothingEnabled=false;const scale=Math.min((size-24)/qr.width,(size-24)/qr.height),ww=Math.floor(qr.width*scale),hh=Math.floor(qr.height*scale);ctx.drawImage(qr,x+Math.floor((size-ww)/2),y+Math.floor((size-hh)/2),ww,hh);ctx.imageSmoothingEnabled=true;const patch=document.createElement('canvas');patch.width=size;patch.height=size;patch.getContext('2d').drawImage(canvas,x,y,size,size,0,0,size,size);qrVerified=!!qrPayload&&decode(patch)===qrPayload;
 $('#qr-status').textContent=qrVerified?'已校验：原码与合成区域解码内容一致；请再用手机试扫。':'未通过合成解码校验，请换用清晰、完整的二维码。';}
 if($('#credit').checked)fitText('工具源自：秋哥 · 夸损有梗',48,artH+254,available,21,'#666');
 $('#export').disabled=false;
}
const collectionLines=()=>$('#copy').value.split('\n').map(s=>s.trim()).filter(Boolean);
function collectionError(){if(selected.format!=='collection')return '';const lines=collectionLines();if(lines.length<2||lines.length>10)return '合集请填写2—10条段子，每行一条；超过10条请拆页。';if(lines.some(s=>s.length>60))return '单条文案超过60字，请缩短，保持海报可读。';return '';}
function prompt(){
 const header=`原创中文搞笑海报；竖版${selected.aspect_ratio||'3:4'}；风格：${selected.name}。\n视觉：${selected.visual}。\n标题逐字呈现：“${$('#title').value.trim()}”。`;
 const end='选题可用于评价排名、表达态度、黑话反转、嘴替、接话或自嘲；不要求每句都设计对话。有具体生活场景，调侃给对方留台阶，不堆需要长解释的典故。中文清晰、包袱完整，人物与画面原创，不使用现有IP；不得添加未提供的对白。底部不生成昵称、二维码或Logo，品牌留给后期独立合成。不得绘制假二维码。';
 if(selected.format==='collection'){
  const lines=collectionLines(),columns=lines.length<=4?1:2,rows=Math.ceil(lines.length/columns);
  return header+`\n这是搞笑信息图合集，不是知识科普。正文共${lines.length}条、${columns}列${rows}行，按行从左到右编号；每条一个独立单元格、一句完整文案、一幅对应小漫画。不得漏项、重复、串格、改字。文字优先，不用缩小字来塞内容。\n`+lines.map((s,i)=>`${String(i+1).padStart(2,'0')} 文案逐字呈现：“${s}”`).join('\n')+`\n逐条对应的画面动作：\n${$('#scene').value.trim().split('\n').slice(0,lines.length).join('\n')}\n若缺少某条画面动作，按该条包袱补充，不改文案。底部说明“趣味合集，非实时热榜。”；引用内容的具体出处另列于交付说明。\n`+end;
 }
 return header+`\n反转文案逐字呈现：“${$('#copy').value.trim()}”。\n画面动作：${$('#scene').value.trim()}。\n`+end;
}
function updatePrompt(){$('#prompt').value=prompt();if(selected.format==='collection')say(collectionError()||`合集共${collectionLines().length}条，修改文案后需重新生图。`);}
function download(blob,name){const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function jsonDownload(value,name){download(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),name);}
async function sample(){const version=++loadVersion;poster=null;$('#export').disabled=true;try{const im=await image(window.MEME_SAMPLE_IMAGES[selected.id]);if(version!==loadVersion)return;poster=im;$('#preview-kind').textContent='已生成的'+selected.name+'样张；修改文案后请重新生图';draw();}catch(e){say(e.message);}}
function choose(id){selected=styles.find(s=>s.id===id);for(const f of ['title','copy','scene'])$('#'+f).value=selected[f];const isCollection=selected.format==='collection';$('#copy').maxLength=isCollection?1200:140;$('#copy').rows=isCollection?10:3;$('#scene').maxLength=isCollection?1600:300;$('#scene').rows=isCollection?8:3;$('#copy-label').textContent=isCollection?'合集文案（每行一条）':'反转文案';$('#scene-label').textContent=isCollection?'逐条画面动作（按编号对应）':'画面动作';$('#collection-hint').hidden=!isCollection;document.querySelectorAll('.style').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.style===id)));updatePrompt();sample();}
for(const s of styles){const b=document.createElement('button');b.className='style';b.dataset.style=s.id;b.type='button';b.setAttribute('aria-pressed','false');const img=document.createElement('img');img.src=window.MEME_SAMPLE_IMAGES[s.id];img.alt=s.name+'实际生图样张';const strong=document.createElement('strong');strong.textContent=s.name;const tag=document.createElement('span');tag.textContent=s.tag;const p=document.createElement('p');p.textContent=s.description;b.append(img,strong,tag,p);b.onclick=()=>choose(s.id);$('#styles').append(b);}
for(const id of ['title','copy','scene','provider'])$('#'+id).addEventListener('input',updatePrompt);
for(const id of ['nickname','signature','credit'])$('#'+id).addEventListener('input',draw);
$('#prompt-button').onclick=()=>{updatePrompt();$('#prompt').select();say('提示词已更新并选中，可复制给生图模型。');};
$('#job-button').onclick=()=>{if(collectionError()){say(collectionError());return;}updatePrompt();jsonDownload({schema_version:'1.0',task:'generate_funny_poster',style_id:selected.id,format:selected.format||'single',aspect_ratio:selected.aspect_ratio||'3:4',items:selected.format==='collection'?collectionLines().map((text,i)=>({number:i+1,text,scene:$('#scene').value.trim().split('\n')[i]||null})):null,provider:$('#provider').value,model:'host_available_image_model',title:$('#title').value,copy:$('#copy').value,scene:$('#scene').value,prompt:$('#prompt').value,brand_composition:'after_generation',status:'not_executed'},'meme-image-request.json');say('已导出生图任务；请交给支持生图的AI执行。');};
$('#sample-button').onclick=sample;
$('#poster-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;const version=++loadVersion;try{const im=await image(await readFile(file));if(im.width*im.height>40e6||im.width/im.height>3||im.height/im.width>4)throw Error('图片过大或比例过长，请先调整画幅。');if(version!==loadVersion)return;poster=im;$('#preview-kind').textContent='已上传自己的成图；昵称与二维码为独立合成层';draw();}catch(e){say(e.message);}};
$('#names-button').onclick=()=>{const key=$('#name-keyword').value.trim()||'快乐';const names=[key+'不加班',key+'有点梗','今天也'+key,key+'小分队','一口'+key];$('#names').replaceChildren();for(const name of names){const b=document.createElement('button');b.type='button';b.textContent=name.slice(0,16);b.onclick=()=>{$('#nickname').value=b.textContent;draw();};$('#names').append(b);}say('点击候选即可采用；这是本地灵感组合，未查询昵称是否重名。');};
function clearQR(){qrVersion++;qr=null;qrPayload=null;qrVerified=false;$('#qr-url').value='';$('#qr-file').value='';$('#qr-status').textContent='未添加二维码';draw();}
$('#qr-mode').onchange=()=>{$('#qr-upload').hidden=$('#qr-mode').value!=='upload';$('#qr-link').hidden=$('#qr-mode').value!=='link';clearQR();};
$('#qr-clear').onclick=()=>{$('#qr-mode').value='none';$('#qr-mode').dispatchEvent(new Event('change'));};
$('#qr-url').oninput=()=>{qrVersion++;qr=null;qrPayload=null;qrVerified=false;$('#qr-status').textContent='链接已修改，请重新生成二维码。';draw();};
$('#qr-generate').onclick=()=>{try{const value=$('#qr-url').value.trim(),url=new URL(value);if(!['https:','http:'].includes(url.protocol)||url.username||url.password)throw Error('请填写完整的http或https网址。');if(new TextEncoder().encode(value).length>600)throw Error('链接过长，请使用较短的目标网址。');window.qrcode.stringToBytes=s=>Array.from(new TextEncoder().encode(s));const code=window.qrcode(0,'M');code.addData(value,'Byte');code.make();const n=code.getModuleCount(),unit=6,pad=4;const c=document.createElement('canvas');c.width=c.height=(n+pad*2)*unit;const cctx=c.getContext('2d');cctx.fillStyle='white';cctx.fillRect(0,0,c.width,c.height);cctx.fillStyle='black';for(let y=0;y<n;y++)for(let x=0;x<n;x++)if(code.isDark(y,x))cctx.fillRect((x+pad)*unit,(y+pad)*unit,unit,unit);qr=c;qrPayload=value;if(decode(c)!==value)throw Error('生成二维码未通过解码，请缩短链接。');draw();say('网址二维码已生成，没有打开目标网址。');}catch(e){qr=null;qrPayload=null;qrVerified=false;draw();$('#qr-status').textContent='二维码未生成';say(e.message);}};
$('#qr-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;const version=++qrVersion;try{qr=null;qrPayload=null;draw();const im=await image(await readFile(file));if(version!==qrVersion)return;const c=imageCanvas(im),decoded=decode(c);if(!decoded)throw Error('未识别到可用二维码，请上传裁切清楚、四周留白的原码。');qr=c;qrPayload=decoded;draw();say('原码已在本地解码；未打开二维码目标。');}catch(e){qr=null;qrPayload=null;qrVerified=false;draw();$('#qr-status').textContent='二维码未识别';say(e.message);}};
$('#export').onclick=()=>{draw();if($('#qr-mode').value!=='none'&&(!qr||!qrVerified)){say('二维码尚未通过合成解码校验。请重新上传/生成，或选择暂不添加。');return;}canvas.toBlob(blob=>{if(blob){download(blob,'夸损有梗-'+selected.id+'-品牌海报.png');say('海报已导出；含二维码时请用手机确认目标。');}else say('导出失败，请重新上传图片。');},'image/png');};
$('#config').onclick=()=>{jsonDownload({schema_version:'0.2.0-preview',brand:{enabled:!!($('#nickname').value||qr),nickname:$('#nickname').value,signature:$('#signature').value,qr_mode:$('#qr-mode').value,qr_url:$('#qr-mode').value==='link'?$('#qr-url').value:null,qr_path:null,footer_mode:'bottom'},appearance:{style_id:selected.id},project_credit:{author:'秋哥',project_name:'夸损有梗',output_credit:$('#credit').checked},note:'上传二维码图片未包含于配置；请另存私人目录。'},'brand.local.json');say('个人配置已下载；当前版本暂不支持导入，重开页面需重新填写。');};
const requested=new URLSearchParams(location.search).get('style');choose(styles.some(s=>s.id===requested)?requested:styles[0].id);
const entryId=new URLSearchParams(location.search).get('entry');
if(entryId){(async()=>{try{const response=await fetch('../knowledge/knowledge.json');if(!response.ok)throw Error();const pack=await response.json(),record=pack.records.find(r=>r.id===entryId);if(!record)throw Error();choose('comic');$('#title').value=record.title.slice(0,32);$('#copy').value=record.social_use.line.slice(0,140);$('#scene').value=record.editorial.visual_idea.slice(0,300);updatePrompt();const back=document.createElement('a');back.href='../../../预览.html?q='+encodeURIComponent(record.title);back.textContent='← 返回“'+record.title+'”资料';document.querySelector('header').append(back);say('已带入“'+record.title+'”的文案和画面构思；预览仍是风格样张，需要重新生图。');}catch{say('未能载入这条资料，可返回资料首页重选；当前仍可使用风格样张。');}})();}

})();
