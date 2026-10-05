# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
"""Transactional code-only InstantID installer. Never writes in a model directory.

The UI, CLI and installer share this module. No imports from downloaded code are
executed during installation; checks use the AST. User-managed trees are read-only.
"""
from __future__ import annotations
import ast, contextlib, hashlib, json, os, shutil, ssl, tempfile, threading, time
from pathlib import Path
from core import file_lock as fcntl
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler
from urllib.error import URLError, HTTPError
from .runtime_env import SHARED_ROOT, SETTINGS_FILE, settings, atomic_json
from .identity_paths import VENDOR_FILES, vendor_files

REPO = 'https://github.com/instantX-research/InstantID'
REVISION = '2145b67f9607da6234702063692330185f374486'
CODE_FILES = (*VENDOR_FILES, 'LICENSE')
MAX_FILE = 4 * 1024 * 1024

class CodeInstallError(ValueError): pass

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CodeInstallError('Unexpected redirect from the pinned official code URL.')

def fetch_code(relative):
    """Allowlisted, revision-pinned Python/license files, not weights or a ZIP."""
    if relative not in CODE_FILES: raise CodeInstallError('Unknown upstream code file')
    url=f'https://raw.githubusercontent.com/instantX-research/InstantID/{REVISION}/{relative}'
    opener=build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
    error=None
    for attempt in range(2):
        try:
            with opener.open(Request(url, headers={'User-Agent':'Zetalvx-SDXL-Code-Installer/0.1.0.12'}), timeout=35) as r:
                data=r.read(MAX_FILE+1)
                if len(data)>MAX_FILE:raise CodeInstallError('Code file exceeds the size limit: '+relative)
                if not data or data.lstrip().lower().startswith((b'<!doctype html', b'<html')):
                    raise CodeInstallError('The official URL did not return a code file: '+relative)
                return data
        except (OSError, URLError, HTTPError) as e:
            error=e
            if attempt==0:time.sleep(.5)
    raise CodeInstallError('Cannot download '+relative+' from raw.githubusercontent.com (HTTPS). Check DNS/network/CA. '+str(error)[:240])

def verify_code(root):
    root=Path(root); errors=[]
    for relative in CODE_FILES:
        p=root/relative
        if p.is_symlink() or not p.is_file() or not p.stat().st_size:
            errors.append(relative+': missing or empty');continue
        if p.stat().st_size>MAX_FILE:
            errors.append(relative+': too large');continue
        if relative.endswith('.py'):
            try:
                tree=ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
                names={n.name for n in tree.body if isinstance(n,(ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))}
                if relative.startswith('pipeline_'):
                    cls='StableDiffusionXLInstantIDImg2ImgPipeline' if 'img2img' in relative else 'StableDiffusionXLInstantIDPipeline'
                    if not {cls,'draw_kps'}<=names:errors.append(relative+': pipeline class or draw_kps missing')
            except (SyntaxError,UnicodeError) as e:errors.append(relative+': invalid Python: '+str(e)[:180])
        elif relative=='LICENSE' and 'Apache License' not in p.read_text(errors='replace'):
            errors.append('LICENSE: expected Apache license text')
    if errors:raise CodeInstallError('; '.join(errors))
    return {rel:hashlib.sha256((root/rel).read_bytes()).hexdigest() for rel in CODE_FILES}

