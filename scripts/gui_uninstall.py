#!/usr/bin/env python3
"""Short-lived spawn helper -> tracked independent uninstall runner, no visible console."""
from __future__ import annotations
import argparse,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from core.app_uninstall import safe_job
from core.install_layout import atomic_json,locked
from core.platform_support import detached_kwargs,process_start
CURRENT_JOB=None

def read_ticket(home,id):
    f=safe_job(home,id)/'job.json'
    if f.is_symlink():raise ValueError('Linked uninstall ticket')
    ticket=json.loads(f.read_text())
    if ticket.get('id')!=id or ticket.get('home')!=str(home) or Path(ticket['source']).resolve()!=ROOT:
        raise ValueError('Uninstall ticket identity mismatch')
    if time.time()-ticket['created_at']>300:raise ValueError('Uninstall authorisation expired')
    return f,ticket

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('--id',required=True);p.add_argument('--spawn',action='store_true');a=p.parse_args()
    global CURRENT_JOB
    home=Path(a.home).absolute();CURRENT_JOB=(home,a.id);f,ticket=read_ticket(home,a.id)
    if a.spawn:
        if ticket['status']!='authorised':raise ValueError('Uninstall not authorised')
        folder=f.parent
        with (folder/'runner.log').open('ab',buffering=0) as log:
            os.chmod(folder/'runner.log',0o600)
            proc=subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),'--home',str(home),'--id',a.id],
                 cwd=ROOT,env=os.environ.copy(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,close_fds=True,**detached_kwargs())
        identity=None
        for _ in range(30):
            identity=process_start(proc.pid)
            if identity:break
            if proc.poll() is not None:break
            time.sleep(.05)
        if not identity:
            proc.terminate();proc.wait(timeout=5);raise ValueError('Cannot track uninstall runner')
        print(json.dumps({'pid':proc.pid,'process_start':identity}),flush=True);return 0
    # Gives HTTP response a chance to reach the browser; completion remains server-side.
    time.sleep(1)
    # Wait until the request has recorded the runner identity and released install.lock.
    with locked(home/'install.lock',blocking=True):
        f,ticket=read_ticket(home,a.id)
        if ticket['status']!='starting' or ticket.get('pid')!=os.getpid() or ticket.get('process_start')!=process_start(os.getpid()):
            raise ValueError('Runner is not the authorised process')
        ticket['status']='running';atomic_json(f,ticket)
        pending=home/'uninstall-pending.json'
        if pending.is_file():
            state=json.loads(pending.read_text(encoding='utf-8'))
            if state.get('id')==a.id:
                state.update(status='running',pid=os.getpid(),process_start=process_start(os.getpid()))
                atomic_json(pending,state)
    from scripts.uninstall import perform
    return perform(home,purge=ticket['purge_data'],job_id=a.id,report_dir=ticket['report_dir'])
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:
        # Only this tracked runner can clear its own pending marker on failure.
        try:
            home,id=CURRENT_JOB;f,ticket=read_ticket(home,id)
            if ticket.get('pid')==os.getpid() and ticket.get('process_start')==process_start(os.getpid()):
                pending=home/'uninstall-pending.json'
                if pending.exists() and json.loads(pending.read_text()).get('id')==id:pending.unlink()
                ticket.update(status='failed',error=str(e));atomic_json(f,ticket)
                report=Path(ticket['report_dir'])/'result.json'
                if not report.exists():atomic_json(report,{'ok':False,'error':str(e),'home':str(home)})
        except Exception:pass
        print('[UNINSTALL ERROR]',e,file=sys.stderr);raise SystemExit(2)
