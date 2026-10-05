# Source export: version assertion matches the unchanged baseline HTML (1.0.18).
"""Static contract checks for the UI-only revision; browser behavior is tested separately.
Standard library only: does not require Flask, a browser, models or GPU.
"""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class Tags(HTMLParser):
    def __init__(self,text):
        super().__init__();self.tags=[];self.feed(text)
    def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs)

class UiRefinement25(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/'templates/index.html').read_text()
        cls.tags=Tags(cls.html).tags
        cls.ids=[a['id'] for _,a in cls.tags if 'id' in a]

    def test_no_duplicate_html_ids(self):
        self.assertEqual({k:v for k,v in Counter(self.ids).items() if v>1},{})

    def test_viewport_safe_area_enabled_without_disabling_zoom(self):
        meta=next(a for t,a in self.tags if t=='meta' and a.get('name')=='viewport')['content']
        self.assertIn('viewport-fit=cover',meta)
        self.assertNotIn('user-scalable=no',meta)
        self.assertNotIn('maximum-scale',meta)

    def test_refinement_styles_loaded_last(self):
        sheets=[a['href'] for t,a in self.tags if t=='link' and a.get('rel')=='stylesheet']
        self.assertTrue(sheets[-1].startswith('/static/maintenance-ui.css'))
        self.assertTrue(any(x.startswith('/static/ui-refinement.css') for x in sheets[:-1]))
        self.assertNotIn('bottom:0!important;padding-bottom:env(safe-area-inset-bottom)',(ROOT/'static/model-hub.css').read_text())

    def test_single_video_workflow_with_native_player_and_exact_preview_save(self):
        self.assertNotIn('frameExtractPanel',self.ids)
        self.assertEqual(self.ids.count('videoPickerPanel'),1)
        player=next(a for t,a in self.tags if a.get('id')=='pickerVideo')
        self.assertIn('controls',player);self.assertIn('playsinline',player)
        for key in ('pickerFirst','pickerLast','pickerSeconds','pickerPreview','pickerSave'):
            self.assertIn(key,self.ids)
        self.assertNotIn('frameExtractMode',(ROOT/'static/edition.js').read_text())

    def test_model_paths_precede_both_lists(self):
        paths=self.html.index('id="hubSdxlPaths"')
        sources=self.html.index('id="localSourcesPanel"')
        checkpoint=self.html.index('data-local-kind="checkpoint"')
        lora=self.html.index('data-local-kind="lora"')
        self.assertLess(paths,sources);self.assertLess(sources,checkpoint);self.assertLess(checkpoint,lora)

    def test_library_selector_and_accessible_switch_status(self):
        select=next((t,a) for t,a in self.tags if a.get('id')=='libraryProjectSelect')
        self.assertEqual(select[0],'select');self.assertIn('data-no-i18n',select[1])
        status=next(a for t,a in self.tags if a.get('id')=='projectSwitchStatus')
        self.assertEqual(status['aria-live'],'polite')

    def test_queue_reset_keeps_confirmation_and_explicit_danger_style(self):
        button=next(a for t,a in self.tags if a.get('id')=='cleanupJobs')
        self.assertIn('ghost',button['class']);self.assertIn('danger',button['class'])
        self.assertEqual(button['aria-describedby'],'jobsCleanupHelp')
        js=(ROOT/'static/app.js').read_text()
        self.assertIn("if(!confirm('Emergency cleanup:",js)
        self.assertIn("api('/api/jobs/cleanup',{method:'POST'})",js)

    def test_public_footer_and_user_guide_version(self):
        self.assertNotIn('Private candidate',self.html)
        self.assertIn('Licenze · Open source',self.html)
        self.assertIn('1.0.18',self.html)

if __name__=='__main__':unittest.main()
