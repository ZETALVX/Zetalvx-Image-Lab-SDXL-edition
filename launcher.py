# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.24: host-issued remote first-setup codes.
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
#!/usr/bin/env python3
"""Local process supervisor and management commands for Zetalvx Image Lab - SDXL Edition."""
from __future__ import annotations
import argparse, contextlib, getpass, hmac, json, os, signal, socket, ssl, subprocess, sys, time, urllib.request, webbrowser
from pathlib import Path
from core.platform_support import venv_python, process_start, detached_kwargs
from core import file_lock as fcntl
from core.first_run_security import FirstRunCodes, print_setup_code
from core.runtime_env import initialize_environment, DATA_ROOT, SHARED_ROOT, MODELS_ROOT, RUNTIME_ROOT, APP_ROOT, SETTINGS_FILE, settings, atomic_json, VERSION, runtime_dir
from core.platform_support import hidden_kwargs
from core.private_cuda_env import private_cuda_env

PIDFILE=SHARED_ROOT/'run/supervisor.json'
STOPFILE=SHARED_ROOT/'run/stop-request.json'

def lan_ip():
    """Best-effort primary LAN address; no external network request is made."""
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1',9))
        ip=s.getsockname()[0]
        return ip if ip and not ip.startswith('127.') else None
    except OSError:return None
    finally:s.close()

def urls(cfg=None):
    cfg=cfg or settings();scheme='https' if cfg.get('https') else 'http';port=int(cfg['port'])
    local=f'{scheme}://127.0.0.1:{port}'
    ip=lan_ip();network=f'{scheme}://{ip}:{port}' if cfg.get('host')=='0.0.0.0' and ip else None
    return local,network

def _process_start(pid):
    return process_start(pid)

def running():
    try:
        d=json.loads(PIDFILE.read_text());p=int(d['pid'])
        if _process_start(p)==d['start'] and d['start'] is not None:return d
    except (OSError,ValueError,KeyError):pass
    return None

def actual_config(process=None):
    """Read the live listener, not this command's temporary launch flags."""
    process=process or running()
    cfg=settings()
    if process:
        if 'host' in process:
            for key in ('host','port','https'):
                if key in process:cfg[key]=process[key]
        else:
            # Compatibility with supervisors created by older builds.
            try:
                env=Path(f"/proc/{int(process['pid'])}/environ").read_bytes().split(b'\0')
                host=next((x.split(b'=',1)[1].decode() for x in env if x.startswith(b'SDXL_STUDIO_HOST_OVERRIDE=')),None)
                stored=json.loads(SETTINGS_FILE.read_text())
                cfg['host']=host or stored.get('host','127.0.0.1')
            except (OSError,ValueError,KeyError):cfg['host']='127.0.0.1'
    return cfg

def cert():
    cfg=SHARED_ROOT/'config';cfg.mkdir(parents=True,exist_ok=True)
    if (cfg/'cert.pem').is_file() and (cfg/'key.pem').is_file():return
    from core.local_certificate import generate_certificate
    generate_certificate(cfg,lan_ip())

def setup_codes():
    return FirstRunCodes(SHARED_ROOT/'config/creator_auth.json', DATA_ROOT/'secrets')

def _setup_control_token():
    secret=SHARED_ROOT/'config/creator_session_secret.txt'
    try:key=secret.read_text(encoding='utf-8').strip().encode('utf-8')
    except OSError:return ''
    return hmac.new(key,b'zetalvx-first-run-code-control-v1','sha256').hexdigest()

def _rotate_setup_code_through_web():
    process=running()
    if not process:return None
    cfg=actual_config(process);local,_=urls(cfg)
    token=_setup_control_token()
    if not token:raise RuntimeError('Setup control secret unavailable.')
    request=urllib.request.Request(local+'/api/first-run/local-code',data=b'',method='POST',
        headers={'X-Zetalvx-Setup-Control':token,'Content-Type':'application/octet-stream'})
    context=ssl._create_unverified_context() if cfg.get('https') else None
    try:
        with urllib.request.urlopen(request,timeout=5,context=context) as response:
            data=json.load(response)
    except Exception as exc:
        raise RuntimeError('Could not rotate the setup code through the running local app. Check creator-sdxl status and try again.') from exc
    code=str(data.get('code') or '')
    if not code:raise RuntimeError('The running app did not return a setup code.')
    return code

