"""Targeted security regressions. Real temp files/state; transport and Windows APIs mocked where stated."""
from __future__ import annotations
import contextlib,hashlib,io,json,os,sqlite3,stat,subprocess,sys,tarfile,tempfile,threading,types,unittest,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PureWindowsPath
from unittest.mock import patch,Mock
from core.safe_paths import portable_relative,safe_child,is_link
from core.private_files import atomic_private_text,private_directory,protect
from core.download_security import TokenStore,DownloadError
from core.login_throttle import LoginThrottle
from core.install_layout import atomic_json
from core.maintenance_state import busy_jobs,BUSY
from vision.link_imports import VisionLinkImports,_safe_rel
from vision.llama_runtime import LlamaRuntimeManager,LlamaRuntimeError,_extract,_preserve_notices,executable_name
ROOT=Path(__file__).resolve().parents[1]

class TempTest(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)/'CreatorStudioSDXL';self.home.mkdir()
 def tearDown(self):self.tmp.cleanup()

class PortablePaths42(TempTest):
 def test_rejects_windows_and_parent_paths_on_all_platforms(self):
  for name in ['../a.json','a/../../x.json',r'..\x.json',r'C:\x.json','C:/x.json',r'\\host\share\x.json','/a.json','a//x.json','a/./b.json','a/../b.json','a:stream.json']:
   with self.subTest(name=name),self.assertRaises(ValueError):portable_relative(name)
 def test_rejects_reserved_names_control_and_trailing(self):
  for name in ['CON.json','con','folder/COM1.txt','LPT9/a.json','COM¹.txt','a./x.json','a /b.json','x\0.json','x\n.json','x?.json','a|b.json','a*.json','a<b.json']:
   with self.subTest(name=name),self.assertRaises(ValueError):portable_relative(name)
 def test_normal_unicode_paths_remain_usable(self):
  for name in ['config.json','processor/tokenizer.json','assets/日本語.txt','model-00001-of-00002.safetensors','.gitattributes']:
   with self.subTest(name=name):
    self.assertEqual(portable_relative(name).as_posix(),name)
    self.assertFalse(PureWindowsPath(name).is_absolute())
    self.assertEqual(safe_child(self.home,name),self.home/Path(name))
 def test_link_in_download_path_refused(self):
  target=Path(self.tmp.name)/'outside';target.mkdir()
  try:(self.home/'link').symlink_to(target,target_is_directory=True)
  except OSError:self.skipTest('Symlink unavailable')
  with self.assertRaises(ValueError):safe_child(self.home,'link/config.json')
  self.assertEqual(list(target.iterdir()),[])
 def test_root_link_refused(self):
  link=Path(self.tmp.name)/'alias'
  try:link.symlink_to(self.home,target_is_directory=True)
  except OSError:self.skipTest('Symlink unavailable')
  with self.assertRaises(ValueError):safe_child(link,'x.json')
 def test_reparse_detection(self):
  fake=Mock();fake.lstat.return_value=types.SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x400)
  self.assertTrue(is_link(fake))
 def test_vision_validator_uses_same_rules(self):
  for name in [r'C:\x.json',r'..\x.json','CON.json']:
   with self.subTest(name=name),self.assertRaises(ValueError):_safe_rel(name)

