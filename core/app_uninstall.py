"""One-use removal approval and a detached, installation-bound runner.
No password is stored, passed on a command line, or written into an uninstall job.
"""
from __future__ import annotations
import contextlib, hashlib, hmac, json, os, re, secrets, subprocess, tempfile, threading, time
from pathlib import Path
from core.install_layout import atomic_json, locked, pointers, release_path, runtime_dirs
from core.platform_support import default_data_root, hidden_kwargs, detached_kwargs, process_start, venv_python
from core.uninstall_plan import make_plan, validate_home, linked

def windows_host():return os.name=='nt'

class UninstallError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message); self.status=status

class Challenges:
    """In-memory, five-minute, single-session and single-action challenges."""
    def __init__(self, clock=time.monotonic):
        self.clock=clock; self.items={}; self.failures={}; self.lock=threading.Lock()
    def issue(self, owner, purge):
        if type(purge) is not bool:raise UninstallError('Invalid data removal option',400)
        with self.lock:
            now=self.clock(); self.items={k:v for k,v in self.items.items() if v['expires']>now}
            # One open challenge per session. No unbounded server memory growth.
            self.items={k:v for k,v in self.items.items() if v['owner']!=owner}
            if len(self.items)>=128:raise UninstallError('Too many pending confirmations. Try later.',429)
            id=secrets.token_hex(16)
            word=secrets.choice(('LUNA','PINETA','RIVA','SASSO','VENTO','FARO'))+'-'+secrets.token_hex(3).upper()
            self.items[id]={'owner':owner,'purge':purge,'word':word,'expires':now+300}
            return {'id':id,'word':word,'expires_in':300}
    def cancel(self, owner, id):
        with self.lock:
            item=self.items.get(id) if isinstance(id,str) else None
            if item and item["owner"]==owner:self.items.pop(id)
    def authorise(self, owner, key, data, password_check, start):
        # Validate and consume under one mutex; concurrent double submissions cannot run twice.
        with self.lock:
            now=self.clock()
            self.failures={k:[x for x in v if now-x<60] for k,v in self.failures.items() if any(now-x<60 for x in v)}
            if len(self.failures)>=256 and key not in self.failures:raise UninstallError('Too many attempts. Try later.',429)
            if len(self.failures.get(key,[]))>=5:raise UninstallError('Too many password attempts. Wait one minute.',429)
            id=data.get('challenge_id');item=self.items.get(id) if isinstance(id,str) else None
            if not item or item['owner']!=owner or item['expires']<=now:raise UninstallError('Confirmation expired. Request a new word.',403)
            word=data.get('word');purge=data.get('purge_data')
            if data.get('understand') is not True or type(purge) is not bool or purge!=item['purge']:
                raise UninstallError('Confirm the exact removal option shown in the summary.',400)
            if not isinstance(word,str) or not word.isascii() or not hmac.compare_digest(word.strip(),item['word']):
                self.failures.setdefault(key,[]).append(now)
                raise UninstallError('The confirmation word does not match.',403)
            a,b=data.get('password'),data.get('password_repeat')
            correct=False
            if isinstance(a,str) and isinstance(b,str) and 1<=len(a)<=1024 and 1<=len(b)<=1024:
                # Require two matching entries, and verify each against the account hash.
                equal=hmac.compare_digest(a.encode('utf-8'),b.encode('utf-8'))
                first=password_check(a);second=password_check(b)
                correct=equal and first and second
            if not correct:
                self.failures.setdefault(key,[]).append(now)
                raise UninstallError('Enter the current app password correctly in both fields.',403)
            self.items.pop(id);self.failures.pop(key,None)
        # Consumed before side effects. A failed preflight requires a NEW explicit confirmation.
        return start(purge)