def setup_code():
    # Windows/host management command: keep terminal output and the local first-run
    # page synchronized by rotating through the already-running web process.
    init()
    auth=json.loads((SHARED_ROOT/'config/creator_auth.json').read_text(encoding='utf-8'))
    if auth.get('password_hash'):
        print('First setup is already complete. Use the configured username and password.')
        return
    if running():
        print_setup_code(_rotate_setup_code_through_web())
    else:
        # Preserve the historical host command contract for offline maintenance.
        # A running first-setup session uses the synchronized web path above.
        print_setup_code(setup_codes().issue())

def password():
    from werkzeug.security import generate_password_hash
    pwd=getpass.getpass('Nuova password per C: ')
    if len(pwd)<10:raise ValueError('Use at least 10 characters.')
    if pwd!=getpass.getpass('Ripeti password: '):raise ValueError('Passwords do not match.')
    manager=setup_codes()
    with manager.locked():
        atomic_json(SHARED_ROOT/'config/creator_auth.json',{'enabled':True,'username':'C','password_hash':generate_password_hash(pwd),'session_hours':12})
        manager.revoke_locked()
    print('[OK] Password updated. Existing sessions are revoked.')

def init():
    cert()
    from core.model_registry import ensure_config
    ensure_config()
    auth=SHARED_ROOT/'config/creator_auth.json'
    if not auth.exists():atomic_json(auth,{'enabled':True,'username':'','password_hash':'','session_hours':12})
    print('Data:',DATA_ROOT)
    if not json.loads(auth.read_text()).get('password_hash'):
        print('First launch: create your account locally, or over HTTPS/LAN with the host-issued setup code.')

def url(cfg=None):return urls(cfg)[0]

def ready(cfg):
    try:
        # Only the local readiness probe accepts our self-signed certificate.
        ctx=ssl._create_unverified_context() if cfg.get('https') else None
        with urllib.request.urlopen(url(cfg)+'/api/health',timeout=1,context=ctx) as r:return json.load(r).get('edition')=='sdxl'
    except Exception:return False

def start(browser=True,mode=None):
    from core.install_layout import locked
    if os.environ.get('SDXL_STUDIO_INSTALLER_ACTIVE')!='1':
        try:
            with locked(DATA_ROOT/'install.lock'):
                return _start_with_launch_lock(browser,mode)
        except BlockingIOError:
            raise RuntimeError('Installazione/aggiornamento in corso. Nessun avvio concorrente eseguito.')
    return _start_with_launch_lock(browser,mode)


def _start_with_launch_lock(browser=True,mode=None):
    initialize_environment()
    fd=os.open(SHARED_ROOT/'run/start.lock',os.O_RDWR|os.O_CREAT,0o600)
    with os.fdopen(fd,'r+b') as fp:
        if os.fstat(fp.fileno()).st_size==0:fp.write(b'\0');fp.flush()
        fcntl.flock(fp.fileno(),fcntl.LOCK_EX)
        try:return _start_locked(browser,mode)
        finally:fcntl.flock(fp.fileno(),fcntl.LOCK_UN)

