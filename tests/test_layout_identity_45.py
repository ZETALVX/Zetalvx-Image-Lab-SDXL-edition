from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class LayoutIdentity45(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/'templates/index.html').read_text(encoding='utf-8')
        cls.css=(ROOT/'static/maintenance-ui.css').read_text(encoding='utf-8')
        cls.js=(ROOT/'static/app.js').read_text(encoding='utf-8')
    def test_mobile_create_is_locally_contained(self):
        self.assertIn('#view-image{width:100%;max-width:100%;min-width:0;overflow-x:clip}',self.css)
        self.assertIn('#view-image .task-tabs{max-width:100%;min-width:0;overflow-x:auto',self.css)
    def test_generate_hides_empty_input_panel(self):
        self.assertIn('$("#inputPanel")?.classList.toggle("hidden",!t.needsSource&&!t.needsMask&&!(t.refs||t.allowRefs));',self.js)
    def test_desktop_preview_stretches_with_controls(self):
        self.assertIn('#imageCreatorLayout{align-items:stretch!important}',self.css)
        self.assertIn('#imagePreviewColumn>.preview-card{display:flex;flex-direction:column;flex:1 1 auto;height:100%',self.css)
    def test_pure_swap_explains_no_sdxl(self):
        self.assertIn('Pure Face Swap uses InsightFace/ONNX and does not use an SDXL checkpoint.',self.html)
    def test_refine_has_own_model_slot(self):
        self.assertIn('id="identitySwapRefineModelSlot"',self.html)
        self.assertIn('id="identityInstantidModelSlot"',self.html)
        self.assertIn('function placeIdentitySdxlPanel()',self.js)
    def test_refine_checkbox_still_controls_backend_flag(self):
        self.assertIn("fd.append('refine_with_sdxl',$('#identitySwapRefine')?.checked?'true':'false')",self.js)
    def test_identity_model_payload_unchanged(self):
        self.assertIn("base_model:'identityBaseModel'",self.js)
    def test_identity_desktop_balanced(self):
        self.assertIn('#view-identity .identity-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important',self.css)

if __name__=='__main__':unittest.main()