class PrivateStorage42(TempTest):
 def test_no_fchmod_required_for_token_roundtrip(self):
  with patch.object(os,'fchmod',side_effect=AssertionError('fchmod must not be called'),create=True):
   s=TokenStore(self.home/'secrets');s.put('huggingface','hf_fake_TEST_ONLY');self.assertEqual(s.get('huggingface'),'hf_fake_TEST_ONLY')
   self.assertNotIn('hf_fake_TEST_ONLY',json.dumps(s.public()));s.delete('huggingface');self.assertEqual(s.get('huggingface'),'')
 def test_unicode_account_metadata_roundtrip(self):
  store=TokenStore(self.home/'secrets');store.put('huggingface','hf_fake_TEST_ONLY','日本語 é')
  self.assertEqual(store.public()['huggingface']['account'],'日本語 é')
 def test_invalid_replacement_preserves_token(self):
  store=TokenStore(self.home/'secrets');store.put('huggingface','hf_fake_TEST_ONLY')
  with self.assertRaises(DownloadError):store.put('huggingface','bad token')
  self.assertEqual(store.get('huggingface'),'hf_fake_TEST_ONLY')
 def test_atomic_replacement_preserves_old_on_failure(self):
  p=self.home/'secrets/value.txt';atomic_private_text(p,'before')
  with patch('core.private_files.os.replace',side_effect=OSError('disk failure')),self.assertRaises(OSError):atomic_private_text(p,'after')
  self.assertEqual(p.read_text(),'before');self.assertEqual(list(p.parent.iterdir()),[p])
 @unittest.skipIf(os.name=='nt','POSIX permissions only; native DACL tested separately')
 def test_posix_mode_and_existing_store_hardened(self):
  root=private_directory(self.home/'secrets');p=root/'value.txt';p.write_text('x');p.chmod(0o644);protect(p)
  self.assertEqual(stat.S_IMODE(root.stat().st_mode),0o700);self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
 def test_windows_dispatch_protects_file_and_folder(self):
  root=self.home/'secrets';root.mkdir();p=root/'file';p.touch()
  with patch('core.private_files._windows_dacl') as api:
   protect(root,directory=True,windows=True);protect(p,windows=True)
   self.assertEqual(api.call_args_list[0].args,(root,True));self.assertEqual(api.call_args_list[1].args,(p,False))
 def test_windows_acl_failure_is_not_ignored(self):
  p=self.home/'x';p.touch()
  with patch('core.private_files._windows_dacl',side_effect=OSError('ACL refused')),self.assertRaises(OSError):protect(p,windows=True)
 def test_acl_applied_before_write(self):
  p=self.home/'secrets/token';calls=[]
  from core.private_files import protect as real
  def watch(path,**kw):
   if not kw.get('directory'):calls.append(Path(path).stat().st_size)
   return real(path,**kw)
  with patch('core.private_files.protect',side_effect=watch):atomic_private_text(p,'sensitive')
  self.assertEqual(calls,[0])
 def test_private_file_symlink_not_followed(self):
  outside=Path(self.tmp.name)/'outside';outside.write_text('untouched');root=self.home/'secrets';root.mkdir()
  try:(root/'token').symlink_to(outside)
  except OSError:self.skipTest('Symlink unavailable')
  with self.assertRaises(OSError):atomic_private_text(root/'token','bad')
  self.assertEqual(outside.read_text(),'untouched')

