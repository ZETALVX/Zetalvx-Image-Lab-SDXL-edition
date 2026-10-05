"""Regression of upstream stable -> nightly-tag.txt -> exact binary release.

The shape is documented by ggml-org/ggml discussion #1579 (2026-08/09).
Tags, IDs, archives and digests here are SYNTHETIC fixtures, not a live GitHub
snapshot or an upstream executable. POSIX tests execute an explicit local stub.
No GPU, model weights, network access or Windows emulation is required.
"""
import copy
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from vision import llama_runtime as lr
from core.download_security import DownloadError

STABLE='v0.5.0'
BINARY='b12001'  # synthetic, intentionally not a claim about the live mapping
OWNER='https://github.com/ggml-org/llama.cpp'

def asset(tag,name,data=b'fixture',aid=1):
    return {'id':aid,'name':name,'size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest(),
            'browser_download_url':OWNER+'/releases/download/'+tag+'/'+name}

def release(tag=STABLE,assets=None,pre=False,rid=50):
    return dict(id=rid,tag_name=tag,draft=False,prerelease=pre,assets=assets or [],html_url=OWNER+'/releases/tag/'+tag)

class Reply:
    def __init__(self,data):self.data=data;self.headers={'Content-Length':str(len(data))}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def chunks(self):
        for i in range(0,len(self.data),37):yield self.data[i:i+37]
    def small(self,limit):
        if len(self.data)>limit:raise DownloadError('Response exceeds limit')
        return self.data

class FixtureTransport:
    def __init__(self,parent,build,raw,bodies=None):
        self.parent=parent;self.build=build;self.raw=raw;self.bodies=bodies or {};self.requests=[]
        self.json_overrides={};self.open_overrides={}
    def json(self,url):
        self.requests.append(('json',url))
        if url in self.json_overrides:out=self.json_overrides[url]
        elif url==lr.RELEASES_API:out=[release('b13000',pre=True,rid=13000),self.parent]
        elif url==lr.LATEST_RELEASE_API:out=self.parent
        elif url==lr.RELEASE_BY_TAG.format(tag=BINARY):out=self.build
        else:raise DownloadError('HTTP 404 fixture '+url)
        if isinstance(out,Exception):raise out
        return copy.deepcopy(out)
    def open(self,url):
        self.requests.append(('open',url))
        if url in self.open_overrides:out=self.open_overrides[url]
        elif url==OWNER+'/releases/download/'+STABLE+'/nightly-tag.txt':out=self.raw
        elif url.endswith('/LICENSE'):out=b'Permission is hereby granted (synthetic test license)'
        elif url in self.bodies:out=self.bodies[url]
        else:raise DownloadError('HTTP 404 fixture '+url)
        if isinstance(out,Exception):raise out
        return Reply(out)

