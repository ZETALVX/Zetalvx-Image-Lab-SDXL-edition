"""Per-user icons. Source-1.0-rc1 guards packaged-only desktop integration."""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from core.desktop_ui import dialog, graphical
from core.install_layout import atomic_json
from core.platform_support import hidden_kwargs

NAMES=[('creator-studio-sdxl.desktop','Zetalvx Image Lab - SDXL Edition','start',False),
 ('creator-studio-sdxl-lan.desktop','Zetalvx Image Lab - SDXL Edition - LAN','start',True),
 ('creator-studio-sdxl-uninstall.desktop','Disinstalla Zetalvx Image Lab - SDXL Edition','uninstall',False)]

def exec_quote(value):
    value=str(value)
    if any(ord(c)<32 for c in value): raise ValueError('Invalid desktop path')
    value=value.replace('\\','\\\\\\\\').replace('"','\\\\"').replace('$','\\\\$').replace('`','\\\\`').replace('%','%%')
    return '"'+value+'"'

def belongs_to_home(text,home):
    return ('X-Zetalvx-Home='+str(Path(home).resolve())) in text.splitlines()

def desktop_entry(home: Path, source: Path, *, lan=False, action='start', python=None):
    title='Disinstalla Zetalvx Image Lab - SDXL Edition' if action=='uninstall' else 'Zetalvx Image Lab - SDXL Edition'+(' - LAN' if lan else '')
    args=[python or sys.executable,home/'bin/gui_launch.py','--home',home,action]
    if lan: args.append('--lan')
    icon=str(source/'static/zetalvx-app.png').replace('\\','\\\\')
    return '[Desktop Entry]\nType=Application\nName='+title+'\nComment=Local SDXL studio\nExec='+' '.join(exec_quote(x) for x in args)+'\nIcon='+icon+'\nTerminal=false\nCategories=Graphics;\nStartupNotify=false\nX-Zetalvx-Home='+str(home)+'\n'

def desktop_directory():
    if shutil.which('xdg-user-dir'):
        try:
            r=subprocess.run(['xdg-user-dir','DESKTOP'],capture_output=True,text=True,check=True,timeout=5)
            if r.stdout.strip(): return Path(r.stdout.strip())
        except (OSError,subprocess.SubprocessError): pass
    return Path.home()/'Desktop'

def desktop_choice(home, policy='keep'):
    f=home/'shared/config/desktop-preferences.json'
    try: saved=json.loads(f.read_text()).get('desktop')
    except (OSError,ValueError): saved=None
    if policy=='keep' and isinstance(saved,bool): return saved
    if policy=='yes': value=True
    elif policy=='no': value=False
    elif policy=='ask' and os.name!='nt' and not graphical():
        # A TTY is not a desktop. On headless Linux do not ask a meaningless GUI question.
        print('[INFO] No graphical desktop session detected; Desktop shortcut skipped.',flush=True)
        value=False
    elif policy=='ask' and (graphical() or (sys.stdin and sys.stdin.isatty())):
        print('Desktop shortcuts: awaiting host confirmation (Yes/No).',flush=True)
        value=dialog('Create one Desktop shortcut to start Zetalvx Image Lab using your saved Local/LAN setting?\n\nCreare una sola icona sul Desktop per avviare Zetalvx Image Lab con la modalità Locale/LAN salvata?\nDisinstalla resta nelle Impostazioni e nella cartella di installazione.',question=True)
    else: value=bool(saved)
    atomic_json(f,{'schema':1,'desktop':value});return value


def desktop_shortcut_status(home: Path):
    # Source-only guard: automatic desktop integration belongs to packaged builds.
    if (Path(__file__).resolve().parents[1]/'SOURCE_RELEASE.json').is_file():
        return {'enabled':False, 'preference':False, 'path':'', 'available':False,
                'reason':'Source checkout: launch with source.py; automatic desktop integration is not included.'}
    home=Path(home).resolve()
    pref=home/'shared/config/desktop-preferences.json'
    try: wanted=bool(json.loads(pref.read_text()).get('desktop'))
    except (OSError,ValueError): wanted=False
    if os.name!='nt':
        path=desktop_directory()/'creator-studio-sdxl.desktop'
        exists=path.is_file() and not path.is_symlink() and belongs_to_home(path.read_text(errors='replace'),home)
        return {'enabled':exists,'preference':wanted,'path':str(path)}
    script=r"""$D=[Environment]::GetFolderPath('DesktopDirectory');$P=Join-Path $D 'Zetalvx Image Lab - SDXL Edition.lnk';[pscustomobject]@{path=$P;exists=(Test-Path -LiteralPath $P)}|ConvertTo-Json -Compress"""
    try:
        r=subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],capture_output=True,text=True,check=True,timeout=15,**hidden_kwargs())
        d=json.loads(r.stdout.strip())
        return {'enabled':bool(d.get('exists')),'preference':wanted,'path':str(d.get('path') or '')}
    except Exception:
        return {'enabled':wanted,'preference':wanted,'path':''}

def set_desktop_shortcut(home: Path, source: Path, enabled: bool):
    return install_shortcuts(Path(home),Path(source),policy=('yes' if enabled else 'no'))

