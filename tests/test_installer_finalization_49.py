import importlib.util, os, tempfile, unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('installer49',ROOT/'scripts/install.py')
installer=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(installer)

class InstallerFinalization49(unittest.TestCase):
    def test_linux_bootstrap_is_exact_private_python(self):
        s=(ROOT/'scripts/bootstrap.sh').read_text(encoding='utf-8')
        self.assertIn("PYTHON_VERSION='3.11.16'",s)
        self.assertIn("UV_VERSION='0.12.19'",s)
        self.assertIn('runtime/python',s)
        self.assertNotIn('python3.12; do',s)
        self.assertIn('System Python will not be used',s)
    def test_windows_bootstrap_is_exact_private_python(self):
        s=(ROOT/'scripts/bootstrap.ps1').read_text(encoding='utf-8')
        self.assertIn("$PythonVersion = '3.11.16'",s)
        self.assertIn("$UvVersion = '0.12.19'",s)
        self.assertIn('system_python_used_for_install=$false',s)
    def test_fresh_auto_backend_is_cuda_without_cpu_fallback(self):
        src=(ROOT/'scripts/install.py').read_text(encoding='utf-8')
        self.assertIn("backend = ('cu126' if '+cu' in old_torch else 'cpu') if old_torch else 'cu126'",src)
        self.assertNotIn("shutil.which('nvidia-smi') else 'cpu'",src)
    def test_torch_smoke_precedes_sdxl_dependencies(self):
        src=(ROOT/'scripts/install.py').read_text(encoding='utf-8')
        a=src.index("'--report',reports/'torch-install.json')")
        b=src.index('torch_smoke(py,release,reports,backend)',a)
        c=src.index("pip(py,reports,'sdxl-install'",b)
        self.assertLess(a,b);self.assertLess(b,c)
    def test_driver_preflight_precedes_runtime_build(self):
        src=(ROOT/'scripts/install.py').read_text(encoding='utf-8')
        install=src.index('def install(args):')
        a=src.index('gpu_preflight(report_dir,backend)',install)
        b=src.index('build_runtime(target,n,report_dir,backend',a)
        self.assertLess(a,b)
    def test_cpu_preflight_never_requires_gpu(self):
        with tempfile.TemporaryDirectory() as d:
            out=installer.gpu_preflight(Path(d),'cpu')
            self.assertEqual(out['status'],'NOT_REQUIRED')
            self.assertTrue((Path(d)/'gpu-preflight.json').is_file())
    def test_cuda_preflight_failure_is_explicit_and_audited(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(installer,'_nvidia_smi',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'[Nn]essun fallback CPU'):
                installer.gpu_preflight(Path(d),'cu126')
            self.assertTrue((Path(d)/'gpu-preflight.json').is_file())
    def test_cuda_preflight_success_records_driver(self):
        result=SimpleNamespace(returncode=0,stdout='NVIDIA GeForce RTX 3090, 580.00\n',stderr='')
        with tempfile.TemporaryDirectory() as d, mock.patch.object(installer,'_nvidia_smi',return_value='/fake/nvidia-smi'), mock.patch.object(installer.subprocess,'run',return_value=result), mock.patch.object(installer.ctypes,'CDLL',return_value=object()):
            out=installer.gpu_preflight(Path(d),'cu126')
            self.assertEqual(out['status'],'PASS');self.assertIn('RTX 3090',out['nvidia_smi_output'])
    def test_runtime_requirements_are_unchanged_from_baseline_scope(self):
        import hashlib
        expected={'requirements-app.txt':'fbfc1b6c1dc9759e9769f943e4cf4362ab8dca9332fd78fbd1fbd74cdeb9760f','requirements-sdxl.txt':'9d0a93435918c9129e205716752aae6e202648050ccdfe10bd40d984c8591f64','requirements-common.txt':'49745297b9ad486ab31d52586223dc0600011f880e00073848d5c5d2d34f4bf8'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)
        status=__import__('json').loads((ROOT/'RELEASE_STATUS.json').read_text())
        self.assertFalse(status['runtime_dependencies_changed'])

if __name__=='__main__':unittest.main()
