import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class SourceDistributionTests(unittest.TestCase):
    def test_source_marker(self):
        d=json.loads((ROOT/'SOURCE_RELEASE.json').read_text(encoding='utf-8'))
        self.assertEqual(d['distribution'],'source')
        self.assertEqual(d['application_code_version'],'1.0.18')
        self.assertFalse(d['automatic_app_installer_included'])
        self.assertFalse(d['model_weights_included'])
        self.assertFalse(d['prebuilt_runtime_included'])
        self.assertFalse(d['packaged_update_payload'])

    def test_required_public_files(self):
        for rel in ('README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','docs/INSTALL_LINUX.md','docs/INSTALL_WINDOWS.md','docs/SOURCE_OPERATION.md','SECURITY.md','CONTRIBUTING.md'):
            self.assertTrue((ROOT/rel).is_file(),rel)

    def test_source_home_is_documented_separately(self):
        text=(ROOT/'README.md').read_text(encoding='utf-8')
        self.assertIn('CreatorStudioSDXL-Source',text)
        self.assertNotIn('source-1.0-rc',text.lower())

    def test_no_packaged_update_descriptor(self):
        self.assertFalse((ROOT/'UPDATE_PACKAGE.json').exists())

if __name__=='__main__':
    unittest.main()
