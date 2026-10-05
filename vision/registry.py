# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
"""Persistent model profiles and separate secrets; file inspection never executes a model."""
from __future__ import annotations
import copy, hashlib
import json, os, re, tempfile, threading, uuid, time, shutil
from pathlib import Path
from core.platform_support import venv_python
from .llama_runtime import managed_executable
from urllib.parse import urlsplit, urlunsplit

class VisionError(ValueError): pass

def atomic_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=path.name+'.')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def identifier(value):
    s=str(value)
    if not re.fullmatch('[a-zA-Z0-9_-]{1,80}',s):raise VisionError('Invalid model identifier')
    return s

def endpoint_url(value):
    u=urlsplit(str(value).strip())
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.query or u.fragment:raise VisionError('Use an HTTP(S) API endpoint without credentials or query parameters')
    if u.scheme=='http' and u.hostname not in ('127.0.0.1','localhost','::1'):raise VisionError('Remote endpoints require HTTPS; add a CA certificate for your LAN server')
    path=u.path.rstrip('/')
    if not path.endswith('/chat/completions'):
        path+=(('/v1' if path=='' else '')+'/chat/completions')
    return urlunsplit((u.scheme,u.netloc,path,'',''))

STRINGS=('name','model_path','processor_path','python_path','llama_path','gguf_path','mmproj_path',
    'endpoint','api_model','ca_bundle','source_url','license_note','instructions')
DEFAULTS={'backend':'transformers','enabled':True,'family':'auto','device':'auto','dtype':'auto',
    'quantization':'native','max_tokens':200,'temperature':0.2,'context':4096,'gpu_layers':-1,
    'threads':4,'timeout':300,'startup_timeout':600,'image_max_side':1024,'unload_after_job':True,
    'disable_thinking':True,'api_thinking_option':False,'terms_reviewed':False}

def normalize(d, old=None):
    if not isinstance(d,dict):raise VisionError('Model configuration must be an object')
    d=dict(d)
    if 'llama_path' not in d and 'llama_server_path' in d:d['llama_path']=d['llama_server_path']
    m={**DEFAULTS,**(old or {})}
    for k in STRINGS:
        if k in d:
            s=str(d[k] or '').strip()
            if len(s)>4096 or '\x00' in s:raise VisionError('Field too long or invalid')
            m[k]=s
        else:m.setdefault(k,'')
    for key,options in {'backend':('api','gguf','transformers'),'family':('auto','qwen_vl','qwen3_5'),
            'device':('auto','cuda','cpu'),'dtype':('auto','float16','bfloat16','float32'),
            'quantization':('native','int4','int8')}.items():
        if key in d:
            if d[key] not in options:raise VisionError('Unsupported '+key)
            m[key]=d[key]
    for k in ('enabled','unload_after_job','disable_thinking','api_thinking_option','terms_reviewed'):
        if k in d:
            if not isinstance(d[k],bool):raise VisionError(k+' must be true or false')
            m[k]=d[k]
    for k,lo,hi in [('max_tokens',16,2048),('context',512,131072),('gpu_layers',-1,1000),('threads',1,128),('timeout',10,1800),('startup_timeout',30,1800),('image_max_side',128,2048)]:
        if k in d:
            try:n=int(d[k])
            except (TypeError,ValueError):raise VisionError('Invalid '+k)
            if n<lo or n>hi:raise VisionError(f'{k}: {lo}–{hi}')
            m[k]=n
    if 'temperature' in d:
        n=float(d['temperature'])
        if not 0<=n<=2:raise VisionError('Temperature: 0–2')
        m['temperature']=n
    if not m['name']:raise VisionError('Enter a model name')
    if m['backend']=='api' and m['endpoint']:m['endpoint']=endpoint_url(m['endpoint'])
    if m['source_url']:
        u=urlsplit(m['source_url'])
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:raise VisionError('Source URL: use a public HTTPS model page without credentials')
    m['id']=(old or {}).get('id') or uuid.uuid4().hex
    m['created_at']=(old or {}).get('created_at') or time.time();m['updated_at']=time.time()
    # Never retain tokens in a model profile or an API response.
    return {k:v for k,v in m.items() if k not in ('token','api_key','token_stored')}

