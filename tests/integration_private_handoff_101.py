#!/usr/bin/env python3
"""Linux process/venv handoff regression, NOT an AI installation acceptance test.

Uses the actual previous GUI supervisor and the candidate's actual context/relay
functions. Copies the host CPython + stdlib into a temporary private root, creates
real venvs, and uses a fixture for activation (no pip, GPU, network, or user data).
The host Python version is recorded; the pinned 3.11.16 install gate is NOT tested.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
STUB=r'''
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import fixture_transaction as incoming
from core.install_layout import pointers,release_path,set_pointers
home=Path(sys.argv[sys.argv.index('--home')+1])
ctx=incoming.private_installer_context(home,release_path(home,pointers(home)['current']))
with (home/'handoff-events.jsonl').open('a') as f:
 f.write(json.dumps({'context':ctx,'argv':sys.argv,'real_python':sys.version})+'\n')
if ctx['kind']=='app-updater':
 raise SystemExit(incoming.relaunch_private_installer(home,ctx))
if (home/'fixture-failure').exists():
 raise SystemExit(2)
old=pointers(home)['current'];(home/'versions/1.0.1').mkdir()
set_pointers(home,'1.0.1',old)
print('FIXTURE activation only: no runtime install or GPU validation',flush=True)
'''
DRIVER=r'''
import json,sys,time
from pathlib import Path
old=Path(sys.argv[1]);home=Path(sys.argv[2]);package=Path(sys.argv[3])
sys.path.insert(0,str(old))
from core.app_updates import UpdateStore,FINAL_STATES
store=UpdateStore(home,old,old.name)
with package.open('rb') as stream: state=store.import_zip(stream,package.name)
store.start(state['id'])
until=time.monotonic()+30
while time.monotonic()<until:
 state=store.read(state['id'])
 if state['status'] in FINAL_STATES: break
 time.sleep(.05)
(home/'observed-update.json').write_text(json.dumps(state,indent=2))
print(json.dumps(state))
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--old-053',type=Path,required=True)
    p.add_argument('--old-100',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    if sys.platform!='linux': raise SystemExit('This optional harness requires Linux; native Windows remains separate.')
    results=[]
    with tempfile.TemporaryDirectory(prefix='zetalvx relay real ') as tmp:
        parent=Path(tmp)
        for label,version,old_input,mapped,fail in [
            ('053-historical-app','0.1.0.53',args.old_053,False,False),
            ('053-mapped-app','0.1.0.53',args.old_053,True,False),
            ('100-historical-app','1.0.0',args.old_100,False,False),
            ('053-child-failure','0.1.0.53',args.old_053,False,True)]:
            home=parent/label/'CreatorStudioSDXL'; base=home/'runtime/python/host-test-python'
            (base/'bin').mkdir(parents=True)
            stdlib=Path(sysconfig.get_path('stdlib'))
            shutil.copytree(stdlib,base/'lib'/stdlib.name,ignore=shutil.ignore_patterns('site-packages','dist-packages','__pycache__','test','tests'))
            private=base/'bin/python3.11'
            shutil.copy2(Path(sys._base_executable).resolve(),private); private.chmod(0o755)
            app=home/('runtime/sets/old-selected/app' if mapped else 'runtime/app')
            subprocess.run([str(private),'-I','-m','venv','--without-pip',str(app)],check=True,capture_output=True)
            old=home/'versions'/version
            shutil.copytree(old_input,old,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            (home/'current').symlink_to(old)
            (old/'.installed-runtime.json').write_text(json.dumps({'schema':1,'backend':'cu126','runtimes':{'app':app.relative_to(home).as_posix(),'sdxl':None}}))
            if fail:(home/'fixture-failure').touch()
            payload=parent/label/'payload';shutil.copytree(ROOT,payload,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            (payload/'scripts/install.py').rename(payload/'scripts/fixture_transaction.py')
            (payload/'scripts/install.py').write_text(STUB)
            files=sorted(f for f in payload.rglob('*') if f.is_file() and f.name!='MANIFEST.sha256')
            (payload/'MANIFEST.sha256').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.relative_to(payload).as_posix()+'\n' for f in files))
            archive=parent/label/'fixture.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for f in payload.rglob('*'):
                    if f.is_file():z.write(f,'zetalvx_creator_studio_sdxl_v1_0_1_linux/'+f.relative_to(payload).as_posix())
            driver=parent/label/'driver.py';driver.write_text(DRIVER)
            env=dict(os.environ,SDXL_STUDIO_HOME=str(home),PYTHONDONTWRITEBYTECODE='1')
            for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):env.pop(key,None)
            proc=subprocess.run([str(app/'bin/python'),'-I',str(driver),str(old),str(home),str(archive)],
                                capture_output=True,text=True,env=env,timeout=40)
            state=json.loads((home/'observed-update.json').read_text()) if (home/'observed-update.json').exists() else {}
            events=[json.loads(line) for line in (home/'handoff-events.jsonl').read_text().splitlines()] if (home/'handoff-events.jsonl').exists() else []
            logfiles=list((home/'shared/updates').glob('*/runner.log'))
            log=logfiles[0].read_text() if logfiles else ''
            expected='failed' if fail else 'completed'
            current=(home/'current').resolve().name
            passed=(proc.returncode==0 and state.get('status')==expected and current==(version if fail else '1.0.1')
                    and [e['context']['kind'] for e in events]==['app-updater','bootstrap']
                    and all('--runtime' in e['argv'] and 'keep' in e['argv'] and '--online' in e['argv'] and '--no-browser' in e['argv'] for e in events))
            results.append({'case':label,'passed':passed,'driver_exit':proc.returncode,'update_status':state.get('status'),
                'installer_exit':state.get('exit_code'),'active_release':current,'events':events,'runner_log':log,
                'driver_stderr':proc.stderr,'fixture_activation':True})
            print(label, 'PASS' if passed else 'FAIL',flush=True)
        report={'host_python':sys.version,'cases':results,'all_passed':all(r['passed'] for r in results),
            'limitations':['Activation is a fixture; full transaction covered separately with simulated pip/GPU/services.',
                           'Private base is a copy of host CPython, not the shipped pinned CPython 3.11.16.',
                           'No browser, GPU, native Windows, download or external network is exercised.']}
        args.report.write_text(json.dumps(report,indent=2)+'\n')
        return 0 if report['all_passed'] else 2
if __name__=='__main__':raise SystemExit(main())
