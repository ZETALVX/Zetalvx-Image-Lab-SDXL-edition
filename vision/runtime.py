# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
"""One owned local Vision process at a time, or calls to an explicit external API.
Workers are never downloaded implicitly. No shell arguments supplied by a model.
"""
from __future__ import annotations
import atexit,base64,hashlib,io,json,os,queue,re,secrets,shutil,signal,socket,subprocess,sys,threading,time
from pathlib import Path
from core.platform_support import venv_python, detached_kwargs, terminate_owned_tree
import requests
from PIL import Image,ImageOps
from .registry import VisionError,endpoint_url
from .llama_runtime import managed_executable, runtime_environment

MAX_IMAGE=32*1024**2

def image_bytes(value,max_side=1024):
    raw=Path(value).read_bytes() if isinstance(value,(str,Path)) else value
    if not isinstance(raw,bytes) or len(raw)>MAX_IMAGE:raise VisionError('Image too large for Vision')
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>32*1024**2:raise VisionError('Image exceeds 32 MP')
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((max_side,max_side));buf=io.BytesIO();im.save(buf,format='JPEG',quality=90);return buf.getvalue()

def clean_caption(c):
    if not isinstance(c,str) or len(c)>16384:raise VisionError('Invalid Vision caption')
    c=re.sub(r'<think>.*?</think>','',c,flags=re.S).strip()
    # An unclosed reasoning block must not enter the training captions.
    if '<think>' in c:c=c.split('<think>')[0].strip()
    if '</think>' in c:c=c.split('</think>')[-1].strip()
    if not c:raise VisionError('Empty caption or thinking-only output; disable thinking or increase the output limit')
    return c

def chat_request(m,image,prompt,token='',cancel=None):
    if cancel and cancel.is_set():raise VisionError('Cancelled')
    data={'model':m['api_model'],'messages':[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(image).decode()}}]}],
        'temperature':m.get('temperature',.2),'max_tokens':m.get('max_tokens',200),'stream':False}
    if m.get('api_thinking_option'):data['chat_template_kwargs']={'enable_thinking':not m.get('disable_thinking',True)}
    headers={'Authorization':'Bearer '+token} if token else {}
    client=requests.Session();client.trust_env=False
    try:
        try:
            with client.post(endpoint_url(m['endpoint']),json=data,headers=headers,verify=m.get('ca_bundle') or True,
                    timeout=(10,m.get('timeout',300)),allow_redirects=False,stream=True) as r:
                if r.status_code!=200:raise VisionError('Vision API HTTP '+str(r.status_code)+'; verify model, access and endpoint')
                parts=[];total=0
                for part in r.iter_content(65536):
                    if cancel and cancel.is_set():raise VisionError('Cancelled')
                    total+=len(part)
                    if total>4*1024**2:raise VisionError('Vision API response too large')
                    parts.append(part)
                out=json.loads(b''.join(parts));cap=out['choices'][0]['message']['content']
        except requests.exceptions.SSLError:raise VisionError('Vision TLS verification failed. Set a trusted CA certificate; certificate verification is not disabled.') from None
        except requests.RequestException:raise VisionError('Vision endpoint connection or timeout error; check endpoint and server') from None
        except (KeyError,IndexError,ValueError) as e:
            if isinstance(e,VisionError):raise
            raise VisionError('Vision API returned an invalid chat-completions response') from None
        return clean_caption(cap)
    finally:client.close()

