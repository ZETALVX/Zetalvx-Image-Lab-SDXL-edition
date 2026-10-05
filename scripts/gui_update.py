#!/usr/bin/env python3
"""Independent updater supervisor. Never imported from an uploaded ZIP.
The --spawn helper deliberately exits to detach ancestry before installer stop.
The uploaded installer executes ONLY after UI password + source-trust consent.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from core.app_updates import UpdateStore,UpdateError
from core.install_layout import VERSION,locked,pointers
from core.platform_support import detached_kwargs,process_start
from core.platform_support import hidden_kwargs

def environment(home):
    env=dict(os.environ)
    for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','SDXL_STUDIO_INSTALLER_ACTIVE','SDXL_STUDIO_HOST_OVERRIDE'):
        env.pop(key,None)
    env.update(SDXL_STUDIO_HOME=str(home),PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    return env

def spawn(store,id):
    folder=store.folder(id)
    # State read is safe here; the caller is holding state.lock and has already saved it.
    state=store.read(id)
    if state['status']!='starting':raise UpdateError('Update was not authorised')
    with (folder/'runner.log').open('ab',buffering=0) as log:
        os.chmod(folder/'runner.log',0o600)
        proc=subprocess.Popen([sys.executable,'-I',str(Path(__file__).absolute()),'--home',str(store.home),'--id',id],
              cwd=ROOT,env=environment(store.home),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
              close_fds=True,**detached_kwargs())
    identity=None
    for _ in range(30):
        identity=process_start(proc.pid)
        if identity:break
        if proc.poll() is not None:break
        time.sleep(.05)
    if not identity:
        proc.terminate();proc.wait(timeout=5)
        raise UpdateError('Cannot track the updater process')
    print(json.dumps({'pid':proc.pid,'process_start':identity}),flush=True)
    return 0

def execute(store,id):
    store._safe_root(create=True)
    with locked(store.root/'execution.lock'):
        state=None
        try:
            with locked(store.root/'state.lock',blocking=True):
                state=store.read(id)
                if state['status']!='starting':raise UpdateError('Update is not awaiting execution')
                store.check_installed();payload=store.recheck(state)
                state.update(status='running',pid=os.getpid(),process_start=process_start(os.getpid()),
                    message='Installer checks running; the app restarts only after preparation succeeds.')
                store.save(state)
            from scripts.install import ensure_idle
            ensure_idle(store.home)
            before=set((store.home/'shared/audits').glob('install-*/result.json'))
            cmd=[sys.executable,'-I',str(payload/'scripts/install.py'),'--home',str(store.home),
                 '--runtime','auto' if state.get('allow_new_runtime') else 'keep','--ai',state['backend'],
                 '--online','--no-browser']
            print('=== GUI update '+state['from_version']+' -> '+state['version']+' ===',flush=True)
            print('Source consent recorded; checksums do not constitute a publisher signature.',flush=True)
            # Trusted, authorised full source package uses its own existing transaction.
            # No shell, arbitrary argument list, driver update, or manual symlink switch.
            result=subprocess.run(cmd,cwd=payload,env=environment(store.home),stdin=subprocess.DEVNULL,check=False, **hidden_kwargs())
            current=pointers(store.home).get('current')
            passed=result.returncode==0 and (current==state['version'] or (current or '').startswith(state['version']+'-'))
            after=set((store.home/'shared/audits').glob('install-*/result.json'))
            new=sorted(after-before,key=lambda p:p.stat().st_mtime)
            state.update(status='completed' if passed else 'failed',exit_code=result.returncode,active_release=current,
                message='Update installed and restarted. Reload the app.' if passed else 'Update did not finish successfully. Read the installer log; do not start another installer until recovery is checked.')
            if new:state['report']=str(new[-1].relative_to(store.home))
            with locked(store.root/'state.lock',blocking=True):store.save(state)
            return 0 if passed else 2
        except BaseException as exc:
            print('[UPDATE ERROR] '+str(exc),flush=True)
            if state:
                with locked(store.root/'state.lock',blocking=True):
                    state.update(status='failed',message=str(exc));store.save(state)
            return 2

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,required=True);parser.add_argument('--id',required=True);parser.add_argument('--spawn',action='store_true')
    args=parser.parse_args();store=UpdateStore(args.home,ROOT,VERSION)
    try:return spawn(store,args.id) if args.spawn else execute(store,args.id)
    except Exception as exc:print('[UPDATE ERROR] '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
