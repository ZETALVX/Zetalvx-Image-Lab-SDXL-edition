"""Serial caption jobs for both Zetalvx dataset layouts; snapshots & safe manual-edit merge."""
from __future__ import annotations
import contextlib,json,re,threading,time,uuid
from pathlib import Path
from .registry import VisionError,atomic_json,identifier

DEFAULT_PROMPT='Write a concise factual training caption in English. Describe only visible subject, action, clothing, lighting and background. No introduction, no speculation. Return only the caption.'
def spans(c,t):
    if not t:return []
    pat=(r'(?<!\w)' if t[0].isalnum() or t[0]=='_' else '')+re.escape(t)+(r'(?!\w)' if t[-1].isalnum() or t[-1]=='_' else '')
    return list(re.finditer(pat,c))
def trigger_apply(c,t,pos):
    if not t or pos=='context' or spans(c,t):return c
    return (t+', '+c) if pos=='prefix' else (c+', '+t)

class Batch:
    def __init__(self,root,datasets,registry,engine,lock=None,before=None,scope=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.datasets=Path(datasets);self.registry=registry;self.engine=engine
        self.lock=lock or threading.RLock();self.start_lock=threading.Lock();self.thread=None;self.stop=threading.Event();self.before=before;self.scope=scope or contextlib.nullcontext;self.active_local=False
        for p in self.root.glob('*.json'):
            try:
                d=json.loads(p.read_text())
                if d.get('status') in ('running','queued'):d.update(status='interrupted',message='Server restarted; run missing captions again');atomic_json(p,d)
            except (OSError,ValueError):pass
    def busy(self):return bool(self.thread and self.thread.is_alive())
    def read(self,did):
        p=self.datasets/identifier(did)/'dataset.json'
        if not p.is_file():raise VisionError('Dataset not found')
        return json.loads(p.read_text()),p
    def list(self):
        out=[]
        for p in self.root.glob('*.json'):
            try:out.append(json.loads(p.read_text()))
            except (ValueError,OSError):pass
        return sorted(out,key=lambda j:j.get('created_at',0),reverse=True)[:30]
    def cancel(self):self.stop.set()
    def start(self,did,mid):
        with self.start_lock:
            if self.busy():raise VisionError('Captioning is busy')
            m=self.registry.effective(self.registry.get(mid))
            if not m.get('terms_reviewed'):raise VisionError('Review model terms in Models before captioning')
            if not m.get('enabled'):raise VisionError('Model disabled')
            report=self.registry.inspect(m)
            if not report['ok']:raise VisionError('Model configuration incomplete: '+'; '.join(x['label'] for x in report['checks'] if not x['ok']))
            with self.lock:
                d,p=self.read(did)
                items=[x.copy() for x in d['items'] if not str(x.get('caption') or '').strip() or str(x.get('caption') or '').strip()==d.get('trigger')]
                if not items:raise VisionError('No images need captions')
                d['vision_model_id']=mid;atomic_json(p,d)
            if self.before:self.before(m)
            j={'id':uuid.uuid4().hex,'dataset_id':did,'model_id':mid,'model_name':m['name'],'backend':m['backend'],'status':'queued',
               'execution':self.registry.execution_info(m),'profile_fingerprint':self.registry.fingerprint(m),
               'done':0,'total':len(items),'failed':0,'needs_review':0,'preserved':0,'items':[],'created_at':time.time(),'message':''}
            atomic_json(self.root/(j['id']+'.json'),j);self.stop.clear();self.active_local=m['backend']!='api'
            self.thread=threading.Thread(target=self.run,args=(j,items,m),daemon=True);self.thread.start();return j
    def run(self,j,items,m):
        def save():atomic_json(self.root/(j['id']+'.json'),j)
        j['status']='running';save()
        try:
            with (self.scope() if m['backend']!='api' else contextlib.nullcontext()):
                for item in items:
                    if self.stop.is_set():break
                    try:
                        f=Path(item['file']).resolve()
                        if not f.is_relative_to((self.datasets/j['dataset_id']).resolve()) or not f.is_file():raise VisionError('Dataset image is outside its folder or missing')
                        with self.lock:d,_=self.read(j['dataset_id'])
                        trigger=str(d.get('trigger') or '').strip();pos=d.get('trigger_position','context')
                        prompt=m.get('instructions') or DEFAULT_PROMPT
                        if trigger and pos=='context':prompt+='\nUse the exact subject/concept trigger once naturally INSIDE the caption: '+json.dumps(trigger,ensure_ascii=False)+'. Preserve spelling, no extra explanation.'
                        elif trigger:prompt+='\nDo not insert a special trigger. The application will insert it if missing.'
                        caption=self.engine.caption(m,f,prompt,self.stop)
                        if trigger and pos=='context' and not spans(caption,trigger) and not self.stop.is_set():
                            caption=self.engine.caption(m,f,prompt+'\nThe exact trigger was omitted in the previous attempt. Include it once in the sentence.',self.stop)
                        if self.stop.is_set():break
                        cap=trigger_apply(caption,trigger,pos);flags=[]
                        if trigger and not spans(cap,trigger):flags.append('missing_trigger')
                        if len(spans(cap,trigger))>1:flags.append('repeated_trigger')
                        with self.lock:
                            d,p=self.read(j['dataset_id']);dest=next((x for x in d['items'] if x['id']==item['id']),None)
                            if dest and dest.get('caption','')==item.get('caption',''):
                                # Never inject using changed dataset settings midway through inference.
                                if str(d.get('trigger') or '').strip()!=trigger or d.get('trigger_position','context')!=pos:
                                    j['preserved']+=1;flags.append('dataset_settings_changed')
                                else:
                                    dest.update(caption=cap,caption_source='vision',caption_model_id=m['id'],caption_model_name=m['name'],caption_flags=flags);atomic_json(p,d)
                            else:j['preserved']+=1;flags.append('manual_edit_preserved')
                        if flags:j['needs_review']+=1
                        j['done']+=1;j['items'].append({'id':item['id'],'status':'review' if flags else 'completed','flags':flags})
                    except Exception as e:
                        if self.stop.is_set():break
                        msg=str(e)[:1200] if isinstance(e,VisionError) else type(e).__name__+': caption failed'
                        j['failed']+=1;j['message']=msg;j['items'].append({'id':item['id'],'status':'failed','error':msg})
                    save()
            j['status']='cancelled' if self.stop.is_set() else ('completed_with_errors' if j['failed'] else ('completed_with_warnings' if j['needs_review'] else 'completed'))
        except Exception as e:j.update(status='failed',message=str(e)[:1200] if isinstance(e,VisionError) else 'Caption job failed')
        finally:
            if m.get('unload_after_job',True) and m['backend']!='api':
                try:self.engine.unload()
                except Exception:pass
            self.active_local=False;j['finished_at']=time.time();save()
