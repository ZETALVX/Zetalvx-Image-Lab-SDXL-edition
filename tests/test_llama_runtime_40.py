import io,json,os,tarfile,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from vision.llama_runtime import LlamaRuntimeManager,managed_executable,LlamaRuntimeError

class LlamaManagedRuntime40Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.home=Path(self.t.name)/'CreatorStudioSDXL';self.home.mkdir()
 def tearDown(self):self.t.cleanup()
 def fake_archive(self,path):
  exe='llama-server.exe' if os.name=='nt' else 'llama-server'
  if path.suffix=='.zip':
   with zipfile.ZipFile(path,'w') as z:z.writestr('llama/'+exe,b'fake');z.writestr('llama/dependency.dll',b'x')
  else:
   with tarfile.open(path,'w:gz') as t:
    data=b'fake';info=tarfile.TarInfo('llama/'+exe);info.size=len(data);info.mode=0o755;t.addfile(info,io.BytesIO(data))
 def test_managed_executable_has_windows_suffix(self):
  p=managed_executable(self.home);self.assertEqual(p.name,'llama-server.exe' if os.name=='nt' else 'llama-server')
 def test_status_missing(self):self.assertFalse(LlamaRuntimeManager(self.home).status()['installed'])
 def test_rejects_wrong_github_asset_host(self):
  m=LlamaRuntimeManager(self.home)
  with self.assertRaises(LlamaRuntimeError):m._download_asset({'browser_download_url':'https://evil.example/a.zip','size':3},Path(self.t.name)/'x')
 def test_safe_archive_rejects_traversal(self):
  from vision.llama_runtime import _extract
  a=Path(self.t.name)/'bad.zip'
  with zipfile.ZipFile(a,'w') as z:z.writestr('../oops',b'x')
  with self.assertRaises(LlamaRuntimeError):_extract(a,Path(self.t.name)/'out')
