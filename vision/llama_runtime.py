# Modified in Zetalvx 1.0.10: verified stable -> nightly-tag.txt -> exact binary build.
# Modified in Zetalvx 0.1.0.48: resilient official-release selection, current Linux/Windows asset naming,
# persistent preparation status/logging. Apache-2.0 application code; upstream llama.cpp retains its license.
from __future__ import annotations
import datetime as dt
import hashlib, json, os, platform, re, shutil, stat, subprocess, tarfile, time, zipfile
from pathlib import Path
from urllib.parse import urlsplit, quote, unquote
from core.safe_paths import portable_relative, safe_child, is_link
from core.install_layout import locked, atomic_json
from core.download_security import PublicHTTPS, TokenStore, DownloadError

RELEASES_API='https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=50'
LATEST_RELEASE_API='https://api.github.com/repos/ggml-org/llama.cpp/releases/latest'
MAX_RELEASE_PAGES=4
RELEASE_BY_ID='https://api.github.com/repos/ggml-org/llama.cpp/releases/{release_id}'
RELEASE_BY_TAG='https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{tag}'
MAX_NIGHTLY_REFERENCE=128
MAX_ARCHIVE=2*1024**3
MAX_EXTRACTED=4*1024**3

class LlamaRuntimeError(ValueError):
    def __init__(self,message,code='llama_prepare_failed'):
        super().__init__(message);self.code=code

class LlamaRuntimeCompatibilityError(LlamaRuntimeError):
    """Only executable/backend compatibility may trigger an automatic fallback.
    Integrity, extraction, license and transport failures never bypass verification.
    """
    def __init__(self,message):super().__init__(message,'llama_backend_unavailable')

def runtime_environment(bin_dir, base=None):
    """Private loader paths for this child process, never OS/PATH configuration."""
    env=dict(os.environ if base is None else base)
    key='PATH' if os.name=='nt' else 'LD_LIBRARY_PATH'
    env[key]=str(Path(bin_dir).resolve())+(os.pathsep+env[key] if env.get(key) else '')
    return env


def executable_name(): return 'llama-server.exe' if os.name=='nt' else 'llama-server'
def managed_executable(home): return Path(home)/'runtime'/'llama.cpp'/'build'/'bin'/executable_name()

def _archive_name(name, directory=False):
    if not isinstance(name,str): raise LlamaRuntimeError('Invalid archive path')
    while name.startswith('./'): name=name[2:]
    if directory: name=name.rstrip('/')
    if not name or name=='.':
        if directory: return None
        raise LlamaRuntimeError('Empty archive path')
    try: return portable_relative(name).as_posix()
    except ValueError as exc: raise LlamaRuntimeError(str(exc)) from None

