"""Untrusted ZIP handling, inert import, reuse-only default and detached orchestration.
All state is in TemporaryDirectory. No installed user app, network or GPU used.
"""
import io,json,hashlib,os,stat,subprocess,sys,tempfile,time,unittest,zipfile,shutil
from pathlib import Path
from unittest.mock import patch
from core import app_updates as u
from core.install_layout import atomic_json,set_pointers,write_runtime_map,verify_manifest
ROOT=Path(__file__).resolve().parents[1]
CURRENT='0.1.0.29';TARGET='0.1.0.30'

def contents(version=TARGET,platform='linux'):
    data={f:b'# inert placeholder\n' for f in u.REQUIRED}
    for f in ('core/runtime_env.py','core/install_layout.py'):data[f]=f"VERSION = {version!r}\n".encode()
    data['UPDATE_PACKAGE.json']=json.dumps({'schema':1,'product':u.PRODUCT,'version':version,'platform':platform,
        'kind':'full-source-online','minimum_updater':CURRENT}).encode()
    data['scripts/install.py']=b"from pathlib import Path\nPath('SHOULD_NOT_RUN').touch()\n"
    data['LICENSE']=b'Apache-2.0\n'
    return data

def zip_bytes(data=None,platform='linux',version=TARGET,extras=(),manifest=None):
    data=contents(version,platform) if data is None else dict(data)
    if manifest is None:manifest=''.join(hashlib.sha256(v).hexdigest()+'  '+k+'\n' for k,v in sorted(data.items()))
    data['MANIFEST.sha256']=manifest.encode()
    prefix='zetalvx_creator_studio_sdxl_v'+version.replace('.','_')+'_'+platform+'/'
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name,value in data.items():z.writestr(prefix+name,value)
        for name,value in extras:z.writestr(name,value)
    return buf.getvalue()

class ArchiveTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.z=self.root/'test.zip';self.dest=self.root/'payload'
    def tearDown(self):self.tmp.cleanup()
    def validate(self,data=None,**kwargs):
        self.z.write_bytes(data or zip_bytes());return u.validate_package(self.z,self.dest,installed_version=CURRENT,platform_name='linux',**kwargs)
    def test_valid_archive_manifest_all_files(self):
        result=self.validate();self.assertEqual(result['version'],TARGET);self.assertFalse(result['signature_verified']);self.assertEqual(set(verify_manifest(self.dest)),u.REQUIRED)
    def test_validation_never_executes_uploaded_python(self):
        self.validate();self.assertFalse((self.dest/'SHOULD_NOT_RUN').exists())
    def test_published_hash_matches(self):
        data=zip_bytes();result=self.validate(data,expected_sha256=hashlib.sha256(data).hexdigest());self.assertTrue(result['publisher_hash_supplied'])
    def test_wrong_published_hash(self):
        with self.assertRaisesRegex(u.UpdateError,'checksum'):self.validate(expected_sha256='0'*64)
        self.assertFalse(self.dest.exists())
    def test_bad_hash_format(self):
        with self.assertRaisesRegex(u.UpdateError,'64 hexadecimal'):self.validate(expected_sha256='abc')
    def test_corrupt_zip(self):
        with self.assertRaises(u.UpdateError):self.validate(b'NOT ZIP')
    def test_tampered_member(self):
        data=contents();manifest=''.join(hashlib.sha256(v).hexdigest()+'  '+k+'\n' for k,v in sorted(data.items()));data['app.py']=b'tampered'
        with self.assertRaisesRegex(ValueError,'checksum'):self.validate(zip_bytes(data,manifest=manifest))
        self.assertFalse(self.dest.exists())
    def test_unlisted_file(self):
        prefix='zetalvx_creator_studio_sdxl_v0_1_0_30_linux/'
        with self.assertRaisesRegex(u.UpdateError,'every package'):self.validate(zip_bytes(extras=[(prefix+'unlisted.py',b'code')]))
        self.assertFalse(self.dest.exists())
    def test_wrong_product(self):
        data=contents();d=json.loads(data['UPDATE_PACKAGE.json']);d['product']='creator-studio-original';data['UPDATE_PACKAGE.json']=json.dumps(d).encode()
        with self.assertRaisesRegex(u.UpdateError,'another application'):self.validate(zip_bytes(data))
    def test_metadata_must_be_object(self):
        data=contents();data['UPDATE_PACKAGE.json']=b'[]'
        with self.assertRaisesRegex(u.UpdateError,'metadata object'):self.validate(zip_bytes(data))
        self.assertFalse(self.dest.exists())
    def test_metadata_size_limit(self):
        data=contents();data['UPDATE_PACKAGE.json']=b' '*65537
        with self.assertRaisesRegex(u.UpdateError,'metadata too large'):self.validate(zip_bytes(data))
    def test_manifest_size_limit(self):
        with self.assertRaisesRegex(u.UpdateError,'manifest too large'):self.validate(zip_bytes(manifest=' '*((2*1024**2)+1)))
    def test_wrong_platform(self):
        with self.assertRaisesRegex(u.UpdateError,'operating system'):self.validate(zip_bytes(platform='windows'))
    def test_windows_package_validation(self):
        self.z.write_bytes(zip_bytes(platform='windows'));self.assertEqual(u.validate_package(self.z,self.dest,installed_version=CURRENT,platform_name='windows')['platform'],'windows')
    def test_same_version_and_downgrade(self):
        for version in [CURRENT,'0.1.0.27']:
            with self.subTest(version=version),self.assertRaisesRegex(u.UpdateError,'newer version'):self.validate(zip_bytes(version=version))
    def test_inconsistent_literal_version(self):
        data=contents();data['core/runtime_env.py']=b"VERSION='0.1.0.99'\n"
        with self.assertRaisesRegex(u.UpdateError,'Conflicting version'):self.validate(zip_bytes(data))
    def test_requires_newer_updater(self):
        data=contents();d=json.loads(data['UPDATE_PACKAGE.json']);d['minimum_updater']='0.1.0.99';data['UPDATE_PACKAGE.json']=json.dumps(d).encode()
        with self.assertRaisesRegex(u.UpdateError,'newer updater'):self.validate(zip_bytes(data))
    def test_missing_required_member(self):
        data=contents();data.pop('scripts/install.py')
        with self.assertRaisesRegex(u.UpdateError,'Incomplete'):self.validate(zip_bytes(data))
    def test_paths_and_reserved_names(self):
        for name in ['../outside','/tmp/out','C:/out','a/../out','a\\out','a//out','a/CON.txt','a/foo.','a/PRN','a/COM1.py','a/b\x00c','a/b:stream','a/x?x']:
            with self.subTest(name=name),self.assertRaises(u.UpdateError):u.portable_path(name)
    def test_duplicate_case_variant(self):
        prefix='zetalvx_creator_studio_sdxl_v0_1_0_30_linux/'
        with self.assertRaisesRegex(u.UpdateError,'Duplicate'):self.validate(zip_bytes(extras=[(prefix+'APP.py',b'x')]))
    def test_zip_path_traversal_rejected(self):
        with self.assertRaises(u.UpdateError):self.validate(zip_bytes(extras=[('../outside',b'x')]))
        self.assertFalse((self.root/'outside').exists())
    def test_symlink_rejected(self):
        info=zipfile.ZipInfo('zetalvx_creator_studio_sdxl_v0_1_0_30_linux/link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        with self.assertRaisesRegex(u.UpdateError,'regular'):self.validate(zip_bytes(extras=[(info,b'/etc/passwd')]))
    def test_size_limit_before_extract(self):
        with patch.object(u,'MAX_FILE',12),self.assertRaisesRegex(u.UpdateError,'too large'):self.validate()
        self.assertFalse(self.dest.exists())
    def test_file_count_limit(self):
        with patch.object(u,'MAX_FILES',2),self.assertRaisesRegex(u.UpdateError,'member count'):self.validate()
    def test_zip_total_size_limit(self):
        with patch.object(u,'MAX_TOTAL',20),self.assertRaisesRegex(u.UpdateError,'512 MiB'):self.validate()
    def test_deflate_bomb(self):
        data=contents();data['big.txt']=b'x'*2*1024**2
        with self.assertRaisesRegex(u.UpdateError,'compression ratio'):self.validate(zip_bytes(data))
    def test_no_overwrite_destination(self):
        self.dest.mkdir();(self.dest/'sentinel').write_text('keep')
        with self.assertRaisesRegex(u.UpdateError,'already exists'):self.validate()
        self.assertEqual((self.dest/'sentinel').read_text(),'keep')
    def test_out_of_disk(self):
        with patch.object(u.shutil,'disk_usage',return_value=type('D',(),{'free':0})()),self.assertRaisesRegex(u.UpdateError,'free space'):self.validate()
    def test_reject_unknown_compression(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_BZIP2) as z:z.writestr('any/file','test')
        with self.assertRaisesRegex(u.UpdateError,'compression'):self.validate(b.getvalue())

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)/'CreatorStudioSDXL';self.source=self.home/'versions'/CURRENT;self.source.mkdir(parents=True)
        set_pointers(self.home,CURRENT,None);self.store=u.UpdateStore(self.home,self.source,CURRENT)
        self.runtimes={n:self.home/'runtime'/n for n in ['app','sdxl']}
        for path in self.runtimes.values():(path/'bin').mkdir(parents=True);(path/'bin/python').touch()
        write_runtime_map(self.home,self.source,self.runtimes,backend='cu126',version=CURRENT)
    def tearDown(self):self.tmp.cleanup()
    def imported(self,body=None):return self.store.import_zip(io.BytesIO(body or zip_bytes()),'release.zip')
    def test_import_does_not_activate(self):
        state=self.imported();self.assertEqual(state['status'],'ready');self.assertEqual((self.home/'current').resolve(),self.source);self.assertFalse(self.store.maintenance())
    def test_bad_id(self):
        for id in ['../','bad','0'*32+'/evil']:
            with self.assertRaises(u.UpdateError):self.store.read(id)
    def test_only_one_staged(self):
        self.imported()
        with self.assertRaisesRegex(u.UpdateError,'previous update'):self.imported()
    def test_discard_never_touches_install(self):
        state=self.imported();self.store.discard(state['id']);self.assertFalse((self.store.folder(state['id'])/'payload').exists());self.assertTrue(self.source.exists())
    def test_recheck_unexpected_file(self):
        state=self.imported();(self.store.folder(state['id'])/'payload/unlisted.py').touch()
        with self.assertRaisesRegex(u.UpdateError,'Unexpected'):self.store.recheck(state)
    def test_staged_tamper_before_start(self):
        state=self.imported();(self.store.folder(state['id'])/'payload/app.py').write_text('changed')
        with self.assertRaises(ValueError):self.store.start(state['id'])
        self.assertEqual((self.home/'current').resolve(),self.source)
    def test_no_restart_while_busy(self):
        state=self.imported()
        with patch('scripts.install.ensure_idle',side_effect=RuntimeError('busy')),self.assertRaisesRegex(RuntimeError,'busy'):self.store.start(state['id'])
        self.assertEqual(self.store.read(state['id'])['status'],'ready')
    def test_reuse_default_and_inert_helper_arguments(self):
        state=self.imported()
        result=subprocess.CompletedProcess([],0,json.dumps({'pid':os.getpid(),'process_start':u.process_start(os.getpid())}), '')
        with patch('scripts.install.ensure_idle'),patch.object(u.subprocess,'run',return_value=result) as run:
            start=self.store.start(state['id'])
        self.assertFalse(start['allow_new_runtime']);cmd=run.call_args.args[0]
        self.assertIn('--spawn',cmd);self.assertIn(str(self.source/'scripts/gui_update.py'),cmd);self.assertNotIn('shell',run.call_args.kwargs)
        self.assertTrue(self.store.maintenance())
    def test_discard_running_refused(self):
        state=self.imported();state.update(status='running',pid=os.getpid(),process_start=u.process_start(os.getpid()));self.store.save(state)
        with self.assertRaisesRegex(u.UpdateError,'cannot be interrupted'):self.store.discard(state['id'])
    def test_failed_spawn_saved(self):
        state=self.imported()
        with patch('scripts.install.ensure_idle'),patch.object(u.subprocess,'run',side_effect=OSError('spawn failed')),self.assertRaises(OSError):self.store.start(state['id'])
        self.assertEqual(self.store.read(state['id'])['status'],'failed');self.assertFalse(self.store.maintenance())
    def test_running_pid_reuse_recognized(self):
        state=self.imported();state.update(status='running',pid=os.getpid(),process_start='wrong',updated_at=time.time()-100);atomic_json(self.store.folder(state['id'])/'state.json',state)
        self.assertFalse(self.store.maintenance());self.assertEqual(self.store.read(state['id'])['status'],'interrupted')
    def test_source_folder_not_installed_refused(self):
        store=u.UpdateStore(self.home,self.home/'not-installed',CURRENT)
        with self.assertRaisesRegex(u.UpdateError,'active installed'):store.import_zip(io.BytesIO(zip_bytes()),'file.zip')
    def test_symlink_updates_root(self):
        self.store.root.parent.mkdir(parents=True,exist_ok=True);target=self.home/'elsewhere';target.mkdir();self.store.root.symlink_to(target,target_is_directory=True)
        with self.assertRaisesRegex(u.UpdateError,'symbolic link'):self.imported()
    def test_large_upload_stream_bounded(self):
        with patch.object(u,'MAX_ZIP',30),self.assertRaisesRegex(u.UpdateError,'128 MiB'):self.imported()

