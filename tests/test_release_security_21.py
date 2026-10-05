"""Regression coverage for the 0.1.0.21 changes (no GPU/model downloads)."""
import ast, importlib.util, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.runtime_security import require_reviewed_torch, reviewed_torch_version
from core.http_security import is_loopback_client, same_origin
from core.platform_support import venv_python, process_start
from scripts.audit_runtime import advisory_key, audit, fetch_advisories
from scripts.release_check import verdict

class TorchFloorTests(unittest.TestCase):
    def test_old_releases_blocked(self):
        for v in ('1.13.0','2.5.1+cu121','2.6.0','2.9.1'):
            with self.subTest(v=v),self.assertRaises(RuntimeError):require_reviewed_torch(v)
    def test_patched_release_and_build_tags(self):
        for v in ('2.14.0','2.14.0+cpu','2.14.0+cu126','2.15.0'):
            self.assertEqual(require_reviewed_torch(v),v)
    def test_unknown_and_prerelease_blocked(self):
        for v in ('','custom','2.14','2.14.0rc1','2.15.0.dev1','2.14.0 garbage','v2.14.0'):
            self.assertFalse(reviewed_torch_version(v))
    def test_missing_torch_fails_closed(self):
        from importlib.metadata import PackageNotFoundError
        with patch('core.runtime_security.metadata.version',side_effect=PackageNotFoundError):
            with self.assertRaises(RuntimeError):require_reviewed_torch()
    def test_metadata_not_importing_torch(self):
        with patch('core.runtime_security.metadata.version',return_value='2.5.1'):
            with self.assertRaises(RuntimeError):require_reviewed_torch()
    def test_validator_has_no_unsafe_pickle_fallback(self):
        tree=ast.parse((ROOT/'core/training_manager.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_run_tensor_validator')
        src=ast.get_source_segment((ROOT/'core/training_manager.py').read_text(),fn)
        self.assertIn('weights_only=True',src);self.assertNotIn('weights_only=False',src)
        self.assertIn('gate+code',src);self.assertIn('require_reviewed_torch()',src)
    def test_worker_main_and_dispatch_gates(self):
        for name in ('services/image_worker.py','services/identity_worker.py','services/training_worker.py','vision/transformers_worker.py'):
            tree=ast.parse((ROOT/name).read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
            self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require_reviewed_torch' for n in ast.walk(fn)))
        self.assertIn('require_reviewed_torch()', (ROOT/'run.py').read_text())

class HTTPBoundaryTests(unittest.TestCase):
    def test_loopback_addresses(self):
        for a in ('127.0.0.1','127.0.0.2','::1','::ffff:127.0.0.1'):self.assertTrue(is_loopback_client(a))
    def test_remote_unknown_addresses(self):
        for a in ('192.168.1.3','10.0.0.5','8.8.8.8','::ffff:192.168.1.2',None,'localhost','127.0.0.1, 8.8.8.8'):self.assertFalse(is_loopback_client(a))
    def test_same_origins(self):
        for a in ('https://localhost:443','https://LOCALHOST','https://localhost/'):
            self.assertTrue(same_origin(a,'https://localhost/'))
    def test_ipv6_origin(self):self.assertTrue(same_origin('https://[::1]:8498','https://[::1]:8498/'))
    def test_cross_scheme_and_port(self):
        for a in ('http://localhost','https://localhost:444','https://evil.test','null','https://user:pass@localhost','https://localhost/evil','https://localhost?x=1','https://localhost:garbage'):
            self.assertFalse(same_origin(a,'https://localhost/'))
    def test_origin_optional_for_native_client(self):self.assertTrue(same_origin(None,'http://localhost/'))

class PortableBoundaryTests(unittest.TestCase):
    def test_linux_venv_path(self):self.assertEqual(venv_python('example',windows=False),Path('example/bin/python'))
    def test_windows_venv_path(self):self.assertEqual(venv_python('example',windows=True),Path('example/Scripts/python.exe'))
    def test_current_pid_identity(self):self.assertIsNotNone(process_start(os.getpid()))
    def test_nonexistent_pid(self):self.assertIsNone(process_start(999999999))
    def test_cross_process_lock(self):
        from core import file_lock
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'test.lock'
            with file.open('a+') as f:
                file_lock.flock(f,file_lock.LOCK_EX|file_lock.LOCK_NB)
                code="from core import file_lock as f;import sys\nwith open(sys.argv[1],'a+') as p:\n try:f.flock(p,f.LOCK_EX|f.LOCK_NB)\n except BlockingIOError:sys.exit(7)\n sys.exit(3)"
                p=subprocess.run([sys.executable,'-c',code,str(file)],cwd=ROOT,timeout=10)
                self.assertEqual(p.returncode,7)
                file_lock.flock(f,file_lock.LOCK_UN)
            with file.open('a+') as f:file_lock.flock(f,file_lock.LOCK_EX|file_lock.LOCK_NB)
    def test_certificate_self_signed_no_external_openssl(self):
        from core.local_certificate import generate_certificate
        from cryptography import x509
        with tempfile.TemporaryDirectory() as tmp:
            generate_certificate(tmp,'192.168.1.7')
            c=x509.load_pem_x509_certificate((Path(tmp)/'cert.pem').read_bytes())
            self.assertEqual(c.issuer,c.subject)
            self.assertFalse(c.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
            self.assertIn('localhost',c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
            if os.name!='nt':self.assertEqual((Path(tmp)/'key.pem').stat().st_mode&0o777,0o600)

class AuditGateTests(unittest.TestCase):
    def fake_inventory(self,version='2.14.0'):
        return {'state':'INVENTORIED','packages':[{'name':'torch','version':version}]}
    def test_public_torch_version(self):self.assertEqual(advisory_key({'name':'Torch','version':'2.10.0+cu126'}),('torch','2.10.0'))
    def test_malformed_package_not_a_url(self):
        with self.assertRaises(ValueError):advisory_key({'name':'../../private','version':'1.0'})
    def test_no_network_offline_and_no_clean_claim(self):
        def forbidden(_):raise AssertionError('Unexpected network check')
        with patch('scripts.audit_runtime.inventory',return_value=self.fake_inventory()):
            r=audit({'test':'dummy'},False,forbidden)
        self.assertEqual(r['result'],'INCOMPLETE');self.assertFalse(r['release_approved'])
    def test_old_torch_blocked_even_offline(self):
        with patch('scripts.audit_runtime.inventory',return_value=self.fake_inventory('2.5.1')):
            self.assertEqual(audit({'test':'dummy'})['result'],'BLOCKED')
    def test_network_unknown_is_not_clean(self):
        with patch('scripts.audit_runtime.inventory',return_value=self.fake_inventory()):
            r=audit({'test':'dummy'},True,lambda p:{'state':'UNKNOWN'})
        self.assertEqual(r['result'],'INCOMPLETE')
    def test_advisory_blocks(self):
        with patch('scripts.audit_runtime.inventory',return_value=self.fake_inventory()):
            r=audit({'test':'dummy'},True,lambda p:{'state':'ADVISORIES_FOUND'})
        self.assertEqual(r['result'],'BLOCKED')
    def test_no_feed_advisories_does_not_approve_release(self):
        with patch('scripts.audit_runtime.inventory',return_value=self.fake_inventory()):
            r=audit({'test':'dummy'},True,lambda p:{'state':'NO_KNOWN_ADVISORIES_IN_CHECKED_FEED'})
        self.assertEqual(r['result'],'NO_KNOWN_ADVISORIES_IN_CHECKED_FEED');self.assertFalse(r['release_approved'])
    def test_no_runtimes_incomplete(self):self.assertEqual(audit({},True)['result'],'INCOMPLETE')
    def test_skipped_tests_block_release(self):
        r=SimpleNamespace(testsRun=4,failures=[],errors=[],skipped=[('HTTP','Flask missing')],expectedFailures=[],unexpectedSuccesses=[],wasSuccessful=lambda:True)
        self.assertFalse(verdict(r)['gate_passed']);self.assertEqual(verdict(r)['passed'],3)
    def test_audit_feed_identity_and_withdrawn(self):
        payload={'info':{'name':'torch','version':'2.10.0'},'vulnerabilities':[{'id':'old','withdrawn':'2026-01-01'}]}
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*a):self.close()
        with patch('scripts.audit_runtime.build_opener') as opener:
            opener.return_value.open.return_value=Response(json.dumps(payload).encode())
            self.assertEqual(fetch_advisories({'name':'torch','version':'2.10.0+cpu'})['state'],'NO_KNOWN_ADVISORIES_IN_CHECKED_FEED')
    def test_bootstrap_plan_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'not-created'
            r=subprocess.run([sys.executable,str(ROOT/'scripts/bootstrap_candidate.py'),'--plan','--home',str(home)],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr);self.assertFalse(home.exists())
    def test_full_apache_license_present(self):
        text=(ROOT/'LICENSE').read_text()
        self.assertIn('Apache License',text);self.assertNotIn('PRIVATE COMMERCIAL CANDIDATE',text)
        self.assertEqual(text,(ROOT/'LICENSE.txt').read_text())

@unittest.skipUnless(importlib.util.find_spec('flask'),'Real HTTP boundary regressions require Flask; not a mocked pass')
class RealHTTP21Tests(unittest.TestCase):
    def request_in_isolated_app(self,body):
        with tempfile.TemporaryDirectory() as home:
            code='import app\napp.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)\nclient=app.app.test_client()\n'+body
            env={**os.environ,'SDXL_STUDIO_HOME':home,'SDXL_STUDIO_NO_BACKGROUND':'1'}
            p=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr)
    def test_remote_first_setup_rejected(self):
        self.request_in_isolated_app("r=client.post('/first-run',data={'password':'abcdefghijk','confirm_password':'abcdefghijk'},environ_overrides={'REMOTE_ADDR':'192.168.1.10'});assert r.status_code==403,r.status_code\nassert not app._load_auth_config()['password_hash']")
    def test_local_first_setup_allowed(self):
        self.request_in_isolated_app("client.get('/first-run')\nwith client.session_transaction() as session: csrf=session['first_run_csrf']\nr=client.post('/first-run',data={'first_run_csrf':csrf,'password':'abcdefghijk','confirm_password':'abcdefghijk'},environ_overrides={'REMOTE_ADDR':'127.0.0.1'});assert r.status_code==302,r.status_code\nassert app._load_auth_config()['password_hash']")
    def test_cross_origin_login_rejected(self):
        self.request_in_isolated_app("r=client.post('/login',headers={'Origin':'https://evil.test'});assert r.status_code==403,r.status_code")
    def test_response_headers(self):
        self.request_in_isolated_app("r=client.get('/api/health');assert r.headers['X-Content-Type-Options']=='nosniff';assert r.headers['X-Frame-Options']=='DENY'")
if __name__=='__main__':unittest.main()