class ReleaseReference110(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)/'home';self.home.mkdir()
        self.manager=lr.LlamaRuntimeManager(self.home)
        self.raw=(BINARY+'\n').encode('ascii')
        self.pointer=asset(STABLE,'nightly-tag.txt',self.raw,aid=51)
        self.parent=release(assets=[self.pointer])
        names=['llama-'+BINARY+'-bin-win-cuda-12.4-x64.zip',
               'cudart-llama-bin-win-cuda-12.4-x64.zip',
               'llama-'+BINARY+'-bin-win-vulkan-x64.zip',
               'llama-'+BINARY+'-bin-win-cpu-x64.zip',
               'llama-'+BINARY+'-bin-ubuntu-cuda-12.8-x64.tar.gz',
               'cudart-llama-bin-ubuntu-cuda-12.8-x64.tar.gz',
               'llama-'+BINARY+'-bin-ubuntu-vulkan-x64.tar.gz',
               'llama-'+BINARY+'-bin-ubuntu-x64.tar.gz',
               'cudart-llama-bin-win-cuda-13.4-x64.zip',
               'llama-'+BINARY+'-bin-win-cuda-13.4-x64.zip',
               'llama-'+BINARY+'-bin-win-cpu-arm64.zip']
        self.build=release(BINARY,[asset(BINARY,n,aid=i+100) for i,n in enumerate(names)],pre=True,rid=12001)
        self.transport=FixtureTransport(self.parent,self.build,self.raw);self.manager.transport=self.transport
        self.logs=[];self.manager._log=self.logs.append
    def tearDown(self):self.tmp.cleanup()
    def resolve(self):return self.manager._resolve_binary_release(self.parent)
    def choose(self,system,preference='auto',nvidia=True):
        with patch.object(self.manager,'_platform',return_value=system),patch.object(self.manager,'_has_nvidia',return_value=nvidia):
            return self.manager._select(self.manager._fetch_releases(),preference)
    def error(self,code=None):
        with self.assertRaises(lr.LlamaRuntimeError) as result:self.resolve()
        if code:self.assertEqual(result.exception.code,code)
        return result.exception
    def test_windows_cuda_follows_stable_pointer_and_matches_dlls(self):
        build,b,main,companions=self.choose('windows')
        self.assertEqual((build['tag_name'],b),(BINARY,'cuda12'))
        self.assertEqual(main['name'],'llama-'+BINARY+'-bin-win-cuda-12.4-x64.zip')
        self.assertEqual([a['name'] for a in companions],['cudart-llama-bin-win-cuda-12.4-x64.zip'])
        self.assertTrue(build['prerelease']);self.assertEqual(build['_stable_reference']['tag_name'],STABLE)
        self.assertEqual([kind for kind,_ in self.transport.requests],['json','open','json'])
    def test_linux_cuda_follows_pointer_matches_ubuntu_archive_and_libraries(self):
        build,b,main,companions=self.choose('linux')
        self.assertEqual((build['tag_name'],b),(BINARY,'cuda12'))
        self.assertTrue(main['name'].endswith('ubuntu-cuda-12.8-x64.tar.gz'))
        self.assertEqual([a['name'] for a in companions],['cudart-llama-bin-ubuntu-cuda-12.8-x64.tar.gz'])
    def test_all_platform_backend_combinations(self):
        for system in ('linux','windows'):
            for backend in ('cpu','vulkan','cuda12'):
                with self.subTest(system=system,backend=backend):
                    build,b,main,companions=self.choose(system,backend)
                    self.assertEqual(b,backend);self.assertIn('-win-' if system=='windows' else '-ubuntu-',main['name'])
                    self.assertEqual(len(companions),int(backend=='cuda12'))
    def test_latest_endpoint_parent_with_fifty_unrelated_nightlies(self):
        self.transport.json_overrides[lr.RELEASES_API]=[release('b'+str(i),pre=True,rid=i) for i in range(20000,20050)]
        self.assertEqual(self.choose('windows')[0]['tag_name'],BINARY)
        self.assertIn(('json',lr.LATEST_RELEASE_API),self.transport.requests)
        self.assertNotIn(('json',lr.RELEASE_BY_TAG.format(tag='b20000')),self.transport.requests)
    def test_unreferenced_prerelease_still_rejected(self):
        self.assertFalse(lr._release_valid(self.build))
        self.parent['prerelease']=True
        self.error('llama_metadata_invalid');self.assertEqual(self.transport.requests,[])
    def test_draft_stable_parent_rejected(self):
        self.parent['draft']=True;self.error('llama_metadata_invalid')
    def test_legacy_full_stable_with_binaries_works_without_pointer(self):
        old=release('v0.4.1',[asset('v0.4.1','llama-v0.4.1-bin-win-cpu-x64.zip')])
        with patch.object(self.manager,'_platform',return_value='windows'):
            selected=self.manager._select([old],'cpu')
        self.assertEqual(selected[0]['tag_name'],'v0.4.1');self.assertEqual(self.transport.requests,[])
    def test_pointer_is_cached_across_backend_fallback(self):
        self.resolve();self.resolve()
        with patch.object(self.manager,'_platform',return_value='windows'):
            self.manager._select([self.parent],'cuda12');self.manager._select([self.parent],'vulkan');self.manager._select([self.parent],'cpu')
        self.assertEqual(len(self.transport.requests),2)
    def test_does_not_resolve_unused_older_pointer(self):
        old=release('v0.4.0',[asset('v0.4.0','nightly-tag.txt',b'b10000')],rid=40)
        with patch.object(self.manager,'_platform',return_value='windows'):
            self.assertEqual(self.manager._select([self.parent,old],'cuda12')[0]['tag_name'],BINARY)
        self.assertEqual(len(self.transport.requests),2)
    def test_missing_pointer_digest_is_not_bypassed(self):
        self.pointer['digest']=None;self.error('llama_integrity_error');self.assertEqual(self.transport.requests,[])
    def test_wrong_pointer_digest_is_rejected_before_binary_lookup(self):
        self.pointer['digest']='sha256:'+'0'*64;self.error('llama_integrity_error')
        self.assertEqual([kind for kind,_ in self.transport.requests],['open'])
    def test_wrong_pointer_size_is_rejected(self):
        self.pointer['size']+=1;self.error('llama_integrity_error')
    def test_oversized_and_invalid_pointer_sizes_are_rejected(self):
        for size in (0,-1,129,True,'8',None):
            with self.subTest(size=size):self.pointer['size']=size;self.error('llama_integrity_error')
        self.assertEqual(self.transport.requests,[])
    def test_ambiguous_pointer_is_rejected(self):
        self.parent['assets'].append(copy.deepcopy(self.pointer));self.error('llama_integrity_error')
    def test_malformed_tags_cannot_become_requests_or_commands(self):
        for raw in (b'b12001\nb12002',b'../b12001',b'https://example.com/x',b'v0.5.0',b'b0',b'b12001;echo evil',b'\xff',b''):
            with self.subTest(raw=raw):
                self.transport.raw=raw;self.pointer['size']=len(raw);self.pointer['digest']='sha256:'+hashlib.sha256(raw).hexdigest()
                self.error()
        self.assertFalse(any(kind=='json' for kind,_ in self.transport.requests))
    def test_crlf_and_trailing_newline_are_accepted(self):
        self.transport.raw=(BINARY+'\r\n').encode();self.pointer['size']=len(self.transport.raw)
        self.pointer['digest']='sha256:'+hashlib.sha256(self.transport.raw).hexdigest()
        self.assertEqual(self.resolve()['tag_name'],BINARY)
    def test_wrong_pointer_owner_or_release_url_is_rejected(self):
        good=self.pointer['browser_download_url']
        for bad in (good.replace('/ggml-org/','/someone/'),good.replace('/v0.5.0/','/v0.4.0/'),good+'?token=bad',good.replace('https://','http://')):
            with self.subTest(url=bad):self.pointer['browser_download_url']=bad;self.error('llama_integrity_error')
        self.assertEqual(self.transport.requests,[])
    def test_linked_release_tag_must_match_pointer(self):
        self.build['tag_name']='b12002';self.error('llama_metadata_invalid')
    def test_linked_draft_is_not_installable(self):
        self.build['draft']=True;self.error('llama_metadata_invalid')
    def test_linked_release_wrong_repository_rejected(self):
        self.build['html_url']='https://github.com/elsewhere/llama.cpp/releases/tag/'+BINARY;self.error('llama_integrity_error')
    def test_linked_metadata_without_id_rejected(self):
        self.build['id']=None;self.error('llama_metadata_invalid')
    def test_build_assets_cannot_point_to_another_release(self):
        self.build['assets'][0]['browser_download_url']=self.build['assets'][0]['browser_download_url'].replace(BINARY,'b12002')
        with self.assertRaises(lr.LlamaRuntimeError) as result:self.choose('windows','cuda12')
        self.assertEqual(result.exception.code,'llama_integrity_error')
    def test_missing_cuda_companion_falls_back_within_verified_build(self):
        self.build['assets']=[a for a in self.build['assets'] if a['name']!='cudart-llama-bin-win-cuda-12.4-x64.zip']
        self.assertEqual(self.choose('windows')[1],'vulkan')
    def test_no_wrong_cuda_minor_pairing(self):
        self.build['assets']=[a for a in self.build['assets'] if a['name']!='cudart-llama-bin-win-cuda-12.4-x64.zip']
        with self.assertRaises(lr.LlamaRuntimeError) as caught:self.choose('windows','cuda12')
        self.assertEqual(caught.exception.code,'llama_no_binary')
    def test_no_nvidia_prefers_vulkan_without_system_mutation(self):
        before=dict(os.environ);self.assertEqual(self.choose('linux',nvidia=False)[1],'vulkan');self.assertEqual(dict(os.environ),before)
    def test_no_compatible_assets_reports_linked_tag_and_asset_list(self):
        self.build['assets']=[asset(BINARY,'only-macos-arm64.zip')]
        with self.assertRaises(lr.LlamaRuntimeError) as result:self.choose('windows')
        self.assertEqual(result.exception.code,'llama_no_binary')
        self.assertTrue(any('Published assets '+BINARY in x for x in self.logs))
    def test_rate_limit_from_linked_api_is_distinguished(self):
        self.transport.json_overrides[lr.RELEASE_BY_TAG.format(tag=BINARY)]=DownloadError('HTTP 403')
        self.error('llama_api_limited')
    def test_pointer_network_error_is_not_no_binary(self):
        self.transport.open_overrides[self.pointer['browser_download_url']]=DownloadError('DNS failure')
        self.error('llama_network_error')
    def test_saved_selection_revalidates_stable_parent_not_arbitrary_build(self):
        self.manager.root.mkdir(parents=True)
        self.manager.selection.write_text(json.dumps({'id':12001,'tag_name':BINARY,'stable_release_id':50,'stable_release_tag':STABLE}))
        self.transport.json_overrides[lr.RELEASES_API]=[];self.transport.json_overrides[lr.LATEST_RELEASE_API]=None
        self.transport.json_overrides[lr.RELEASE_BY_ID.format(release_id=50)]=self.parent
        self.assertEqual(self.choose('windows')[0]['tag_name'],BINARY)
        self.assertIn(('json',lr.RELEASE_BY_ID.format(release_id=50)),self.transport.requests)
        self.assertNotIn(('json',lr.RELEASE_BY_ID.format(release_id=12001)),self.transport.requests)
    def test_saved_build_without_verified_parent_is_not_trusted(self):
        self.manager.root.mkdir(parents=True);self.manager.selection.write_text(json.dumps({'id':12001,'tag_name':BINARY}))
        self.transport.json_overrides[lr.RELEASES_API]=[];self.transport.json_overrides[lr.LATEST_RELEASE_API]=None
        self.transport.json_overrides[lr.RELEASE_BY_ID.format(release_id=12001)]=self.build
        with self.assertRaises(lr.LlamaRuntimeError):self.manager._fetch_releases()

    def archives(self,system):
        # The Windows .exe is a non-executable fixture. Windows self-check is mocked.
        # POSIX uses a tiny harmless local shell script and really starts a child.
        if system=='windows':
            main='llama-'+BINARY+'-bin-win-cuda-12.4-x64.zip';comp='cudart-llama-bin-win-cuda-12.4-x64.zip'
            def pack(files):
                stream=io.BytesIO()
                with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                    for name,data in files:z.writestr('llama-'+BINARY+'/'+name,data)
                return stream.getvalue()
            a=pack([('llama-server.exe',b'MZ SYNTHETIC TEST ONLY'),('ggml-cuda.dll',b'ggml fixture')])
            b=pack([('cudart64_12.dll',b'cudart fixture'),('cublas64_12.dll',b'cublas fixture'),('LICENSE.txt',b'CUDA fixture notice')])
        else:
            main='llama-'+BINARY+'-bin-ubuntu-cuda-12.8-x64.tar.gz';comp='cudart-llama-bin-ubuntu-cuda-12.8-x64.tar.gz'
            def pack(files,links=()):
                stream=io.BytesIO()
                with tarfile.open(fileobj=stream,mode='w:gz') as t:
                    for name,data in files:
                        m=tarfile.TarInfo('llama-'+BINARY+'/'+name);m.size=len(data);t.addfile(m,io.BytesIO(data))
                    for name,target in links:
                        m=tarfile.TarInfo('llama-'+BINARY+'/'+name);m.type=tarfile.SYMTYPE;m.linkname=target;t.addfile(m)
                return stream.getvalue()
            a=pack([('llama-server',b'#!/bin/sh\ncase "$1" in --version) echo "fixture only";; --list-devices) echo "CUDA0: synthetic device";; *) exit 1;; esac\n'),('libggml.so.0.5.0',b'ggml fixture')],[('libggml.so.0','libggml.so.0.5.0'),('libggml.so','libggml.so.0')])
            b=pack([('libcudart.so.12',b'cudart fixture'),('libcublas.so.12',b'cublas fixture'),('LICENSE.txt',b'CUDA fixture notice')],[('libcudart.so','libcudart.so.12')])
        self.build['assets']=[asset(BINARY,main,a,aid=101),asset(BINARY,comp,b,aid=102)]
        self.transport.bodies={x['browser_download_url']:data for x,data in zip(self.build['assets'],(a,b))}

    def roundtrip(self,system):
        self.archives(system)
        exe='llama-server.exe' if system=='windows' else 'llama-server'
        with patch.object(self.manager,'_system_log_root',return_value=self.home/'state'),patch.object(self.manager,'_platform',return_value=system),patch.object(lr,'executable_name',return_value=exe),patch.object(self.manager,'_has_nvidia',return_value=True):
            if system=='windows':
                with patch.object(self.manager,'_self_check') as check:
                    result=self.manager.install();check.assert_called_once()
                    self.assertEqual(check.call_args.args[1],'cuda12')
            else:result=self.manager.install()
        self.assertTrue(result['installed']);self.assertEqual(result['backend'],'cuda12')
        self.assertEqual(result['version'],BINARY)
        meta=json.loads(self.manager.meta.read_text());selection=json.loads(self.manager.selection.read_text())
        self.assertEqual(meta['stable_reference']['tag_name'],STABLE);self.assertTrue(meta['binary_prerelease'])
        self.assertEqual(selection['stable_release_id'],50);self.assertEqual(selection['stable_release_tag'],STABLE)
        self.assertEqual(len(meta['sha256']),2);self.assertTrue(meta['upstream_digest_verified'])
        self.assertTrue((self.manager.root/'build/licenses/llama.cpp/LICENSE').is_file())
        self.assertEqual(list(self.manager.root.glob('.incoming-*')),[])
        self.assertEqual(list(self.manager.root.glob('build.new-*')),[])
        return result
    def test_windows_archive_download_verification_extract_publish_fixture(self):
        self.roundtrip('windows')
        for name in ('llama-server.exe','ggml-cuda.dll','cudart64_12.dll','cublas64_12.dll'):
            self.assertTrue((self.manager.root/'build/bin'/name).is_file())
    @unittest.skipIf(os.name=='nt','POSIX stub execution; native Windows acceptance separate')
    def test_linux_archive_hash_library_chain_and_real_stub_process(self):
        self.roundtrip('linux')
        for name in ('libggml.so','libggml.so.0','libcudart.so'):
            p=self.manager.root/'build/bin'/name;self.assertTrue(p.is_file());self.assertFalse(p.is_symlink())
        self.assertTrue(any('--version: fixture only' in s for s in self.logs))
        self.assertTrue(any('--list-devices: CUDA0: synthetic device' in s for s in self.logs))
    def test_failed_pointer_install_preserves_existing_runtime(self):
        old=self.manager.root/'build/bin';old.mkdir(parents=True);(old/lr.executable_name()).write_bytes(b'OLD DO NOT DELETE')
        self.manager.meta.write_text('{"release":"old"}')
        self.pointer['digest']='sha256:'+'0'*64
        with patch.object(self.manager,'_system_log_root',return_value=self.home/'state'):
            with self.assertRaises(lr.LlamaRuntimeError):self.manager.install('cpu')
        self.assertEqual((old/lr.executable_name()).read_bytes(),b'OLD DO NOT DELETE')
        self.assertEqual(json.loads(self.manager.meta.read_text()),{'release':'old'})
        self.assertEqual(self.manager.status()['error_code'],'llama_integrity_error')
    def test_binary_sha_failure_preserves_old_runtime_and_never_executes(self):
        self.archives('windows');main=self.build['assets'][0];main['digest']='sha256:'+'0'*64
        old=self.manager.root/'build/bin';old.mkdir(parents=True);(old/lr.executable_name()).write_bytes(b'old')
        with patch.object(self.manager,'_system_log_root',return_value=self.home/'state'),patch.object(self.manager,'_platform',return_value='windows'),patch.object(self.manager,'_has_nvidia',return_value=True),patch.object(self.manager,'_self_check') as check:
            with self.assertRaises(lr.LlamaRuntimeError) as result:self.manager.install()
            check.assert_not_called()
        self.assertEqual(result.exception.code,'llama_integrity_error')
        self.assertEqual((old/lr.executable_name()).read_bytes(),b'old')
        self.assertEqual(list(self.manager.root.glob('.incoming-*')),[])
        self.assertEqual(list(self.manager.root.glob('build.new-*')),[])

if __name__=='__main__':unittest.main()
