from pathlib import Path
import json,re,unittest
ROOT=Path(__file__).resolve().parents[1]
class FirstRun109(unittest.TestCase):
 def test_username_is_blank_on_fresh_setup(self):
  app=(ROOT/'app.py').read_text(encoding='utf-8'); launcher=(ROOT/'launcher.py').read_text(encoding='utf-8')
  self.assertIn('"username":""',app)
  self.assertIn("'username':'','password_hash':''",launcher)
  self.assertIn('request.method=="POST" else ""',app)
 def test_first_run_scroll_contract(self):
  html=(ROOT/'templates/first_run.html').read_text(encoding='utf-8'); css=(ROOT/'static/style.css').read_text(encoding='utf-8')
  self.assertIn('creator-first-run-page',html)
  self.assertIn('.creator-login-page.creator-first-run-page{display:block;min-height:100dvh;overflow-y:auto;',css)
  self.assertIn('.creator-first-run-page .creator-first-run-card{margin:0 auto}',css)
 def test_setup_copy_has_no_first_account_wording(self):
  html=(ROOT/'templates/first_run.html').read_text(encoding='utf-8'); loc=(ROOT/'static/first-run-locale.js').read_text(encoding='utf-8')
  self.assertNotIn('only for the first account',html)
  self.assertNotIn('only for the first account',loc)
  self.assertNotIn('solo per il primo account',loc)
  self.assertIn('Valid for 20 minutes. This local page refreshes the code automatically when it expires.',html)
 def test_twelve_languages_for_both_host_commands(self):
  s=(ROOT/'static/first-run-locale.js').read_text(encoding='utf-8')
  for src in ['SETUP-CODE.cmd can also rotate it manually.','creator-sdxl setup-code can also rotate it manually.']:
   self.assertIn(src,s)
  for lang in ['en','it','es','fr','de','pt','ru','zh','ja','ko','tr','ar']:
   self.assertGreaterEqual(s.count('"'+lang+'"'),2)
if __name__=='__main__':unittest.main()
