"""Build public knowledge artifacts from editable Obsidian Markdown notes.

No remote writes, background tasks, or user-history mutations are performed.
"""
from pathlib import Path
from collections import Counter
from datetime import date, datetime
import argparse
import base64
import hashlib
import json
import os
import re
import tempfile
try:
    import yaml
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import ValidationError
except ImportError as exc:
    raise SystemExit('缺少校验依赖。请在独立Python环境安装 tools/requirements.txt。') from exc

ROOT = Path(__file__).resolve().parents[1]

def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'

def read_note(path):
    text = path.read_text(encoding='utf-8')
    match = re.match(r'\A---\n(.*?)\n---\n(.*)\Z', text, re.S)
    if not match:
        raise ValueError(f'{path.name}: 缺少YAML属性区')
    props = yaml.safe_load(match[1])
    if not isinstance(props, dict):
        raise ValueError(f'{path.name}: 属性必须为对象')
    props = json.loads(json.dumps(props, default=lambda x: x.isoformat() if isinstance(x, (date, datetime)) else str(x)))
    if props.get('id') != path.stem:
        raise ValueError(f'{path.name}: 文件名必须与id一致')
    return props, match[2]

def section(body, heading):
    found = re.search(r'^## ' + re.escape(heading) + r'\s*\n(.*?)(?=^## |\Z)', body, re.M | re.S)
    if not found or not found[1].strip():
        raise ValueError(f'缺少正文段落：{heading}')
    return found[1].strip()

def bullets(text):
    values = [m[1].strip() for m in re.finditer(r'^[-*] (.+)$', text, re.M)]
    if not values:
        raise ValueError('使用场景和使用提示需用Markdown列表')
    return values

