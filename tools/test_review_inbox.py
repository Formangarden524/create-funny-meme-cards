"""Review and collection regressions on disposable notes; no live model call."""
from pathlib import Path
import json,shutil,tempfile,unittest
from unittest.mock import patch
from local_workbench import Store,Conflict
from review_inbox import ReviewInbox
from auto_collect import Collector

class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='review-test-');self.root=Path(self.tmp.name)/'project'
        shutil.copytree(Path(__file__).resolve().parents[1],self.root,ignore=shutil.ignore_patterns('.venv','.git','__pycache__','私人','采集收件箱'))
        self.store=Store(self.root);self.q=ReviewInbox(self.store)
        self.item={'title':'审核测试梗','meaning':'用于回归的编辑说明','line':'脑子已经下班，身体还在打卡。','scenario':'下班前自嘲','humor':'身体和脑子作息不同','visual':'小人身体打卡，脑子戴墨镜离开','avoid':'友善自嘲，不攻击具体的人','evidence_date':'2026-11-05','source_url':'https://example.com/review-test','source_title':'隔离测试来源','source_support':'测试填写，不是真实梗','source_limitations':'仅用于回归，不证明传播','categories':['meme'],'functions':['self_mock'],'read_method':'page_read'}
    def tearDown(self):self.tmp.cleanup()
    def test_feedback_revision_approval_and_idempotency(self):
        self.assertEqual(self.q.import_batch({'items':[self.item]})['new'],1)
        data=self.q.listing()['items'][0]
        self.assertNotIn(data['draft']['title'],[e['title'] for e in self.store.listing()])
        revised=self.q.action({'id':data['id'],'revision':data['revision'],'action':'revise','feedback':'用法再短一点','edits':{'line':'脑子先下班了。'}})
        self.assertEqual(revised['status'],'needs_revision');self.assertEqual(revised['draft']['line'],'脑子先下班了。')
        bad={**self.item,'id':data['id'],'based_on_revision':data['revision']}
        self.assertEqual(self.q.import_batch({'items':[bad]})['conflicts'],1)
        fix={**self.item,'line':'脑子先下班了。','id':data['id'],'based_on_revision':revised['revision'],'revision_note':'缩短包袱'}
        self.assertEqual(self.q.import_batch({'items':[fix]})['updated'],1)
        updated=self.q.listing()['items'][0]
        with self.assertRaises(Conflict):self.q.action({'id':data['id'],'revision':data['revision'],'action':'approve'})
        approved=self.q.action({'id':data['id'],'revision':updated['revision'],'action':'approve'})
        self.assertEqual(self.store.entry(approved['entry_id'])['decision'],'include')
        again=self.q.action({'id':data['id'],'revision':updated['revision'],'action':'approve'})
        self.assertEqual(again['entry_id'],approved['entry_id'])
        self.assertEqual(len([e for e in self.store.listing() if e['title']==self.item['title']]),1)
    def test_reject_restore_duplicates_and_search_excerpt(self):
        with self.assertRaises(ValueError):self.q.import_batch({'items':[{**self.item,'read_method':'search_excerpt'}]})
        self.assertEqual(self.q.listing()['items'],[])
        self.assertEqual(self.q.import_batch({'items':[{**self.item,'title':'班味'}]})['duplicates'],1)
        self.q.import_batch({'items':[self.item]});data=self.q.listing()['items'][0]
        rejected=self.q.action({'id':data['id'],'revision':data['revision'],'action':'reject','feedback':'不好玩'})
        self.assertEqual(self.q.import_batch({'items':[self.item]})['preserved'],1)
        with self.assertRaises(ValueError):self.q.action({'id':data['id'],'revision':rejected['revision'],'action':'approve'})
        restored=self.q.action({'id':data['id'],'revision':rejected['revision'],'action':'restore'})
        self.assertEqual(restored['status'],'pending')
        self.assertTrue((self.store.kb/'私人/审核历史'/data['id']).exists())
    def test_runner_validates_and_does_not_publish(self):
        def fake_run(command,**kwargs):
            output=Path(command[command.index('--output-last-message')+1]);output.write_text(json.dumps({'coverage':'测试源','items':[self.item]}))
            self.assertIn('--sandbox',command);self.assertIn('read-only',command);self.assertIn('--ignore-user-config',command)
            return type('Result',(),{'returncode':0})()
        with patch.object(Collector,'executable',return_value='/fake/codex'), patch('auto_collect.subprocess.run',side_effect=fake_run):state=Collector(self.store).run(1)
        self.assertEqual(state['status'],'completed');self.assertEqual(state['counts']['new'],1)
        self.assertFalse(any(e['title']==self.item['title'] for e in self.store.listing()))
        with patch.object(Collector,'executable',return_value='/fake/codex'), patch('auto_collect.subprocess.run',return_value=type('Result',(),{'returncode':2})()):failed=Collector(self.store).run(1)
        self.assertEqual(failed['status'],'failed')

if __name__=='__main__':unittest.main(verbosity=2)
