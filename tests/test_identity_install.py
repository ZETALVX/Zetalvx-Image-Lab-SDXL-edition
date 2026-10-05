"""Code installation regressions. Fake downloaded source; no network, no GPU."""
import ast,json,os,tempfile,threading,time,types,sys,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
from core.identity_code import CodeInstaller,CodeInstallError,CODE_FILES,verify_code,REVISION
from core.identity_paths import identity_files

def fake_code(relative):
 if relative=='LICENSE':return b'Apache License\nVersion 2.0'
 if relative.startswith('pipeline_'):
  cls='StableDiffusionXLInstantIDImg2ImgPipeline' if 'img2img' in relative else 'StableDiffusionXLInstantIDPipeline'
  return f'def draw_kps(*a): return None\nclass {cls}: pass\n'.encode()
 return b'# offline test code\nvalue = 1\n'

class InstallerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.shared=self.root/'sdxl/shared';self.config=self.shared/'config/settings.json';self.config.parent.mkdir(parents=True)
  self.weights=self.root/'CreatorStudio/models/Identity/InstantID';self.weights.mkdir(parents=True);(self.weights/'ip-adapter.bin').write_bytes(b'my existing weights');(self.weights/'ControlNetModel').mkdir()
  self.original={'identity_vendor':str(self.weights),'identity_root':str(self.weights.parent),'identity_instantid_root':str(self.weights),'identity_insightface_root':str(self.weights.parent/'insightface'),'identity_swapper_model':str(self.weights.parent/'inswapper_128.onnx'),'host':'127.0.0.1','custom_setting':'kept'}
  self.config.write_text(json.dumps(self.original));self.installer=CodeInstaller(self.shared,self.config)
 def tearDown(self):self.tmp.cleanup()
 def install(self):return self.installer.prepare(fake_code)
 def test_weights_path_is_never_installer_destination(self):
  before=set(self.weights.rglob('*'));out=self.install();cfg=json.loads(self.config.read_text());self.assertEqual(set(self.weights.rglob('*')),before);self.assertEqual((self.weights/'ip-adapter.bin').read_bytes(),b'my existing weights');self.assertNotEqual(cfg['identity_vendor'],str(self.weights));self.assertEqual(cfg['identity_vendor'],out['target'])
 def test_only_code_path_changes(self):
  self.install();cfg=json.loads(self.config.read_text());self.assertEqual({k:v for k,v in cfg.items() if k!='identity_vendor'},{k:v for k,v in self.original.items() if k!='identity_vendor'})
 def test_gui_and_worker_file_contract_ready_after_install(self):
  self.install();s=identity_files(json.loads(self.config.read_text()),self.root/'sdxl/models',self.shared);self.assertTrue(s['vendor_ready']);self.assertFalse(s['vendor_points_to_weights'])
 def test_failed_download_does_not_rewrite_settings(self):
  before=self.config.read_bytes()
  def fail(relative):raise OSError('simulated unavailable network')
  with self.assertRaises(CodeInstallError):self.installer.prepare(fail)
  self.assertEqual(before,self.config.read_bytes());self.assertEqual(self.installer.status()['status'],'failed');self.assertFalse(self.installer.target.exists())
 def test_bad_python_is_not_published(self):
  with self.assertRaises(CodeInstallError):self.installer.prepare(lambda rel:b'bad syntax !' if rel.endswith('.py') else fake_code(rel))
  self.assertEqual(json.loads(self.config.read_text()),self.original)
 def test_missing_pipeline_class_not_accepted(self):
  with self.assertRaises(CodeInstallError):self.installer.prepare(lambda rel:b'x=1' if rel.startswith('pipeline_') else fake_code(rel))
 def test_html_not_valid_code(self):
  with self.assertRaises(CodeInstallError):self.installer.prepare(lambda rel:b'<html>error</html>')
 def test_second_install_reuses_complete_code(self):
  self.install()
  def forbidden(_):raise AssertionError('Second install must not fetch')
  out=self.installer.prepare(forbidden);self.assertEqual(out['status'],'completed')
 def test_existing_incomplete_owned_tree_preserved(self):
  t=self.installer.target;t.mkdir(parents=True);(t/'custom.py').write_text('# do not delete')
  out=self.install();self.assertNotEqual(out['target'],str(t));self.assertEqual((t/'custom.py').read_text(),'# do not delete')
 def test_custom_valid_code_preserved(self):
  custom=self.root/'my-code';custom.mkdir()
  for rel in CODE_FILES:p=custom/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(fake_code(rel))
  cfg={**self.original,'identity_vendor':str(custom)};self.config.write_text(json.dumps(cfg));out=self.install();self.assertEqual(out['target'],str(custom));self.assertFalse(self.installer.target.exists())
 def test_config_backup_exists(self):
  self.install();backups=list(self.config.parent.glob('settings.before-instantid-*.json'));self.assertEqual(len(backups),1);self.assertEqual(json.loads(backups[0].read_text()),self.original)
 def test_concurrent_model_edit_is_kept(self):
  def fetch(rel):
   if rel==CODE_FILES[-1]:
    self.config.write_text(json.dumps({**self.original,'identity_vendor':'/different/user/choice'}))
   return fake_code(rel)
  with self.assertRaisesRegex(CodeInstallError,'edited during'):
   self.installer.prepare(fetch)
  self.assertEqual(json.loads(self.config.read_text())['identity_vendor'],'/different/user/choice')
 def test_other_settings_changed_during_fetch_are_preserved(self):
  def fetch(rel):
   if rel==CODE_FILES[-1]:self.config.write_text(json.dumps({**self.original,'host':'0.0.0.0','custom_setting':'new'}))
   return fake_code(rel)
  self.installer.prepare(fetch);cfg=json.loads(self.config.read_text());self.assertEqual(cfg['host'],'0.0.0.0');self.assertEqual(cfg['custom_setting'],'new')
 def test_status_survives_new_manager(self):
  self.install();another=CodeInstaller(self.shared,self.config);self.assertEqual(another.status()['status'],'completed')
 def test_stale_install_marked_interrupted(self):
  self.installer._state(status='running');self.assertEqual(self.installer.status()['status'],'interrupted')
 def test_two_installers_do_not_write_concurrently(self):
  entered=threading.Event();release=threading.Event();errors=[]
  def fetch(rel):entered.set();release.wait(3);return fake_code(rel)
  def install():
   try:self.installer.prepare(fetch)
   except Exception as e:errors.append(str(e))
  thread=threading.Thread(target=install);thread.start();self.assertTrue(entered.wait(2))
  another=CodeInstaller(self.shared,self.config)
  try:
   self.assertEqual(another.status()['status'],'running')
   with self.assertRaisesRegex(CodeInstallError,'already running'):another.prepare(fake_code)
  finally:release.set();thread.join(4)
  self.assertFalse(errors)
 def test_managed_directory_symlink_cannot_write_in_weights(self):
  self.installer.folder.parent.mkdir(parents=True,exist_ok=True);self.installer.folder.symlink_to(self.weights,target_is_directory=True)
  before=set(self.weights.rglob('*'))
  with self.assertRaisesRegex(CodeInstallError,'outside app shared data'):self.install()
  self.assertEqual(set(self.weights.rglob('*')),before);self.assertEqual(json.loads(self.config.read_text()),self.original)
 def test_pinned_source_and_allowlist_exclude_weights(self):
  self.assertEqual(len(REVISION),40);self.assertTrue(all(x.endswith('.py') or x=='LICENSE' for x in CODE_FILES))

