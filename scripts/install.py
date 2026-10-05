#!/usr/bin/env python3
"""Source distribution: shared lifecycle helpers, NOT the automatic installer.

Adapted for source-1.0-rc1 from the Apache-2.0 Windows 1.0.16 baseline.
Function bodies below are retained verbatim for existing application imports.
Automatic dependency installation, bootstrap, staging and activation are omitted.
See docs/SOURCE_BOUNDARY.md and LICENSE / NOTICE.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from core.install_layout import locked, runtime_dirs
from core.platform_support import process_start, venv_python, hidden_kwargs
INSTALL_SESSION_LOG = None
INSTALL_SYSTEM_LOG = None

def _session_log(text):
    for target in (INSTALL_SESSION_LOG,INSTALL_SYSTEM_LOG):
        if not target:continue
        try:
            Path(target).parent.mkdir(parents=True,exist_ok=True)
            with Path(target).open('a',encoding='utf-8') as f:f.write(str(text))
        except OSError:pass

def environment(home, *, background=False):
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'SDXL_STUDIO_HOST_OVERRIDE', 'SDXL_STUDIO_INSTALLER_ACTIVE'):
        env.pop(key, None)
    env.update(SDXL_STUDIO_HOME=str(home), PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
    if background: env.pop('SDXL_STUDIO_NO_BACKGROUND', None)
    else: env['SDXL_STUDIO_NO_BACKGROUND'] = '1'
    return env

def run(command, *, cwd=ROOT, env=None, log=None, capture=False, timeout=None):
    command = [str(x) for x in command]
    line='> '+subprocess.list2cmdline(command)+'\n';print(line,end='',flush=True);_session_log(line)
    if log:
        with Path(log).open('a', encoding='utf-8') as out:
            out.write('> '+subprocess.list2cmdline(command)+'\n'); out.flush()
            proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', **hidden_kwargs())
            try:
                for line in proc.stdout:
                    print(line, end='', flush=True); out.write(line); out.flush(); _session_log(line)
                rc = proc.wait()
            except BaseException:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                raise
            if rc: raise subprocess.CalledProcessError(rc, command)
            return ''
    result = subprocess.run(command, cwd=cwd, env=env, check=True,
        capture_output=capture, text=True, encoding='utf-8', errors='replace', timeout=timeout, **hidden_kwargs())
    return result.stdout if capture else ''

def inventory(py: Path | None) -> dict:
    if py is None or not py.is_file(): return {'exists':False, 'packages':{}}
    code = '''import sys, json, importlib.metadata as m, re
from pathlib import Path
packages={re.sub(r"[-_.]+", "-", d.metadata.get("Name", "")).lower():d.version for d in m.distributions() if d.metadata.get("Name")}
marker={}
try:
 marker=json.loads((Path(sys.prefix)/".zetalvx-runtime.json").read_text(encoding="utf-8"))
except (OSError,ValueError):
 pass
print(json.dumps({"exists":True,"python":list(sys.version_info[:3]),"prefix":sys.prefix,"packages":packages,"runtime_marker":marker}))'''
    try:
        p = subprocess.run([str(py), '-I', '-c', code], capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30, check=True, **hidden_kwargs())
        return json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return {'exists':True, 'error':str(e), 'packages':{}}

def direct_pins(path: Path) -> dict:
    result = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith('-r '): result.update(direct_pins(path.parent/line[3:].strip())); continue
        m = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s#]+)', line)
        if m: result[re.sub('[-_.]+', '-', m[1]).lower()] = m[2]
    return result

def reusable(info, pins) -> bool:
    if not info.get('exists') or info.get('error') or tuple(info.get('python',[])[:2]) not in ((3,11),(3,12)):
        return False
    installed = info.get('packages', {})
    return all(installed.get(n,'').split('+')[0] == v for n,v in pins.items())

def supervisor(home):
    path = home/'shared/run/supervisor.json'
    if not path.exists(): return None
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
        return d if d.get('start') and process_start(int(d['pid'])) == d['start'] else None
    except (OSError, ValueError, KeyError, TypeError): return None

def busy_jobs(home):
    from core.maintenance_state import busy_jobs as collect
    return collect(home)

def ensure_idle(home):
    active = busy_jobs(home)
    if active: raise RuntimeError('Lavori presenti: '+', '.join(active[:8])+'. Terminarli/annullarli dalla GUI prima di aggiornare. Nessun processo fermato.')

def launcher_command(home, release, *args, env=None, capture=False):
    roots = runtime_dirs(home, release)
    py = venv_python(roots['app'])
    # .19 also has launcher.py; direct invocation works without assuming a dispatcher.
    return run([py, release/'launcher.py', *args], cwd=release,
        env={**(env or environment(home, background=True)), 'SDXL_STUDIO_INSTALLER_ACTIVE':'1'}, capture=capture, timeout=None if args and args[0]=='desktop' else 120)

def stop_release(home, release):
    # New installer-side lifecycle even when the running version predates this fix.
    py=venv_python(runtime_dirs(home,release)['app'])
    run([py, ROOT/'scripts/stop_owned.py','--home',home],cwd=ROOT,
        env=environment(home,background=True),timeout=100)
    if supervisor(home):raise RuntimeError('Supervisor not stopped; active version unchanged.')
    with locked(home/'shared/run/supervisor.lock'):pass

def live_state(home):
    d=supervisor(home)
    if not d: return None
    if 'host' not in d:
        cfg=home/'shared/config/settings.json'
        stored=json.loads(cfg.read_text()) if cfg.exists() else {}
        d=dict(d);d['host']=stored.get('host','127.0.0.1')
        if os.name!='nt':
            try:
                environ=Path('/proc/'+str(int(d['pid']))+'/environ').read_bytes().split(b'\0')
                value=next((e.split(b'=',1)[1].decode() for e in environ if e.startswith(b'SDXL_STUDIO_HOST_OVERRIDE=')),None)
                if value in ('127.0.0.1','0.0.0.0'):d['host']=value
            except (OSError,ValueError,KeyError):pass
    return d

def worker_health(port):
    # Only loopback; never use an externally configured HTTP proxy for local probes.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:'+str(int(port))+'/health',timeout=4) as r:
        return json.load(r)

if __name__ == '__main__':
    raise SystemExit('This source package has no automatic app installer. Read docs/INSTALL_LINUX.md or docs/INSTALL_WINDOWS.md.')
