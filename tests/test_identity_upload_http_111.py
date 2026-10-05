"""Real Flask + Cheroot + TLS test, intentionally skipped if dependencies absent.
No fake Flask is injected; only model execution/background dispatch is disabled.
"""
import importlib.util,subprocess,sys,unittest
from pathlib import Path
READY=all(importlib.util.find_spec(x) for x in ('flask','werkzeug','cheroot'))
SCRIPT=r'''
import os,tempfile,json,threading,time,hashlib
from pathlib import Path
import requests
with tempfile.TemporaryDirectory() as td:
 os.environ['SDXL_STUDIO_HOME']=td;os.environ['SDXL_STUDIO_NO_BACKGROUND']='1'
 import app as mod
 from werkzeug.security import generate_password_hash
 from core.local_certificate import generate_certificate
 from core.web_server import make_server
 mod.atomic_json(mod.AUTH_CONFIG_PATH,{'enabled':True,'username':'test','password_hash':generate_password_hash('upload-test-password'),'session_hours':1})
 mod.app.config.update(TESTING=False,SESSION_COOKIE_SECURE=True)
 cert=Path(td)/'test-certs';cert.mkdir();generate_certificate(cert)
 server=make_server(mod.app,'127.0.0.1',0,tls=(str(cert/'cert.pem'),str(cert/'key.pem')))
 thread=threading.Thread(target=server.start,daemon=True);thread.start()
 try:
  for _ in range(100):
   if getattr(server,'ready',False):break
   time.sleep(.05)
  assert server.ready,'Server did not start'
  url='https://127.0.0.1:'+str(server.socket.getsockname()[1])
  s=requests.Session();s.verify=str(cert/'cert.pem')
  assert s.post(url+'/api/identity/jobs',data={}).status_code==401
  r=s.post(url+'/login',data={'username':'test','password':'upload-test-password'},allow_redirects=False);assert r.status_code==302,r.text
  pid=s.post(url+'/api/projects',json={'name':'HTTP fixture'}).json()['project']['id']
  payload=b'\x89PNG\r\n\x1a\n'+b'unchanged-upload-bytes'*1000
  def files():return [('references',('face.png',payload,'image/png')),('base_image',('base.png',payload,'image/png'))]
  for mode in ('face_swap','instantid','face_swap'):
   r=s.post(url+'/api/identity/jobs',data={'project_id':pid,'mode':mode,'guidance':'5','seed':'111'},files=files(),timeout=15)
   assert r.status_code==202,r.text
   job=mod.identity_get_job(r.json()['job_id']);assert Path(job['reference_paths'][0]).read_bytes()==payload
  before=len(list(mod.IDENTITY_JOBS.iterdir()))
  r=s.post(url+'/api/identity/jobs',data=b'bad multipart',headers={'Content-Type':'multipart/form-data; boundary=not-there'});assert r.status_code==400,r.text
  assert r.json()['code']=='identity_upload_invalid' and not r.json()['queued']
  assert len(list(mod.IDENTITY_JOBS.iterdir()))==before
  r=s.post(url+'/api/identity/jobs',data=b'bad',headers={'Content-Type':'multipart/form-data'});assert r.status_code==400 and r.json()['diagnostic_id']
  assert s.post(url+'/api/identity/jobs',json={}).status_code==415
  assert s.post(url+'/api/identity/jobs',data={'project_id':pid,'mode':'face_swap'},files=files(),headers={'Origin':'https://evil.invalid'}).status_code==403
  mod.app.config['MAX_CONTENT_LENGTH']=4096
  r=s.post(url+'/api/identity/jobs',data={'project_id':pid},files=files());assert r.status_code==413 and r.json()['code']=='identity_upload_too_large'
  mod.app.config['MAX_CONTENT_LENGTH']=128*1024*1024
  r=s.post(url+'/api/identity/jobs',data={'project_id':pid,'mode':'face_swap'},files=files());assert r.status_code==202,r.text
  r=s.post(url+'/api/identity/auto-test',data={'project_id':pid,'mode':'instantid','sweep_config':'{"identity":[0.9],"pose":[0.6],"cfg":[5]}'},files=files());assert r.status_code==202 and r.json()['count']==1,r.text
  print('IDENTITY_REAL_HTTPS_111_OK')
 finally:server.stop();thread.join(timeout=10)
'''
class IdentityRealHTTP111(unittest.TestCase):
 @unittest.skipUnless(READY,'Flask/Werkzeug/Cheroot unavailable: real HTTPS not executed')
 def test_actual_upload_rejection_and_recovery_over_tls(self):
  p=subprocess.run([sys.executable,'-c',SCRIPT],cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=60)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('IDENTITY_REAL_HTTPS_111_OK',p.stdout)
if __name__=='__main__':unittest.main(verbosity=2)
