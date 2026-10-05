"""HTTP boundary tests for the update blueprint; run when Flask is installed."""
import importlib.util,unittest,tempfile,io
from pathlib import Path
from unittest.mock import patch
HAS_FLASK=importlib.util.find_spec('flask') is not None
@unittest.skipUnless(HAS_FLASK,'Flask unavailable: update HTTP/auth tests need runtime/app')
class UpdateHTTP28(unittest.TestCase):
    def setUp(self):
        from flask import Flask,session,jsonify
        from werkzeug.security import generate_password_hash
        from core.app_update_api import register
        from core.install_layout import set_pointers
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)/'home';self.source=self.home/'versions/0.1.0.29';self.source.mkdir(parents=True)
        set_pointers(self.home,'0.1.0.29',None)
        self.app=Flask(__name__);self.app.secret_key='fixture-secret';self.app.config['TESTING']=True
        @self.app.before_request
        def gate():
            from flask import request
            from core.http_security import same_origin
            if not session.get('creator_authenticated'):return jsonify(error='Authentication required'),401
            if request.method in {'POST','PUT','DELETE','PATCH'} and not same_origin(request.headers.get('Origin'),request.host_url):return jsonify(error='Cross origin'),403
        self.config={'enabled':True,'password_hash':generate_password_hash('test-password-123')}
        self.store=register(self.app,self.home,self.source,lambda:self.config)
        @self.app.post('/api/fixture-write')
        def write():return jsonify(ok=True)
        self.client=self.app.test_client()
    def tearDown(self):self.tmp.cleanup()
    def auth(self):
        with self.client.session_transaction() as s:s.update(creator_authenticated=True,creator_username='C',auth_stamp='fixture',creator_csrf_nonce='nonce')
        return self.client.get('/api/app-updates').json['csrf']
    def test_state_requires_login(self):self.assertEqual(self.client.get('/api/app-updates').status_code,401)
    def test_import_requires_csrf(self):
        self.auth();self.assertEqual(self.client.post('/api/app-updates/import').status_code,403)
    def test_disabled_login_rejected(self):
        self.auth();self.config['enabled']=False;self.assertEqual(self.client.get('/api/app-updates').status_code,403)
    def test_remote_plain_http_rejected(self):
        self.auth();self.assertEqual(self.client.get('/api/app-updates',environ_overrides={'REMOTE_ADDR':'192.168.1.2'}).status_code,403)
    def test_reauthentication_wrong_password(self):
        csrf=self.auth()
        with patch.object(self.store,'start') as start:
            r=self.client.post('/api/app-updates/'+('a'*32)+'/start',json={'trust_source':True,'password':'wrong'},headers={'X-CSRF-Token':csrf})
            self.assertEqual(r.status_code,403);start.assert_not_called()
    def test_confirmation_body_must_be_object(self):
        csrf=self.auth();r=self.client.post('/api/app-updates/'+('a'*32)+'/start',json=['bad'],headers={'X-CSRF-Token':csrf});self.assertEqual(r.status_code,400)
    def test_non_ascii_csrf_rejected(self):
        self.auth();r=self.client.post('/api/app-updates/import',headers={'X-CSRF-Token':'é'});self.assertEqual(r.status_code,403)
    def test_missing_trust_rejected(self):
        csrf=self.auth();r=self.client.post('/api/app-updates/'+('a'*32)+'/start',json={'password':'test-password-123'},headers={'X-CSRF-Token':csrf});self.assertEqual(r.status_code,400)
    def test_confirmed_start_calls_service_once(self):
        csrf=self.auth()
        with patch.object(self.store,'start') as start,patch.object(self.store,'public_state',return_value={'status':'starting'}):
            r=self.client.post('/api/app-updates/'+('a'*32)+'/start',json={'trust_source':True,'password':'test-password-123'},headers={'X-CSRF-Token':csrf});self.assertEqual(r.status_code,202);start.assert_called_once_with('a'*32,False)
    def test_import_cannot_execute_start(self):
        csrf=self.auth()
        with patch.object(self.store,'import_zip') as load,patch.object(self.store,'start') as start:
            r=self.client.post('/api/app-updates/import',data={'file':(io.BytesIO(b'fixture'),'release.zip')},headers={'X-CSRF-Token':csrf})
            self.assertEqual(r.status_code,200);load.assert_called_once();start.assert_not_called()
    def test_update_blocks_new_writes_not_status(self):
        self.auth()
        with patch.object(self.store,'maintenance',return_value=True):
            self.assertEqual(self.client.post('/api/fixture-write').status_code,503);self.assertEqual(self.client.get('/api/app-updates').status_code,200)
    def test_source_cross_origin_rejected(self):
        csrf=self.auth();r=self.client.post('/api/app-updates/import',headers={'X-CSRF-Token':csrf,'Origin':'https://evil.example'});self.assertEqual(r.status_code,403)
    def test_password_rate_limit(self):
        csrf=self.auth();codes=[]
        for _ in range(6):codes.append(self.client.post('/api/app-updates/'+('a'*32)+'/start',json={'trust_source':True,'password':'wrong'},headers={'X-CSRF-Token':csrf}).status_code)
        self.assertEqual(codes,[403]*5+[429])
    def test_no_cache_tokens_response(self):self.auth();self.assertEqual(self.client.get('/api/app-updates').headers['Cache-Control'],'no-store')
if __name__=='__main__':unittest.main()
