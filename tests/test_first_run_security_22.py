"""Host-issued first-account code, no Flask/GPU/model dependencies."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.first_run_security import (FirstRunCodes, SetupCodeError, normalize_code,
    local_setup_request, print_setup_code, CODE_TTL_SECONDS, MAX_ATTEMPTS, ALPHABET)
from core.runtime_env import atomic_json

class SetupCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.auth=self.root/'shared/config/creator_auth.json'
        atomic_json(self.auth,{'username':'C','password_hash':'','enabled':True})
        self.now=1000.0
        self.m=FirstRunCodes(self.auth,self.root/'secrets',lambda:self.now)
    def verify(self,code):
        with self.m.locked():self.m.verify_locked(code)
    def test_format_and_entropy_alphabet(self):
        self.assertEqual(len(ALPHABET),32)
        c=self.m.issue();self.assertEqual([len(x) for x in c.split('-')],[4]*6)
        self.assertEqual(len(normalize_code(c)),24)
    def test_code_accepted(self):self.verify(self.m.issue())
    def test_lowercase_whitespace_hyphens(self):
        c=self.m.issue();self.verify(' \t'+c.lower().replace('-',' - ')+ '\n')
    def test_issued_codes_differ(self):self.assertNotEqual(self.m.issue(),self.m.issue())
    def test_only_hash_on_disk(self):
        c=self.m.issue();text=self.m.state_path.read_text()
        self.assertNotIn(c,text);self.assertNotIn(normalize_code(c),text)
        self.assertEqual(len(json.loads(text)['digest']),64)
    def test_wrong_code_denied(self):
        self.m.issue()
        with self.assertRaises(SetupCodeError):self.verify('NOT-A-VALID-CODE')
    def test_missing_code_denied(self):
        self.m.issue()
        with self.assertRaises(SetupCodeError):self.verify('')
    def test_missing_state_denied(self):
        with self.assertRaises(SetupCodeError):self.verify('AAAA-'*5+'AAAA')
    def test_invalid_unicode_oversize_type_rejected(self):
        for v in (None,123,['A'], 'A'*1000,'Ä'*24,'Ａ'*24,'𝘈'*24,'0'*24,'1'*24):
            self.assertEqual(normalize_code(v),'')
    def test_expired(self):
        c=self.m.issue();self.now+=CODE_TTL_SECONDS
        with self.assertRaises(SetupCodeError):self.verify(c)
    def test_just_before_expiry(self):
        c=self.m.issue();self.now+=CODE_TTL_SECONDS-1;self.verify(c)
    def test_backwards_clock_denied(self):
        c=self.m.issue();self.now-=1
        with self.assertRaises(SetupCodeError):self.verify(c)
    def test_rotation_revokes_previous(self):
        old=self.m.issue();new=self.m.issue()
        with self.assertRaises(SetupCodeError):self.verify(old)
        self.verify(new)
    def test_revocation(self):
        c=self.m.issue()
        with self.m.locked():self.m.revoke_locked()
        with self.assertRaises(SetupCodeError):self.verify(c)
    def test_existing_account_blocks_issue_and_use(self):
        c=self.m.issue();atomic_json(self.auth,{'password_hash':'already-configured'})
        self.assertIsNone(self.m.issue());self.assertFalse(self.m.state_path.exists())
        with self.assertRaises(SetupCodeError):self.verify(c)
    def test_account_commit_blocks_replay_even_before_cleanup(self):
        c=self.m.issue();atomic_json(self.auth,{'password_hash':'hash'})
        self.assertTrue(self.m.state_path.exists())
        with self.assertRaises(SetupCodeError):self.verify(c)
    def test_corrupt_auth_fails_closed(self):
        for text in ('{','{}','[]','{"password_hash":42}'):
            self.auth.write_text(text)
            with self.assertRaises(RuntimeError):self.m.issue()
    def test_corrupt_state_fails_closed(self):
        c=self.m.issue()
        for text in ('{','{}','[]','{"schema":2}','null'):
            self.m.state_path.write_text(text)
            with self.assertRaises(SetupCodeError):self.verify(c)
    def test_nonfinite_expiry_denied(self):
        c=self.m.issue();state=json.loads(self.m.state_path.read_text());state['expires_at']=float('inf')
        self.m.state_path.write_text(json.dumps(state))
        with self.assertRaises(SetupCodeError):self.verify(c)
    def test_ten_bad_attempts_then_cooldown(self):
        c=self.m.issue()
        for _ in range(MAX_ATTEMPTS):
            with self.assertRaises(SetupCodeError) as e:self.verify('bad')
            self.assertEqual(e.exception.status,403)
        with self.assertRaises(SetupCodeError) as e:self.verify(c)
        self.assertEqual(e.exception.status,429);self.assertEqual(e.exception.retry_after,60)
        self.now+=60;self.verify(c)
    def test_failure_counter_shared_between_instances(self):
        c=self.m.issue();other=FirstRunCodes(self.auth,self.root/'secrets',lambda:self.now)
        for _ in range(MAX_ATTEMPTS):
            with other.locked():
                with self.assertRaises(SetupCodeError):other.verify_locked('bad')
        with self.assertRaises(SetupCodeError) as e:self.verify(c)
        self.assertEqual(e.exception.status,429)
    def test_verification_alone_does_not_consume_code(self):
        c=self.m.issue();self.verify(c);self.verify(c)
    def test_owner_only_permissions(self):
        self.m.issue()
        if os.name=='nt':
            self.assertTrue(self.m.state_path.is_file());return
        self.assertEqual(self.m.state_path.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.m.lock_path.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.m.secrets_dir.stat().st_mode & 0o777,0o700)
    def test_concurrent_commit_exactly_one_winner(self):
        c=self.m.issue();barrier=threading.Barrier(2);wins=[];errors=[]
        def submit(name):
            barrier.wait()
            try:
                with self.m.locked():
                    self.m.verify_locked(c)
                    time.sleep(.02)
                    atomic_json(self.auth,{'password_hash':'hash','username':name})
                    self.m.revoke_locked();wins.append(name)
            except SetupCodeError:pass
            except Exception as e:errors.append(repr(e))
        threads=[threading.Thread(target=submit,args=(x,)) for x in ('a','b')]
        for t in threads:t.start()
        for t in threads:t.join(3)
        self.assertFalse(any(t.is_alive() for t in threads));self.assertEqual(errors,[])
        self.assertEqual(len(wins),1);self.assertEqual(json.loads(self.auth.read_text())['username'],wins[0])
    def test_cross_process_account_commit_serialized(self):
        # Real OS lock across independent Python processes, not a mocked lock.
        c=self.m.issue()
        code='''import sys,time
from pathlib import Path
from core.first_run_security import FirstRunCodes,SetupCodeError
from core.runtime_env import atomic_json
m=FirstRunCodes(Path(sys.argv[1]),Path(sys.argv[2]),lambda:1000.0)
try:
 with m.locked():
  m.verify_locked(sys.argv[3]);time.sleep(.1)
  atomic_json(m.auth_path,{'password_hash':'configured','username':sys.argv[4]})
  m.revoke_locked()
 print('WIN')
except SetupCodeError:print('DENIED')
'''
        procs=[subprocess.Popen([sys.executable,'-c',code,str(self.auth),str(self.root/'secrets'),c,name],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for name in ('a','b')]
        results=[p.communicate(timeout=10) for p in procs]
        self.assertTrue(all(p.returncode==0 for p in procs),results)
        self.assertEqual(sorted(x[0].strip() for x in results),['DENIED','WIN'])
    def test_display_only_explicitly(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):c=self.m.issue()
        self.assertEqual(output.getvalue(),'')
        with contextlib.redirect_stdout(output):print_setup_code(c)
        self.assertIn(c,output.getvalue());self.assertIn('20',output.getvalue())

class LocalRequestTests(unittest.TestCase):
    def test_local_ipv4_ipv6_and_localhost(self):
        for addr,url in [('127.0.0.1','https://127.0.0.1:8498'),('::1','https://[::1]:8498'),('127.0.0.1','https://localhost:8498'),('::ffff:127.0.0.1','https://localhost')]:
            self.assertTrue(local_setup_request(addr,url,{}))
    def test_remote_even_if_host_spoofed(self):
        self.assertFalse(local_setup_request('192.168.1.20','https://localhost',{}))
    def test_local_peer_lan_host_needs_code(self):
        self.assertFalse(local_setup_request('127.0.0.1','https://192.168.1.5',{}))
    def test_forwarded_headers_never_bypass_code(self):
        for key in ('Forwarded','X-Forwarded-For','X-Forwarded-Host','X-Forwarded-Proto','X-Real-IP'):
            self.assertFalse(local_setup_request('127.0.0.1','https://localhost',{key:'127.0.0.1'}))
    def test_invalid_peer_or_hostname(self):
        for peer,host in [(None,'https://localhost'),('garbage','https://localhost'),('127.0.0.1','https://localhost.evil.test'),('127.0.0.1','https://[')]:
            self.assertFalse(local_setup_request(peer,host,{}))

class LauncherCodeTests(unittest.TestCase):
    def test_existing_first_run_forced_local_removed(self):
        # Complemented by real launcher/HTTP smoke tests, not treated as those.
        source=(ROOT/'launcher.py').read_text()
        self.assertNotIn('First account setup is local only',source)
        self.assertIn("'SDXL_STUDIO_SETUP_CODE_MANAGED':'1'",source)
    def test_windows_start_keeps_console_visible(self):
        source=(ROOT/'START.cmd').read_text().lower()
        self.assertIn('if not defined sdxl_no_pause pause',source)
    def test_shortcuts_forward_lan_option(self):
        self.assertIn('command.sh" start --lan',(ROOT/'start-lan.sh').read_text())
        self.assertIn('command.ps1" start --lan',(ROOT/'START-LAN.cmd').read_text())


class LauncherFlowTests(unittest.TestCase):
    def test_lan_launch_preserves_lan_and_passes_clear_code_only_to_supervisor_memory(self):
        import launcher
        with tempfile.TemporaryDirectory() as home:
            root=Path(home);shared=root/'shared'
            for name in ('config','logs','run'):(shared/name).mkdir(parents=True,exist_ok=True)
            auth=shared/'config/creator_auth.json';atomic_json(auth,{'password_hash':''})
            def cfg():return {'host':os.environ.get('SDXL_STUDIO_HOST_OVERRIDE','127.0.0.1'),'https':True,'port':8498,'image_port':8499,'training_port':8500,'identity_port':8501}
            output=io.StringIO()
            with patch.object(launcher,'SHARED_ROOT',shared),patch.object(launcher,'DATA_ROOT',root),patch.object(launcher,'running',return_value=None),patch.object(launcher,'initialize_environment'),patch.object(launcher,'init'),patch.object(launcher,'settings',side_effect=cfg),patch.object(launcher.socket,'socket'),patch.object(launcher,'ready',return_value=True),patch.object(launcher,'lan_ip',return_value='192.168.1.5'),patch.object(launcher.subprocess,'Popen') as proc,patch.dict(os.environ,{},clear=False),contextlib.redirect_stdout(output):
                proc.return_value.poll.return_value=None
                launcher.start(browser=False,mode='lan')
                self.assertEqual(os.environ['SDXL_STUDIO_HOST_OVERRIDE'],'0.0.0.0')
                env=proc.call_args.kwargs['env']
                self.assertEqual(env['SDXL_STUDIO_SETUP_CODE_MANAGED'],'1')
            self.assertIn('Access: LAN',output.getvalue())
            self.assertIn('https://192.168.1.5:8498',output.getvalue())
            code=output.getvalue().split('Codice / Code: ')[1].splitlines()[0]
            self.assertEqual(env.get('SDXL_STUDIO_FIRST_RUN_DISPLAY_CODE'),code);self.assertNotIn(code,(shared/'logs/launcher.log').read_text())
            m=FirstRunCodes(auth,root/'secrets')
            with m.locked():m.verify_locked(code)
    def test_remote_first_launch_without_https_denied(self):
        import launcher
        with tempfile.TemporaryDirectory() as home:
            shared=Path(home)/'shared';(shared/'config').mkdir(parents=True)
            atomic_json(shared/'config/creator_auth.json',{'password_hash':''})
            with patch.object(launcher,'SHARED_ROOT',shared),patch.object(launcher,'running',return_value=None),patch.object(launcher,'init'),patch.object(launcher,'settings',return_value={'host':'0.0.0.0','https':False}):
                with self.assertRaisesRegex(RuntimeError,'requires HTTPS'):launcher._start_locked(browser=False)
    def test_existing_account_starts_without_new_pairing_code(self):
        import launcher
        with tempfile.TemporaryDirectory() as home:
            root=Path(home);shared=root/'shared'
            for name in ('config','logs','run'):(shared/name).mkdir(parents=True,exist_ok=True)
            atomic_json(shared/'config/creator_auth.json',{'password_hash':'existing-hash'})
            cfg={'host':'127.0.0.1','https':True,'port':8498,'image_port':8499,'training_port':8500,'identity_port':8501}
            output=io.StringIO()
            with patch.object(launcher,'SHARED_ROOT',shared),patch.object(launcher,'DATA_ROOT',root),patch.object(launcher,'running',return_value=None),patch.object(launcher,'init'),patch.object(launcher,'settings',return_value=cfg),patch.object(launcher.socket,'socket'),patch.object(launcher,'ready',return_value=True),patch.object(launcher,'lan_ip',return_value=None),patch.object(launcher.subprocess,'Popen') as proc,contextlib.redirect_stdout(output):
                proc.return_value.poll.return_value=None
                launcher._start_locked(browser=False)
            self.assertNotIn('Codice / Code:',output.getvalue());self.assertFalse((root/'secrets/first-run-code.json').exists())
    def test_host_cli_rotation_works_without_restarting(self):
        with tempfile.TemporaryDirectory() as home:
            env={**os.environ,'SDXL_STUDIO_HOME':home,'SDXL_STUDIO_NO_BACKGROUND':'1','PYTHONDONTWRITEBYTECODE':'1'}
            env.pop('SDXL_STUDIO_HOST_OVERRIDE',None)
            codes=[]
            for _ in range(2):
                p=subprocess.run([sys.executable,str(ROOT/'run.py'),'launcher','setup-code'],cwd=ROOT,env=env,text=True,capture_output=True,timeout=15)
                self.assertEqual(p.returncode,0,p.stderr)
                codes.append(p.stdout.split('Codice / Code: ')[1].splitlines()[0])
            m=FirstRunCodes(Path(home)/'shared/config/creator_auth.json',Path(home)/'secrets')
            with m.locked():
                with self.assertRaises(SetupCodeError):m.verify_locked(codes[0])
                m.verify_locked(codes[1])
    def test_private_cancellation_or_password_reset_not_added_to_http(self):
        source=(ROOT/'app.py').read_text()
        self.assertNotIn('@app.get("/setup-code")',source)
        self.assertNotIn('@app.post("/setup-code")',source)

if __name__=='__main__':unittest.main(verbosity=2)
