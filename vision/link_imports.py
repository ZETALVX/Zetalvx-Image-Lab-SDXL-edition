# Modified in Zetalvx 0.1.0.42: targeted pre-release stabilization; see audit/STABILIZATION_0_1_0_42.md.
"""Safe link imports for Vision GGUF files and Hugging Face Transformers repositories.

Downloads are explicit, HTTPS-only, never execute repository Python code and never
follow local/private network targets. Hugging Face credentials reuse the app's local
Model Hub token store and are origin-bound by PublicHTTPS.
"""
from __future__ import annotations
import hashlib, json, os, queue, re, shutil, threading, time, uuid
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit
from email.message import Message

from core.download_security import DownloadError, Cancelled, TokenStore, PublicHTTPS, clean_user_url, parse_url, safe_source
from core.runtime_env import atomic_json
from core.download_manager import COORDINATOR
from core.install_layout import locked
from .registry import VisionError
from core.safe_paths import portable_relative, safe_child, is_link

ACTIVE={'queued','downloading','installing','cancelling'}
MAX_FILE=32*1024**3
MAX_REPO=64*1024**3
ALLOWED_REPO_SUFFIXES={'.safetensors','.json','.model','.txt','.tiktoken','.jinja'}
ALLOWED_REPO_NAMES={'merges.txt','vocab.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json',
                    'preprocessor_config.json','processor_config.json','generation_config.json','config.json','chat_template.jinja'}


def _safe_component(value:str)->str:
    s=re.sub(r'[^A-Za-z0-9._-]+','-',str(value or '')).strip('-.')
    if not s or len(s)>120:raise VisionError('Invalid repository or file name')
    return s


def _safe_rel(name:str)->Path:
    try:return portable_relative(name)
    except ValueError as exc:raise VisionError(str(exc)) from None


def _hf_repo_url(url:str):
    url=clean_user_url(str(url).strip());p=urlsplit(url);host=(p.hostname or '').lower()
    if host not in ('huggingface.co','www.huggingface.co'):raise VisionError('Transformers import currently accepts Hugging Face repository links only')
    bits=[unquote(x) for x in p.path.strip('/').split('/') if x]
    if len(bits)<2:raise VisionError('Use a Hugging Face model repository URL')
    repo='/'.join(bits[:2]);revision='main';prefix=''
    if len(bits)>2:
        if bits[2]!='tree' or len(bits)<4:raise VisionError('For a full Vision model use the repository page or a /tree/<revision> link')
        revision=bits[3];prefix='/'.join(bits[4:]).strip('/')
    return url,repo,revision,prefix


def _hf_file_url(url:str):
    url=clean_user_url(str(url).strip());p=urlsplit(url);host=(p.hostname or '').lower()
    if host not in ('huggingface.co','www.huggingface.co'):return None
    bits=[unquote(x) for x in p.path.strip('/').split('/') if x]
    if len(bits)<5 or bits[2] not in ('blob','resolve'):raise VisionError('Hugging Face GGUF: paste the exact file link (blob or resolve)')
    repo='/'.join(bits[:2]);revision=bits[3];filename='/'.join(bits[4:])
    return url,repo,revision,filename


def _allowed_repo_file(name:str)->bool:
    base=PurePosixPath(name).name.lower();suffix=PurePosixPath(name).suffix.lower()
    if base.endswith('.safetensors.index.json'):return True
    return base in ALLOWED_REPO_NAMES or suffix in ALLOWED_REPO_SUFFIXES


