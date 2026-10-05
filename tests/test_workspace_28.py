# Source export: assert manual-source layout and metadata; retain case-collision/UI checks.
from pathlib import Path
from html.parser import HTMLParser
import unittest,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
class Nodes(HTMLParser):
    def __init__(self,text):super().__init__();self.stack=[];self.nodes=[];self.feed(text)
    def handle_starttag(self,t,a):
        a=dict(a);self.nodes.append((t,a,list(self.stack)))
        if t not in ['img','input','meta','link','br','hr','source']:self.stack.append((t,a))
    def handle_startendtag(self,t,a):self.handle_starttag(t,a)
    def handle_endtag(self,t):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==t:self.stack=self.stack[:i];break
class Workspace28(unittest.TestCase):
    def setUp(self):self.text=(ROOT/'templates/index.html').read_text();self.nodes=Nodes(self.text).nodes
    def get(self,id):return next(n for n in self.nodes if n[1].get('id')==id)
    def test_media_edit_is_closed_details(self):
        node=self.get('imageToolsPanel');self.assertEqual(node[0],'details');self.assertNotIn('open',node[1]);self.assertNotIn('open',self.get('videoPickerPanel')[1])
    def test_image_controls_all_inside_fold(self):
        for id in ['mtSource','mtUpload','mtUseActive','mtFields','mtRunBtn']:
            self.assertIn('imageToolsPanel',[a.get('id') for _,a in self.get(id)[2]])
    def test_queue_history_outside_config(self):
        for id in ['liveQueue','imageHistoryGrid']:
            parents=[a.get('id') for _,a in self.get(id)[2]]
            self.assertIn('imageOutputs',parents);self.assertNotIn('imageControlsColumn',parents);self.assertNotIn('imageCreatorLayout',parents)
    def test_layout_toggle_accessible(self):
        n=self.get('imageLayoutSwapBtn');self.assertEqual(n[0],'button');self.assertEqual(n[1]['aria-controls'],'imageCreatorLayout')
    def test_preview_and_controls_inside_only_upper_layout(self):
        for id in ['imagePreviewColumn','imageControlsColumn']:self.assertIn('imageCreatorLayout',[a.get('id') for _,a in self.get(id)[2]])
    def test_comparisons_advanced_only(self):self.assertIn('advanced-only',self.get('imageTestPanel')[1]['class'])
    def test_simple_preset_apply_remains(self):self.assertNotIn('advanced-only',self.get('workflowPresetSuite')[1]['class'])
    def test_mode_switch_notifies_without_reset(self):
        js=(ROOT/'static/app.js').read_text();part=js.split('function setImageUiMode(mode){',1)[1].split('function applyQuickStyle',1)[0]
        self.assertIn('imageuimodechange',part);self.assertNotIn('applyImagePreset',part);self.assertNotIn('activateClean',part)
    def test_presets_select_use_pane_on_simple(self):
        js=(ROOT/'static/preset-lab.js').read_text();self.assertIn("if(simple&&presetTab!=='use')setTab('use')",js)
    def test_updater_in_settings(self):self.assertIn('view-settings',[a.get('id') for _,a in self.get('appUpdatesPanel')[2]])
    def test_update_needs_explicit_trust_and_password(self):
        for id in ['appUpdateTrust','appUpdatePassword','appUpdateStart','appUpdateAllowRuntime']:self.get(id)
        self.assertEqual(self.get('appUpdatePassword')[1]['type'],'password');self.assertNotIn('checked',self.get('appUpdateAllowRuntime')[1])
    def test_guide_adds_update_and_clean_install(self):
        self.get('guide-updates');self.assertIn('un altro account',self.text);self.assertIn('non azzera',self.text)
    def test_logo_bytes_unchanged(self):self.assertEqual(hashlib.sha256((ROOT/'static/zetalvx-logo.png').read_bytes()).hexdigest(),'0a51cacfbd8d91d72794b5682e792b0dad192f747b5b614c8276bf8e2360f274')
    def test_no_duplicate_ids(self):
        ids=[a['id'] for _,a,_ in self.nodes if 'id' in a];self.assertEqual(len(ids),len(set(ids)))
    def test_source_has_no_case_colliding_paths(self):
        paths=[p.relative_to(ROOT).as_posix().casefold() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        self.assertEqual(len(paths),len(set(paths)))
        self.assertFalse((ROOT/'install.sh').exists());self.assertFalse((ROOT/'update.sh').exists())
        self.assertFalse((ROOT/'INSTALL.cmd').exists());self.assertFalse((ROOT/'UPDATE.cmd').exists());self.assertTrue((ROOT/'source.py').is_file())
    def test_descriptor_is_source_online_not_runtime(self):
        d=json.loads((ROOT/'SOURCE_RELEASE.json').read_text());self.assertEqual(d['application_code_version'],'1.0.18');self.assertEqual(d['distribution'],'source');self.assertFalse(d['prebuilt_runtime_included']);self.assertFalse(d['packaged_update_payload'])
if __name__=='__main__':unittest.main()