def _extract(archive:Path,dest:Path):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    seen=set();regular=set();total=0;count=0
    def target(name,size,directory):
        nonlocal total,count
        name=_archive_name(name,directory)
        if name is None:return None
        count+=1;total+=max(0,int(size))
        if count>20000 or total>MAX_EXTRACTED:raise LlamaRuntimeError('llama.cpp archive exceeds extraction limits')
        key=name.casefold()
        if key in seen:raise LlamaRuntimeError('Duplicate/case-colliding archive path')
        seen.add(key)
        try:
            out=safe_child(dest,name)
            if directory:out.mkdir(parents=True,exist_ok=True)
            else:out.parent.mkdir(parents=True,exist_ok=True)
            return safe_child(dest,name)
        except (ValueError,FileExistsError) as exc:raise LlamaRuntimeError('Unsafe llama.cpp archive destination') from exc
    def write(source,out,size):
        done=0
        with out.open('xb') as f:
            while True:
                chunk=source.read(min(1024*1024,max(1,size-done+1)))
                if not chunk:break
                done+=len(chunk)
                if done>size:raise LlamaRuntimeError('Archive member exceeds its declared size')
                f.write(chunk)
        if done!=size:raise LlamaRuntimeError('Truncated archive member')
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as z:
                for i in z.infolist():
                    mode=(i.external_attr>>16)&0xffff;kind=stat.S_IFMT(mode)
                    if kind not in (0,stat.S_IFREG,stat.S_IFDIR) or i.flag_bits&1:raise LlamaRuntimeError('Links/special/encrypted archive entries are not allowed')
                    out=target(i.filename,i.file_size,i.is_dir())
                    if out is not None and not i.is_dir():
                        with z.open(i) as f:write(f,out,i.file_size)
            return
        links={}
        with tarfile.open(archive,'r:*') as t:
            for m in t:
                if m.issym():
                    # Upstream Linux packages contain versioned lib*.so symlinks.
                    # Resolve only same-directory library names, then COPY bytes;
                    # never create a symlink or dereference an OS path from a tar.
                    name=_archive_name(m.name)
                    library=r'lib[A-Za-z0-9_.+-]+\.so(?:\.[0-9]+)*'
                    if (not re.fullmatch(library,Path(name).name)
                            or not re.fullmatch(library,m.linkname)):
                        raise LlamaRuntimeError('Links/devices/special archive entries are not allowed')
                    out=target(name,0,False)
                    links[out]=safe_child(dest,(Path(name).parent/m.linkname).as_posix())
                    continue
                if not (m.isfile() or m.isdir()):raise LlamaRuntimeError('Links/devices/special archive entries are not allowed')
                out=target(m.name,m.size,m.isdir())
                if out is not None and m.isfile():
                    f=t.extractfile(m)
                    if f is None:raise LlamaRuntimeError('Invalid llama.cpp release archive')
                    with f:write(f,out,m.size)
                    regular.add(out)
        for out,source in links.items():
            chain={out}
            while source in links:
                if source in chain:raise LlamaRuntimeError('Cyclic shared-library link in archive')
                chain.add(source);source=links[source]
            if source not in regular or not source.is_file() or is_link(source):raise LlamaRuntimeError('Missing shared-library link target')
            size=source.stat().st_size;total+=size
            if total>MAX_EXTRACTED:raise LlamaRuntimeError('llama.cpp archive exceeds extraction limits')
            with source.open('rb') as f:write(f,out,size)
        return
    except (tarfile.TarError,zipfile.BadZipFile,TypeError) as exc:
        raise LlamaRuntimeError('Invalid llama.cpp release archive') from exc

def _preserve_notices(source,staging,asset_name):
    folder=staging/'licenses'/asset_name
    for p in source.rglob('*'):
        if p.is_file() and re.match(r'^(license|notice|copying|copyright)([._-]|$)',p.name,re.I):
            out=safe_child(folder,p.relative_to(source).as_posix());out.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,out)

def _find_server(root:Path):
    name=executable_name().lower()
    found=[p for p in root.rglob('*') if p.is_file() and p.name.lower()==name]
    if len(found)!=1: raise LlamaRuntimeError('Official llama.cpp package did not contain exactly one llama-server executable')
    return found[0]

def _copy_payload(source_dir:Path,dest:Path):
    for p in source_dir.iterdir():
        if p.is_file(): shutil.copy2(p,dest/p.name)

def _asset_url(asset):
    u=urlsplit(str(asset.get('browser_download_url') or ''))
    if u.scheme!='https' or u.hostname!='github.com' or not u.path.startswith('/ggml-org/llama.cpp/releases/download/'):
        raise LlamaRuntimeError('Unexpected llama.cpp release asset URL')
    if u.username or u.password or u.port not in (None,443) or u.query or u.fragment:raise LlamaRuntimeError('Unexpected llama.cpp asset URL')
    return u.geturl()

def _release_metadata_valid(d):
    return (isinstance(d,dict) and type(d.get('id')) is int and d.get('id',0)>0
            and re.fullmatch(r'[A-Za-z0-9._-]+',str(d.get('tag_name',''))) is not None
            and isinstance(d.get('assets'),list) and not d.get('draft'))

def _release_valid(d):
    # Direct selection still requires a published stable release. A prerelease
    # is usable ONLY when its exact bNNNN tag is referenced by a verified stable.
    return _release_metadata_valid(d) and not d.get('prerelease')

