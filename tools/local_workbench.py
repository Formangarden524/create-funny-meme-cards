"""Loopback-only Obsidian workbench; Markdown is the authoritative store."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, unquote, parse_qs, urlencode
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
import argparse
import hashlib
import html
import json
import mimetypes
import re
import secrets
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
import webbrowser
import yaml
import build_from_obsidian as build

TZ = ZoneInfo('Asia/Shanghai')
ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,100}$')

class Conflict(ValueError): pass

def digest(text): return hashlib.sha256(text.encode()).hexdigest()
def now(): return datetime.now(TZ).isoformat(timespec='seconds')
def stamp(): return datetime.now(TZ).strftime('%Y%m%d-%H%M%S-') + str(time.time_ns())[-8:]
def encode(value): return json.dumps(value, ensure_ascii=False, indent=2) + '\n'
def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + secrets.token_hex(5) + '.tmp')
    try:
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
def note(props, body): return '---\n' + yaml.safe_dump(props, allow_unicode=True, sort_keys=False) + '---\n\n' + body + '\n'
def props(path):
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---\n'): raise ValueError('笔记缺少YAML属性')
    return yaml.safe_load(text.split('---\n', 2)[1])

class Store:
    def __init__(self, root):
        self.root = root.resolve()
        self.kb = self.root / '知识库'
        self.lock = threading.RLock()
        self.search_lock = threading.Lock()
        self.review_path = self.kb / '收录复审.json'
    def reviews(self): return json.loads(self.review_path.read_text(encoding='utf-8'))
    def entry_path(self, id):
        if not isinstance(id, str) or not ID.fullmatch(id): raise ValueError('无效条目ID')
        p = self.kb / '条目' / (id + '.md')
        if p.is_symlink() or p.resolve().parent != (self.kb / '条目').resolve(): raise ValueError('不允许链接或越界路径')
        if not p.is_file(): raise ValueError('条目不存在')
        return p
    def entry(self, id):
        with self.lock:
            p = self.entry_path(id)
            raw = p.read_text(encoding='utf-8')
            review = self.reviews()['entries'][id]
            return {'id': id, 'markdown': raw, 'revision': digest(raw), 'decision': review['decision'], 'title': props(p)['title'], 'path': str(p.relative_to(self.root)), 'deleted_on': review.get('deleted_on')}
    def listing(self):
        with self.lock:
            review = self.reviews()['entries']
            pack = build.load_package(self.root)
            records = {r['id']: r for r in pack['records']}
            entries = []
            for id, r in review.items():
                e = self.entry(id)
                e.pop('markdown')
                e['functions'] = records.get(id, {}).get('social_use', {}).get('functions', [])
                e['evidence_date'] = records.get(id, {}).get('recent_evidence_date')
                entries.append(e)
            entries.sort(key=lambda e: (e['evidence_date'] or '', e['id']), reverse=True)
            return entries
    def snapshot(self, id, raw):
        version = stamp()
        atomic(self.kb / '私人/编辑历史' / id / (version + '.md'), raw)
        return version
    def history(self, id):
        self.entry_path(id)
        return [{'version': p.stem, 'markdown': p.read_text(encoding='utf-8')} for p in sorted((self.kb / '私人/编辑历史' / id).glob('*.md'), reverse=True)]
    def change(self, action, id, revision, markdown=None, version=None):
        with self.lock:
            e = self.entry(id)
            if revision != e['revision']: raise Conflict('笔记已被Obsidian或另一个窗口修改，请重新打开后再操作。')
            p = self.entry_path(id)
            old_raw = e['markdown']
            old_review = self.review_path.read_text(encoding='utf-8')
            review = json.loads(old_review)
            state = review['entries'][id]
            trash = self.kb / '私人/回收站' / (id + '.md')
            old_trash = trash.read_text(encoding='utf-8') if trash.exists() else None
            if action == 'restore':
                if state['decision'] != 'trash' or old_trash is None: raise ValueError('此条目不在回收站')
                new_raw = old_trash
                state['decision'] = state.pop('previous_decision', 'include')
                state.pop('deleted_on', None)
            elif action == 'delete':
                if state['decision'] == 'trash': raise ValueError('此条目已在回收站')
                atomic(trash, old_raw)
                state['previous_decision'] = state['decision']
                state['decision'] = 'trash'
                state['deleted_on'] = now()
                new_raw = note({'id': id, 'title': e['title'], 'status': 'trash'}, f'# {e["title"]}（已移到回收站）\n\n正文保存在[本地回收站](../私人/回收站/{id}.md)，可从本地工作台恢复。\n\n[返回首页](../首页.md)')
            elif action in {'edit', 'restore-version'}:
                if state['decision'] == 'trash': raise ValueError('请先从回收站恢复')
                if action == 'restore-version':
                    if not isinstance(version, str) or not re.fullmatch(r'[0-9-]{10,60}', version): raise ValueError('版本号无效')
                    hp = self.kb / '私人/编辑历史' / id / (version + '.md')
                    if not hp.is_file(): raise ValueError('历史版本不存在')
                    markdown = hp.read_text(encoding='utf-8')
                if not isinstance(markdown, str) or len(markdown) > 150_000: raise ValueError('笔记为空或过大')
                new_raw = markdown
            else: raise ValueError('未知操作')
            try:
                if action != 'restore': self.snapshot(id, old_raw)
                atomic(p, new_raw)
                atomic(self.review_path, encode(review))
                build.run(self.root)
            except Exception:
                atomic(p, old_raw)
                atomic(self.review_path, old_review)
                if old_trash is None: trash.unlink(missing_ok=True)
                else: atomic(trash, old_trash)
                build.run(self.root)
                raise
            if action == 'restore': trash.unlink(missing_ok=True)
            return self.entry(id)
    def create(self, data):
        if not isinstance(data, dict): raise ValueError('新增资料格式无效')
        def field(key, required=False, limit=2000):
            value=data.get(key, '')
            if not isinstance(value, str) or len(value)>limit: raise ValueError('字段过长或格式无效：'+key)
            value=value.strip()
            if required and not value: raise ValueError('请填写：'+key)
            if re.search(r'^#{1,3} |^---$',value,re.M): raise ValueError('表单里请填写普通文字，不要插入Markdown标题或属性分隔线')
            return value
        title=field('title',True,60);meaning=field('meaning',True);line=field('line',True,500)
        decision=data.get('decision','hold')
        if decision not in {'include','hold'}: raise ValueError('请选择复审草稿或加入首页')
        include=decision=='include'
        scenario=field('scenario',include,500) or '待补充具体使用场景'
        humor=field('humor',include) or '待补充笑点分析'
        visual=field('visual',include) or '待补充画面构思'
        avoid=field('avoid',False,500) or '根据关系和语境适度使用；自拟用法不代表流行原句或受众验证。'
        categories=data.get('categories',['meme']);functions=data.get('functions',['self_mock'])
        if not isinstance(categories,list) or not categories or any(c not in {'hotword','meme','slang'} for c in categories): raise ValueError('请选择有效表达类别')
        if not isinstance(functions,list) or not functions or any(f not in {'reply','tease','self_mock','praise','bond','rating','stance','jargon'} for f in functions): raise ValueError('请选择有效社交用途')
        evidence_date=field('evidence_date',include,10)
        today=datetime.now(TZ).date()
        if evidence_date:
            try: day=datetime.strptime(evidence_date,'%Y-%m-%d').date()
            except ValueError: raise ValueError('日期请用YYYY-MM-DD')
            if day>today or day.year<1960: raise ValueError('资料日期不能在未来，也不能早于1960年')
        else: day=today
        source_url=field('source_url',include,2000)
        if source_url:
            u=urlsplit(source_url)
            if u.scheme not in {'http','https'} or not u.hostname or u.username or u.password: raise ValueError('来源网址须为无账号密码的完整http或https链接')
        source_title=field('source_title',include,300)
        support=field('source_support',include)
        limitation=field('source_limitations',include)
        if include and data.get('source_checked') is not True: raise ValueError('加入首页前，请确认已阅读来源、核对含义与中文趣味使用场景')
        with self.lock:
            normalized=lambda v: re.sub(r'\s+','',v).casefold()
            for id, state in self.reviews()['entries'].items():
                meta=props(self.entry_path(id))
                if normalized(title) in [normalized(t) for t in [meta['title'],*meta.get('aliases',[])]]:
                    raise Conflict('已有同名或别名条目“'+meta['title']+'”；请编辑原条目，或从回收站恢复。')
            id='cn-user-'+secrets.token_hex(6)
            path=self.kb/'条目'/(id+'.md')
            old_review=self.review_path.read_text(encoding='utf-8');review=json.loads(old_review)
            source_ids=[];new_source=None;source_body=None
            if include:
                for sp in (self.kb/'来源').glob('*.md'):
                    if props(sp)['url']==source_url: source_ids=[sp.stem];break
                if not source_ids:
                    sid='source-user-'+secrets.token_hex(6);source_ids=[sid]
                    new_source=self.kb/'来源'/(sid+'.md')
                    source_body=note({'id':sid,'title':source_title,'url':source_url,'type':'secondary','published_date':None,'accessed_on':today.isoformat(),'read_method':'page_read','locator':None},'# '+source_title+'\n\n用户在新增表单中确认已阅读来源；程序未代为访问或核实原页。\n\n## 来源限制\n\n'+limitation+'\n\n[返回知识库首页](../首页.md)')
            metadata={'id':id,'title':title,'aliases':[],'kind':'phrase_template','language':'zh-CN','culture_scope':'中国大陆中文生活语境（用户录入）','template_family':id,'review_status':'source_checked' if include else 'pending','reference_year':day.year,'decade':str(day.year//10*10)+'s','grouping_reason':'用户填写的有据讨论日期；不是首创日期。' if evidence_date else '草稿录入年份，尚未核实传播时间，不进入首页。','original_work_date':None,'documented_event_date':None,'popularized_date':None,'origin_status':'not_fully_verified','suitability':'adapt','source_ids':source_ids,'tags':['夸损有梗','手动新增'],'focus_categories':categories,'recent_evidence_date':evidence_date or None,'social_use':{'functions':functions,'audience':'中文生活社交用户；需结合具体对象与关系','trigger':scenario,'line':line,'follow_up':None,'avoid':avoid,'evidence_status':'editorial_example_not_audience_tested'}}
            body='# '+title+'\n\n## 含义\n\n'+meaning+'\n\n## 关注依据\n\n用户手动录入'+('并确认已阅读来源；程序未另行核查。' if include else '，待复审核查；不显示在资料首页。')+'未测量实时热度。\n\n## 笑点机制\n\n'+humor+'\n\n## 漫画构思\n\n'+visual+'\n\n## 使用场景\n\n- '+scenario.replace('\n',' ')+'\n\n## 使用提示\n\n- '+avoid.replace('\n',' ')+'\n\n## 证据支持范围\n\n'
            body+=('### '+source_ids[0]+'\n\n'+support) if source_ids else '待核查；草稿没有被视为已读来源条目。'
            if source_url: body+='\n\n## 待核或补充来源\n\n'+source_url+'\n\n'+source_title+'\n\n'+support+'\n\n'+limitation
            body+='\n\n[返回知识库首页](../首页.md)'
            review['entries'][id]={'decision':decision,'reason':'用户手动录入并确认来源与趣味用途' if include else '手动新增草稿，等待来源与趣味语境复审','mainland_usage_evidence':[]}
            created=[]
            try:
                # Exclusive creation never overwrites a note or follows a preexisting symlink.
                for dest, raw in ([(new_source,source_body)] if new_source else [])+[(path,note(metadata,body))]:
                    with dest.open('x',encoding='utf-8') as out: out.write(raw)
                    created.append(dest)
                atomic(self.review_path,encode(review))
                build.run(self.root)
            except Exception:
                for dest in created: dest.unlink(missing_ok=True)
                atomic(self.review_path,old_review)
                build.run(self.root)
                raise
            return self.entry(id)
    def runs(self):
        with self.lock:
            return [props(p) for p in sorted((self.kb / '采集收件箱').glob('*.md'), reverse=True)][:30]
    @staticmethod
    def fetch_rss(provider, query):
        if provider == 'google_news':
            url = 'https://news.google.com/rss/search?' + urlencode({'q': query + ' when:7d', 'hl': 'zh-CN', 'gl': 'CN', 'ceid': 'CN:zh-Hans'})
        else:
            url = 'https://www.bing.com/search?' + urlencode({'q': query, 'format': 'rss', 'setlang': 'zh-hans', 'cc': 'cn'})
        # Native curl follows the working network route on macOS; urllib is the portable fallback.
        curl = shutil.which('curl')
        if curl:
            response = subprocess.run([curl, '--fail', '--location', '--silent', '--show-error', '--connect-timeout', '8', '--max-time', '18', '--max-filesize', '2000000', '--url', url], capture_output=True, timeout=22)
            if response.returncode:
                raise OSError(response.stderr.decode(errors='replace')[:180])
            payload = response.stdout
        else:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 MemeObsidianWorkbench/0.1'})
            with urlopen(req, timeout=18) as response:
                payload = response.read(2_000_001)
        if len(payload) > 2_000_000: raise ValueError('检索源响应过大')
        if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper(): raise ValueError('不支持的XML声明')
        tree = ET.fromstring(payload)
        result = []
        for item in tree.findall('.//item')[:25]:
            title = re.sub(r'\s+', ' ', html.unescape(item.findtext('title') or '')).strip()
            link = (item.findtext('link') or '').strip()
            if not title or urlsplit(link).scheme not in {'http','https'}: continue
            published = None
            raw_date = item.findtext('pubDate')
            if raw_date:
                try: published = parsedate_to_datetime(raw_date).astimezone(TZ).isoformat()
                except (ValueError, TypeError, OverflowError): pass
            result.append({'id': 'candidate-' + hashlib.sha256(link.encode()).hexdigest()[:16], 'title': title[:400], 'url': link, 'published_at': published, 'provider': provider, 'read_status': 'search_feed_only'})
        return result
    def search(self, query):
        if not isinstance(query, str) or not query.strip() or len(query) > 100: raise ValueError('请输入1—100字检索词')
        if not self.search_lock.acquire(blocking=False): raise Conflict('查询正在进行，请等本轮完成')
        try:
            errors, items = [], []
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {p: pool.submit(self.fetch_rss, p, query.strip()) for p in ['google_news','bing_rss']}
                for provider, future in futures.items():
                    try: items.extend(future.result())
                    except Exception as ex: errors.append({'provider': provider, 'message': type(ex).__name__ + ': ' + str(ex)[:160]})
            with self.lock:
                previous = {c['id']:c.get('first_seen') for p in sorted((self.kb / '采集收件箱').glob('*.md'), reverse=True) for c in props(p).get('candidates', [])}
                pack = build.load_package(self.root)
                unique = {}
                for c in items:
                    if c['id'] in unique: continue
                    matches = [r['id'] for r in pack['records'] if any(len(t)>=2 and t.casefold() in c['title'].casefold() for t in [r['title'], *r['aliases']])]
                    c.update(first_seen=previous.get(c['id']) or now(), is_new=c['id'] not in previous, matched_entry_ids=matches)
                    unique[c['id']] = c
                candidates = sorted(unique.values(), key=lambda c: c['published_at'] or '', reverse=True)
                run = {'id': 'scan-' + stamp(), 'queried_at': now(), 'query': query.strip(), 'status': 'partial' if errors and candidates else ('failed' if errors else 'success'), 'errors': errors, 'candidates': candidates, 'new_count': sum(c['is_new'] for c in candidates)}
                body = '# 查询更新记录\n\n新发现指此前查询未见的链接，不等于梗首次出现或实时热度最高。条目均为检索线索，原页未核查；不自动进入正式库。\n\n'
                body += '\n'.join(f'- [{c["title"]}]({c["url"]}) · {c["published_at"] or "来源日期未知"} · {"新发现线索" if c["is_new"] else "此前已见"}' for c in candidates)
                atomic(self.kb / '采集收件箱' / (run['id'] + '.md'), note(run, body))
                return run
        finally: self.search_lock.release()
    def pending(self, run_id, candidate_id):
        if not isinstance(run_id, str) or not re.fullmatch(r'scan-[0-9-]+', run_id): raise ValueError('无效查询记录')
        with self.lock:
            run_path = self.kb / '采集收件箱' / (run_id + '.md')
            if not run_path.is_file(): raise ValueError('查询记录不存在')
            candidate = next((c for c in props(run_path)['candidates'] if c['id']==candidate_id), None)
            if not candidate: raise ValueError('候选不存在')
            id = 'pending-' + candidate['id'].removeprefix('candidate-')
            path = self.kb / '待核线索' / (id + '.md')
            if not path.exists():
                atomic(path, note({'id':id,'title':candidate['title'],'candidate_period':candidate['published_at'] or '待核','status':'pending','clue_urls':[candidate['url']]}, '# ' + candidate['title'] + '\n\n## 待核原因\n\n联网检索发现；只读取RSS检索结果，尚未读取原页、提取具体表达或核实大陆传播与趣味用途。请核查后再转正式条目。\n\n## 导航\n\n[返回首页](../首页.md)'))
                try: build.run(self.root)
                except Exception:
                    path.unlink()
                    raise
            return {'id':id,'path':str(path.relative_to(self.root))}

class Handler(BaseHTTPRequestHandler):
    server_version = 'MemeLocal/0.1'
    def log_message(self, fmt, *args): pass
    def allowed(self):
        port = self.server.server_port
        if self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}: return False
        origin = self.headers.get('Origin')
        return not origin or origin in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'}
    def respond(self, value, status=200):
        raw = encode(value).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if not self.allowed(): return self.respond({'error':'仅允许本机同源访问'},403)
        path = unquote(urlsplit(self.path).path)
        query = parse_qs(urlsplit(self.path).query)
        store = self.server.store
        try:
            if path == '/api/bootstrap': return self.respond({'token':self.server.token,'storage':'Obsidian Markdown','vault_path':str(store.kb),'local_time':now()})
            if path == '/api/entries': return self.respond({'entries':store.listing()})
            if path == '/api/entry': return self.respond(store.entry(query.get('id',[''])[0]))
            if path == '/api/history': return self.respond({'versions':store.history(query.get('id',[''])[0])})
            if path == '/api/runs': return self.respond({'runs':store.runs()})
            if path.startswith('/api/'): return self.respond({'error':'接口不存在'},404)
            relative = path.lstrip('/') or '预览.html'
            parts = Path(relative).parts
            if any(p.startswith('.') or p in {'私人','采集收件箱','private','runtime','outputs','__pycache__','tools','config'} for p in parts): return self.respond({'error':'此目录不公开服务'},403)
            target = (store.root / relative).resolve()
            if not target.is_relative_to(store.root) or not target.is_file(): return self.respond({'error':'文件不存在'},404)
            if any(p.startswith('.') or p in {'私人','采集收件箱','private','runtime','outputs','__pycache__','tools','config'} for p in target.relative_to(store.root).parts): return self.respond({'error':'此目录不公开服务'},403)
            raw = target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',(mimetypes.guess_type(str(target))[0] or 'application/octet-stream') + ('; charset=utf-8' if target.suffix in {'.html','.js','.css','.md','.json'} else ''))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except Exception as ex: self.respond({'error':str(ex)},400)
    def do_POST(self):
        if not self.allowed() or self.headers.get('X-Workbench-Token') != self.server.token: return self.respond({'error':'需要本地页面授权令牌'},403)
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 200_000: raise ValueError('请求为空或过大')
            if not self.headers.get('Content-Type','').startswith('application/json'): raise ValueError('仅接受JSON请求')
            data = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            if path == '/api/search': result = self.server.store.search(data.get('query'))
            elif path == '/api/create': result = self.server.store.create(data)
            elif path == '/api/pending': result = self.server.store.pending(data.get('run_id'),data.get('candidate_id'))
            elif path in {'/api/edit','/api/delete','/api/restore','/api/restore-version'}:
                result = self.server.store.change(path.removeprefix('/api/'), data.get('id'), data.get('revision'), markdown=data.get('markdown'), version=data.get('version'))
            elif path == '/api/rebuild':
                with self.server.store.lock: result = build.run(self.server.store.root)
            else: return self.respond({'error':'接口不存在'},404)
            self.respond(result)
        except Conflict as ex: self.respond({'error':str(ex)},409)
        except Exception as ex: self.respond({'error':str(ex)},400)

def make_server(root, port=17861):
    server = ThreadingHTTPServer(('127.0.0.1',port), Handler)
    server.store = Store(root)
    server.token = secrets.token_urlsafe(32)
    return server

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--port',type=int,default=17861)
    parser.add_argument('--open',action='store_true',help='Open local UI after binding')
    args=parser.parse_args()
    build.load_package(args.root)
    try:
        server = make_server(args.root,args.port)
    except OSError as ex:
        if args.open and ex.errno in {48,98}:
            print(f'端口已在使用，打开现有本地页面：http://127.0.0.1:{args.port}/',flush=True)
            webbrowser.open(f'http://127.0.0.1:{args.port}/')
            raise SystemExit(0)
        raise SystemExit(f'本地服务未能启动：{ex}')
    with server:
        print(f'本地工作台：http://127.0.0.1:{server.server_port}/ · Ctrl+C停止',flush=True)
        if args.open: webbrowser.open(f'http://127.0.0.1:{server.server_port}/')
        try: server.serve_forever()
        except KeyboardInterrupt: print('本地服务已停止；已缓存资料与海报工具仍可使用。',flush=True)
