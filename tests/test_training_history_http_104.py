"""Real Flask/auth/origin/delete-route tests when runtime/app deps are present.
Run in a subprocess to avoid borrowing another test's application singleton.
"""
import importlib.util,subprocess,sys,unittest
from pathlib import Path
HAS_FLASK=importlib.util.find_spec('flask') is not None
SCRIPT=r'''
import json,os,tempfile
from pathlib import Path
from unittest.mock import patch
with tempfile.TemporaryDirectory() as td:
 os.environ['SDXL_STUDIO_HOME']=td;os.environ['SDXL_STUDIO_NO_BACKGROUND']='1'
 import app as mod
 from core import training_manager as tm
 from werkzeug.security import generate_password_hash
 mod.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
 mod.atomic_json(mod.AUTH_CONFIG_PATH,{'enabled':True,'username':'C','password_hash':generate_password_hash('history-local-test-password'),'session_hours':1})
 mod._creator_gpu_jobs_busy=lambda:None;mod._identity_gpu_busy=lambda:None
 jid='abcdef123456';p=tm.JOBS/jid;p.mkdir(parents=True)
 (p/'job.json').write_text(json.dumps({'id':jid,'status':'completed','mode':'lora'}));(p/'progress.json').write_text('{}');(p/'job.log').write_text('old log')
 tm.DATASETS.mkdir(parents=True,exist_ok=True);(tm.DATASETS/'keep.txt').write_text('keep')
 tm.LORA_ROOT.mkdir(parents=True,exist_ok=True);(tm.LORA_ROOT/'published.safetensors').write_bytes(b'keep-model')
 c=mod.app.test_client();url='/api/training/jobs/'+jid
 with patch.object(tm,'worker_health',return_value={'ok':True,'busy':False}):
  assert c.delete(url,json={'confirm':True}).status_code==401
  c.post('/login',data={'username':'C','password':'history-local-test-password'})
  assert c.delete(url,json={'confirm':True},headers={'Origin':'https://evil.invalid'}).status_code==403
  assert c.delete(url,json={}).status_code==400
  assert c.delete(url,json={'confirm':'true'}).status_code==400
  (p/'progress.json').write_text('{"status":"running"}')
  assert c.delete(url,json={'confirm':True}).status_code==409;assert p.exists()
  (p/'progress.json').write_text('{}')
  r=c.delete(url,json={'confirm':True});assert r.status_code==200,r.data
  assert not p.exists();assert (tm.DATASETS/'keep.txt').read_text()=='keep';assert (tm.LORA_ROOT/'published.safetensors').read_bytes()==b'keep-model'
  assert c.delete(url,json={'confirm':True}).json['deleted']['already_absent'] is True
 print('HISTORY_HTTP_104_OK (7 contracts)')
'''
class TrainingHistoryHttp104(unittest.TestCase):
    @unittest.skipUnless(HAS_FLASK,'Flask unavailable: run with runtime/app; NOT an HTTP pass')
    def test_real_authenticated_endpoint_contracts(self):
        p=subprocess.run([sys.executable,'-c',SCRIPT],cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('HISTORY_HTTP_104_OK',p.stdout)
