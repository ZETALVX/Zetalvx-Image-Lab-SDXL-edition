"""Local ZIP update staging. No uploaded Python is imported during validation.
Checksums establish integrity, NOT publisher authenticity. Only an authenticated,
re-confirmed administrator can authorise execution via the detached runner.
Standard library; no downloads and no modification of active versions/runtimes here.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zipfile

from core.install_layout import (atomic_json, child, locked, pointers, release_path,
    runtime_dirs, sha256, verify_manifest)
from core.platform_support import process_start, venv_python
from core.platform_support import hidden_kwargs

PRODUCT = 'zetalvx-creator-studio-sdxl'
SCHEMA = 1
MAX_ZIP = 128 * 1024**2
MAX_FILES = 4000
MAX_FILE = 64 * 1024**2
MAX_TOTAL = 512 * 1024**2
BUSY_STATES = {'starting', 'running'}
FINAL_STATES = {'completed', 'failed', 'interrupted', 'discarded'}
VERSION_RE = re.compile(r'\d{1,4}(?:\.\d{1,4}){2,3}')
ID_RE = re.compile(r'[a-f0-9]{32}')
REQUIRED = {'app.py','launcher.py','scripts/install.py','core/runtime_env.py',
            'core/install_layout.py','requirements-app.txt','requirements-sdxl.txt',
            'UPDATE_PACKAGE.json','LICENSE'}

class UpdateError(ValueError):
    def __init__(self,message,status=400):super().__init__(message);self.status=status

def version_tuple(value):
    if not isinstance(value,str) or not VERSION_RE.fullmatch(value):
        raise UpdateError('Invalid update version')
    parts=tuple(map(int,value.split('.')))
    return parts + (0,)*(4-len(parts))

def host_platform():return 'windows' if os.name=='nt' else 'linux'

def portable_path(name):
    """Reject ambiguous names on both Linux and Windows, before writing anything."""
    if not isinstance(name,str) or not name or len(name)>240 or '\\' in name or ':' in name or name.startswith('/'):
        raise UpdateError('Invalid archive path')
    if any(ord(c)<32 or c in '<>"|?*' for c in name):raise UpdateError('Invalid archive path')
    parts=name.rstrip('/').split('/')
    reserved={'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}
    for part in parts:
        if part in {'','.','..'} or part.endswith((' ','.')) or part.split('.')[0].upper() in reserved:
            raise UpdateError('Unsafe archive path')
    return '/'.join(parts)

def validate_package(zip_path:Path, destination:Path, *, installed_version:str,
                     platform_name=None, expected_sha256=''):
    """Extract only regular members into a new private destination, then verify.
    Rejects unlisted files, symlinks, devices, duplicates and archive bombs.
    Does not execute installer --plan or import anything from the new package.
    """
    zip_path=Path(zip_path);destination=Path(destination)
    platform_name=platform_name or host_platform()
    if zip_path.stat().st_size>MAX_ZIP:raise UpdateError('Update ZIP exceeds 128 MiB',413)
    digest=sha256(zip_path)
    if expected_sha256:
        expected_sha256=expected_sha256.strip().lower()
        if not re.fullmatch(r'[0-9a-f]{64}',expected_sha256):raise UpdateError('SHA-256 must contain 64 hexadecimal characters')
        if not __import__('hmac').compare_digest(digest,expected_sha256):raise UpdateError('Published ZIP checksum does not match')
    if destination.exists():raise UpdateError('Staging directory already exists')
    created=False
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries=archive.infolist()
            if not entries or len(entries)>MAX_FILES:raise UpdateError('Invalid archive member count')
            seen={};roots=set();files=[];total=0
            for item in entries:
                path=portable_path(item.filename)
                if path.casefold() in seen:raise UpdateError('Duplicate archive path')
                seen[path.casefold()]=item.is_dir()
                roots.add(path.split('/')[0])
                kind=stat.S_IFMT(item.external_attr>>16)
                if kind not in (0,stat.S_IFREG,stat.S_IFDIR) or (kind==stat.S_IFDIR and not item.is_dir()) or (kind==stat.S_IFREG and item.is_dir()):
                    raise UpdateError('Only regular files and directories are allowed')
                if item.flag_bits&1:raise UpdateError('Encrypted ZIP archives are not supported')
                if item.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise UpdateError('Unsupported ZIP compression')
                if item.is_dir():continue
                if item.file_size>MAX_FILE:raise UpdateError('An update member is too large',413)
                if path.endswith('/UPDATE_PACKAGE.json') and item.file_size>64*1024:raise UpdateError('Update metadata too large',413)
                if path.endswith('/MANIFEST.sha256') and item.file_size>2*1024**2:raise UpdateError('Update manifest too large',413)
                if item.file_size>1024**2 and item.file_size/max(1,item.compress_size)>250:raise UpdateError('Excessive ZIP compression ratio',413)
                total+=item.file_size;files.append((item,path))
            if len(roots)!=1 or total>MAX_TOTAL:raise UpdateError('Expected one source folder, maximum 512 MiB extracted')
            top=next(iter(roots))
            if not re.fullmatch(r'zetalvx_creator_studio_sdxl_v[0-9_]+_(?:linux|windows)',top):
                raise UpdateError('This is not a supported SDXL update ZIP')
            relative_files=[path[len(top)+1:] for _,path in files if path.startswith(top+'/')]
            if len(relative_files)!=len(files) or not REQUIRED.union({'MANIFEST.sha256'}).issubset(relative_files):
                raise UpdateError('Incomplete SDXL source package')
            # File-vs-directory conflicts are rejected before extraction.
            for item,path in files:
                for parent in PurePosixPath(path).parents:
                    if str(parent)!='.' and seen.get(str(parent).casefold()) is False:raise UpdateError('Archive path conflict')
            destination.parent.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(destination.parent).free < total + MAX_ZIP:
                raise UpdateError('Not enough free space to stage the update',507)
            destination.mkdir(mode=0o700);created=True
            actual=0
            for item,path in files:
                rel=path[len(top)+1:];out=child(destination,rel)
                out.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                size=0
                with archive.open(item) as src,out.open('xb') as dst:
                    os.chmod(out,0o600)
                    while True:
                        block=src.read(1024**2)
                        if not block:break
                        size+=len(block);actual+=len(block)
                        if size>MAX_FILE or actual>MAX_TOTAL or size>item.file_size:raise UpdateError('Expanded ZIP exceeds declared limits',413)
                        dst.write(block)
                if size!=item.file_size:raise UpdateError('Truncated ZIP member')
        checked=set(verify_manifest(destination))
        if checked != set(relative_files)-{'MANIFEST.sha256'} or not REQUIRED.issubset(checked):
            raise UpdateError('Manifest does not cover every package file')
        desc=json.loads((destination/'UPDATE_PACKAGE.json').read_text(encoding='utf-8'))
        if not isinstance(desc,dict):raise UpdateError('Invalid update metadata object')
        if desc.get('schema')!=SCHEMA or desc.get('product')!=PRODUCT:raise UpdateError('Update is for another application')
        if desc.get('platform')!=platform_name:raise UpdateError('ZIP is for a different operating system')
        if desc.get('kind')!='full-source-online':raise UpdateError('Unsupported update package type')
        target=desc.get('version')
        if version_tuple(target)<=version_tuple(installed_version):raise UpdateError('Select a newer version; use the rollback command for an older one')
        if version_tuple(desc.get('minimum_updater','0.1.0.29'))>version_tuple(installed_version):raise UpdateError('This update needs a newer updater; use INSTALL/UPDATE from the ZIP')
        # Compare data-only release status and literal version assignments, never import.
        import ast
        for f in ['core/runtime_env.py','core/install_layout.py']:
            tree=ast.parse((destination/f).read_text(encoding='utf-8'))
            versions=[node.value.value for node in tree.body if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant)
                      and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets)]
            if versions != [target]:raise UpdateError('Conflicting version metadata')
        expected_root='zetalvx_creator_studio_sdxl_v'+target.replace('.','_')+'_'+platform_name
        if top!=expected_root:raise UpdateError('Package folder and metadata disagree')
        return {'version':target,'platform':platform_name,'sha256':digest,'manifest_sha256':sha256(destination/'MANIFEST.sha256'),
                'files':len(checked),'extracted_bytes':total,'signature_verified':False,'publisher_hash_supplied':bool(expected_sha256)}
    except (zipfile.BadZipFile,RuntimeError,KeyError,SyntaxError,UnicodeError) as exc:
        if created:shutil.rmtree(destination)
        raise UpdateError('Invalid update ZIP: '+str(exc)) from exc
    except BaseException:
        if created:shutil.rmtree(destination)
        raise

class UpdateStore:
    def __init__(self,home:Path,source:Path,version:str):
        self.home=Path(home).absolute();self.source=Path(source).absolute();self.version=version
        self.root=self.home/'shared/updates'
    def _safe_root(self,create=False):
        for p in (self.home,self.home/'shared',self.root):
            if p.is_symlink():raise UpdateError('Updates directory must not be a symbolic link')
        if create:self.root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.root,0o700)
        return self.root
    def folder(self,id):
        if not isinstance(id,str) or not ID_RE.fullmatch(id):raise UpdateError('Invalid update identifier')
        self._safe_root();return child(self.root,id)
    def read(self,id):
        p=self.folder(id)/'state.json'
        if not p.is_file() or p.is_symlink():raise UpdateError('Update not found',404)
        return json.loads(p.read_text(encoding='utf-8'))
    def save(self,state):
        state['updated_at']=time.time();atomic_json(self.folder(state['id'])/'state.json',state)
    def current_state(self,reconcile=False):
        path=self._safe_root()/'current.json'
        if not path.exists():return None
        if path.is_symlink():raise UpdateError('Invalid update state')
        id=json.loads(path.read_text())['id'];state=self.read(id)
        if reconcile and state['status'] in BUSY_STATES:
            pid=state.get('pid');identity=state.get('process_start')
            alive=bool(pid and identity and process_start(pid)==identity)
            if not alive and time.time()-state['updated_at']>90:
                state.update(status='interrupted',message='Update process is no longer running. Check installer logs and the active version before retrying.')
                self.save(state)
        return state
    def maintenance(self):
        state=self.current_state(reconcile=True)
        return bool(state and state.get('status') in BUSY_STATES)
    def check_installed(self):
        if (self.home/'uninstall-pending.json').exists():raise UpdateError('Uninstall in progress; update not started',409)
        state=pointers(self.home)
        if not state.get('current') or release_path(self.home,state['current']).resolve()!=self.source.resolve():
            raise UpdateError('Run updates from the active installed app, not the extracted source folder',409)
        return state
    def import_zip(self,stream,filename,expected_sha256=''):
        self.check_installed();self._safe_root(create=True)
        if not str(filename).lower().endswith('.zip'):raise UpdateError('Select a ZIP archive')
        with locked(self.root/'state.lock'):
            active=self.current_state(reconcile=True)
            if active and active['status'] not in FINAL_STATES:raise UpdateError('Finish or discard the previous update first',409)
            id=uuid.uuid4().hex;folder=self.folder(id);folder.mkdir(mode=0o700);zip_path=folder/'package.zip'
            try:
                count=0
                with zip_path.open('xb') as dst:
                    os.chmod(zip_path,0o600)
                    while True:
                        block=stream.read(1024**2)
                        if not block:break
                        count+=len(block)
                        if count>MAX_ZIP:raise UpdateError('Update ZIP exceeds 128 MiB',413)
                        dst.write(block)
                info=validate_package(zip_path,folder/'payload',installed_version=self.version,expected_sha256=expected_sha256)
                # Only one staged ZIP is retained. Failure logs are separate, but old payloads
                # are removed when the user intentionally imports the next candidate.
                if active:
                    old=self.folder(active['id'])
                    if (old/'payload').is_dir():shutil.rmtree(old/'payload')
                    (old/'package.zip').unlink(missing_ok=True)
                state={'schema':1,'id':id,'status':'ready','from_version':self.version,'from_release':self.source.name,
                       'created_at':time.time(),'message':'ZIP checked. Awaiting confirmation; no uploaded code has run.',**info}
                self.save(state);atomic_json(self.root/'current.json',{'id':id});return state
            except BaseException:shutil.rmtree(folder);raise
    def recheck(self,state):
        folder=self.folder(state['id']);payload=folder/'payload'
        if payload.is_symlink():raise UpdateError('Staged payload must not be a symlink')
        if sha256(folder/'package.zip')!=state['sha256'] or sha256(payload/'MANIFEST.sha256')!=state['manifest_sha256']:
            raise UpdateError('Staged package changed; discard and import again')
        checked=set(verify_manifest(payload))
        actual={p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()}
        if any(p.is_symlink() for p in payload.rglob('*')) or actual!=checked|{'MANIFEST.sha256'}:
            raise UpdateError('Unexpected file in staged package')
        return payload
    def discard(self,id):
        self._safe_root(create=True)
        with locked(self.root/'state.lock'):
            state=self.read(id)
            if state['status'] in BUSY_STATES:raise UpdateError('The installer cannot be interrupted from this page',409)
            folder=self.folder(id)
            if (folder/'payload').is_dir():shutil.rmtree(folder/'payload')
            (folder/'package.zip').unlink(missing_ok=True)
            state.update(status='discarded',message='ZIP discarded; installed version unchanged.');self.save(state)
            return state
    def start(self,id,allow_new_runtime=False):
        self._safe_root(create=True)
        with locked(self.root/'state.lock'):
            self.check_installed();state=self.read(id)
            if state['status']!='ready':raise UpdateError('Import a ready ZIP before starting',409)
            if self.current_state()['id']!=id:raise UpdateError('A different update is selected',409)
            self.recheck(state)
            # Use the installed, trusted inspector, not code from the upload.
            from scripts.install import ensure_idle
            ensure_idle(self.home)
            runtime_map=self.source/'.installed-runtime.json'
            mapping=json.loads(runtime_map.read_text()) if runtime_map.exists() else {}
            backend=mapping.get('backend')
            if backend not in {'cu126','cpu','none'}:raise UpdateError('Cannot determine the current runtime backend; use UPDATE from the ZIP')
            state.update(status='starting',message='Starting the independent updater…',allow_new_runtime=bool(allow_new_runtime),backend=backend)
            self.save(state)
            env=dict(os.environ)
            for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','SDXL_STUDIO_INSTALLER_ACTIVE','SDXL_STUDIO_HOST_OVERRIDE'):
                env.pop(key,None)
            env.update(SDXL_STUDIO_HOME=str(self.home),PYTHONDONTWRITEBYTECODE='1')
            # A short-lived helper exits before the runner starts installing. This avoids
            # the Windows app process-tree shutdown killing the updater as a descendant.
            command=[str(venv_python(runtime_dirs(self.home,self.source)['app'])),'-I',str(self.source/'scripts/gui_update.py'),
                     '--home',str(self.home),'--id',id,'--spawn']
            try:
                p=subprocess.run(command,cwd=self.source,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30,check=True, **hidden_kwargs())
                identity=json.loads(p.stdout)
                state.update(pid=int(identity['pid']),process_start=str(identity['process_start']))
                self.save(state);return state
            except BaseException as exc:
                state.update(status='failed',message='Could not start updater: '+str(exc));self.save(state);raise
    def public_state(self):
        state=self.current_state(reconcile=True)
        if not state:return None
        fields=('id','status','version','platform','sha256','files','extracted_bytes','signature_verified',
                'publisher_hash_supplied','message','created_at','updated_at','exit_code','active_release','allow_new_runtime','report')
        result={key:state[key] for key in fields if key in state}
        log=self.folder(state['id'])/'runner.log'
        if log.is_file() and not log.is_symlink():
            with log.open('rb') as f:
                f.seek(max(0,log.stat().st_size-12000));result['log_tail']=f.read(12000).decode('utf-8','replace')
        return result
