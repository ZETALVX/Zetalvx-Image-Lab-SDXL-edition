"""1.0.14: old GUI entry -> verified private bootstrap.

Guard tests use filesystem fixtures and supplied interpreter metadata. Transaction
regressions use the existing real-filesystem fixture with pip/GPU/services mocked;
they are not a fresh NVIDIA installation or native Windows acceptance.
"""
from __future__ import annotations
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from core import install_layout as layout
from scripts import install as installer

ROOT = Path(__file__).resolve().parents[1]

class PrivateUpdater101(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='creator updater ')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)/'CreatorStudioSDXL'
        self.base = self.home/'runtime/python/cpython-3.11.16'
        self.base_python = self.file(self.base/'bin/python3.11')
        self.old = self.home/'versions/0.1.0.53'; self.old.mkdir(parents=True)
        self.previous = self.home/'versions/0.1.0.52'; self.previous.mkdir()
        self.app = self.home/'runtime/app'
        self.app_python = self.file(self.app/'bin/python')
        self.sdxl = self.home/'runtime/sdxl'; self.file(self.sdxl/'bin/python')
        layout.set_pointers(self.home, self.old.name, self.previous.name)
        layout.write_runtime_map(self.home, self.old, {'app':self.app,'sdxl':self.sdxl})
    def file(self, path):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture'); return path
    def check(self, *, executable=None, prefix=None, base=None, release=True, windows=False):
        info=SimpleNamespace(executable=str(executable or self.app_python),
                             prefix=str(prefix or self.app), base_prefix=str(base or self.base))
        with patch.object(installer, 'sys', info):
            return installer.private_installer_context(self.home, self.old if release else None, windows=windows)
    def denied(self, **kw):
        with self.assertRaisesRegex(RuntimeError, 'Interpreti esterni'):
            self.check(**kw)
    def test_private_bootstrap_no_handoff(self):
        result=self.check(executable=self.base_python, prefix=self.base, release=False)
        self.assertEqual(result['kind'], 'bootstrap')
        self.assertEqual(result['python'], str(self.base_python.resolve()))
    def test_old_053_gui_app_uses_private_base(self):
        result=self.check()
        self.assertEqual(result['kind'], 'app-updater')
        self.assertEqual(result['python'], str(self.base_python.resolve()))
    def test_100_gui_app_uses_private_base(self):
        newer=self.home/'versions/1.0.0'; self.old.rename(newer); self.old=newer
        layout.set_pointers(self.home,'1.0.0',self.previous.name)
        self.assertEqual(self.check()['kind'], 'app-updater')
    def test_mapped_app_under_runtime_sets(self):
        other=self.home/'runtime/sets/0.1.0.53-saved/app'
        py=self.file(other/'bin/python')
        layout.write_runtime_map(self.home,self.old,{'app':other,'sdxl':self.sdxl})
        self.assertEqual(self.check(executable=py,prefix=other)['kind'], 'app-updater')
    @unittest.skipIf(os.name=='nt', 'POSIX venv symlink layout; Windows copy tested separately')
    def test_posix_venv_python_symlink_is_allowed(self):
        self.app_python.unlink(); self.app_python.symlink_to(self.base_python)
        self.assertEqual(self.check()['kind'], 'app-updater')
    def test_windows_venv_copy_with_spaces(self):
        base_py=self.file(self.base/'python.exe')
        app_py=self.file(self.app/'Scripts/python.exe')
        result=self.check(executable=app_py,windows=True)
        self.assertEqual(result['kind'], 'app-updater')
        self.assertEqual(result['python'], str(base_py.resolve()))
    def test_windows_bootstrap_layout(self):
        base_py=self.file(self.base/'python.exe')
        self.assertEqual(self.check(executable=base_py,prefix=self.base,windows=True,release=False)['kind'],'bootstrap')
    def test_system_prefix_cannot_hide_behind_private_filename(self):
        external=self.home.parent/'system'; external.mkdir()
        self.denied(base=external)
    def test_system_python_is_rejected(self):
        self.denied(executable=Path(sys.executable),prefix=Path(sys.prefix),base=Path(sys.base_prefix))
    def test_unmapped_runtime_is_rejected(self):
        other=self.home/'runtime/sets/unreferenced/app'; py=self.file(other/'bin/python')
        self.denied(executable=py,prefix=other)
    def test_sdxl_venv_cannot_install(self):
        self.denied(executable=self.sdxl/'bin/python',prefix=self.sdxl)
    def test_app_venv_requires_active_release(self):
        self.denied(release=False)
    def test_stale_release_is_rejected(self):
        layout.set_pointers(self.home,self.previous.name,None)
        self.denied()
    def test_prefix_lookalike_not_a_private_root(self):
        other=self.home/'runtime/python-external'; py=self.file(other/'bin/python3.11')
        self.denied(executable=py,prefix=other,base=other)
    def test_missing_base_executable_fails_without_download(self):
        self.base_python.unlink()
        self.denied()
    def test_unexpected_executable_name_is_rejected(self):
        py=self.file(self.app/'bin/not-python'); self.denied(executable=py)
    def test_app_executable_outside_bin_is_rejected(self):
        py=self.file(self.app/'other/python'); self.denied(executable=py)
    @unittest.skipIf(os.name=='nt', 'POSIX link fixture; native reparse-point checks need Windows')
    def test_private_root_symlink_escape_is_rejected(self):
        root=self.home/'runtime/python'; outside=self.home.parent/'external-python'
        root.rename(outside); root.symlink_to(outside,target_is_directory=True)
        self.denied()
    @unittest.skipIf(os.name=='nt', 'POSIX link fixture')
    def test_app_executable_symlink_escape_is_rejected(self):
        outside=self.file(self.home.parent/'external/python')
        self.app_python.unlink(); self.app_python.symlink_to(outside)
        self.denied()
    @unittest.skipIf(os.name=='nt', 'POSIX link fixture')
    def test_base_executable_symlink_escape_is_rejected(self):
        outside=self.file(self.home.parent/'external/python')
        self.base_python.unlink(); self.base_python.symlink_to(outside)
        self.denied()
    def test_environment_cannot_choose_the_bootstrap(self):
        with patch.dict(os.environ, {'SDXL_BOOTSTRAP_PYTHON':'/tmp/untrusted-python','PYTHON':'/tmp/python'}):
            self.assertEqual(self.check()['python'], str(self.base_python.resolve()))
    def test_read_only_plan_does_not_need_private_python(self):
        target=self.home.parent/'empty-home'
        result=subprocess.run([sys.executable,'-I',str(ROOT/'scripts/install.py'),'--plan','--home',str(target),
                               '--app-only','--resume-stage','none'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(target.exists())
    def test_relay_preserves_flags_no_shell_and_cleans_python_environment(self):
        context=self.check()
        argv=['install.py','--home',str(self.home),'--runtime','keep','--ai','cu126','--online','--no-browser']
        fake=SimpleNamespace(argv=argv)
        with patch.object(installer,'sys',fake), patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run, \
             patch.dict(os.environ,{'PYTHONPATH':'bad','PYTHONHOME':'bad','VIRTUAL_ENV':'bad'}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(installer.relaunch_private_installer(self.home,context),0)
        args, kw=run.call_args
        self.assertEqual(args[0], [context['python'],'-I',str(ROOT/'scripts/install.py'),*argv[1:]])
        self.assertNotIn('shell',kw); self.assertFalse(kw['check'])
        for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'): self.assertNotIn(key,kw['env'])
        self.assertEqual(kw['env']['SDXL_STUDIO_HOME'],str(self.home))
        self.assertNotIn('capture_output',kw)  # output is inherited by runner.log
    def test_relay_propagates_child_failure(self):
        with patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=2)), \
             patch.object(installer,'sys',SimpleNamespace(argv=['install.py'])), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(installer.relaunch_private_installer(self.home,self.check()),2)
    def test_old_gui_command_contract_unchanged(self):
        text=(ROOT/'scripts/gui_update.py').read_text()
        self.assertIn("cmd=[sys.executable,'-I',str(payload/'scripts/install.py')",text)
        self.assertIn("'--runtime','auto' if state.get('allow_new_runtime') else 'keep'",text)
        self.assertIn("'--online','--no-browser'",text)


class UpdateTransaction101(unittest.TestCase):
    """Actual file staging/maps/config snapshots; hardware/services/pip simulated."""
    def setUp(self):
        # Do not import the test class directly into this module: unittest would
        # discover and count the inherited baseline tests a second time.
        import test_installation_25 as fixtures
        self.fixtures=fixtures
        self.tx=fixtures.Transaction25Tests()
        self.tx.setUp(); self.addCleanup(self.tx.doCleanups)
        self.tx.actions={'app':'reuse','sdxl':'reuse'}
        new_old=self.tx.home/'versions/0.1.0.53'
        self.tx.old.rename(new_old); self.tx.old=new_old
        layout.set_pointers(self.tx.home,'0.1.0.53','0.1.0.18')
    def install(self):
        return installer.install(self.fixtures.arguments(home=self.tx.home,runtime='keep',resume_stage='none'))
    def test_053_update_keeps_runtimes_and_settings(self):
        self.assertEqual(self.install(),0)
        state=layout.pointers(self.tx.home)
        self.assertEqual(state,{'current':'1.0.14','previous':'0.1.0.53'})
        self.tx.assert_old_files()
        roots=layout.runtime_dirs(self.tx.home,self.tx.home/'versions/1.0.14')
        self.assertEqual(roots,self.tx.roots)
        self.assertFalse(any(c[0]=='build' for c in self.tx.calls))
    def test_100_update_keeps_runtimes(self):
        old=self.tx.home/'versions/1.0.0'; self.tx.old.rename(old); self.tx.old=old
        layout.set_pointers(self.tx.home,'1.0.0','0.1.0.18')
        self.assertEqual(self.install(),0)
        self.assertEqual(layout.pointers(self.tx.home),{'current':'1.0.14','previous':'1.0.0'})
        self.tx.assert_old_files()
        self.assertFalse(any(c[0]=='build' for c in self.tx.calls))
    def test_validation_failure_does_not_stop_current_release(self):
        self.tx.smoke_error=True
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(layout.pointers(self.tx.home)['current'],'0.1.0.53')
        self.assertFalse(any(c[0]=='stop' for c in self.tx.calls))
        self.tx.assert_old_files()
    def test_activation_failure_restores_configuration_and_old_release(self):
        self.tx.init_error=True
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(layout.pointers(self.tx.home),{'current':'0.1.0.53','previous':'0.1.0.18'})
        self.tx.assert_old_files()
        self.assertIn(('start','0.1.0.53','--no-browser','--lan'),self.tx.calls)
    def test_start_failure_restores_old_release(self):
        self.tx.start_error=True
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(layout.pointers(self.tx.home)['current'],'0.1.0.53')
        self.tx.assert_old_files()
    def test_app_handoff_precedes_mutation_and_return_code_propagates(self):
        with patch.object(installer,'private_installer_context',return_value={'kind':'app-updater'}), \
             patch.object(installer,'relaunch_private_installer',return_value=2) as relay:
            self.assertEqual(self.install(),2)
        relay.assert_called_once()
        self.assertEqual(self.tx.calls,[])
        self.assertFalse((self.tx.home/'versions/1.0.14').exists())
        self.assertFalse((self.tx.home/'install.lock').exists())
        self.tx.assert_old_files()

if __name__=='__main__': unittest.main()
