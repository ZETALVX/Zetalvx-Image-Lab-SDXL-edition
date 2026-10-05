"""1.0.1 regressions: private ORT loader path, dependency aliases, interrupted-runtime rejection."""
import importlib.util, json, tempfile, unittest, subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('installer52',ROOT/'scripts/install.py')
installer=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(installer)
from core.private_cuda_env import private_cuda_env, private_cuda_library_dirs

class IdentityRuntime52(unittest.TestCase):
    def test_private_linux_cuda_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);py=root/'bin/python';py.parent.mkdir();py.touch()
            cudnn=root/'lib/python3.11/site-packages/nvidia/cudnn/lib';cudnn.mkdir(parents=True)
            torchlib=root/'lib/python3.11/site-packages/torch/lib';torchlib.mkdir(parents=True)
            dirs=private_cuda_library_dirs(py,platform_name='posix')
            self.assertIn(cudnn,dirs);self.assertIn(torchlib,dirs)
            env=private_cuda_env(py,{'LD_LIBRARY_PATH':'/host'},platform_name='posix')
            self.assertTrue(env['LD_LIBRARY_PATH'].startswith(str(cudnn)))
            self.assertTrue(env['LD_LIBRARY_PATH'].endswith('/host'))
    def test_private_windows_cuda_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);py=root/'Scripts/python.exe';py.parent.mkdir();py.touch()
            cudnn=root/'Lib/site-packages/nvidia/cudnn/bin';cudnn.mkdir(parents=True)
            env=private_cuda_env(py,{'PATH':'C:\\Windows'},platform_name='nt')
            self.assertTrue(env['PATH'].startswith(str(cudnn)+';'))
    def test_runtime_marker_required_for_reuse(self):
        base={**installer.direct_pins(ROOT/'requirements-sdxl.txt'),**installer.TOOL_PINS,**installer.identity_runtime_pins(ROOT,'cu126')}
        base['torch']='2.14.0+cu126'
        info={'exists':True,'python':[3,11,16],'packages':base,'runtime_marker':{}}
        self.assertFalse(installer._runtime_matches_candidate(info,'sdxl','cu126'))
        info['runtime_marker']={'identity_runtime_schema':2,'backend':'cu126'}
        self.assertTrue(installer._runtime_matches_candidate(info,'sdxl','cu126'))
    def test_final_sdxl_check_is_alias_aware(self):
        src=(ROOT/'scripts/install.py').read_text()
        self.assertIn("pip(exe,report_dir,key+'-final-pip-check','check')",src)
        self.assertIn("identity_aliases=label.startswith('sdxl-')",src)
    def test_selected_runtime_identity_smoked_before_activation(self):
        src=(ROOT/'scripts/install.py').read_text()
        self.assertIn('identity_smoke(ai,dest,report_dir,backend)',src)
        self.assertLess(src.index('identity_smoke(ai,dest,report_dir,backend)',src.index('write_runtime_map(home,dest')), src.index('# Also check the old workers'))
    def test_installer_smoke_uses_private_cuda_env(self):
        src=(ROOT/'scripts/install.py').read_text()
        self.assertIn("env=private_cuda_env(Path(py),environment(home_path()))",src)
    def test_launcher_identity_uses_private_cuda_env(self):
        src=(ROOT/'launcher.py').read_text()
        self.assertIn("if name=='identity': child_env=private_cuda_env(Path(exe),child_env)",src)
    def test_no_system_cuda_install_commands(self):
        text=(ROOT/'scripts/install.py').read_text()+(ROOT/'core/private_cuda_env.py').read_text()
        for bad in ('apt install','apt-get install','/usr/local/cuda','setx PATH','ldconfig'):
            self.assertNotIn(bad,text)
    def test_alias_check_accepts_only_reviewed_identity_substitutions(self):
        output=("insightface 1.0.1 requires onnxruntime, which is not installed.\n"
                "insightface 1.0.1 requires opencv-python, which is not installed.\n")
        result=subprocess.CompletedProcess([],1,output,'')
        with tempfile.TemporaryDirectory() as d, \
             patch.object(installer,'assert_private_runtime_python',return_value={'python':'x','prefix':'x'}), \
             patch.object(installer,'inventory',return_value={'packages':{'onnxruntime-gpu':'1.20.2','opencv-python-headless':'4.12.0.88'}}), \
             patch.object(installer.subprocess,'run',return_value=result):
            installer.pip_check(Path(d)/'python',Path(d),'alias-check',identity_aliases=True)
    def test_alias_check_rejects_unrelated_dependency_breakage(self):
        result=subprocess.CompletedProcess([],1,'other 1.0 requires missing, which is not installed.\n','')
        with tempfile.TemporaryDirectory() as d, \
             patch.object(installer,'assert_private_runtime_python',return_value={'python':'x','prefix':'x'}), \
             patch.object(installer,'inventory',return_value={'packages':{'onnxruntime-gpu':'1.20.2','opencv-python-headless':'4.12.0.88'}}), \
             patch.object(installer.subprocess,'run',return_value=result):
            with self.assertRaises(RuntimeError):installer.pip_check(Path(d)/'python',Path(d),'alias-check',identity_aliases=True)
    def test_dependency_baseline_bumped(self):
        d=json.loads((ROOT/'UPDATE_PACKAGE.json').read_text())
        self.assertEqual(d['version'],'1.0.14');self.assertEqual(d['dependency_baseline'],'0.1.0.53')

if __name__=='__main__':unittest.main()
