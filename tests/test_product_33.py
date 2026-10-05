""".33 regressions. Real temp filesystem, sockets and Linux processes; native Windows untested."""
import json, os, socket, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from core.desktop_shortcuts import desktop_entry,desktop_choice,install_shortcuts,exec_quote,NAMES
from core.uninstall_plan import make_plan,execute_linux,validate_home
from core.app_lifecycle import owned_service,stop_owned
from core.listener_check import probe_port,wait_ports
from core.execution_device import normalized_config
from core.install_layout import atomic_json
import psutil
ROOT=Path(__file__).resolve().parents[1]

class Product33(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);self.home=self.base/'CreatorStudioSDXL';self.home.mkdir()
        atomic_json(self.home/'.zetalvx-install.json',{'schema':1,'product':'Zetalvx Creator Studio SDXL','home':str(self.home),'id':'test-unique'})
    def test_uninstall_preserves_data_by_default(self):
        for name in ['versions/1.0.1/a','runtime/app/a','bin/a','models/sdxl/model','shared/projects/art','config/x','secrets/key']:
            p=self.home/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('keep data')
        plan=make_plan(self.home)
        with patch('core.uninstall_plan.remove_linux_shortcuts'):execute_linux(plan)
        for name in ('models/sdxl/model','shared/projects/art','secrets/key','config/x'):self.assertTrue((self.home/name).exists())
        for name in ('versions','runtime','bin'):self.assertFalse((self.home/name).exists())
    def test_purge_does_not_follow_model_symlink(self):
        external=self.base/'outside';external.mkdir();(external/'precious').write_text('keep')
        (self.home/'models').symlink_to(external,target_is_directory=True)
        with patch('core.uninstall_plan.remove_linux_shortcuts'):execute_linux(make_plan(self.home,True))
        self.assertFalse(self.home.exists());self.assertEqual((external/'precious').read_text(),'keep')
    def test_uninstall_rejects_missing_marker(self):
        (self.home/'.zetalvx-install.json').unlink()
        with self.assertRaises(OSError):make_plan(self.home)
    def test_uninstall_rejects_changed_identity(self):
        p=make_plan(self.home);d=json.loads((self.home/'.zetalvx-install.json').read_text());d['id']='new';atomic_json(self.home/'.zetalvx-install.json',d)
        with self.assertRaises(ValueError):execute_linux(p)
    def test_uninstall_rejects_linked_root(self):
        p=self.base/'link';p.symlink_to(self.home,target_is_directory=True)
        with self.assertRaises(ValueError):make_plan(p)
    def test_uninstall_rejects_home(self):
        with self.assertRaises(ValueError):make_plan(Path.home())
    def test_uninstall_does_not_accept_arbitrary_remove_list(self):
        external=self.base/'external';external.write_text('keep');p=make_plan(self.home);p['remove']=[str(external)]
        with patch('core.uninstall_plan.remove_linux_shortcuts'):execute_linux(p)
        self.assertEqual(external.read_text(),'keep')
    def test_menu_icons_without_desktop(self):
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.base/'xdg')}),patch('core.desktop_shortcuts.desktop_directory',return_value=self.base/'Desktop'),patch('core.desktop_shortcuts.shutil.which',return_value=None):
            paths=install_shortcuts(self.home,ROOT,policy='no');self.assertEqual(len(paths),2)
            self.assertFalse((self.base/'Desktop').exists());self.assertTrue(all('Terminal=false' in p.read_text() for p in paths))
    def test_desktop_choice_explicit_and_persistent(self):
        self.assertTrue(desktop_choice(self.home,'yes'));self.assertTrue(desktop_choice(self.home,'keep'));self.assertFalse(desktop_choice(self.home,'no'))
    def test_declining_desktop_still_installs_menu(self):
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.base/'xdg')}),patch('core.desktop_shortcuts.desktop_directory',return_value=self.base/'Desktop'),patch('core.desktop_shortcuts.shutil.which',return_value=None),patch('core.desktop_shortcuts.graphical',return_value=True),patch('core.desktop_shortcuts.dialog',return_value=False) as ask:
            paths=install_shortcuts(self.home,ROOT,'ask');self.assertEqual(len(paths),2);self.assertEqual(ask.call_count,1)
    def test_unrelated_shortcut_not_overwritten(self):
        d=self.base/'xdg/applications';d.mkdir(parents=True);p=d/NAMES[0][0];p.write_text('unrelated app')
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(self.base/'xdg')}),patch('core.desktop_shortcuts.desktop_directory',return_value=self.base/'Desktop'):
            with self.assertRaises(RuntimeError):install_shortcuts(self.home,ROOT,'no')
        self.assertEqual(p.read_text(),'unrelated app')
    def test_menu_desktop_uninstall_entry(self):
        text=desktop_entry(self.home,ROOT,action='uninstall',python='/tmp/python')
        self.assertIn('"uninstall"',text);self.assertIn('Terminal=false',text);self.assertIn('gui_launch.py',text)
    def test_exec_escape_percent_quotes(self):
        self.assertIn('%%',exec_quote('x%y'));self.assertIn('\\\\"',exec_quote('x"y'))
        with self.assertRaises(ValueError):exec_quote('bad\ncommand')
    def test_cpu_offload_never_used_without_accelerator(self):
        d=normalized_config({'device':'cpu','cpu_offload':True,'memory_mode':'cpu_offload','dtype':'float16'},False)
        self.assertEqual(d['dtype'],'float32');self.assertFalse(d['cpu_offload']);self.assertEqual(d['memory_mode'],'full_gpu')
    def test_cuda_unavailable_rejected_explicitly(self):
        with self.assertRaises(RuntimeError):normalized_config({'device':'cuda'},False)
    def test_first_cpu_install_sets_cpu_defaults(self):
        from core import model_registry as registry
        source=self.base/'source';(source/'config').mkdir(parents=True)
        (source/'config/models.defaults.json').write_bytes((ROOT/'config/models.defaults.json').read_bytes())
        (source/'.installed-runtime.json').write_text(json.dumps({'backend':'cpu'}))
        target=self.home/'shared/config/models.json'
        with patch.object(registry,'APP_ROOT',source),patch.object(registry,'MODELS_CONFIG',target),patch.object(registry,'MODELS_ROOT',self.home/'models'):
            registry.ensure_config();cfg=json.loads(target.read_text())['models'][0]['config']
            self.assertEqual(cfg['device'],'cpu');self.assertEqual(cfg['dtype'],'float32');self.assertFalse(cfg['cpu_offload'])
            registry.update_model('sdxl',{'config':{'device':'cpu','memory_mode':'cpu_offload','dtype':'float16'}})
            cfg=json.loads(target.read_text())['models'][0]['config'];self.assertEqual(cfg['memory_mode'],'full_gpu');self.assertEqual(cfg['dtype'],'float32')
    def test_existing_model_configuration_is_not_overwritten(self):
        from core import model_registry as registry
        target=self.home/'models.json';original={'models':[{'id':'sdxl','provider':'sdxl','config':{'device':'cuda','checkpoint':'custom.safetensors'}}]};target.write_text(json.dumps(original))
        with patch.object(registry,'MODELS_CONFIG',target):registry.ensure_config()
        self.assertEqual(json.loads(target.read_text()),original)
    def test_cuda_config_not_changed(self):
        cfg={'device':'cuda','memory_mode':'cpu_offload','dtype':'float16'};self.assertEqual(normalized_config(cfg,True),cfg)
    def test_cpu_normalization_does_not_mutate_input(self):
        cfg={'device':'cpu','cpu_offload':True};normalized_config(cfg,False);self.assertTrue(cfg['cpu_offload'])
    def test_live_listener_cannot_be_stolen(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
            with self.assertRaises(OSError):probe_port('127.0.0.1',port)
    def test_time_wait_does_not_block_rebind(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
            c=socket.create_connection(('127.0.0.1',port));peer,_=listener.accept();peer.shutdown(socket.SHUT_WR);peer.close();c.recv(1);c.close()
        probe_port('127.0.0.1',port)
    @unittest.skipIf(os.name=='nt','This is the real Linux process recovery test')
    def test_only_owned_worker_stopped_updater_kept(self):
        src=self.home/'versions/0.1.0.32';src.mkdir(parents=True);(src/'launcher.py').write_text('# marker')
        for n in ('run.py','gui_update.py'):(src/n).write_text('import time;time.sleep(120)')
        env={**os.environ,'SDXL_STUDIO_HOME':str(self.home)}
        worker=subprocess.Popen([sys.executable,str(src/'run.py'),'web'],cwd=src,env=env)
        updater=subprocess.Popen([sys.executable,str(src/'gui_update.py')],cwd=src,env=env)
        other=subprocess.Popen([sys.executable,str(src/'run.py'),'web'],cwd=src,env={**env,'SDXL_STUDIO_HOME':str(self.base/'Other')})
        try:
            time.sleep(.15);self.assertTrue(owned_service(psutil.Process(worker.pid),self.home));self.assertFalse(owned_service(psutil.Process(updater.pid),self.home))
            stopped=stop_owned(self.home,timeout=.2);self.assertIn(worker.pid,stopped);self.assertIsNone(updater.poll());self.assertIsNone(other.poll())
        finally:
            for p in (worker,updater,other):
                if p.poll() is None:p.terminate()
                p.wait(timeout=5)
    def test_new_assets_and_unique_ids(self):
        from html.parser import HTMLParser
        class P(HTMLParser):
            def __init__(self):super().__init__();self.ids=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if 'id'in a:self.ids.append(a['id'])
        p=P();p.feed((ROOT/'templates/index.html').read_text());self.assertEqual(len(p.ids),len(set(p.ids)))
        for k in ('view-user-presets','imageViewer','themeOptions','pmEditor'):self.assertIn(k,p.ids)
    def test_all_new_locale_entries_cover_12_languages(self):
        s=(ROOT/'static/product-locale.js').read_text();items=json.loads(s.split('const entries=',1)[1].split(';window.ZETALVX',1)[0]);expected=set('en it es fr de pt ru zh ja ko tr ar'.split())
        for x in items:self.assertEqual(set(x['text']),expected);self.assertTrue(all(x['text'].values()))
    def test_default_preview_right_respects_existing_preference(self):
        s=(ROOT/'static/workspace.js').read_text();self.assertIn("let side='right'",s);self.assertIn("saved==='left'||saved==='right'",s)
    def test_uninstall_windows_waits_and_checks_identity(self):
        s=(ROOT/'scripts/uninstall_windows.ps1').read_text(encoding='utf-8-sig');self.assertIn('WaitForExit',s);self.assertIn('ReparsePoint',s);self.assertIn('$M.id -ne $Spec.installation_id',s);self.assertNotIn('Stop-Process',s)
    def test_gui_entry_no_fixed_source_release(self):
        s=(ROOT/'scripts/gui_launch.py').read_text();self.assertIn('m.active(home)',s);self.assertIn('m.interpreter(home,source)',s)
