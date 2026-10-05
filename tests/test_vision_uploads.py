import io, tempfile, unittest
from pathlib import Path
from vision.uploads import BrowserVisionUploads
from vision.registry import VisionError

class Stream:
    def __init__(self,data):
        self.stream=io.BytesIO(data);self.content_length=len(data)

class VisionUploadsTest(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.home=Path(self.t.name);self.u=BrowserVisionUploads(self.home)
    def tearDown(self):self.t.cleanup()
    def upload(self,name='vision.gguf',role='gguf_path',data=b'GGUF'+b'x'*128):
        st=self.u.create(name,len(data),role);self.u.append(st['id'],0,Stream(data));return st
    def test_model_upload(self):
        st=self.upload();r=self.u.finalize(st['id']);p=Path(r['path']);self.assertTrue(p.is_file());self.assertEqual(p.parent,self.home/'models/Vision/GGUF');self.assertEqual(r['role'],'gguf_path')
    def test_mmproj_upload(self):
        st=self.upload('mmproj.gguf','mmproj_path');r=self.u.finalize(st['id']);self.assertEqual(r['role'],'mmproj_path')
    def test_reject_non_gguf(self):
        st=self.upload(data=b'NOPE'+b'x'*10)
        with self.assertRaises(VisionError):self.u.finalize(st['id'])
    def test_no_overwrite(self):
        a=self.upload('same.gguf');p1=Path(self.u.finalize(a['id'])['path']);b=self.upload('same.gguf');p2=Path(self.u.finalize(b['id'])['path']);self.assertNotEqual(p1,p2);self.assertEqual(p2.name,'same-2.gguf')
    def test_cancel(self):
        st=self.upload('cancel.gguf');self.u.cancel(st['id']);self.assertFalse(any(self.u.root.iterdir()))
    def test_reject_executable_role(self):
        with self.assertRaises(VisionError):self.u.create('llama-server',4,'llama_path')

if __name__=='__main__':unittest.main()
