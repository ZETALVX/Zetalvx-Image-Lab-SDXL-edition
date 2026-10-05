"""CPU regression tests for the integrated editor, without model/Flask dependencies."""
import io,json,tempfile,unittest,zipfile,threading,time,importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from core.dataset_workspace import Workspace,DatasetConflict,DatasetBusy
from core.dataset_exchange import DatasetError,atomic_json
from vision.batch import Batch
from vision.registry import Registry


def png(color='navy',size=(24,32)):
    b=io.BytesIO();Image.new('RGB',size,color).save(b,'PNG');return b.getvalue()
def file(name,data):return SimpleNamespace(filename=name,stream=io.BytesIO(data))

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.busy=False
        self.w=Workspace(self.root/'datasets',self.root/'jobs',caption_active=lambda did:self.busy)
        self.d=self.w.create({'name':'Test','trigger':'itapigna','trigger_position':'context'});self.did=self.d['id']
    def tearDown(self):self.temp.cleanup()
    def add(self,caption='',name='one.png',color='navy'):
        files=[file(name,png(color))]
        if caption is not None:files.append(file(Path(name).stem+'.txt',caption.encode('utf8')))
        return self.w.uploads(self.did,files)['dataset']['items'][-1]
    def test_shared_schema(self):
        self.assertEqual(self.w.read(self.did)['trigger_position'],'context')
        self.assertEqual(self.w.read(self.did)['id'],self.did)
    def test_verbatim_caption_upload(self):
        cap='  A photo of itapigna, in a garden.\n';it=self.add(cap)
        self.assertEqual(it['caption'],cap);self.assertEqual(it['caption_source'],'imported')
    def test_empty_upload_does_not_inject_trigger(self):
        it=self.add(None);self.assertEqual(it['caption'],'');self.assertEqual(self.w.info(self.w.read(self.did))['needs_caption'],1)
    def test_utf8_bom_caption(self):
        r=self.w.uploads(self.did,[file('one.png',png()),file('one.txt',b'\xef\xbb\xbfitapigna, test')]);self.assertEqual(r['dataset']['items'][0]['caption'],'itapigna, test')
    def test_duplicate_hash_preserves_caption(self):
        self.add('MANUAL');r=self.w.uploads(self.did,[file('different.png',png()),file('different.txt',b'REPLACE')]);self.assertEqual(r['duplicates'],1);self.assertEqual(r['dataset']['items'][0]['caption'],'MANUAL')
    def test_legacy_no_sha_deduped(self):
        it=self.add('');d=self.w.read(self.did);d['items'][0].pop('sha256');atomic_json(self.w.folder(self.did)/'dataset.json',d)
        self.assertEqual(self.w.uploads(self.did,[file('copy.png',png())])['duplicates'],1)
    def test_legacy_metadata_preserved(self):
        d=self.w.read(self.did);d['legacy_extra']={'opaque':True};atomic_json(self.w.folder(self.did)/'dataset.json',d)
        self.w.update(self.did,{'name':'New'});self.assertEqual(self.w.read(self.did)['legacy_extra'],{'opaque':True})
    def test_manual_caption_exact_save(self):
        it=self.add('old');cap='  one\ntwo  ';r=self.w.update(self.did,{'captions':{it['id']:cap},'expected_captions':{it['id']:'old'}});self.assertEqual(r['items'][0]['caption'],cap)
    def test_stale_caption_rejected(self):
        it=self.add('new')
        with self.assertRaises(DatasetConflict):self.w.update(self.did,{'captions':{it['id']:'stale'},'expected_captions':{it['id']:'old'}})
        self.assertEqual(self.w.read(self.did)['items'][0]['caption'],'new')
    def test_idempotent_save_allowed(self):
        it=self.add('same');self.w.update(self.did,{'captions':{it['id']:'same'},'expected_captions':{it['id']:'old'}})
    def test_removed_image_conflict(self):
        with self.assertRaises(DatasetConflict):self.w.update(self.did,{'captions':{'gone':'text'}})
    def test_stale_settings_rejected(self):
        with self.assertRaises(DatasetConflict):self.w.update(self.did,{'name':'Overwrite','expected':{'name':'not-current'}})
    def test_profile_remembered(self):
        self.w.update(self.did,{'vision_model_id':'mymodel'});self.assertEqual(self.w.read(self.did)['vision_model_id'],'mymodel')
    def test_prefix_only_missing(self):
        a=self.add('a portrait');b=self.add('A photo of itapigna walking','two.png','red')
        self.w.update(self.did,{'trigger_position':'prefix'});r=self.w.apply(self.did)
        self.assertEqual(r['changed'],1);self.assertEqual(r['dataset']['items'][0]['caption'],'itapigna, a portrait');self.assertEqual(r['dataset']['items'][1]['caption'],b['caption'])
    def test_suffix_only_missing(self):
        self.add('a portrait');self.w.update(self.did,{'trigger_position':'suffix'});self.assertEqual(self.w.apply(self.did)['dataset']['items'][0]['caption'],'a portrait, itapigna')
    def test_context_does_not_rewrite(self):
        self.add('a portrait');self.assertEqual(self.w.apply(self.did)['changed'],0)
    def test_trigger_only_needs_caption(self):
        self.add('itapigna');self.assertEqual(self.w.info(self.w.read(self.did))['needs_caption'],1)
    def test_roundtrip_standalone_zip(self):
        for i,c in enumerate(['itapigna, beginning','end, itapigna','photo of itapigna smiling']):self.add(c,f'{i}.png',['red','blue','green'][i])
        out=self.root/'out.zip';self.w.export_archive(self.did,out)
        other=Workspace(self.root/'other',self.root/'other_jobs');d=other.import_archive(out)
        self.assertEqual([i['caption'] for i in d['items']],[i['caption'] for i in self.w.read(self.did)['items']]);self.assertNotEqual(d['id'],self.did)
        self.assertNotIn(str(self.root),zipfile.ZipFile(out).read('dataset.json').decode())
    def test_txt_only_fills_empty(self):
        it=self.add('');r=self.w.uploads(self.did,[file('one.txt',b'new caption')]);self.assertEqual(r['captions_imported'],1);self.assertEqual(r['dataset']['items'][0]['caption'],'new caption')
    def test_txt_only_preserves_manual(self):
        self.add('manual');r=self.w.uploads(self.did,[file('one.txt',b'new')]);self.assertEqual(r['captions_preserved'],1);self.assertEqual(r['dataset']['items'][0]['caption'],'manual')
    def test_orphan_txt_rejected(self):
        with self.assertRaises(DatasetError):self.w.uploads(self.did,[file('orphan.txt',b'text')])
    def test_invalid_utf8_rejected(self):
        with self.assertRaises(DatasetError):self.w.uploads(self.did,[file('one.png',png()),file('one.txt',b'\xff')])
        self.assertEqual(self.w.read(self.did)['items'],[])
    def test_ambiguous_stems_rejected(self):
        with self.assertRaises(DatasetError):self.w.uploads(self.did,[file('one.png',png()),file('one.jpg',png('red'))])
    def test_invalid_images_atomic(self):
        with self.assertRaises(DatasetError):self.w.uploads(self.did,[file('one.png',png()),file('bad.png',b'not a photo')])
        self.assertEqual(self.w.read(self.did)['items'],[]);self.assertEqual(list((self.w.folder(self.did)/'images').iterdir()),[])
    def test_disk_commit_failure_rolls_back_files(self):
        with patch('core.dataset_workspace.atomic_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.add('text')
        self.assertEqual(list((self.w.folder(self.did)/'images').iterdir()),[])
    def test_path_escape_rejected(self):
        with self.assertRaises(DatasetError):self.w.read('../other')
    def test_symlink_dataset_rejected(self):
        (self.w.root/'linked').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(DatasetError):self.w.folder('linked')
    def test_external_image_refused(self):
        it=self.add('');d=self.w.read(self.did);d['items'][0]['file']=str(self.root/'outside.png');(self.root/'outside.png').write_bytes(png());atomic_json(self.w.folder(self.did)/'dataset.json',d)
        with self.assertRaises(DatasetError):self.w.remove_item(self.did,it['id'])
        self.assertTrue((self.root/'outside.png').exists())
    def test_delete_own_image_only(self):
        it=self.add('');p=Path(it['file']);self.w.remove_item(self.did,it['id']);self.assertFalse(p.exists())
    def test_busy_caption_allows_manual_edit(self):
        it=self.add('');self.busy=True;self.w.update(self.did,{'captions':{it['id']:'manual'}})
        with self.assertRaises(DatasetBusy):self.w.remove(self.did)
        with self.assertRaises(DatasetBusy):self.w.remove_item(self.did,it['id'])
        with self.assertRaises(DatasetBusy):self.w.uploads(self.did,[file('new.png',png())])
    def test_training_locks_dataset(self):
        it=self.add('');p=self.w.jobs/'job1';p.mkdir(parents=True);atomic_json(p/'job.json',{'id':'job1','dataset_id':self.did,'status':'queued'})
        with self.assertRaises(DatasetBusy):self.w.update(self.did,{'name':'x'})
        with self.assertRaises(DatasetBusy):self.w.preflight(self.did)
        atomic_json(p/'progress.json',{'status':'completed'});self.assertEqual(self.w.preflight(self.did)['dataset']['id'],self.did)
    def test_use_is_no_copy_no_mutation(self):
        self.add('a portrait of itapigna');before=(self.w.folder(self.did)/'dataset.json').read_bytes();self.w.preflight(self.did);self.assertEqual(before,(self.w.folder(self.did)/'dataset.json').read_bytes())
    def test_preflight_empty_blocked(self):
        with self.assertRaises(DatasetError):self.w.preflight(self.did)
    def test_preflight_caption_busy_blocked(self):
        self.add('');self.busy=True
        with self.assertRaises(DatasetBusy):self.w.preflight(self.did)

class CaptionMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.lock=threading.RLock();self.enter=threading.Event();self.go=threading.Event();self.calls=[]
        self.w=Workspace(self.root/'datasets',self.root/'jobs',lock=self.lock)
        self.d=self.w.create({'name':'Batch','trigger':'itapigna','trigger_position':'suffix'});self.did=self.d['id']
        self.it=self.w.uploads(self.did,[file('one.png',png())])['dataset']['items'][0]
        registry=Registry(self.root);self.model=registry.save({'name':'Fake test','backend':'api','api_model':'fake','endpoint':'http://127.0.0.1:1/v1','terms_reviewed':True,'enabled':True})
        outer=self
        class Engine:
            def caption(self,m,img,prompt,cancel):
                outer.calls.append(prompt);outer.enter.set();outer.go.wait(3)
                return 'a person outside'
            def unload(self):pass
        self.batch=Batch(self.root/'caption-jobs',self.w.root,registry,Engine(),lock=self.lock)
    def tearDown(self):self.go.set();self.batch.thread and self.batch.thread.join(5);self.temp.cleanup()
    def run_job(self):
        j=self.batch.start(self.did,self.model['id']);self.assertTrue(self.enter.wait(3));return j
    def test_caption_saved_to_same_training_dataset(self):
        j=self.run_job();self.go.set();self.batch.thread.join(5);d=self.w.read(self.did)
        self.assertEqual(d['items'][0]['caption'],'a person outside, itapigna');self.assertEqual(d['vision_model_id'],self.model['id'])
    def test_manual_edit_during_inference_preserved(self):
        self.run_job();self.w.update(self.did,{'captions':{self.it['id']:'my manual caption'},'expected_captions':{self.it['id']:''}});self.go.set();self.batch.thread.join(5)
        self.assertEqual(self.w.read(self.did)['items'][0]['caption'],'my manual caption');self.assertEqual(self.batch.list()[0]['preserved'],1)
    def test_trigger_change_during_inference_not_applied(self):
        self.run_job();self.w.update(self.did,{'trigger':'different'});self.go.set();self.batch.thread.join(5)
        self.assertEqual(self.w.read(self.did)['items'][0]['caption'],'');self.assertEqual(self.batch.list()[0]['preserved'],1)
    def test_context_retry_reports_missing(self):
        self.w.update(self.did,{'trigger_position':'context'});self.go.set();self.batch.start(self.did,self.model['id']);self.batch.thread.join(5)
        self.assertEqual(len(self.calls),2);self.assertEqual(self.batch.list()[0]['needs_review'],1)
    def test_cancel_preserves_empty(self):
        self.run_job();self.batch.cancel();self.go.set();self.batch.thread.join(5);self.assertEqual(self.batch.list()[0]['status'],'cancelled');self.assertEqual(self.w.read(self.did)['items'][0]['caption'],'')


class InvalidCreateTests(unittest.TestCase):
    def test_invalid_create_does_not_leave_partial_dataset(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);w=Workspace(root/'datasets',root/'jobs')
            with self.assertRaises(DatasetError):w.create({'name':'safe','common_caption':['wrong type']})
            self.assertEqual(list(w.root.iterdir()),[])

if __name__=='__main__':unittest.main(verbosity=2)