def safe_job(home, id):
    if not isinstance(id,str) or not re.fullmatch('[a-f0-9]{32}',id):raise UninstallError('Invalid uninstall job',400)
    home=Path(home).absolute()
    for p in (home,home/'shared',home/'shared/uninstall',home/'shared/uninstall'/id):
        if linked(p):raise UninstallError('Linked uninstall state is not allowed')
    return home/'shared/uninstall'/id

def lifecycle_locks(home, *, blocking=False):
    # Control locks must not be created outside the app via links or junctions.
    home=Path(home).absolute()
    for rel in ('install.lock','shared','shared/run','shared/run/start.lock','shared/run/execution.lock','shared/updates','shared/updates/state.lock','shared/updates/execution.lock'):
        if linked(home/rel):raise UninstallError('Linked lifecycle state is not allowed')
    stack=contextlib.ExitStack()
    try:
        for relative in ('install.lock','shared/run/start.lock','shared/updates/execution.lock','shared/updates/state.lock','shared/run/execution.lock'):
            stack.enter_context(locked(Path(home)/relative,blocking=blocking))
        return stack
    except BaseException:
        stack.close();raise

def check_idle_and_update(home):
    from scripts.install import ensure_idle, worker_health
    ensure_idle(home)
    path=Path(home)/'shared/updates/current.json'
    if path.exists():
        id=json.loads(path.read_text()).get('id')
        if not isinstance(id,str) or not re.fullmatch('[a-f0-9]{32}',id):raise UninstallError('Update state needs inspection')
        state=Path(home)/'shared/updates'/id/'state.json'
        if state.is_symlink():raise UninstallError('Linked update state')
        if state.is_file() and json.loads(state.read_text()).get('status') in ('starting','running'):
            raise UninstallError('An update is active. Finish it before uninstalling.')
    cfgpath=Path(home)/'shared/config/settings.json'
    cfg=json.loads(cfgpath.read_text()) if cfgpath.is_file() else {}
    for name,port in [('image',cfg.get('image_port',8299)),('identity',cfg.get('identity_port',8301)),('training',cfg.get('training_port',8300))]:
        try:health=worker_health(port)
        except (OSError,ValueError):continue
        if health.get('busy'):raise UninstallError(name+' is busy. Finish or cancel its work first.')