class LoginThrottle42(TempTest):
 def limiter(self,**kw):return LoginThrottle(self.home/'secrets/login.sqlite3',**kw)
 def test_ninth_peer_attempt_throttled(self):
  t=self.limiter(clock=lambda:100)
  self.assertEqual([t.reserve('192.0.2.1') for _ in range(8)],[0]*8);self.assertEqual(t.reserve('192.0.2.1'),60)
 def test_new_peer_allowed(self):
  t=self.limiter(clock=lambda:100)
  for _ in range(8):t.reserve('192.0.2.1')
  self.assertEqual(t.reserve('192.0.2.2'),0)
 def test_global_limit_bounds_different_peers(self):
  t=self.limiter(clock=lambda:100,total=5)
  self.assertEqual([t.reserve(str(i)) for i in range(5)],[0]*5);self.assertEqual(t.reserve('new'),60)
 def test_persistent_across_instances(self):
  a=self.limiter(clock=lambda:100)
  for _ in range(8):a.reserve('peer')
  self.assertEqual(self.limiter(clock=lambda:101).reserve('peer'),59)
 def test_expiration_reopens(self):
  now=[100];t=self.limiter(clock=lambda:now[0])
  for _ in range(8):t.reserve('peer')
  now[0]=161;self.assertEqual(t.reserve('peer'),0)
 def test_success_resets_only_current_peer(self):
  t=self.limiter(clock=lambda:100)
  for _ in range(8):t.reserve('a');t.reserve('b')
  t.success('a');self.assertEqual(t.reserve('a'),0);self.assertEqual(t.reserve('b'),60)
 def test_concurrent_reservations_bounded(self):
  t=self.limiter(clock=lambda:100)
  with ThreadPoolExecutor(max_workers=12) as executor:results=list(executor.map(t.reserve,['peer']*24))
  self.assertEqual(results.count(0),8);self.assertEqual(results.count(60),16)
 def test_database_stores_no_clear_peer_or_user_secret(self):
  t=self.limiter(clock=lambda:100);t.reserve('192.0.2.55')
  with contextlib.closing(sqlite3.connect(t.path)) as db:rows=list(db.execute('SELECT * FROM attempts'))
  self.assertEqual(len(rows),1);self.assertNotEqual(rows[0][1],'192.0.2.55');self.assertEqual(len(rows[0][1]),64)
 def test_corrupted_state_fails_closed(self):
  t=self.limiter();t.path.parent.mkdir();t.path.write_text('invalid db')
  with self.assertRaises(sqlite3.DatabaseError):t.reserve('peer')

class Maintenance42(TempTest):
 def put(self,relative,status):
  p=self.home/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'status':status}));return p
 def test_all_busy_vision_statuses_detected(self):
  for status in BUSY:
   with self.subTest(status=status):self.put('shared/vision/link-imports/x.json',status);self.assertTrue(busy_jobs(self.home))
 def test_final_statuses_do_not_block(self):
  for status in ['complete','completed','cancelled','failed','interrupted']:
   with self.subTest(status=status):self.put('shared/vision/link-imports/x.json',status);self.assertEqual(busy_jobs(self.home),[])
 def test_runtime_preparation_detected(self):
  self.put('jobs/vision-actions/runtime.json','running');self.assertTrue(busy_jobs(self.home))
 def test_base_model_preparation_detected(self):
  self.put('shared/config/sdxl_base_install.json','downloading');self.assertTrue(busy_jobs(self.home))
 def test_model_hub_still_detected(self):
  self.put('shared/downloads/model-hub/job.json','queued');self.assertTrue(busy_jobs(self.home))
 def test_corrupt_known_state_is_not_idle(self):
  p=self.put('shared/vision/link-imports/x.json','complete');p.write_text('bad')
  with self.assertRaises(ValueError):busy_jobs(self.home)
 def test_installer_same_guard(self):
  from scripts.install import ensure_idle
  self.put('shared/vision/link-imports/x.json','verifying')
  with self.assertRaises(RuntimeError):ensure_idle(self.home)
 def test_no_writes_during_inventory(self):
  p=self.put('shared/vision/link-imports/x.json','downloading');before=p.read_bytes();busy_jobs(self.home);self.assertEqual(p.read_bytes(),before)

class Response:
 def __init__(self,data,length=None):self.data=data;self.headers={'Content-Length':str(len(data) if length is None else length)}
 def __enter__(self):return self
 def __exit__(self,*_):pass
 def chunks(self):yield self.data
 def small(self,maximum):
  if len(self.data)>maximum:raise DownloadError('too big')
  return self.data

