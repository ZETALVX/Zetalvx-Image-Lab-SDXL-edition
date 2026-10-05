import json,re,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
class Release100(unittest.TestCase):
 def test_version_and_dependencies_frozen(self):
  d=json.loads((ROOT/'UPDATE_PACKAGE.json').read_text());self.assertEqual(d['version'],'1.0.14');self.assertFalse(d['runtime_dependencies_changed']);self.assertEqual(d['dependency_baseline'],'0.1.0.53')
 def test_identity_selected_files_are_removable(self):
  s=(ROOT/'static/app.js').read_text();self.assertIn('data-identity-file-remove',s);self.assertIn("input.value=''",s);self.assertIn('new DataTransfer()',s)
 def test_training_refreshes_standard_lora_inventory(self):
  s=(ROOT/'static/app.js').read_text();self.assertIn('await api("/api/loras")',s);self.assertIn('@app.get("/api/loras")',(ROOT/'app.py').read_text())
 def test_checkpoint_promotion_is_idempotent(self):
  s=(ROOT/'core/training_manager.py').read_text();block=s[s.index('def promote_checkpoint'):s.index('def checkpoint_download_path')];self.assertNotIn('while dst.exists()',block);self.assertIn('already_promoted',block)
 def test_checkpoint_promotion_twice_reuses_same_file(self):
  from core import training_manager as t
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);jobs=r/'jobs';lora=r/'loras';jid='abc123def456';cp=jobs/jid/'checkpoints'/'step_000100';cp.mkdir(parents=True);lora.mkdir()
   (jobs/jid/'job.json').write_text(json.dumps({'id':jid,'name':'demo','mode':'lora'}));(jobs/jid/'progress.json').write_text('{}');(cp/'pytorch_lora_weights.safetensors').write_bytes(b'weights')
   with patch.multiple(t,JOBS=jobs,LORA_ROOT=lora,EXPORTS=r/'exports'):
    a=t.promote_checkpoint(jid,100);b=t.promote_checkpoint(jid,100)
    self.assertEqual(a['path'],b['path']);self.assertTrue(b['already_promoted']);self.assertEqual(len(list(lora.glob('*.safetensors'))),1)
 def test_downloads_use_common_attachment_response(self):
  s=(ROOT/'app.py').read_text();self.assertIn('def _download_attachment',s);self.assertIn("conditional=True",s);self.assertGreaterEqual(s.count('_download_attachment('),6)
 def test_installer_fresh_access_choice(self):
  sh=(ROOT/'scripts/bootstrap.sh').read_text();ps=(ROOT/'scripts/bootstrap.ps1').read_text();ins=(ROOT/'scripts/install.py').read_text();self.assertIn('[ACCESS] How should Zetalvx Image Lab be reachable?',sh);self.assertIn('[ACCESS] How should Zetalvx Image Lab be reachable?',ps);self.assertIn("access.add_argument('--local'",ins);self.assertIn("'0.0.0.0' if getattr(args,'lan',False) else '127.0.0.1'",ins)
 def test_release_links_github_and_keeps_apache(self):
  self.assertIn('https://github.com/ZETALVX',(ROOT/'templates/index.html').read_text());self.assertIn('Apache License', (ROOT/'LICENSE').read_text())
if __name__=='__main__':unittest.main()
