import importlib.util,importlib,unittest,os,tempfile,sys
from pathlib import Path
HAS=importlib.util.find_spec('flask') is not None
@unittest.skipUnless(HAS,'Flask tests require the installed app runtime')
class VisionHTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='zetalvx-vision-http-')
  cls.old_env={k:os.environ.get(k) for k in ('SDXL_STUDIO_HOME','SDXL_STUDIO_NO_BACKGROUND')}
  os.environ['SDXL_STUDIO_HOME']=cls.tmp.name;os.environ['SDXL_STUDIO_NO_BACKGROUND']='1'
  # CPU-only test modules may have imported runtime constants before this suite.
  # Reload before app initialization; never initialize/write a production app home.
  if 'app' not in sys.modules:
   for name in ('core.runtime_env','core.paths','core.db'):
    if name in sys.modules:importlib.reload(sys.modules[name])
  elif not Path(sys.modules['app'].DATA_ROOT).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
   raise unittest.SkipTest('HTTP tests must run in an isolated process/data directory')
  import app
  # check.sh imports this suite without app loaded; discover may already have an isolated test app.
  active=Path(app.DATA_ROOT).resolve()
  if not active.is_relative_to(Path(tempfile.gettempdir()).resolve()):
   raise RuntimeError('Refusing to write test auth outside a temporary app home')
  from werkzeug.security import generate_password_hash
  cls.mod=app;app.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
  app.atomic_json(app.AUTH_CONFIG_PATH,{'enabled':True,'username':'C','password_hash':generate_password_hash('vision-test-password'),'session_hours':1})
 @classmethod
 def tearDownClass(cls):
  cls.tmp.cleanup()
  for key,value in cls.old_env.items():
   if value is None:os.environ.pop(key,None)
   else:os.environ[key]=value
 def setUp(self):
  self.c=self.mod.app.test_client();self.c.post('/login',data={'username':'C','password':'vision-test-password'});self.csrf=self.c.get('/api/vision/session').json['csrf']
 def test_csrf(self):self.assertEqual(self.c.post('/api/vision/models',json={'name':'bad'}).status_code,403)
 def test_crud(self):
  r=self.c.post('/api/vision/models',json={'name':'test','backend':'api','endpoint':'http://127.0.0.1:1/v1','api_model':'fake','token':'secret'},headers={'X-CSRF-Token':self.csrf});self.assertEqual(r.status_code,200);self.assertNotIn('secret',r.get_data(as_text=True));mid=r.json['model']['id'];self.assertEqual(self.c.delete('/api/vision/models/'+mid,json={},headers={'X-CSRF-Token':self.csrf}).status_code,200)
 def test_no_weights_download_endpoint(self):self.assertEqual(self.c.post('/api/setup/model-download/antelopev2',json={}).status_code,403)
 def test_path_report(self):
  r=self.c.post('/api/setup/identity-resolve',json={},headers={'X-CSRF-Token':self.csrf});self.assertEqual(r.status_code,200);self.assertIn('vendor_root',r.json['status']);self.assertIn('required_files',r.json['status'])