class ScopedCsrfTests(unittest.TestCase):
 """Exercises the pure derivation against concurrent signed-session snapshots."""
 def load(self,session):
  import importlib.util
  name='csrf_test_only';p=Path(__file__).resolve().parents[1]/'core/csrf.py';spec=importlib.util.spec_from_file_location(name,p);module=importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules,{'flask':types.SimpleNamespace(session=session,current_app=types.SimpleNamespace(secret_key='test-secret'))}):spec.loader.exec_module(module)
  return module
 def test_parallel_endpoints_do_not_mutate_session(self):
  session={'creator_username':'C','auth_stamp':'a','creator_csrf_nonce':'nonce'};before=dict(session);c=self.load(session);self.assertEqual(c.token('vision'),c.token('vision'));self.assertNotEqual(c.token('vision'),c.token('model-hub'));self.assertEqual(session,before)
 def test_legacy_session_tokens_stable_on_refresh(self):
  session={'creator_username':'C','auth_stamp':'a'};a=self.load(dict(session));b=self.load(dict(session));self.assertEqual(a.token('vision'),b.token('vision'))
 def test_session_rotation_invalidates_token(self):
  a=self.load({'auth_stamp':'a','creator_csrf_nonce':'1'});b=self.load({'auth_stamp':'a','creator_csrf_nonce':'2'});self.assertFalse(b.valid('vision',a.token('vision')))
 def test_scope_cannot_be_reused(self):
  c=self.load({'auth_stamp':'a'});self.assertFalse(c.valid('vision',c.token('model-hub')));self.assertFalse(c.valid('vision',''))

if __name__=='__main__':unittest.main(verbosity=2)