class Engine:
    def __init__(self,registry):
        self.registry=registry;self.lock=threading.RLock();self.proc=None;self.mid='';self.signature='';self.messages=None;self.endpoint='';self.key='';self.keyfile=None;self.log=None;self.busy=False;self.loaded=False;self.last_error=''
        atexit.register(self.close)
    def status(self):
        return {'backend_process_running':bool(self.proc and self.proc.poll() is None),'model_id':self.mid,
            'loaded':self.loaded,'busy':self.busy,'last_error':self.last_error,'pid':self.proc.pid if self.proc and self.proc.poll() is None else None}
    def close(self):
        # Nonblocking here so shutdown cannot deadlock on an outstanding request.
        if self.proc:
            p=self.proc;self.proc=None
            if p.poll() is None:
                try:terminate_owned_tree(p,timeout=4)
                except (OSError,subprocess.TimeoutExpired):pass
            for stream in (p.stdin,p.stdout):
                if stream:
                    try:stream.close()
                    except OSError:pass
        if self.log:self.log.close();self.log=None
        if self.keyfile:self.keyfile.unlink(missing_ok=True);self.keyfile=None
        self.loaded=False;self.signature='';self.mid='';self.key='';self.endpoint=''
    def unload(self):
        if not self.lock.acquire(blocking=False):raise VisionError('Vision is busy; cancel the job first')
        try:self.close()
        finally:self.lock.release()
    def _read(self,timeout,cancel):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if cancel and cancel.is_set():self.close();raise VisionError('Cancelled')
            try:
                msg=self.messages.get(timeout=.2)
                if not msg.get('ok'):raise VisionError(msg.get('error','Vision worker stopped'))
                return msg
            except queue.Empty:
                if not self.proc or self.proc.poll() is not None:raise VisionError('Vision worker exited; see the local Vision runtime log')
        self.close();raise VisionError('Local Vision worker timed out and was stopped')
    def _open_log(self):
        path=self.registry.home/'logs/vision-runtime.log';path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.stat().st_size>4*1024**2:path.replace(path.with_suffix('.previous.log'))
        self.log=path.open('ab');os.chmod(path,0o600)
    def _ensure(self,m,cancel):
        m=self.registry.effective(m)
        sig=self.registry.fingerprint(m)
        if self.proc and self.proc.poll() is None and sig==self.signature and self.loaded:return
        self.close();report=self.registry.inspect(m)
        if not report['ok']:raise VisionError('Missing configuration: '+'; '.join(x['label']+' → '+x['path'] for x in report['checks'] if not x['ok']))
        self._open_log();self.mid=m['id'];self.signature=sig
        root=Path(__file__).resolve().parent
        env={k:v for k,v in os.environ.items() if k not in ('HF_TOKEN','HUGGING_FACE_HUB_TOKEN','OPENAI_API_KEY') and not k.startswith('LLAMA_ARG_')}
        env.update(ZETALVX_VISION_PARENT=str(os.getpid()),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
        if m['backend']=='transformers':
            exe=m.get('python_path') or str(venv_python(self.registry.home/'runtime/vision'))
            self.proc=subprocess.Popen([str(Path(exe).expanduser()),'-u',str(root.parent/'run.py'),'transformers'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,env=env,text=True,bufsize=1,**detached_kwargs())
            self.messages=queue.Queue();q=self.messages;p=self.proc
            def reader():
                try:
                    for line in p.stdout:
                        if line.startswith('ZETALVX_VISION_JSON '):
                            try:q.put(json.loads(line.split(' ',1)[1]))
                            except ValueError:q.put({'ok':False,'error':'Invalid worker response'})
                except (ValueError,OSError):pass
            threading.Thread(target=reader,daemon=True).start()
            self.proc.stdin.write(json.dumps({'model':m})+'\n');self.proc.stdin.flush();self._read(m['startup_timeout'],cancel)
        else:
            exe=m.get('llama_path') or shutil.which('llama-server') or str(managed_executable(self.registry.home))
            if Path(exe).expanduser().resolve()==managed_executable(self.registry.home).resolve():
                env=runtime_environment(Path(exe).expanduser().parent,env)
            with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
            self.key=secrets.token_hex(32);self.keyfile=self.registry.secrets/('local-'+secrets.token_hex(8)+'.key')
            fd=os.open(self.keyfile,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as f:f.write(self.key)
            args=[str(Path(exe).expanduser()),'--model',str(Path(m['gguf_path']).expanduser()),'--mmproj',str(Path(m['mmproj_path']).expanduser()),
                '--host','127.0.0.1','--port',str(port),'--ctx-size',str(m['context']),'--n-gpu-layers',str(0 if m['device']=='cpu' else m['gpu_layers']),
                '--threads',str(m['threads']),'--parallel','1','--alias','zetalvx-vision','--api-key-file',str(self.keyfile),
                '--chat-template-kwargs',json.dumps({'enable_thinking':not m['disable_thinking']})]
            if os.name == 'nt':
                # Windows execv re-joins argv without safe quoting and exits the
                # tracked Python helper. Launch the owned server directly instead.
                # Use llama.cpp's process-local JSON option to avoid another native
                # launcher interpreting its quotes. The profile value is unchanged.
                env['LLAMA_ARG_CHAT_TEMPLATE_KWARGS'] = args[-1]
                command = args[:-2]
            else:
                command = [sys.executable,str(root.parent/'run.py'),'child',str(os.getpid()),*args]
            self.proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=self.log,stderr=self.log,env=env,**detached_kwargs())
            self.endpoint=f'http://127.0.0.1:{port}/v1'
            client=requests.Session();client.trust_env=False;end=time.monotonic()+m['startup_timeout']
            try:
                while time.monotonic()<end:
                    if cancel and cancel.is_set():raise VisionError('Cancelled')
                    if self.proc.poll() is not None:raise VisionError('llama-server exited; verify its version, model and matching mmproj (local log)')
                    try:
                        r=client.get(self.endpoint+'/models',headers={'Authorization':'Bearer '+self.key},timeout=1,allow_redirects=False)
                        if r.status_code==200:
                            data=r.json().get('data',[])
                            if any(x.get('id')=='zetalvx-vision' for x in data):break
                    except (requests.RequestException,ValueError):pass
                    time.sleep(.25)
                else:raise VisionError('llama-server startup timeout')
            finally:client.close()
        self.loaded=True
    def caption(self,m,image,prompt,cancel=None):
        m=self.registry.effective(m)
        if not m.get('enabled',True):raise VisionError('Model disabled')
        if not m.get('terms_reviewed'):raise VisionError('Review the model terms in its configuration before use')
        with self.lock:
            self.busy=True;self.last_error=''
            try:
                raw=image_bytes(image,m.get('image_max_side',1024))
                if m['backend']=='api':return chat_request(m,raw,prompt,self.registry.token(m['id']),cancel)
                self._ensure(m,cancel)
                if m['backend']=='gguf':
                    return chat_request({**m,'endpoint':self.endpoint,'api_model':'zetalvx-vision','ca_bundle':'','api_thinking_option':False},raw,prompt,self.key,cancel)
                rid=secrets.token_hex(8)
                self.proc.stdin.write(json.dumps({'op':'caption','image':base64.b64encode(raw).decode(),'prompt':prompt,'request_id':rid})+'\n');self.proc.stdin.flush()
                answer=self._read(m['timeout'],cancel)
                if answer.get('request_id')!=rid:raise VisionError('Unexpected Vision response')
                return clean_caption(answer.get('caption'))
            except Exception as e:
                self.last_error=str(e)[:1200] if isinstance(e,VisionError) else type(e).__name__+': local Vision error'
                if m['backend']!='api':self.close()
                raise VisionError(self.last_error) from None
            finally:self.busy=False
