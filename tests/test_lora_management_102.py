"""Real filesystem tests for the 1.0.2 LoRA library; no models/GPU/network."""
import hashlib,json,struct,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from core.local_models import LocalModels,LocalModelError
from core.model_downloads import classify_safetensors
from core.lora_files import library_lock,publish
from core import training_manager as tm


def weights(width=2048,style='diffusers',metadata=None,value=0):
    stem='unet.down_blocks.1.attentions.0.transformer_blocks.0.attn2.to_k.'
    down='lora.down.weight' if style=='diffusers' else 'lora_A.weight'
    up='lora.up.weight' if style=='diffusers' else 'lora_B.weight'
    n=width*2
    header={stem+down:{'dtype':'F16','shape':[1,width],'data_offsets':[0,n]},stem+up:{'dtype':'F16','shape':[640,1],'data_offsets':[n,n+1280]}}
    if metadata:header['__metadata__']=metadata
    data=json.dumps(header,separators=(',',':')).encode()
    return struct.pack('<Q',len(data))+data+bytes([value])*(n+1280)

class LoraManagement102(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.models=self.root/'models';self.loras=self.models/'loras/SDXL';self.loras.mkdir(parents=True)
        self.store=LocalModels(self.models,self.root/'config/local_models.json')
        self.path=self.loras/'trained.safetensors';self.path.write_bytes(weights())
    def tearDown(self):self.tmp.cleanup()
    def test_diffusers_unet_only_header(self):
        self.assertEqual({k:classify_safetensors(self.path)[k] for k in ('kind','family')},{'kind':'lora','family':'sdxl'})
    def test_peft_unet_only_header(self):
        self.path.write_bytes(weights(style='peft'));self.assertEqual(classify_safetensors(self.path)['family'],'sdxl')
    def test_sd1_cross_attention_not_accepted_as_sdxl(self):
        self.path.write_bytes(weights(768));self.assertEqual(self.store.scan('lora'),[])
    def test_explicit_foreign_architecture_is_not_overridden(self):
        self.path.write_bytes(weights(metadata={'ss_base_model_version':'sd_v1'}));self.assertEqual(self.store.scan('lora'),[])
    def test_no_accidental_checkpoint_classification(self):self.assertEqual(self.store.scan('checkpoint',extra_roots=[self.loras]),[])
    def test_legacy_trained_file_discovered_without_rewrite(self):
        old=self.path.read_bytes();self.assertEqual(self.store.scan('lora')[0]['path'],str(self.path));self.assertEqual(old,self.path.read_bytes())
    def test_disconnect_keeps_file_and_catalog(self):
        row=self.store.scan('lora')[0];self.store.set_lora_availability(row['id'],False)
        self.assertEqual(self.store.scan('lora'),[]);self.assertTrue(self.path.exists())
        self.assertFalse(self.store.inventory()['lora'][0]['generation_enabled'])
    def test_reconnect_restores_selection(self):
        id=self.store.scan('lora')[0]['id'];self.store.set_lora_availability(id,False);self.store.set_lora_availability(id,True)
        self.assertEqual(len(self.store.scan('lora')),1)
    def test_availability_survives_new_instance(self):
        id=self.store.scan('lora')[0]['id'];self.store.set_lora_availability(id,False)
        second=LocalModels(self.models,self.store.registry_path);self.assertEqual(second.scan('lora'),[])
    def test_one_step_disabled_does_not_disable_another(self):
        p=self.loras/'step300.safetensors';p.write_bytes(weights(value=1))
        id=next(r['id'] for r in self.store.scan('lora') if r['path']==str(self.path));self.store.set_lora_availability(id,False)
        self.assertEqual([r['path'] for r in self.store.scan('lora')],[str(p)])
    def test_bool_required(self):
        id=self.store.scan('lora')[0]['id']
        for v in (0,1,'false',None):
            with self.subTest(value=v),self.assertRaises(LocalModelError):self.store.set_lora_availability(id,v)
    def test_unknown_id_does_not_write(self):
        with self.assertRaises(LocalModelError):self.store.set_lora_availability('a'*24,False)
        self.assertFalse(self.store.visibility_path.exists())
    def test_corrupt_availability_not_overwritten(self):
        self.store.visibility_path.parent.mkdir();self.store.visibility_path.write_text('corrupt')
        with self.assertRaises(LocalModelError):self.store.scan('lora')
        self.assertEqual(self.store.visibility_path.read_text(),'corrupt')
    def test_explicit_external_lora_can_be_disabled_without_unlinking(self):
        p=self.root/'external.safetensors';p.write_bytes(weights());self.store.add(str(p),'lora')
        rid=next(r['id'] for r in self.store.scan('lora') if r['path']==str(p))
        before=self.store.registry_path.read_bytes();self.store.set_lora_availability(rid,False)
        self.assertTrue(p.exists());self.assertEqual(before,self.store.registry_path.read_bytes())
        self.assertFalse(next(x for x in self.store.inventory()['lora'] if x['path']==str(p))['managed'])
    def test_publication_is_content_idempotent(self):
        with library_lock(self.loras):a=publish(self.path,self.loras,'published');b=publish(self.path,self.loras,'published')
        self.assertEqual(a[0],b[0]);self.assertFalse(a[1]);self.assertTrue(b[1])
    def test_reuse_legacy_numbered_copy_when_canonical_different(self):
        (self.loras/'result.safetensors').write_bytes(b'other weights')
        legacy=self.loras/'result_3.safetensors';legacy.write_bytes(self.path.read_bytes())
        with library_lock(self.loras):result=publish(self.path,self.loras,'result')
        self.assertEqual(result[0],legacy);self.assertTrue(result[1]);self.assertEqual(len(list(self.loras.glob('result*'))),2)
    def test_same_name_collision_keeps_old_file(self):
        p=self.loras/'same.safetensors';p.write_bytes(b'other')
        with library_lock(self.loras):a=publish(self.path,self.loras,'same');b=publish(self.path,self.loras,'same')
        self.assertEqual(p.read_bytes(),b'other');self.assertEqual(a[0],b[0]);self.assertIn('_sha256_',a[0].name)
    def test_parallel_promotion_produces_one_copy(self):
        def go(_):
            with library_lock(self.loras):return publish(self.path,self.loras,'parallel')[0]
        with ThreadPoolExecutor(max_workers=4) as pool:paths=list(pool.map(go,range(8)))
        self.assertEqual(len(set(paths)),1);self.assertEqual(len(list(self.loras.glob('parallel*'))),1)
    def test_temp_files_removed(self):
        with library_lock(self.loras):publish(self.path,self.loras,'clean')
        self.assertEqual(list(self.loras.glob('*.part')),[])

class TrainingArtifactManagement102(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();r=Path(self.tmp.name);self.root=r;self.jobs=r/'jobs';self.loras=r/'loras';self.loras.mkdir()
        self.jid='abc123def456';self.job=self.jobs/self.jid;self.cp=self.job/'checkpoints/step_000100';self.cp.mkdir(parents=True)
        (self.cp/'pytorch_lora_weights.safetensors').write_bytes(weights());(self.cp/'trainer_state.json').write_text('{"step":100}')
        (self.job/'job.json').write_text(json.dumps({'id':self.jid,'name':'demo','mode':'lora','status':'completed'}));(self.job/'progress.json').write_text('{}')
        self.patch=patch.multiple(tm,JOBS=self.jobs,LORA_ROOT=self.loras,EXPORTS=r/'exports',ensure=lambda:None);self.patch.start()
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def test_checkpoint_promote_twice(self):
        a=tm.promote_checkpoint(self.jid,100);b=tm.promote_checkpoint(self.jid,100)
        self.assertEqual(a['path'],b['path']);self.assertTrue(b['already_promoted']);self.assertEqual(len(list(self.loras.glob('*.safetensors'))),1)
    def test_promoted_step_metadata_is_not_final_job_step(self):
        (self.job/'progress.json').write_text('{"step":300,"max_steps":300}')
        out=tm.promote_checkpoint(self.jid,100)
        row=next(x for x in tm.list_loras() if x['path']==out['path'])
        self.assertEqual(row['job']['step'],100);self.assertEqual(row['job']['max_steps'],300)
    def test_checkpoint_mapping_persisted(self):
        a=tm.promote_checkpoint(self.jid,100);d=json.loads((self.job/'progress.json').read_text());self.assertEqual(d['checkpoint_loras']['100']['path'],a['path'])
        self.assertEqual(tm._job_payload(self.jid)['checkpoints'][0]['promoted_lora_path'],a['path'])
    def test_delete_checkpoint_keeps_promoted_copy_and_final(self):
        out=tm.promote_checkpoint(self.jid,100);final=self.job/'final';final.mkdir();f=final/'pytorch_lora_weights.safetensors';f.write_bytes(weights())
        tm.delete_checkpoint(self.jid,100)
        self.assertFalse(self.cp.exists());self.assertTrue(Path(out['path']).exists());self.assertTrue(f.exists());self.assertTrue((self.job/'job.json').exists())
    def test_cannot_delete_active_checkpoint(self):
        (self.job/'progress.json').write_text('{"status":"running"}')
        with self.assertRaises(RuntimeError):tm.delete_checkpoint(self.jid,100)
        self.assertTrue(self.cp.exists())
    def test_cannot_delete_source_of_active_continuation(self):
        other=self.jobs/'def123abc456';other.mkdir();(other/'job.json').write_text(json.dumps({'id':other.name,'status':'queued','source_weights_checkpoint':str(self.cp)}))
        with self.assertRaises(RuntimeError):tm.delete_checkpoint(self.jid,100)
    def test_delete_only_selected_lora_preserves_final_and_checkpoints(self):
        final=self.job/'final';final.mkdir();f=final/'pytorch_lora_weights.safetensors';f.write_bytes(weights())
        p=self.loras/'registered.safetensors';p.write_bytes(weights());(self.job/'progress.json').write_text(json.dumps({'registered_lora':str(p)}))
        tm.delete_lora(tm._lora_id(p));self.assertFalse(p.exists());self.assertTrue(f.exists());self.assertTrue(self.cp.exists())
    def test_recover_reuses_matching_copy(self):
        final=self.job/'final';final.mkdir();f=final/'pytorch_lora_weights.safetensors';f.write_bytes(weights())
        p=self.loras/'demo_step_000100.safetensors';p.write_bytes(weights());(self.job/'progress.json').write_text('{"step":100}')
        result=tm.recover_lora(tm._lora_id(f));self.assertEqual(result['path'],str(p));self.assertTrue(result['already_registered'])
    def test_removed_promotion_does_not_claim_already_registered(self):
        p=Path(tm.promote_checkpoint(self.jid,100)['path']);p.unlink();self.assertEqual(tm._job_payload(self.jid)['checkpoints'][0]['promoted_lora_path'],'')
    def test_checkpoint_link_escape_refused(self):
        outside=self.root/'outside';outside.mkdir();(outside/'keep').write_text('keep')
        import shutil;shutil.rmtree(self.cp)
        try:self.cp.symlink_to(outside,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
        with self.assertRaises(RuntimeError):tm.delete_checkpoint(self.jid,100)
        self.assertTrue((outside/'keep').exists())

if __name__=='__main__':unittest.main(verbosity=2)
