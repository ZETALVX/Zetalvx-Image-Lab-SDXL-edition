"""Guarded per-user removal. Personal data preserved by default; links never followed."""
from __future__ import annotations
import json, os, shutil, stat, re
from pathlib import Path
APP_ONLY=('current','previous','install-state.json','versions','runtime','bin','shared/updates','shared/run',
          'creator-studio-sdxl-uninstall.desktop','Disinstalla Zetalvx Creator Studio.lnk','Disinstalla Zetalvx Image Lab - SDXL Edition.lnk','UNINSTALL.cmd','uninstall.sh',
          'install.lock','uninstall-pending.json')

def linked(p):
    try:return Path(p).is_symlink() or bool(Path(p).lstat().st_file_attributes & 0x400)
    except AttributeError:return Path(p).is_symlink()
    except FileNotFoundError:return False

def validate_home(path):
    raw=Path(path).expanduser().absolute()
    if any(linked(p) for p in (raw,*raw.parents)):raise ValueError('Refusing a linked installation root or ancestor')
    h=raw.resolve()
    if h==Path.home().resolve() or h==Path(h.anchor) or len(h.parts)<3:raise ValueError('Unsafe removal root')
    marker=h/'.zetalvx-install.json'
    if linked(marker):raise ValueError('Linked installation marker')
    d=json.loads(marker.read_text(encoding='utf-8'))
    if d.get('product')!='Zetalvx Creator Studio SDXL' or d.get('schema')!=1 or not d.get('id') or Path(d.get('home','')).resolve()!=h:
        raise ValueError('Installation identity mismatch; nothing removed')
    return h,d

def mounted_paths():
    # stat/ismount alone misses same-device bind mounts. mountinfo is authoritative on Linux.
    if os.name=='nt':return set()
    try:
        data=Path('/proc/self/mountinfo').read_text(encoding='utf-8')
    except FileNotFoundError:return set()
    found=set()
    for line in data.splitlines():
        fields=line.split()
        if len(fields)>4:
            name=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),fields[4])
            found.add(Path(name).absolute())
    return found

def reject_mounts(root):
    """Don't recurse into mounted external storage, including same-device Linux bind mounts."""
    root=Path(root).absolute();mounts=mounted_paths()
    if any(p==root or root in p.parents for p in mounts):
        raise ValueError('Mounted storage is preserved; unmount it before removal: '+str(root))
    for directory,dirs,_ in os.walk(root,followlinks=False):
        for name in dirs[:]:
            p=Path(directory)/name
            if linked(p):dirs.remove(name);continue
            if os.path.ismount(p):raise ValueError('Mounted folder preserved; unmount it before full removal: '+str(p))

def make_plan(home,purge=False):
    h,d=validate_home(home)
    if type(purge) is not bool:raise ValueError('Invalid removal mode')
    if purge:reject_mounts(h)
    return {'home':str(h),'installation_id':d['id'],'purge_data':purge,'remove':[str(h)] if purge else [str(h/n) for n in APP_ONLY],
      'data_preserved':not purge,'external_model_links_followed':False}

def remove_tree(p):
    p=Path(p)
    if linked(p):p.unlink()
    elif p.is_dir():
        if os.path.ismount(p):raise ValueError('Refusing to remove a mounted directory: '+str(p))
        reject_mounts(p);shutil.rmtree(p)
    elif p.exists():p.unlink()

def remove_linux_shortcuts(home):
    from core.desktop_shortcuts import NAMES, desktop_directory, belongs_to_home
    dirs=[Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications',desktop_directory()]
    for d in dirs:
        for name,*_ in NAMES:
            p=d/name
            if p.is_file() and not linked(p) and belongs_to_home(p.read_text(errors='replace'),home):p.unlink()
    cli=Path.home()/'.local/bin/creator-sdxl'
    if cli.is_file() and not linked(cli):
        import shlex
        text=cli.read_text(errors='replace')
        expected=shlex.quote(str(home/'bin/creator-sdxl'))
        if ('exec '+expected+' "$@"') in text:cli.unlink()
    if shutil.which('update-desktop-database'):
        import subprocess
        subprocess.run(['update-desktop-database',str(dirs[0])],capture_output=True,check=False)

def execute_linux(plan):
    h,d=validate_home(plan['home'])
    if d['id']!=plan['installation_id']:raise ValueError('Installation changed during confirmation')
    if type(plan.get('purge_data')) is not bool:raise ValueError('Invalid removal mode')
    if plan['purge_data']:reject_mounts(h)
    remove_linux_shortcuts(h)
    # Never accept a file list from the browser or serialized job as a delete instruction.
    if plan['purge_data']:remove_tree(h)
    else:
        for n in APP_ONLY:
            path=h/n
            # An external shared directory is not followed even for shared/run or updates.
            parents=[];parent=path.parent
            while parent!=h:parents.append(parent);parent=parent.parent
            if any(linked(p) for p in parents):continue
            remove_tree(path)
