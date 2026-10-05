import hashlib, tempfile, threading, unittest
from pathlib import Path
from vision.link_imports import VisionLinkImports, _allowed_repo_file, _safe_rel

class FakeResponse:
    def __init__(self,data,headers=None):
        self.data=data;self.headers=headers or {'Content-Length':str(len(data))}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def chunks(self,size=1024*1024):
        for i in range(0,len(self.data),size):yield self.data[i:i+size]

class FakeTransport:
    def __init__(self):
        self.files={
            'config.json':b'{"model_type":"qwen2_vl","vision_config":{}}',
            'model.safetensors':b'SAFE-DATA',
            'tokenizer.json':b'{}',
            'preprocessor_config.json':b'{}',
            'modeling_custom.py':b'print("must never download")',
            'vision.gguf':b'GGUF'+b'0'*64,
        }
    def json(self,url,token_override=None):
        siblings=[]
        for name,data in self.files.items():
            siblings.append({'rfilename':name,'lfs':{'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}})
        return {'sha':'a'*40,'siblings':siblings,'cardData':{'license':'apache-2.0'}}
    def open(self,url,**kwargs):
        from urllib.parse import unquote,urlsplit
        name=unquote(urlsplit(url).path).split('/')[-1]
        data=self.files[name]
        return FakeResponse(data)

class VisionLinkImport38(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)/'CreatorStudioSDXL';self.home.mkdir()
        self.imp=VisionLinkImports(self.home,start_worker=False);self.imp.transport=FakeTransport()
    def tearDown(self):self.tmp.cleanup()
    def test_safe_repo_filter_never_downloads_python(self):
        self.assertTrue(_allowed_repo_file('model.safetensors'))
        self.assertTrue(_allowed_repo_file('config.json'))
        self.assertFalse(_allowed_repo_file('modeling_custom.py'))
        with self.assertRaises(Exception):_safe_rel('../escape.json')
    def test_transformers_repo_download_is_data_only(self):
        plan=self.imp._plan_repo('https://huggingface.co/org/model')
        names={x['relative'] for x in plan['files']}
        self.assertIn('config.json',names);self.assertIn('model.safetensors',names);self.assertNotIn('modeling_custom.py',names)
        jid='1'*32;self.imp.events[jid]=threading.Event();self.imp.jobs[jid]={'id':jid,'status':'queued','created_at':0,'downloaded_bytes':0,'total_bytes':plan['size'],'file_count':len(plan['files']),'completed_files':0,'error':'','path':''}
        self.imp._run(jid,plan);job=self.imp.get(jid);root=Path(job['path'])
        self.assertEqual(job['status'],'complete');self.assertTrue((root/'config.json').is_file());self.assertTrue((root/'model.safetensors').is_file());self.assertFalse((root/'modeling_custom.py').exists())
    def test_hf_gguf_download_validates_magic(self):
        plan=self.imp._plan_gguf('https://huggingface.co/org/model/blob/main/vision.gguf','gguf_path')
        jid='2'*32;self.imp.events[jid]=threading.Event();self.imp.jobs[jid]={'id':jid,'status':'queued','created_at':0,'downloaded_bytes':0,'total_bytes':plan['size'],'file_count':1,'completed_files':0,'error':'','path':''}
        self.imp._run(jid,plan);job=self.imp.get(jid)
        self.assertEqual(job['status'],'complete');self.assertEqual(Path(job['path']).read_bytes()[:4],b'GGUF')

if __name__=='__main__':unittest.main()
