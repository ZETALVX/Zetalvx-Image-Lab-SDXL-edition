"""Installer regressions. Real filesystem/SQLite/processes; pip and service/network
boundaries are deliberately mocked in TransactionTests. Not a native OS/GPU install.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

ROOT=Path(__file__).resolve().parents[1]
from core import install_layout as layout
from core.desktop_shortcuts import desktop_entry
from core.platform_support import venv_python
from scripts import install as installer
from scripts import installed_command as command


def manifest(root):
    items=[]
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name!='MANIFEST.sha256':
            items.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix())
    (root/'MANIFEST.sha256').write_text('\n'.join(items)+'\n')


def source_tree(path):
    path.mkdir(parents=True)
    for name in ('launcher.py','app.py','core/runtime_env.py','LICENSE','requirements-app.txt','requirements-sdxl.txt',
                 'scripts/install_smoke.py','scripts/audit_runtime.py','scripts/installed_command.py'):
        p=path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture '+name+'\n')
    manifest(path)
    return path


def arguments(**kw):
    d=dict(home=None,plan=False,runtime='auto',ai='auto',app_only=False,offline=False,online=True,
           no_start=False,no_browser=True,lan=False,no_shortcuts=True,resume_stage='auto')
    return argparse.Namespace(**(d|kw))


class Layout25Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.home=self.base/'CreatorStudioSDXL';self.home.mkdir()
        for n in ('0.1.0.18','0.1.0.19','1.0.14'):(self.home/'versions'/n).mkdir(parents=True)
    def test_canonical_home_not_preview(self):
        with patch.dict(os.environ,{'HOME':str(self.base)},clear=True):
            if os.name!='nt':self.assertEqual(layout.home_path(),self.base/'.local/share/CreatorStudioSDXL')
        self.assertEqual(layout.home_path(self.home),self.home)
    def test_windows_atomic_pointers_no_symlink(self):
        layout.set_pointers(self.home,'1.0.14','0.1.0.19',windows=True)
        self.assertEqual(layout.pointers(self.home,windows=True),{'current':'1.0.14','previous':'0.1.0.19'})
        self.assertFalse((self.home/'current').exists())
    def test_linux_historical_pointers(self):
        if os.name=='nt':
            layout.set_pointers(self.home,'1.0.14','0.1.0.19')
            self.assertEqual(layout.pointers(self.home)['current'],'1.0.14');return
        layout.set_pointers(self.home,'0.1.0.19','0.1.0.18')
        layout.set_pointers(self.home,'1.0.14','0.1.0.19')
        self.assertEqual((self.home/'current').resolve(),self.home/'versions/1.0.14')
        self.assertEqual(layout.pointers(self.home)['previous'],'0.1.0.19')
    def test_rejects_outside_pointer(self):
        if os.name=='nt':
            layout.atomic_json(self.home/'install-state.json',{'current':'../elsewhere'})
            with self.assertRaises(ValueError):layout.pointers(self.home)
            return
        outside=self.base/'0.1.0.19';outside.mkdir();(self.home/'current').symlink_to(outside)
        with self.assertRaises(ValueError):layout.pointers(self.home)
    def test_regular_current_never_overwritten(self):
        if os.name=='nt':
            (self.home/'current').mkdir();layout.set_pointers(self.home,'1.0.14','0.1.0.19')
            self.assertTrue((self.home/'current').is_dir());return
        (self.home/'current').mkdir()
        with self.assertRaises(ValueError):layout.set_pointers(self.home,'1.0.14','0.1.0.19')
        self.assertTrue((self.home/'current').is_dir())
    def test_cannot_point_to_missing_version(self):
        with self.assertRaises(ValueError):layout.set_pointers(self.home,'0.1.0.99',None,windows=True)
    def test_bad_release_name_rejected(self):
        for s in ('../0.1','/tmp/1','C:\\1','1/../2','1\n2',''):
            with self.subTest(s=s),self.assertRaises(ValueError):layout.release_path(self.home,s)
    def test_child_rejects_traversal_on_both_platforms(self):
        for s in ('../x','/etc/passwd','C:/x','x\\y','a/../../b','x\x00','a\nb'):
            with self.subTest(s=s),self.assertRaises(ValueError):layout.child(self.home,s)
    def test_legacy_runtime_fallback(self):
        self.assertEqual(layout.runtime_dirs(self.home,self.home/'versions/0.1.0.19'),
            {'app':self.home/'runtime/app','sdxl':self.home/'runtime/sdxl'})
    def test_new_map_preserves_legacy(self):
        old=self.home/'versions/0.1.0.19';new=self.home/'versions/1.0.14'
        dirs={'app':self.home/'runtime/sets/1.0.14/app','sdxl':self.home/'runtime/sets/1.0.14/sdxl'}
        layout.write_runtime_map(self.home,new,dirs,version='1.0.14')
        self.assertEqual(layout.runtime_dirs(self.home,new),dirs)
        self.assertEqual(layout.runtime_dirs(self.home,old)['app'],self.home/'runtime/app')
        self.assertFalse((old/layout.RUNTIME_MAP).exists())
    def test_map_without_ai_explicit(self):
        new=self.home/'versions/1.0.14'
        layout.write_runtime_map(self.home,new,{'app':self.home/'runtime/app','sdxl':None})
        self.assertIsNone(layout.runtime_dirs(self.home,new)['sdxl'])
    def test_map_rejects_external_runtime(self):
        new=self.home/'versions/1.0.14'
        layout.atomic_json(new/layout.RUNTIME_MAP,{'schema':1,'runtimes':{'app':'runtime/../../outside','sdxl':None}})
        with self.assertRaises(ValueError):layout.runtime_dirs(self.home,new)
    def test_dispatcher_understands_per_version_map(self):
        new=self.home/'versions/1.0.14'
        layout.write_runtime_map(self.home,new,{'app':self.home/'runtime/sets/1.0.14/app','sdxl':None})
        self.assertEqual(command.interpreter(self.home,new),venv_python(self.home/'runtime/sets/1.0.14/app'))
        self.assertEqual(command.interpreter(self.home,self.home/'versions/0.1.0.19'),venv_python(self.home/'runtime/app'))
    def test_atomic_json_replaces_complete_file(self):
        p=self.home/'config/state.json';layout.atomic_json(p,{'a':1});layout.atomic_json(p,{'b':2})
        self.assertEqual(json.loads(p.read_text()),{'b':2});self.assertFalse(list(p.parent.glob('*.tmp')))
        if os.name!='nt':self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_lock_excludes_second_process(self):
        p=self.home/'install.lock'
        code='from pathlib import Path;from core.install_layout import locked\ntry:\n with locked(Path(__import__("sys").argv[1])):pass\nexcept BlockingIOError:raise SystemExit(7)'
        with layout.locked(p):
            proc=subprocess.run([sys.executable,'-c',code,str(p)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(proc.returncode,7,proc.stderr)
        with layout.locked(p):pass
    def test_original_creator_directory_rejected(self):
        with self.assertRaises(ValueError):installer.check_layout(self.base/'CreatorStudio',ROOT)
    def test_source_cannot_contain_persistent_home(self):
        with self.assertRaises(ValueError):installer.check_layout(ROOT/'nested-data',ROOT)
    def test_shared_config_symlink_rejected(self):
        if os.name=='nt':return # Windows junction path is handled separately at bootstrap.
        (self.home/'shared').mkdir();outside=self.base/'other-config';outside.mkdir()
        (self.home/'shared/config').symlink_to(outside)
        with self.assertRaises(ValueError):installer.check_layout(self.home,ROOT)


class Manifest25Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=source_tree(Path(self.temp.name)/'source')
    def test_manifest_accepts_complete_payload(self):self.assertIn('launcher.py',layout.verify_manifest(self.root))
    def test_modified_byte_rejected(self):
        (self.root/'app.py').write_text('changed')
        with self.assertRaises(ValueError):layout.verify_manifest(self.root)
    def test_missing_file_rejected(self):
        (self.root/'launcher.py').unlink()
        with self.assertRaises(ValueError):layout.verify_manifest(self.root)
    def test_duplicate_record_rejected(self):
        p=self.root/'MANIFEST.sha256';p.write_text(p.read_text()+p.read_text().splitlines()[0]+'\n')
        with self.assertRaises(ValueError):layout.verify_manifest(self.root)
    def test_required_file_must_be_listed(self):
        p=self.root/'MANIFEST.sha256';p.write_text('\n'.join(x for x in p.read_text().splitlines() if not x.endswith('  LICENSE'))+'\n')
        with self.assertRaises(ValueError):layout.verify_manifest(self.root)
    def test_internal_symlink_is_not_a_regular_payload(self):
        if os.name=='nt':return
        target=self.root/'copy.py';target.write_bytes((self.root/'app.py').read_bytes())
        (self.root/'app.py').unlink();(self.root/'app.py').symlink_to(target)
        with self.assertRaises(ValueError):layout.verify_manifest(self.root)


class Preflight25Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=Path(self.temp.name)/'home'
    def test_cli_plan_is_read_only(self):
        p=subprocess.run([sys.executable,str(ROOT/'scripts/install.py'),'--plan','--home',str(self.home)],cwd=ROOT,
                         text=True,capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);self.assertFalse(self.home.exists())
        self.assertNotIn('preview-',p.stdout)
    def test_metadata_inventory_real_interpreter(self):
        d=installer.inventory(Path(sys.executable));self.assertTrue(d['exists']);self.assertEqual(d['python'][:2],list(sys.version_info[:2]))
    def test_exact_pins_require_compatible_python_and_torch(self):
        good={'exists':True,'python':[3,11,9],'packages':{'torch':'2.10.0+cu126'}}
        self.assertTrue(installer.reusable(good,{'torch':'2.10.0'}))
        self.assertFalse(installer.reusable(good,{'torch':'2.11.0'}))
        self.assertFalse(installer.reusable(good|{'python':[3,13,1]},{'torch':'2.10.0'}))
    def test_busy_sqlite_queue_blocks_without_modification(self):
        db=self.home/'shared/data/sdxl_studio.sqlite3';db.parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(db)) as c:
            c.execute('CREATE TABLE jobs(id TEXT,status TEXT)');c.execute("INSERT INTO jobs VALUES('x','running')");c.commit()
        before=db.read_bytes()
        with self.assertRaises(RuntimeError):installer.ensure_idle(self.home)
        self.assertEqual(db.read_bytes(),before)
    def test_corrupt_known_database_fails_closed(self):
        db=self.home/'shared/data/sdxl_studio.sqlite3';db.parent.mkdir(parents=True);db.write_bytes(b'not sqlite')
        with self.assertRaises(sqlite3.Error):installer.ensure_idle(self.home)
    def test_training_progress_blocks(self):
        for rel,status in [('shared/training/jobs/job1/progress.json','running'),
            ('shared/downloads/model-hub/download.json','downloading'),
            ('shared/config/instantid_code_install.json','running')]:
            p=self.home/rel;layout.atomic_json(p,{'status':status})
            with self.subTest(rel=rel),self.assertRaises(RuntimeError):installer.ensure_idle(self.home)
            p.unlink()
    def test_completed_jobs_do_not_block(self):
        p=self.home/'shared/training/jobs/job1/progress.json';layout.atomic_json(p,{'status':'completed'})
        installer.ensure_idle(self.home)
    def test_backup_and_immediate_restore_no_model_copy(self):
        config=self.home/'shared/config/creator_auth.json';layout.atomic_json(config,{'token':'fixture-not-a-real-secret'})
        model=self.home/'models/test.safetensors';model.parent.mkdir(parents=True);model.write_bytes(b'weights-fixture')
        before=model.read_bytes();backup=self.home/'shared/audits/test/backup'
        installer.backup_state(self.home,backup);layout.atomic_json(config,{'unexpected':'changed'})
        installer.restore_failed_activation(self.home,backup)
        self.assertEqual(json.loads(config.read_text()),{'token':'fixture-not-a-real-secret'})
        self.assertEqual(model.read_bytes(),before);self.assertFalse((backup/'models').exists())
        self.assertTrue((backup/'failed-state/shared/config/creator_auth.json').exists())
    def test_offline_still_rejects_known_block(self):
        report=self.home/'audit.json';layout.atomic_json(report,{'result':'BLOCKED','issues':[]})
        with patch.object(installer.subprocess,'run',return_value=argparse.Namespace(returncode=2)):
            with self.assertRaises(RuntimeError):installer.audit_offline(['fake'],ROOT,self.home,report)
    def test_offline_unknown_inventory_rejected(self):
        report=self.home/'audit.json';layout.atomic_json(report,{'result':'INCOMPLETE','issues':[{'state':'UNKNOWN'}]})
        with patch.object(installer.subprocess,'run',return_value=argparse.Namespace(returncode=2)):
            with self.assertRaises(RuntimeError):installer.audit_offline(['fake'],ROOT,self.home,report)
    def test_offline_only_feed_skipped_explicitly_accepted(self):
        report=self.home/'audit.json';layout.atomic_json(report,{'result':'INCOMPLETE','issues':[{'state':'NOT_CHECKED_OFFLINE'}]})
        with patch.object(installer.subprocess,'run',return_value=argparse.Namespace(returncode=2)):
            installer.audit_offline(['fake'],ROOT,self.home,report)
    def test_environment_not_original_creator_and_not_install_override(self):
        with patch.dict(os.environ,{'PYTHONPATH':'bad','VIRTUAL_ENV':'old','SDXL_STUDIO_INSTALLER_ACTIVE':'1'}):
            env=installer.environment(self.home)
        self.assertNotIn('PYTHONPATH',env);self.assertNotIn('VIRTUAL_ENV',env)
        self.assertNotIn('SDXL_STUDIO_INSTALLER_ACTIVE',env);self.assertEqual(env['SDXL_STUDIO_HOME'],str(self.home))
    def test_desktop_entry_graphical_and_correct_home(self):
        entry=desktop_entry(Path('/tmp/My SDXL'),ROOT,lan=True)
        self.assertIn('"/tmp/My SDXL/bin/gui_launch.py" "--home" "/tmp/My SDXL" "start" "--lan"',entry)
        self.assertIn('Terminal=false',entry);self.assertNotIn('preview',entry)
    def test_no_start_parameter_implies_no_daemon(self):
        help_=subprocess.run([sys.executable,str(ROOT/'scripts/install.py'),'--help'],capture_output=True,text=True)
        self.assertIn('--no-start',help_.stdout);self.assertIn('--no-browser',help_.stdout)




class Resume25Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.home=self.base/'CreatorStudioSDXL';self.home.mkdir()
        old=self.home/'versions/0.1.0.19';old.mkdir(parents=True)
        prev=self.home/'versions/0.1.0.18';prev.mkdir()
        layout.set_pointers(self.home,'0.1.0.19','0.1.0.18')
        self.stage=source_tree(self.home/'versions/0.1.0.23-staged')
        self.roots={'app':self.home/'runtime/sets/staged/app','sdxl':self.home/'runtime/sets/staged/sdxl'}
        for r in self.roots.values():
            py=venv_python(r);py.parent.mkdir(parents=True);py.write_bytes(b'fixture')
        layout.write_runtime_map(self.home,self.stage,self.roots,version='0.1.0.23')
    def good_info(self,kind):
        req=ROOT/('requirements-app.txt' if kind=='app' else 'requirements-sdxl.txt')
        packages=installer.direct_pins(req)|installer.TOOL_PINS
        if kind=='sdxl':
            packages.update(installer.identity_runtime_pins(ROOT,'cu126'))
            packages['torch']='2.14.0+cu126'
        return {'exists':True,'python':[3,11,14],'packages':packages,'runtime_marker':({'identity_runtime_schema':2,'backend':'cu126'} if kind=='sdxl' else {})}
    def test_auto_resume_finds_compatible_staged_runtime(self):
        state=layout.pointers(self.home)
        with patch.object(installer,'inventory',side_effect=[self.good_info('app'),self.good_info('sdxl')]):
            r=installer.resumable_stage(self.home,state,'cu126','auto')
        self.assertEqual(r[0],self.stage);self.assertEqual(r[1],self.roots)
    def test_explicit_incompatible_stage_fails_closed(self):
        state=layout.pointers(self.home);bad=self.good_info('app');bad['packages']['click']='1.0'
        with patch.object(installer,'inventory',side_effect=[bad,self.good_info('sdxl')]):
            with self.assertRaises(RuntimeError):installer.resumable_stage(self.home,state,'cu126',self.stage.name)
    def test_current_24_runtime_binding_is_reused_by_ui_only_25(self):
        current=self.home/'versions/0.1.0.24';current.mkdir()
        layout.write_runtime_map(self.home,current,self.roots,version='0.1.0.24',backend='cu126')
        layout.set_pointers(self.home,'0.1.0.24','0.1.0.19')
        before={p:p.read_bytes() for p in [current/layout.RUNTIME_MAP,*(venv_python(x) for x in self.roots.values())]}
        with patch.object(installer,'inventory',side_effect=[self.good_info('app'),self.good_info('sdxl')]):
            result=installer.plan(arguments(home=self.home,plan=True,runtime='keep',ai='cu126'))
        self.assertEqual(result[2],self.roots)
        self.assertEqual(result[5],{'app':'reuse','sdxl':'reuse'})
        self.assertEqual(layout.pointers(self.home)['current'],'0.1.0.24')
        for p,content in before.items():self.assertEqual(p.read_bytes(),content)

    def test_none_disables_resume(self):
        self.assertIsNone(installer.resumable_stage(self.home,layout.pointers(self.home),'cu126','none'))

class Transaction25Tests(unittest.TestCase):
    """Real home, manifest, pointers, per-version map, backups. External boundaries
    (pip, services, hardware, audit feed) are simulated and are NOT end-to-end tests.
    """
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.home=self.base/'CreatorStudioSDXL';self.home.mkdir()
        self.source=source_tree(self.base/'payload')
        self.old=self.home/'versions/0.1.0.19';self.old.mkdir(parents=True)
        self.prev=self.home/'versions/0.1.0.18';self.prev.mkdir()
        layout.set_pointers(self.home,'0.1.0.19','0.1.0.18')
        for r in ('app','sdxl'):
            p=venv_python(self.home/'runtime'/r);p.parent.mkdir(parents=True);p.write_bytes(b'old-runtime-'+r.encode())
        self.cfg=self.home/'shared/config/settings.json'
        layout.atomic_json(self.cfg,{'host':'0.0.0.0','identity_instantid_enabled':True,'identity_faceswap_enabled':True})
        self.auth=self.home/'shared/config/creator_auth.json';layout.atomic_json(self.auth,{'password_hash':'fixture'})
        self.model=self.home/'models/SDXL/model.safetensors';self.model.parent.mkdir(parents=True);self.model.write_bytes(b'unchanged-model')
        self.before={str(p.relative_to(self.home)):p.read_bytes() for p in [self.cfg,self.auth,self.model,venv_python(self.home/'runtime/app'),venv_python(self.home/'runtime/sdxl')]}
        self.roots=layout.runtime_dirs(self.home,self.old)
        self.inventories={'app':{'exists':True,'python':[3,11,10],'packages':{}},
                          'sdxl':{'exists':True,'python':[3,11,10],'packages':{'torch':'2.5.1+cu121','insightface':'0.7.3'}}}
        self.actions={'app':'reuse','sdxl':'stage-new'}
        self.calls=[];self.live=True;self.failed=False
        self.smoke_error=False;self.init_error=False;self.start_error=False;self.started_health_error=False
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        for name,value in [('ROOT',self.source),('plan',self.fake_plan),('build_runtime',self.build),
                           ('smoke',self.smoke),('launcher_command',self.launch),('stop_release',self.stop),
                           ('live_state',self.live_state),('supervisor',lambda h:self.live_state(h)),
                           ('worker_health',lambda p:{'ok':True,'busy':False}),('gpu_preflight',lambda *a,**k:{'status':'PASS'}),('verify_started',self.verify),
                           ('create_commands',lambda *a:self.calls.append(('commands',))),('pip',lambda *a:self.calls.append(('pip-check',))),
                           ('run',lambda *a,**kw:'' )]:
            self.stack.enter_context(patch.object(installer,name,value))
        self.stack.enter_context(patch.object(installer.sys,'version_info',(3,11,16)))
        private_boot=self.home/'runtime/python/cpython-3.11.16/bin/python3';private_boot.parent.mkdir(parents=True,exist_ok=True);private_boot.write_bytes(b'fixture-private-python')
        self.stack.enter_context(patch.object(installer.sys,'executable',str(private_boot)))
        self.stack.enter_context(patch.object(installer.sys,'prefix',str(private_boot.parent.parent)))
        self.stack.enter_context(patch.object(installer.sys,'base_prefix',str(private_boot.parent.parent)))
        if hasattr(os,'geteuid'):self.stack.enter_context(patch.object(installer.os,'geteuid',return_value=1000))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
    def fake_plan(self,args):return self.home,self.old,self.roots,self.inventories,'cu126',self.actions,layout.pointers(self.home)
    def live_state(self,home):return {'pid':1234,'start':'fixture','host':'0.0.0.0'} if self.live else None
    def build(self,target,*args):
        self.calls.append(('build',str(target)));p=venv_python(target);p.parent.mkdir(parents=True);p.write_bytes(b'new-runtime')
    def smoke(self,*args):
        self.calls.append(('smoke',))
        if self.smoke_error:raise RuntimeError('simulated preflight failure')
    def stop(self,home,release):self.calls.append(('stop',release.name));self.live=False
    def launch(self,home,release,*args,**kw):
        self.calls.append((args[0],release.name,*args[1:]))
        if args[0]=='init' and self.init_error:
            layout.atomic_json(self.auth,{'oops':'changed'});raise RuntimeError('simulated activation failure')
        if args[0]=='start':
            if release.name.startswith('1.0.14') and self.start_error:raise RuntimeError('simulated startup failure')
            self.live=True
    def verify(self,*args):
        if self.started_health_error:raise RuntimeError('simulated worker unavailable')
    def assert_old_files(self):
        for relative,content in self.before.items():self.assertEqual((self.home/relative).read_bytes(),content,relative)
    def test_update_commits_correct_home_and_old_previous(self):
        self.assertEqual(installer.install(arguments(home=self.home)),0)
        self.assertEqual(layout.pointers(self.home),{'current':'1.0.14','previous':'0.1.0.19'})
        self.assert_old_files()
        new=self.home/'versions/1.0.14';self.assertEqual(layout.runtime_dirs(self.home,new)['app'],self.home/'runtime/app')
        self.assertEqual(layout.runtime_dirs(self.home,new)['sdxl'],self.home/'runtime/sets/1.0.14/sdxl')
        self.assertIn(('start','1.0.14','--no-browser','--lan'),self.calls)
        self.assertFalse(any('preview-' in str(p) for p in self.base.iterdir()))
    def test_preflight_failure_keeps_running_old_and_pointers(self):
        self.smoke_error=True
        with self.assertRaises(RuntimeError):installer.install(arguments(home=self.home))
        self.assertEqual(layout.pointers(self.home)['current'],'0.1.0.19');self.assertTrue(self.live);self.assert_old_files()
        self.assertFalse(any(c[0]=='stop' for c in self.calls))
    def test_init_failure_restores_account_and_old_current(self):
        self.init_error=True
        with self.assertRaises(RuntimeError):installer.install(arguments(home=self.home))
        self.assertEqual(layout.pointers(self.home),{'current':'0.1.0.19','previous':'0.1.0.18'})
        self.assertTrue(self.live);self.assert_old_files();self.assertIn(('start','0.1.0.19','--no-browser','--lan'),self.calls)
    def test_start_failure_restores_old_runtime_and_service(self):
        self.start_error=True
        with self.assertRaises(RuntimeError):installer.install(arguments(home=self.home))
        self.assertEqual(layout.pointers(self.home)['current'],'0.1.0.19');self.assertTrue(self.live);self.assert_old_files()
    def test_unavailable_worker_does_not_leave_partial_new_service(self):
        self.started_health_error=True
        with self.assertRaises(RuntimeError):installer.install(arguments(home=self.home))
        self.assertEqual(layout.pointers(self.home)['current'],'0.1.0.19');self.assertTrue(self.live);self.assert_old_files()
    def test_no_start_does_not_launch_any_service(self):
        self.assertEqual(installer.install(arguments(home=self.home,no_start=True)),0)
        self.assertFalse(any(c[0]=='start' for c in self.calls));self.assertFalse(self.live)
    def test_keep_incompatible_runtime_stops_before_writes(self):
        with self.assertRaises(RuntimeError):installer.install(arguments(home=self.home,runtime='keep'))
        self.assertFalse((self.home/'versions/1.0.14').exists());self.assertEqual(self.calls,[]);self.assert_old_files()
    def test_offline_stage_needed_stops_before_writes(self):
        with self.assertRaises(RuntimeError):installer.install(arguments(home=self.home,offline=True))
        self.assertFalse((self.home/'versions/1.0.14').exists());self.assertEqual(self.calls,[]);self.assert_old_files()
    def test_reuse_never_calls_build(self):
        self.actions={'app':'reuse','sdxl':'reuse'}
        self.assertEqual(installer.install(arguments(home=self.home)),0)
        self.assertFalse(any(c[0]=='build' for c in self.calls));self.assert_old_files()
    def test_busy_job_prevents_preparation_or_stop(self):
        layout.atomic_json(self.home/'shared/training/jobs/active/progress.json',{'status':'running'})
        with self.assertRaises(RuntimeError):installer.install(arguments(home=self.home))
        self.assertEqual(self.calls,[]);self.assertTrue(self.live);self.assert_old_files()
    def test_code_tampering_stops_before_activation(self):
        (self.source/'app.py').write_text('tampered')
        with self.assertRaises(ValueError):installer.install(arguments(home=self.home))
        self.assertEqual(self.calls,[]);self.assertTrue(self.live);self.assert_old_files()
    def test_resume_stage_reuses_validated_runtime_and_still_commits_transaction(self):
        stage=source_tree(self.home/'versions/0.1.0.23-staged')
        staged_roots={'app':self.home/'runtime/sets/staged/app','sdxl':self.home/'runtime/sets/staged/sdxl'}
        for r in staged_roots.values():
            p=venv_python(r);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'staged-runtime')
        staged_infos={'app':{'exists':True,'python':[3,11,14],'packages':{}},
                      'sdxl':{'exists':True,'python':[3,11,14],'packages':{'insightface':'0.7.3'}}}
        with patch.object(installer,'resumable_stage',return_value=(stage,staged_roots,staged_infos)):
            self.assertEqual(installer.install(arguments(home=self.home)),0)
        current=layout.pointers(self.home)['current'];self.assertTrue(current.startswith('1.0.14'))
        new=layout.release_path(self.home,current)
        self.assertEqual(layout.runtime_dirs(self.home,new),staged_roots)
        self.assertFalse(any(c[0]=='build' for c in self.calls))
        self.assertEqual(layout.pointers(self.home)['previous'],'0.1.0.19')

    def test_existing_version_dir_not_overwritten(self):
        original=self.home/'versions/1.0.14';original.mkdir();(original/'sentinel').write_text('old trial')
        self.assertEqual(installer.install(arguments(home=self.home)),0)
        self.assertNotEqual(layout.pointers(self.home)['current'],'1.0.14');self.assertEqual((original/'sentinel').read_text(),'old trial')


if __name__=='__main__':unittest.main()
