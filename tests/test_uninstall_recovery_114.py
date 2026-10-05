"""1.0.14 uninstall recovery regression. No production data is removed."""
import contextlib, json, subprocess, sys, tempfile, time, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.install_layout import atomic_json,set_pointers
from core.app_uninstall import UninstallService,UninstallError
from core.platform_support import process_start
from unittest.mock import Mock,patch

class UninstallRecovery114(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.home=Path(self.tmp.name)/'CreatorStudioSDXL';self.source=self.home/'versions/1.0.14';self.source.mkdir(parents=True)
  atomic_json(self.home/'.zetalvx-install.json',{'schema':1,'product':'Zetalvx Creator Studio SDXL','id':'install-114','home':str(self.home.resolve())})
  set_pointers(self.home,'1.0.14',None)
  self.service=UninstallService(self.home,self.source)
 def pending(self,**kw):
  d={'id':'a'*32,'installation_id':'install-114','status':'starting','created_at':time.time()-120};d.update(kw)
  atomic_json(self.home/'uninstall-pending.json',d)
  folder=self.home/'shared/uninstall'/('a'*32);folder.mkdir(parents=True,exist_ok=True)
  atomic_json(folder/'job.json',{'id':'a'*32,'home':str(self.home.resolve()),'source':str(self.source.resolve()),'created_at':time.time()-120,'status':'starting','report_dir':str(Path(self.tmp.name)/'report')})
 def test_orphaned_runner_marker_is_recovered(self):
  self.pending(pid=99999999,process_start='gone')
  plan=self.service.plan(False)
  self.assertFalse((self.home/'uninstall-pending.json').exists());self.assertFalse(plan['purge_data'])
  job=json.loads((self.home/'shared/uninstall'/('a'*32)/'job.json').read_text());self.assertEqual(job['status'],'interrupted')
 def test_live_runner_marker_still_blocks(self):
  proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])
  self.addCleanup(lambda: proc.poll() is None and proc.kill())
  start=None
  for _ in range(20):
   start=process_start(proc.pid)
   if start:break
   time.sleep(.02)
  self.assertTrue(start);self.pending(pid=proc.pid,process_start=start)
  with self.assertRaisesRegex(UninstallError,'already in progress'):self.service.plan(False)
  self.assertTrue((self.home/'uninstall-pending.json').exists())

 def test_windows_starts_native_worker_without_python_runner(self):
  fake=Mock();fake.pid=4242;fake.poll.return_value=None
  with patch('core.app_uninstall.windows_host',return_value=True),\
       patch('core.app_uninstall.lifecycle_locks',return_value=contextlib.nullcontext()),\
       patch('core.app_uninstall.check_idle_and_update'),\
       patch('core.app_uninstall.runtime_dirs',return_value={'app':self.home/'runtime/app','sdxl':None}),\
       patch('core.windows_uninstall.launch',return_value=(fake,'win-filetime-test')) as native:
   r=self.service.start(False)
  native.assert_called_once()
  state=json.loads((self.home/'uninstall-pending.json').read_text())
  self.assertEqual(state['cleanup_pid'],4242);self.assertEqual(state['cleanup_start'],'win-filetime-test')
  self.assertEqual(state['engine'],'native-powershell-v1');self.assertTrue(r['native_windows'])
 def test_recent_untracked_start_is_not_recovered(self):
  self.pending();d=json.loads((self.home/'uninstall-pending.json').read_text());d['created_at']=time.time();atomic_json(self.home/'uninstall-pending.json',d)
  with self.assertRaisesRegex(UninstallError,'already in progress'):self.service.plan(False)

if __name__=='__main__':unittest.main()
