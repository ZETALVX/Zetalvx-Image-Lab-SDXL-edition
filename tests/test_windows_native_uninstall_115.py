"""Focused 1.0.15 regression tests; OS-native tests are explicitly separate."""
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core import windows_uninstall
from core.app_uninstall import UninstallService
from core.install_layout import atomic_json, set_pointers, verify_manifest

class NativeUninstall115(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.home=self.base/'installed'; self.home.mkdir()
        self.report=self.base/'report'; self.report.mkdir()
        self.plan={'home':str(self.home),'installation_id':'install-115','purge_data':False}
        self.job='b'*32
        self.proc=Mock(pid=4321); self.proc.poll.return_value=None

    def launch(self):
        with patch('core.windows_uninstall.subprocess.Popen',return_value=self.proc) as popen, \
             patch('core.windows_uninstall.process_start',return_value='win-filetime-123'):
            value=windows_uninstall.launch(self.plan,ROOT,self.report,self.job)
        return value,popen.call_args

    def test_native_process_not_venv_redirector(self):
        (process,identity), call=self.launch()
        self.assertEqual(process,self.proc);self.assertEqual(identity,'win-filetime-123')
        self.assertTrue(call.args[0][0].endswith('powershell.exe'))
        self.assertNotIn('gui_uninstall.py',' '.join(call.args[0]))
        self.assertNotIn('python.exe',' '.join(call.args[0]))

    def test_visible_independent_worker(self):
        _,call=self.launch()
        self.assertEqual(call.kwargs['creationflags'],0x10)
        self.assertEqual(call.kwargs['cwd'],self.report)
        self.assertNotIn('stdout',call.kwargs) # console, not a hidden pipe held by the web worker

    def test_stages_both_files_outside_installation(self):
        self.launch()
        self.assertEqual((self.report/'cleanup.ps1').read_bytes(),(ROOT/'scripts/uninstall_windows.ps1').read_bytes())
        self.assertEqual((self.report/'uninstall_tree.cs').read_bytes(),(ROOT/'scripts/uninstall_tree.cs').read_bytes())
        self.assertEqual(list(self.home.iterdir()),[])

    def test_default_spec_preserves_data(self):
        self.launch();spec=json.loads((self.report/'spec.json').read_text())
        self.assertIs(spec['purge_data'],False);self.assertEqual(spec['id'],self.job)
        self.assertEqual(spec['schema'],'zetalvx.native-uninstall.v1')
        self.assertFalse(spec['recover_legacy'])

    def test_explicit_purge_survives_launch(self):
        self.plan['purge_data']=True;self.launch()
        self.assertIs(json.loads((self.report/'spec.json').read_text())['purge_data'],True)

    def test_no_credentials_written(self):
        self.launch();text=(self.report/'spec.json').read_text()
        self.assertNotIn('password',text);self.assertNotIn('challenge',text)

    def test_refuses_helper_within_removed_tree(self):
        self.report=self.home/'temp';self.report.mkdir()
        with self.assertRaisesRegex(ValueError,'outside'):
            windows_uninstall.launch(self.plan,ROOT,self.report,self.job)

    def test_refuses_helper_equal_to_removed_tree(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            windows_uninstall.launch(self.plan,ROOT,self.home,self.job)

    def test_no_identity_is_failure_not_success(self):
        self.proc.poll.return_value=1
        with patch('core.windows_uninstall.subprocess.Popen',return_value=self.proc), \
             patch('core.windows_uninstall.process_start',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'Cannot track'):
                windows_uninstall.launch(self.plan,ROOT,self.report,self.job)
        self.proc.terminate.assert_called_once()

    def test_powershell_launch_failure_is_propagated(self):
        with patch('core.windows_uninstall.subprocess.Popen',side_effect=OSError('cannot launch')):
            with self.assertRaisesRegex(OSError,'cannot launch'):
                windows_uninstall.launch(self.plan,ROOT,self.report,self.job)

    def test_old_runner_rejects_a_venv_redirector_child(self):
        # Reproduce the concrete defect in the old Python entry, without Windows:
        # launcher PID=100, actual executing interpreter PID=101.
        from scripts import gui_uninstall
        ticket={'id':self.job,'home':str(self.home),'source':str(ROOT),'status':'starting',
                'pid':100,'process_start':'launcher-start','created_at':0}
        with patch.object(sys,'argv',['gui_uninstall.py','--home',str(self.home),'--id',self.job]), \
             patch('scripts.gui_uninstall.read_ticket',return_value=(self.report/'job.json',ticket)), \
             patch('scripts.gui_uninstall.locked',return_value=contextlib.nullcontext()), \
             patch('scripts.gui_uninstall.time.sleep'), \
             patch('scripts.gui_uninstall.os.getpid',return_value=101):
            with self.assertRaisesRegex(ValueError,'not the authorised process'):
                gui_uninstall.main()

    def test_package_uninstall_does_not_require_active_dispatcher(self):
        cmd=(ROOT/'UNINSTALL.cmd').read_text()
        self.assertIn('uninstall_windows_entry.ps1',cmd)
        self.assertNotIn('command.ps1',cmd)
        self.assertIn('cd /d "%TEMP%"',cmd)

    def test_native_local_entry_has_explicit_data_confirmation(self):
        text=(ROOT/'scripts/uninstall_windows_entry.ps1').read_text()
        self.assertIn('$Purge=$false',text)
        self.assertIn('CONFIRM PERMANENT DELETION',text)
        self.assertIn('recover_legacy=$true',text)
        self.assertNotIn('bootstrap.ps1',text)

    def test_missing_legacy_marker_recovery_is_local_and_evidence_bound(self):
        text=(ROOT/'scripts/uninstall_windows_entry.ps1').read_text()
        self.assertIn('$Root -eq $DefaultRoot',text)
        self.assertIn('$Previous.purge_data -is [bool]',text)
        self.assertIn("$Previous.installation_id -match '^[a-f0-9]{32}$'",text)
        self.assertIn('[IO.FileMode]::CreateNew',text)
        self.assertLess(text.index('if ($Plan)'),text.index('if ($MarkerRecovery) {'))
        self.assertNotIn('MarkerRecovery',(ROOT/'core/windows_uninstall.py').read_text())

    def test_legacy_cleanup_takeover_requires_exact_identity_and_local_consent(self):
        text=(ROOT/'scripts/uninstall_windows.ps1').read_text()
        part=text[text.index('function Stop-LegacyCleanup'):text.index('function Get-LifecycleLocks')]
        self.assertIn('-not $Spec.recover_legacy',part)
        self.assertIn("$Old.engine -eq 'native-powershell-v1'",part)
        self.assertIn('$Cim.CommandLine -inotmatch $ScriptPattern',part)
        self.assertIn('$Cim.CommandLine -inotmatch $SpecPattern',part)
        self.assertIn('$Identity -ne $Old.cleanup_start',part)
        self.assertIn('GetOwnerSid',part)

    def test_delete_order_keeps_retry_controls_until_payload_is_removed(self):
        text=(ROOT/'scripts/uninstall_windows.ps1').read_text()
        fn=text[text.index('function Remove-InstallationPayload'):text.index('function Show-UninstallMessage')]
        self.assertLess(fn.index("@('runtime','versions'"),fn.index("@('bin','SETUP-CODE.cmd'"))
        self.assertLess(fn.index("@('bin','SETUP-CODE.cmd'"),fn.index('Remove-OwnedTree $Marker'))
        self.assertIn('[IO.Directory]::Delete($Root, $false)',fn)

    def test_only_owned_executable_processes_eligible(self):
        text=(ROOT/'scripts/uninstall_windows.ps1').read_text()
        self.assertIn('GetOwnerSid',text);self.assertIn('Test-UnderRoot ([string]$P.ExecutablePath) $Root',text)
        self.assertIn('$Identity -ne $Record.identity',text)
        self.assertNotIn('taskkill',text.lower())
        self.assertNotIn('Stop-Process -Name',text)

    def test_persistent_errors_and_finite_retries(self):
        text=(ROOT/'scripts/uninstall_windows.ps1').read_text()
        self.assertIn('$Attempt -le 5',text)
        self.assertIn('Timeout waiting for lifecycle lock:',text)
        self.assertIn("'result.json'",text);self.assertIn("'cleanup.log'",text)
        self.assertIn('Final verification failed:',text)

    def test_tree_removal_does_not_follow_reparse_points(self):
        text=(ROOT/'scripts/uninstall_tree.cs').read_text()
        self.assertLess(text.index('(attrs & FileAttributes.ReparsePoint)'),text.index('Directory.EnumerateFileSystemEntries(p)'))
        self.assertIn('RemoveLeaf(p,dir); return;',text)
        self.assertNotIn('Directory.Delete(p,true)',text)

    def test_failed_native_launch_clears_pending(self):
        source=self.home/'versions/1.0.15';source.mkdir(parents=True)
        atomic_json(self.home/'.zetalvx-install.json',{'schema':1,'product':'Zetalvx Creator Studio SDXL','id':'install-115','home':str(self.home)})
        set_pointers(self.home,'1.0.15',None)
        service=UninstallService(self.home,source)
        with patch('core.app_uninstall.windows_host',return_value=True), \
             patch('core.app_uninstall.lifecycle_locks',return_value=contextlib.nullcontext()), \
             patch('core.app_uninstall.check_idle_and_update'), \
             patch('core.app_uninstall.runtime_dirs',side_effect=AssertionError('Windows launch must not depend on Python runtime map')), \
             patch('core.windows_uninstall.launch',side_effect=RuntimeError('launch failed')):
            with self.assertRaisesRegex(RuntimeError,'launch failed'):service.start(False)
        self.assertFalse((self.home/'uninstall-pending.json').exists())

    def test_installer_copies_native_retry_entry(self):
        text=(ROOT/'scripts/install.py').read_text()
        self.assertIn("('uninstall_windows_entry.ps1','uninstall_windows.ps1','uninstall_tree.cs')",text)
        self.assertIn('bin\\\\uninstall_windows_entry.ps1',text)

class NativePowerShellChecks115(unittest.TestCase):
    @unittest.skipUnless(shutil.which('powershell.exe') or shutil.which('pwsh'),'PowerShell runtime unavailable on this test host')
    def test_powershell_parser(self):
        executable=shutil.which('powershell.exe') or shutil.which('pwsh')
        code="$fail=$false;foreach($p in $args){$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile($p,[ref]$t,[ref]$e)|Out-Null;if($e.Count){$e|Out-String|Write-Host;$fail=$true}};if($fail){exit 1}"
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'parse.ps1';path.write_text(code)
            subprocess.run([executable,'-NoProfile','-File',str(path),str(ROOT/'scripts/uninstall_windows.ps1'),str(ROOT/'scripts/uninstall_windows_entry.ps1'),str(ROOT/'tests/test_windows_native_uninstall_115.ps1')],check=True,timeout=30)

    @unittest.skipUnless(os.name=='nt','Native Windows filesystem/process tests require Windows; not simulated')
    def test_native_fixture_end_to_end(self):
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tests/test_windows_native_uninstall_115.ps1')],check=True,timeout=180)

if __name__=='__main__':unittest.main()