def _start_locked(browser=True,mode=None):
    if (DATA_ROOT/'uninstall-pending.json').exists():raise RuntimeError('Uninstall in progress.')
    # --lan / --local override only this launch; GUI/settings remain the persistent default.
    if mode in ('lan','local'):
        os.environ['SDXL_STUDIO_HOST_OVERRIDE']='0.0.0.0' if mode=='lan' else '127.0.0.1'
    if running():
        d=running();cfg=actual_config(d);local,network=urls(cfg)
        desired='0.0.0.0' if mode=='lan' else '127.0.0.1'
        if mode in ('lan','local') and desired!=cfg.get('host'):
            raise RuntimeError('App già attiva in modalità '+('LAN' if cfg.get('host')=='0.0.0.0' else 'LOCAL')+'. Per non interrompere i lavori, esegui prima creator-sdxl stop, poi ripeti start con la modalità desiderata.')
        print('[OK] Already running · '+('LAN' if cfg.get('host')=='0.0.0.0' else 'LOCAL'))
        print('Local:  ',local)
        if network:print('Network:',network)
        print('Browser:','opened' if browser else 'disabled (--no-browser)')
        if browser:webbrowser.open(local)
        if not json.loads((SHARED_ROOT/'config/creator_auth.json').read_text()).get('password_hash'):
            print('Prima configurazione in attesa: usa setup-code.sh / SETUP-CODE.cmd per un nuovo codice.')
        return
    init();cfg=settings()
    auth=json.loads((SHARED_ROOT/'config/creator_auth.json').read_text())
    if not auth.get('password_hash') and cfg.get('host')!='127.0.0.1' and not cfg.get('https'):
        raise RuntimeError('Remote first setup requires HTTPS. Enable HTTPS before starting in LAN mode.')
    ports=[cfg['port'],cfg['image_port'],cfg['identity_port'],cfg['training_port']]
    if len(set(ports))!=len(ports):raise RuntimeError('Configure four different ports in settings.json.')
    from core.listener_check import probe_port
    for port in ports:
        try:probe_port(cfg['host'] if port==cfg['port'] else '127.0.0.1',int(port))
        except OSError:raise RuntimeError(f'Port {port} already in use. No unrelated service has been stopped.')
    first_code=setup_codes().issue()
    log=(SHARED_ROOT/'logs/launcher.log').open('a')
    env={**os.environ,'PYTHONUNBUFFERED':'1','SDXL_STUDIO_SETUP_CODE_MANAGED':'1'}
    if first_code:
        # Clear setup code exists only in process memory so the direct local
        # first-run page can show the same code printed by this host launcher.
        env['SDXL_STUDIO_FIRST_RUN_DISPLAY_CODE']=first_code
    else:
        env.pop('SDXL_STUDIO_FIRST_RUN_DISPLAY_CODE',None)
    env.pop('SDXL_STUDIO_INSTALLER_ACTIVE',None)
    p=subprocess.Popen([sys.executable,str(APP_ROOT/'run.py'),'launcher','_serve'],cwd=APP_ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,**detached_kwargs())
    log.close()
    for _ in range(100):
        if p.poll() is not None:raise RuntimeError('Startup failed. Read '+str(SHARED_ROOT/'logs/launcher.log'))
        if ready(cfg):
            local,network=urls(cfg)
            print(f'Zetalvx Image Lab - SDXL Edition {VERSION}')
            print('Status: RUNNING')
            print('HTTPS:','enabled' if cfg.get('https') else 'disabled')
            print('Access:','LAN' if cfg['host']=='0.0.0.0' else 'LOCAL')
            print('Local:  ',local)
            if network:print('Network:',network)
            print('Browser:','opened' if browser else 'disabled (--no-browser)')
            print('Logs:',SHARED_ROOT/'logs')
            if cfg['host']=='0.0.0.0':print('LAN enabled. Login is required; do not expose this app directly to the Internet.')
            print_setup_code(first_code)
            if browser:webbrowser.open(local)
            return
        time.sleep(.2)
    raise RuntimeError('Startup is taking longer than expected. Check creator-sdxl status and launcher.log.')

