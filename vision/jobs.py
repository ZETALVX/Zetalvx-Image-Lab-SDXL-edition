# Modified in Zetalvx 0.1.0.42: targeted pre-release stabilization; see audit/STABILIZATION_0_1_0_42.md.
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; see CHANGELOG.md.
"""Persistent, identifiable tests/runtime actions with immutable profile snapshots."""
import contextlib,base64,copy,json,threading,time,uuid,subprocess
from pathlib import Path
from .registry import VisionError,atomic_json,identifier
from .llama_runtime import LlamaRuntimeManager,LlamaRuntimeError

class Actions:
    def __init__(self,registry,engine):
        self.registry=registry;self.engine=engine;self.jobs={};self.lock=threading.RLock()
        self.scope=lambda m:contextlib.nullcontext();self.before=None;self.cancel_flags={}
        self.root=registry.home/'jobs/vision-actions';self.root.mkdir(parents=True,exist_ok=True)
        for p in self.root.glob('*.json'):
            try:
                j=json.loads(p.read_text());identifier(j['id'])
                if j['status'] in ('running','queued','cancelling'):
                    j.update(status='interrupted',message='Server restarted. Run a new test.',finished_at=time.time());atomic_json(p,j)
                if j.get('kind')=='runtime' and j.get('status')=='failed' and str(j.get('message','')).startswith('Automatic Transformers Vision runtime installation remains paused'):
                    j.update(status='unavailable',message='Automatic Transformers Vision runtime preparation is currently paused. Existing explicit local runtimes remain selectable.');atomic_json(p,j)
                self.jobs[j['id']]=j
            except (OSError,ValueError,KeyError):continue
        self._trim()
    def _trim(self):
        ordered=sorted(self.jobs.values(),key=lambda j:j.get('created_at',0),reverse=True)
        for j in ordered[24:]:
            if j['status'] not in ('running','queued','cancelling'):
                self.jobs.pop(j['id'],None);(self.root/(j['id']+'.json')).unlink(missing_ok=True)
    def _save(self,j):atomic_json(self.root/(j['id']+'.json'),j)
    def list(self):
        with self.lock:return copy.deepcopy(sorted(self.jobs.values(),key=lambda j:j.get('created_at',0),reverse=True)[:24])
    def cancel(self,jid):
        with self.lock:
            j=self.jobs.get(identifier(jid))
            if not j:raise VisionError('Test not found')
            if j['status']=='running' and j['kind']=='test':
                self.cancel_flags[jid].set();j.update(status='cancelling',message='Cancelling the current test…');self._save(j)
            return copy.deepcopy(j)
    def start(self,kind,mid=None,image=None,prompt=None,options=None):
        if kind not in ('runtime','llama_runtime','test'):raise VisionError('Unsupported Vision action')
        options=options or {}
        m=None;image_data=None
        if kind=='test':
            # Snapshot BEFORE scheduling: saves during a test affect only the next job.
            m=self.registry.effective(self.registry.get(mid))
            try:image_data=base64.b64decode(image,validate=True)
            except (ValueError,TypeError):raise VisionError('Invalid test image') from None
        with self.lock:
            if any(x['status'] in ('running','cancelling') for x in self.jobs.values()):raise VisionError('A Vision action is already running')
            j={'id':uuid.uuid4().hex,'kind':kind,'model_id':mid,'model_name':m.get('name','') if m else '',
               'backend':m.get('backend','') if m else '', 'status':'running','message':'','created_at':time.time()}
            if m:j.update(profile_fingerprint=self.registry.fingerprint(m),execution=self.registry.execution_info(m))
            stop=threading.Event();self.cancel_flags[j['id']]=stop;self.jobs[j['id']]=j;self._save(j)
        def run():
            try:
                if kind=='runtime':
                    raise VisionError('Automatic Transformers Vision runtime installation remains paused; existing explicit local runtimes remain selectable.')
                elif kind=='llama_runtime':
                    manager=LlamaRuntimeManager(self.registry.home)
                    def report(done,total,index,count,label):
                        with self.lock:
                            local=int(done*100/total) if total else 0
                            pct=int((((index-1)+(done/total if total else 0))/max(1,count))*100)
                            j['progress']=pct;j['message']=f'{label} · {local}% · file {index}/{count}';self._save(j)
                    state=manager.install(options.get('preference','auto'),report)
                    with self.lock:
                        j['log_path']=state.get('log_path','');j['progress']=100;j['release']=state.get('version','');j['runtime_backend']=state.get('backend','');j['fallbacks']=state.get('fallbacks',[]);self._save(j)
                    value='Managed llama.cpp runtime ready · '+str(state.get('version') or '')+' · '+str(state.get('backend') or '')
                else:
                    if self.before:self.before(m)
                    with self.scope(m):
                        value=self.engine.caption(m,image_data,prompt or m.get('instructions') or 'Describe this image briefly. Return only the description.',stop)
                    if m.get('unload_after_job',True):self.engine.unload()
                with self.lock:
                    j.update(status='cancelled' if stop.is_set() else 'completed',message='Test cancelled.' if stop.is_set() else value)
                    if kind=='test' and not stop.is_set():j['caption']=value
            except Exception as e:
                if kind!='runtime':
                    try:self.engine.unload()
                    except Exception:pass
                with self.lock:
                    if kind=='llama_runtime':
                        try:j['log_path']=manager.status().get('log_path','');j['error_code']=getattr(e,'code','llama_prepare_failed')
                        except Exception:pass
                    j.update(status='cancelled' if stop.is_set() else 'failed',message='Test cancelled.' if stop.is_set() else (str(e)[:1600] if isinstance(e,(VisionError,LlamaRuntimeError)) else type(e).__name__+': operation failed'))
            finally:
                with self.lock:
                    j['finished_at']=time.time();self._save(j);self.cancel_flags.pop(j['id'],None);self._trim()
        threading.Thread(target=run,daemon=True,name='vision-action-'+j['id'][:8]).start()
        with self.lock:return copy.deepcopy(j)
