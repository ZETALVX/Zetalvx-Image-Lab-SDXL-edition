import io, tempfile, unittest
from pathlib import Path
from core.local_models import LocalModels, LocalModelError
from core.model_uploads import BrowserModelUploads
from tests.test_model_hub import sample

class BrowserUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.models=self.root/'models';self.models.mkdir()
        self.catalog=LocalModels(self.models,self.root/'refs.json');self.up=BrowserModelUploads(self.models,self.catalog)
    def tearDown(self):self.tmp.cleanup()
    def fs(self,data):
        class F:
            def __init__(self,b):self.stream=io.BytesIO(b);self.content_length=len(b)
        return F(data)
    def upload(self,kind='checkpoint',name='model.safetensors',data=None):
        data=data or sample(kind,'sdxl');st=self.up.create(name,len(data),kind);self.up.append(st['id'],0,self.fs(data));return st
    def test_checkpoint_upload_to_standard_folder(self):
        st=self.upload();r=self.up.finalize(st['id']);p=Path(r['path']);self.assertTrue(p.is_file());self.assertEqual(p.parent,self.models/'SDXL');self.assertEqual(len(self.catalog.scan('checkpoint')),1)
    def test_lora_upload_to_standard_folder(self):
        st=self.upload('lora','style.safetensors');r=self.up.finalize(st['id']);self.assertEqual(Path(r['path']).parent,self.models/'loras/SDXL');self.assertEqual(len(self.catalog.scan('lora')),1)
    def test_upload_does_not_overwrite(self):
        d=sample('checkpoint','sdxl');(self.models/'SDXL').mkdir();(self.models/'SDXL/model.safetensors').write_bytes(d)
        st=self.upload(data=d);r=self.up.finalize(st['id']);self.assertEqual(Path(r['path']).name,'model-2.safetensors')
    def test_offset_mismatch_rejected(self):
        data=sample('checkpoint','sdxl');st=self.up.create('m.safetensors',len(data),'checkpoint');self.assertRaises(LocalModelError,self.up.append,st['id'],1,self.fs(data))
    def test_cancel_removes_stage(self):
        data=sample('checkpoint','sdxl');st=self.up.create('m.safetensors',len(data),'checkpoint');self.up.cancel(st['id']);self.assertFalse((self.up.root/f"{st['id']}.json").exists())
    def test_non_safetensors_name_rejected(self):self.assertRaises(LocalModelError,self.up.create,'model.ckpt',12,'checkpoint')
    def test_wrong_kind_rejected_on_finalize(self):
        data=sample('lora','sdxl');st=self.up.create('x.safetensors',len(data),'checkpoint');self.up.append(st['id'],0,self.fs(data));self.assertRaises(LocalModelError,self.up.finalize,st['id'])

if __name__=='__main__':unittest.main()
