"""Real Flask and HTTPS integration; fresh processes prevent shared fixture state.
Skipped only if the actual dependencies are missing; no mocked HTTP passes.
"""
import importlib.util,os,subprocess,sys,tempfile,textwrap,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PRELUDE='''
import app,json
from werkzeug.security import generate_password_hash
app._save_auth_config('Tester',generate_password_hash('test-password-42'))
app.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=True)
client=app.app.test_client()
base='https://localhost:8298'
def login(password='test-password-42',username='Tester',**kwargs):
 return client.post('/login',data={'username':username,'password':password},base_url=base,**kwargs)
'''
@unittest.skipUnless(importlib.util.find_spec('flask') and importlib.util.find_spec('werkzeug'),'Requires real Flask/Werkzeug in runtime/app')
class StabilizationHTTP42(unittest.TestCase):
 def check(self,body):
  with tempfile.TemporaryDirectory(prefix='sdxl-auth-http-') as home:
   env={**os.environ,'SDXL_STUDIO_HOME':home,'SDXL_STUDIO_NO_BACKGROUND':'1','PYTHONDONTWRITEBYTECODE':'1'}
   for key in ['PYTHONPATH','PYTHONHOME','SDXL_STUDIO_HOST_OVERRIDE']:env.pop(key,None)
   r=subprocess.run([sys.executable,'-c',PRELUDE+'\n'+textwrap.dedent(body)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=45)
   self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)
 def test_ninth_bad_login_is_throttled(self):
  self.check('''
  for _ in range(8):assert login('wrong').status_code==200
  r=login('wrong');assert r.status_code==429;assert int(r.headers['Retry-After'])>0
  assert client.get('/api/account',base_url=base).status_code==401
  ''')
 def test_over_limit_does_not_check_password_hash(self):
  self.check('''
  from unittest.mock import patch
  for _ in range(8):app.login_throttle.reserve('127.0.0.1')
  with patch.object(app,'check_password_hash',side_effect=AssertionError('hash called')):
   assert login('wrong').status_code==429
  ''')
 def test_expired_limit_allows_valid_login(self):
  self.check('''
  import time
  now=time.time()
  app.login_throttle.clock=lambda:now
  for _ in range(8):login('wrong')
  app.login_throttle.clock=lambda:now+61
  assert login().status_code==302
  assert client.get('/api/account',base_url=base).json['username']=='Tester'
  ''')
 def test_forwarded_peer_does_not_bypass(self):
  self.check('''
  for i in range(8):assert login('wrong',headers={'X-Forwarded-For':f'192.0.2.{i}'}).status_code==200
  assert login('wrong',headers={'X-Forwarded-For':'192.0.2.100'}).status_code==429
  ''')
 def test_long_password_never_hashed(self):
  self.check('''
  from unittest.mock import patch
  with patch.object(app,'check_password_hash',side_effect=AssertionError('hash called')):
   assert login('x'*1025).status_code==200
  assert client.get('/api/account',base_url=base).status_code==401
  ''')
 def test_large_login_body_rejected(self):
  self.check("assert login('x'*20000).status_code==413")
 def test_non_ascii_username_is_not_server_error(self):
  self.check("assert login(username='測試').status_code==200")
 def test_foreign_origin_login_rejected(self):
  self.check("assert login(headers={'Origin':'https://foreign.invalid'}).status_code==403")
 def test_success_issues_secure_cookie(self):
  self.check("r=login();assert r.status_code==302;assert 'Secure' in r.headers['Set-Cookie'];assert 'HttpOnly' in r.headers['Set-Cookie']")
 def test_restart_with_download_returns_conflict(self):
  self.check('''
  from unittest.mock import patch
  assert login().status_code==302
  p=app.DATA_ROOT/'shared/vision/link-imports/fixture.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'status':'downloading'}))
  with patch.object(app.subprocess,'Popen',side_effect=AssertionError('must not stop services')):
   r=client.post('/api/app-control/restart',base_url=base)
   assert r.status_code==409,r.get_data(as_text=True)
  ''')

@unittest.skipUnless(importlib.util.find_spec('flask') and importlib.util.find_spec('cheroot'),'Requires real Flask and Cheroot; no mock web server result')
class RealWebTransport42(unittest.TestCase):
 def test_https_login_token_storage_restart_and_lan_binding(self):
  with tempfile.TemporaryDirectory(prefix='sdxl-real-https-') as home:
   env={**os.environ,'SDXL_STUDIO_HOME':home,'SDXL_STUDIO_NO_BACKGROUND':'1','PYTHONDONTWRITEBYTECODE':'1'}
   for key in ['PYTHONPATH','PYTHONHOME','SDXL_STUDIO_HOST_OVERRIDE']:env.pop(key,None)
   r=subprocess.run([sys.executable,str(ROOT/'scripts/web_transport_smoke.py')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
   self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)

if __name__=='__main__':unittest.main()
