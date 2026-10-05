#!/usr/bin/env python3
# Modified in Zetalvx 0.1.0.42: targeted pre-release stabilization; see audit/STABILIZATION_0_1_0_42.md.
"""Detached stop/restart helper; source-1.0-rc1 adds a source checkout fallback."""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path

CREATE_NO_WINDOW=0x08000000

def active(home: Path) -> Path:
    # Source-only packaging adapter; installed branches below are unchanged.
    source = Path(__file__).resolve().parents[1]
    if (source/'SOURCE_RELEASE.json').is_file():
        from source import source_home
        if Path(home).resolve() != source_home():
            raise ValueError('Source home does not match the running source instance.')
        return source
    if os.name=='nt':
        state=json.loads((home/'install-state.json').read_text(encoding='utf-8'))
        return (home/'versions'/state['current']).resolve(strict=True)
    return (home/'current').resolve(strict=True)

def hidden():
    return {'creationflags':CREATE_NO_WINDOW} if os.name=='nt' else {}

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('--action',choices=['stop','restart','rollback'],required=True);a=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from core.maintenance_state import busy_jobs
    home=Path(a.home).expanduser().absolute();logdir=home/'shared/logs';logdir.mkdir(parents=True,exist_ok=True);log=logdir/'app-control.log'
    pending=home/'shared/run/app-control.pending';pending.parent.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'SDXL_STUDIO_HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
    for k in ('PYTHONPATH','PYTHONHOME','SDXL_STUDIO_HOST_OVERRIDE','SDXL_STUDIO_INSTALLER_ACTIVE'):env.pop(k,None)
    time.sleep(.8)
    try:
        source=active(home); launcher=source/'launcher.py'
        with log.open('a',encoding='utf-8') as out:
            out.write(f'\n=== {a.action} {time.strftime("%Y-%m-%d %H:%M:%S")} ===\n');out.flush()
            busy=busy_jobs(home)
            if busy:
                out.write('Not stopped: finish/cancel active jobs first: '+', '.join(busy[:10])+'\n');out.flush();return 2
            if a.action=='rollback':
                result=subprocess.run([sys.executable,str(source/'scripts/control.py'),'rollback'],cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT,text=True,**hidden())
                return result.returncode
            stop=subprocess.run([sys.executable,str(launcher),'stop'],cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT,text=True,**hidden())
            if stop.returncode not in (0,):return stop.returncode
            if a.action=='restart':
                time.sleep(.7);source=active(home);launcher=source/'launcher.py'
                start=subprocess.run([sys.executable,str(launcher),'start','--no-browser'],cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT,text=True,**hidden())
                return start.returncode
        return 0
    finally:
        try:pending.unlink()
        except FileNotFoundError:pass

if __name__=='__main__':
    raise SystemExit(main())
