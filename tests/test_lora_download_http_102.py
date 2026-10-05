"""Real application routes, signed login, CSRF and file responses, not fake Flask.
Run with runtime/app. Skipped when dependencies are unavailable.
Fixtures contain tiny structurally valid weights; no inference or training.
"""
import importlib.util, os, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PRELUDE='''
import app, json, hashlib
from pathlib import Path
from werkzeug.security import generate_password_hash
from tests.test_lora_management_102 import weights
from core import training_manager as tm
from core.runtime_env import atomic_json
app._save_auth_config('Tester', generate_password_hash('download-fixture-102'))
app.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=True)
p=tm.LORA_ROOT/'step300.safetensors';p.parent.mkdir(parents=True,exist_ok=True);data=weights();p.write_bytes(data)
lid=tm._lora_id(p);route='/api/training/loras/'+lid+'/download'
jid='abc123def456';job=tm.JOBS/jid;cp=job/'checkpoints/step_000100';cp.mkdir(parents=True,exist_ok=True)
(cp/'pytorch_lora_weights.safetensors').write_bytes(data)
atomic_json(job/'job.json',{'id':jid,'name':'test','mode':'lora','status':'completed'})
atomic_json(job/'progress.json',{})
cp_route='/api/training/jobs/'+jid+'/checkpoints/100/download'
client=app.app.test_client();base='https://127.0.0.1:8298'
def login():
 r=client.post('/login',data={'username':'Tester','password':'download-fixture-102'},base_url=base,headers={'Origin':base})
 assert r.status_code==302, r.get_data(as_text=True)
def get(path,method='GET',**kwargs):return client.open(path,method=method,base_url=base,**kwargs)
'''
HAS=bool(importlib.util.find_spec('flask') and importlib.util.find_spec('werkzeug'))
@unittest.skipUnless(HAS,'Requires real Flask/Werkzeug in runtime/app; not simulated')
class LoraDownloadHTTP102(unittest.TestCase):
 def run_body(self,body,timeout=40):
  with tempfile.TemporaryDirectory(prefix='sdxl-102-http-') as home:
   env={**os.environ,'SDXL_STUDIO_HOME':home,'SDXL_STUDIO_NO_BACKGROUND':'1','PYTHONDONTWRITEBYTECODE':'1'}
   for k in ('PYTHONPATH','PYTHONHOME','SDXL_STUDIO_HOST_OVERRIDE','CREATOR_LORA_ROOTS'):env.pop(k,None)
   result=subprocess.run([sys.executable,'-c',PRELUDE+'\n'+textwrap.dedent(body)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=timeout)
   self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
 def test_download_anonymous_refused(self):
  self.run_body("assert get(route).status_code==401; assert get(route,method='HEAD').status_code==401; assert get(cp_route).status_code==401")
 def test_download_authenticated_full_sha_and_head_both_hosts(self):
  self.run_body('''
  for base in ('https://127.0.0.1:8298','https://192.168.1.239:8298'):
   login()
   for url in (route,cp_route):
    h=get(url,method='HEAD');assert h.status_code==200;assert not h.data;assert int(h.headers['Content-Length'])==len(data)
    r=get(url);assert r.status_code==200;assert r.data==data;assert r.headers['Content-Disposition'].startswith('attachment;');assert r.headers['Content-Type'].startswith('application/octet-stream')
    assert r.headers['Accept-Ranges']=='bytes';assert 'private' in r.headers['Cache-Control']
    assert hashlib.sha256(r.data).digest()==hashlib.sha256(p.read_bytes()).digest()
  ''')
 def test_range_length_and_invalid_range(self):
  self.run_body('''
  login()
  for url in (route,cp_route):
   r=get(url,headers={'Range':'bytes=8-39'});assert r.status_code==206;assert r.data==data[8:40];assert int(r.headers['Content-Length'])==32
   assert r.headers['Content-Range']==f'bytes 8-39/{len(data)}'
   assert get(url,headers={'Range':f'bytes={len(data)+1}-'}).status_code==416
  ''')
 def test_expired_session_and_unknown_id(self):
  self.run_body('''
  login();assert get('/api/training/loras/0000000000000000/download').status_code==404
  app._save_auth_config('Tester',generate_password_hash('new-password-fixture-102'))
  assert get(route).status_code==401
  ''')
 def test_toggle_needs_auth_csrf_and_same_origin(self):
  self.run_body('''
  cid=app.local_models.scan('lora')[0]['id'];url=f'/api/model-hub/local/loras/{cid}/availability'
  assert get(url,method='PUT',json={'enabled':False}).status_code==401
  login();assert get(url,method='PUT',json={'enabled':False}).status_code==403
  token=get('/api/model-hub/local').json['csrf']
  assert get(url,method='PUT',json={'enabled':False},headers={'X-CSRF-Token':token,'Origin':'https://foreign.invalid'}).status_code==403
  assert p.read_bytes()==data
  ''')
 def test_inventory_training_generate_and_reconnect(self):
  self.run_body('''
  login();cid=app.local_models.scan('lora')[0]['id'];url=f'/api/model-hub/local/loras/{cid}/availability'
  token=get('/api/model-hub/local').json['csrf'];headers={'X-CSRF-Token':token,'Origin':base}
  assert any(x['path']==str(p) for x in get('/api/loras').json['loras'])
  assert get(url,method='PUT',json={'enabled':False},headers=headers).status_code==200
  assert not any(x['path']==str(p) for x in get('/api/loras').json['loras'])
  row=next(x for x in get('/api/training/loras').json['loras'] if x['path']==str(p));assert row['generation_enabled'] is False
  assert get(route).data==data
  assert get(url,method='PUT',json={'enabled':True},headers=headers).status_code==200
  assert any(x['path']==str(p) for x in get('/api/loras').json['loras']);assert p.read_bytes()==data
  ''')
 def test_checkpoint_delete_retains_promoted_lora(self):
  self.run_body('''
  login();action='/api/training/jobs/'+jid+'/checkpoints/100'
  a=get(action+'/promote',method='POST').json['promoted'];b=get(action+'/promote',method='POST').json['promoted']
  assert a['path']==b['path'];assert b['already_promoted'] is True
  assert get(action,method='DELETE').status_code==200
  assert not cp.exists();assert Path(a['path']).read_bytes()==data;assert (job/'job.json').is_file()
  ''')
 @unittest.skipUnless(importlib.util.find_spec('cheroot'),'Requires native Cheroot transport')
 def test_real_cheroot_tls_cookie_and_stream(self):
  self.run_body('''
  import ssl, threading, time, requests
  from core.local_certificate import generate_certificate
  from core.web_server import make_server
  folder=app.DATA_ROOT/'shared/config';generate_certificate(folder)
  server=make_server(app.app,'127.0.0.1',0,tls=(str(folder/'cert.pem'),str(folder/'key.pem')))
  thread=threading.Thread(target=server.start,daemon=True);thread.start()
  try:
   deadline=time.monotonic()+10
   while not server.ready and time.monotonic()<deadline:time.sleep(.05)
   assert server.ready
   base='https://127.0.0.1:'+str(server.socket.getsockname()[1])
   with requests.Session() as c:
    c.trust_env=False;c.verify=str(folder/'cert.pem')
    assert c.get(base+route,timeout=10).status_code==401
    r=c.post(base+'/login',data={'username':'Tester','password':'download-fixture-102'},headers={'Origin':base},allow_redirects=False,timeout=10);assert r.status_code==302
    assert any(k.secure and k.name=='creator_sdxl_session' for k in c.cookies)
    h=c.head(base+route,timeout=10);assert h.status_code==200;assert int(h.headers['Content-Length'])==len(data)
    with c.get(base+route,stream=True,timeout=10) as r:
     assert r.status_code==200;result=b''.join(r.iter_content(128));assert result==data
    r=c.get(base+route,headers={'Range':'bytes=8-39'},timeout=10);assert r.status_code==206;assert r.content==data[8:40]
  finally:server.stop();thread.join(5)
  ''',timeout=45)
if __name__=='__main__':unittest.main(verbosity=2)
