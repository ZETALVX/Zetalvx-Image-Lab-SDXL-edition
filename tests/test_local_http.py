"""Actual Flask route/auth checks when Flask is installed. No GPU. Not simulated passes."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from core.local_models import LocalModels
from tests.test_model_hub import sample
HAS=importlib.util.find_spec('flask') is not None
@unittest.skipUnless(HAS,'Flask not installed: run check.sh in runtime/app')
class LocalHTTP(unittest.TestCase):
 def setUp(self):
  from flask import Flask,session,request,jsonify
  from core.model_hub_api import register_model_hub
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.models=self.root/'models';self.models.mkdir()
  self.catalog=LocalModels(self.models,self.root/'refs.json');self.weight=self.root/'test.safetensors';self.weight.write_bytes(sample('checkpoint','sdxl'))
  self.m={'id':'sdxl','provider':'sdxl','capabilities':['generate'],'config':{}}
  self.app=Flask(__name__);self.app.secret_key='tests-only'
  @self.app.before_request
  def auth():
   if not session.get('test_auth'):return jsonify(error='Unauthorized'),401
  def upd(mid,d):self.m['config'].update(d['config'])
  cb={'models':lambda:[self.m],'model_by_id':lambda id:self.m,'update_model':upd,'validate_model':lambda m:{'ready':True},'settings':lambda:{},'identity_status':lambda:{},'scan_checkpoints':lambda:self.catalog.scan('checkpoint',self.m['config']),'scan_loras':lambda:self.catalog.scan('lora',self.m['config']),'local_models':self.catalog}
  self.patches=[patch('core.model_hub_api.DATA_ROOT',self.root),patch('core.model_hub_api.SHARED_ROOT',self.root/'shared'),patch('core.model_hub_api.MODELS_ROOT',self.models),patch.dict('os.environ',{'SDXL_STUDIO_NO_BACKGROUND':'1'})]
  for p in self.patches:p.start()
  register_model_hub(self.app,cb);self.client=self.app.test_client()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def login(self):
  with self.client.session_transaction() as s:s['test_auth']=True
  self.headers={'X-CSRF-Token':self.client.get('/api/model-hub/local').json['csrf']}
 def add(self,**kw):return self.client.post('/api/model-hub/local',json={'path':str(self.weight),'kind':'checkpoint',**kw},headers=self.headers)
 def test_auth(self):self.assertEqual(self.client.get('/api/model-hub/local').status_code,401)
 def test_csrf(self):
  self.login();self.assertEqual(self.client.post('/api/model-hub/local',json={'kind':'checkpoint','path':str(self.weight)}).status_code,403)
 def test_add(self):
  self.login();r=self.add();self.assertEqual(r.status_code,200);self.assertEqual(r.json['catalog']['checkpoint'][0]['path'],str(self.weight))
 def test_no_copy(self):
  self.login();self.add();self.assertTrue(self.weight.exists());self.assertFalse((self.models/'SDXL/test.safetensors').exists())
 def test_remove_preserves_weights(self):
  self.login();rid=self.add().json['entry']['id'];r=self.client.delete('/api/model-hub/local/'+rid,json={},headers=self.headers);self.assertFalse(r.json['weights_deleted']);self.assertTrue(self.weight.exists())
 def test_folder(self):
  self.login();self.assertEqual(self.add(path=str(self.root),entry_type='folder').status_code,200)
 def test_bad_path(self):
  self.login();self.assertEqual(self.add(path='../escape').status_code,400)
 def test_bad_kind(self):
  self.login();self.assertEqual(self.add(kind='arbitrary').status_code,400)
 def test_browser_upload(self):
  import io
  self.login();data=sample('checkpoint','sdxl')
  r=self.client.post('/api/model-hub/uploads',json={'filename':'browser.safetensors','size':len(data),'kind':'checkpoint'},headers=self.headers);self.assertEqual(r.status_code,200);uid=r.json['upload']['id']
  r=self.client.post(f'/api/model-hub/uploads/{uid}/chunk',data={'offset':'0','chunk':(io.BytesIO(data),'chunk.bin')},headers={'X-CSRF-Token':self.headers['X-CSRF-Token']},content_type='multipart/form-data');self.assertEqual(r.status_code,200)
  r=self.client.post(f'/api/model-hub/uploads/{uid}/finalize',json={},headers=self.headers);self.assertEqual(r.status_code,200);self.assertTrue(Path(r.json['path']).is_file())
if __name__=='__main__':unittest.main()
