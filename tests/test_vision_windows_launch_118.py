"""GGUF launch regression: platform branch, JSON, process ownership and POSIX path.
No models/downloads/GPU. Mocked Windows launch is not a native Windows test.
The portable process test uses a small local HTTP fixture, not llama.cpp.
"""
from __future__ import annotations
import atexit
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from PIL import Image
from vision import runtime
from vision.registry import Registry, VisionError

JSON_ENV = 'LLAMA_ARG_CHAT_TEMPLATE_KWARGS'

class OSView:
    """Override only the module-local platform decision, never pathlib/the host."""
    def __init__(self, name): self.name = name
    def __getattr__(self, name): return getattr(os, name)

class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vision launch test ')
        self.home = Path(self.tmp.name)
        self.registry = Registry(self.home)
        self.exe = self.home / 'server folder' / 'llama-server.exe'
        self.exe.parent.mkdir()
        self.exe.write_bytes(b'fixture, never executed')
        self.exe.chmod(0o700)
        model = self.home / 'model folder' / 'qwen modello.gguf'
        model.parent.mkdir()
        model.write_bytes(b'GGUFfixture')
        projector = model.parent / 'mmproj modello.gguf'
        projector.write_bytes(b'GGUFfixture')
        self.model = self.registry.save({
            'name':'Vision launch fixture', 'backend':'gguf',
            'llama_path':str(self.exe), 'gguf_path':str(model),
            'mmproj_path':str(projector), 'terms_reviewed':True,
            'context':4096, 'threads':4, 'gpu_layers':-1,
            'device':'auto', 'disable_thinking':True, 'startup_timeout':30,
        })
        self.engine = runtime.Engine(self.registry)
        self.proc = Mock(pid=23456, stdin=None, stdout=None)
        self.proc.poll.return_value = None
        self.session = Mock(trust_env=True)
        self.session.get.return_value.status_code = 200
        self.session.get.return_value.json.return_value = {'data':[{'id':'zetalvx-vision'}]}

    def tearDown(self):
        self.proc.poll.return_value = 0
        self.engine.close()
        atexit.unregister(self.engine.close)
        self.tmp.cleanup()

    def launch(self, platform='nt', **changes):
        model = {**self.model, **changes}
        flags = {'creationflags':0x08000200} if platform=='nt' else {'start_new_session':True}
        with patch.object(runtime, 'os', OSView(platform)), \
             patch.object(runtime.subprocess, 'Popen', return_value=self.proc) as popen, \
             patch.object(runtime.requests, 'Session', return_value=self.session), \
             patch.object(runtime, 'detached_kwargs', return_value=flags):
            self.engine._ensure(model, None)
        self.assertEqual(popen.call_count, 1)
        self.assertFalse(self.session.trust_env)
        return popen.call_args.args[0], popen.call_args.kwargs

    def test_windows_launches_owned_server_directly(self):
        command, opts = self.launch()
        self.assertEqual(command[0], str(self.exe))
        self.assertNotIn('child', command)
        self.assertNotIn(str(ROOT/'run.py'), command)
        self.assertNotIn('--chat-template-kwargs', command)
        self.assertNotIn('shell', opts)
        self.assertEqual(opts['creationflags'], 0x08000200)
        self.assertIs(self.engine.proc, self.proc)
        self.assertTrue(self.engine.loaded)

    def test_windows_thinking_disabled_keeps_valid_json(self):
        command, opts = self.launch(disable_thinking=True)
        self.assertEqual(opts['env'][JSON_ENV], '{"enable_thinking": false}')
        self.assertEqual(json.loads(opts['env'][JSON_ENV]), {'enable_thinking':False})
        self.assertFalse(any('enable_thinking' in x for x in command))

    def test_windows_thinking_enabled_is_not_forced_off(self):
        _, opts = self.launch(disable_thinking=False)
        self.assertEqual(json.loads(opts['env'][JSON_ENV]), {'enable_thinking':True})

    def test_paths_with_spaces_are_individual_arguments(self):
        command, _ = self.launch()
        for flag, key in (('--model','gguf_path'), ('--mmproj','mmproj_path')):
            self.assertEqual(command[command.index(flag)+1], self.model[key])
        self.assertEqual(command[command.index('--api-key-file')+1], str(self.engine.keyfile))

    def test_windows_all_other_server_options_unchanged(self):
        command, _ = self.launch()
        self.assertEqual(command[1:], [
            '--model', self.model['gguf_path'], '--mmproj', self.model['mmproj_path'],
            '--host','127.0.0.1','--port',self.engine.endpoint.split(':')[-1].split('/')[0],
            '--ctx-size','4096','--n-gpu-layers','-1','--threads','4','--parallel','1',
            '--alias','zetalvx-vision','--api-key-file',str(self.engine.keyfile),
        ])

    def test_cpu_selection_preserved(self):
        command, _ = self.launch(device='cpu')
        self.assertEqual(command[command.index('--n-gpu-layers')+1], '0')

    def test_parent_environment_not_mutated_and_credentials_filtered(self):
        upstream = {JSON_ENV:'{"enable_thinking":"untrusted"}',
                    'LLAMA_ARG_HOST':'0.0.0.0','HF_TOKEN':'test-only-secret',
                    'OPENAI_API_KEY':'test-only-secret'}
        with patch.dict(os.environ, upstream):
            before = dict(os.environ)
            _, opts = self.launch()
            self.assertEqual(dict(os.environ), before)
        env = opts['env']
        self.assertEqual(json.loads(env[JSON_ENV]), {'enable_thinking':False})
        for name in ('LLAMA_ARG_HOST','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','OPENAI_API_KEY'):
            self.assertNotIn(name, env)
        for name in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_HUB_DISABLE_TELEMETRY'):
            self.assertEqual(env[name], '1')

    def test_posix_retains_exec_guard_and_exact_json_argument(self):
        command, opts = self.launch('posix')
        self.assertEqual(command[:5], [sys.executable,str(ROOT/'run.py'),'child',str(os.getpid()),str(self.exe)])
        self.assertEqual(command[-2:], ['--chat-template-kwargs','{"enable_thinking": false}'])
        self.assertNotIn(JSON_ENV, opts['env'])
        self.assertTrue(opts['start_new_session'])

    def test_posix_preserves_thinking_on(self):
        command, opts = self.launch('posix', disable_thinking=False)
        self.assertEqual(json.loads(command[-1]), {'enable_thinking':True})
        self.assertNotIn(JSON_ENV, opts['env'])

    def test_unload_uses_owned_process_and_removes_key(self):
        self.launch()
        keyfile = self.engine.keyfile
        self.assertTrue(keyfile.exists())
        with patch.object(runtime, 'terminate_owned_tree') as terminate:
            self.engine.unload()
        terminate.assert_called_once_with(self.proc, timeout=4)
        self.assertFalse(keyfile.exists())
        self.assertIsNone(self.engine.proc)

    def test_same_profile_reuses_tracked_process(self):
        self.launch()
        with patch.object(runtime.subprocess, 'Popen') as popen:
            self.engine._ensure(self.model, None)
        popen.assert_not_called()
        self.assertIs(self.engine.proc, self.proc)

    @unittest.skipUnless(os.name=='nt', 'Native Windows argv/env roundtrip not available on this host')
    def test_native_windows_argument_and_environment_roundtrip(self):
        command, opts = self.launch()
        code = 'import json,os,sys;print(json.dumps([sys.argv[1:],os.environ["'+JSON_ENV+'"]]))'
        result = subprocess.run([sys.executable,'-c',code,*command[1:]], env=opts['env'],
                                capture_output=True, text=True, check=True, timeout=15)
        argv, encoded = json.loads(result.stdout)
        self.assertEqual(argv, command[1:])
        self.assertEqual(json.loads(encoded), {'enable_thinking':False})


