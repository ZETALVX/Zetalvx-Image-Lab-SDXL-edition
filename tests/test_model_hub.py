"""Offline model-import tests: real parser/queue/storage, simulated HTTPS endpoints.
No tokens, model downloads, inference, or production data are used.
"""
import hashlib, json, os, socket, struct, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from core.download_security import (DownloadError, TokenStore, PublicHTTPS,
                                    safe_name, public_addresses, clean_user_url)
from core.model_downloads import ModelDownloads, classify_safetensors, normalize_link
from core.model_policy import catalog, external_reason, SDXL_REPO, SDXL_FILE, SDXL_SHA256


def sample(kind='lora', family='sdxl'):
    keys={'lora':['lora_te2_encoder.lora_down.weight'],
          'checkpoint':['model.diffusion_model.input_blocks.0.weight'],
          'vae':['encoder.weight','quant_conv.weight'],
          'control':['control_model.weight'],'unknown':['weight']}
    header={};offset=0
    for key in keys[kind]:
        header[key]={'dtype':'F32','shape':[1],'data_offsets':[offset,offset+4]};offset+=4
    if family:header['__metadata__']={'ss_base_model_version':family}
    raw=json.dumps(header,separators=(',',':')).encode()
    return struct.pack('<Q',len(raw))+raw+b'\x00'*offset

class FakeResponse:
    def __init__(self,data,headers=None):
        self.data=data;self.headers={'Content-Type':'application/octet-stream','Content-Length':str(len(data)),**(headers or {})}
    def chunks(self,*_):
        for i in range(0,len(self.data),13):yield self.data[i:i+13]
    def __enter__(self):return self
    def __exit__(self,*_):pass

class FakeTransport:
    def __init__(self,data):self.data=data;self.headers={};self.metadata={};self.calls=[]
    def open(self,url,**kw):self.calls.append(url);return FakeResponse(self.data,self.headers)
    def json(self,url,**kw):self.calls.append(url);return self.metadata

class URLTests(unittest.TestCase):
    def test_hf_blob_normalized(self):
        p=normalize_link('https://huggingface.co/me/repo/blob/main/sub/my.safetensors?download=true')
        self.assertEqual(p['url'],'https://huggingface.co/me/repo/resolve/main/sub/my.safetensors')
    def test_hf_revision_retained(self):self.assertEqual(normalize_link('https://huggingface.co/a/b/resolve/abc/x.safetensors')['revision'],'abc')
    def test_hf_repo_page_rejected(self):
        with self.assertRaises(DownloadError):normalize_link('https://huggingface.co/a/b')
    def test_civitai_version_page(self):self.assertEqual(normalize_link('https://civitai.com/models/12/foo?modelVersionId=42')['version'],'42')
    def test_civitai_download(self):self.assertEqual(normalize_link('https://civitai.com/api/download/models/42?format=SafeTensor')['version'],'42')
    def test_civitai_without_version_rejected(self):
        with self.assertRaises(DownloadError):normalize_link('https://civitai.com/models/12')
    def test_tokens_rejected_in_query(self):
        for key in ('token','api_key','access_token','authorization'):
            with self.subTest(key=key),self.assertRaises(DownloadError):clean_user_url(f'https://civitai.com/api/download/models/1?{key}=SECRET')
    def test_only_https(self):
        for url in ('http://example.org/x','file:///tmp/a','https://user:pw@example.org/a','https://example.org:8080/x','https://example.org/a b'):
            with self.subTest(url=url),self.assertRaises(DownloadError):normalize_link(url)
    def test_filename_traversal_stripped(self):self.assertEqual(safe_name('../../evil.safetensors'),'evil.safetensors')
    def test_disallowed_file_types(self):
        for name in ('a.bin','a.zip','a.ckpt','a.onnx','a.py','a.safetensors.py'):
            with self.subTest(name=name),self.assertRaises(DownloadError):safe_name(name)
    def test_private_dns_rejected(self):
        for ip in ('127.0.0.1','192.168.1.239','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1'):
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]),self.subTest(ip=ip),self.assertRaises(DownloadError):public_addresses('example.org')
    def test_mixed_dns_rejected(self):
        result=[(2,1,6,'',(x,443)) for x in ['1.1.1.1','127.0.0.1']]
        with patch('socket.getaddrinfo',return_value=result),self.assertRaises(DownloadError):public_addresses('example.org')
    def test_identity_policy_not_auto(self):
        self.assertTrue(all(x['mode']=='external' for x in catalog() if x['id'] in ('instantid','antelopev2','buffalo_l','inswapper')))
        for url in ('https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/x.safetensors','https://example.org/inswapper_128.onnx'):
            self.assertTrue(external_reason(url))
            with self.assertRaises(DownloadError):normalize_link(url)

class TokenTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=TokenStore(Path(self.tmp.name)/'secrets')
    def tearDown(self):self.tmp.cleanup()
    def test_store_private_not_returned(self):
        token='hf_private_example_notreal';self.store.put('huggingface',token,'Tester')
        self.assertEqual(self.store.get('huggingface'),token)
        self.assertNotIn(token,json.dumps(self.store.public()))
        self.assertEqual(self.store.root.stat().st_mode&0o777,0o700)
        self.assertEqual((self.store.root/'huggingface.json').stat().st_mode&0o777,0o600)
    def test_delete(self):self.store.put('civitai','FAKE_KEY_1234');self.store.delete('civitai');self.assertEqual(self.store.get('civitai'),'')
    def test_whitespace_rejected(self):
        with self.assertRaises(DownloadError):self.store.put('huggingface','hf_bad token')
    def test_symlink_secrets_rejected(self):
        dest=Path(self.tmp.name)/'elsewhere';dest.mkdir();self.store.root.symlink_to(dest,target_is_directory=True)
        with self.assertRaises(DownloadError):self.store.put('huggingface','hf_badsecret')
    def test_cross_origin_redirect_strips_token_permanently(self):
        self.store.put('huggingface','hf_DO_NOT_FORWARD')
        responses=[(302,{'Location':'https://cdn.example.org/model'}),(302,{'Location':'https://huggingface.co/final'}),(200,{})];calls=[]
        class Pool:
            def __init__(self,address,port,**kw):self.host=kw['server_hostname'];self.address=address
            def urlopen(self,*args,**kw):
                calls.append((self.address,self.host,kw['headers']))
                status,headers=responses.pop(0)
                class Raw:
                    def close(self):pass
                r=Raw();r.status=status;r.headers=headers;return r
            def close(self):pass
        with patch('core.download_security.public_addresses',return_value=['1.1.1.1']),patch('urllib3.HTTPSConnectionPool',Pool):
            PublicHTTPS(self.store).open('https://huggingface.co/a').close()
        self.assertEqual(calls[0][2]['Authorization'],'Bearer hf_DO_NOT_FORWARD')
        self.assertNotIn('Authorization',calls[1][2]);self.assertNotIn('Authorization',calls[2][2]);self.assertEqual(calls[0][0],'1.1.1.1')
    def test_private_redirect_rejected(self):
        class Pool:
            def __init__(self,*_,**kw):pass
            def urlopen(self,*_,**kw):
                class Raw:
                    status=302;headers={'Location':'https://127.0.0.1/private'}
                    def close(self):pass
                return Raw()
            def close(self):pass
        with patch('core.download_security.public_addresses',side_effect=[['1.1.1.1'],DownloadError('private')]),patch('urllib3.HTTPSConnectionPool',Pool),self.assertRaises(DownloadError):PublicHTTPS(self.store).open('https://example.org/a')

