"""Executable client contracts; real application HTTP is tested separately."""
import json,shutil,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class IdentitySubmission111(unittest.TestCase):
 @unittest.skipUnless(shutil.which('node'),'Node unavailable')
 def test_real_js_file_snapshot_and_error_contracts(self):
  r=subprocess.run(['node',str(ROOT/'tests/identity_submit_111.cjs')],capture_output=True,text=True,timeout=10)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  self.assertEqual(json.loads(r.stdout)['passed'],20)
 def test_all_new_errors_localized(self):
  s=(ROOT/'static/identity-request-locale.js').read_text();rows=json.loads(s.split('push(...',1)[1].rsplit(');',1)[0])
  expected={'en','it','es','fr','de','pt','ru','zh','ja','ko','tr','ar'}
  self.assertEqual(len(rows),8)
  for r in rows:self.assertEqual(set(r['text']),expected);self.assertTrue(all(r['text'].values()))
 def test_unlock_does_not_call_mode_renderer(self):
  s=(ROOT/'static/app.js').read_text();block=s[s.index('async function sendIdentityForm'):s.index('function sweepVals')]
  self.assertIn('identitySubmissionInFlight=false',block)
  self.assertNotIn('setIdentityMode(identityMode())',block)
  self.assertNotIn('await pollIdentityLive',block)
 def test_no_delayed_onboarding_navigation(self):
  s=(ROOT/'static/edition.js').read_text();self.assertNotIn("setTimeout(()=>{showView('models')",s)
  s=(ROOT/'static/app.js').read_text();self.assertIn('sessionStorage.setItem(creatorViewKey,name)',s);self.assertIn("u.searchParams.delete('onboarding')",s)
  block=s[s.index('async function bootstrap(){'):s.index('// 0.1.0.26: selection')]
  self.assertLess(block.index('const startupView=rememberedCreatorView()'),block.index("setTask('generate')"));self.assertIn("showView(onboarding?'models':startupView)",block)
 @unittest.skipUnless(shutil.which('node'),'Node unavailable')
 def test_navigation_storage_and_onboarding_query(self):
  r=subprocess.run(['node',str(ROOT/'tests/navigation_111.cjs')],capture_output=True,text=True,timeout=10)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(json.loads(r.stdout)['passed'],7)
