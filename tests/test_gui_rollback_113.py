# Source export: validate source metadata, not the intentionally omitted installer payload.
import json, pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class GuiRollback113(unittest.TestCase):
 def test_contract(self):
  api=(ROOT/'core/app_update_api.py').read_text();host=(ROOT/'scripts/app_host_control.py').read_text();js=(ROOT/'static/app-updates.js').read_text();html=(ROOT/'templates/index.html').read_text();loc=(ROOT/'static/release-locale.js').read_text()
  self.assertIn("@app.post('/api/app-updates/rollback')",api)
  self.assertIn("'--action','rollback'",api);self.assertIn("choices=['stop','restart','rollback']",host);self.assertIn("scripts/control.py'),'rollback'",host)
  self.assertIn('id="appRollbackStart"',html);self.assertIn("request('/rollback'",js);self.assertIn('Previous version: {v}',loc)
  self.assertIn('1.0.18',html);self.assertEqual(json.loads((ROOT/'SOURCE_RELEASE.json').read_text())['application_code_version'],'1.0.18');self.assertFalse((ROOT/'UPDATE_PACKAGE.json').exists())
 def test_all_languages_for_rollback(self):
  loc=(ROOT/'static/release-locale.js').read_text()
  block=loc[loc.rfind('Previous version: {v}'):]
  for code in ('en','it','es','fr','de','pt','ru','zh','ja','ko','tr','ar'):self.assertIn('"'+code+'"',block)
if __name__=='__main__':unittest.main()
