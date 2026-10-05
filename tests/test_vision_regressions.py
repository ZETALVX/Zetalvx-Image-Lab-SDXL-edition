"""Saved-path, immutable test snapshot and persistent action regressions. No GPU."""
import base64,io,json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision.registry import Registry,VisionError
from vision.service import Service
from vision.jobs import Actions
from PIL import Image

class FakeEngine:
 def __init__(self):self.used=[];self.mid='';self.entered=threading.Event();self.release=threading.Event();self.block=False
 def caption(self,m,img,prompt,cancel=None):
  self.used.append(dict(m));self.entered.set()
  if self.block:self.release.wait(3)
  if cancel and cancel.is_set():raise VisionError('Cancelled')
  return 'A square.'
 def unload(self):pass
 def status(self):return {'busy':False}

class VisionRegressionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.r=Registry(self.home);self.e=FakeEngine();self.a=Actions(self.r,self.e)
  self.exe=self.home/'external-llama-server';self.exe.write_text('#!/bin/sh\nexit 0\n');self.exe.chmod(0o700)
  for n in ('model.gguf','mmproj.gguf'):(self.home/n).write_bytes(b'GGUFfixture')
  self.m=self.r.save({'name':'My Qwen','backend':'gguf','gguf_path':str(self.home/'model.gguf'),'mmproj_path':str(self.home/'mmproj.gguf'),'llama_path':str(self.exe),'terms_reviewed':True})
  b=io.BytesIO();Image.new('RGB',(8,8)).save(b,'PNG');self.image=base64.b64encode(b.getvalue()).decode()
 def tearDown(self):self.e.release.set();self.tmp.cleanup()
 def wait(self,j):
  end=time.time()+5
  while time.time()<end:
   a=next(x for x in self.a.list() if x['id']==j['id'])
   if a['status'] not in ('running','cancelling'):return a
   time.sleep(.02)
  self.fail('Job timed out')
 def test_check_and_test_use_same_explicit_executable(self):
  report=self.r.inspect(self.m);j=self.a.start('test',self.m['id'],self.image);out=self.wait(j)
  self.assertEqual(out['status'],'completed');self.assertEqual(out['execution'],report['execution']);self.assertEqual(self.e.used[-1]['llama_path'],str(self.exe));self.assertEqual(out['profile_fingerprint'],report['profile_fingerprint'])
 def test_edit_while_test_running_only_affects_next_test(self):
  self.e.block=True;j=self.a.start('test',self.m['id'],self.image);self.assertTrue(self.e.entered.wait(2));self.r.save({'llama_path':'/new/llama-server'},self.m['id']);self.e.release.set();out=self.wait(j);self.assertEqual(out['execution']['llama_path'],str(self.exe));self.assertEqual(self.e.used[-1]['llama_path'],str(self.exe))
 def test_snapshot_taken_before_background_fetch(self):
  with patch.object(self.r,'get',wraps=self.r.get) as get:
   j=self.a.start('test',self.m['id'],self.image);self.wait(j);self.assertEqual(get.call_count,1)
 def test_explicit_wrong_executable_is_not_replaced(self):
  bad={**self.m,'llama_path':'/not/exist/llama-server'}
  with patch('vision.registry.shutil.which',return_value=str(self.exe)):
   self.assertEqual(self.r.effective(bad)['llama_path'],'/not/exist/llama-server');self.assertFalse(self.r.inspect(bad)['ok'])
 def test_existing_legacy_path_alias_supported(self):
  d={**self.m};d.pop('llama_path');d['llama_server_path']=str(self.exe);self.assertEqual(self.r.effective(d)['llama_path'],str(self.exe))
 def test_saved_path_not_mutated_by_inspection(self):
  before=self.r.get(self.m['id']);self.r.inspect(before);self.assertEqual(before,self.r.get(self.m['id']))
 def test_partial_form_save_preserves_llama_path(self):
  self.r.save({'name':'New display name'},self.m['id']);self.assertEqual(self.r.get(self.m['id'])['llama_path'],str(self.exe))
 def test_action_history_persisted_not_mixed(self):
  one=self.wait(self.a.start('test',self.m['id'],self.image));self.e.caption=lambda *a,**k: (_ for _ in ()).throw(VisionError('test error'));two=self.wait(self.a.start('test',self.m['id'],self.image));other=Actions(self.r,FakeEngine());self.assertEqual([j['status'] for j in other.list()],['failed','completed']);self.assertNotEqual(one['id'],two['id'])
 def test_cancel_action_no_fake_success(self):
  self.e.block=True;j=self.a.start('test',self.m['id'],self.image);self.assertTrue(self.e.entered.wait(2));self.a.cancel(j['id']);self.e.release.set();out=self.wait(j);self.assertEqual(out['status'],'cancelled');self.assertNotIn('caption',out)
 def test_action_history_contains_no_api_token(self):
  m=self.r.save({'name':'API','backend':'api','endpoint':'http://127.0.0.1:8888/v1','api_model':'VL','token':'TEST_SUPER_SECRET','terms_reviewed':True});j=self.wait(self.a.start('test',m['id'],self.image));self.assertNotIn('TEST_SUPER_SECRET',json.dumps(j));self.assertNotIn('TEST_SUPER_SECRET',(self.a.root/(j['id']+'.json')).read_text())
 def test_restart_marks_old_running_interrupted(self):
  from vision.registry import atomic_json
  atomic_json(self.a.root/('a'*32+'.json'),{'id':'a'*32,'kind':'test','status':'running','created_at':0});new=Actions(self.r,self.e);self.assertEqual(new.list()[0]['status'],'interrupted')
 def test_config_fingerprint_ignores_save_time(self):
  a=self.r.fingerprint(self.m);self.assertEqual(a,self.r.fingerprint({**self.m,'updated_at':time.time()+100}))
 def test_config_fingerprint_changes_for_executable(self):self.assertNotEqual(self.r.fingerprint(self.m),self.r.fingerprint({**self.m,'llama_path':'/other/llama-server'}))

if __name__=='__main__':unittest.main(verbosity=2)
