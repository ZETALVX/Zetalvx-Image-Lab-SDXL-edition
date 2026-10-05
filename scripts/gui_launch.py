#!/usr/bin/env python3
"""Installed stable graphical entry; no dependency on the extracted ZIP folder."""
from __future__ import annotations
import argparse, importlib.util, json, os, shutil, subprocess, sys, tempfile, webbrowser
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('action',choices=['start','uninstall']);p.add_argument('--lan',action='store_true');a=p.parse_args()
    home=Path(a.home).expanduser().absolute()
    if os.name=='nt' and a.action=='uninstall' and (home/'bin/uninstall_windows_entry.ps1').is_file():
        shell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        return subprocess.call([str(shell),'-NoLogo','-NoProfile','-ExecutionPolicy','Bypass',
            '-File',str(home/'bin/uninstall_windows_entry.ps1'),'--home',str(home),'--gui'],
            cwd=tempfile.gettempdir(),creationflags=0x08000000)
    spec=importlib.util.spec_from_file_location('sdxl_manage',home/'bin/manage.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    source=m.active(home);py=m.interpreter(home,source)
    management=home/'bin/management.json'
    support=m.release(home,json.loads(management.read_text())['release']) if management.exists() else source
    sys.path.insert(0,str(support))
    from core.desktop_ui import dialog
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    env={**os.environ,'SDXL_STUDIO_HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
    for key in ('PYTHONPATH','PYTHONHOME','SDXL_STUDIO_INSTALLER_ACTIVE','SDXL_STUDIO_HOST_OVERRIDE'):env.pop(key,None)
    if a.action=='uninstall' and os.name!='nt' and not (shutil.which('zenity') or shutil.which('kdialog')):
        # Minimal desktops: show explicit text confirmations in an available terminal.
        args=[str(py),str(support/'scripts/uninstall.py'),'--home',str(home)]
        for term,extra in [('x-terminal-emulator',['-e']),('gnome-terminal',['--']),('konsole',['-e']),('xfce4-terminal',['-x']),('xterm',['-e']),('alacritty',['-e']),('kitty',[])]:
            if shutil.which(term):
                subprocess.Popen([term,*extra,*args],env=env,cwd=tempfile.gettempdir(),start_new_session=True);return 0
        dialog('No native dialog or terminal available. Run creator-sdxl uninstall from a terminal.');return 2
    if a.action=='uninstall':
        cmd=[str(py),str(support/'scripts/uninstall.py'),'--home',str(home),'--gui']
    else:
        cmd=[str(py),str(source/'launcher.py'),'start','--no-browser']+(['--lan'] if a.lan else [])
    result=subprocess.run(cmd,cwd=tempfile.gettempdir(),env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',**flags)
    if result.returncode:
        text=(result.stdout+'\n'+result.stderr).strip()
        log=home/'shared/logs/gui-launch-error.log';log.parent.mkdir(parents=True,exist_ok=True);log.write_text(text,encoding='utf-8')
        dialog('Avvio non riuscito / Operation failed.\n'+text[-3500:]+'\n\nLog: '+str(log));return result.returncode
    if a.action=='start':
        cfg=json.loads((home/'shared/config/settings.json').read_text())
        webbrowser.open(('https' if cfg.get('https',True) else 'http')+'://127.0.0.1:'+str(cfg.get('port',8298)))
        auth=home/'shared/config/creator_auth.json'
        if (a.lan or cfg.get('host')=='0.0.0.0') and (not auth.exists() or not json.loads(auth.read_text()).get('password_hash')):
            text=result.stdout
            # Already-running pending setup does not print a fresh code automatically.
            if 'Already running' in text:
                code=subprocess.run([str(py),str(source/'launcher.py'),'setup-code'],env=env,cwd=source,capture_output=True,text=True,**flags)
                text += '\n'+code.stdout
            dialog(text+'\n\nCodice del primo accesso LAN: non condividere questa finestra.\nFirst LAN setup: keep this code private.')
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as e:
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(e),'Zetalvx Image Lab - error',0x10)
        elif sys.stderr: print(e,file=sys.stderr)
        raise SystemExit(1)
