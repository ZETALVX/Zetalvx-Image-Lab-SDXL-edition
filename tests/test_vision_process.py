"""Process ownership/protocol tests with a fake llama-server, never a real model."""
import io,json,os,sys,tempfile,textwrap,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from vision.registry import Registry,VisionError
from vision.runtime import Engine
class ProcessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.r=Registry(self.home);self.e=Engine(self.r)
  for x in ('model.gguf','mmproj.gguf'):(self.home/x).write_bytes(b'GGUFmock')
  script='''#!PYTHON
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import sys,json
args=sys.argv[1:]; port=int(args[args.index('--port')+1]);key=Path(args[args.index('--api-key-file')+1]).read_text()
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  self.send_response(200 if self.headers.get('Authorization')=='Bearer '+key else 401);self.end_headers();self.wfile.write(b'{"data":[{"id":"zetalvx-vision"}]}')
 def do_POST(self):
  d=json.loads(self.rfile.read(int(self.headers['Content-Length'])));assert d['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,');self.send_response(200);self.end_headers();self.wfile.write(b'{"choices":[{"message":{"content":"A square."}}]}')
ThreadingHTTPServer(('127.0.0.1',port),H).serve_forever()
'''.replace('PYTHON',sys.executable)
  self.exe=self.home/'llama-server';self.exe.write_text(script);self.exe.chmod(0o700)
  self.m=self.r.save({'name':'test GGUF','backend':'gguf','gguf_path':str(self.home/'model.gguf'),'mmproj_path':str(self.home/'mmproj.gguf'),'llama_path':str(self.exe),'terms_reviewed':True,'device':'cpu','timeout':10,'startup_timeout':30});b=io.BytesIO();Image.new('RGB',(8,8)).save(b,format='PNG');self.image=b.getvalue()
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def test_own_process_reuse_and_cleanup(self):
  self.assertEqual(self.e.caption(self.m,self.image,'Describe'),'A square.');pid=self.e.proc.pid;key=self.e.keyfile;self.assertTrue(key.is_file());self.assertEqual(self.e.caption(self.m,self.image,'Describe'),'A square.');self.assertEqual(self.e.proc.pid,pid);self.e.unload();self.assertFalse(key.exists());self.assertFalse(self.e.status()['backend_process_running'])
  with self.assertRaises(ProcessLookupError):os.kill(pid,0)
 def test_no_model_substitution_missing_projector(self):
  m={**self.m,'mmproj_path':str(self.home/'wrong.gguf')}
  with self.assertRaises(VisionError):self.e.caption(m,self.image,'Describe')
  self.assertFalse(self.e.status()['backend_process_running'])
 def test_local_args_no_download_or_wildcard_host(self):
  self.e.caption(self.m,self.image,'Describe');cmd=Path(f'/proc/{self.e.proc.pid}/cmdline').read_bytes().replace(b'\x00',b' ').decode();self.assertIn('--mmproj',cmd);self.assertIn('--host 127.0.0.1',cmd);self.assertNotIn('-hf ',cmd);self.assertNotIn('0.0.0.0',cmd)
if __name__=='__main__':unittest.main()
