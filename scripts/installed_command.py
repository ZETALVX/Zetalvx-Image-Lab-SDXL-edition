#!/usr/bin/env python3
# Modified in Zetalvx 0.1.0.42: targeted pre-release stabilization; see audit/STABILIZATION_0_1_0_42.md.
"""Stable SDXL dispatcher. Also works after rolling back to the legacy .19.
Standard library only; does not depend on the extracted ZIP folder.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def hidden_kwargs():
    return {"creationflags": 0x08000000} if os.name=="nt" else {}

def get_home():
    fallback = (Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'CreatorStudioSDXL'
        if os.name=='nt' else Path.home()/'.local/share/CreatorStudioSDXL')
    return Path(os.environ.get('SDXL_STUDIO_HOME',str(fallback))).expanduser().absolute()


def release(home, name):
    if not re.fullmatch(r'[0-9][0-9A-Za-z._-]{0,119}', name or ''):
        raise ValueError('Invalid installed version')
    p=(home/'versions'/name).resolve(strict=True)
    if p.parent != (home/'versions').resolve():raise ValueError('Version escapes installation')
    return p


def active(home):
    if os.name=='nt':
        name=json.loads((home/'install-state.json').read_text(encoding='utf-8'))['current']
        return release(home,name)
    p=(home/'current').resolve(strict=True)
    if not (home/'current').is_symlink() or p != release(home,p.name):
        raise ValueError('Invalid current symlink')
    return p


def interpreter(home, source):
    f=source/'.installed-runtime.json'
    rel=json.loads(f.read_text())['runtimes']['app'] if f.is_file() else 'runtime/app'
    if not isinstance(rel,str) or not rel.startswith('runtime/') or '..' in Path(rel).parts or '\\' in rel or ':' in rel or any(ord(c)<32 for c in rel):
        raise ValueError('Invalid app runtime')
    root=(home/rel).resolve()
    if (home/'runtime').resolve() not in root.parents:raise ValueError('Runtime escapes installation')
    return root/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def main():
    home=get_home();args=sys.argv[1:] or ['start']
    if os.name=='nt' and args[0]=='uninstall':
        native=home/'bin/uninstall_windows_entry.ps1'
        if native.is_file():
            shell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
            return subprocess.call([str(shell),'-NoLogo','-NoProfile','-ExecutionPolicy','Bypass',
                '-File',str(native),'--home',str(home),*args[1:]],cwd=os.environ.get('TEMP',str(Path.home())))
    source=active(home)
    env={**os.environ,'SDXL_STUDIO_HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1'}
    for key in ('PYTHONPATH','PYTHONHOME','SDXL_STUDIO_NO_BACKGROUND','SDXL_STUDIO_HOST_OVERRIDE','SDXL_STUDIO_INSTALLER_ACTIVE'):
        env.pop(key,None)
    if args[0]=='firewall-restore':
        cmd=[interpreter(home,source),source/'scripts/firewall_restore.py',*args[1:]]
    elif args[0]=='uninstall':
        management=home/'bin/management.json'
        support=release(home,json.loads(management.read_text())['release']) if management.exists() else source
        cmd=[interpreter(home,source),support/'scripts/uninstall.py',*args[1:]]
    elif args[0] in ('rollback','check','tests','diagnostics','version','verify'):
        controlfile=home/'bin/management.json'
        if controlfile.is_file():control=release(home,json.loads(controlfile.read_text())['release'])
        else:
            control=Path(__file__).resolve().parents[1]
            if not (control/'scripts/control.py').is_file():raise ValueError('Management module not installed')
        cmd=[sys.executable,control/'scripts/control.py',*args]
    else:
        cmd=[interpreter(home,source),source/'launcher.py',*args]
    creation={} if args[0]=='setup-code' else hidden_kwargs()
    return subprocess.call([str(x) for x in cmd],cwd=source,env=env, **creation)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print('[ERROR] Installazione SDXL non disponibile: '+str(exc),file=sys.stderr);raise SystemExit(2)
