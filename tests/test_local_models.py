"""Actual filesystem/catalogue tests, no torch or GPU model loading."""
import json, tempfile, unittest
from pathlib import Path
from core.local_models import LocalModels, LocalModelError
from tests.test_model_hub import sample

class LocalCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.models=self.root/'models';self.cp=self.models/'SDXL';self.lr=self.models/'loras/SDXL'
        self.cp.mkdir(parents=True);self.lr.mkdir(parents=True)
        self.catalog=LocalModels(self.models,self.root/'config/local_models.json',(self.root/'secrets',))
    def tearDown(self):self.tmp.cleanup()
    def weight(self,name='a.safetensors',kind='checkpoint',family='sdxl',root=None):
        p=(root or (self.cp if kind=='checkpoint' else self.lr))/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(sample(kind,family));return p
    def test_standard_discovery(self):
        p=self.weight();l=self.weight('b.safetensors','lora');self.assertEqual(self.catalog.scan('checkpoint')[0]['path'],str(p));self.assertEqual(self.catalog.scan('lora')[0]['path'],str(l))
    def test_add_file_without_copy(self):
        p=self.weight(root=self.root/'external');before=p.read_bytes();e=self.catalog.add(str(p),'checkpoint');self.assertIn('entry',e);self.assertEqual(p.read_bytes(),before);self.assertEqual(list(self.cp.iterdir()),[]);self.assertEqual(len(self.catalog.scan('checkpoint')),1)
    def test_duplicate_reference(self):
        p=self.weight();self.catalog.add(str(p),'checkpoint');self.assertTrue(self.catalog.add(str(p),'checkpoint')['already_linked']);self.assertEqual(len(self.catalog.sources()),1)
    def test_remove_does_not_delete(self):
        p=self.weight(root=self.root/'ext');e=self.catalog.add(str(p),'checkpoint')['entry'];self.catalog.remove(e['id']);self.assertTrue(p.exists());self.assertEqual(self.catalog.scan('checkpoint'),[])
    def test_standard_remains_after_unlink(self):
        p=self.weight();e=self.catalog.add(str(p),'checkpoint')['entry'];self.catalog.remove(e['id']);self.assertEqual(len(self.catalog.scan('checkpoint')),1)
    def test_add_folder_and_rescan(self):
        d=self.root/'external';d.mkdir();self.catalog.add(str(d),'lora','folder');self.assertEqual(self.catalog.scan('lora'),[]);p=self.weight('later.safetensors','lora',root=d);self.assertEqual(self.catalog.scan('lora')[0]['path'],str(p))
    def test_multiple_folders(self):
        for i in range(2):
            d=self.root/str(i);d.mkdir();self.catalog.add(str(d),'checkpoint','folder');self.weight(root=d)
        self.assertEqual(len(self.catalog.scan('checkpoint')),2)
    def test_missing_reference_visible(self):
        p=self.weight(root=self.root/'ext');self.catalog.add(str(p),'checkpoint');p.unlink();self.assertEqual(self.catalog.scan('checkpoint'),[]);self.assertFalse(self.catalog.inventory()['checkpoint'][0]['present'])
    def test_registry_reloaded(self):
        p=self.weight();self.catalog.add(str(p),'checkpoint');c=LocalModels(self.models,self.catalog.registry_path);self.assertEqual(len(c.sources()),1)
    def test_unknown_requires_confirmation(self):
        p=self.weight('unknown.safetensors','unknown',family='');r=self.catalog.add(str(p),'checkpoint');self.assertTrue(r['needs_confirmation']);self.assertEqual(self.catalog.sources(),[]);self.assertIn('entry',self.catalog.add(str(p),'checkpoint',accept_unknown=True))
    def test_known_other_family_rejected(self):
        p=self.weight(family='flux');self.assertRaises(LocalModelError,self.catalog.add,str(p),'checkpoint',accept_unknown=True)
    def test_lora_as_checkpoint_rejected(self):
        p=self.weight('a.safetensors','lora');self.assertRaises(LocalModelError,self.catalog.add,str(p),'checkpoint',accept_unknown=True)
    def test_checkpoint_as_lora_rejected(self):
        p=self.weight();self.assertRaises(LocalModelError,self.catalog.add,str(p),'lora',accept_unknown=True)
    def test_html_rejected(self):
        p=self.cp/'error.safetensors';p.write_text('<html>NO MODEL</html>');self.assertRaises(LocalModelError,self.catalog.add,str(p),'checkpoint')
    def test_pickle_not_linkable(self):
        p=self.cp/'a.ckpt';p.write_bytes(b'pickle');self.assertRaises(LocalModelError,self.catalog.add,str(p),'checkpoint')
    def test_legacy_scanned_marked(self):
        p=self.cp/'a.ckpt';p.write_bytes(b'legacy trusted');self.assertTrue(self.catalog.scan('checkpoint')[0]['legacy'])
    def test_invalid_paths_rejected(self):
        for x in ('','/','/proc','/sys/any','/dev/null','relative.safetensors','https://a.b/c.safetensors',str(self.root/'secrets/key.safetensors')):
            with self.subTest(path=x):self.assertRaises(LocalModelError,self.catalog.add,x,'checkpoint')
    def test_case_insensitive_extension(self):
        p=self.weight('Test.SAFETENSORS');self.catalog.add(str(p),'checkpoint');self.assertEqual(len(self.catalog.scan('checkpoint')),1)
    def test_paths_with_spaces(self):
        p=self.weight('base model.safetensors',root=self.root/'my dir');self.catalog.add(str(p),'checkpoint');self.assertEqual(self.catalog.scan('checkpoint')[0]['path'],str(p))
    def test_symlink_file_deduplicated(self):
        p=self.weight();(self.cp/'alias.safetensors').symlink_to(p);self.assertEqual(len(self.catalog.scan('checkpoint')),1)
    def test_symlink_directory_cycle(self):
        self.weight();(self.cp/'loop').symlink_to(self.cp,target_is_directory=True);self.assertEqual(len(self.catalog.scan('checkpoint')),1)
    def test_active_outside_roots(self):
        p=self.weight(root=self.root/'elsewhere');r=self.catalog.scan('checkpoint',{'checkpoint':str(p)});self.assertTrue(r[0]['active'])
    def test_changed_file_invalidates_cache(self):
        p=self.weight();self.assertEqual(len(self.catalog.scan('checkpoint')),1);p.write_bytes(b'broken');self.assertEqual(self.catalog.scan('checkpoint'),[])
    def test_corrupt_registry_not_overwritten(self):
        self.catalog.registry_path.parent.mkdir();self.catalog.registry_path.write_text('{oops');p=self.weight();self.assertRaises(LocalModelError,self.catalog.add,str(p),'checkpoint');self.assertEqual(self.catalog.registry_path.read_text(),'{oops')
    def test_unlink_bad_id(self):self.assertRaises(LocalModelError,self.catalog.remove,'../escape')
    def test_atomic_private_registry(self):
        p=self.weight();self.catalog.add(str(p),'checkpoint');self.assertEqual(self.catalog.registry_path.stat().st_mode&0o777,0o600)
    def diffusers(self):
        d=self.cp/'trained-model';d.mkdir();(d/'model_index.json').write_text(json.dumps({'_class_name':'StableDiffusionXLPipeline'}))
        for sub in ('unet','vae','text_encoder','text_encoder_2','tokenizer','tokenizer_2','scheduler'):
            (d/sub).mkdir();f='tokenizer_config.json' if sub.startswith('tokenizer') else 'scheduler_config.json' if sub=='scheduler' else 'config.json';(d/sub/f).write_text('{}')
            if sub in ('unet','vae','text_encoder','text_encoder_2'):(d/sub/'model.safetensors').write_bytes(sample('unknown',''))
        return d
    def test_config_only_diffusers_folder_not_discovered(self):
        d=self.cp/'config';d.mkdir();(d/'model_index.json').write_text(json.dumps({'_class_name':'StableDiffusionXLPipeline'}))
        for sub in ('unet','vae','text_encoder','text_encoder_2','tokenizer','tokenizer_2','scheduler'):
            (d/sub).mkdir();f='tokenizer_config.json' if sub.startswith('tokenizer') else 'scheduler_config.json' if sub=='scheduler' else 'config.json';(d/sub/f).write_text('{}')
        self.assertEqual(self.catalog.scan('checkpoint'),[])
    def test_inpaint_config_only_folder_not_discovered(self):
        d=self.cp/'inpaint_config';d.mkdir();(d/'model_index.json').write_text(json.dumps({'_class_name':'StableDiffusionXLInpaintPipeline'}))
        (d/'unet').mkdir();(d/'unet/config.json').write_text('{}')
        self.assertEqual(self.catalog.scan('checkpoint'),[])
    def test_diffusers_complete_linked(self):
        d=self.diffusers();self.catalog.add(str(d),'checkpoint');r=self.catalog.scan('checkpoint');self.assertEqual(len(r),1);self.assertEqual(r[0]['format'],'diffusers')
    def test_diffusers_missing_component(self):
        d=self.diffusers();(d/'text_encoder_2/model.safetensors').unlink();self.assertRaises(LocalModelError,self.catalog.add,str(d),'checkpoint')
    def test_diffusers_missing_shard(self):
        d=self.diffusers();(d/'unet/model.safetensors.index.json').write_text(json.dumps({'weight_map':{'a':'missing.safetensors'}}));self.assertRaises(LocalModelError,self.catalog.add,str(d),'checkpoint')
    def test_diffusers_shard_traversal(self):
        d=self.diffusers();(d/'unet/model.safetensors.index.json').write_text(json.dumps({'weight_map':{'a':'../model.safetensors'}}));self.assertRaises(LocalModelError,self.catalog.add,str(d),'checkpoint')
    def test_diffusers_other_arch(self):
        d=self.diffusers();(d/'model_index.json').write_text(json.dumps({'_class_name':'FluxPipeline'}));self.assertRaises(LocalModelError,self.catalog.add,str(d),'checkpoint')
    def test_safetensors_vae_not_a_checkpoint(self):
        p=self.weight('vae.safetensors','vae',family='');self.assertRaises(LocalModelError,self.catalog.add,str(p),'checkpoint',accept_unknown=True)
    def test_folder_file_count_bounded(self):
        for i in range(12):self.weight(f'{i}.safetensors')
        from unittest.mock import patch
        with patch('core.local_models.MAX_FILES',3):self.assertEqual(len(self.catalog.scan('checkpoint')),3)
    def test_configured_lora_paths_combined(self):
        a=self.root/'a';b=self.root/'b';self.weight('a.safetensors','lora',root=a);self.weight('b.safetensors','lora',root=b)
        self.assertEqual(len(self.catalog.scan('lora',{'lora_root':str(a)+':'+str(b)})),2)
    def test_entry_validation(self):self.assertRaises(LocalModelError,self.catalog.add,str(self.cp),'vae','folder')
    def test_never_selects_on_add(self):
        cfg={'checkpoint':str(self.weight('original.safetensors'))};new=self.weight('new.safetensors');self.catalog.add(str(new),'checkpoint');r=self.catalog.scan('checkpoint',cfg);self.assertEqual(next(x['name'] for x in r if x['active']),'original.safetensors')

if __name__=='__main__':unittest.main()
