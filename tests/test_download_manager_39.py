import hashlib, tempfile, threading, unittest
from pathlib import Path

from core.download_manager import COORDINATOR, DownloadCoordinator, normalize_job
from core.model_downloads import ModelDownloads
from tests.test_model_hub import FakeTransport as ModelTransport, sample
from vision.link_imports import VisionLinkImports
from tests.test_vision_link_imports_38 import FakeTransport as VisionTransport

class DownloadManager39Tests(unittest.TestCase):
    def test_model_download_history_is_persistent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'models';jobs=Path(td)/'jobs';dl=ModelDownloads(root,jobs,ModelTransport(sample()),start_worker=False)
            preview=dl.inspect('https://example.org/test.safetensors')
            job=dl.start(preview['id'],True);jid,plan=dl.pending.get();dl._run(jid,plan);job=dl.get(jid)
            states=[x.get('status') for x in job.get('history',[])]
            self.assertEqual(job['status'],'complete');self.assertIn('queued',states);self.assertIn('downloading',states);self.assertIn('complete',states)
            self.assertTrue(job.get('started_at'))
            restored=ModelDownloads(root,jobs,ModelTransport(sample()),start_worker=False).get(jid)
            self.assertEqual(restored['status'],'complete');self.assertEqual(restored['history'],job['history'])

    def test_vision_download_history_and_manager_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)/'CreatorStudioSDXL';home.mkdir();imp=VisionLinkImports(home,start_worker=False);imp.transport=VisionTransport()
            plan=imp._plan_gguf('https://huggingface.co/org/model/blob/main/vision.gguf','gguf_path')
            now=1.0;jid='3'*32;imp.events[jid]=threading.Event();imp.jobs[jid]={'id':jid,'kind':'gguf','role':'gguf_path','status':'queued','created_at':now,'updated_at':now,'source':plan['source'],'downloaded_bytes':0,'total_bytes':plan['size'],'file_count':1,'completed_files':0,'error':'','path':'','history':[{'at':now,'status':'queued','message':''}]}
            imp._run(jid,plan);job=imp.get(jid);states=[x.get('status') for x in job['history']]
            self.assertEqual(job['status'],'complete');self.assertIn('downloading',states);self.assertIn('installing',states);self.assertIn('complete',states)
            n=normalize_job('vision',job);self.assertEqual(n['source'],'vision');self.assertEqual(n['status'],'complete');self.assertEqual(n['downloaded_bytes'],n['total_bytes']);self.assertTrue(n['history'])


    def test_vision_cancel_cleans_temporary_and_records_cancelled(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)/'CreatorStudioSDXL';home.mkdir();imp=VisionLinkImports(home,start_worker=False);imp.transport=VisionTransport()
            plan=imp._plan_gguf('https://huggingface.co/org/model/blob/main/vision.gguf','gguf_path')
            job=imp.start('gguf','https://huggingface.co/org/model/blob/main/vision.gguf','gguf_path',True)
            imp.cancel(job['id']);jid,queued=imp.pending.get();imp._loop_once = None
            try:imp._run(jid,queued)
            except Exception as e:
                from core.download_security import Cancelled
                if isinstance(e,Cancelled):imp._save(jid,status='cancelled',error=str(e))
                else:raise
            final=imp.get(jid);self.assertEqual(final['status'],'cancelled');self.assertFalse(list(imp.incoming.glob(jid+'*')))

    def test_template_has_persistent_download_views(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'templates/index.html').read_text(encoding='utf-8')
        js=(root/'static/download-manager.js').read_text(encoding='utf-8')
        self.assertIn('data-hub-tab="downloads"',html)
        self.assertIn('id="downloadManagerList"',html)
        self.assertIn('id="jobsDownloadPanel"',html)
        self.assertIn('/api/download-manager',js)
        self.assertIn('data-download-cancel',js)
        self.assertIn('Log and verification',js)

    def test_shared_coordinator_limits_parallel_downloads(self):
        gate=DownloadCoordinator();gate.set_limit(1);release=threading.Event();entered=[]
        def first():
            self.assertTrue(gate.acquire('a'));entered.append('a');release.wait(2);gate.release('a')
        def second():
            self.assertTrue(gate.acquire('b'));entered.append('b');gate.release('b')
        a=threading.Thread(target=first);b=threading.Thread(target=second);a.start();
        import time;time.sleep(.08);b.start();time.sleep(.08);self.assertEqual(entered,['a']);release.set();a.join(2);b.join(2);self.assertEqual(entered,['a','b'])
        gate.set_limit(3);self.assertEqual(gate.snapshot()['limit'],3)

    def test_template_exposes_queue_and_parallel_setting(self):
        root=Path(__file__).resolve().parents[1];html=(root/'templates/index.html').read_text(encoding='utf-8');js=(root/'static/download-manager.js').read_text(encoding='utf-8')
        self.assertIn('id="downloadConcurrency"',html);self.assertIn('Download queue',html);self.assertIn('/api/download-manager/settings',js);self.assertIn('queue_position',js)

    def test_server_browsers_start_from_app_managed_paths(self):
        root=Path(__file__).resolve().parents[1]
        app=(root/'app.py').read_text(encoding='utf-8');vision=(root/'static/vision-ui.js').read_text(encoding='utf-8')
        self.assertIn("request.args.get('path') or MODELS_ROOT",app)
        for token in ('__APP_VISION_GGUF__','__APP_VISION_TRANSFORMERS__','__APP_VISION_RUNTIME__','__APP_LLAMA_RUNTIME__'):
            self.assertIn(token,vision)

if __name__=='__main__':unittest.main()