class DetachedRunnerTests(unittest.TestCase):
    setUp=StoreTests.setUp
    tearDown=StoreTests.tearDown
    imported=StoreTests.imported
    @unittest.skipIf(os.name=='nt','This fixture uses Linux symlinks; native Windows remains a separate acceptance test')
    def test_real_detached_runner_survives_helper_exit(self):
        # Copy only our trusted stdlib control layer. AI, web server and actual activation
        # are not run: a tiny fixture installer only records arguments in this temp home.
        for relative in ['scripts/gui_update.py','scripts/install.py','scripts/__init__.py','core/app_updates.py','core/install_layout.py','core/platform_support.py','core/private_cuda_env.py','core/file_lock.py','core/__init__.py','core/maintenance_state.py','core/private_files.py','core/safe_paths.py']:
            out=self.source/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,out)
        py=self.runtimes['app']/'bin/python';py.unlink();py.symlink_to(sys.executable)
        data=contents()
        data['scripts/install.py']=b'''import json,sys,time\nfrom pathlib import Path\nhome=Path(sys.argv[sys.argv.index('--home')+1]);(home/'fixture-arguments.json').write_text(json.dumps(sys.argv))\ntime.sleep(.1)\nnew=home/'versions/0.1.0.30';new.mkdir();tmp=home/'current.test';tmp.symlink_to(new);tmp.replace(home/'current')\n'''
        state=self.imported(zip_bytes(data))
        # start launches old installed helper, helper detaches a grandchild and exits.
        started=self.store.start(state['id']);self.assertTrue(started['pid'])
        until=time.time()+20
        while time.time()<until:
            observed=self.store.read(state['id'])
            if observed['status'] in u.FINAL_STATES:break
            time.sleep(.1)
        self.assertEqual(observed['status'],'completed',observed)
        args=json.loads((self.home/'fixture-arguments.json').read_text());self.assertIn('keep',args);self.assertIn('--online',args);self.assertIn('--no-browser',args)
        self.assertEqual((self.home/'current').resolve().name,TARGET)
        self.assertTrue((self.runtimes['sdxl']/'bin/python').exists())
        self.assertFalse((self.store.folder(state['id'])/'payload/SHOULD_NOT_RUN').exists())

if __name__=='__main__':unittest.main()
