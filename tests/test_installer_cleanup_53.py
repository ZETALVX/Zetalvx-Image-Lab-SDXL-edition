"""1.0.1 regressions: ONNX security pin and failed staging runtime garbage collection."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer53',ROOT/'scripts/install.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
spec2=importlib.util.spec_from_file_location('audit53',ROOT/'scripts/audit_runtime.py');auditmod=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(auditmod)
from core.install_layout import write_runtime_map

class InstallerCleanup53(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.home=Path(self.t.name)/'CreatorStudioSDXL'
  (self.home/'versions').mkdir(parents=True);(self.home/'runtime/sets').mkdir(parents=True);(self.home/'shared/audits').mkdir(parents=True)
 def release(self,name,runtimes):
  r=self.home/'versions'/name;r.mkdir();write_runtime_map(self.home,r,runtimes,version=name);return r
 def failed_result(self,stage):
  d=self.home/'shared/audits'/('install-'+stage.name);d.mkdir();(d/'result.json').write_text(json.dumps({'ok':False,'staged_release_kept':str(stage)}))
 def test_identity_pin_moves_off_advisory_affected_onnx(self):
  self.assertEqual(installer.direct_pins(ROOT/'requirements-identity.txt')['onnx'],'1.22.0')
 def test_removes_only_failed_unreferenced_runtime_sets(self):
  cur_app=self.home/'runtime/sets/current/app';cur_app.mkdir(parents=True);(cur_app/'keep').write_bytes(b'x')
  cur=self.release('0.1.0.50',{'app':cur_app,'sdxl':None})
  bad_app=self.home/'runtime/sets/failed/app';bad_sdxl=self.home/'runtime/sets/failed/sdxl';bad_app.mkdir(parents=True);bad_sdxl.mkdir(parents=True)
  (bad_sdxl/'large').write_bytes(b'x'*4096);stage=self.release('0.1.0.52-failed',{'app':bad_app,'sdxl':bad_sdxl});self.failed_result(stage)
  report=self.home/'report.json';out=installer.cleanup_failed_staging(self.home,{'current':cur.name,'previous':None},None,report)
  self.assertTrue(cur_app.exists());self.assertFalse(bad_app.exists());self.assertFalse(bad_sdxl.exists());self.assertTrue(stage.exists())
  self.assertGreaterEqual(out['freed_bytes'],4096);self.assertFalse(out['models_touched']);self.assertTrue(report.is_file())
 def test_preserves_selected_resume_stage(self):
  p=self.home/'runtime/sets/resume/sdxl';p.mkdir(parents=True);stage=self.release('0.1.0.52-resume',{'app':self.home/'runtime/sets/resume/app','sdxl':p});(self.home/'runtime/sets/resume/app').mkdir()
  self.failed_result(stage);installer.cleanup_failed_staging(self.home,{'current':None,'previous':None},stage,None);self.assertTrue(p.exists())
 def test_refuses_runtime_map_that_escapes_sets(self):
  outside=self.home/'outside';outside.mkdir();(outside/'sentinel').write_text('safe')
  stage=self.home/'versions/0.1.0.52-escape';stage.mkdir();(stage/'.installed-runtime.json').write_text(json.dumps({'schema':1,'runtimes':{'app':'runtime/sets/escape/app','sdxl':None}}))
  link=self.home/'runtime/sets/escape';link.symlink_to(outside,target_is_directory=True);self.failed_result(stage)
  installer.cleanup_failed_staging(self.home,{'current':None,'previous':None},None,None);self.assertEqual((outside/'sentinel').read_text(),'safe')
 def test_advisory_audit_still_blocks_real_advisory(self):
  inv={'state':'INVENTORIED','python':'3.11.16','packages':[{'name':'onnx','version':'1.20.1','license_expression':'','license_metadata':'','license_classifiers':[]}]}
  with patch.object(auditmod,'inventory',return_value=inv):
   report=auditmod.audit({'selected':'python'},online=True,fetcher=lambda p:{'state':'ADVISORIES_FOUND','advisories':[{'id':'TEST'}]})
  self.assertEqual(report['result'],'BLOCKED');self.assertEqual(report['issues'][0]['package'],'onnx')

if __name__=='__main__':unittest.main()
