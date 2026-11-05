"""Run bounded read-only Codex research, validate proposals, never auto-publish."""
from pathlib import Path
from datetime import datetime
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import threading
from local_workbench import Store, Conflict, now, stamp, atomic, encode, props
from review_inbox import ReviewInbox

class Collector:
    def __init__(self, store):
        self.store=store;self.folder=store.kb/'私人/自动收集'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.state=self.folder/'status.json'
    @staticmethod
    def executable():
        return shutil.which('codex') or next((p for p in ['/opt/homebrew/bin/codex','/usr/local/bin/codex'] if Path(p).is_file()),None)
    def status(self):
        data=json.loads(self.state.read_text()) if self.state.exists() else {'status':'idle'}
        if data.get('status')=='running':
            try: os.kill(data.get('owner_pid',0),0)
            except (ProcessLookupError,PermissionError):
                data.update(status='interrupted',error='上次任务进程已退出，可以重新启动。');atomic(self.state,encode(data))
        schedule=self.folder/'schedule.json'
        data['schedule']=json.loads(schedule.read_text()) if schedule.exists() else None
        data['available']=bool(self.executable())
        return data
    def start(self, limit=5):
        if not isinstance(limit,int) or not 1<=limit<=8: raise ValueError('每批数量须为1—8')
        if not self.executable(): raise ValueError('这台电脑未找到Codex CLI，请先安装并登录；不会返回模拟草稿')
        queue=ReviewInbox(self.store)
        with queue.locked():
            if self.status()['status']=='running': raise Conflict('自动收集正在运行，请等待本轮完成')
            job={'id':'collect-'+stamp(),'status':'running','started_at':now(),'owner_pid':os.getpid(),'requested_count':limit}
            atomic(self.state,encode(job))
        thread=threading.Thread(target=self._worker,args=(job,limit),daemon=True);thread.start()
        return self.status()
    def run(self, limit=5):
        if not self.executable(): raise ValueError('未找到Codex CLI，请安装并登录后重试')
        if not isinstance(limit,int) or not 1<=limit<=8: raise ValueError('每批数量须为1—8')
        queue=ReviewInbox(self.store)
        with queue.locked():
            if self.status()['status']=='running': raise Conflict('自动收集正在运行')
            job={'id':'collect-'+stamp(),'status':'running','started_at':now(),'owner_pid':os.getpid(),'requested_count':limit}
            atomic(self.state,encode(job))
        self._worker(job,limit)
        return self.status()
    def _worker(self, job, limit):
        try:
            queue=ReviewInbox(self.store);inbox=queue.listing()['items']
            known=[{'title':props(p)['title'],'aliases':props(p).get('aliases',[])} for p in (self.store.kb/'条目').glob('*.md')]
            # Only public expression names and relevant local review feedback enter model context.
            context={'today':now()[:10],'known_expressions':known,'do_not_repeat':[x['draft']['title'] for x in inbox if x['status']!='needs_revision'],'revision_requests':[{'id':x['id'],'based_on_revision':x['revision'],'draft':x['draft'],'history':x['history'][-5:]} for x in inbox if x['status']=='needs_revision'][:8]}
            instructions=(self.store.root/'tools/自动收集任务.md').read_text()
            with tempfile.TemporaryDirectory(prefix='meme-collector-') as tmp:
                work=Path(tmp);(work/'context.json').write_text(encode(context));schema=work/'output.schema.json';shutil.copyfile(self.store.root/'tools/collector-output.schema.json',schema)
                result=work/'result.json';prompt=instructions+'\n本次最多新增'+str(limit)+'条，优先处理修改意见。请读取当前目录context.json；最终只返回符合schema的JSON。'
                command=[self.executable(),'exec','--ignore-user-config','--ephemeral','--sandbox','read-only','--skip-git-repo-check','-c','web_search="live"','--output-schema',str(schema),'--output-last-message',str(result),'-C',str(work),'-']
                with (self.folder/(job['id']+'.log')).open('w') as log:
                    completed=subprocess.run(command,input=prompt,text=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
                if completed.returncode: raise RuntimeError('AI采集未成功退出，请查看本地自动收集日志或确认Codex登录和网络；未发布任何条目。')
                if not result.exists() or result.stat().st_size>200000: raise ValueError('未取得有效的结构化候选')
                payload=json.loads(result.read_text());stats=queue.import_batch(payload)
                job.update(status='completed',completed_at=now(),counts=stats,coverage=payload.get('coverage',''))
        except subprocess.TimeoutExpired: job.update(status='failed',completed_at=now(),error='自动整理超过15分钟，本轮已停止；可检查网络后重试。')
        except Exception as ex: job.update(status='failed',completed_at=now(),error=str(ex)[:1000])
        atomic(self.state,encode(job))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--limit',type=int,default=5);parser.add_argument('--status',action='store_true');args=parser.parse_args()
    collector=Collector(Store(args.root));print(encode(collector.status() if args.status else collector.run(args.limit)))
if __name__=='__main__': main()
