"""Managed runtime regression. Official-shaped metadata/archive fixtures, no remote binary.
Native stub self-check tests execute a harmless script only on POSIX hosts.
"""
import hashlib,io,json,os,subprocess,tarfile,tempfile,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from vision import llama_runtime as lr
from core.download_security import DownloadError


def release(rid=7,assets=None,pre=False):
    return dict(id=rid,tag_name='v0.4.1' if not pre else f'b{rid}',assets=assets or [],draft=False,prerelease=pre)

def asset(name,data=b'x'):
    return dict(id=1,name=name,size=len(data),digest='sha256:'+hashlib.sha256(data).hexdigest(),
                browser_download_url='https://github.com/ggml-org/llama.cpp/releases/download/v0.4.1/'+name)

class Reply:
    def __init__(self,data):self.data=data;self.headers={'Content-Length':str(len(data))}
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def chunks(self):yield self.data[:3];yield self.data[3:]
    def small(self,limit):
        if len(self.data)>limit:raise DownloadError('too large')
        return self.data

class ManagedRuntime108(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.home=Path(self.t.name)/'home';self.home.mkdir()
        self.manager=lr.LlamaRuntimeManager(self.home)
        self.log=[];self.manager._log=self.log.append
    def tearDown(self):self.t.cleanup()
    def metadata(self,values):
        self.urls=[]
        def get(url):
            self.urls.append(url);value=values.get(url,DownloadError('HTTP 404'))
            if isinstance(value,Exception):raise value
            return value
        self.manager.transport=SimpleNamespace(json=get)
    def test_first_page_prereleases_use_official_latest(self):
        r=release();self.metadata({lr.RELEASES_API:[release(i,pre=True) for i in range(1,51)],lr.LATEST_RELEASE_API:r})
        self.assertEqual(self.manager._fetch_releases(),[r]);self.assertEqual(self.urls,[lr.RELEASES_API,lr.LATEST_RELEASE_API])
    def test_stable_first_page_does_not_need_latest(self):
        r=release();self.metadata({lr.RELEASES_API:[release(8,pre=True),r]})
        self.assertEqual(self.manager._fetch_releases(),[r]);self.assertEqual(self.urls,[lr.RELEASES_API])
    def test_latest_can_work_when_listing_is_unreachable(self):
        r=release();self.metadata({lr.RELEASES_API:DownloadError('HTTP 403'),lr.LATEST_RELEASE_API:r})
        self.assertEqual(self.manager._fetch_releases(),[r])
    def test_no_draft_or_prerelease_is_relabelled_stable(self):
        for kind in ('draft','prerelease'):
            r=release();r[kind]=True;self.metadata({lr.RELEASES_API:[],lr.LATEST_RELEASE_API:r})
            with self.assertRaises(lr.LlamaRuntimeError) as caught:self.manager._fetch_releases()
            self.assertEqual(caught.exception.code,'llama_no_stable')
    def test_page_two_fallback_finds_stable(self):
        r=release(500);self.metadata({lr.RELEASES_API:[release(i,pre=True) for i in range(1,51)],
          lr.LATEST_RELEASE_API:DownloadError('HTTP 404'),lr.RELEASES_API+'&page=2':[r]})
        self.assertEqual(self.manager._fetch_releases(),[r]);self.assertEqual(len(self.urls),3)
    def test_pagination_is_bounded(self):
        pages={lr.RELEASES_API:[release(i,pre=True) for i in range(1,51)],lr.LATEST_RELEASE_API:release(999,pre=True)}
        for i in range(2,5):pages[lr.RELEASES_API+'&page='+str(i)]=[release(j+100*i,pre=True) for j in range(50)]
        self.metadata(pages)
        with self.assertRaises(lr.LlamaRuntimeError):self.manager._fetch_releases()
        self.assertEqual(len(self.urls),5);self.assertNotIn(lr.RELEASES_API+'&page=5',self.urls)
    def test_distinct_error_codes_preserve_technical_log(self):
        for message,code in [('HTTP 403','llama_api_limited'),('HTTP 429','llama_api_limited'),
                             ('DNS lookup failed','llama_network_error'),('Invalid JSON response','llama_metadata_invalid')]:
            self.metadata({lr.RELEASES_API:DownloadError(message),lr.LATEST_RELEASE_API:DownloadError(message)})
            with self.assertRaises(lr.LlamaRuntimeError) as caught:self.manager._fetch_releases()
            self.assertEqual(caught.exception.code,code);self.assertTrue(any(message in v for v in self.log))
    def test_saved_metadata_never_accepts_another_release_id(self):
        self.manager.root.mkdir(parents=True);self.manager.selection.write_text(json.dumps({'id':10,'tag_name':'v0.4.1'}))
        self.metadata({lr.RELEASES_API:[],lr.LATEST_RELEASE_API:None,lr.RELEASE_BY_ID.format(release_id=10):release(11)})
        with self.assertRaises(lr.LlamaRuntimeError):self.manager._fetch_releases()
    def test_cuda_companion_matches_platform_and_minor(self):
        names=['llama-v0.4.1-bin-win-cuda-12.4-x64.zip','cudart-llama-bin-win-cuda-12.4-x64.zip',
               'llama-v0.4.1-bin-ubuntu-cuda-12.4-x64.tar.gz','cudart-llama-bin-ubuntu-cuda-12.4-x64.tar.gz',
               'cudart-llama-bin-win-cuda-12.8-x64.zip']
        r=release(assets=[asset(n) for n in names])
        for system,part in [('windows','-win-'),('linux','-ubuntu-')]:
            with patch.object(self.manager,'_platform',return_value=system):
                backend,main,comp=self.manager._choose_backend(r,'cuda12')
                self.assertEqual(len(comp),1);self.assertIn(part,comp[0]['name']);self.assertIn('12.4',comp[0]['name'])
    def test_wrong_platform_companion_is_rejected(self):
        r=release(assets=[asset(n) for n in ['llama-v0.4.1-bin-win-cuda-12.4-x64.zip','cudart-llama-bin-ubuntu-cuda-12.4-x64.tar.gz']])
        with patch.object(self.manager,'_platform',return_value='windows'):
            with self.assertRaises(lr.LlamaRuntimeError):self.manager._choose_backend(r,'cuda12')
    def test_auto_nvidia_backend_order_and_explicit_choice(self):
        r=release(assets=[asset(n) for n in ['llama-v0.4.1-bin-win-cpu-x64.zip','llama-v0.4.1-bin-win-vulkan-x64.zip',
          'llama-v0.4.1-bin-win-cuda-12.4-x64.zip','cudart-llama-bin-win-cuda-12.4-x64.zip']])
        with patch.object(self.manager,'_platform',return_value='windows'),patch.object(self.manager,'_has_nvidia',return_value=True):
            self.assertEqual(self.manager._select([r])[1],'cuda12');self.assertEqual(self.manager._select([r],'cpu')[1],'cpu')
        with patch.object(self.manager,'_platform',return_value='windows'),patch.object(self.manager,'_has_nvidia',return_value=False):
            self.assertEqual(self.manager._select([r])[1],'vulkan')
    def test_nvidia_probe_must_work_not_just_exist(self):
        with patch.object(lr.shutil,'which',return_value='/system/nvidia-smi'),patch.object(lr.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
            self.assertFalse(self.manager._has_nvidia())
    def test_private_loader_env_does_not_change_parent(self):
        old=dict(os.environ);base={'PATH':'old','LD_LIBRARY_PATH':'previous'};original=base.copy()
        env=lr.runtime_environment(self.home,base)
        self.assertEqual(base,original);self.assertEqual(dict(os.environ),old)
        key='PATH' if os.name=='nt' else 'LD_LIBRARY_PATH'
        self.assertTrue(env[key].startswith(str(self.home)));self.assertTrue(env[key].endswith(original[key]))
    def test_self_check_gpu_requires_device_enumeration(self):
        with patch.object(lr.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='version 1.0\nAvailable devices:\n')) as run:
            with self.assertRaises(lr.LlamaRuntimeCompatibilityError):self.manager._self_check(self.home/'llama-server','cuda12')
            self.assertEqual(run.call_count,2)
        with patch.object(lr.subprocess,'run',side_effect=[SimpleNamespace(returncode=0,stdout='version'),SimpleNamespace(returncode=0,stdout='  CUDA0: NVIDIA test (123 MiB)')]):
            self.manager._self_check(self.home/'llama-server','cuda12')
    def test_vulkan_device_check(self):
        with patch.object(lr.subprocess,'run',side_effect=[SimpleNamespace(returncode=0,stdout='version'),SimpleNamespace(returncode=0,stdout='Available devices:\nVulkan0: Test device')]):
            self.manager._self_check(self.home/'llama-server','vulkan')
    def test_integrity_failure_never_falls_back(self):
        with patch.object(self.manager,'_fetch_releases',return_value=[release()]),patch.object(self.manager,'_select',return_value=(release(),'cuda12',{},[])) as select,patch.object(self.manager,'_install_choice',side_effect=lr.LlamaRuntimeError('SHA-256 mismatch','llama_integrity_error')) as install:
            with self.assertRaises(lr.LlamaRuntimeError) as caught:self.manager._install()
            self.assertEqual(caught.exception.code,'llama_integrity_error');self.assertEqual(install.call_count,1);self.assertEqual(select.call_count,1)
    def test_compatibility_fallback_order_is_explicitly_reported(self):
        r=release();seen=[]
        def choose(rs,pref='auto'):return r,'cuda12' if pref=='auto' else pref,{},[]
        def install(r,b,*args):
            seen.append(b)
            if b!='cpu':raise lr.LlamaRuntimeCompatibilityError('no device')
            return {'installed':True,'backend':'cpu'}
        with patch.object(self.manager,'_fetch_releases',return_value=[r]),patch.object(self.manager,'_select',side_effect=choose),patch.object(self.manager,'_install_choice',side_effect=install):
            self.assertEqual(self.manager._install()['backend'],'cpu')
        self.assertEqual(seen,['cuda12','vulkan','cpu']);self.assertEqual([x['backend'] for x in self.manager._fallbacks],['cuda12','vulkan'])
    def test_explicit_backend_does_not_silently_change(self):
        with patch.object(self.manager,'_fetch_releases',return_value=[release()]),patch.object(self.manager,'_select',return_value=(release(),'cuda12',{},[])),patch.object(self.manager,'_install_choice',side_effect=lr.LlamaRuntimeCompatibilityError('no GPU')) as call:
            with self.assertRaises(lr.LlamaRuntimeCompatibilityError):self.manager._install('cuda12')
            self.assertEqual(call.call_count,1)
    def test_archive_hash_checked_before_extraction_or_execution(self):
        bad=asset('a.zip',b'expected');self.manager.transport=SimpleNamespace(open=lambda u:Reply(b'changed!'))
        with self.assertRaises(lr.LlamaRuntimeError) as caught:self.manager._download_asset(bad,self.home/'a.zip')
        self.assertEqual(caught.exception.code,'llama_integrity_error')
    @unittest.skipIf(os.name=='nt','POSIX stub; Windows native executable acceptance is separate')
    def test_actual_process_self_check_and_transaction_fixture(self):
        # No remote code: this explicit local stub exercises extraction/chmod/exec/publish.
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('runtime/llama-server',b'#!/bin/sh\necho "test runtime version"\nexit 0\n')
        data=stream.getvalue();a=asset('llama-v0.4.1-bin-ubuntu-x64.zip',data);r=release(assets=[a])
        self.manager.transport=SimpleNamespace(json=lambda u:[r],open=lambda u:Reply(b'Permission is hereby granted (fixture license)' if u.endswith('/LICENSE') else data))
        # Keep test logs confined to the temporary test home, including the second copy.
        with patch.object(self.manager,'_system_log_root',return_value=self.home/'state'):
            result=self.manager.install('cpu')
        self.assertTrue(result['installed']);self.assertEqual(result['backend'],'cpu')
        self.assertTrue(lr.managed_executable(self.home).is_file());self.assertTrue(json.loads(self.manager.meta.read_text())['upstream_digest_verified'])
        self.assertEqual(list(self.manager.root.glob('.incoming-*')),[]);self.assertEqual(list(self.manager.root.glob('build.new-*')),[])
    def test_failed_compatibility_preserves_existing_runtime(self):
        old=self.manager.root/'build/bin';old.mkdir(parents=True);(old/lr.executable_name()).write_bytes(b'keep old')
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('runtime/'+lr.executable_name(),b'test exe')
        data=stream.getvalue();a=asset('llama-v0.4.1-bin-ubuntu-x64.zip',data);r=release(assets=[a])
        self.manager.transport=SimpleNamespace(json=lambda u:[r],open=lambda u:Reply(b'Permission is hereby granted (fixture)' if u.endswith('/LICENSE') else data))
        with patch.object(self.manager,'_system_log_root',return_value=self.home/'state'),patch.object(self.manager,'_platform',return_value='linux'),patch.object(self.manager,'_self_check',side_effect=lr.LlamaRuntimeCompatibilityError('not compatible')):
            with self.assertRaises(lr.LlamaRuntimeError):self.manager.install('cpu')
        self.assertEqual((old/lr.executable_name()).read_bytes(),b'keep old')
        self.assertEqual(self.manager.status()['state'],'failed');self.assertEqual(self.manager.status()['error_code'],'llama_backend_unavailable')

class TarLibraries108(unittest.TestCase):
    def setUp(self):self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
    def tearDown(self):self.t.cleanup()
    def archive(self,links,regular=True,hard=False):
        a=self.root/'runtime.tar.gz'
        with tarfile.open(a,'w:gz') as t:
            if regular:
                f=tarfile.TarInfo('runtime/libggml.so.1.2');f.size=6;t.addfile(f,io.BytesIO(b'abcdef'))
            for name,target in links:
                m=tarfile.TarInfo(name);m.type=tarfile.LNKTYPE if hard else tarfile.SYMTYPE;m.linkname=target;t.addfile(m)
        return a
    def test_safe_same_directory_library_chain_is_copied_not_linked(self):
        a=self.archive([('runtime/libggml.so','libggml.so.1'),('runtime/libggml.so.1','libggml.so.1.2')]);out=self.root/'out';lr._extract(a,out)
        for name in ('libggml.so','libggml.so.1','libggml.so.1.2'):
            p=out/'runtime'/name;self.assertFalse(p.is_symlink());self.assertEqual(p.read_bytes(),b'abcdef')
    def test_library_links_cannot_escape_directory(self):
        for i,target in enumerate(('../libggml.so.1.2','/libggml.so.1.2','sub/libggml.so.1.2',r'..\libggml.so.1.2')):
            with self.assertRaises(lr.LlamaRuntimeError):lr._extract(self.archive([('runtime/libggml.so',target)]),self.root/f'out{i}')
    def test_nonlibrary_links_still_rejected(self):
        with self.assertRaises(lr.LlamaRuntimeError):lr._extract(self.archive([('runtime/llama-server','libggml.so.1.2')]),self.root/'out')
    def test_hardlinks_still_rejected(self):
        with self.assertRaises(lr.LlamaRuntimeError):lr._extract(self.archive([('runtime/libggml.so','libggml.so.1.2')],hard=True),self.root/'out')
    def test_library_link_cycle_rejected(self):
        with self.assertRaises(lr.LlamaRuntimeError):lr._extract(self.archive([('runtime/libggml.so','libggml.so.1'),('runtime/libggml.so.1','libggml.so')]),self.root/'out')
    def test_library_link_missing_target_rejected(self):
        with self.assertRaises(lr.LlamaRuntimeError):lr._extract(self.archive([('runtime/libggml.so','libggml.so.9')]),self.root/'out')
    def test_materialized_libraries_count_towards_extraction_limit(self):
        a=self.archive([('runtime/libggml.so','libggml.so.1.2')])
        with patch.object(lr,'MAX_EXTRACTED',10):
            with self.assertRaises(lr.LlamaRuntimeError):lr._extract(a,self.root/'out')
    def test_duplicate_path_rejected(self):
        a=self.archive([('runtime/libggml.so.1.2','libggml.so.1.2')])
        with self.assertRaises(lr.LlamaRuntimeError):lr._extract(a,self.root/'out')

class Localization108(unittest.TestCase):
    def test_runtime_translations_cover_all_twelve_languages(self):
        import re
        root=Path(__file__).resolve().parents[1];s=(root/'static/vision-runtime-locale.js').read_text()
        entries=json.JSONDecoder().raw_decode(s[s.index('const entries=')+len('const entries='):])[0]
        langs=set('en it es fr de pt ru zh ja ko tr ar'.split())
        self.assertGreaterEqual(len(entries),20)
        for entry in entries:
            self.assertEqual(set(entry['text']),langs)
            self.assertTrue(all(isinstance(v,str) and v.strip() for v in entry['text'].values()))
    def test_linux_setup_command_is_localized_not_windows_only(self):
        root=Path(__file__).resolve().parents[1];s=(root/'static/first-run-locale.js').read_text()
        self.assertIn('creator-sdxl setup-code',s);self.assertIn("setup_code_command",(root/'templates/first_run.html').read_text())
    def test_identity_history_image_urls_are_stable(self):
        root=Path(__file__).resolve().parents[1];s=(root/'static/app.js').read_text();s=s[s.index('function renderIdentityJobs'):s.index('function applyIdentityJobSettings')]
        self.assertNotIn('Date.now()',s);self.assertIn('ZetalvxIdentityDOM.rows',s)

if __name__=='__main__':unittest.main()
