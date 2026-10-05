"""New Flask dataset/video routes; run with runtime/app. No GPU required."""
import importlib.util,io,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
HAS=importlib.util.find_spec('flask') is not None
@unittest.skipUnless(HAS,'Flask not installed: run from installed SDXL runtime/app')
class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();os.environ['SDXL_STUDIO_HOME']=cls.tmp.name;os.environ['SDXL_STUDIO_NO_BACKGROUND']='1'
        import app
        from werkzeug.security import generate_password_hash
        cls.mod=app;app.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
        app.atomic_json(app.AUTH_CONFIG_PATH,{'enabled':True,'username':'C','password_hash':generate_password_hash('test-password-123'),'session_hours':1})
        app.image_worker_health=lambda:{'ok':False};app.training_worker_health=lambda:{'ok':False};app.identity_worker_health=lambda:{'online':False}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):self.client=self.mod.app.test_client()
    def login(self):
        self.client.post('/login',data={'username':'C','password':'test-password-123'})
        self.headers={'X-CSRF-Token':self.client.get('/api/vision/session').json['csrf']}
    def test_private_routes(self):
        for route in ['/api/training/datasets/import-zip','/api/image-tools/video-picker']:self.assertEqual(self.client.post(route).status_code,401)
    def test_caption_roundtrip(self):
        self.login();from PIL import Image
        im=io.BytesIO();Image.new('RGB',(12,16)).save(im,'PNG');z=io.BytesIO();cap='a picture of itapigna, preserved\n'
        with zipfile.ZipFile(z,'w') as f:f.writestr('one.png',im.getvalue());f.writestr('one.txt',cap)
        z.seek(0);r=self.client.post('/api/training/datasets/import-zip',data={'file':(z,'data.zip')},headers=self.headers);self.assertEqual(r.status_code,200);did=r.json['dataset']['id'];self.assertEqual(r.json['dataset']['items'][0]['caption'],cap)
        r=self.client.get('/api/training/datasets/'+did+'/export');self.assertEqual(r.status_code,200)
        with zipfile.ZipFile(io.BytesIO(r.data)) as f:self.assertEqual(f.read('images/00001.txt').decode(),cap)
        self.assertEqual(self.client.get('/api/training/datasets/'+did+'/caption-check').json['report']['images'],1)
    def test_picker_validation(self):
        self.login();self.assertEqual(self.client.post('/api/image-tools/video-picker').status_code,400)
        self.assertEqual(self.client.post('/api/image-tools/video-picker',headers={'Origin':'https://other.example'}).status_code,403)
if __name__=='__main__':unittest.main(verbosity=2)
