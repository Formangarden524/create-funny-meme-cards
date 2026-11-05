"""Exercise edits/recovery on a disposable copy, never the user's source notes."""
from pathlib import Path
import json
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from local_workbench import Store, Conflict, make_server

class WorkbenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='meme-workbench-test-')
        cls.root=Path(cls.tmp.name)/'project'
        shutil.copytree(Path(__file__).resolve().parents[1],cls.root,ignore=shutil.ignore_patterns('.venv','.git','__pycache__','私人','采集收件箱'))
        cls.store=Store(cls.root)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def test_edit_conflict_validation_and_version_restore(self):
        s=self.store;e=s.entry('cn-how-so-what')
        bad=e['markdown'].replace('## 含义','## 缺失含义')
        with self.assertRaises(ValueError):s.change('edit',e['id'],e['revision'],bad)
        self.assertEqual(s.entry(e['id'])['markdown'],e['markdown'])
        valid=e['markdown'].replace('## 含义','## 含义\n\n本地编辑测试说明。')
        updated=s.change('edit',e['id'],e['revision'],valid)
        self.assertEqual(updated['markdown'],valid)
        with self.assertRaises(Conflict):s.change('edit',e['id'],e['revision'],e['markdown'])
        old=next(v for v in s.history(e['id']) if v['markdown']==e['markdown'])
        restored=s.change('restore-version',e['id'],updated['revision'],version=old['version'])
        self.assertEqual(restored['markdown'],e['markdown'])
        self.assertTrue(any(v['markdown']==valid for v in s.history(e['id'])))
    def test_trash_restore_and_demo_parent(self):
        s=self.store
        for id in ['cn-diving','cn-embodied-term']:
            e=s.entry(id);deleted=s.change('delete',id,e['revision'])
            self.assertEqual(deleted['decision'],'trash')
            self.assertNotIn(id,[r['id'] for r in __import__('build_from_obsidian').load_package(self.root)['records']])
            self.assertTrue((s.kb/'私人/回收站'/f'{id}.md').is_file())
            restored=s.change('restore',id,deleted['revision'])
            self.assertEqual(restored['markdown'],e['markdown'])
            self.assertEqual(restored['decision'],e['decision'])
    def test_search_seen_state_and_pending(self):
        s=self.store
        def feed(provider,query):
            return [{'id':'candidate-1234567890abcdef','title':'班味也能玩出反差','url':'https://example.com/test-meme','published_at':None,'provider':provider,'read_status':'search_feed_only'}]
        with patch.object(Store,'fetch_rss',side_effect=feed):
            a=s.search('趣味表达');b=s.search('趣味表达')
        self.assertEqual(a['new_count'],1);self.assertEqual(b['new_count'],0)
        self.assertEqual(a['candidates'][0]['matched_entry_ids'],['cn-work-smell'])
        saved=s.pending(a['id'],a['candidates'][0]['id'])
        self.assertTrue((self.root/saved['path']).exists())
        self.assertIn('尚未读取原页',(self.root/saved['path']).read_text())
        with patch.object(Store,'fetch_rss',side_effect=OSError('offline')):
            failed=s.search('趣味表达')
        self.assertEqual(failed['status'],'failed');self.assertEqual(len(failed['errors']),2)
        self.assertTrue((s.kb/'采集收件箱'/f'{failed["id"]}.md').exists())
    def test_levels_and_priority_topic_recovery(self):
        s=self.store;e=s.entry('cn-hang-to-la')
        bad=e['markdown'].replace('| 3 |', '| 9 |')
        with self.assertRaises(ValueError):s.change('edit',e['id'],e['revision'],bad)
        self.assertEqual(s.entry(e['id'])['markdown'],e['markdown'])
        deleted=s.change('delete',e['id'],e['revision'])
        focus=json.loads((self.root/'create-funny-meme-cards/assets/knowledge/focus.json').read_text())
        self.assertEqual(next(t for t in focus['priority_topic_status'] if t['entry_id']==e['id'])['state'],'trash')
        s.change('restore',e['id'],deleted['revision'])
        pack=__import__('build_from_obsidian').load_package(self.root)
        levels=next(r for r in pack['records'] if r['id']==e['id'])['ranking_levels']
        self.assertEqual([l['label'] for l in levels],['夯','顶级','人上人','NPC','拉（拉完了）'])

    def test_manual_create_draft_checked_entry_and_rollback(self):
        s=self.store
        basic={'title':'新增测试草稿','meaning':'隔离副本里的趣味表达','line':'今天的脑子正在加载。','decision':'hold'}
        draft=s.create(basic)
        self.assertEqual(draft['decision'],'hold')
        self.assertTrue((self.root/draft['path']).is_file())
        self.assertNotIn(draft['id'],[r['id'] for r in __import__('build_from_obsidian').load_package(self.root)['records']])
        with self.assertRaises(Conflict):s.create(basic)
        invalid={**basic,'title':'新增不完整正式条目','decision':'include'}
        before=s.review_path.read_text()
        with self.assertRaises(ValueError):s.create(invalid)
        self.assertEqual(before,s.review_path.read_text())
        checked={**basic,'title':'新增测试正式条目','decision':'include','scenario':'朋友聊天时自嘲状态','humor':'把脑子当作加载中的网页','visual':'小人头顶一个进度条','evidence_date':'2026-11-05','source_url':'https://example.com/manual-create-test','source_title':'测试来源，仅用于隔离回归','source_support':'测试用字段，不是真实收录','source_limitations':'测试网址不代表真实传播证据','source_checked':True}
        record=s.create(checked)
        pack=__import__('build_from_obsidian').load_package(self.root)
        self.assertIn(record['id'],[r['id'] for r in pack['records']])
        self.assertEqual(len([x for x in pack['sources'] if x['url']==checked['source_url']]),1)
        again=s.create({**checked,'title':'同来源另一测试表达'})
        pack=__import__('build_from_obsidian').load_package(self.root)
        self.assertEqual(len([x for x in pack['sources'] if x['url']==checked['source_url']]),1)
        before_review=s.review_path.read_text();before_notes=set((self.root/'知识库/条目').glob('*.md'));before_sources=set((self.root/'知识库/来源').glob('*.md'))
        with patch('local_workbench.build.outputs',side_effect=ValueError('模拟导出失败')):
            with self.assertRaises(ValueError):s.create({**checked,'title':'导出失败测试','source_url':'https://example.com/rollback'})
        self.assertEqual(before_review,s.review_path.read_text())
        self.assertEqual(before_notes,set((self.root/'知识库/条目').glob('*.md')))
        self.assertEqual(before_sources,set((self.root/'知识库/来源').glob('*.md')))
        deleted=s.change('delete',record['id'],record['revision'])
        restored=s.change('restore',record['id'],deleted['revision'])
        self.assertEqual(restored['decision'],'include')

    def test_http_origin_token_and_private_files(self):
        server=make_server(self.root,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def req(path,headers=None,data=None):
            return urlopen(Request(base+path,headers=headers or {},data=data),timeout=5)
        try:
            with req('/') as r:self.assertIn('今天，来点有梗的。',r.read().decode())
            with req('/manifest.webmanifest') as r:self.assertEqual(json.load(r)['start_url'],'./预览.html')
            with req('/app.html?view=about') as r:self.assertIn('项目说明',r.read().decode())
            with req('/api/bootstrap') as r:token=json.load(r)['token']
            with req('/api/review-inbox') as r:self.assertIn('items',json.load(r))
            with req('/api/collect-status') as r:self.assertIn('status',json.load(r))
            with patch('auto_collect.Collector.start',return_value={'status':'running'}):
                with req('/api/collect-start',{'Content-Type':'application/json','X-Workbench-Token':token},b'{"limit":2}') as r:self.assertEqual(json.load(r)['status'],'running')
            with self.assertRaises(HTTPError) as cm:req('/api/rebuild',{'Content-Type':'application/json'},b'{}')
            self.assertEqual(cm.exception.code,403);cm.exception.close()
            with self.assertRaises(HTTPError) as cm:req('/api/bootstrap',{'Origin':'https://example.com'})
            self.assertEqual(cm.exception.code,403);cm.exception.close()
            with self.assertRaises(HTTPError) as cm:req('/api/bootstrap',{'Host':'evil.example'})
            self.assertEqual(cm.exception.code,403);cm.exception.close()
            with self.assertRaises(HTTPError) as cm:req('/%E7%9F%A5%E8%AF%86%E5%BA%93/%E7%A7%81%E4%BA%BA/test.md')
            self.assertEqual(cm.exception.code,403);cm.exception.close()
            with req('/api/rebuild',{'Content-Type':'application/json','X-Workbench-Token':token},b'{}') as r:
                self.assertIn('records',json.load(r))
        finally:server.shutdown();server.server_close();thread.join()
        with self.assertRaises(ValueError):self.store.entry('../bad')

if __name__=='__main__':unittest.main(verbosity=2)