class HeaderTests(unittest.TestCase):
    def inspect(self,data):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model';p.write_bytes(data);return classify_safetensors(p)
    def test_sdxl_lora(self):self.assertEqual(self.inspect(sample())['kind'],'lora')
    def test_sdxl_checkpoint(self):self.assertEqual(self.inspect(sample('checkpoint'))['family'],'sdxl')
    def test_vae_requires_confirmation(self):self.assertEqual(self.inspect(sample('vae'))['family'],'unknown')
    def test_other_family(self):self.assertEqual(self.inspect(sample('lora','flux'))['family'],'other')
    def test_controlnet_not_checkpoint(self):self.assertEqual(self.inspect(sample('control'))['kind'],'unsupported')
    def test_unknown(self):self.assertEqual(self.inspect(sample('unknown',''))['family'],'unknown')
    def test_html_or_truncation_rejected(self):
        for data in (b'<html>login please</html>',b'PK\x03\x04',sample()[:-2]):
            with self.subTest(length=len(data)),self.assertRaises(DownloadError):self.inspect(data)
    def test_bad_offsets_rejected(self):
        raw=json.dumps({'a':{'dtype':'F32','shape':[1],'data_offsets':[1,5]}}).encode()
        with self.assertRaises(DownloadError):self.inspect(struct.pack('<Q',len(raw))+raw+b'\0'*5)
    def test_duplicate_keys_rejected(self):
        raw=b'{"a":{},"a":{}}'
        with self.assertRaises(DownloadError):self.inspect(struct.pack('<Q',len(raw))+raw+b'1234')

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'models';self.transport=FakeTransport(sample());self.installed=[]
        self.dl=ModelDownloads(self.root,Path(self.tmp.name)/'jobs',self.transport,lambda k,p:self.installed.append((k,p)),start_worker=False)
    def tearDown(self):self.tmp.cleanup()
    def preview(self,kind='auto'):return self.dl.inspect('https://example.org/test.safetensors',kind)
    def run_one(self,preview=None):
        j=self.dl.start((preview or self.preview())['id'],True);jid,p=self.dl.pending.get();self.dl._run(jid,p);return self.dl.jobs[jid]
    def test_requires_terms_confirmation(self):
        p=self.preview()
        with self.assertRaises(DownloadError):self.dl.start(p['id'],False)
    def test_install_and_provenance(self):
        j=self.run_one();self.assertEqual(j['status'],'complete');self.assertEqual(j['kind'],'lora')
        p=Path(j['path']);self.assertEqual(p.parent,self.root/'loras/SDXL');self.assertEqual(p.read_bytes(),sample())
        self.assertTrue(p.with_suffix('.source.json').is_file());self.assertEqual(j['sha256'],hashlib.sha256(sample()).hexdigest())
    def test_collision_never_overwrites(self):
        first=self.run_one();Path(first['path']).write_bytes(b'leave me intact');second=self.run_one()
        self.assertNotEqual(first['path'],second['path']);self.assertEqual(Path(first['path']).read_bytes(),b'leave me intact')
    def test_wrong_kind_fails(self):j=self.run_one(self.preview('checkpoint'));self.assertEqual(j['status'],'failed');self.assertFalse(self.installed)
    def test_mismatched_hash_fails(self):
        p=self.preview();self.dl.plans[p['id']]['sha256']='0'*64;j=self.run_one(p)
        self.assertEqual(j['status'],'failed');self.assertIn('SHA-256',j['error']);self.assertFalse(list(self.dl.incoming.glob('*.part')))
    def test_unknown_waits_and_installs_only_after_confirmation(self):
        self.transport.data=sample('unknown','');j=self.run_one();self.assertEqual(j['status'],'needs_confirmation')
        with self.assertRaises(DownloadError):self.dl.finalize(j['id'],'vae',False)
        j=self.dl.finalize(j['id'],'vae',True);self.assertEqual(j['status'],'complete')
    def test_cancel_queued(self):
        p=self.preview();j=self.dl.start(p['id'],True);self.dl.cancel(j['id']);jid,plan=self.dl.pending.get();self.dl._run(jid,plan)
        self.assertEqual(self.dl.jobs[jid]['status'],'cancelled');self.assertFalse(self.installed)
    def test_cancel_unknown_cleans_part(self):
        self.transport.data=sample('unknown','');j=self.run_one();self.dl.cancel(j['id'])
        self.assertFalse(list(self.dl.incoming.glob('*.part')));self.assertEqual(self.dl.jobs[j['id']]['status'],'cancelled')
    def test_restart_does_not_resume_secret_urls(self):
        p=self.preview();j=self.dl.start(p['id'],True);self.dl.cancel(j['id'])
        new=ModelDownloads(self.root,self.dl.state_root,self.transport,start_worker=False)
        self.assertEqual(new.jobs[j['id']]['status'],'interrupted')
        self.assertNotIn('url',new.jobs[j['id']])
    def test_reject_downloaded_html(self):
        self.transport.data=b'<html>access denied</html>'
        self.assertEqual(self.run_one()['status'],'failed')
    def test_non_sdxl_rejected(self):
        self.transport.data=sample('lora','qwen-image');self.assertEqual(self.run_one()['status'],'failed')
    def test_destination_symlink_rejected(self):
        elsewhere=Path(self.tmp.name)/'elsewhere';elsewhere.mkdir();(self.root/'loras').mkdir();(self.root/'loras/SDXL').symlink_to(elsewhere,target_is_directory=True)
        j=self.run_one();self.assertEqual(j['status'],'failed');self.assertFalse(list(elsewhere.iterdir()))
    def test_hf_metadata_pins_revision_and_hash(self):
        self.transport.metadata={'sha':'a'*40,'cardData':{'license':'example-license'},'siblings':[{'rfilename':'model.safetensors','lfs':{'size':123,'sha256':'b'*64}}]}
        p=self.dl.inspect('https://huggingface.co/a/b/blob/main/model.safetensors')
        self.assertIn('a'*40,self.dl.plans[p['id']]['url']);self.assertEqual(p['sha256'],'b'*64);self.assertIn('metadata',p['license'])
    def test_civitai_ambiguous_files_rejected(self):
        self.transport.metadata={'baseModel':'SDXL 1.0','files':[{'name':'a.safetensors'},{'name':'b.safetensors'}]}
        with self.assertRaises(DownloadError):self.dl.inspect('https://civitai.com/api/download/models/12')
    def test_civitai_metadata_resolves_file(self):
        self.transport.metadata={'baseModel':'SDXL 1.0','modelId':7,'model':{'type':'LORA'},'files':[{'name':'a.safetensors','sizeKB':1,'downloadUrl':'https://civitai.com/api/download/models/12?format=SafeTensor','hashes':{'SHA256':'c'*64},'metadata':{'format':'SafeTensor'}}]}
        p=self.dl.inspect('https://civitai.com/api/download/models/12?format=SafeTensor');self.assertEqual(p['kind_hint'],'lora');self.assertEqual(p['sha256'],'c'*64)
    def test_civitai_non_sdxl_rejected(self):
        self.transport.metadata={'baseModel':'SD 1.5','files':[{'name':'a.safetensors','downloadUrl':'https://civitai.com/api/download/models/12'}]}
        with self.assertRaises(DownloadError):self.dl.inspect('https://civitai.com/api/download/models/12')
    def test_official_sdxl_hash_not_source_override(self):
        self.transport.metadata={};p=self.dl.inspect(f'https://huggingface.co/{SDXL_REPO}/blob/main/{SDXL_FILE}',builtin=True)
        self.assertEqual(p['sha256'],SDXL_SHA256)

if __name__=='__main__':unittest.main(verbosity=2)
