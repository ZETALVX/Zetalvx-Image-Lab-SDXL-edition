"""HTTP boundary tests. Require Flask/Werkzeug; never remove a real installation."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
try:
 from flask import Flask
 from werkzeug.security import generate_password_hash
 HAVE_FLASK=True
except ImportError:HAVE_FLASK=False

@unittest.skipUnless(HAVE_FLASK,'Flask/Werkzeug absent: run these uninstall HTTP tests in runtime/app')
class UninstallHTTPTests(unittest.TestCase):
 def setUp(self):
  from core.app_uninstall_api import register
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.home=Path(self.tmp.name);self.cfg={'enabled':True,'username':'admin','password_hash':generate_password_hash('current-password')}
  self.service=Mock();self.service.home=self.home
  self.service.plan.side_effect=lambda purge=False:{'home':str(self.home),'purge_data':purge,'data_preserved':not purge,'can_purge_data':True}
  self.service.start.side_effect=lambda purge:{'id':'a'*32,'status':'starting','data_preserved':not purge,'report':'/tmp/result.json'}
  self.app=Flask(__name__);self.app.secret_key='test-only-secret'
  with patch('core.app_uninstall_api.UninstallService',return_value=self.service):register(self.app,self.home,self.home,lambda:self.cfg)
  self.app.add_url_rule('/api/dummy-write',view_func=lambda:('ok',200),methods=['POST'])
  self.client=self.app.test_client();self.sign_in()
  self.csrf=self.client.get('/api/app-uninstall').get_json()['csrf']
 def sign_in(self):
  with self.client.session_transaction() as s:s.update(creator_authenticated=True,creator_username='admin',auth_stamp=self.cfg['password_hash'][-20:],creator_csrf_nonce='nonce')
 def post(self,path,d,**kw):return self.client.post('/api/app-uninstall'+path,json=d,headers=kw.pop('headers',{'X-CSRF-Token':self.csrf,'Origin':'http://localhost'}),**kw)
 def challenge(self,purge=False):return self.post('/challenge',{'purge_data':purge}).get_json()['challenge']
 def data(self,purge=False):
  c=self.challenge(purge);return {'challenge_id':c['id'],'word':c['word'],'purge_data':purge,'understand':True,'password':'current-password','password_repeat':'current-password'}
 def test_valid_start_accepted_once(self):
  d=self.data();self.assertEqual(self.post('/start',d).status_code,202);self.assertEqual(self.post('/start',d).status_code,403);self.service.start.assert_called_once_with(False)
 def test_two_passwords_required(self):
  d=self.data();d.pop('password_repeat');self.assertEqual(self.post('/start',d).status_code,403);self.service.start.assert_not_called()
 def test_wrong_password(self):
  d=self.data();d['password']=d['password_repeat']='wrong';self.assertEqual(self.post('/start',d).status_code,403)
 def test_wrong_word(self):
  d=self.data();d['word']='wrong';self.assertEqual(self.post('/start',d).status_code,403)
 def test_invalid_csrf(self):self.assertEqual(self.post('/challenge',{},headers={'X-CSRF-Token':'x'}).status_code,403)
 def test_foreign_origin(self):self.assertEqual(self.post('/challenge',{},headers={'X-CSRF-Token':self.csrf,'Origin':'https://attacker.invalid'}).status_code,403)
 def test_anonymous_denied(self):
  with self.client.session_transaction() as s:s.clear()
  self.assertEqual(self.client.get('/api/app-uninstall').status_code,403)
 def test_auth_disabled_denied(self):
  self.cfg['enabled']=False;self.assertEqual(self.client.get('/api/app-uninstall').status_code,403)
 def test_other_user_denied(self):
  with self.client.session_transaction() as s:s['creator_username']='other'
  self.assertEqual(self.client.get('/api/app-uninstall').status_code,403)
 def test_replaced_password_denied(self):
  self.cfg['password_hash']=generate_password_hash('replacement');self.assertEqual(self.client.get('/api/app-uninstall').status_code,403)
 def test_remote_plain_http_denied(self):self.assertEqual(self.client.get('/api/app-uninstall',environ_overrides={'REMOTE_ADDR':'192.168.1.9'}).status_code,403)
 def test_remote_https_allowed(self):self.assertEqual(self.client.get('/api/app-uninstall',base_url='https://localhost',environ_overrides={'REMOTE_ADDR':'192.168.1.9'}).status_code,200)
 def test_default_keeps_data(self):self.assertFalse(self.client.get('/api/app-uninstall').get_json()['plan']['purge_data'])
 def test_purge_cannot_change_after_word(self):
  d=self.data();d['purge_data']=True;self.assertEqual(self.post('/start',d).status_code,400)
 def test_no_acknowledgement(self):
  d=self.data();d['understand']=False;self.assertEqual(self.post('/start',d).status_code,400)
 def test_cancel_invalidates_word(self):
  d=self.data();self.assertEqual(self.post('/cancel',{'challenge_id':d['challenge_id']}).status_code,200);self.assertEqual(self.post('/start',d).status_code,403)
 def test_preflight_failure_does_not_retry(self):
  d=self.data();self.service.start.side_effect=RuntimeError('Busy');self.assertEqual(self.post('/start',d).status_code,409);self.assertEqual(self.post('/start',d).status_code,403)
 def test_other_session_same_account_denied(self):
  d=self.data()
  with self.client.session_transaction() as s:s['creator_csrf_nonce']='different'
  self.csrf=self.client.get('/api/app-uninstall').get_json()['csrf'];self.assertEqual(self.post('/start',d).status_code,403)
 def test_result_has_no_password(self):
  d=self.data();r=self.post('/start',d);self.assertNotIn('current-password',r.get_data(as_text=True));self.assertEqual(r.headers.get('Cache-Control'),'no-store')
 def test_maintenance_prevents_other_writes(self):
  (self.home/'uninstall-pending.json').write_text('{}');self.assertEqual(self.client.post('/api/dummy-write').status_code,503)
 def test_invalid_json(self):self.assertEqual(self.post('/challenge',[]).status_code,400)
if __name__=='__main__':unittest.main()
