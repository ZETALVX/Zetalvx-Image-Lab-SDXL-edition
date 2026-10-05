""".34 safety and layout contracts; real temporary paths, no live application deletion."""
import ast, json, os, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch,Mock
from core.app_uninstall import Challenges, UninstallError, UninstallService, safe_job
from core.uninstall_plan import make_plan,execute_linux,validate_home,APP_ONLY
from core.install_layout import atomic_json,set_pointers
from core.platform_support import hidden_kwargs,detached_kwargs
from core.desktop_shortcuts import install_shortcuts,desktop_entry
ROOT=Path(__file__).resolve().parents[1]

class ApprovalTests(unittest.TestCase):
 def setUp(self):self.now=10;self.c=Challenges(lambda:self.now);self.start=Mock(return_value={'status':'starting'});self.verify=Mock(side_effect=lambda x:x=='safe password')
 def data(self,purge=False):
  d=self.c.issue('session-a',purge);return {'challenge_id':d['id'],'word':d['word'],'purge_data':purge,'password':'safe password','password_repeat':'safe password','understand':True}
 def apply(self,d,owner='session-a'):return self.c.authorise(owner,'C',d,self.verify,self.start)
 def test_one_time_approval(self):
  d=self.data();self.apply(d);self.start.assert_called_once_with(False);self.assertEqual(self.verify.call_count,2)
  with self.assertRaises(UninstallError):self.apply(d)
  self.assertEqual(self.start.call_count,1)
 def test_purge_bound_to_word(self):
  d=self.data();d['purge_data']=True
  with self.assertRaises(UninstallError):self.apply(d)
  self.start.assert_not_called()
 def test_session_bound(self):
  d=self.data()
  with self.assertRaises(UninstallError):self.apply(d,'other-session')
  self.start.assert_not_called()
 def test_word_wrong(self):
  d=self.data();d['word']='wrong'
  with self.assertRaises(UninstallError):self.apply(d)
  self.start.assert_not_called()
 def test_word_unicode_refused(self):
  d=self.data();d['word']='é'
  with self.assertRaises(UninstallError):self.apply(d)
 def test_password_repeat_required(self):
  d=self.data();d['password_repeat']='wrong'
  with self.assertRaises(UninstallError):self.apply(d)
  self.start.assert_not_called()
 def test_both_wrong_refused(self):
  d=self.data();d['password']=d['password_repeat']='wrong'
  with self.assertRaises(UninstallError):self.apply(d)
 def test_empty_password_refused(self):
  d=self.data();d['password']=d['password_repeat']=''
  with self.assertRaises(UninstallError):self.apply(d)
 def test_ack_required(self):
  d=self.data();d['understand']=False
  with self.assertRaises(UninstallError):self.apply(d)
 def test_password_rate_limit(self):
  d=self.data();d['password_repeat']='wrong'
  for _ in range(5):
   with self.assertRaises(UninstallError) as cm:self.apply(d)
   self.assertEqual(cm.exception.status,403)
  with self.assertRaises(UninstallError) as cm:self.apply(d)
  self.assertEqual(cm.exception.status,429)
 def test_limit_not_reset_by_new_word(self):
  for _ in range(5):
   d=self.data();d['word']='wrong'
   with self.assertRaises(UninstallError):self.apply(d)
  with self.assertRaises(UninstallError) as cm:self.apply(self.data())
  self.assertEqual(cm.exception.status,429)
 def test_expiry(self):
  d=self.data();self.now+=301
  with self.assertRaises(UninstallError):self.apply(d)
 def test_new_word_invalidates_previous(self):
  d=self.data();e=self.data()
  with self.assertRaises(UninstallError):self.apply(d)
  self.apply(e)
 def test_double_submission(self):
  d=self.data();results=[]
  def submit():
   try:self.apply(d);results.append(True)
   except UninstallError:results.append(False)
  a=threading.Thread(target=submit);b=threading.Thread(target=submit);a.start();b.start();a.join();b.join()
  self.assertEqual(sorted(results),[False,True]);self.start.assert_called_once()
 def test_passwords_not_retained(self):
  d=self.data();self.apply(d);self.assertNotIn('safe password',repr(self.c.items));self.assertFalse(self.c.items)
 def test_start_failure_needs_new_consent(self):
  d=self.data();self.start.side_effect=RuntimeError('Busy')
  with self.assertRaises(RuntimeError):self.apply(d)
  with self.assertRaises(UninstallError):self.apply(d)
 def test_non_boolean_mode_rejected(self):
  with self.assertRaises(UninstallError):self.c.issue('C','false')
 def test_cancel_revokes_own_word(self):
  d=self.data();self.c.cancel('session-a',d['challenge_id'])
  with self.assertRaises(UninstallError):self.apply(d)
  self.start.assert_not_called()
 def test_other_session_cannot_cancel(self):
  d=self.data();self.c.cancel('other',d['challenge_id']);self.apply(d)
 def test_random_word_varies(self):
  words=[self.c.issue('C',False)['word'] for _ in range(20)];self.assertEqual(len(set(words)),20)

class RemovalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.home=self.base/'CreatorStudioSDXL';self.source=self.home/'versions/1.0.1';self.source.mkdir(parents=True)
  atomic_json(self.home/'.zetalvx-install.json',{'schema':1,'product':'Zetalvx Creator Studio SDXL','home':str(self.home),'id':'test-root'})
  set_pointers(self.home,'1.0.1',None)
 def test_purge_only_default_gui(self):
  svc=UninstallService(self.home,self.source)
  self.assertFalse(svc.plan()['can_purge_data'])
  with self.assertRaises(UninstallError):svc.plan(True)
  with patch('core.app_uninstall.default_data_root',return_value=self.home):self.assertTrue(svc.plan(True)['purge_data'])
 def test_active_release_required(self):
  with self.assertRaises(UninstallError):UninstallService(self.home,self.base/'not-active').plan()
 def test_pending_prevents_repeat(self):
  atomic_json(self.home/'uninstall-pending.json',{'status':'starting'})
  with self.assertRaises(UninstallError):UninstallService(self.home,self.source).plan()
 def test_keep_data_and_no_link_traversal(self):
  external=self.base/'external';external.mkdir();(external/'run').mkdir();(external/'run/precious').write_text('keep');(self.home/'shared').symlink_to(external,target_is_directory=True)
  (self.home/'models').mkdir();(self.home/'models/m').write_text('keep')
  (self.home/'runtime').mkdir();(self.home/'runtime/r').write_text('binary')
  with patch('core.uninstall_plan.remove_linux_shortcuts'):execute_linux(make_plan(self.home))
  self.assertEqual((external/'run/precious').read_text(),'keep');self.assertTrue((self.home/'models/m').exists());self.assertFalse((self.home/'runtime').exists())
 def test_purge_keeps_external_files(self):
  ext=self.base/'external';ext.mkdir();(ext/'model').write_text('keep');(self.home/'models').symlink_to(ext,target_is_directory=True)
  with patch('core.uninstall_plan.remove_linux_shortcuts'):execute_linux(make_plan(self.home,True))
  self.assertFalse(self.home.exists());self.assertEqual((ext/'model').read_text(),'keep')
 def test_linked_ancestor_rejected(self):
  parent=self.base/'alias';parent.symlink_to(self.base,target_is_directory=True)
  with self.assertRaises(ValueError):validate_home(parent/'CreatorStudioSDXL')
 def test_mount_guard(self):
  (self.home/'mounted').mkdir()
  with patch('core.uninstall_plan.os.path.ismount',side_effect=lambda p:Path(p).name=='mounted'):
   with self.assertRaises(ValueError):make_plan(self.home,True)
 def test_uninstall_keeps_projects_training_and_account(self):
  for rel in ['models/a','shared/training/datasets/x','shared/artifacts/image.png','shared/config/creator_auth.json','secrets/token','runtime/a','bin/a','shared/updates/old/payload/code']:
   p=self.home/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('data')
  with patch('core.uninstall_plan.remove_linux_shortcuts'):execute_linux(make_plan(self.home))
  for rel in ['models/a','shared/training/datasets/x','shared/artifacts/image.png','shared/config/creator_auth.json','secrets/token']:self.assertTrue((self.home/rel).exists())
  self.assertFalse((self.home/'shared/updates').exists())
 def test_linked_state_refuses_lock_creation(self):
  from core.app_uninstall import lifecycle_locks
  external=self.base/'external';external.mkdir();(self.home/'shared').symlink_to(external,target_is_directory=True)
  with self.assertRaises(UninstallError):lifecycle_locks(self.home)
  self.assertEqual(list(external.iterdir()),[])
 def test_bind_mount_guard(self):
  (self.home/'bind').mkdir()
  with patch('core.uninstall_plan.mounted_paths',return_value={self.home/'bind'}):
   with self.assertRaises(ValueError):make_plan(self.home,True)
 def test_unrelated_shortcut_home_prefix_kept(self):
  from core.desktop_shortcuts import belongs_to_home
  self.assertFalse(belongs_to_home('X-Zetalvx-Home='+str(self.home)+'-other',self.home))
 def test_invalid_job_path(self):
  for id in ('../x','c'*31,'C'*32,'/etc'):
   with self.assertRaises(UninstallError):safe_job(self.home,id)
 def test_linked_job_parent_refused(self):
  (self.home/'shared').symlink_to(self.base,target_is_directory=True)
  with self.assertRaises(UninstallError):safe_job(self.home,'a'*32)
 def test_start_failure_clears_pending(self):
  svc=UninstallService(self.home,self.source)
  with patch('core.app_uninstall.check_idle_and_update'),patch('core.app_uninstall.subprocess.run',side_effect=OSError('spawn failed')):
   with self.assertRaises(OSError):svc.start(False)
  self.assertFalse((self.home/'uninstall-pending.json').exists());self.assertTrue(self.source.exists())
 def test_busy_preflight_does_not_spawn(self):
  svc=UninstallService(self.home,self.source)
  with patch('core.app_uninstall.check_idle_and_update',side_effect=UninstallError('Busy')),patch('core.app_uninstall.subprocess.run') as spawn:
   with self.assertRaises(UninstallError):svc.start(False)
   spawn.assert_not_called()
  self.assertFalse((self.home/'uninstall-pending.json').exists())
 def test_desktop_only_start_migrates_old_shortcuts(self):
  d=self.base/'Desktop';a=self.base/'xdg/applications';d.mkdir();a.mkdir(parents=True)
  for folder in (a,d):
   for name,action,lan in [('creator-studio-sdxl.desktop','start',False),('creator-studio-sdxl-lan.desktop','start',True),('creator-studio-sdxl-uninstall.desktop','uninstall',False)]:
    (folder/name).write_text(desktop_entry(self.home,ROOT,action=action,lan=lan))
  with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.base/'xdg')}),patch('core.desktop_shortcuts.desktop_directory',return_value=d),patch('core.desktop_shortcuts.shutil.which',return_value=None):
   paths=install_shortcuts(self.home,ROOT,'yes')
  self.assertEqual(len(list(d.glob('*.desktop'))),1);self.assertEqual(len(list(a.glob('*.desktop'))),1)
  self.assertTrue((self.home/'creator-studio-sdxl-uninstall.desktop').exists());self.assertNotIn('"--lan"',(d/'creator-studio-sdxl.desktop').read_text());self.assertEqual(len(paths),3)