def _asset_in_release(release,asset):
    # Asset names/URLs must agree with the exact release returned by GitHub.
    # A different tag or repository is an integrity error, never a fallback.
    try:
        if not isinstance(asset,dict):raise ValueError('Invalid release asset')
        name=str(asset.get('name') or '')
        if not name or portable_relative(name).name!=name:raise ValueError('Invalid release asset name')
        url=_asset_url(asset)
        expected='/ggml-org/llama.cpp/releases/download/'+str(release['tag_name'])+'/'+name
        if unquote(urlsplit(url).path)!=expected:raise ValueError('Asset URL does not belong to its declared release')
        return url
    except (ValueError,KeyError) as exc:
        raise LlamaRuntimeError(str(exc),'llama_integrity_error') from None

def _under(path:Path,parent:Path):
    try:path.absolute().relative_to(parent.absolute());return True
    except ValueError:return False

class LlamaRuntimeManager:
    def __init__(self,home):
        self.home=Path(home).expanduser().resolve();self.root=self.home/'runtime'/'llama.cpp';self.meta=self.root/'managed.json';self.selection=self.root/'selection.json';self.operation=self.root/'status.json';self.transport=PublicHTTPS(TokenStore(self.home/'secrets'))
        self.log_dir=self.home/'shared/logs/vision';self._log_path=None;self._system_log_path=None
    def _system_log_root(self):
        if os.name=='nt':
            base=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))
            return base/'Zetalvx'/'CreatorStudioSDXL'/'Logs'/'vision'
        base=Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))
        return base/'CreatorStudioSDXL'/'logs'/'vision'
    def _log(self,message):
        if not self._log_path and not self._system_log_path:return
        stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        for target in (self._log_path,self._system_log_path):
            if not target:continue
            try:
                target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('a',encoding='utf-8') as f:f.write(f'[{stamp}] {message}\n')
            except OSError:pass
    def _state(self,state,message='',progress=0,error='',release='',backend='',error_code=''):
        release=release or getattr(self,'_active_release','');backend=backend or getattr(self,'_active_backend','')
        payload={'schema':1,'state':state,'message':message,'progress':max(0,min(100,int(progress or 0))),
                 'error':str(error or '')[:2000],'release':release,'backend':backend,'updated_at':time.time(),
                 'log_path':str(self._log_path) if self._log_path else '',
                 'system_log_path':str(self._system_log_path) if self._system_log_path else '',
                 'error_code':error_code,'fallbacks':getattr(self,'_fallbacks',[])}
        self.root.mkdir(parents=True,exist_ok=True);atomic_json(self.operation,payload);self._log((state+': '+(message or error or '')).strip())
    def status(self):
        exe=managed_executable(self.home);meta={};op={}
        try:
            if self.meta.is_file():meta=json.loads(self.meta.read_text(encoding='utf-8'))
        except (OSError,ValueError):meta={}
        try:
            if self.operation.is_file():op=json.loads(self.operation.read_text(encoding='utf-8'))
        except (OSError,ValueError):op={}
        return {'installed':exe.is_file(),'executable':str(exe) if exe.is_file() else '',
                'version':meta.get('release',''),'backend':meta.get('backend',''),'source':'ggml-org/llama.cpp' if meta else '',
                'managed':bool(meta and exe.is_file()),'state':op.get('state','ready' if exe.is_file() else 'idle'),
                'message':op.get('message',''),'progress':op.get('progress',100 if exe.is_file() else 0),'error':op.get('error',''),
                'log_path':op.get('log_path',''),'system_log_path':op.get('system_log_path',''),
                'operation_release':op.get('release',''),'operation_backend':op.get('backend',''),
                'error_code':op.get('error_code',''),'fallbacks':op.get('fallbacks',[])}
    def _fetch_releases(self):
        self._state('searching','Reading official llama.cpp releases…',2)
        self._binary_release_cache={}
        releases=[];seen=set();errors=[]
        def read(url):
            try:return self.transport.json(url)
            except DownloadError as exc:
                # PublicHTTPS has already stripped secrets/redirect queries from its errors.
                detail=str(exc);errors.append(detail);self._log('Release metadata '+url+': '+detail)
                return None
        def add(items):
            for item in items:
                if _release_valid(item) and item['id'] not in seen:
                    releases.append(item);seen.add(item['id'])
        data=read(RELEASES_API)
        if data is not None and not isinstance(data,list):
            errors.append('Invalid official llama.cpp releases metadata');data=None
        add(data or [])
        # Frequent b* prereleases can push the latest stable beyond the first 50.
        # Do NOT relabel a prerelease as stable: ask the official dedicated endpoint.
        if not releases:
            latest=read(LATEST_RELEASE_API)
            if _release_valid(latest):add([latest])
            elif latest is not None:self._log('Latest endpoint did not return a published full release')
        # Bounded fallback for missing latest metadata. No HTML scraping or arbitrary URLs.
        if not releases and isinstance(data,list) and len(data)>=50:
            for page in range(2,MAX_RELEASE_PAGES+1):
                more=read(RELEASES_API+'&page='+str(page))
                if not isinstance(more,list):break
                add(more)
                if releases or len(more)<50:break
        try:selected=json.loads(self.selection.read_text(encoding='utf-8')) if self.selection.is_file() else {}
        except (OSError,ValueError):selected={}
        rid=selected.get('stable_release_id',selected.get('id'))
        selected_tag=selected.get('stable_release_tag',selected.get('tag_name'))
        if type(rid) is int and rid>0 and rid not in seen:
            old=read(RELEASE_BY_ID.format(release_id=rid))
            if _release_valid(old) and old['id']==rid and (not selected_tag or old['tag_name']==selected_tag):add([old])
        if not releases:
            text=' | '.join(errors)
            code=('llama_api_limited' if any(x in text for x in ('401','403','429')) else
                  'llama_metadata_invalid' if 'JSON' in text or 'metadata' in text else
                  'llama_network_error' if errors else 'llama_no_stable')
            raise LlamaRuntimeError('No published stable official release was available. '+(text or 'Only draft/prerelease or empty metadata was returned.'),code)
        self._log('Stable release candidates: '+', '.join(str(x['tag_name']) for x in releases[:12]))
        return releases[:12]
    def _resolve_binary_release(self,release):
        """Follow the upstream stable -> nightly-tag.txt -> bNNNN contract.

        Never pick an arbitrary prerelease and never derive a b-tag from a
        version/commit number. Both pointer and binaries retain upstream hashes.
        The pointer is tiny, read as data only, and cached for this preparation.
        """
        if not _release_valid(release):
            raise LlamaRuntimeError('A published stable parent release is required','llama_metadata_invalid')
        key=(release['id'],release['tag_name'])
        cache=getattr(self,'_binary_release_cache',{})
        if key in cache:return cache[key]
        refs=[a for a in release['assets'] if isinstance(a,dict) and a.get('name')=='nightly-tag.txt']
        if not refs:  # legacy full release with binaries attached
            cache[key]=release;self._binary_release_cache=cache
            return release
        if len(refs)!=1:
            raise LlamaRuntimeError('Ambiguous nightly-tag.txt reference','llama_integrity_error')
        ref=refs[0];url=_asset_in_release(release,ref)
        size=ref.get('size');digest=str(ref.get('digest') or '').lower()
        if type(size) is not int or not 0<size<=MAX_NIGHTLY_REFERENCE:
            raise LlamaRuntimeError('Invalid nightly-tag.txt size','llama_integrity_error')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):
            raise LlamaRuntimeError('Missing upstream SHA-256 for nightly-tag.txt','llama_integrity_error')
        self._log('Reading verified binary reference for '+release['tag_name'])
        try:
            with self.transport.open(url) as response:
                raw=response.small(MAX_NIGHTLY_REFERENCE)
        except DownloadError as exc:
            self._log('Binary reference transport: '+str(exc))
            raise LlamaRuntimeError('Cannot read the official nightly-tag.txt reference: '+str(exc),'llama_network_error') from None
        if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest.split(':',1)[1]:
            raise LlamaRuntimeError('nightly-tag.txt size/SHA-256 mismatch','llama_integrity_error')
        try:tag=raw.decode('ascii').strip()
        except UnicodeError:
            raise LlamaRuntimeError('nightly-tag.txt is not an ASCII build tag','llama_metadata_invalid') from None
        if not re.fullmatch(r'b[1-9][0-9]{0,11}',tag):
            raise LlamaRuntimeError('nightly-tag.txt must contain one bNNNN build tag','llama_metadata_invalid')
        try:build=self.transport.json(RELEASE_BY_TAG.format(tag=tag))
        except DownloadError as exc:
            self._log('Linked release metadata: '+str(exc))
            code='llama_api_limited' if any(v in str(exc) for v in ('401','403','429')) else 'llama_network_error'
            raise LlamaRuntimeError('Cannot read the officially linked binary release '+tag+': '+str(exc),code) from None
        if not _release_metadata_valid(build) or build['tag_name']!=tag:
            raise LlamaRuntimeError('Linked release is missing, draft or has an unexpected tag','llama_metadata_invalid')
        official='https://github.com/ggml-org/llama.cpp/releases/tag/'+tag
        if build.get('html_url') and build['html_url']!=official:
            raise LlamaRuntimeError('Linked release is not from ggml-org/llama.cpp','llama_integrity_error')
        # Keep the upstream prerelease flag; do not mislabel the build as stable.
        build=dict(build)
        build['_stable_reference']={'id':release['id'],'tag_name':release['tag_name'],
            'asset_id':ref.get('id'),'asset_name':'nightly-tag.txt','digest':digest,
            'binary_tag':tag,'binary_prerelease':bool(build.get('prerelease'))}
        self._log('Official binary mapping: '+release['tag_name']+' -> '+tag+
            ' (nightly-tag.txt SHA-256 verified; upstream prerelease='+str(bool(build.get('prerelease')))+')')
        cache[key]=build;self._binary_release_cache=cache
        return build
    def _platform(self):
        machine=platform.machine().lower()
        if machine not in ('amd64','x86_64'):raise LlamaRuntimeError('Managed llama.cpp runtime currently supports x64 Windows/Linux hosts')
        if os.name=='nt':return 'windows'
        if sys_platform().startswith('linux'):return 'linux'
        raise LlamaRuntimeError('Managed llama.cpp runtime is available on Windows and Linux')
    def _has_nvidia(self):
        exe=shutil.which('nvidia-smi')
        if not exe:return False
        try:
            r=subprocess.run([exe,'--query-gpu=name','--format=csv,noheader'],capture_output=True,text=True,timeout=8,
                             creationflags=(0x08000000 if os.name=='nt' else 0))
            return r.returncode==0 and bool(r.stdout.strip())
        except (OSError,subprocess.TimeoutExpired):return False
    def _choose_backend(self,release,backend):
        system=self._platform();assets=release['assets'];matches=[]
        for a in assets:
            n=str(a.get('name') or '').lower()
            if n.startswith('cudart-'):continue
            if system=='windows':
                if backend=='cuda12' and re.search(r'-bin-win-cuda-12(?:\.\d+)?-x64\.zip$',n):matches.append(a)
                elif backend=='vulkan' and re.search(r'-bin-win-vulkan-x64\.zip$',n):matches.append(a)
                elif backend=='cpu' and re.search(r'-bin-win-cpu-x64\.zip$',n):matches.append(a)
            else:
                if backend=='cuda12' and re.search(r'-bin-ubuntu-cuda-12(?:\.\d+)?-x64\.(?:tar\.gz|zip)$',n):matches.append(a)
                elif backend=='vulkan' and re.search(r'-bin-ubuntu-vulkan-x64\.(?:tar\.gz|zip)$',n):matches.append(a)
                elif backend=='cpu' and re.search(r'-bin-ubuntu-x64\.(?:tar\.gz|zip)$',n):matches.append(a)
        if len(matches)!=1:raise LlamaRuntimeError('release has no unique '+backend+' package for this host')
        main=matches[0];companions=[]
        if backend=='cuda12':
            n=str(main.get('name') or '').lower();m=re.search(r'cuda-(12(?:\.\d+)?)-x64',n)
            if not m:raise LlamaRuntimeError('CUDA package name does not declare its CUDA 12 runtime version')
            marker='cuda-'+m.group(1)+'-x64'
            suffix=(r'-bin-win-'+re.escape(marker)+r'\.zip$' if system=='windows' else
                    r'-bin-ubuntu-'+re.escape(marker)+r'\.(?:tar\.gz|zip)$')
            companions=[a for a in assets if str(a.get('name') or '').lower().startswith('cudart-')
                        and re.search(suffix,str(a.get('name') or '').lower())]
            if len(companions)!=1:raise LlamaRuntimeError('CUDA package is missing its matching official runtime library archive')
        return backend,main,companions
    def _select(self,releases,preference='auto'):
        pref=str(preference or 'auto').lower()
        if pref not in ('auto','cuda12','vulkan','cpu'):raise LlamaRuntimeError('Unsupported llama.cpp runtime choice')
        order=(['cuda12','vulkan','cpu'] if self._has_nvidia() else ['vulkan','cpu']) if pref=='auto' else [pref]
        failures=[]
        candidates=[]
        for backend in order:
            for parent in releases:
                # Resolve lazily: a usable newest release must not be blocked by
                # an unnecessary request for an older release's reference.
                release=self._resolve_binary_release(parent)
                if not any(r['id']==release['id'] for r in candidates):candidates.append(release)
                try:
                    chosen=self._choose_backend(release,backend)
                    for asset in [chosen[1]]+chosen[2]:_asset_in_release(release,asset)
                    self._log(f'Selected {release["tag_name"]} / {backend} / {chosen[1].get("name")}')
                    return release,*chosen
                except LlamaRuntimeError as exc:
                    if exc.code=='llama_integrity_error':raise
                    failures.append(f'{release.get("tag_name")}/{backend}: {exc}')
        self._log('Selection failures: '+' | '.join(failures[-12:]))
        for release in candidates[:3]:
            self._log('Published assets '+release['tag_name']+': '+', '.join(str(a.get('name','')) for a in release['assets'] if isinstance(a,dict)))
        raise LlamaRuntimeError('No compatible official llama.cpp binary was found in the recent stable releases','llama_no_binary')
    def _download_asset(self,asset,dest,progress=None,index=1,count=1):
        url=_asset_url(asset);size=int(asset.get('size') or 0);expected=str(asset.get('digest') or '').lower()
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',expected):raise LlamaRuntimeError('GitHub did not provide an expected SHA-256 digest: binary not installed','llama_integrity_error')
        expected=expected.split(':',1)[1]
        if size<=0 or size>MAX_ARCHIVE:raise LlamaRuntimeError('Invalid or oversized llama.cpp release asset')
        h=hashlib.sha256();done=0;last_pct=-1;last_report=0.;name=str(asset.get('name') or 'llama.cpp')
        try:
            with self.transport.open(url) as r, dest.open('xb') as f:
                length=int(r.headers.get('Content-Length') or 0)
                if length and length!=size:raise LlamaRuntimeError('Release asset length differs from GitHub metadata')
                for chunk in r.chunks():
                    if not chunk:continue
                    done+=len(chunk)
                    if done>size:raise LlamaRuntimeError('llama.cpp download exceeded expected length')
                    f.write(chunk);h.update(chunk)
                    pct=int(done*100/size) if size else 0
                    overall=((index-1)+(done/size if size else 0))/max(1,count)
                    now=time.monotonic()
                    if done==size or (pct!=last_pct and now-last_report>=0.4):
                        self._state('downloading',f'Downloading {name} · {pct}% · file {index}/{count}',10+int(overall*55))
                        if progress:progress(done,size,index,count,'Downloading '+name)
                        last_pct=pct;last_report=now
                f.flush();os.fsync(f.fileno())
        except DownloadError as exc:
            self._log('Download transport: '+str(exc))
            raise LlamaRuntimeError('llama.cpp download failed; check Internet access and retry','llama_network_error') from None
        if done!=size:raise LlamaRuntimeError('llama.cpp download was incomplete')
        self._state('verifying',f'Verifying SHA-256 · {name}',67)
        if h.hexdigest()!=expected:raise LlamaRuntimeError('llama.cpp SHA-256 mismatch: binary will not be extracted or executed','llama_integrity_error')
        self._log(f'Verified {name}: sha256 {expected}')
        return h.hexdigest()
    def install(self,preference='auto',progress=None):
        if is_link(self.root):raise LlamaRuntimeError('Managed runtime root cannot be a link')
        self.root.mkdir(parents=True,exist_ok=True);self.log_dir.mkdir(parents=True,exist_ok=True)
        stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+os.urandom(3).hex()
        self._log_path=self.log_dir/('llama-runtime-'+stamp+'.log')
        self._system_log_path=self._system_log_root()/('llama-runtime-'+stamp+'.log')
        self._state('starting','Preparing managed llama.cpp runtime…',1)
        try:
            with locked(self.root/'prepare.lock',blocking=False):return self._install(preference,progress)
        except BaseException as exc:
            message=str(exc) if isinstance(exc,LlamaRuntimeError) else type(exc).__name__+': operation failed'
            self._state('failed','Preparation failed',0,error=message,error_code=getattr(exc,'code','llama_prepare_failed'))
            raise
    def _install(self,preference='auto',progress=None):
        releases=self._fetch_releases()
        choice=self._select(releases,preference)
        self._fallbacks=[]
        while True:
            release,backend,main,companions=choice
            try:return self._install_choice(release,backend,main,companions,progress)
            except LlamaRuntimeCompatibilityError as exc:
                if str(preference or 'auto').lower()!='auto' or backend=='cpu':raise
                self._fallbacks.append({'backend':backend,'reason':str(exc)})
                self._log('Backend fallback after '+backend+' self-check: '+str(exc))
                remaining=['vulkan','cpu'] if backend=='cuda12' else ['cpu']
                choice=None
                for fallback in remaining:
                    try:choice=self._select(releases,fallback);break
                    except LlamaRuntimeError as candidate_error:
                        if candidate_error.code!='llama_no_binary':raise
                if choice is None:raise
                self._state('fallback','Trying the next compatible backend…',7,backend=choice[1])

    def _self_check(self,exe,backend):
        env=runtime_environment(exe.parent)
        def run(args):
            try:r=subprocess.run([str(exe),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,errors='replace',timeout=30,env=env,creationflags=(0x08000000 if os.name=='nt' else 0))
            except (OSError,subprocess.TimeoutExpired) as exc:
                self._log('llama-server self-check: '+type(exc).__name__)
                raise LlamaRuntimeCompatibilityError('llama-server could not be started after installation') from None
            self._log('llama-server '+' '.join(args)+': '+(r.stdout or '').strip()[:3000])
            if r.returncode!=0:raise LlamaRuntimeCompatibilityError('llama-server self-check failed after installation')
            return r.stdout or ''
        run(['--version'])
        if backend!='cpu':
            devices=run(['--list-devices'])
            pattern=r'(?im)^\s*'+('CUDA' if backend=='cuda12' else 'Vulkan')+r'\d+\s*:'
            if not re.search(pattern,devices):
                raise LlamaRuntimeCompatibilityError('llama-server has no usable '+backend+' device on this host')

    def _install_choice(self,release,backend,main,companions,progress=None):
        tag=release['tag_name'];self._active_release=tag;self._active_backend=backend;self._state('selected',f'Selected {tag} · {backend}',6,release=tag,backend=backend)
        incoming=self.root/('.incoming-'+str(os.getpid())+'-'+str(time.time_ns()));incoming.mkdir(parents=True,exist_ok=False)
        staging=self.root/('build.new-'+str(os.getpid())+'-'+str(time.time_ns()));bin_dir=staging/'bin';bin_dir.mkdir(parents=True,exist_ok=False)
        hashes={};assets=[main]+companions
        try:
            for i,a in enumerate(assets,1):
                name=str(a['name'])
                if portable_relative(name).name!=name:raise LlamaRuntimeError('Invalid release asset name')
                archive=safe_child(incoming,name);hashes[name]=self._download_asset(a,archive,progress,i,len(assets))
                self._state('extracting',f'Extracting {name} · file {i}/{len(assets)}',72+int(i/max(1,len(assets))*10),release=tag,backend=backend)
                extracted=incoming/('extract-'+str(i));extracted.mkdir();_extract(archive,extracted);_preserve_notices(extracted,staging,name)
                if i==1:
                    server=_find_server(extracted);_copy_payload(server.parent,bin_dir)
                else:
                    files=[p for p in extracted.rglob('*') if p.is_file() and (p.name.lower().endswith('.dll') if self._platform()=='windows' else re.search(r'\.so(?:\.[0-9]+)*$',p.name))]
                    if not files:raise LlamaRuntimeError('Empty llama.cpp CUDA runtime package')
                    common=files[0].parent
                    if all(p.parent==common for p in files):_copy_payload(common,bin_dir)
                    else:
                        for p in files:
                            out=bin_dir/p.name
                            if out.exists():raise LlamaRuntimeError('Duplicate llama.cpp CUDA payload filename')
                            shutil.copy2(p,out)
            self._state('license','Retrieving upstream llama.cpp license…',84,release=tag,backend=backend)
            license_url='https://raw.githubusercontent.com/ggml-org/llama.cpp/'+quote(tag,safe='')+'/LICENSE'
            try:
                with self.transport.open(license_url) as r:license_bytes=r.small(1024*1024)
            except DownloadError:raise LlamaRuntimeError('Cannot retrieve the selected llama.cpp license; existing runtime preserved') from None
            if b'Permission is hereby granted' not in license_bytes:raise LlamaRuntimeError('Unexpected upstream llama.cpp license')
            license_dir=staging/'licenses'/'llama.cpp';license_dir.mkdir(parents=True,exist_ok=True);(license_dir/'LICENSE').write_bytes(license_bytes)
            exe=bin_dir/executable_name()
            if not exe.is_file():raise LlamaRuntimeError('llama-server executable missing after extraction')
            if os.name!='nt':exe.chmod(exe.stat().st_mode|0o755)
            self._state('testing','Running llama-server self-check…',90,release=tag,backend=backend)
            self._self_check(exe,backend)
            final=self.root/'build';backup=self.root/('build.previous-'+str(time.time_ns()))
            if is_link(final):raise LlamaRuntimeError('Managed runtime build cannot be a link')
            old_meta=self.meta.read_bytes() if self.meta.is_file() else None;moved=False;published=False
            try:
                self._state('publishing','Publishing verified llama.cpp runtime…',96,release=tag,backend=backend)
                if final.exists():final.rename(backup);moved=True
                staging.rename(final);published=True
                meta={'schema':3,'release':tag,'release_id':release['id'],'backend':backend,'installed_at':time.time(),
                      'assets':[{'id':a.get('id'),'name':a['name'],'size':a['size'],'digest':a['digest']} for a in assets],
                      'sha256':hashes,'upstream_digest_verified':True,'license_sha256':hashlib.sha256(license_bytes).hexdigest(),
                      'source':'https://github.com/ggml-org/llama.cpp','fallbacks':self._fallbacks,
                      'stable_reference':release.get('_stable_reference'),
                      'binary_prerelease':bool(release.get('prerelease'))}
                atomic_json(self.meta,meta)
                atomic_json(self.selection,{'schema':2,'id':release['id'],'tag_name':tag,'backend':backend,
                    'assets':[a['name'] for a in assets],'source':'ggml-org/llama.cpp','selected_at':time.time(),
                    'stable_release_id':release.get('_stable_reference',{}).get('id',release['id']),
                    'stable_release_tag':release.get('_stable_reference',{}).get('tag_name',tag)})
            except BaseException:
                if published and final.exists():shutil.rmtree(final)
                if moved:backup.rename(final)
                if old_meta is not None:self.meta.write_bytes(old_meta)
                raise
            if moved:shutil.rmtree(backup,ignore_errors=True)
            self._state('ready',f'Managed llama.cpp runtime ready · {tag} · {backend}',100,release=tag,backend=backend)
            if progress:
                try:progress(1,1,len(assets),len(assets),'llama.cpp runtime ready')
                except Exception:pass
            return self.status()
        finally:
            shutil.rmtree(incoming,ignore_errors=True)
            if staging.exists():shutil.rmtree(staging,ignore_errors=True)

def sys_platform():
    import sys
    return sys.platform
