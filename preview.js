(() => {
'use strict';
const data=JSON.parse(document.getElementById('knowledge-data').textContent);
const focus=JSON.parse(document.getElementById('focus-data').textContent);
const sources=new Map(data.sources.map(s=>[s.id,s]));
const $=s=>document.querySelector(s);
const categories=focus.categories;
const kinds={early_network_humor:'早期网络幽默',network_expression:'网络表达',visual_meme:'视觉梗',network_slang:'流行语',prank_format:'恶作剧格式',visual_template:'图文模板',phrase_template:'句式 / 表达类别',cultural_keyword:'文化词',character_trend:'角色趋势',animation_trend:'动画趋势',technical_term:'术语'};
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const link=s=>/^https?:\/\//.test(s)?escape(s):'#';
const shownDate=r=>r.recent_evidence_date||String(r.dates.reference_year);
const dateKey=r=>Number(shownDate(r).replaceAll('-','').padEnd(8,'0'));
const year=r=>Number(shownDate(r).slice(0,4));
const recent=r=>focus.priority_years.includes(year(r));
const records=[...data.records].sort((a,b)=>dateKey(b)-dateKey(a)||a.language.localeCompare(b.language)||a.id.localeCompare(b.id));
const decades=[...new Set(records.map(r=>r.dates.decade))].sort().reverse();
let active='recent';
const inRange=r=>active==='all'||active==='recent'&&recent(r)||active.startsWith('year:')&&year(r)===Number(active.slice(5))||active.startsWith('decade:')&&r.dates.decade===active.slice(7);
const items=[['recent','近三年 · 优先',records.filter(recent).length],...focus.priority_years.map(y=>['year:'+y,y+' 年',records.filter(r=>year(r)===y).length]),['all','全部资料',records.length],...decades.map(d=>['decade:'+d,d.slice(0,4)+' 年代',records.filter(r=>r.dates.decade===d).length]),['decade:1960s','1960 年代 · 背景',0]];
$('#timeline').innerHTML=items.map(([id,label,count])=>`<button type="button" data-range="${id}" aria-pressed="${id===active}"><span>${label}</span><span>${count}</span></button>`).join('');
$('#category').innerHTML='<option value="all">全部类别</option>'+Object.entries(categories).map(([id,label])=>`<option value="${id}">${label}</option>`).join('');
$('#social-function').innerHTML='<option value="all">全部社交用途</option>'+Object.entries(focus.social_functions).map(([id,label])=>`<option value="${id}">${label}</option>`).join('');
$('#priority-topics').innerHTML='<p><b>先玩这几个</b></p>'+ (focus.priority_topic_status||[]).map(t=>`<button type="button" data-topic="${escape(t.title)}">${escape(t.title)} · ${escape(({include:'已收录',hold:'复审中',trash:'回收站',unresolved:'待核查'})[t.state]||t.state)}</button>`).join('');
$('#priority-topics').addEventListener('click',e=>{const b=e.target.closest('[data-topic]');if(!b)return;active='all';$('#query').value=b.dataset.topic;$('#social-function').value='all';$('#category').value='all';document.querySelectorAll('#timeline button').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.range==='all')));render();});
$('#stat-total').textContent=records.length;
$('#stat-recent').textContent=records.filter(recent).length;
$('#stat-sources').textContent=data.sources.length;
function render(){
 const q=$('#query').value.trim().toLocaleLowerCase(),lang=$('#language').value,category=$('#category').value,social=$('#social-function').value;
 const filtered=records.filter(r=>inRange(r)&&(lang==='all'||(lang==='cn'?r.language.startsWith('zh'):!r.language.startsWith('zh')))&&(category==='all'||r.categories.includes(category))&&(social==='all'||r.social_use.functions.includes(social))&&[r.title,...r.aliases,r.meaning,r.culture_scope,r.dates.reference_year,shownDate(r),r.attention_basis,r.editorial.humor_mechanism,r.editorial.scenarios.join(' '),...Object.values(r.social_use).flat(),...r.evidence.map(e=>sources.get(e.source_id).title)].join(' ').toLocaleLowerCase().includes(q));
 $('#result-count').textContent=`${filtered.length} 条资料 · 最新在前`;
 $('#current-scope').textContent=items.find(i=>i[0]===active)?.[1]||'资料';
 $('#context').hidden=active!=='decade:1960s';
 $('#empty').hidden=filtered.length>0||active==='decade:1960s';
 $('#library').innerHTML=filtered.map(r=>`<article class="entry" data-entry-id="${escape(r.id)}" data-year="${year(r)}" data-date-key="${dateKey(r)}"><div class="entry-meta"><span>${escape(shownDate(r))}</span><span>${r.categories.map(c=>escape(categories[c])).join(' · ')}</span><span>${escape(r.language)}</span></div><h3>${escape(r.title)}</h3>${r.ranking_levels?`<p><b>常见等级 · 从高到低</b></p><table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr><th scope="col">顺位</th><th scope="col">档位</th><th scope="col">含义（编辑归纳）</th></tr></thead><tbody>${r.ranking_levels.map(l=>`<tr><td style="padding:6px;border-bottom:1px solid #ddd">${l.rank}</td><th scope="row" style="padding:6px;border-bottom:1px solid #ddd">${escape(l.label)}</th><td style="padding:6px;border-bottom:1px solid #ddd">${escape(l.meaning)}</td></tr>`).join("")}</tbody></table><small>常见玩法；具体评价维度由作者说明。</small>`:""}<p class="idea"><span>${r.social_use.functions.map(f=>escape(focus.social_functions[f])).join(" · ")}</span>${escape(r.social_use.trigger)}</p><p><b>用法示例</b>　${escape(r.social_use.line)}</p>${r.social_use.follow_up?`<p><b>可选接法</b>　${escape(r.social_use.follow_up)}</p>`:""}<small>编辑自拟用法，未做受众实测</small><details><summary>查看语境、时间与来源</summary><div class="detail-body"><p><b>对象与分寸</b>${escape(r.social_use.audience)}；${escape(r.social_use.avoid)}</p><p><b>表达含义</b>${escape(r.meaning)}</p><p><b>收录依据</b>${escape(r.attention_basis)}</p><p><b>时间含义</b>上方时间为有据的收录、传播或讨论节点。${escape(r.dates.grouping_reason)}</p><p><b>文化范围 / 详细类型</b>${escape(r.culture_scope)} · ${escape(kinds[r.kind]||r.kind)}</p>${r.aliases.length?`<p><b>别名与变体</b>${escape(r.aliases.join('、'))}</p>`:''}<p><b>编辑解读与漫画构思</b>${escape(r.editorial.humor_mechanism)}；${escape(r.editorial.visual_idea)}</p><p><b>使用提示</b>${escape(r.cautions.join('；'))}</p>${r.evidence.map(e=>{const s=sources.get(e.source_id);return `<p><b>来源</b><a href="${link(s.url)}" target="_blank" rel="noopener noreferrer">${escape(s.title)} ↗</a><small>${escape(e.supports)}</small><small>来源类型：${escape(s.type)} · 阅读日期：${escape(s.accessed_on)}</small></p>`}).join('')}<p class="evidence-note">有传播/收录记录 ≠ 全网最受欢迎。未统一测量实时热度和逐词喜爱率；未附第三方媒体素材。<br>ID：${escape(r.id)}</p></div></details><div class="entry-actions"><a href="create-funny-meme-cards/assets/poster-studio/index.html?entry=${encodeURIComponent(r.id)}">用这个做海报 →</a><a href="本地工作台.html">去维护资料 →</a></div></article>`).join('');
}
$('#timeline').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;active=b.dataset.range;document.querySelectorAll('#timeline button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));render();});
$('#query').addEventListener('input',render);
$('#language').addEventListener('change',render);
$('#category').addEventListener('change',render);
$('#social-function').addEventListener('change',render);
$('#reset').addEventListener('click',()=>{active='recent';$('#query').value='';$('#language').value='cn';$('#category').value='all';$('#social-function').value='all';document.querySelectorAll('#timeline button').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.range==='recent')));render();});
const mobileFilters=matchMedia('(max-width:600px)');function arrangeFilters(){document.querySelector('.filter-options').open=!mobileFilters.matches;}arrangeFilters();mobileFilters.addEventListener('change',arrangeFilters);
const initial=new URLSearchParams(location.search).get('q');if(initial){active='all';$('#query').value=initial.slice(0,120);document.querySelectorAll('#timeline button').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.range==='all')));}
render();
})();