def load_package(root):
    kb = root / '知识库'
    pack = json.loads((kb / '资料包信息.json').read_text(encoding='utf-8'))
    sources = []
    for path in sorted((kb / '来源').glob('*.md')):
        p, body = read_note(path)
        p.pop('tags', None)
        p['limitations'] = section(body, '来源限制')
        sources.append(p)
    review = json.loads((kb / '收录复审.json').read_text(encoding='utf-8'))['entries']
    note_ids = {p.stem for p in (kb / '条目').glob('*.md')}
    if set(review) != note_ids:
        raise ValueError('每条原始资料都必须有明确的收录复审结论')
    records = []
    record_keys = ['id', 'title', 'aliases', 'kind', 'language', 'culture_scope', 'template_family', 'review_status']
    date_keys = ['reference_year', 'decade', 'grouping_reason', 'original_work_date', 'documented_event_date', 'popularized_date', 'origin_status']
    for path in sorted((kb / '条目').glob('*.md')):
        p, body = read_note(path)
        decision = review[p['id']]
        if decision['decision'] not in {'include', 'hold', 'trash'} or not decision['reason']:
            raise ValueError(f'{path.name}: 无效复审结论')
        if decision['decision'] in {'hold', 'trash'}:
            continue
        if not p['language'].startswith('zh'):
            proof = decision.get('mainland_usage_evidence', [])
            if not proof or any(not e.get('supports') or e.get('source_id') not in p['source_ids'] for e in proof):
                raise ValueError(f'{path.name}: 英文表达缺少大陆使用传播的证据说明')
        record = {k: p[k] for k in record_keys}
        if record['review_status'] != 'source_checked':
            raise ValueError(f'{path.name}: 未完成来源阅读，请先放待核线索')
        record['categories'] = p['focus_categories']
        record['recent_evidence_date'] = p.get('recent_evidence_date')
        record['attention_basis'] = section(body, '关注依据')
        record['social_use'] = p['social_use']
        record['dates'] = {k: p[k] for k in date_keys}
        record['meaning'] = section(body, '含义')
        if re.search(r'^## 等级与顺序\s*$', body, re.M):
            levels = []
            for row in section(body, '等级与顺序').splitlines():
                cells = [c.strip() for c in row.strip().strip('|').split('|')]
                if row.strip().startswith('|') and len(cells) == 3 and cells[0].isdigit():
                    levels.append({'rank': int(cells[0]), 'label': cells[1], 'meaning': cells[2]})
            if not levels or [l['rank'] for l in levels] != list(range(1, len(levels)+1)):
                raise ValueError(f'{path.name}: 等级表顺位必须从1连续排列')
            record['ranking_levels'] = levels

        record['editorial'] = {'humor_mechanism': section(body, '笑点机制'), 'visual_idea': section(body, '漫画构思'), 'scenarios': bullets(section(body, '使用场景')), 'suitability': p['suitability'], 'is_editorial_interpretation': True}
        evidence_text = section(body, '证据支持范围')
        evidence = []
        for source_id in p['source_ids']:
            match = re.search(r'^### ' + re.escape(source_id) + r'\s*\n(.*?)(?=^### |\Z)', evidence_text, re.M | re.S)
            if not match or not match[1].strip():
                raise ValueError(f'{path.name}: 没有{source_id}的证据支持范围')
            evidence.append({'source_id': source_id, 'supports': match[1].strip()})
        record['evidence'] = evidence
        record['popularity'] = {'current_status': 'not_measured', 'snapshots': []}
        record['cautions'] = bullets(section(body, '使用提示'))
        record['rights'] = {'third_party_media_included': False, 'media_reuse_permission': 'not_established', 'original_explanation_license': 'MIT'}
        records.append(record)
    records.sort(key=lambda r: (-sort_date(r), r['language'], r['id']))
    backlog = []
    for path in sorted((kb / '待核线索').glob('*.md')):
        p, body = read_note(path)
        p.pop('tags', None)
        p['reason'] = section(body, '待核原因')
        backlog.append(p)
    used_sources = {e['source_id'] for r in records for e in r['evidence']}
    sources = [s for s in sources if s['id'] in used_sources]
    pack.update(sources=sources, records=records, backlog=backlog)
    schema = json.loads((root / 'create-funny-meme-cards/references/schemas/knowledge.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(pack)
    source_map = {s['id']: s for s in sources}
    if len(source_map) != len(sources) or len({s['url'] for s in sources}) != len(sources):
        raise ValueError('来源ID或URL重复')
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('条目ID重复')
    for record in records:
        if record['dates']['decade'] != f"{record['dates']['reference_year'] // 10 * 10}s":
            raise ValueError(f"年代不一致：{record['id']}")
        for evidence in record['evidence']:
            source = source_map.get(evidence['source_id'])
            if not source or source['read_method'] == 'search_excerpt':
                raise ValueError(f"{record['id']}: 来源未登记或只有检索摘要，请先放待核线索")
    demos = json.loads((root / 'examples/knowledge-to-copy.json').read_text(encoding='utf-8'))
    if any(d['entry_id'] not in note_ids for d in demos['examples']):
        raise ValueError('演示父条目的原始笔记不存在')
    return pack

def evidence_year(record):
    return int((record.get('recent_evidence_date') or str(record['dates']['reference_year']))[:4])

def sort_date(record):
    value = record.get('recent_evidence_date') or str(record['dates']['reference_year'])
    return int(value.replace('-', '').ljust(8, '0'))

def outputs(root, pack):
    records, sources = pack['records'], pack['sources']
    smap = {s['id']: s for s in sources}
    focus = json.loads((root / '知识库/收集范围.json').read_text(encoding='utf-8'))
    reviews = json.loads((root / '知识库/收录复审.json').read_text(encoding='utf-8'))['entries']
    focus['priority_topic_status'] = [dict(a, state=reviews.get(a.get('entry_id'), {}).get('decision', 'unresolved')) for a in focus.get('user_endorsed_topic_anchors', [])]
    recent = [r for r in records if evidence_year(r) in focus['priority_years']]
    labels = focus['categories']
    counts = dict(sorted(Counter(r['dates']['decade'] for r in records).items(), reverse=True))
    result = {}
    studio = root / 'create-funny-meme-cards/assets/poster-studio'
    styles = json.loads((studio / 'styles.json').read_text(encoding='utf-8'))
    studio_relative = studio.relative_to(root)
    result[studio_relative / 'styles.js'] = 'window.MEME_STYLES = ' + json.dumps(styles, ensure_ascii=False, indent=2) + ';\n'
    images = {s['id']: 'data:image/png;base64,' + base64.b64encode((studio / s['sample']).read_bytes()).decode() for s in styles}
    result[studio_relative / 'samples.js'] = 'window.MEME_SAMPLE_IMAGES = ' + json.dumps(images) + ';\n'
    path = Path('create-funny-meme-cards/assets/knowledge')
    result[path / 'knowledge.json'] = json_text(pack)
    result[path / 'focus.json'] = json_text(focus)
    index = [{'id': r['id'], 'title': r['title'], 'year': r['dates']['reference_year'], 'decade': r['dates']['decade'], 'language': r['language'], 'kind': r['kind'], 'template_family': r['template_family'], 'suitability': r['editorial']['suitability'], 'categories': r['categories'], 'recent_evidence_date': r['recent_evidence_date'], 'social_functions': r['social_use']['functions']} for r in records]
    result[path / 'index.json'] = json_text({'schema_version': pack['schema_version'], 'record_count': len(records), 'entries': index})
    summary = json.loads((root / 'docs/阶段交付清单.json').read_text(encoding='utf-8'))
    summary.update(stage='local_pwa_preview', record_count=len(records), source_count=len(sources), decade_counts=counts, language_counts=dict(Counter(r['language'] for r in records)), obsidian_authoring='knowledge_markdown_is_authoritative', recent_record_count=len(recent), recent_year_counts={str(y): sum(evidence_year(r)==y for r in recent) for y in focus['priority_years']}, category_counts={labels[c]: sum(c in r['categories'] for r in records) for c in labels}, sort='recent_evidence_date_desc', completed=['独立公开版结构','Obsidian笔记主本与可重复导出','中文趣味表达初筛与复审隔离','来源与局限记录','近期优先和倒序浏览','三种单张风格与信息图合集的宿主生图流程及实际样张','昵称辅助和二维码本地生成/校验/合成/PNG导出','个人品牌与作者出处独立配置','本地查询更新与Obsidian收件箱','条目编辑、回收站与版本恢复','PWA安装入口、统一导航与公开资源离线缓存'], release_status='v0.1.0公开PWA预览；用户确认Mac Chrome安装可用；离线与数据维护已自测；公网网站和自动同步未配置')
    result[Path('docs/阶段交付清单.json')] = json_text(summary)
    html = (root / '预览.html').read_text(encoding='utf-8')
    embedded = json.dumps(pack, ensure_ascii=False).replace('<', '\\u003c')
    html = re.sub(r'(<script id="knowledge-data" type="application/json">).*?(</script>)', lambda m: m[1] + embedded + m[2], html, flags=re.S)
    html = re.sub(r'(<script id="focus-data" type="application/json">).*?(</script>)', lambda m: m[1] + json.dumps(focus, ensure_ascii=False) + m[2], html, flags=re.S)
    result[Path('预览.html')] = html
    lines = [f'# 中文趣味表达库：{len(records)}条，其中近三年{len(recent)}条', '', '中文优先，收集2024—2026年好玩热词、梗、趣味黑话/俚语。英文须有大陆流行证据；纯知识概念与海外独热资料不纳入。按有据的最近收录或讨论时间倒序；这一时间不是首创时间，也不代表全网热度排名。', '', '本文件由Obsidian笔记导出，请编辑“知识库”中的笔记。类别允许交叉。', '']
    for r in records:
        shown = r['recent_evidence_date'] or str(r['dates']['reference_year'])
        lines += [f"## {shown} · {r['title']}", '', f"ID：{r['id']}｜{'、'.join(labels[c] for c in r['categories'])}｜{r['language']}｜{r['culture_scope']}", '', f"**含义：**{r['meaning']}", f"**对话场景：**{r['social_use']['trigger']}", f"**你可以说（编辑自拟）：**{r['social_use']['line']}", f"**可选接法（编辑自拟）：**{r['social_use']['follow_up'] or '独立表达，无需接话'}", f"**对象与分寸：**{r['social_use']['audience']}；{r['social_use']['avoid']}", f"**关注依据：**{r['attention_basis']}", f"**资料年份含义：**{r['dates']['grouping_reason']}", f"**编辑解读：**{r['editorial']['humor_mechanism']}", f"**漫画构思：**{r['editorial']['visual_idea']}", f"**使用提示：**{'；'.join(r['cautions'])}"]
        if r.get('ranking_levels'):
            lines += ['', '**等级从高到低（含义为编辑归纳）：**', '', '| 顺位 | 档位 | 含义 |', '|---|---|---|']
            lines += [f"| {l['rank']} | {l['label']} | {l['meaning']} |" for l in r['ranking_levels']]
            lines += ['']
        for e in r['evidence']:
            s = smap[e['source_id']]
            lines += [f"**来源：**[{s['title']}]({s['url']})。{e['supports']}"]
        lines += ['**状态：**来源已读；未统一测量当前热度与喜爱率；素材权利未确认。', '']
    lines += ['## 待核线索（不计入条目数）', '']
    lines += [f"- {b['title']}：{b['reason']}" for b in pack['backlog']]
    result[Path('docs/年代基础包_阅读版.md')] = '\n'.join(lines) + '\n'
    # Sources are also newest-first, while their IDs remain stable.
    ordered_sources = sorted(sources, key=lambda s: (s['published_date'] or '', s['id']), reverse=True)
    lines = [f'# 来源清单：{len(sources)}个页面', '', '按已知页面日期倒序。page_read_prior_seed为此前种子整理时读取，page_read为本轮读取；日期未知列在后面。', '', '| ID | 来源 | 页面日期 | 阅读方式 |', '|---|---|---|---|']
    lines += [f"| {s['id']} | [{s['title']}]({s['url']}) | {s['published_date'] or '未确定'} | {s['read_method']} |" for s in ordered_sources]
    result[Path('docs/来源清单.md')] = '\n'.join(lines) + '\n'
    home = ['# 夸损有梗 · 中文好玩表达', '', '由秋哥发起并整理。收集有趣味、有表达力、值得使用或分享的表达；评价排名、态度表达、黑话趣玩和聊天互动都可，中文优先；英文须有大陆流行证据。重点2024—2026年，历史趣味表达留作补充。笔记是编辑主本，skill数据与网页由它们导出。', '', f'当前共 **{len(records)}条**，其中近三年相关 **{len(recent)}条**，关联 **{len(sources)}个来源**。分类可交叉，不把词典收录或社区票选称作全民喜爱率。', '', '## 先看最近', '', '- [近三年全部 · 最新在前](索引/近三年.md)']
    home += ['', '## 用户点名 · 优先跟进', '']
    for topic in focus['priority_topic_status']:
        label = {'include':'已收录','hold':'复审中','trash':'已移到回收站','unresolved':'待核查'}.get(topic['state'], topic['state'])
        home.append(f"- {topic['title']}：{label}" + (f" · [查看笔记](条目/{topic['entry_id']}.md)" if topic.get('entry_id') in reviews else ''))
    home += ['', '## 按年份查找', '']
    for year in focus['priority_years']:
        n = sum(evidence_year(r)==year for r in recent)
        home.append(f'- [{year}年 · {n}条近期记录](索引/{year}年.md)')
    home += ['', '## 按表达类别查找', '']
    for code,label in labels.items():
        home.append(f"- [{label} · {sum(code in r['categories'] for r in recent)}条近三年资料](索引/{'黑话与俚语' if code=='slang' else label}.md)")
    home += ['', '## 按社交用途查找', '', '[社交用法与选材标准](社交用法与选材标准.md)', '']
    for code,label in focus['social_functions'].items():
        home.append(f'- [{label}](索引/社交-{code}.md)')
    home += ['', '例句为编辑自拟候选，尚未做受众实测；不把梗的热度当作社交效果。', '', '## 最近收录或讨论的表达', '', '| 时间依据 | 表达 | 类别 |', '|---|---|---|']
    for r in recent[:30]:
        home.append(f"| {r['recent_evidence_date'] or r['dates']['reference_year']} | [{r['title']}](条目/{r['id']}.md) | {'、'.join(labels[c] for c in r['categories'])} |")
    home += ['', '## 历史补充 · 从近到远', '']
    for decade in counts:
        home.append(f'- [{decade[:4]}年代](索引/{decade[:4]}年代.md)')
    home += ['- [1960年代 · 网络前史](索引/1960年代.md)', '', '## 编辑与维护', '', '- [收录标准与复审区](归档与复审.md)', '- [海报工坊：三种风格与个人品牌](../create-funny-meme-cards/assets/poster-studio/index.html)', '- [本地工作台：更新、编辑与恢复](../本地工作台.html)', '- [日常更新流程](维护说明.md)', '- [来源索引](索引/来源索引.md)', '- [待核线索](索引/待核线索.md)', '- [新条目模板说明](模板/新条目模板.md)', '- [GitHub同步与发布方案](../docs/Obsidian与GitHub维护方案.md)', '- [项目说明](../README.md)', '', '## 时间与证据', '', '时间指有据的年度收录、词典收录、传播或持续讨论，不等于首次出现。同年内有具体日期的按日期排列，只有年份的保留年份，不猜月日。Obsidian保存不会自动联网、导出或推送GitHub。']
    result[Path('知识库/首页.md')] = '\n'.join(home) + '\n'
    def index_page(title, entries):
        rows = [f'# {title}', '', '按近期证据时间倒序。每项仍保留原有资料年份与来源。', '', '| 最近记录/年度依据 | 条目 | 类别 |', '|---|---|---|']
        rows += [f"| {r['recent_evidence_date'] or r['dates']['reference_year']} | [{r['title']}](../条目/{r['id']}.md) | {'、'.join(labels[c] for c in r['categories'])} |" for r in entries]
        return '\n'.join(rows) + '\n\n[返回首页](../首页.md)\n'
    result[Path('知识库/索引/近三年.md')] = index_page('2024—2026年网络表达', recent)
    for year in focus['priority_years']:
        result[Path(f'知识库/索引/{year}年.md')] = index_page(f'{year}年近期记录', [r for r in recent if evidence_year(r)==year])
    for code,label in labels.items():
        result[Path(f"知识库/索引/{'黑话与俚语' if code=='slang' else label}.md")] = index_page(f'近三年 · {label}', [r for r in recent if code in r['categories']])
    result[Path('知识库/索引/1960年代.md')] = '# 1960年代 · 网络前史\n\n1969年早期ARPANET四节点网络仅作背景，不作为热梗入库。\n\n[Internet Society历史资料](https://www.internetsociety.org/internet/history-internet/brief-history-internet/)\n\n[返回首页](../首页.md)\n'
    for decade in counts:
        result[Path(f'知识库/索引/{decade[:4]}年代.md')] = index_page(decade[:4]+'年代历史补充', [r for r in records if r['dates']['decade']==decade])
    lines = ['# 来源索引', ''] + [f"- {s['published_date'] or '日期未确定'} · [{s['title']}](../来源/{s['id']}.md)" for s in ordered_sources] + ['', '[返回首页](../首页.md)']
    result[Path('知识库/索引/来源索引.md')] = '\n'.join(lines) + '\n'
    lines = ['# 待核线索', '', '不计入来源已核对的条目。'] + [f"- [{b['title']}](../待核线索/{b['id']}.md)" for b in pack['backlog']] + ['', '[返回首页](../首页.md)']
    result[Path('知识库/索引/待核线索.md')] = '\n'.join(lines) + '\n'
    for code, label in focus['social_functions'].items():
        rows = [f'# 社交用法 · {label}', '', '以下是编辑自拟对话候选，尚未做受众实测。按证据时间倒序，包含历史补充。', '']
        for r in records:
            u = r['social_use']
            if code in u['functions']:
                rows += [f"## [{r['title']}](../条目/{r['id']}.md)", '', f"场景：{u['trigger']}", f"你可以说：{u['line']}", f"可选接法：{u['follow_up'] or '独立表达，无需接话'}", f"对象与分寸：{u['audience']}；{u['avoid']}", '']
        rows += ['[返回首页](../首页.md)']
        result[Path(f'知识库/索引/社交-{code}.md')] = '\n'.join(rows) + '\n'
    # Keep earlier index URLs valid while removing held entries from their lists.
    for old in (root / '知识库/索引').glob('*.md'):
        relative = old.relative_to(root)
        if relative not in result:
            result[relative] = '# 此索引已调整\n\n请从[首页](../首页.md)查看中文趣味表达；原始资料见[复审区](../归档与复审.md)。\n'
    # An explicit public allowlist is shared by the worker and validation; API/private files never enter it.
    public = ['app.html','app.css','app-home.js','app-pwa.js','app-pwa.css','offline.html','manifest.webmanifest',
              '预览.html','preview.js','本地工作台.html','workbench.js','workbench.css',
              'pwa/icons/icon.svg','pwa/icons/icon-192.png','pwa/icons/icon-512.png','pwa/icons/apple-touch-icon.png',
              'create-funny-meme-cards/assets/knowledge/knowledge.json','create-funny-meme-cards/assets/knowledge/index.json','create-funny-meme-cards/assets/knowledge/focus.json',
              'create-funny-meme-cards/assets/poster-studio/index.html','create-funny-meme-cards/assets/poster-studio/studio.css',
              'create-funny-meme-cards/assets/poster-studio/studio.js','create-funny-meme-cards/assets/poster-studio/styles.js',
              'create-funny-meme-cards/assets/poster-studio/samples.js','create-funny-meme-cards/assets/poster-studio/vendor/qrcode.js',
              'create-funny-meme-cards/assets/poster-studio/vendor/jsQR.js']
    checksums = {}
    for name in public:
        relative = Path(name)
        payload = result[relative].encode('utf-8') if relative in result else (root / relative).read_bytes()
        checksums[name] = hashlib.sha256(payload).hexdigest()
    template = (root / 'tools/service_worker.template.js').read_text(encoding='utf-8')
    version = hashlib.sha256((template + json_text(checksums)).encode('utf-8')).hexdigest()[:16]
    result[Path('sw.js')] = template.replace('__PWA_VERSION__', json.dumps(version)).replace('__PWA_ASSETS__', json.dumps(public, ensure_ascii=False))
    result[Path('pwa-shell.json')] = json_text({'version':version,'public_resources':checksums,'private_api_cached':False})
    return result

def run(root, check=False):
    pack = load_package(root)
    changed = []
    pending = outputs(root, pack)  # All input/schema/reference validation precedes any write.
    for relative, content in pending.items():
        dest = root / relative
        if not dest.exists() or dest.read_text(encoding='utf-8') != content:
            changed.append(str(relative))
    if check:
        if changed:
            raise ValueError('导出文件不是最新，请先运行构建：' + '、'.join(changed))
    else:
        for relative in changed:
            dest = root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=dest.name, suffix='.tmp', dir=dest.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(pending[Path(relative)])
                os.replace(tmp, dest)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
    return {'mode': 'check' if check else 'build', 'records': len(pack['records']), 'sources': len(pack['sources']), 'changed_files': changed}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Project root, primarily for isolated validation')
    parser.add_argument('--check', action='store_true', help='Validate notes and ensure exports are current without writing')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.root, args.check), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, yaml.YAMLError, ValidationError) as exc:
        raise SystemExit(f'导出未完成：{exc}') from exc
