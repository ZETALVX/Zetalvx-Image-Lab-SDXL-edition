# Source export: cache-buster expectation aligned to unchanged Windows 1.0.16 input templates (1.0.18).
"""Release-specific UI/branding contracts. No app import or installed-data access."""
from pathlib import Path
from html.parser import HTMLParser
import unittest,hashlib,struct
ROOT=Path(__file__).resolve().parents[1]
class Tree(HTMLParser):
    def __init__(self,source):super().__init__();self.nodes=[];self.feed(source)
    def handle_starttag(self,tag,attrs):self.nodes.append((tag,dict(attrs)))
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs)
class ReleaseUi27(unittest.TestCase):
    def setUp(self):self.html=(ROOT/'templates/index.html').read_text();self.nodes=Tree(self.html).nodes
    def node(self,id):return next((tag,attr) for tag,attr in self.nodes if attr.get('id')==id)
    def test_single_preset_workspace(self):
        self.assertEqual(sum(1 for tag,a in self.nodes if a.get('id')=='workflowPresetSuite'),1)
        self.assertNotIn('advanced-only',self.node('workflowPresetSuite')[1]['class'])
    def test_retired_controls_not_visible(self):self.assertIn('hidden',self.node('legacyPresetControls')[1]);self.assertEqual(self.node('legacyPresetControls')[1]['aria-hidden'],'true')
    def test_use_save_manage_tabs(self):
        tabs=[a.get('data-preset-tab') for _,a in self.nodes if 'data-preset-tab' in a];self.assertEqual(tabs,['use','save','manage'])
    def test_custom_and_automatic(self):self.assertIn('data-test-mode',self.node('testModeAutomatic')[1]);self.assertIn('data-test-mode',self.node('testModeCustom')[1])
    def test_confirmation_dialog_present(self):self.assertEqual(self.node('imageTestPreview')[1]['role'],'dialog');self.assertEqual(self.node('imageTestPreview')[1]['aria-modal'],'true')
    def test_guide_all_sections(self):
        keys=[a.get('data-guide-key') for _,a in self.nodes if 'data-guide-key' in a]
        for key in ['start','create','presets','scope','recipes','tests','seed','models','identity','training','library','tools','access']:self.assertIn(key,keys)
    def test_brand_header_does_not_repeat_edition(self):self.assertIn('ZETALVX IMAGE LAB</b>',self.html);self.assertNotIn('ZETALVX IMAGE LAB - SDXL EDITION</b>',self.html);self.assertIn('SDXL Edition · 1.0',self.html)
    def test_brand_home_not_external(self):
        tag,a=next((t,a) for t,a in self.nodes if 'brand-home-link' in a.get('class',''))
        self.assertEqual(tag,'button');self.assertEqual(a['data-goto'],'home');self.assertNotIn('href',a)
    def test_logo_rgba_png(self):
        data=(ROOT/'static/zetalvx-logo.png').read_bytes();self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n');self.assertEqual(data[25],6)
        self.assertEqual(struct.unpack('>II',data[16:24]),(1254,1254))
    def test_logo_containers_have_no_backing(self):
        css=(ROOT/'static/release-polish.css').read_text();self.assertIn('background:transparent!important;border:0!important;box-shadow:none!important',css)
    def test_new_static_assets_cache_busted(self):
        for t,a in self.nodes:
            for key in ['src','href']:
                value=a.get(key,'')
                if value.startswith('/static/') and any(x in value for x in ['.js','.css','.png']):self.assertIn('?v=1.0.18',value)
    def test_preview_uses_separate_endpoint(self):
        js=(ROOT/'static/preset-lab.js').read_text();self.assertIn('/api/image/auto-test/preview',js);self.assertIn('if(submitting||!snapshot)return',js)

if __name__=='__main__':unittest.main()
