"""Private review queue: AI imports proposals, only an explicit review can publish."""
from pathlib import Path
from contextlib import contextmanager
import argparse
import hashlib
import json
import re
import time
import os
from local_workbench import Store, Conflict, note, props, atomic, encode, now, stamp, digest

FIELDS=('title','meaning','line','scenario','humor','visual','avoid','evidence_date','source_url','source_title','source_support','source_limitations','categories','functions')
STATES={'pending','needs_revision','revised','approved','rejected'}

class ReviewInbox:
    def __init__(self, store):
        self.store=store
        self.folder=store.kb/'私人/审核收件箱'
        self.folder.mkdir(parents=True,exist_ok=True)
    @contextmanager
    def locked(self):
        # A short cross-process lock protects CLI imports against simultaneous UI review.
        path=self.folder/'.write-lock'
        for _ in range(100):
            try: fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);break
            except FileExistsError: time.sleep(.05)
        else: raise Conflict('审核队列正在更新，请稍后重试；若进程异常退出，请检查私人队列的.write-lock文件')
        try: yield
        finally: os.close(fd);path.unlink(missing_ok=True)
    def path(self,id):
        if not isinstance(id,str) or not re.fullmatch(r'review-[a-f0-9]{20}',id): raise ValueError('审核ID无效')
        path=self.folder/(id+'.md')
        if path.is_symlink(): raise ValueError('不支持审核文件链接')
        return path
    def read(self,id):
        path=self.path(id)
        if not path.is_file(): raise ValueError('审核候选不存在')
        data=props(path);data['revision']=digest(path.read_text())
        return data
    def save(self,data):
        data={k:v for k,v in data.items() if k!='revision'}
        body='# 审核候选 · '+data['draft']['title']+'\n\n自动整理的候选，未经人工通过不会进入资料首页。\n\n## 审核意见\n\n'
        body+='\n'.join('- '+h['at']+' · '+h['action']+' · '+h.get('feedback','') for h in data.get('history',[])) or '尚未审核。'
        atomic(self.path(data['id']),note(data,body))
    def listing(self):
        with self.locked():
            items=[self.read(p.stem) for p in self.folder.glob('review-*.md')]
            meta=self.folder/'last-run.json'
            return {'items':sorted(items,key=lambda v:v['updated_at'],reverse=True),'last_run':json.loads(meta.read_text()) if meta.exists() else None}
    def import_batch(self, payload):
        if not isinstance(payload,dict) or not isinstance(payload.get('items'),list) or len(payload['items'])>20: raise ValueError('每批需提供items数组，最多20条')
        counts={'new':0,'updated':0,'duplicates':0,'preserved':0,'conflicts':0};prepared=[]
        # Validate the whole batch before any writes. Search-only snippets cannot be approved drafts.
        for item in payload['items']:
            if not isinstance(item,dict) or item.get('read_method')!='page_read': raise ValueError('候选须实际读取来源原页；不能只用检索摘要')
            draft={k:item.get(k) for k in FIELDS}
            self.store.create({**draft,'decision':'include','source_checked':True},validate_only=True)
            normalized=re.sub(r'\s+','',draft['title']).casefold()
            id='review-'+hashlib.sha256(normalized.encode()).hexdigest()[:20]
            if item.get('id'): id=item['id'];self.path(id)
            prepared.append((id,draft,item))
        with self.locked():
            known={re.sub(r'\s+','',str(t)).casefold() for p in (self.store.kb/'条目').glob('*.md') for t in [props(p)['title'],*props(p).get('aliases',[])]}
            for id,draft,item in prepared:
                path=self.path(id)
                if path.exists():
                    old=self.read(id)
                    if old['status']!='needs_revision': counts['preserved']+=1;continue
                    if item.get('based_on_revision')!=old['revision']: counts['conflicts']+=1;continue
                    old.update(draft=draft,status='revised',updated_at=now(),collector='AI宿主自动整理',read_method='page_read')
                    old['history'].append({'at':now(),'action':'AI修订','feedback':str(item.get('revision_note','已按审核意见修订'))[:2000]})
                    self.save(old);counts['updated']+=1
                elif re.sub(r'\s+','',draft['title']).casefold() in known: counts['duplicates']+=1
                else:
                    self.save({'id':id,'draft':draft,'status':'pending','created_at':now(),'updated_at':now(),'collector':'AI宿主自动整理','read_method':'page_read','history':[],'entry_id':None})
                    counts['new']+=1
            atomic(self.folder/'last-run.json',encode({'at':now(),'counts':counts,'coverage':str(payload.get('coverage','未声明平台覆盖'))[:2000]}))
        return counts
    def action(self, request):
        if not isinstance(request,dict): raise ValueError('审核请求无效')
        with self.locked(), self.store.lock:
            data=self.read(request.get('id'));action=request.get('action')
            if action=='approve' and data['status']=='approved': return data
            if request.get('revision')!=data['revision']: raise Conflict('候选已更新，请刷新审核队列后再提交意见')
            feedback=request.get('feedback','')
            if not isinstance(feedback,str) or len(feedback)>4000: raise ValueError('审核意见过长或格式无效')
            edits=request.get('edits',{})
            if not isinstance(edits,dict) or set(edits)-{'title','meaning','line','visual','avoid'}: raise ValueError('不支持的修改字段')
            if action in {'revise','approve'}: data['draft'].update(edits)
            if action=='revise':
                if data['status'] not in {'pending','revised','needs_revision'}: raise ValueError('此状态不能要求修订')
                if not feedback.strip(): raise ValueError('请写一句修改意见，AI将按此修订')
                data['status']='needs_revision'
            elif action=='reject':
                if data['status']=='approved': raise ValueError('已通过条目请在资料维护中移入回收站')
                data['status']='rejected'
            elif action=='restore':
                if data['status']!='rejected': raise ValueError('只有已跳过候选可以恢复')
                data['status']='pending'
            elif action=='approve':
                if data['status'] not in {'pending','revised'}: raise ValueError('请等待AI修订完成再审核，或先恢复已跳过候选')
                draft=dict(data['draft']);edits=request.get('edits',{})
                if not isinstance(edits,dict) or set(edits)-{'title','meaning','line','visual','avoid'}: raise ValueError('只允许修改名称、含义、用法、画面与使用分寸')
                draft.update(edits)
                # Recover safely if a prior process saved the note then stopped before marking approval.
                existing=next((p.stem for p in (self.store.kb/'条目').glob('*.md') if props(p).get('review_candidate_id')==data['id']),None)
                entry=self.store.entry(existing) if existing else self.store.create({**draft,'decision':'include','source_checked':True,'review_candidate_id':data['id']})
                data.update(draft=draft,status='approved',entry_id=entry['id'])
            else: raise ValueError('未知审核操作')
            raw=self.path(data['id']).read_text()
            atomic(self.store.kb/'私人/审核历史'/data['id']/(stamp()+'.md'),raw)
            data['updated_at']=now();data['history'].append({'at':now(),'action':action,'feedback':feedback.strip()})
            self.save(data)
            return self.read(data['id'])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('command',choices=['list','import'])
    parser.add_argument('file',type=Path,nargs='?')
    args=parser.parse_args();queue=ReviewInbox(Store(args.root))
    if args.command=='list': result=queue.listing()
    else:
        if not args.file: parser.error('import需要JSON文件')
        result=queue.import_batch(json.loads(args.file.read_text()))
    print(encode(result))
if __name__=='__main__': main()
