import json,os,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from core.first_run_security import FirstRunCodes,CODE_TTL_SECONDS
from core.runtime_env import atomic_json

class WindowsFirstSetup107Tests(unittest.TestCase):
    def manager(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);auth=root/'shared/config/creator_auth.json'
        atomic_json(auth,{'username':'C','password_hash':'','enabled':True})
        now=[1000.0]
        return root,FirstRunCodes(auth,root/'secrets',lambda:now[0]),now

    def test_remaining_seconds_expires_without_plaintext_on_disk(self):
        root,m,now=self.manager();code=m.issue()
        self.assertEqual(m.remaining_seconds(code),CODE_TTL_SECONDS)
        text=m.state_path.read_text(encoding='utf-8')
        self.assertNotIn(code,text);self.assertNotIn(code.replace('-',''),text)
        now[0]+=CODE_TTL_SECONDS
        self.assertEqual(m.remaining_seconds(code),0)

    def test_local_page_has_live_code_polling_contract(self):
        template=(ROOT/'templates/first_run.html').read_text(encoding='utf-8')
        js=(ROOT/'static/first-run-code.js').read_text(encoding='utf-8')
        app=(ROOT/'app.py').read_text(encoding='utf-8')
        self.assertIn('data-local-setup-code',template)
        self.assertIn('setup_code_expires_in',template)
        self.assertIn('/static/first-run-code.js?v=1.0.18',template)
        self.assertIn("fetch('/api/first-run/local-code'",js)
        self.assertIn('@app.route("/api/first-run/local-code",methods=["GET","POST"])',app)
        self.assertIn('local_setup_request(request.remote_addr,request.host_url,request.headers)',app)
        self.assertIn('X-Zetalvx-Setup-Control',app)
        self.assertIn('_ensure_local_setup_code(rotate=rotate)',app)

    def test_host_control_secret_is_not_exposed_to_browser_script(self):
        js=(ROOT/'static/first-run-code.js').read_text(encoding='utf-8')
        self.assertNotIn('X-Zetalvx-Setup-Control',js)
        self.assertNotIn('creator_session_secret',js)

    def test_setup_code_cmd_uses_installed_stable_dispatcher(self):
        cmd=(ROOT/'SETUP-CODE.cmd').read_text(encoding='utf-8')
        self.assertIn('%LOCALAPPDATA%\\CreatorStudioSDXL',cmd)
        self.assertIn('\\bin\\creator-sdxl.cmd',cmd)
        self.assertIn('setup-code %*',cmd)
        self.assertNotIn('command.ps1',cmd)

    def test_installer_creates_stable_installed_setup_code_cmd(self):
        src=(ROOT/'scripts/install.py').read_text(encoding='utf-8')
        self.assertIn("(home/'SETUP-CODE.cmd').write_bytes",src)
        self.assertIn('creator-sdxl.cmd" setup-code',src)

    def test_setup_code_keeps_console_and_rotates_through_running_web(self):
        dispatch=(ROOT/'scripts/installed_command.py').read_text(encoding='utf-8')
        launcher=(ROOT/'launcher.py').read_text(encoding='utf-8')
        self.assertIn("creation={} if args[0]=='setup-code' else hidden_kwargs()",dispatch)
        self.assertIn("local+'/api/first-run/local-code'",launcher)
        self.assertIn("X-Zetalvx-Setup-Control",launcher)
        self.assertIn("if running():",launcher)
        self.assertIn("print_setup_code(setup_codes().issue())",launcher)
        self.assertIn("print_setup_code(_rotate_setup_code_through_web())",launcher)

    def test_auto_refresh_copy_is_localized_in_all_languages(self):
        import re
        js=(ROOT/'static/first-run-locale.js').read_text(encoding='utf-8')
        payload=re.search(r'const entries=(\[.*\]);\nC\.entries',js,re.S).group(1)
        entries=json.loads(payload)
        source='Valid for 20 minutes. This local page refreshes the code automatically when it expires. SETUP-CODE.cmd can also rotate it manually.'
        found=[e for e in entries if source in e.get('sources',[])]
        self.assertEqual(len(found),1)
        self.assertEqual(set(found[0]['text']),{'en','it','es','fr','de','pt','ru','zh','ja','ko','tr','ar'})
        self.assertTrue(all(v.strip() for v in found[0]['text'].values()))

if __name__=='__main__':unittest.main(verbosity=2)
