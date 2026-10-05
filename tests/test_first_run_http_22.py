"""Real Flask integration tests, isolated processes (no mock HTTP passes)."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
ROOT=Path(__file__).resolve().parents[1]
PRELUDE='''
import re,json,threading
import app
from core.runtime_env import SETTINGS_FILE,atomic_json
app.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=True)
client=app.app.test_client()
base='https://192.168.1.5:8498'
peer='192.168.1.20'
code=app.first_run_codes.issue()

def form(c=None,url=None,addr=None,headers=None):
 c=c or client;url=url or base;addr=addr or peer
 r=c.get('/first-run',base_url=url,environ_overrides={'REMOTE_ADDR':addr},headers=headers or {})
 assert r.status_code==200,(r.status_code,r.get_data(as_text=True))
 match=re.search(r'name="first_run_csrf" value="([^"]+)"',r.get_data(as_text=True))
 assert match,r.get_data(as_text=True)
 return {'username':'Tester','password':'pairing-pass-123','confirm_password':'pairing-pass-123','setup_code':code,'first_run_csrf':match.group(1),'network':'lan'},r

def submit(data,c=None,url=None,addr=None,headers=None):
 return (c or client).post('/first-run',data=data,base_url=url or base,environ_overrides={'REMOTE_ADDR':addr or peer},headers=headers or {})
'''

@unittest.skipUnless(importlib.util.find_spec('flask'),'Real Flask not installed; run with runtime/app Python')
class FirstRunHTTP22Tests(unittest.TestCase):
    def check(self,body):
        with tempfile.TemporaryDirectory(prefix='sdxl-first-run-http-') as home:
            env={**os.environ,'SDXL_STUDIO_HOME':home,'SDXL_STUDIO_NO_BACKGROUND':'1','PYTHONDONTWRITEBYTECODE':'1'}
            env.pop('SDXL_STUDIO_HOST_OVERRIDE',None)
            p=subprocess.run([sys.executable,'-c',PRELUDE+'\n'+textwrap.dedent(body)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
    def test_remote_form_is_available_and_does_not_reveal_code(self):
        self.check('''
        d,r=form();text=r.get_data(as_text=True)
        assert 'name="setup_code"' in text
        assert code not in text and code not in str(r.headers)
        assert 'no-store' in r.headers['Cache-Control']
        assert r.headers['Referrer-Policy']=='no-referrer'
        assert 'value="lan" selected' in text
        ''')
    def test_remote_valid_code_creates_account_and_session(self):
        self.check('''
        d,_=form();r=submit(d);assert r.status_code==302,r.get_data(as_text=True)
        assert r.headers['Location'].startswith('/?onboarding=1')
        assert app._load_auth_config()['password_hash']
        assert not app.first_run_codes.state_path.exists()
        assert json.loads(SETTINGS_FILE.read_text())['host']=='0.0.0.0'
        assert client.get('/api/account',base_url=base).json['username']=='Tester'
        ''')
    def test_remote_missing_code_denied(self):
        self.check("d,_=form();d.pop('setup_code');r=submit(d);assert r.status_code==403,r.status_code\nassert not app._load_auth_config()['password_hash']")
    def test_remote_wrong_code_denied(self):
        self.check("d,_=form();d['setup_code']='bad';r=submit(d);assert r.status_code==403,r.status_code\nassert not app._load_auth_config()['password_hash']")
    def test_remote_plain_http_denied(self):
        self.check("r=client.get('/first-run',base_url='http://192.168.1.5',environ_overrides={'REMOTE_ADDR':peer});assert r.status_code==403,r.status_code")
    def test_local_desktop_does_not_need_code(self):
        self.check('''
        url='https://localhost:8498';addr='127.0.0.1'
        d,r=form(url=url,addr=addr);assert 'name="setup_code"' not in r.get_data(as_text=True)
        d.pop('setup_code');d['network']='local';r=submit(d,url=url,addr=addr)
        assert r.status_code==302,r.get_data(as_text=True)
        assert not app.first_run_codes.state_path.exists()
        ''')
    def test_missing_csrf_denied_even_locally(self):
        self.check("d,_=form(url='https://localhost',addr='127.0.0.1');d.pop('first_run_csrf');assert submit(d,url='https://localhost',addr='127.0.0.1').status_code==403")
    def test_csrf_is_session_bound(self):
        self.check("d,_=form();other=app.app.test_client();assert submit(d,c=other).status_code==403\nassert not app._load_auth_config()['password_hash']")
    def test_unicode_csrf_does_not_crash(self):
        self.check("d,_=form();d['first_run_csrf']='é'*40;assert submit(d).status_code==403")
    def test_cross_origin_rejected_with_correct_code(self):
        self.check("d,_=form();r=submit(d,headers={'Origin':'https://evil.test'});assert r.status_code==403\nassert not app._load_auth_config()['password_hash']")
    def test_forwarded_local_peer_still_needs_code(self):
        self.check('''
        d,_=form(url='https://localhost',addr='127.0.0.1',headers={'X-Forwarded-For':peer})
        d.pop('setup_code');r=submit(d,url='https://localhost',addr='127.0.0.1',headers={'X-Forwarded-For':peer})
        assert r.status_code==403,r.status_code
        ''')
    def test_expired_code_denied(self):
        self.check("d,_=form();app.first_run_codes.clock=lambda:1e12;assert submit(d).status_code==403")
    def test_rotate_code_without_restart(self):
        self.check("d,_=form();new=app.first_run_codes.issue();assert submit(d).status_code==403\nd['setup_code']=new;assert submit(d).status_code==302")
    def test_invalid_password_does_not_consume_code(self):
        self.check("d,_=form();d['password']='short';d['confirm_password']='short';assert submit(d).status_code==400\nd['password']=d['confirm_password']='valid-pass-123';assert submit(d).status_code==302")
    def test_no_second_account_or_code_after_setup(self):
        self.check("d,_=form();assert submit(d).status_code==302\nassert app.first_run_codes.issue() is None\nd['username']='Other';r=submit(d);assert r.headers['Location']=='/login'\nassert app._load_auth_config()['username']=='Tester'")
    def test_normal_login_still_works_without_setup_code(self):
        self.check("d,_=form();assert submit(d).status_code==302\nclient.get('/logout',base_url=base)\nr=client.post('/login',base_url=base,data={'username':'Tester','password':'pairing-pass-123'});assert r.status_code==302\nassert client.get('/api/account',base_url=base).json['username']=='Tester'")
    def test_code_never_reflected_in_error_page(self):
        self.check("d,_=form();d['password']='short';r=submit(d);assert code not in r.get_data(as_text=True) and code not in str(r.headers)")
    def test_rate_limit_returns_retry_after_and_recovers(self):
        self.check('''
        now=app.first_run_codes.clock();app.first_run_codes.clock=lambda:now
        code=app.first_run_codes.issue();d,_=form();d['setup_code']='bad'
        for _ in range(10):assert submit(d).status_code==403
        d['setup_code']=code;r=submit(d);assert r.status_code==429;assert 1<=int(r.headers['Retry-After'])<=60
        now+=61;assert submit(d).status_code==302
        ''')
    def test_two_browser_submissions_only_one_account(self):
        self.check('''
        clients=[app.app.test_client(),app.app.test_client()]
        forms=[form(c=c)[0] for c in clients]
        forms[0]['username']='First';forms[1]['username']='Second'
        barrier=threading.Barrier(2);results=[]
        def go(i):
         barrier.wait();r=submit(forms[i],c=clients[i]);results.append((i,r.status_code,r.headers.get('Location','')))
        ts=[threading.Thread(target=go,args=(i,)) for i in range(2)]
        for t in ts:t.start()
        for t in ts:t.join(10)
        wins=[i for i,status,location in results if status==302 and location.startswith('/?onboarding=1')]
        assert len(wins)==1,results
        assert app._load_auth_config()['username']==forms[wins[0]]['username']
        assert clients[1-wins[0]].get('/api/account',base_url=base).status_code==401
        ''')
    def test_keep_lan_does_not_request_unnecessary_restart(self):
        self.check("cfg=app.settings();cfg['host']='0.0.0.0';atomic_json(SETTINGS_FILE,cfg)\nd,_=form();r=submit(d);assert 'network_restart' not in r.headers['Location']")

if __name__=='__main__':unittest.main(verbosity=2)