class Registry:
    def __init__(self,home):
        self.home=Path(home).expanduser().resolve();self.folder=self.home/'config/vision';self.secrets=self.home/'secrets/vision';self.lock=threading.RLock()
        self.folder.mkdir(parents=True,exist_ok=True);self.secrets.mkdir(parents=True,exist_ok=True);self.secrets.chmod(0o700)
    def get(self,mid):
        p=self.folder/(identifier(mid)+'.json')
        if not p.is_file():raise VisionError('Vision model not found')
        d=json.loads(p.read_text())
        if not isinstance(d,dict) or d.get('id')!=mid:raise VisionError('Invalid model profile')
        return d
    def public(self,m):return {**m,'token_stored':(self.secrets/(m['id']+'.token')).is_file()}
    def list(self):
        with self.lock:
            out=[]
            for p in self.folder.glob('*.json'):
                try:out.append(self.public(self.get(p.stem)))
                except (ValueError,OSError):continue
            return sorted(out,key=lambda m:m.get('name','').lower())
    def save(self,d,mid=None):
        with self.lock:
            old=self.get(mid) if mid else None;m=normalize(d,old)
            token=str(d.get('token') or '').strip()
            if len(token)>16384 or any(c in token for c in '\r\n\x00'):raise VisionError('Invalid API token')
            atomic_json(self.folder/(m['id']+'.json'),m)
            secret=self.secrets/(m['id']+'.token')
            if d.get('forget_token'):secret.unlink(missing_ok=True)
            elif d.get('token'):
                token=str(d['token']).strip()
                if len(token)>16384 or any(c in token for c in '\r\n\x00'):raise VisionError('Invalid API token')
                fd=os.open(secret,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
                with os.fdopen(fd,'w') as f:f.write(token)
                secret.chmod(0o600)
            return self.public(m)
    def token(self,mid):
        p=self.secrets/(identifier(mid)+'.token');return p.read_text().strip() if p.exists() else ''
    def delete(self,mid):
        with self.lock:
            self.get(mid);(self.folder/(mid+'.json')).unlink();(self.secrets/(mid+'.token')).unlink(missing_ok=True)
    def effective(self,m):
        """Resolve once using only this profile. Invalid explicit paths never fall back."""
        m=copy.deepcopy(m)
        def absolute(value):return str(Path(value).expanduser().absolute())
        if m['backend']=='gguf':
            explicit=str(m.get('llama_path') or m.get('llama_server_path') or '').strip()
            chosen=explicit or shutil.which('llama-server') or str(managed_executable(self.home))
            m['llama_path']=absolute(chosen)
            for key in ('gguf_path','mmproj_path'):
                if m.get(key):m[key]=absolute(m[key])
        elif m['backend']=='transformers':
            m['python_path']=absolute(m.get('python_path') or venv_python(self.home/'runtime/vision'))
            for key in ('model_path','processor_path'):
                if m.get(key):m[key]=absolute(m[key])
        return m
    def execution_info(self,m):
        m=self.effective(m)
        fields=('llama_path','gguf_path','mmproj_path') if m['backend']=='gguf' else (('python_path','model_path','processor_path') if m['backend']=='transformers' else ('endpoint','api_model'))
        return {k:m.get(k,'') for k in fields}
    def fingerprint(self,m):
        m=self.effective(m)
        data={k:v for k,v in m.items() if k not in ('created_at','updated_at','token','token_stored','api_key')}
        return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    def inspect(self,m):
        m=self.effective(m)
        checks=[];notes=[];info={}
        def check(label,value,ok):checks.append({'label':label,'path':str(value),'ok':bool(ok)})
        def p(v):return Path(v).expanduser() if v else Path('/__missing_vision_path__')
        if m['backend']=='api':
            try:endpoint_url(m.get('endpoint',''));valid=True
            except ValueError:valid=False
            check('Endpoint',m.get('endpoint',''),valid);check('API model ID',m.get('api_model',''),bool(m.get('api_model')))
            if m.get('ca_bundle'):check('CA certificate',m['ca_bundle'],p(m['ca_bundle']).is_file())
            notes.append('Configuration check only. Test with an image to verify multimodal support.')
        elif m['backend']=='gguf':
            for key,label in [('gguf_path','GGUF model'),('mmproj_path','Matching vision projector (mmproj)')]:
                f=p(m.get(key));ok=False
                if f.is_file():
                    try:
                        with f.open('rb') as h:ok=h.read(4)==b'GGUF'
                    except OSError:pass
                check(label,f,ok)
            binary=m.get('llama_path') or shutil.which('llama-server') or str(managed_executable(self.home))
            check('llama-server executable',binary,p(binary).is_file() and os.access(binary,os.X_OK))
            notes.append('GGUF architecture and mmproj compatibility are checked by your llama.cpp build when loading; file presence is not an inference test.')
        else:
            root=p(m.get('model_path'));proc=p(m.get('processor_path') or m.get('model_path'));cfg=root/'config.json'
            check('Model directory',root,root.is_dir());check('Model config.json',cfg,cfg.is_file())
            try:
                if cfg.stat().st_size>4*1024**2:raise ValueError('Config too large')
                c=json.loads(cfg.read_text());info={k:c.get(k) for k in ('model_type','architectures','quantization_config')}
                check('Vision configuration',c.get('model_type','unknown'),bool(c.get('vision_config') or c.get('visual')))
                if c.get('auto_map'):notes.append('Custom Python code from model repositories is disabled (trust_remote_code=False).')
                if c.get('quantization_config'):notes.append('Pre-quantized weights: use Native. Support depends on Transformers, quantization backend and GPU.')
            except (OSError,ValueError):pass
            idx=root/'model.safetensors.index.json';weight_files=[f for f in root.glob('*.safetensors') if f.is_file() and f.stat().st_size>0]
            if idx.is_file():
                try:
                    if idx.stat().st_size>8*1024**2:raise ValueError('Index too large')
                    shards=set(json.loads(idx.read_text()).get('weight_map',{}).values())
                    missing=[x for x in shards if not isinstance(x,str) or not (root/x).resolve().is_relative_to(root.resolve()) or not (root/x).is_file()]
                    check('Safetensors shards',f'{len(shards)} shards; missing: '+', '.join(map(str,missing[:6])),bool(shards) and not missing)
                except (OSError,ValueError):check('Safetensors index',idx,False)
            else:check('Safetensors weights',root,bool(weight_files))
            check('Tokenizer',proc,any((proc/f).is_file() for f in ('tokenizer.json','tokenizer.model')))
            check('Image processor',proc,any((proc/f).is_file() for f in ('preprocessor_config.json','processor_config.json')))
            python=m.get('python_path') or str(venv_python(self.home/'runtime/vision'))
            check('Vision Python',python,p(python).is_file() and os.access(python,os.X_OK))
            notes.append('Use the full local model directory, not a single shard. No files are downloaded by inference.')
        return {'ok':all(x['ok'] for x in checks),'checks':checks,'notes':notes,'detected':info,'level':'files/config only','execution':self.execution_info(m),'profile_fingerprint':self.fingerprint(m)}
    def browse(self,value):
        managed={'__APP_VISION_GGUF__':self.home/'models'/'Vision'/'GGUF',
                 '__APP_VISION_TRANSFORMERS__':self.home/'models'/'Vision'/'Transformers',
                 '__APP_VISION_RUNTIME__':self.home/'runtime'/'vision',
                 '__APP_LLAMA_RUNTIME__':managed_executable(self.home).parent}
        p=Path(managed.get(str(value or ''),value or (self.home/'models'/'Vision'))).expanduser().resolve()
        denied=[self.home/'secrets',Path('/proc'),Path('/sys'),Path('/dev'),Path.home()/'.ssh',Path.home()/'.gnupg']
        if any(p.is_relative_to(x.resolve()) for x in denied):raise VisionError('Private or system directory')
        if not p.is_dir():p=p.parent
        if not p.is_dir():raise VisionError('Folder not found')
        items=[]
        for f in sorted(p.iterdir(),key=lambda f:(not f.is_dir(),f.name.lower())):
            if f.name.startswith('.') or any(f.resolve().is_relative_to(x.resolve()) for x in denied):continue
            if f.is_dir() or f.suffix.lower() in ('.gguf','.json','.safetensors','.pem','.crt') or f.name.startswith('python') or f.name=='llama-server':
                items.append({'name':f.name,'path':str(f),'directory':f.is_dir()})
            if len(items)>=500:break
        return {'path':str(p),'parent':str(p.parent),'entries':items}
