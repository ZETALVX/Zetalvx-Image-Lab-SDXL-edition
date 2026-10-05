"""Real staging layout and runtime-map selection; package inventory is simulated.
No pip install or service stop is performed by these tests.
"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from core import install_layout as layout
from core.platform_support import venv_python
from scripts import install as installer
from tests.test_installation_25 import source_tree, arguments

ROOT = Path(__file__).resolve().parents[1]

class Resume42To43Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)/'CreatorStudioSDXL'
        for name in ('0.1.0.91','0.1.0.90'):
            (self.home/'versions'/name).mkdir(parents=True)
        self.stage = source_tree(self.home/'versions/0.1.0.92')
        self.staged = {'app':self.home/'runtime/sets/0.1.0.92/app', 'sdxl':self.home/'runtime/sdxl'}
        self.old = {'app':self.home/'runtime/app', 'sdxl':self.home/'runtime/sdxl'}
        for p in {*self.old.values(), *self.staged.values()}:
            py=venv_python(p);py.parent.mkdir(parents=True,exist_ok=True);py.write_bytes(b'fixture')
        layout.set_pointers(self.home,'0.1.0.91','0.1.0.90')
        layout.write_runtime_map(self.home,self.stage,self.staged,version='0.1.0.92',backend='cu126')
        self.before={p:p.read_bytes() for p in self.home.rglob('*') if p.is_file() and not p.is_symlink()}

    def info(self, exe):
        exe=Path(exe)
        kind='sdxl' if exe==venv_python(self.staged['sdxl']) else 'app'
        packages=installer.direct_pins(ROOT/('requirements-'+kind+'.txt'))|installer.TOOL_PINS
        if kind=='sdxl':
            packages.update(installer.identity_runtime_pins(ROOT,'cu126'))
            packages['torch']='2.14.0+cu126'
        if exe==venv_python(self.old['app']):packages.pop('cheroot',None)
        return {'exists':True,'python':[3,11,2],'packages':packages,'runtime_marker':({'identity_runtime_schema':2,'backend':'cu126'} if kind=='sdxl' else {})}

    def test_finds_staged_web_runtime_and_existing_ai(self):
        with patch.object(installer,'inventory',side_effect=self.info):
            result=installer.resumable_stage(self.home,layout.pointers(self.home),'cu126','auto')
        self.assertEqual(result[0],self.stage)
        self.assertEqual(result[1],self.staged)
        self.assertEqual(layout.pointers(self.home)['current'],'0.1.0.91')
        for p,content in self.before.items():self.assertEqual(p.read_bytes(),content)

    def test_keep_plan_can_resume_without_rebuild(self):
        out=io.StringIO()
        with patch.object(installer,'inventory',side_effect=self.info), \
             patch.object(installer,'build_runtime',side_effect=AssertionError('must not build')), \
             patch.object(installer,'stop_release',side_effect=AssertionError('must not stop')), \
             redirect_stdout(out):
            rc=installer.install(arguments(home=self.home,plan=True,runtime='keep',ai='cu126'))
        self.assertEqual(rc,0)
        plan=json.loads(out.getvalue())
        self.assertEqual(plan['version'],'1.0.14')
        self.assertEqual(plan['resume_stage'],'0.1.0.92')
        self.assertEqual(plan['runtimes'],{'app':'resume-stage','sdxl':'resume-stage'})
        for p,content in self.before.items():self.assertEqual(p.read_bytes(),content)

if __name__=='__main__':unittest.main()
