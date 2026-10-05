"""1.0.1 regressions: Identity runtime completeness, headless Desktop prompt, mobile path wrapping."""
import importlib.util, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from core.desktop_shortcuts import desktop_choice
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('installer51',ROOT/'scripts/install.py')
installer=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(installer)

class IdentityHeadless51(unittest.TestCase):
    def test_identity_runtime_pins_complete(self):
        pins=installer.direct_pins(ROOT/'requirements-identity.txt')
        self.assertEqual(pins['insightface'],'1.0.1')
        self.assertEqual(pins['opencv-python-headless'],'4.12.0.88')
        self.assertIn('einops',pins);self.assertIn('scikit-image',pins)
    def test_cuda_uses_single_gpu_ort(self):
        pins=installer.identity_runtime_pins(ROOT,'cu126')
        self.assertEqual(pins['onnxruntime-gpu'],'1.20.2');self.assertNotIn('onnxruntime',pins)
    def test_cpu_uses_single_cpu_ort(self):
        pins=installer.identity_runtime_pins(ROOT,'cpu')
        self.assertEqual(pins['onnxruntime'],'1.20.2');self.assertNotIn('onnxruntime-gpu',pins)
    def test_runtime_match_requires_identity_packages(self):
        base={**installer.direct_pins(ROOT/'requirements-sdxl.txt'),**installer.TOOL_PINS}
        packages={k:v for k,v in base.items()};packages['torch']='2.14.0+cu126'
        info={'exists':True,'python':[3,11,16],'packages':packages}
        self.assertFalse(installer._runtime_matches_candidate(info,'sdxl','cu126'))
    def test_headless_linux_ask_does_not_prompt(self):
        if os.name=='nt':self.skipTest('Linux behavior')
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{},clear=True), \
             patch('core.desktop_shortcuts.graphical',return_value=False), \
             patch('core.desktop_shortcuts.dialog') as dialog:
            self.assertFalse(desktop_choice(Path(d),'ask'));dialog.assert_not_called()
    def test_graphical_linux_still_prompts(self):
        if os.name=='nt':self.skipTest('Linux behavior')
        with tempfile.TemporaryDirectory() as d, patch('core.desktop_shortcuts.graphical',return_value=True), \
             patch('core.desktop_shortcuts.dialog',return_value=True) as dialog:
            self.assertTrue(desktop_choice(Path(d),'ask'));dialog.assert_called_once()
    def test_mobile_identity_path_wrap_rule_present(self):
        css=(ROOT/'static/vision-ui.css').read_text()
        self.assertIn('#identityResolvedReport>button.ghost',css)
        self.assertIn('overflow-wrap:anywhere',css)
    def test_identity_smoke_requires_cv2_and_provider(self):
        src=(ROOT/'scripts/install.py').read_text()
        self.assertIn('import torch,cv2,onnx,scipy,skimage,einops,insightface',src)
        self.assertIn('CUDAExecutionProvider',src);self.assertIn('InferenceSession',src)
    def test_no_model_weights_are_installed(self):
        src=(ROOT/'scripts/install.py').read_text()
        section=src[src.index('def build_runtime'):src.index('def create_commands')]
        self.assertNotIn('buffalo_l',section);self.assertNotIn('antelopev2',section);self.assertNotIn('inswapper_128',section)
    def test_package_declares_runtime_dependency_change(self):
        d=json.loads((ROOT/'UPDATE_PACKAGE.json').read_text())
        self.assertFalse(d['runtime_dependencies_changed']);self.assertEqual(d['dependency_baseline'],'0.1.0.53')

if __name__=='__main__':unittest.main()
