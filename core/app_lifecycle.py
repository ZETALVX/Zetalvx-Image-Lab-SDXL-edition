"""Stop only verified service processes belonging to this installation and user.
No port-based kills, no substring matching, no recursive kill of detached updaters.
"""
import json, os, signal, time
from pathlib import Path
import psutil
from core.install_layout import atomic_json
from core.platform_support import process_start

def alive(p):
    try: return p.is_running() and p.status()!=psutil.STATUS_ZOMBIE
    except psutil.Error: return False

def owned_service(p, home):
    try:
        home=Path(home).resolve()
        if p.pid==os.getpid() or not alive(p): return False
        if os.name=='nt':
            if p.username().casefold()!=psutil.Process().username().casefold(): return False
        elif p.uids().real!=os.getuid(): return False
        e=p.environ()
        if not e.get('SDXL_STUDIO_HOME') or Path(e['SDXL_STUDIO_HOME']).resolve()!=home: return False
        cwd=Path(p.cwd()).resolve()
        if cwd.parent != home/'versions' or not (cwd/'launcher.py').is_file(): return False
        a=p.cmdline()
        if len(a)<2: return False
        # Only service entry points are eligible. install.py/gui_update.py remain alive.
        script=Path(a[1])
        if not script.is_absolute(): script=cwd/script
        script=script.resolve()
        if script==cwd/'run.py':
            return a[2:] in (['web'],['image'],['training'],['identity'],['launcher','_serve'])
        if script==cwd/'launcher.py': return a[2:]==['_serve']
        if script==cwd/'app.py': return len(a)==2
        return a[1:3]==['-m','services.image_worker'] or a[1:3]==['-m','services.training_worker'] or a[1:3]==['-m','services.identity_worker']
    except (OSError,ValueError,psutil.Error): return False

def services(home):
    return [p for p in psutil.process_iter() if owned_service(p,home)]

def stop_owned(home, timeout=35):
    home=Path(home).resolve(); snapshot=services(home)
    pidfile=home/'shared/run/supervisor.json'
    try: state=json.loads(pidfile.read_text())
    except (OSError,ValueError): state={}
    p=next((p for p in snapshot if p.pid==state.get('pid')),None)
    if p and process_start(p.pid)==state.get('start'):
        if os.name=='nt': atomic_json(home/'shared/run/stop-request.json', {'pid':p.pid,'start':state['start']})
        else: p.send_signal(signal.SIGTERM)
        end=time.monotonic()+timeout
        while any(alive(q) for q in snapshot) and time.monotonic()<end: time.sleep(.1)
    # Orphans, or a supervisor that failed to finish, are individually revalidated.
    remaining=[p for p in snapshot if alive(p) and owned_service(p,home)]
    for p in remaining:
        try: p.terminate()
        except psutil.NoSuchProcess: pass
    _, remaining=psutil.wait_procs(remaining,timeout=5)
    for p in remaining:
        if alive(p) and owned_service(p,home):
            try: p.kill()
            except psutil.NoSuchProcess: pass
    psutil.wait_procs(remaining,timeout=5)
    still=services(home)
    if still: raise RuntimeError('Owned services still active: '+', '.join(str(p.pid) for p in still))
    if state and process_start(state.get('pid',0))==state.get('start') and state.get('start') is not None:
        try:
            if alive(psutil.Process(int(state['pid']))):raise RuntimeError('Supervisor identity not safely stoppable; metadata preserved.')
        except psutil.NoSuchProcess:pass
    pidfile.unlink(missing_ok=True)
    (home/'shared/run/stop-request.json').unlink(missing_ok=True)
    return [p.pid for p in snapshot]
