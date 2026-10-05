import shutil,subprocess,unittest
from pathlib import Path
@unittest.skipUnless(shutil.which('node'),'Node is needed for actual client script logic tests')
class DownloadClient102(unittest.TestCase):
 def test_actual_script_fourteen_dom_fetch_cases(self):
  r=subprocess.run([shutil.which('node'),str(Path(__file__).with_name('file_downloads_102.cjs'))],capture_output=True,text=True,timeout=30)
  self.assertEqual(r.returncode,0,r.stdout+'\n'+r.stderr)
  self.assertEqual(r.stdout.count('PASS '),14)