class UninstallService:
    def __init__(self,home,source):self.home=Path(home).absolute();self.source=Path(source).resolve()
    def _recover_stale_pending(self,h,d):
        pending=h/'uninstall-pending.json'
        if not pending.is_file():return
        try:state=json.loads(pending.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            # A corrupt marker cannot be trusted while it is fresh. Old corrupt
            # markers are recoverable because no process identity can own them.
            try:age=time.time()-pending.stat().st_mtime
            except OSError:age=0
            if age<60:raise UninstallError('Uninstall is already in progress.')
            pending.unlink(missing_ok=True);return
        if state.get('installation_id')!=d['id']:
            raise UninstallError('Uninstall state belongs to another installation. Inspect it before continuing.')
        pid=state.get('cleanup_pid') or state.get('pid')
        start=state.get('cleanup_start') or state.get('process_start')
        if isinstance(pid,int) and start and process_start(pid)==start:
            raise UninstallError('Uninstall is already in progress.')
        created=float(state.get('created_at') or 0)
        if not pid and created and time.time()-created<60:
            raise UninstallError('Uninstall is already in progress.')
        # No tracked owner is alive. Preserve the old report/ticket for diagnosis,
        # but release maintenance mode so a retry can finish the uninstall.
        id=state.get('id')
        if isinstance(id,str) and re.fullmatch('[a-f0-9]{32}',id):
            try:
                f=safe_job(h,id)/'job.json'
                if f.is_file() and not f.is_symlink():
                    ticket=json.loads(f.read_text(encoding='utf-8'))
                    ticket.update(status='interrupted',error='Previous uninstall runner is no longer active; retry is allowed.')
                    atomic_json(f,ticket)
                    report_dir=ticket.get('report_dir')
                    if report_dir:
                        report=Path(report_dir)/'result.json'
                        if not report.exists():atomic_json(report,{'ok':False,'error':'Uninstall runner stopped before cleanup completed. Retry is allowed.','home':str(h),'data_preserved':None})
            except Exception:pass
        pending.unlink(missing_ok=True)
    def check_installed(self):
        h,d=validate_home(self.home);s=pointers(h)
        if not s.get('current') or release_path(h,s['current']).resolve()!=self.source:raise UninstallError('Use the active installed app, not the extracted ZIP.')
        self._recover_stale_pending(h,d)
        return h,d
    def plan(self,purge=False):
        h,d=self.check_installed()
        if type(purge) is not bool:raise UninstallError('Invalid data removal option',400)
        # Browser purge is intentionally limited to the standard application root.
        # No browser request supplies a path; external model directories are never traversed.
        standard=h==default_data_root().expanduser().resolve()
        if purge and not standard:raise UninstallError('Full data removal from the browser is only allowed for the default installation folder.')
        plan=make_plan(h,purge)
        return {**plan,'can_purge_data':standard,'external_paths_deleted':False}
    def start(self,purge):
        plan=self.plan(purge);home=self.home
        try:
            with lifecycle_locks(home):
                self.check_installed();check_idle_and_update(home)
                id=secrets.token_hex(16);folder=safe_job(home,id);folder.mkdir(parents=True,mode=0o700);os.chmod(folder,0o700)
                report_dir=Path(tempfile.mkdtemp(prefix='zetalvx-uninstall-'));os.chmod(report_dir,0o700)
                ticket={**plan,'id':id,'source':str(self.source),'status':'authorised','created_at':time.time(),'report_dir':str(report_dir)}
                atomic_json(folder/'job.json',ticket)
                atomic_json(home/'uninstall-pending.json',{'id':id,'installation_id':plan['installation_id'],'status':'starting','created_at':ticket['created_at']})
                env=dict(os.environ)
                for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','SDXL_STUDIO_INSTALLER_ACTIVE','SDXL_STUDIO_HOST_OVERRIDE'):env.pop(key,None)
                env.update(SDXL_STUDIO_HOME=str(home),PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
                try:
                    if windows_host():
                        from core.windows_uninstall import launch, ENGINE
                        proc, identity = launch(plan, self.source, report_dir, id)
                        ticket.update(pid=proc.pid,process_start=identity,status='starting',engine=ENGINE)
                        atomic_json(folder/'job.json',ticket)
                    else:
                        # Keep the existing POSIX detach path unchanged.
                        py=venv_python(runtime_dirs(home,self.source)['app'])
                        result=subprocess.run([str(py),'-I',str(self.source/'scripts/gui_uninstall.py'),'--home',str(home),'--id',id,'--spawn'],
                            env=env,cwd=self.source,capture_output=True,text=True,encoding='utf-8',check=True,timeout=30,**hidden_kwargs())
                        identity=json.loads(result.stdout)
                        ticket.update(pid=int(identity['pid']),process_start=identity['process_start'],status='starting');atomic_json(folder/'job.json',ticket)
                    state={'id':id,'installation_id':plan['installation_id'],'status':'starting','created_at':ticket['created_at'],'pid':ticket['pid'],'process_start':ticket['process_start'],'report_dir':str(report_dir)}
                    if windows_host():
                        state.update(cleanup_pid=ticket['pid'],cleanup_start=ticket['process_start'],engine=ENGINE)
                    atomic_json(home/'uninstall-pending.json',state)
                except BaseException:
                    (home/'uninstall-pending.json').unlink(missing_ok=True)
                    ticket['status']='failed-to-start';atomic_json(folder/'job.json',ticket);raise
                return {'id':id,'status':'starting','data_preserved':not purge,'home':str(home),'report':str(report_dir/'result.json'),'native_windows':windows_host()}
        except BlockingIOError as exc:raise UninstallError('Another operation is active. Wait before uninstalling.') from exc
