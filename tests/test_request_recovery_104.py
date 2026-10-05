"""Execute the shipped JavaScript transport with simulated network failures."""
import subprocess,shutil,unittest
from pathlib import Path
class RequestRecovery104(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node unavailable')
    def test_network_and_timeout_contracts(self):
        result=subprocess.run(['node',str(Path(__file__).with_name('request_recovery_104.cjs'))],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('"passed":12',result.stdout)
if __name__=='__main__':unittest.main(verbosity=2)
