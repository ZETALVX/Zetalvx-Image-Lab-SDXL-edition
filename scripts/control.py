#!/usr/bin/env python3
"""Read-only diagnostics and explicit code/runtime rollback. No user-data rollback."""
from __future__ import annotations
import datetime as dt
import json
import os
import platform
import shutil
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from core.install_layout import *
from core.platform_support import venv_python
from scripts.install import (environment, ensure_idle, inventory, launcher_command, stop_release, supervisor, live_state)
from core.platform_support import hidden_kwargs


def rollback(home):
    with locked(home/'install.lock'):
        state=pointers(home)
        if not state['previous']:raise RuntimeError('Nessuna versione precedente disponibile.')
        old=release_path(home,state['current']);target=release_path(home,state['previous'])
        if not venv_python(runtime_dirs(home,target)['app']).is_file():raise RuntimeError('Runtime precedente non disponibile: rollback non eseguito.')
        ensure_idle(home)
        was_running=live_state(home)
        try:
            with locked(home/'shared/run/start.lock'):
                stop_release(home,old)
                ensure_idle(home)
                set_pointers(home,state['previous'],state['current'])
            if was_running:
                args=['start','--no-browser']
                if was_running.get('host')=='0.0.0.0':args.append('--lan')
                launcher_command(home,target,*args)
        except BaseException:
            stop_release(home,target)
            set_pointers(home,state['current'],state['previous'])
            if was_running:launcher_command(home,old,'start','--no-browser')
            raise
        print('[OK] Versione ripristinata:',state['previous'])
        print('Dati, credenziali, modelli e nuovi lavori conservati. Nessuna cancellazione.')
        print('Le proprietà di sicurezza della versione precedente restano quelle della versione precedente.')


def main():
    args=sys.argv[1:] or ['status'];home=home_path();state=pointers(home)
    source=release_path(home,state['current']);roots=runtime_dirs(home,source)
    if args[0]=='rollback':rollback(home);return 0
    if args[0]=='version':
        print('Zetalvx Image Lab - SDXL Edition',state['current']);print('Home:',home);print('Codice:',source);return 0
    if args[0]=='verify':
        checked=verify_manifest(source);print('[OK]',len(checked),'file verificati');return 0
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+os.urandom(3).hex()
    if args[0] in ('check','tests'):
        report=home/'shared/audits'/('tests-'+stamp+'.json')
        return subprocess.call([str(venv_python(roots['app'])),str(source/'scripts/release_check.py'),'--report',str(report)],cwd=source,env=environment(home), **hidden_kwargs())
    if args[0]=='diagnostics':
        # Curated diagnostics only: never include account files, tokens, cookies, prompts, model images or arbitrary app logs.
        def private_runtime(path):
            if not path:return {'private':False}
            py=venv_python(path);info=inventory(py);prefix=Path(str(info.get('prefix') or '')).absolute() if info.get('prefix') else None
            try:private=bool(prefix and prefix.relative_to((home/'runtime').absolute()) is not None)
            except ValueError:private=False
            return {'python':str(py),'prefix':str(prefix) if prefix else None,'private':private}
        usage=shutil.disk_usage(home);logroot=home/'shared/logs';curated=[]
        logroots=[logroot]
        if os.name=='nt':logroots.append(Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'Zetalvx'/'CreatorStudioSDXL'/'Logs')
        else:logroots.append(Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'CreatorStudioSDXL'/'logs')
        seen_logs=set()
        for lr in logroots:
            for pattern in ('installer/*.log','vision/llama-runtime-*.log'):
                for f in lr.glob(pattern):
                    try:
                        st=f.stat();key=(f.name,st.st_size)
                        if key in seen_logs:continue
                        seen_logs.add(key);curated.append({'path':str(f),'size':st.st_size,'mtime':st.st_mtime})
                    except OSError:pass
        curated=sorted(curated,key=lambda x:x['mtime'],reverse=True)[:20]
        gpu=''
        try:
            if shutil.which('nvidia-smi'):
                gpu=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'],capture_output=True,text=True,timeout=8,**hidden_kwargs()).stdout.strip()
        except (OSError,subprocess.SubprocessError):pass
        report={'version':state['current'],'previous':state['previous'],'home':str(home),
            'system':{'platform':platform.platform(),'python_bootstrap':sys.executable,'disk_free_bytes':usage.free,'disk_total_bytes':usage.total,'gpu':gpu},
            'runtimes':{n:{'path':str(p) if p else None,'inventory':inventory(venv_python(p) if p else None),'isolation':private_runtime(p)} for n,p in roots.items()},
            'running':bool(supervisor(home)),'curated_logs':curated,'gpu_generation_validated':False,'customer_release_approved':False}
        path=home/'shared/audits'/('diagnostics-'+stamp+'.json');atomic_json(path,report)
        text=home/'shared/audits'/('diagnostics-'+stamp+'.txt')
        lines=['Zetalvx Image Lab - SDXL Edition diagnostics '+state['current'],'Home: '+str(home),'Platform: '+report['system']['platform'],'GPU: '+(gpu or 'not detected'),'Disk free: '+str(usage.free),'']
        for name,data in report['runtimes'].items():lines.append(f'Runtime {name}: {data["isolation"]}')
        lines+=['','Curated logs:']+[x['path'] for x in curated]
        for item in curated[:8]:
            f=Path(item['path']);lines+=['','===== '+str(f)+' =====']
            try:
                chunk=f.read_text(encoding='utf-8',errors='replace').splitlines()[-160:];lines.extend(chunk)
            except OSError as exc:lines.append('[unreadable] '+str(exc))
        text.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2));print('Report:',path);print('Combined log:',text);return 0
    raise ValueError('Comando di gestione sconosciuto')

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        print('[ERROR]',exc,file=sys.stderr);raise SystemExit(2)