@unittest.skipIf(os.name=='nt', 'Portable fixture uses a POSIX shebang; not a Windows native llama.cpp test')
class PortableDirectProcessTests(unittest.TestCase):
    def test_direct_branch_real_process_caption_reuse_unload(self):
        with tempfile.TemporaryDirectory(prefix='vision process with spaces ') as folder:
            home=Path(folder); registry=Registry(home)
            exe=home/'llama-server'
            script='''#!PYTHON
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
argv=sys.argv[1:]
assert '--chat-template-kwargs' not in argv
options=json.loads(os.environ['LLAMA_ARG_CHAT_TEMPLATE_KWARGS'])
assert options == {'enable_thinking': False}
assert 'HF_TOKEN' not in os.environ
Path(__file__).with_suffix('.received.json').write_text(json.dumps({'argv':argv,'options':options}))
port=int(argv[argv.index('--port')+1]);key=Path(argv[argv.index('--api-key-file')+1]).read_text()
class H(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  self.send_response(200 if self.headers.get('Authorization')=='Bearer '+key else 401)
  self.end_headers();self.wfile.write(b'{"data":[{"id":"zetalvx-vision"}]}')
 def do_POST(self):
  payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  assert payload['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
  self.send_response(200);self.end_headers()
  self.wfile.write(b'{"choices":[{"message":{"content":"A test square."}}]}')
ThreadingHTTPServer(('127.0.0.1',port),H).serve_forever()
'''.replace('PYTHON',sys.executable)
            exe.write_text(script);exe.chmod(0o700)
            for name in ('model test.gguf','mmproj test.gguf'):(home/name).write_bytes(b'GGUFfixture')
            model=registry.save({'name':'portable fixture','backend':'gguf','llama_path':str(exe),
                                'gguf_path':str(home/'model test.gguf'),'mmproj_path':str(home/'mmproj test.gguf'),
                                'terms_reviewed':True,'disable_thinking':True,'device':'cpu',
                                'timeout':10,'startup_timeout':30})
            engine=runtime.Engine(registry)
            try:
                buf=io.BytesIO();Image.new('RGB',(8,8)).save(buf,'PNG')
                # Real POSIX subprocess/HTTP; only the new Windows branch is selected.
                with patch.object(runtime,'os',OSView('nt')):
                    self.assertEqual(engine.caption(model,buf.getvalue(),'Describe'),'A test square.')
                    pid=engine.proc.pid;key=engine.keyfile
                    self.assertEqual(engine.caption(model,buf.getvalue(),'Describe again'),'A test square.')
                    self.assertEqual(engine.proc.pid,pid)
                captured=json.loads(exe.with_suffix('.received.json').read_text())
                self.assertEqual(captured['options'],{'enable_thinking':False})
                self.assertIn(str(home/'model test.gguf'),captured['argv'])
                engine.unload()
                self.assertFalse(key.exists())
                self.assertFalse(engine.status()['backend_process_running'])
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            finally:
                engine.close();atexit.unregister(engine.close)

if __name__=='__main__': unittest.main(verbosity=2)