class RuntimeIntegrity42(TempTest):
 def asset(self,data=b'archive'):
  return {'id':99,'name':'llama-bin-ubuntu-x64.zip','browser_download_url':'https://github.com/ggml-org/llama.cpp/releases/download/b123/llama-bin-ubuntu-x64.zip','size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest()}
 def test_expected_digest_and_length_match(self):
  m=LlamaRuntimeManager(self.home);m.transport=Mock();m.transport.open.return_value=Response(b'archive');p=self.home/'archive'
  self.assertEqual(m._download_asset(self.asset(),p),hashlib.sha256(b'archive').hexdigest())
 def test_missing_upstream_digest_refuses_before_network(self):
  a=self.asset();del a['digest'];m=LlamaRuntimeManager(self.home);m.transport=Mock()
  with self.assertRaisesRegex(LlamaRuntimeError,'expected SHA'):m._download_asset(a,self.home/'archive')
  m.transport.open.assert_not_called()
 def test_bad_digest_refused(self):
  m=LlamaRuntimeManager(self.home);m.transport=Mock();m.transport.open.return_value=Response(b'WRONG!!')
  with self.assertRaisesRegex(LlamaRuntimeError,'SHA-256 mismatch'):m._download_asset(self.asset(),self.home/'archive')
 def test_truncation_refused(self):
  m=LlamaRuntimeManager(self.home);m.transport=Mock();m.transport.open.return_value=Response(b'arc',length=7)
  with self.assertRaisesRegex(LlamaRuntimeError,'incomplete'):m._download_asset(self.asset(),self.home/'archive')
 def test_header_conflict_refused(self):
  m=LlamaRuntimeManager(self.home);m.transport=Mock();m.transport.open.return_value=Response(b'archive',length=9)
  with self.assertRaisesRegex(LlamaRuntimeError,'length'):m._download_asset(self.asset(),self.home/'archive')
 def test_cross_repository_source_refused(self):
  m=LlamaRuntimeManager(self.home);a=self.asset();a['browser_download_url']=a['browser_download_url'].replace('/ggml-org/','/impostor/')
  with self.assertRaises(LlamaRuntimeError):m._download_asset(a,self.home/'archive')
 def test_recent_stable_release_list_preferred_over_old_selection(self):
  m=LlamaRuntimeManager(self.home);m.root.mkdir(parents=True);m.selection.write_text(json.dumps({'id':123,'tag_name':'b123'}));m.transport=Mock()
  current={'id':124,'tag_name':'b124','assets':[],'draft':False,'prerelease':False};old={'id':123,'tag_name':'b123','assets':[],'draft':False,'prerelease':False}
  m.transport.json.side_effect=[[current],old]
  releases=m._fetch_releases();self.assertEqual([x['id'] for x in releases],[124,123]);self.assertIn('per_page=50',m.transport.json.call_args_list[0].args[0])
 def test_old_selection_identity_change_is_not_trusted(self):
  m=LlamaRuntimeManager(self.home);m.root.mkdir(parents=True);m.selection.write_text(json.dumps({'id':123,'tag_name':'b123'}));m.transport=Mock()
  current={'id':124,'tag_name':'b124','assets':[],'draft':False,'prerelease':False};changed={'id':123,'tag_name':'changed','assets':[],'draft':False,'prerelease':False}
  m.transport.json.side_effect=[[current],changed]
  releases=m._fetch_releases();self.assertEqual([x['id'] for x in releases],[124])
 def test_safe_zip_retains_notices_and_server(self):
  archive=self.home/'a.zip';out=self.home/'out';stage=self.home/'stage';stage.mkdir()
  with zipfile.ZipFile(archive,'w') as z:z.writestr('docs/LICENSE.txt','license');z.writestr('bin/'+executable_name(),b'fake')
  _extract(archive,out);_preserve_notices(out,stage,'a.zip');self.assertEqual((stage/'licenses/a.zip/docs/LICENSE.txt').read_text(),'license')
 def test_zip_case_collision_refused(self):
  archive=self.home/'a.zip'
  with zipfile.ZipFile(archive,'w') as z:z.writestr('file.txt','x');z.writestr('FILE.txt','x')
  with self.assertRaises(LlamaRuntimeError):_extract(archive,self.home/'out')
 def test_zip_symlink_refused(self):
  archive=self.home/'a.zip';entry=zipfile.ZipInfo('link');entry.create_system=3;entry.external_attr=(stat.S_IFLNK|0o777)<<16
  with zipfile.ZipFile(archive,'w') as z:z.writestr(entry,'outside')
  with self.assertRaises(LlamaRuntimeError):_extract(archive,self.home/'out')
 def test_tar_special_devices_refused(self):
  archive=self.home/'a.tar';entry=tarfile.TarInfo('device');entry.type=tarfile.CHRTYPE
  with tarfile.open(archive,'w') as t:t.addfile(entry)
  with self.assertRaises(LlamaRuntimeError):_extract(archive,self.home/'out')
 def test_tar_hardlink_refused(self):
  archive=self.home/'a.tar';entry=tarfile.TarInfo('link');entry.type=tarfile.LNKTYPE;entry.linkname='outside'
  with tarfile.open(archive,'w') as t:t.addfile(entry)
  with self.assertRaises(LlamaRuntimeError):_extract(archive,self.home/'out')
 def test_archive_size_budget_enforced(self):
  archive=self.home/'a.zip'
  with zipfile.ZipFile(archive,'w') as z:z.writestr('file',b'123456')
  with patch('vision.llama_runtime.MAX_EXTRACTED',5),self.assertRaises(LlamaRuntimeError):_extract(archive,self.home/'out')
 def test_bad_download_preserves_existing_runtime_and_never_executes(self):
  m=LlamaRuntimeManager(self.home);build=m.root/'build/bin';build.mkdir(parents=True);(build/executable_name()).write_text('old');m.meta.write_text('{"release":"old"}')
  a=self.asset()
  release={'id':123,'tag_name':'b123','assets':[a],'draft':False,'prerelease':False}
  with patch.object(m,'_fetch_releases',return_value=[release]),patch.object(m,'_select',return_value=(release,'cpu',a,[])),patch.object(m,'_download_asset',side_effect=LlamaRuntimeError('digest')),patch('vision.llama_runtime.subprocess.run') as run:
   with self.assertRaises(LlamaRuntimeError):m.install()
  run.assert_not_called();self.assertEqual((build/executable_name()).read_text(),'old');self.assertEqual(json.loads(m.meta.read_text())['release'],'old')
 def test_full_install_keeps_exact_license_and_metadata(self):
  data=io.BytesIO()
  with zipfile.ZipFile(data,'w') as z:z.writestr('bin/'+executable_name(),'fake');z.writestr('LICENSES/NOTICE','notice')
  archive=data.getvalue();a=self.asset(archive);m=LlamaRuntimeManager(self.home);m.transport=Mock();m.transport.open.side_effect=lambda url:Response(b'Permission is hereby granted (fixture license)' if 'raw.githubusercontent' in url else archive)
  release={'id':123,'tag_name':'b123','assets':[a],'draft':False,'prerelease':False}
  with patch.object(m,'_fetch_releases',return_value=[release]),patch.object(m,'_select',return_value=(release,'cpu',a,[])),patch('vision.llama_runtime.subprocess.run',return_value=subprocess.CompletedProcess([],0,'test')):
   m.install()
  meta=json.loads(m.meta.read_text());self.assertTrue(meta['upstream_digest_verified']);self.assertEqual(meta['release_id'],123);self.assertTrue((m.root/'build/licenses/llama.cpp/LICENSE').is_file());self.assertTrue((m.root/'build/licenses'/a['name']/'LICENSES/NOTICE').is_file())
 def test_runtime_metadata_failure_restores_old_build(self):
  data=io.BytesIO()
  with zipfile.ZipFile(data,'w') as z:z.writestr('bin/'+executable_name(),'new')
  a=self.asset(data.getvalue());m=LlamaRuntimeManager(self.home);old=m.root/'build/bin';old.mkdir(parents=True);(old/executable_name()).write_text('old');m.meta.write_text('{"release":"old"}')
  m.transport=Mock();m.transport.open.side_effect=lambda url:Response(b'Permission is hereby granted (fixture)' if 'raw.githubusercontent' in url else data.getvalue())
  release={'id':123,'tag_name':'b123','assets':[a],'draft':False,'prerelease':False}
  real_atomic=atomic_json
  def fail_meta(path,data):
   if Path(path)==m.meta:raise OSError('metadata error')
   return real_atomic(path,data)
  with patch.object(m,'_fetch_releases',return_value=[release]),patch.object(m,'_select',return_value=(release,'cpu',a,[])),patch('vision.llama_runtime.subprocess.run',return_value=subprocess.CompletedProcess([],0,'')),patch('vision.llama_runtime.atomic_json',side_effect=fail_meta):
   with self.assertRaises(OSError):m.install()
  self.assertEqual((old/executable_name()).read_text(),'old');self.assertEqual(json.loads(m.meta.read_text())['release'],'old')

class WebConfiguration42(unittest.TestCase):
 def test_server_has_bounded_threads_and_tls12(self):
  from core.web_server import make_server
  obj=types.SimpleNamespace();server=Mock(return_value=obj);adapter=Mock(return_value=types.SimpleNamespace(context=types.SimpleNamespace()))
  mods={'cheroot':types.ModuleType('cheroot'),'cheroot.wsgi':types.SimpleNamespace(Server=server),'cheroot.ssl':types.ModuleType('cheroot.ssl'),'cheroot.ssl.builtin':types.SimpleNamespace(BuiltinSSLAdapter=adapter)}
  mods['cheroot.server']=types.SimpleNamespace(HTTPConnection=type('Connection',(),{}),HTTPRequest=type('Request',(),{}))
  with patch.dict(sys.modules,mods):s=make_server(lambda e,r:[],'0.0.0.0',8298,tls=('cert','key'))
  import ssl
  self.assertEqual(server.call_args.kwargs['max'],24);self.assertEqual(s.ssl_adapter.context.minimum_version,ssl.TLSVersion.TLSv1_2)
 def test_development_web_server_not_used(self):
  self.assertNotIn('app.run(', (ROOT/'app.py').read_text());self.assertIn('from core.web_server import serve',(ROOT/'app.py').read_text())
 def test_web_dependency_not_in_ai_requirements(self):
  from scripts.install import direct_pins
  self.assertEqual(direct_pins(ROOT/'requirements-app.txt')['cheroot'],'11.1.2')
  self.assertNotIn('cheroot',direct_pins(ROOT/'requirements-sdxl.txt'))

class FirewallJournal42(unittest.TestCase):
 def test_shared_interpreter_warning_present(self):
  s=(ROOT/'static/edition.js').read_text();self.assertIn('altre applicazioni',s);self.assertIn('ripristin',s)
 def test_no_delete_by_display_name(self):
  s=(ROOT/'scripts/firewall_operation.ps1').read_text();self.assertNotIn('Remove-NetFirewallRule -DisplayName',s);self.assertIn('Equal-Snapshot',s);self.assertIn('changed since configuration',s)
 def test_journal_precedes_block_changes(self):
  s=(ROOT/'scripts/firewall_operation.ps1').read_text();self.assertLess(s.index('$script:J.disabled+=@($entry);Save-Journal'),s.index('$r|Disable-NetFirewallRule'))
 def test_not_windows_no_modification(self):
  from core.network_access import configure_firewall
  if os.name=='nt':self.skipTest('Non-Windows contract')
  with self.assertRaises(RuntimeError):configure_firewall(8298)
 def test_elevation_encodes_code_instead_of_loading_temp_script(self):
  s=(ROOT/'core/network_access.py').read_text();self.assertIn('-EncodedCommand',s);self.assertNotIn('-File ',s)

if __name__=='__main__':unittest.main()
