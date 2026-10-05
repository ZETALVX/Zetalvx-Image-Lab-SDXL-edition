#!/usr/bin/env python3
"""Local uninstaller. GUI requests use a one-use authorisation, never a password argument."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
# Route Windows before importing psutil/Flask or reading the active release state.
if __name__=='__main__' and os.name=='nt':
    from core.windows_uninstall import powershell_executable
    raise SystemExit(subprocess.call([powershell_executable(), '-NoLogo', '-NoProfile',
        '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'scripts/uninstall_windows_entry.ps1'),
        *sys.argv[1:]], cwd=tempfile.gettempdir()))
from core.install_layout import home_path, atomic_json
from core.uninstall_plan import make_plan, execute_linux
from core.desktop_ui import dialog
from core.app_lifecycle import stop_owned, alive
from core.platform_support import detached_kwargs, process_start
from core.app_uninstall import lifecycle_locks, check_idle_and_update
import psutil

def perform(home, *, purge=False, gui=False, job_id=None, report_dir=None):
    if os.name=='nt':
        raise RuntimeError('Use UNINSTALL.cmd or the native Windows uninstall service. The legacy Python runner is disabled on Windows.')
    home=Path(home).absolute();plan=make_plan(home,purge)
    pending=home/'uninstall-pending.json'
    if os.name!='nt' and os.geteuid()==0:raise ValueError('Run as the installing user, without sudo.')
    report_dir=Path(report_dir) if report_dir else Path(tempfile.mkdtemp(prefix='zetalvx-uninstall-'))
    report_dir.mkdir(parents=True,exist_ok=True);os.chmod(report_dir,0o700)
    owns_pending=False
    try:
        # The HTTP process releases these locks after the detached runner is tracked.
        with lifecycle_locks(home,blocking=bool(job_id)):
            if pending.exists():
                d=json.loads(pending.read_text())
                if not job_id or d.get('id')!=job_id or d.get('installation_id')!=plan['installation_id']:
                    raise RuntimeError('Uninstall already in progress. Check the cleanup report before retrying.')
            elif job_id:raise RuntimeError('Uninstall authorisation no longer exists')
            owns_pending=True
            check_idle_and_update(home)
            atomic_json(pending,{'id':job_id,'pid':os.getpid(),'installation_id':plan['installation_id'],'status':'running'})
            stop_owned(home)
            # An unrelated process using our paths is not killed. Refuse deletion instead.
            me=psutil.Process();ancestors=me.parents();own={me.pid,*[p.pid for p in ancestors]}
            h=home.resolve()
            for q in psutil.process_iter():
                if q.pid in own or not alive(q):continue
                try:
                    cwd=Path(q.cwd()).resolve();exe=Path(q.exe()).resolve()
                    if cwd==h or h in cwd.parents or h in exe.parents:
                        raise RuntimeError('Close the remaining process before uninstalling: PID '+str(q.pid))
                except (psutil.NoSuchProcess,psutil.AccessDenied,OSError):pass
        os.chdir(report_dir);execute_linux(plan)
        atomic_json(report_dir/'result.json',{'ok':True,'data_preserved':not purge,'home':str(home),'external_paths_deleted':False})
        message='Disinstallazione completata / Uninstall complete. '+('Personal data deleted.' if purge else 'Personal data preserved at '+str(home))
        if gui:dialog(message)
        else:print(message,flush=True)
        return 0
    except BaseException as e:
        if owns_pending:pending.unlink(missing_ok=True)
        atomic_json(report_dir/'result.json',{'ok':False,'error':str(e),'home':str(home),'data_preserved':None,'note':'Deletion may be partial if a filesystem error occurred; consult this report.'})
        raise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home');p.add_argument('--plan',action='store_true');p.add_argument('--gui',action='store_true');p.add_argument('--purge-data',action='store_true');p.add_argument('--yes',action='store_true');a=p.parse_args()
    home=home_path(a.home);plan=make_plan(home,a.purge_data)
    if a.plan:print(json.dumps(plan,indent=2));return 0
    if not a.yes:
        if not dialog('Rimuovere Zetalvx Image Lab e i runtime? Modelli, progetti e account restano conservati.\nRemove app and runtime? Models, projects and account are kept by default.',question=True):return 0
        if a.gui and not a.purge_data:
            a.purge_data=dialog('Eliminare ANCHE modelli, immagini, progetti, preset e account?\nDelete ALL personal data too? Choose No to keep your data.',question=True)
        if a.purge_data and not dialog('CONFERMA ELIMINAZIONE DEFINITIVA di tutti i dati in:\n'+str(home)+'\n\nPermanently delete all data in this installation?',question=True):return 0
    return perform(home,purge=a.purge_data,gui=a.gui)
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as e:
        if '--gui' in sys.argv:dialog(str(e))
        else:print('[ERROR]',e,file=sys.stderr)
        raise SystemExit(2)