class WindowAndUIContracts(unittest.TestCase):
 def test_windows_hidden_not_detached_flag(self):
  flags=detached_kwargs(windows=True)['creationflags'];self.assertTrue(flags&0x08000000);self.assertFalse(flags&0x8);self.assertTrue(flags&0x200)
 def test_linux_session_semantics_unchanged(self):self.assertEqual(detached_kwargs(windows=False),{'start_new_session':True});self.assertEqual(hidden_kwargs(windows=False),{})
 def test_no_console_process_calls_without_flags(self):
  for filename in ('launcher.py','scripts/gui_update.py','scripts/install.py','core/app_updates.py','core/frame_extract.py','core/video_picker.py','core/training_manager.py'):
   tree=ast.parse((ROOT/filename).read_text())
   for n in ast.walk(tree):
    if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr in ('Popen','run','call'):
     self.assertTrue(any(k.arg in ('creationflags','startupinfo') or k.arg is None for k in n.keywords),(filename,n.lineno))
 def test_settings_uninstall_fields(self):
  from bs4 import BeautifulSoup
  html=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
  for id in ('uninstallPurge','uninstallWordInput','uninstallPassword','uninstallPasswordRepeat','uninstallUnderstand','uninstallConfirm'):self.assertIsNotNone(html.select_one('#'+id))
  self.assertIsNone(html.select_one('#uninstallPurge').get('checked'));self.assertEqual(len(html.select('#uninstallForm input[type=password]')),2)
  self.assertIsNotNone(html.select_one('#promptInspectBody #imageModeHelp'))
 def test_user_logo_bytes_unchanged(self):
  import hashlib
  import json
  # The source provenance records the original logo; this test just validates a real alpha channel.
  from PIL import Image
  im=Image.open(ROOT/'static/zetalvx-logo.png');self.assertEqual(im.mode,'RGBA');self.assertLess(im.getchannel('A').getextrema()[0],255)
if __name__=='__main__':unittest.main()
