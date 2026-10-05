
import json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from core import sdxl_assets


def make_config(root:Path):
    for rel in sdxl_assets.BASE_REQUIRED:
        p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')


class SdxlAssets32(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        self.models=self.root/'models';self.models.mkdir()
        self.base=self.root/'base';self.inpaint=self.root/'inpaint'
        self.settings=lambda:{'sdxl_config':str(self.base),'inpaint_config':str(self.inpaint)}
    def tearDown(self):self.t.cleanup()
    def status(self,cfg):
        with patch.object(sdxl_assets,'MODELS_ROOT',self.models),patch.object(sdxl_assets,'settings',self.settings):
            return sdxl_assets.asset_status(cfg)
    def test_partial_install_reports_only_missing_component(self):
        cp=self.root/'custom.safetensors';cp.write_bytes(b'x');make_config(self.inpaint)
        s=self.status({'checkpoint':str(cp)})
        self.assertEqual(s['missing_components'],['base_config']);self.assertEqual(s['present_components'],2)
    def test_invalid_configured_path_is_not_hidden_by_default_file(self):
        d=self.models/'SDXL';d.mkdir();(d/'sd_xl_base_1.0.safetensors').write_bytes(b'x');make_config(self.base);make_config(self.inpaint)
        s=self.status({'checkpoint':str(self.root/'gone.safetensors')})
        self.assertIn('checkpoint',s['missing_components']);self.assertTrue(s['checkpoint']['default_exists'])
    def test_all_present_is_ready(self):
        cp=self.root/'custom.safetensors';cp.write_bytes(b'x');make_config(self.base);make_config(self.inpaint)
        s=self.status({'checkpoint':str(cp)});self.assertTrue(s['ready']);self.assertEqual(s['present_components'],3)
    def test_stale_running_state_becomes_interrupted(self):
        shared=self.root/'shared';shared.mkdir();models=self.root/'models2';models.mkdir()
        installer=sdxl_assets.SDXLBaseInstaller(shared,models,Path(__file__).resolve().parents[1])
        installer.state_file.parent.mkdir(parents=True,exist_ok=True)
        installer.state_file.write_text(json.dumps({'status':'running','pid':999999,'process_start':'old','updated_at':time.time()-20}))
        with patch.object(sdxl_assets,'MODELS_ROOT',models),patch.object(sdxl_assets,'settings',self.settings),patch.object(sdxl_assets,'process_start',return_value=None):
            s=installer.status({})
        self.assertEqual(s['status'],'interrupted');self.assertIn('Download missing',s['message'])

if __name__=='__main__':unittest.main()