@contextlib.contextmanager
def settings_lock():
    SETTINGS_FILE.parent.mkdir(parents=True,exist_ok=True)
    with (SETTINGS_FILE.parent/'settings.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)

class CodeInstaller:
    def __init__(self, shared_root=None, config_file=None):
        self.shared=Path(shared_root or SHARED_ROOT)
        self.config_file=Path(config_file or SETTINGS_FILE)
        self.folder=self.shared/'identity/vendor'
        self.state_file=self.shared/'config/instantid_code_install.json'
        self.lock_file=self.shared/'run/instantid-code.lock'
        self._thread=None;self._mutex=threading.RLock()
    @property
    def target(self):return self.folder/('InstantID-'+REVISION[:12])
    def _read_cfg(self):
        try:return json.loads(self.config_file.read_text())
        except FileNotFoundError:return {}
    def _state(self, **fields):
        with self._mutex:
            try:d=json.loads(self.state_file.read_text())
            except (OSError,ValueError):d={}
            d.update(fields,updated_at=time.time())
            atomic_json(self.state_file,d)
            return d
    def status(self):
        try:d=json.loads(self.state_file.read_text())
        except (OSError,ValueError):return {'status':'idle','target':str(self.target),'revision':REVISION}
        # A lock, not a PID or a volatile thread, decides if an install is still active.
        if d.get('status') in ('queued','running'):
            self.lock_file.parent.mkdir(parents=True,exist_ok=True)
            with self.lock_file.open('a') as f:
                try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:return d
                try:
                    if not (self._thread and self._thread.is_alive()):
                        d=self._state(status='interrupted',stage='interrupted',message='Code installation was interrupted. Retry safely; weights and configuration were preserved.')
                finally:fcntl.flock(f,fcntl.LOCK_UN)
        return d
    def _publish_config(self, target, previous):
        self.config_file.parent.mkdir(parents=True,exist_ok=True)
        with (self.config_file.parent/'settings.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            cfg=self._read_cfg()
            if str(cfg.get('identity_vendor') or '')!=previous:
                raise CodeInstallError('The code path was edited during installation. Verified code is at '+str(target)+'. It was not activated; use that folder or retry.')
            # Backup only on an actual path change. Never change host or child weight paths.
            if str(target)!=previous:
                atomic_json(self.config_file.parent/('settings.before-instantid-'+str(time.time_ns())+'.json'),cfg)
            cfg['identity_vendor']=str(target)
            atomic_json(self.config_file,cfg)
            fcntl.flock(lock,fcntl.LOCK_UN)
    def prepare(self, downloader=fetch_code):
        self.lock_file.parent.mkdir(parents=True,exist_ok=True)
        with self.lock_file.open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise CodeInstallError('Code installation is already running')
            previous=str(self._read_cfg().get('identity_vendor') or '')
            self._state(id=str(time.time_ns()),status='running',stage='checking',completed=0,total=len(CODE_FILES),message='Checking code; model files will not be touched.',error='',previous_path=previous,target=str(self.target),revision=REVISION)
            staging=None
            try:
                configured=Path(previous).expanduser() if previous else self.folder/'InstantID'
                # Existing complete custom code is preserved, never refreshed in place.
                if configured.is_dir():
                    try:hashes=verify_code(configured)
                    except (CodeInstallError,OSError):pass
                    else:
                        self._publish_config(configured,previous)
                        return self._state(status='completed',stage='ready',target=str(configured),completed=len(CODE_FILES),message='Existing code verified and preserved. No weights changed.',files=hashes)
                # Managed installs may never escape into a symlinked models tree.
                if not self.folder.resolve().is_relative_to(self.shared.resolve()):
                    raise CodeInstallError('Managed code directory points outside app shared data. Fix the symlink or select valid existing code; no files were changed.')
                target=self.target
                valid=False
                if target.is_dir():
                    try:hashes=verify_code(target);valid=True
                    except (CodeInstallError,OSError):pass
                if not valid:
                    self.folder.mkdir(parents=True,exist_ok=True)
                    # Even a manually placed partial tree is preserved: use a different owned directory.
                    if target.exists() or target.is_symlink():target=self.folder/(target.name+'-'+str(time.time_ns()))
                    staging=Path(tempfile.mkdtemp(prefix='.instantid-install-',dir=self.folder))
                    self._state(stage='downloading',target=str(target))
                    for i,relative in enumerate(CODE_FILES):
                        self._state(message='Downloading code: '+relative,current_file=relative,completed=i)
                        data=downloader(relative)
                        if not isinstance(data,bytes) or not data or len(data)>MAX_FILE:raise CodeInstallError('Invalid download: '+relative)
                        dest=staging/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                    self._state(stage='verifying',message='Validating Python source and license.')
                    hashes=verify_code(staging)
                    atomic_json(staging/'ZETALVX_CODE_SOURCE.json',{'repository':REPO,'revision':REVISION,'files':hashes})
                    staging.rename(target);staging=None
                self._state(stage='activating',message='Saving the verified code path. Weight paths remain unchanged.',target=str(target))
                self._publish_config(target,previous)
                atomic_json(self.shared/'config/instantid_code_source.json',{'repository':REPO,'commit':REVISION,'path':str(target),'files':hashes})
                return self._state(status='completed',stage='ready',completed=len(CODE_FILES),message='InstantID code installed and connected. No page refresh or weight download needed.',files=hashes,error='')
            except Exception as e:
                error=str(e)[:1800]
                self._state(status='failed',stage='failed',message='Code was not activated. Existing files were preserved.',error=error)
                raise CodeInstallError(error) from e
            finally:
                if staging and staging.is_dir():shutil.rmtree(staging)
                fcntl.flock(lock,fcntl.LOCK_UN)
    def start(self):
        with self._mutex:
            if self._thread and self._thread.is_alive():return self.status()
            # Avoid creating concurrent network jobs when the CLI is running.
            if self.status().get('status') in ('queued','running'):return self.status()
            def run():
                try:self.prepare()
                except Exception:pass # structured error is persisted by prepare()
            self._state(status='queued',stage='queued',message='Code installation queued.',error='',completed=0,total=len(CODE_FILES),target=str(self.target))
            self._thread=threading.Thread(target=run,daemon=True,name='instantid-code-installer');self._thread.start()
            return self.status()
