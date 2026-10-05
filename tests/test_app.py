"""Run with the installed app runtime to test real Flask login/JSON routes."""
import importlib.util, os, sys, tempfile, unittest, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
HAS_FLASK=importlib.util.find_spec('flask') is not None

@unittest.skipUnless(HAS_FLASK,'Flask not installed here: HTTP/login tests require runtime/app')
class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='creator-sdxl-http-test-')
        os.environ['SDXL_STUDIO_HOME']=cls.tmp.name;os.environ['SDXL_STUDIO_NO_BACKGROUND']='1'
        import app
        from werkzeug.security import generate_password_hash
        cls.mod=app;app.app.config['TESTING']=True
        app.app.config['SESSION_COOKIE_SECURE']=False  # test client uses HTTP only
        app.atomic_json(app.AUTH_CONFIG_PATH,{'enabled':True,'username':'C','password_hash':generate_password_hash('test-password-123'),'session_hours':1})
        app.image_worker_health=lambda:{'ok':False}
        app.training_worker_health=lambda:{'ok':False}
        app.identity_worker_health=lambda:{'online':False}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):self.client=self.mod.app.test_client()
    def signin(self):return self.client.post('/login',data={'username':'C','password':'test-password-123'})
    def test_public_health(self):self.assertEqual(self.client.get('/api/health').json['edition'],'sdxl')
    def test_private_api_locked(self):self.assertEqual(self.client.get('/api/bootstrap').status_code,401)
    def test_correct_login(self):self.assertEqual(self.signin().status_code,302);self.assertEqual(self.client.get('/api/bootstrap').status_code,200)
    def test_bad_login(self):self.client.post('/login',data={'username':'C','password':'wrong'});self.assertEqual(self.client.get('/api/bootstrap').status_code,401)
    def test_no_open_redirect(self):self.assertEqual(self.client.post('/login',data={'username':'C','password':'test-password-123','next':'//evil.example'}).headers['Location'],'/')
    def test_cross_origin_write(self):self.signin();self.assertEqual(self.client.post('/api/projects',json={'name':'x'},headers={'Origin':'https://evil.example'}).status_code,403)
    def test_setup_api(self):self.signin();self.assertIn('models',self.client.get('/api/setup').json)
    def test_presets_roundtrip(self):
        self.signin();r=self.client.post('/api/image/presets/user',json={'name':'Test','preset_type':'complete','includes':{'prompt':True},'prompt':'original','params':{'steps':20}})
        self.assertEqual(r.status_code,200);pid=r.json['preset']['id'];self.assertEqual(r.json['preset']['prompt'],'original')
        self.assertEqual(self.client.delete('/api/image/presets/user/'+pid).status_code,200)

    def test_model_hub_auth_and_csrf(self):
        self.assertEqual(self.client.get('/api/model-hub/status').status_code,401)
        self.signin();r=self.client.get('/api/model-hub/status');self.assertEqual(r.status_code,200)
        self.assertIn('csrf',r.json);self.assertIn('task_support',r.json['models'][0])
        self.assertEqual(self.client.post('/api/model-hub/downloads',json={}).status_code,403)
        self.assertEqual(self.client.post('/api/model-hub/inspect',json={'url':'http://localhost/x'},headers={'X-CSRF-Token':r.json['csrf']}).status_code,400)

    def test_research_weight_downloads_are_disabled_server_side(self):
        self.signin()
        self.client.put('/api/setup',json={'identity_license_acknowledged':True},headers={'X-CSRF-Token':self.client.get('/api/vision/session').json['csrf']})
        for component in ['instantid','buffalo_l','inswapper','antelopev2']:
            r=self.client.post('/api/setup/model-download/'+component,json={})
            self.assertEqual(r.status_code,403)

    def test_token_store_write_read_disconnect_no_token_echo(self):
        self.signin();csrf=self.client.get('/api/model-hub/status').json['csrf']
        token='hf_FAKE_FLASK_TEST_ONLY'
        r=self.client.put('/api/model-hub/accounts/huggingface',json={'token':token,'store_without_test':True},headers={'X-CSRF-Token':csrf})
        self.assertEqual(r.status_code,200);self.assertNotIn(token,r.get_data(as_text=True))
        self.assertNotIn(token,self.client.get('/api/model-hub/status').get_data(as_text=True))
        path=self.mod.DATA_ROOT/'secrets'
        self.assertEqual(self.client.get('/api/setup/browse',query_string={'path':str(path)}).status_code,403)
        r=self.client.delete('/api/model-hub/accounts/huggingface',json={},headers={'X-CSRF-Token':csrf});self.assertEqual(r.status_code,200)

    def test_first_run_gui_and_account_change(self):
        from werkzeug.security import generate_password_hash
        # First-run is exercised in-place and then the test account is restored.
        try:
            self.mod.atomic_json(self.mod.AUTH_CONFIG_PATH,{'enabled':True,'username':'C','password_hash':'','session_hours':1})
            self.client=self.mod.app.test_client()
            self.assertEqual(self.client.get('/login').headers['Location'],'/first-run')
            self.client.get('/first-run')
            with self.client.session_transaction() as session: csrf=session['first_run_csrf']
            r=self.client.post('/first-run',data={'first_run_csrf':csrf,'username':'Tester','password':'first-run-pass-123','confirm_password':'first-run-pass-123','network':'local'})
            self.assertEqual(r.status_code,302);self.assertTrue(r.headers['Location'].startswith('/?onboarding=1'))
            self.assertEqual(self.client.get('/api/account').json['username'],'Tester')
            r=self.client.put('/api/account',json={'username':'Tester2','current_password':'first-run-pass-123','new_password':'second-pass-123','confirm_password':'second-pass-123'})
            self.assertEqual(r.status_code,200);self.assertEqual(r.json['username'],'Tester2')
            self.client.get('/logout')
            self.assertEqual(self.client.post('/login',data={'username':'Tester2','password':'second-pass-123'}).status_code,302)
        finally:
            self.mod.atomic_json(self.mod.AUTH_CONFIG_PATH,{'enabled':True,'username':'C','password_hash':generate_password_hash('test-password-123'),'session_hours':1})
            self.client=self.mod.app.test_client()

if __name__=='__main__':unittest.main(verbosity=2)
