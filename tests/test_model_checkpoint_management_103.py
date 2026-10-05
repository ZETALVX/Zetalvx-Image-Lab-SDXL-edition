"""Focused 1.0.3 checkpoint-library tests. No GPU/network/app server."""
import tempfile, unittest
from pathlib import Path
from core.local_models import LocalModels, LocalModelError
from tests.test_model_hub import sample

class CheckpointManagement103(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.models=self.root/'models';self.cp=self.models/'SDXL';self.cp.mkdir(parents=True)
        self.store=LocalModels(self.models,self.root/'shared/config/local_models.json')
        self.a=self.cp/'a.safetensors';self.b=self.cp/'b.safetensors'
        self.a.write_bytes(sample('checkpoint','sdxl'));self.b.write_bytes(sample('checkpoint','sdxl'))
        self.cfg={'checkpoint':str(self.a)}
    def tearDown(self):self.tmp.cleanup()
    def rows(self):return self.store.scan('checkpoint',self.cfg,include_disabled=True)
    def test_disconnect_non_default_hides_from_generation_but_keeps_file(self):
        bid=next(r['id'] for r in self.rows() if r['path']==str(self.b))
        before=self.b.read_bytes()
        self.store.set_checkpoint_availability(bid,False,self.cfg)
        self.assertTrue(self.b.exists())
        self.assertEqual(self.b.read_bytes(),before)
        self.assertNotIn(str(self.b),[r['path'] for r in self.store.scan('checkpoint',self.cfg)])
        self.assertFalse(next(r for r in self.store.inventory(self.cfg)['checkpoint'] if r['path']==str(self.b))['generation_enabled'])
    def test_reconnect_restores_checkpoint(self):
        bid=next(r['id'] for r in self.rows() if r['path']==str(self.b))
        self.store.set_checkpoint_availability(bid,False,self.cfg);self.store.set_checkpoint_availability(bid,True,self.cfg)
        self.assertIn(str(self.b),[r['path'] for r in self.store.scan('checkpoint',self.cfg)])
    def test_default_cannot_be_disconnected(self):
        aid=next(r['id'] for r in self.rows() if r['path']==str(self.a))
        with self.assertRaises(LocalModelError):self.store.set_checkpoint_availability(aid,False,self.cfg)
        self.assertTrue(self.a.exists())
    def test_managed_non_default_can_be_deleted(self):
        bid=next(r['id'] for r in self.rows() if r['path']==str(self.b))
        out=self.store.delete_managed_checkpoint(bid,self.cfg)
        self.assertTrue(out['weights_deleted']);self.assertFalse(self.b.exists())
    def test_default_cannot_be_deleted(self):
        aid=next(r['id'] for r in self.rows() if r['path']==str(self.a))
        with self.assertRaises(LocalModelError):self.store.delete_managed_checkpoint(aid,self.cfg)
        self.assertTrue(self.a.exists())
    def test_external_checkpoint_is_never_deleted(self):
        ext=self.root/'external.safetensors';ext.write_bytes(sample('checkpoint','sdxl'))
        self.store.add(str(ext),'checkpoint')
        row=next(r for r in self.store.scan('checkpoint',self.cfg,include_disabled=True) if r['path']==str(ext))
        with self.assertRaises(LocalModelError):self.store.delete_managed_checkpoint(row['id'],self.cfg)
        self.assertTrue(ext.exists())
    def test_visibility_persists(self):
        bid=next(r['id'] for r in self.rows() if r['path']==str(self.b))
        self.store.set_checkpoint_availability(bid,False,self.cfg)
        second=LocalModels(self.models,self.store.registry_path)
        self.assertNotIn(str(self.b),[r['path'] for r in second.scan('checkpoint',self.cfg)])

if __name__=='__main__':unittest.main()
