"""Terminal training history deletion, using actual temporary files (no GPU)."""
import json, tempfile, unittest, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from core import training_manager as tm
from core import training_history as history

class TrainingHistory104(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.jobs=self.root/'training/jobs';self.jobs.mkdir(parents=True)
        self.datasets=self.root/'training/datasets';self.datasets.mkdir()
        self.loras=self.root/'models/loras/SDXL';self.loras.mkdir(parents=True)
        self.full=self.root/'models/SDXL/trained';self.full.mkdir(parents=True)
        self.jid='abcdef123456';self.job=self.make_job(self.jid,'completed')
        cp=self.job/'checkpoints/step_000100';cp.mkdir(parents=True);(cp/'weights.safetensors').write_bytes(b'checkpoint')
        (self.job/'final').mkdir();(self.job/'final/unexported.safetensors').write_bytes(b'final')
        (self.job/'job.log').write_text('a log');(self.datasets/'keep.json').write_bytes(b'dataset')
        self.published=self.loras/'exported.safetensors';self.published.write_bytes(b'exported LoRA')
        (self.full/'model.safetensors').write_bytes(b'exported full model')
        self.patches=patch.multiple(tm,JOBS=self.jobs,DATASETS=self.datasets,LORA_ROOT=self.loras,FULL_ROOT=self.full,ensure=lambda:None,worker_health=lambda:{'ok':True,'busy':False})
        self.patches.start()
    def tearDown(self):self.patches.stop();self.tmp.cleanup()
    def make_job(self,jid,status,**fields):
        p=self.jobs/jid;p.mkdir();(p/'job.json').write_text(json.dumps({'id':jid,'name':'Test','mode':'lora','status':status,**fields}));(p/'progress.json').write_text('{}');return p
    def blocked(self):
        with self.assertRaises((ValueError,RuntimeError)):history.delete_job(self.jid,confirm=True)
        self.assertTrue((self.job/'job.json').exists())
    def test_delete_terminal_removes_card_and_all_job_files(self):
        result=history.delete_job(self.jid,confirm=True)
        self.assertTrue(result['deleted']);self.assertGreater(result['removed_bytes'],0);self.assertFalse(self.job.exists())
        self.assertEqual(tm.list_jobs({'ok':True,'busy':False}),[])
    def test_preserves_dataset_and_all_exported_model_bytes(self):
        history.delete_job(self.jid,confirm=True)
        self.assertEqual((self.datasets/'keep.json').read_bytes(),b'dataset')
        self.assertEqual(self.published.read_bytes(),b'exported LoRA')
        self.assertEqual((self.full/'model.safetensors').read_bytes(),b'exported full model')
    def test_confirm_is_explicit_boolean(self):
        for value in (False,None,1,'true'):
            with self.subTest(value=value),self.assertRaises(ValueError):history.delete_job(self.jid,confirm=value)
        self.assertTrue(self.job.exists())
    def test_missing_job_idempotent(self):
        history.delete_job(self.jid,confirm=True)
        self.assertTrue(history.delete_job(self.jid,confirm=True)['already_absent'])
    def test_rejects_path_traversal(self):
        for value in ('../outside','/tmp/test','a/b','a\\b',''):
            with self.subTest(value=value),self.assertRaises(RuntimeError):history.delete_job(value,confirm=True)
    def test_all_active_or_unknown_statuses_blocked(self):
        for status in ('running','queued','saving','dispatching','preparing','starting','cancelling','unknown',None):
            (self.job/'progress.json').write_text(json.dumps({'status':status}));self.blocked()
    def test_stopped_failed_cancelled_can_be_removed(self):
        for status in history.TERMINAL-{'completed'}:
            with self.subTest(status=status):
                p=self.make_job('old_'+status,status);history.delete_job(p.name,confirm=True);self.assertFalse(p.exists())
    def test_unavailable_worker_blocks_destructive_action(self):
        with patch.object(tm,'worker_health',return_value={'ok':False}):self.blocked()
    def test_worker_claims_completed_job_is_still_active(self):
        with patch.object(tm,'worker_health',return_value={'ok':True,'busy':True,'job_id':self.jid}):self.blocked()
    def test_unidentified_busy_worker_blocks(self):
        with patch.object(tm,'worker_health',return_value={'ok':True,'busy':True}):self.blocked()
    def test_active_continuation_parent_blocks(self):
        self.make_job('another','queued',continuation_of=self.jid);self.blocked()
    def test_active_checkpoint_reference_blocks(self):
        self.make_job('another','running',source_weights_checkpoint=str(self.job/'checkpoints/step_000100'));self.blocked()
    def test_worker_active_reference_overrides_stale_completed_status(self):
        self.make_job('another','completed',init_lora_path=str(self.job/'final/unexported.safetensors'))
        with patch.object(tm,'worker_health',return_value={'ok':True,'busy':True,'job_id':'another'}):self.blocked()
    def test_unrelated_active_training_kept(self):
        p=self.make_job('another','running',dataset_id='other')
        with patch.object(tm,'worker_health',return_value={'ok':True,'busy':True,'job_id':'another'}):history.delete_job(self.jid,confirm=True)
        self.assertTrue(p.exists())
    def test_completed_continuation_kept(self):
        p=self.make_job('another','completed',continuation_of=self.jid)
        history.delete_job(self.jid,confirm=True);self.assertTrue(p.exists())
    def test_corrupt_metadata_never_removed(self):
        (self.job/'progress.json').write_text('not JSON');self.blocked()
    def test_wrong_job_id_never_removed(self):
        (self.job/'job.json').write_text('{"id":"other","status":"completed"}');self.blocked()
    def test_symlink_inside_job_blocks_without_touching_target(self):
        outside=self.root/'outside';outside.mkdir();(outside/'keep').write_bytes(b'keep')
        try:(self.job/'linked').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('symlink privilege unavailable')
        self.blocked();self.assertEqual((outside/'keep').read_bytes(),b'keep')
    def test_symlink_job_root_rejected(self):
        link=self.jobs/'alias'
        try:link.symlink_to(self.job,target_is_directory=True)
        except OSError:self.skipTest('symlink privilege unavailable')
        with self.assertRaises(RuntimeError):history.delete_job('alias',confirm=True)
        self.assertTrue(self.job.exists())
    def test_library_nested_in_job_is_protected(self):
        with patch.object(tm,'DATASETS',self.job/'datasets'):self.blocked()
    def test_lock_is_reentrant_for_continue_create(self):
        @history.guarded
        def outer():
            with history.operation_lock():return 'ok'
        self.assertEqual(outer(),'ok')
    def test_concurrent_resume_is_serialized_against_delete(self):
        entered=threading.Event();proceed=threading.Event()
        @history.guarded
        def resume_fixture():
            entered.set();proceed.wait(5);(self.job/'progress.json').write_text('{"status":"queued"}')
        with ThreadPoolExecutor(max_workers=2) as ex:
            a=ex.submit(resume_fixture);self.assertTrue(entered.wait(3))
            b=ex.submit(history.delete_job,self.jid,confirm=True);proceed.set();a.result(5)
            with self.assertRaises(RuntimeError):b.result(5)
        self.assertTrue(self.job.exists())
    def test_empty_old_job_folder_can_be_removed(self):
        import shutil
        shutil.rmtree(self.job/'checkpoints');shutil.rmtree(self.job/'final')
        history.delete_job(self.jid,confirm=True);self.assertFalse(self.job.exists())

if __name__=='__main__':unittest.main(verbosity=2)
