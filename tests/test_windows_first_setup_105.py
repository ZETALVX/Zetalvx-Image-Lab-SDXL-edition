import contextlib, io, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from core.first_run_security import FirstRunCodes, print_setup_code, CODE_TTL_SECONDS
from core.runtime_env import atomic_json

class WindowsFirstSetup105Tests(unittest.TestCase):
    def manager(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root=Path(tmp.name); auth=root/'shared/config/creator_auth.json'
        atomic_json(auth,{'username':'C','password_hash':'','enabled':True})
        now=[1000.0]
        return root,FirstRunCodes(auth,root/'secrets',lambda:now[0]),now

    def test_current_code_can_be_checked_without_plaintext_on_disk(self):
        root,m,now=self.manager(); code=m.issue()
        self.assertTrue(m.matches_current(code))
        text=m.state_path.read_text(encoding='utf-8')
        self.assertNotIn(code,text); self.assertNotIn(code.replace('-',''),text)
        self.assertEqual(len(json.loads(text)['digest']),64)

    def test_rotation_and_expiry_make_display_candidate_stale(self):
        root,m,now=self.manager(); old=m.issue(); new=m.issue()
        self.assertFalse(m.matches_current(old)); self.assertTrue(m.matches_current(new))
        now[0]+=CODE_TTL_SECONDS
        self.assertFalse(m.matches_current(new))

    def test_setup_code_command_contract_still_exists(self):
        self.assertIn('setup-code %*',(ROOT/'SETUP-CODE.cmd').read_text(encoding='utf-8'))
        self.assertIn("elif a.command=='setup-code':setup_code()",(ROOT/'launcher.py').read_text(encoding='utf-8'))

    def test_launcher_passes_clear_code_only_in_process_memory(self):
        src=(ROOT/'launcher.py').read_text(encoding='utf-8')
        self.assertIn("env['SDXL_STUDIO_FIRST_RUN_DISPLAY_CODE']=first_code",src)
        self.assertIn("if name!='web':",src)
        self.assertIn("child_env.pop('SDXL_STUDIO_FIRST_RUN_DISPLAY_CODE',None)",src)

    def test_installer_windows_tees_start_output(self):
        src=(ROOT/'scripts/install.py').read_text(encoding='utf-8')
        self.assertIn("if os.name=='nt':",src)
        self.assertIn("launcher_command(home,dest,*startargs,capture=True)",src)
        self.assertIn("_session_log(start_output)",src)

    def test_local_template_has_display_box_but_remote_input_remains(self):
        text=(ROOT/'templates/first_run.html').read_text(encoding='utf-8')
        self.assertIn('{% if setup_code_display %}',text)
        self.assertIn('{{ setup_code_display }}',text)
        self.assertIn('{% if code_required %}',text)
        self.assertIn('name="setup_code"',text)

if __name__=='__main__': unittest.main(verbosity=2)
