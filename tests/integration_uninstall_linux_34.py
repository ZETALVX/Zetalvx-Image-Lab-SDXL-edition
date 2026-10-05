"""Disposable-home integration. No network/UI; real child runner and synthetic service."""
import json,os,sys,tempfile,time,subprocess,shutil
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from core.install_layout import atomic_json,set_pointers,write_runtime_map
from core.app_uninstall import UninstallService
BASE=Path(tempfile.mkdtemp(prefix='zetalvx34-e2e-'));reports=[]
for purge in (False,True):
 user=BASE/('purge' if purge else 'keep');user.mkdir();os.environ['HOME']=str(user);os.environ['XDG_DATA_HOME']=str(user/'.local/share')
 h=user/'.local/share/CreatorStudioSDXL';s=h/'versions/1.0.1';shutil.copytree(SOURCE,s,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
 atomic_json(h/'.zetalvx-install.json',{'schema':1,'product':'Zetalvx Creator Studio SDXL','id':'e2e-test','home':str(h)})
 set_pointers(h,'1.0.1',None)
 subprocess.run([sys.executable,'-m','venv','--without-pip','--system-site-packages',str(h/'runtime/app')],check=True)
 # Test-only package copy: --system-site-packages excludes the outer sandbox venv.
 import psutil
 site=next((h/'runtime/app/lib').glob('python*/site-packages'));shutil.copytree(Path(psutil.__file__).parent,site/'psutil')
 write_runtime_map(h,s,{'app':h/'runtime/app','sdxl':None},version='1.0.1')
 for rel in ['models/original.txt','shared/artifacts/image.txt','shared/training/datasets/d/image.txt','shared/config/creator_auth.json','secrets/personal.txt']:
  f=h/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('PERSONAL')
 external=user/'external';external.mkdir();(external/'keep.txt').write_text('EXTERNAL');(h/'models/linked').symlink_to(external,target_is_directory=True)
 # Validate the real lifecycle detection with a synthetic, idle owned web service.
 (s/'run.py').write_text('import time\ntime.sleep(90)\n')
 service=subprocess.Popen([str(h/'runtime/app/bin/python'),str(s/'run.py'),'web'],cwd=s,env={**os.environ,'SDXL_STUDIO_HOME':str(h)},stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
 time.sleep(.2)
 try:
  r=UninstallService(h,s).start(purge);report=Path(r['report']);until=time.monotonic()+25
  while not report.is_file() and time.monotonic()<until:time.sleep(.2)
  assert report.is_file(),r
  d=json.loads(report.read_text());assert d['ok'],d
  service.wait(timeout=5)
  assert not (h/'runtime').exists();assert not (h/'versions').exists();assert (external/'keep.txt').read_text()=='EXTERNAL'
  if purge:assert not h.exists()
  else:
   for rel in ['models/original.txt','shared/artifacts/image.txt','shared/training/datasets/d/image.txt','shared/config/creator_auth.json','secrets/personal.txt']:assert (h/rel).read_text()=='PERSONAL'
  reports.append({'mode':'purge' if purge else 'keep_data','passed':True,'real_detached_runner':True,'owned_synthetic_service_stopped':True,'external_data_preserved':True,'result':d})
 finally:
  if service.poll() is None:service.terminate();service.wait(timeout=5)
print(json.dumps({'environment':'Linux real files/processes under disposable per-user homes; no Flask HTTP and no production app','runs':reports},indent=2))
shutil.rmtree(BASE)
