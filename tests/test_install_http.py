"""Real Flask request tests, skipped when Flask is absent. No network/code download."""
import importlib.util, importlib, os, sys, tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
HAS=importlib.util.find_spec('flask') is not None

@unittest.skipUnless(HAS,'Flask is required: run in installed runtime/app')
class InstallHTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='zetalvx-code-http-')
  cls.old={k:os.environ.get(k) for k in ('SDXL_STUDIO_HOME','SDXL_STUDIO_NO_BACKGROUND')}
  os.environ.update(SDXL_STUDIO_HOME=cls.tmp.name,SDXL_STUDIO_NO_BACKGROUND='1')
  if 'app' not in sys.modules:
   for mod in ('core.runtime_env','core.paths','core.db','core.identity_code'):
    if mod in sys.modules:importlib.reload(sys.modules[mod])
  import app
  if not Path(app.DATA_ROOT).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
   raise unittest.SkipTest('Requires temporary app home; refusing to write production settings')
  cls.mod=app
  from werkzeug.security import generate_password_hash
  app.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
  app.atomic_json(app.AUTH_CONFIG_PATH,{'enabled':True,'username':'C','password_hash':generate_password_hash('code-test-password'),'session_hours':1})
  cls.health_patches=[patch.object(app,x,return_value=y) for x,y in [('image_worker_health',{'ok':False}),('identity_worker_health',{'online':False}),('training_worker_health',{'ok':False})]]
  for p in cls.health_patches:p.start()
 @classmethod
 def tearDownClass(cls):
  for p in cls.health_patches:p.stop()
  cls.tmp.cleanup()
  for k,v in cls.old.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
 def setUp(self):
  self.c=self.mod.app.test_client();self.c.post('/login',data={'username':'C','password':'code-test-password'})
 def tokens(self):return self.c.get('/api/session/tokens').json['tokens']
 def test_install_requires_token(self):
  with patch.object(self.mod._identity_code_installer,'start') as start:
   r=self.c.post('/api/setup/identity-prepare-code',json={});self.assertEqual(r.status_code,403);self.assertEqual(r.json['code'],'csrf_failed');start.assert_not_called()
 def test_install_returns_action_not_fake_success(self):
  with patch.object(self.mod._identity_code_installer,'start',return_value={'status':'running','target':'/fake/code'}) as start:
   r=self.c.post('/api/setup/identity-prepare-code',json={},headers={'X-CSRF-Token':self.tokens()['vision']})
   self.assertEqual(r.status_code,202);self.assertEqual(r.json['installation']['status'],'running');start.assert_called_once()
 def test_status_returns_exact_failure(self):
  with patch.object(self.mod._identity_code_installer,'status',return_value={'status':'failed','error':'network test error'}):
   r=self.c.get('/api/setup/identity-code-status');self.assertEqual(r.status_code,200);self.assertEqual(r.json['installation']['error'],'network test error')
 def test_parallel_read_scopes_remain_valid(self):
  first=self.tokens();vision=self.c.get('/api/vision/session').json['csrf'];hub=self.c.get('/api/model-hub/status').json['csrf'];last=self.tokens()
  self.assertEqual(first,last);self.assertEqual(vision,last['vision']);self.assertEqual(hub,last['model-hub'])
  with patch.object(self.mod._identity_code_installer,'start',return_value={'status':'running'}):
   self.assertEqual(self.c.post('/api/setup/identity-prepare-code',json={},headers={'X-CSRF-Token':vision}).status_code,202)
 def test_session_get_does_not_add_csrf_fields(self):
  with self.c.session_transaction() as s:before=dict(s)
  self.tokens();self.c.get('/api/vision/session');self.c.get('/api/model-hub/status')
  with self.c.session_transaction() as s:after=dict(s)
  self.assertEqual(before,after)
 def test_cross_scope_rejected(self):
  r=self.c.post('/api/setup/identity-prepare-code',json={},headers={'X-CSRF-Token':self.tokens()['model-hub']});self.assertEqual(r.status_code,403)
 def test_setup_write_uses_same_csrf_scope(self):
  r=self.c.put('/api/setup',json={'identity_instantid_enabled':True},headers={'X-CSRF-Token':self.tokens()['vision']});self.assertEqual(r.status_code,200)
 def test_weights_remain_blocked(self):
  for c in ['instantid','antelopev2','buffalo_l','inswapper']:
   self.assertEqual(self.c.post('/api/setup/model-download/'+c,json={},headers={'X-CSRF-Token':self.tokens()['vision']}).status_code,403)

if __name__=='__main__':unittest.main(verbosity=2)