class VisionLinkImports:
    def __init__(self,home,start_worker=True):
        self.home=Path(home).expanduser().resolve();self.root=self.home/'models'/'Vision'
        self.state_root=self.home/'shared'/'vision'/'link-imports';self.incoming=self.root/'.incoming-links'
        self.root.mkdir(parents=True,exist_ok=True);self.state_root.mkdir(parents=True,exist_ok=True)
        if is_link(self.incoming) or is_link(self.root):raise VisionError('Vision temporary download folder cannot be a symbolic link')
        self.incoming.mkdir(parents=True,exist_ok=True)
        self.tokens=TokenStore(self.home/'secrets');self.transport=PublicHTTPS(self.tokens)
        self.lock=threading.RLock();self.jobs={};self.events={};self.pending=queue.Queue()
        for p in self.state_root.glob('*.json'):
            try:
                j=json.loads(p.read_text(encoding='utf-8'));jid=j['id']
                if not re.fullmatch('[a-f0-9]{32}',jid):continue
                if j.get('status') in ACTIVE:
                    now=time.time();j['status']='interrupted';j['error']='App restarted: repeat the Vision link import.'
                    history=j.get('history') if isinstance(j.get('history'),list) else []
                    history.append({'at':now,'status':'interrupted','message':j['error']});j['history']=history[-80:];j['updated_at']=now
                    (self.incoming/(jid+'.gguf.part')).unlink(missing_ok=True);shutil.rmtree(self.incoming/(jid+'.repo'),ignore_errors=True);atomic_json(p,j)
                if not isinstance(j.get('history'),list):j['history']=[]
                self.jobs[jid]=j
            except (OSError,ValueError,KeyError):pass
        if start_worker:
            for i in range(3):threading.Thread(target=self._loop,daemon=True,name=f'vision-link-imports-{i+1}').start()
    def _save(self,jid,**change):
        with self.lock:
            job=self.jobs[jid];now=time.time();old_status=job.get('status');new_status=change.get('status',old_status)
            if new_status=='downloading' and not job.get('started_at'):change.setdefault('started_at',now)
            history=job.get('history') if isinstance(job.get('history'),list) else []
            if new_status!=old_status:
                message=str(change.get('error') or '')[:500]
                history.append({'at':now,'status':new_status,'message':message})
                change['history']=history[-80:]
            job.update(change,updated_at=now);atomic_json(self.state_root/(jid+'.json'),job);return dict(job)
    def list(self):
        with self.lock:return sorted((dict(x) for x in self.jobs.values()),key=lambda x:x.get('created_at',0),reverse=True)[:50]
    def get(self,jid):
        with self.lock:
            if jid not in self.jobs:raise VisionError('Vision download not found')
            return dict(self.jobs[jid])
    def start(self,kind,url,role='',confirm_terms=False):
        if kind not in ('gguf','transformers'):raise VisionError('Unsupported Vision import type')
        if kind=='gguf' and role not in ('gguf_path','mmproj_path'):raise VisionError('Choose GGUF model or matching mmproj')
        if not confirm_terms:raise VisionError('Confirm that you have reviewed the model source and terms')
        with self.lock:
            if sum(x.get('status') in ACTIVE for x in self.jobs.values())>=30:raise VisionError('The Vision download queue already contains 30 jobs')
        plan=self._plan_gguf(url,role) if kind=='gguf' else self._plan_repo(url)
        try:
            with locked(self.home/'install.lock',blocking=False):
                if (self.home/'uninstall-pending.json').exists():raise VisionError('App maintenance in progress; retry later')
                jid=uuid.uuid4().hex;self.events[jid]=threading.Event()
                now=time.time()
                job={'id':jid,'kind':kind,'role':role,'status':'queued','created_at':now,'updated_at':now,'source':plan['source'],
                     'downloaded_bytes':0,'total_bytes':plan.get('size',0),'file_count':plan.get('file_count',1),'completed_files':0,'error':'','path':'',
                     'history':[{'at':now,'status':'queued','message':''}]}
                with self.lock:self.jobs[jid]=job;atomic_json(self.state_root/(jid+'.json'),job)
                self.pending.put((jid,plan));return dict(job)
        except BlockingIOError:raise VisionError('App maintenance in progress; retry later') from None
    def cancel(self,jid):
        with self.lock:
            if jid not in self.jobs:raise VisionError('Vision download not found')
            self.events.setdefault(jid,threading.Event()).set()
            if self.jobs[jid].get('status') in ACTIVE:return self._save(jid,status='cancelling')
            return dict(self.jobs[jid])
    def _plan_gguf(self,url,role):
        url=clean_user_url(str(url).strip());hf=_hf_file_url(url);plan={'kind':'gguf','role':role,'sha256':'','size':0}
        if hf:
            _,repo,revision,filename=hf
            if not filename.lower().endswith('.gguf'):raise VisionError('Vision GGUF import requires a .gguf file')
            data=self.transport.json(f'https://huggingface.co/api/models/{repo}/revision/{quote(revision,safe="")}?blobs=true')
            if not isinstance(data,dict):raise VisionError('Invalid Hugging Face repository metadata')
            sha=str(data.get('sha') or '')
            if re.fullmatch('[a-f0-9]{40}',sha):revision=sha
            item=next((x for x in data.get('siblings',[]) if x.get('rfilename')==filename),None)
            if not item:raise VisionError('GGUF file not found in the selected repository revision')
            lfs=item.get('lfs') or {};size=int(lfs.get('size') or item.get('size') or 0)
            digest=str(lfs.get('sha256') or lfs.get('oid') or '').removeprefix('sha256:').lower()
            if digest and not re.fullmatch('[a-f0-9]{64}',digest):digest=''
            plan.update(url=f'https://huggingface.co/{repo}/resolve/{quote(revision,safe="")}/{quote(filename,safe="/")}',
                        source=f'https://huggingface.co/{repo}',filename=PurePosixPath(filename).name,size=size,sha256=digest)
        else:
            p,host=parse_url(url);name=PurePosixPath(p.path).name
            if not name.lower().endswith('.gguf'):raise VisionError('Direct Vision link must point to a .gguf file')
            with self.transport.open(url) as r:
                ct=str(r.headers.get('Content-Type') or '').lower()
                if any(x in ct for x in ('text/html','application/json','text/plain')):raise VisionError('The link returned a page instead of a GGUF file')
                m=Message();m['content-disposition']=r.headers.get('Content-Disposition','');name=PurePosixPath(m.get_filename() or name).name
                size=int(r.headers.get('Content-Length') or 0)
            plan.update(url=url,source=safe_source(url),filename=name,size=size)
        if not 0<=plan['size']<=MAX_FILE:raise VisionError('Vision GGUF file exceeds the 32 GiB limit')
        return plan
    def _plan_repo(self,url):
        source,repo,revision,prefix=_hf_repo_url(url)
        data=self.transport.json(f'https://huggingface.co/api/models/{repo}/revision/{quote(revision,safe="")}?blobs=true')
        if not isinstance(data,dict):raise VisionError('Invalid Hugging Face repository metadata')
        sha=str(data.get('sha') or '')
        if re.fullmatch('[a-f0-9]{40}',sha):revision=sha
        prefix=(prefix.rstrip('/')+'/') if prefix else ''
        files=[];total=0;seen=set()
        for item in data.get('siblings',[]):
            name=str(item.get('rfilename') or '')
            if prefix and not name.startswith(prefix):continue
            rel=name[len(prefix):] if prefix else name
            if not rel or not _allowed_repo_file(rel):continue
            _safe_rel(rel)
            folded=rel.casefold()
            if folded in seen:raise VisionError('Duplicate/case-colliding repository file path')
            seen.add(folded)
            lfs=item.get('lfs') or {};size=int(lfs.get('size') or item.get('size') or 0)
            digest=str(lfs.get('sha256') or lfs.get('oid') or '').removeprefix('sha256:').lower()
            if digest and not re.fullmatch('[a-f0-9]{64}',digest):digest=''
            total+=size;files.append({'repo_file':name,'relative':rel,'size':size,'sha256':digest})
        names={x['relative'].lower() for x in files}
        if 'config.json' not in names or not any(x.endswith('.safetensors') for x in names):
            raise VisionError('Repository does not expose a complete safe Transformers Vision folder (config.json + safetensors)')
        if not files or len(files)>5000:raise VisionError('Unsupported repository file count')
        if total>MAX_REPO:raise VisionError('Vision repository exceeds the 64 GiB limit')
        return {'kind':'transformers','repo':repo,'revision':revision,'prefix':prefix,'files':files,'size':total,'file_count':len(files),'source':f'https://huggingface.co/{repo}'}
    def _loop(self):
        while True:
            jid,plan=self.pending.get();key='vision:'+jid;event=self.events.setdefault(jid,threading.Event());acquired=False
            try:
                acquired=COORDINATOR.acquire(key,event)
                if not acquired:
                    self._save(jid,status='cancelled',error='Download cancelled before start')
                    continue
                self._run(jid,plan)
            except Cancelled as e:
                try:self._save(jid,status='cancelled',error=str(e))
                except Exception:pass
            except Exception as e:
                msg=str(e) if isinstance(e,(VisionError,DownloadError)) else 'Vision download failed locally. No model was installed.'
                try:self._save(jid,status='failed',error=msg)
                except Exception:pass
            finally:
                if acquired:COORDINATOR.release(key)
                self.pending.task_done()
    def _download(self,url,path,event,expected='',base_done=0,total_hint=0,jid=None,expected_size=0):
        digest=hashlib.sha256();done=0;last=0
        with self.transport.open(url,cancel=event) as r, path.open('xb') as f:
            total=int(r.headers.get('Content-Length') or 0)
            if expected_size and total and total!=expected_size:raise VisionError('Remote file size differs from repository metadata')
            if total<0 or total>MAX_FILE:raise VisionError('Vision file exceeds the 32 GiB limit')
            for chunk in r.chunks():
                if event.is_set():raise Cancelled('Download cancelled')
                done+=len(chunk)
                if done>MAX_FILE:raise VisionError('Vision file exceeds the 32 GiB limit')
                f.write(chunk);digest.update(chunk)
                if jid and time.monotonic()-last>.6:self._save(jid,downloaded_bytes=base_done+done,total_bytes=max(total_hint,base_done+total));last=time.monotonic()
            f.flush();os.fsync(f.fileno())
        if (total and done!=total) or (expected_size and done!=expected_size):raise VisionError('Vision download was incomplete: unexpected file size')
        if event.is_set():raise Cancelled('Download cancelled')
        sha=digest.hexdigest()
        if expected and sha!=expected:raise VisionError('SHA-256 does not match the Hugging Face metadata')
        return done,sha
    def _run(self,jid,plan):
        event=self.events[jid];self._save(jid,status='downloading',current_file=str(plan.get('filename') or plan.get('repo') or ''))
        if plan['kind']=='gguf':
            dest_dir=safe_child(self.root,'GGUF');dest_dir.mkdir(parents=True,exist_ok=True);tmp=self.incoming/(jid+'.gguf.part')
            try:
                if shutil.disk_usage(self.root).free<max(plan.get('size',0),128*1024**2)+128*1024**2:raise VisionError('Not enough disk space for Vision download')
                done,sha=self._download(plan['url'],tmp,event,plan.get('sha256',''),0,plan.get('size',0),jid,plan.get('size',0))
                with tmp.open('rb') as f:
                    if f.read(4)!=b'GGUF':raise VisionError('Downloaded file is not a valid GGUF file')
                name=_safe_component(plan['filename']);dest=safe_child(dest_dir,name)
                if dest.exists():dest=safe_child(dest_dir,dest.stem+'-'+jid[:8]+dest.suffix)
                self._save(jid,status='installing');os.replace(tmp,dest)
                self._save(jid,status='complete',path=str(dest),downloaded_bytes=done,total_bytes=done,completed_files=1,error='',sha256=sha,upstream_digest_verified=bool(plan.get('sha256')))
            except Exception:
                tmp.unlink(missing_ok=True);raise
            return
        temp=self.incoming/(jid+'.repo');temp.mkdir(parents=True,exist_ok=False)
        try:
            if shutil.disk_usage(self.root).free<max(plan.get('size',0),512*1024**2)+256*1024**2:raise VisionError('Not enough disk space for Vision repository')
            done_total=0
            for index,item in enumerate(plan['files']):
                if event.is_set():raise Cancelled('Download cancelled')
                rel=_safe_rel(item['relative']);out=safe_child(temp,rel.as_posix());out.parent.mkdir(parents=True,exist_ok=True);out=safe_child(temp,rel.as_posix());self._save(jid,current_file=str(item['relative']))
                url=f'https://huggingface.co/{plan["repo"]}/resolve/{quote(plan["revision"],safe="")}/{quote(item["repo_file"],safe="/")}'
                size,_=self._download(url,out,event,item.get('sha256',''),done_total,plan.get('size',0),jid,item.get('size',0));done_total+=size
                if done_total>MAX_REPO:raise VisionError('Vision repository exceeds the 64 GiB limit')
                self._save(jid,completed_files=index+1,downloaded_bytes=done_total)
            # Revalidate the two minimum non-executable artifacts after download.
            if not (temp/'config.json').is_file() or not any(temp.rglob('*.safetensors')):raise VisionError('Downloaded repository is incomplete')
            base=_safe_component(plan['repo'].split('/')[-1]);suffix=plan['revision'][:8] if re.fullmatch('[a-f0-9]{40}',plan['revision']) else jid[:8]
            dest_root=safe_child(self.root,'Transformers');dest_root.mkdir(parents=True,exist_ok=True);dest=safe_child(dest_root,base+'-'+suffix)
            if dest.exists():dest=safe_child(dest_root,base+'-'+suffix+'-'+jid[:6])
            self._save(jid,status='installing');os.replace(temp,dest)
            self._save(jid,status='complete',path=str(dest),downloaded_bytes=done_total,total_bytes=done_total,completed_files=len(plan['files']),error='')
        except Exception:
            shutil.rmtree(temp,ignore_errors=True);raise