def install_shortcuts(home: Path, source: Path, policy='keep'):
    # Source-only packaging guard. No files/preferences/shortcuts are written.
    if (Path(source)/'SOURCE_RELEASE.json').is_file():
        raise RuntimeError('Source checkout: use source.py start. Automatic desktop integration is provided by the packaged installer.')
    home=Path(home).resolve();source=Path(source).resolve()
    desktop=desktop_choice(home,policy)
    if os.name!='nt':
        appdir=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications'
        destdesk=desktop_directory();result=[]
        # Only the normal Start icon belongs in menus and on Desktop.
        # Remove our old LAN/Uninstall shortcuts, never an unrelated user's shortcut.
        for directory, enabled in [(appdir,True),(destdesk,desktop)]:
            if enabled: directory.mkdir(parents=True,exist_ok=True)
            for filename,_,action,lan in NAMES:
                p=directory/filename
                ours=p.is_file() and not p.is_symlink() and belongs_to_home(p.read_text(errors='replace'),home)
                create=enabled and action=='start' and not lan
                if create:
                    if p.exists() and not ours:raise RuntimeError('Shortcut belongs to another installation: '+str(p))
                    p.write_text(desktop_entry(home,source),encoding='utf-8');p.chmod(0o755);result.append(p)
                elif ours:p.unlink()
        uninstall=home/'creator-studio-sdxl-uninstall.desktop'
        uninstall.write_text(desktop_entry(home,source,action='uninstall'),encoding='utf-8');uninstall.chmod(0o755)
        result.append(uninstall)
        if shutil.which('update-desktop-database'): subprocess.run(['update-desktop-database',str(appdir)],capture_output=True,check=False,**hidden_kwargs())
        atomic_json(home/'shared/config/desktop-shortcuts.json',{'files':[str(p) for p in result]})
        return result
    # COM handles localized/OneDrive known folders; arguments never interpolate into code.
    py=Path(sys.executable);pyw=py.with_name('pythonw.exe');py=pyw if pyw.exists() else py
    entries=[]
    for _,title,action,lan in NAMES:
        if lan:continue
        target=str(py)
        if action=='uninstall':
            target=str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')
            args=['-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',
                  str(home/'bin/uninstall_windows_entry.ps1'),'--home',str(home),'--gui']
        else:
            args=[str(home/'bin/gui_launch.py'),'--home',str(home),action]
        entries.append({'name':title,'action':action,'target':target,'arguments':subprocess.list2cmdline(args)})
    spec={'home':str(home),'python':str(py),'icon':str(source/'static/zetalvx-app.ico'),'desktop':desktop,'entries':entries}
    script=r'''
$ErrorActionPreference='Stop'
$Spec=Get-Content -LiteralPath $env:ZETALVX_SHORTCUT_SPEC -Raw -Encoding UTF8 | ConvertFrom-Json
$Wsh=New-Object -ComObject WScript.Shell
function Test-OwnedShortcut($Link,[string]$Root) {
 $Pattern='(?:^|\s)--home\s+(?:"'+[regex]::Escape($Root)+'"|'+[regex]::Escape($Root)+')(?:\s|$)'
 return $Link.Arguments -imatch $Pattern -or $Link.TargetPath.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase)
}
$Programs=[Environment]::GetFolderPath('Programs');$Desktop=[Environment]::GetFolderPath('DesktopDirectory')
$Menu=Join-Path $Programs 'Zetalvx Image Lab - SDXL Edition'
New-Item -ItemType Directory -Force -Path $Menu | Out-Null
# Remove only owned legacy shortcuts from Desktop and the menu.
foreach($Folder in @($Menu,(Join-Path $Programs 'Zetalvx Creator Studio'),(Join-Path $Programs 'Zetalvx SDXL'),$Desktop,$Spec.home)) {
 foreach($Name in @('Zetalvx Creator Studio','Zetalvx Creator Studio - LAN','Disinstalla Zetalvx Creator Studio','Zetalvx SDXL','Zetalvx SDXL - LAN','Zetalvx Image Lab - SDXL Edition - LAN','Disinstalla Zetalvx Image Lab - SDXL Edition')) {
  $P=Join-Path $Folder ($Name+'.lnk');if(Test-Path -LiteralPath $P){$L=$Wsh.CreateShortcut($P);if((Test-OwnedShortcut $L $Spec.home)){Remove-Item -LiteralPath $P}}
 }
}
foreach($E in $Spec.entries) {
 $Folders=if($E.action -eq 'uninstall'){@($Spec.home)}else{@($Menu,$Desktop)}
 foreach($Folder in $Folders) {
  if(-not $Folder){continue};$Path=Join-Path $Folder ($E.name+'.lnk')
  if((Test-Path -LiteralPath $Path)) {$Old=$Wsh.CreateShortcut($Path);if(-not ((Test-OwnedShortcut $Old $Spec.home))){throw 'Unrelated shortcut would be overwritten'}}
  if($Folder -eq $Desktop -and -not $Spec.desktop){if(Test-Path -LiteralPath $Path){Remove-Item -LiteralPath $Path};continue}
  $L=$Wsh.CreateShortcut($Path);$L.TargetPath=$E.target;$L.Arguments=$E.arguments
  $L.WorkingDirectory=$env:TEMP;$L.IconLocation=$Spec.icon+',0';$L.Description='Zetalvx Image Lab - SDXL Edition';$L.Save();Write-Output $Path
 }
}
'''
    with tempfile.TemporaryDirectory(prefix='zetalvx-shortcuts-') as temp:
        p=Path(temp)/'shortcuts.ps1';p.write_text(script,encoding='utf-8-sig')
        config=Path(temp)/'config.json';config.write_text(json.dumps(spec),encoding='utf-8')
        r=subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',str(p)],env={**os.environ,'ZETALVX_SHORTCUT_SPEC':str(config)},capture_output=True,text=True,check=True,timeout=45,**hidden_kwargs())
    return [Path(x) for x in r.stdout.splitlines() if x.strip()]
