import ast,base64,io,json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from vision.registry import Registry,VisionError,endpoint_url,normalize,atomic_json
from vision.runtime import Engine,clean_caption,image_bytes
from vision.batch import Batch,trigger_apply,spans
from vision.service import Service

class RegistryTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.r=Registry(self.home)
 def tearDown(self):self.tmp.cleanup()
 def test_crud_secrets_and_export(self):
  s=Service(self.home);m=s.handle('/api/vision/models','POST',{'name':'Local API','backend':'api','endpoint':'http://localhost:8080/v1','api_model':'VL','token':'secret-only-for-tests'})['model'];self.assertTrue(m['token_stored']);self.assertNotIn('secret-only-for-tests',json.dumps(m));self.assertEqual(self.r.token(m['id']),'secret-only-for-tests');self.assertEqual((self.home/'secrets/vision'/f"{m['id']}.token").stat().st_mode&0o777,0o600)
  e=s.handle('/api/vision/models/'+m['id']+'/export','GET');self.assertNotIn('secret-only',json.dumps(e));other=s.handle('/api/vision/import','POST',e)['model'];self.assertFalse(other['token_stored']);self.assertNotEqual(other['id'],m['id']);s.handle('/api/vision/models/'+m['id'],'DELETE');self.assertEqual(len(self.r.list()),1)
 def test_bad_token_does_not_save(self):
  with self.assertRaises(VisionError):self.r.save({'name':'bad','token':'a\nb'})
  self.assertEqual(self.r.list(),[])
 def test_endpoint(self):
  self.assertEqual(endpoint_url('http://127.0.0.1:8080'), 'http://127.0.0.1:8080/v1/chat/completions')
  for u in ['http://192.168.1.1/v1','https://a:b@example.test','https://example.test?a=token','ftp://bad','']:
   with self.assertRaises(VisionError):endpoint_url(u)
 def test_no_remote_code_or_args(self):
  m=self.r.save({'name':'safe','trust_remote_code':True,'extra_args':['-hf','evil'],'shell_command':'rm xyz'})
  self.assertNotIn('trust_remote_code',m);self.assertNotIn('extra_args',m);self.assertNotIn('shell_command',m)
 def test_validate_config_limits(self):
  for d in [{'context':0},{'threads':1000},{'temperature':float('nan')},{'enabled':'yes'},{'backend':'magic'}]:
   with self.assertRaises(ValueError):self.r.save({'name':'bad',**d})
 def test_unknown_id(self):
  for i in ['../a','x/y','..','']:
   with self.assertRaises(VisionError):self.r.get(i)
 def test_gguf_matching_required(self):
  model=self.home/'one.gguf';model.write_bytes(b'GGUFfake');m=self.r.save({'name':'test','backend':'gguf','gguf_path':str(model),'llama_path':sys.executable});self.assertFalse(self.r.inspect(m)['ok'])
  proj=self.home/'mmproj.gguf';proj.write_bytes(b'GGUFfake');m=self.r.save({'mmproj_path':str(proj)},m['id']);self.assertTrue(self.r.inspect(m)['ok'])
 def test_transformers_complete_directory(self):
  root=self.home/'weights';root.mkdir();(root/'config.json').write_text(json.dumps({'model_type':'qwen3_vl','vision_config':{'layers':1}}));(root/'model.safetensors').write_bytes(b'fake');(root/'tokenizer.json').write_text('{}');(root/'preprocessor_config.json').write_text('{}')
  m=self.r.save({'name':'Qwen','model_path':str(root),'python_path':sys.executable});self.assertTrue(self.r.inspect(m)['ok']);(root/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{'a':'missing.safetensors'}}));self.assertFalse(self.r.inspect(m)['ok'])
 def test_text_only_not_vision(self):
  root=self.home/'text';root.mkdir();(root/'config.json').write_text('{"model_type":"qwen3"}');m=self.r.save({'name':'text','model_path':str(root),'python_path':sys.executable});self.assertFalse(self.r.inspect(m)['ok'])
 def test_browse_private(self):
  with self.assertRaises(VisionError):self.r.browse(str(self.r.secrets))
 def test_browse_defaults_to_managed_vision_library(self):
  gguf=self.home/'models/Vision/GGUF';trans=self.home/'models/Vision/Transformers';runtime=self.home/'runtime/vision';llama=self.home/'runtime/llama.cpp/build/bin'
  for d in (gguf,trans,runtime,llama):d.mkdir(parents=True,exist_ok=True)
  self.assertEqual(Path(self.r.browse('')['path']),self.home/'models/Vision')
  self.assertEqual(Path(self.r.browse('__APP_VISION_GGUF__')['path']),gguf)
  self.assertEqual(Path(self.r.browse('__APP_VISION_TRANSFORMERS__')['path']),trans)
  self.assertEqual(Path(self.r.browse('__APP_VISION_RUNTIME__')['path']),runtime)
  self.assertEqual(Path(self.r.browse('__APP_LLAMA_RUNTIME__')['path']),llama)
 def test_legacy_api_migration(self):
  s=Service(self.home);s.migrate_legacy({'endpoint':'http://127.0.0.1:8888','model':'Qwen'},'oldtoken');self.assertEqual(len(s.registry.list()),1);m=s.registry.list()[0];self.assertFalse(m['terms_reviewed']);self.assertTrue(m['token_stored']);s.migrate_legacy({'endpoint':'http://127.0.0.1:8888','model':'Qwen'});self.assertEqual(len(s.registry.list()),1)

class ProtocolTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.service=Service(self.home);self.requests=[];self.mode=200;owner=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));owner.requests.append((self.path,dict(self.headers),data));self.send_response(owner.mode)
    if owner.mode==302:self.send_header('Location','http://127.0.0.1:1/stolen')
    self.end_headers();self.wfile.write(json.dumps({'choices':[{'message':{'content':'<think>private</think> A red square.'}}]}).encode())
  self.srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.srv.serve_forever,daemon=True).start();self.m=self.service.registry.save({'name':'API','backend':'api','endpoint':f'http://127.0.0.1:{self.srv.server_port}/v1','api_model':'VL','token':'test-secret','terms_reviewed':True});self.img=io.BytesIO();Image.new('RGB',(16,16),'red').save(self.img,format='PNG')
 def tearDown(self):self.service.engine.close();self.srv.shutdown();self.srv.server_close();self.tmp.cleanup()
 def test_api_payload(self):
  caption=self.service.engine.caption(self.m,self.img.getvalue(),'Describe');self.assertEqual(caption,'A red square.');p,h,d=self.requests[0];self.assertEqual(h['Authorization'],'Bearer test-secret');self.assertEqual(d['model'],'VL');self.assertTrue(d['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,'));self.assertFalse(self.service.engine.status()['backend_process_running'])
 def test_no_redirect_with_token(self):
  self.mode=302
  with self.assertRaises(VisionError):self.service.engine.caption(self.m,self.img.getvalue(),'Describe')
  self.assertEqual(len(self.requests),1)
 def test_terms_required(self):
  m={**self.m,'terms_reviewed':False}
  with self.assertRaises(VisionError):self.service.engine.caption(m,self.img.getvalue(),'Describe')
  self.assertEqual(self.requests,[])
 def test_async_test(self):
  j=self.service.handle('/api/vision/caption','POST',{'model_id':self.m['id'],'image':base64.b64encode(self.img.getvalue()).decode(),'confirm':True})['action'];end=time.time()+5
  while self.service.actions.list()[0]['status']=='running' and time.time()<end:time.sleep(.02)
  self.assertEqual(self.service.actions.list()[0]['status'],'completed');self.assertEqual(self.service.actions.list()[0]['message'],'A red square.')
 def test_invalid_image(self):
  with self.assertRaises(VisionError):self.service.engine.caption(self.m,b'bad image','Describe')
 def test_reasoning_only_not_caption(self):
  for s in ['<think> unfinished','<think>reasoning</think>']:
   with self.assertRaises(VisionError):clean_caption(s)

class BatchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.r=Registry(self.home);self.m=self.r.save({'name':'model-A','backend':'api','endpoint':'http://127.0.0.1:8080/v1','api_model':'VL','terms_reviewed':True});root=self.home/'datasets/dataset';root.mkdir(parents=True);self.f=root/'image.png';Image.new('RGB',(8,8)).save(self.f);self.dp=root/'dataset.json';self.output='A person standing.';self.calls=[];self.unloaded=False;owner=self
  class Fake:
   def caption(self,m,f,p,cancel=None):owner.calls.append((m,p));return owner.output
   def unload(self):owner.unloaded=True
  self.engine=Fake();self.batch=Batch(self.home/'jobs',self.home/'datasets',self.r,self.engine)
 def tearDown(self):self.tmp.cleanup()
 def setup_d(self,pos,caption=''):
  atomic_json(self.dp,{'id':'dataset','trigger':'itapigna','trigger_position':pos,'items':[{'id':'one','file':str(self.f),'caption':caption}]})
 def runjob(self):self.batch.start('dataset',self.m['id']);self.batch.thread.join(5);self.assertFalse(self.batch.busy());return json.loads(self.dp.read_text()),self.batch.list()[0]
 def test_prefix(self):self.setup_d('prefix');d,j=self.runjob();self.assertEqual(d['items'][0]['caption'],'itapigna, A person standing.');self.assertEqual(d['vision_model_id'],self.m['id']);self.assertEqual(j['model_name'],'model-A')
 def test_suffix(self):self.setup_d('suffix');d,j=self.runjob();self.assertEqual(d['items'][0]['caption'],'A person standing., itapigna')
 def test_trigger_only_caption_generated(self):self.setup_d('prefix','itapigna');d,j=self.runjob();self.assertEqual(j['done'],1)
 def test_context_existing_no_duplicate(self):self.setup_d('prefix');self.output='A photo of itapigna standing.';d,j=self.runjob();self.assertEqual(d['items'][0]['caption'],self.output)
 def test_context_missing_flags_after_retry(self):self.setup_d('context');d,j=self.runjob();self.assertEqual(len(self.calls),2);self.assertEqual(j['needs_review'],1);self.assertIn('missing_trigger',d['items'][0]['caption_flags'])
 def test_repeated_flag(self):self.setup_d('context');self.output='itapigna and itapigna.';d,j=self.runjob();self.assertEqual(j['needs_review'],1)
 def test_existing_manual_not_overwritten(self):
  self.setup_d('prefix','a custom manual caption')
  with self.assertRaises(VisionError):self.batch.start('dataset',self.m['id'])
 def test_edit_during_generation_preserved(self):
  self.setup_d('prefix');original=self.engine.caption
  def delayed(*a):
   d=json.loads(self.dp.read_text());d['items'][0]['caption']='user edit';atomic_json(self.dp,d);return original(*a)
  self.engine.caption=delayed;d,j=self.runjob();self.assertEqual(d['items'][0]['caption'],'user edit');self.assertEqual(j['preserved'],1)
 def test_missing_dataset(self):
  with self.assertRaises(VisionError):self.batch.start('missing',self.m['id'])
 def test_exact_trigger_spans(self):self.assertFalse(spans('itapigna2','itapigna'));self.assertTrue(spans('a itapigna.','itapigna'));self.assertEqual(trigger_apply('x itapigna y','itapigna','suffix'),'x itapigna y')
 def test_changed_trigger_not_injected(self):
  self.setup_d('prefix');original=self.engine.caption
  def delayed(*a):
   d=json.loads(self.dp.read_text());d['trigger']='other';atomic_json(self.dp,d);return original(*a)
  self.engine.caption=delayed;d,j=self.runjob();self.assertEqual(d['items'][0]['caption'],'');self.assertEqual(j['preserved'],1)
 def test_restart_marks_interrupted(self):
  atomic_json(self.home/'jobs/job.json',{'id':'job','status':'running'});b=Batch(self.home/'jobs',self.home/'datasets',self.r,self.engine);self.assertEqual(b.list()[0]['status'],'interrupted')

if __name__=='__main__':unittest.main()
