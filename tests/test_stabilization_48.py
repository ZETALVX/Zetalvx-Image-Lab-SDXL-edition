import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from vision.llama_runtime import LlamaRuntimeManager
from scripts import install as installer

class Stabilization48(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.home=Path(self.t.name);self.m=LlamaRuntimeManager(self.home)
 def tearDown(self):self.t.cleanup()
 def asset(self,name):return {"id":1,"name":name,"browser_download_url":"https://github.com/ggml-org/llama.cpp/releases/download/v0.4.1/"+name,"size":1,"digest":"sha256:"+"0"*64}
 def release(self,names):return {"id":7,"tag_name":"v0.4.1","assets":[self.asset(x) for x in names],"draft":False,"prerelease":False}
 @patch("vision.llama_runtime.platform.machine",return_value="x86_64")
 def test_linux_current_cuda12_name(self,_):
  r=self.release(["llama-v0.4.1-bin-ubuntu-cuda-12.8-x64.tar.gz","cudart-llama-v0.4.1-bin-ubuntu-cuda-12.8-x64.tar.gz"])
  with patch("vision.llama_runtime.os.name","posix"),patch("vision.llama_runtime.sys_platform",return_value="linux"):
   b,main,comp=self.m._choose_backend(r,"cuda12")
  self.assertEqual(b,"cuda12");self.assertIn("cuda-12.8",main["name"]);self.assertEqual(len(comp),1)
 @patch("vision.llama_runtime.platform.machine",return_value="x86_64")
 def test_linux_cpu_name(self,_):
  r=self.release(["llama-v0.4.1-bin-ubuntu-x64.tar.gz"])
  with patch("vision.llama_runtime.os.name","posix"),patch("vision.llama_runtime.sys_platform",return_value="linux"):
   b,main,comp=self.m._choose_backend(r,"cpu")
  self.assertEqual((b,main["name"],comp),("cpu","llama-v0.4.1-bin-ubuntu-x64.tar.gz",[]))
 @patch("vision.llama_runtime.platform.machine",return_value="x86_64")
 def test_windows_current_cuda12_name(self,_):
  r=self.release(["llama-v0.4.1-bin-win-cuda-12.4-x64.zip","cudart-llama-v0.4.1-bin-win-cuda-12.4-x64.zip"])
  with patch("vision.llama_runtime.os.name","nt"):
   b,main,comp=self.m._choose_backend(r,"cuda12")
  self.assertEqual(b,"cuda12");self.assertIn("cuda-12.4",main["name"]);self.assertEqual(len(comp),1)

class RuntimeIsolation48(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.home=Path(self.t.name)/"CreatorStudioSDXL";(self.home/"runtime/app/bin").mkdir(parents=True)
 def tearDown(self):self.t.cleanup()
 def test_global_python_target_is_refused(self):
  with patch("scripts.install.home_path",return_value=self.home),patch("scripts.install.inventory",return_value={"prefix":"/usr"}):
   with self.assertRaisesRegex(RuntimeError,"Refusing pip outside"):installer.assert_private_runtime_python(Path("/usr/bin/python3"))
 def test_private_runtime_prefix_is_accepted(self):
  py=self.home/"runtime/app/bin/python";prefix=self.home/"runtime/app"
  with patch("scripts.install.home_path",return_value=self.home),patch("scripts.install.inventory",return_value={"prefix":str(prefix)}):
   out=installer.assert_private_runtime_python(py)
  self.assertEqual(out["prefix"],str(prefix.absolute()))

if __name__=="__main__":unittest.main()