def serve():
    # One supervisor per isolated data directory. Stop signals only its own children.
    cfg=settings();lockfile=(SHARED_ROOT/'run/supervisor.lock').open('a+b')
    if os.fstat(lockfile.fileno()).st_size==0:lockfile.write(b'\0');lockfile.flush()
    fcntl.flock(lockfile.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    if os.environ.get('SDXL_STUDIO_SETUP_CODE_MANAGED')!='1':
        print_setup_code(setup_codes().issue())
        os.environ['SDXL_STUDIO_SETUP_CODE_MANAGED']='1'
    STOPFILE.unlink(missing_ok=True)
    pid=os.getpid();atomic_json(PIDFILE,{'pid':pid,'start':_process_start(pid),'version':VERSION,'app_root':str(APP_ROOT),'host':cfg['host'],'port':cfg['port'],'https':bool(cfg.get('https'))})
    children=[];stopping=False;reported=set()
    def stop_signal(sig,frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop_signal);signal.signal(signal.SIGINT,stop_signal)
    specs=[('web',sys.executable,[str(APP_ROOT/'run.py'),'web'])]
    ai=venv_python(runtime_dir('sdxl') or RUNTIME_ROOT/'not-installed')
    if ai.is_file():
        specs += [(name,str(ai),[str(APP_ROOT/'run.py'),name]) for name in ('image','training','identity')]
    try:
        for name,exe,args in specs:
            fp=(SHARED_ROOT/'logs'/f'{name}-worker.log').open('a')
            child_env={**os.environ,'PYTHONUNBUFFERED':'1'}
            if name!='web':
                child_env.pop('SDXL_STUDIO_FIRST_RUN_DISPLAY_CODE',None)
            if name=='identity': child_env=private_cuda_env(Path(exe),child_env)
            p=subprocess.Popen([exe,*args],cwd=APP_ROOT,stdin=subprocess.DEVNULL,stdout=fp,stderr=subprocess.STDOUT,env=child_env, **hidden_kwargs())
            fp.close();children.append((name,p))
        while not stopping:
            if STOPFILE.exists():
                try:
                    req=json.loads(STOPFILE.read_text())
                    if req.get('pid')==pid and req.get('start')==_process_start(pid):stopping=True
                except (OSError,ValueError):pass
            for name,p in children:
                if p.poll() is not None and p.pid not in reported:
                    reported.add(p.pid)
                    print(f'{name} exited: {p.returncode}',flush=True)
                    if name=='web':stopping=True
            time.sleep(1)
    finally:
        for _,p in children:
            if p.poll() is None:p.terminate()
        for _,p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        if running() and running()['pid']==pid:PIDFILE.unlink(missing_ok=True)
        lockfile.close()

def stop():
    from core.app_lifecycle import stop_owned
    from core.listener_check import wait_ports
    from core.install_layout import locked
    with locked(SHARED_ROOT/'run/start.lock'):
        cfg=actual_config();stopped=stop_owned(DATA_ROOT);wait_ports(cfg)
    print('[OK] Stopped verified services:',stopped)


def status():
    d=running();cfg=actual_config(d);local,network=urls(cfg)
    print(f'Zetalvx Image Lab - SDXL Edition {VERSION}')
    print('Status:', 'RUNNING' if d else 'STOPPED')
    if d:print('PID:',d.get('pid'))
    print('HTTPS:', 'yes' if cfg.get('https') else 'no')
    print('Access:', 'LAN' if cfg.get('host')=='0.0.0.0' else 'LOCAL')
    print('Port:',cfg['port'])
    print('Local:',local)
    if network:print('Network:',network)
    print('Data:',DATA_ROOT)

def configure_existing(root):
    """Read paths only. Do not copy credentials, datasets, models or change old venvs."""
    from core.model_registry import update_model
    root=Path(root).expanduser().resolve()
    if not (root/'models').is_dir():raise ValueError('Choose the CreatorStudio parent folder containing models/ and shared/.')
    patch={'checkpoint_roots':str(root/'models/SDXL'),'lora_root':str(root/'models/loras/SDXL')}
    old=root/'shared/config/models.json'
    if old.is_file():
        d=json.loads(old.read_text());m=next((m for m in d.get('models',[]) if m.get('provider')=='sdxl'),{})
        for key in ('checkpoint','inpaint_checkpoint','vae'):
            value=(m.get('config') or {}).get(key)
            if value and Path(value).expanduser().exists():patch[key]=value
    if not patch.get('checkpoint') and (root/'models/SDXL/sd_xl_base_1.0.safetensors').exists():patch['checkpoint']=str(root/'models/SDXL/sd_xl_base_1.0.safetensors')
    update_model('sdxl',{'config':patch})
    cfg=settings()
    if (root/'models/Identity').exists():
        identity_root=root/'models/Identity'
        cfg['identity_root']=str(identity_root)
        cfg['identity_instantid_root']=str(identity_root/'InstantID')
        cfg['identity_insightface_root']=str(identity_root/'insightface')
        cfg['identity_swapper_model']=str(identity_root/'inswapper_128.onnx')
    vendor=root/'shared/identity/vendor/InstantID'
    if vendor.exists():cfg['identity_vendor']=str(vendor)
    atomic_json(SETTINGS_FILE,cfg)
    print('[OK] Reused paths only:',json.dumps(patch,indent=2))
    print('Review Identity model licenses in Setup and restart this app. Original installation unchanged.')

def desktop(policy='ask'):
    from core.desktop_shortcuts import install_shortcuts
    for path in install_shortcuts(DATA_ROOT, APP_ROOT, policy=policy):print('[OK] Collegamento:',path)


def main():
    initialize_environment()
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for cmd in ['init','password','stop','status','doctor','download-configs','identity-code','_serve','setup-code']:sub.add_parser(cmd)
    q=sub.add_parser('desktop');q.add_argument('--policy',choices=['keep','ask','yes','no'],default='ask')
    q=sub.add_parser('start');q.add_argument('--no-browser',action='store_true');g=q.add_mutually_exclusive_group();g.add_argument('--lan',action='store_true');g.add_argument('--local',action='store_true')
    q=sub.add_parser('configure-existing');q.add_argument('root')
    q=sub.add_parser('download-base');q.add_argument('--accept-license',action='store_true')
    q=sub.add_parser('network');q.add_argument('mode',choices=['local','lan'])
    a=p.parse_args()
    if a.command=='init':init()
    elif a.command=='password':password()
    elif a.command=='setup-code':setup_code()
    elif a.command=='desktop':desktop(a.policy)
    elif a.command=='start':start(not a.no_browser,'lan' if a.lan else ('local' if a.local else None))
    elif a.command=='_serve':serve()
    elif a.command=='stop':stop()
    elif a.command=='status':status()
    elif a.command=='identity-code':sys.exit(subprocess.call([sys.executable,str(APP_ROOT/'run.py'),'identity-code'],cwd=APP_ROOT, **hidden_kwargs()))
    elif a.command=='configure-existing':configure_existing(a.root)
    elif a.command=='network':
        cfg=settings();cfg['host']='127.0.0.1' if a.mode=='local' else '0.0.0.0';cfg['https']=True;atomic_json(SETTINGS_FILE,cfg);print('Saved. Restart the app to apply.')
    elif a.command in ('download-configs','download-base'):
        ai=venv_python(runtime_dir('sdxl') or RUNTIME_ROOT/'not-installed')
        if not ai.is_file():raise RuntimeError('SDXL runtime not installed.')
        args=[str(ai),str(APP_ROOT/'run.py'),'models','configs' if a.command=='download-configs' else 'base']
        if getattr(a,'accept_license',False):args+=['--accept-license']
        sys.exit(subprocess.call(args,cwd=APP_ROOT, **hidden_kwargs()))
    elif a.command=='doctor':
        print('Zetalvx Image Lab - SDXL Edition',VERSION,'|',DATA_ROOT)
        for name in ('app','sdxl'):
            py=venv_python(runtime_dir(name) or RUNTIME_ROOT/'not-installed');print(name,py,'exists=',py.exists())
            if py.exists():
                code="import importlib.metadata as m; print({n:m.version(n) for n in ['Flask','Pillow']})" if name=='app' else "import torch, diffusers, transformers; print('torch',torch.__version__,'CUDA',torch.cuda.is_available(),'diffusers',diffusers.__version__,'transformers',transformers.__version__)"
                subprocess.run([str(py),'-c',code],check=False, **hidden_kwargs())
        from core.model_registry import load_registry,validate_model
        for m in load_registry()['models']:print(json.dumps(validate_model(m),indent=2))
        print('Identity paths:',settings()['identity_root'],settings()['identity_vendor'])
        print('Logs:',SHARED_ROOT/'logs')
if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,OSError,subprocess.CalledProcessError) as e:print('[ERROR]',e,file=sys.stderr);sys.exit(1)
