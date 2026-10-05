"""Real Flask integration tests. They skip only when Flask is unavailable; no GPU."""
import importlib.util,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
HAS=importlib.util.find_spec('flask') is not None
@unittest.skipUnless(HAS,'Flask unavailable: run with installed runtime/app')
class WorkspaceHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();os.environ['SDXL_STUDIO_HOME']=cls.tmp.name;os.environ['SDXL_STUDIO_NO_BACKGROUND']='1'
        import app
        from werkzeug.security import generate_password_hash
        if not Path(app.DATA_ROOT).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise unittest.SkipTest('Temporary app home required; refusing to write production data')
        cls.m=app;app.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
        app.atomic_json(app.AUTH_CONFIG_PATH,{'enabled':True,'username':'C','password_hash':generate_password_hash('test-password-123'),'session_hours':1})
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.c=self.m.app.test_client();self.c.post('/login',data={'username':'C','password':'test-password-123'})
        r=self.c.get('/api/vision/session');self.h={'X-CSRF-Token':r.json['csrf']}
    def create(self):
        r=self.c.post('/api/training/datasets',json={'name':'HTTP dataset','trigger':'itapigna','trigger_position':'context'},headers=self.h)
        self.assertEqual(r.status_code,200,r.data);return r.json['dataset']
    def upload(self,d):
        from PIL import Image
        b=io.BytesIO();Image.new('RGB',(16,24)).save(b,'PNG');b.seek(0)
        r=self.c.post('/api/training/datasets/'+d['id']+'/upload',data={'files':[(b,'one.png'),(io.BytesIO(b'a portrait of itapigna'),'one.txt')]},headers=self.h)
        self.assertEqual(r.status_code,200,r.data);return r.json['dataset']
    def test_authentication_required(self):
        c=self.m.app.test_client();self.assertEqual(c.post('/api/training/datasets',json={'name':'x'}).status_code,401)
    def test_csrf_is_required(self):
        r=self.c.post('/api/training/datasets',json={'name':'x'});self.assertEqual(r.status_code,403);self.assertEqual(r.json['code'],'csrf_failed')
    def test_multipart_and_thumbnail(self):
        d=self.upload(self.create());it=d['items'][0]
        r=self.c.get(f"/api/training/datasets/{d['id']}/items/{it['id']}/thumbnail")
        self.assertEqual(r.status_code,200);self.assertEqual(r.mimetype,'image/jpeg')
        self.assertEqual(d['items'][0]['caption'],'a portrait of itapigna')
    def test_optimistic_caption_conflict(self):
        d=self.upload(self.create());iid=d['items'][0]['id']
        r=self.c.put('/api/training/datasets/'+d['id'],headers=self.h,json={'captions':{iid:'replacement'},'expected_captions':{iid:'stale'}})
        self.assertEqual(r.status_code,409);self.assertEqual(r.json['code'],'dataset_conflict')
    def test_handoff_preserves_dataset_and_no_job(self):
        d=self.upload(self.create());r=self.c.post('/api/training/datasets/'+d['id']+'/use',json={},headers=self.h)
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['dataset'],d)
        self.assertNotIn('job',r.json)
    def test_empty_handoff_rejected(self):
        d=self.create();r=self.c.post('/api/training/datasets/'+d['id']+'/use',json={},headers=self.h);self.assertEqual(r.status_code,400)
    def test_removal_requires_csrf(self):
        d=self.create();r=self.c.delete('/api/training/datasets/'+d['id']);self.assertEqual(r.status_code,403)
        r=self.c.delete('/api/training/datasets/'+d['id'],headers=self.h,json={});self.assertEqual(r.status_code,200)
    def test_reuse_model_selection_persists(self):
        d=self.create();r=self.c.put('/api/training/datasets/'+d['id'],json={'vision_model_id':'a'*32},headers=self.h)
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['dataset']['vision_model_id'],'a'*32)
if __name__=='__main__':unittest.main(verbosity=2)
