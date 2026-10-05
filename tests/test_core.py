"""CPU/unit regression tests. No downloaded models, GPU or running services required."""
import ast, atexit, contextlib, io, json, math, os, shutil, sys, tempfile, types, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
# Always isolate tests even when launched from an installed production instance.
TMP=tempfile.TemporaryDirectory(prefix='creator-sdxl-test-')
os.environ['SDXL_STUDIO_HOME']=TMP.name;os.environ['SDXL_STUDIO_NO_BACKGROUND']='1'
os.environ['CREATOR_IDENTITY_ROOT']='/tmp/old-creator-sentinel'
os.environ['CREATOR_LORA_ROOTS']='/tmp/other-family-sentinel'
from core.runtime_env import initialize_environment,DATA_ROOT,SHARED_ROOT,MODELS_ROOT,atomic_json,worker_headers
initialize_environment()
from core import model_registry as registry, task_adapters as adapters, db, training_manager as training, media_tools
from PIL import Image
atexit.register(TMP.cleanup)

def extracted_functions(path,names,namespace=None):
    """Compile exact source functions without importing heavy runtime dependencies."""
    tree=ast.parse((ROOT/path).read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if len(nodes)!=len(names):raise AssertionError('Missing source functions')
    ns=namespace or {};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns);return ns

class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):db.init();registry.ensure_config();training.ensure()
    def test_01_paths_isolated(self):self.assertEqual(DATA_ROOT,Path(TMP.name));self.assertTrue(str(SHARED_ROOT).startswith(TMP.name));self.assertTrue(os.environ['CREATOR_IDENTITY_ROOT'].startswith(TMP.name));self.assertTrue(os.environ['CREATOR_LORA_ROOTS'].startswith(TMP.name))
    def test_02_worker_key(self):self.assertEqual(len(worker_headers()['X-SDXL-Worker-Key']),64)
    def test_03_private_key_mode(self):self.assertEqual((SHARED_ROOT/'config/worker_key').stat().st_mode&0o777,0o600)
    def test_04_atomic_json(self):
        p=DATA_ROOT/'test.json';atomic_json(p,{'ok':1});self.assertEqual(json.loads(p.read_text()),{'ok':1})
    def test_05_nan_rejected(self):
        with self.assertRaises(ValueError):atomic_json(DATA_ROOT/'nan.json',{'bad':float('nan')})
    def test_06_registry_only_sdxl(self):self.assertEqual([m['provider'] for m in registry.load_registry()['models']],['sdxl'])
    def test_07_registry_rejects_other(self):
        with self.assertRaises(ValueError):registry.save_registry({'models':[{'provider':'other'}]})
    def test_08_config_not_ready_without_weights(self):self.assertFalse(registry.validate_model(registry.model_by_id('sdxl'))['ready'])
    def test_09_generation_native(self):self.assertEqual(adapters.task_support({'provider':'sdxl'},'generate')['level'],'native')
    def test_10_reference_fallback(self):self.assertEqual(adapters.resolve_strategy({'provider':'sdxl'},'reference')['source_mode'],'first_reference')
    def test_11_multi_contact_sheet(self):self.assertEqual(adapters.resolve_strategy({'provider':'sdxl'},'multi_image')['source_mode'],'contact_sheet')
    def test_12_generic_inpaint(self):self.assertEqual(adapters.resolve_strategy({'provider':'sdxl'},'inpaint')['worker_task'],'generic_inpaint')
    def test_13_dedicated_inpaint(self):
        p=DATA_ROOT/'test-inpaint.safetensors';p.touch();self.assertEqual(adapters.resolve_strategy({'provider':'sdxl'},'inpaint',{'inpaint_checkpoint_override':str(p)})['worker_task'],'inpaint')
    def test_14_other_model_rejected(self):
        with self.assertRaises(RuntimeError):adapters.resolve_strategy({'provider':'other'},'generate_image')
    def test_15_dataset_crud(self):
        d=training.create_dataset('Regression','mytag','mytag, portrait')
        self.assertEqual(training.get_dataset(d['id'])['trigger'],'mytag')
        training.update_dataset(d['id'],{'name':'Renamed'});self.assertEqual(training.get_dataset(d['id'])['name'],'Renamed')
        training.delete_dataset(d['id']);self.assertIsNone(training.get_dataset(d['id']))
    def test_16_dataset_manual_caption(self):
        d=training.create_dataset('Images','abc','abc, hand');image=DATA_ROOT/'test.png';Image.new('RGB',(32,32)).save(image)
        f=types.SimpleNamespace(filename='original.png',save=lambda dest:shutil.copy(image,dest))
        item=training.add_dataset_file(d['id'],f);self.assertEqual(item['caption'],'abc, hand');self.assertEqual(item['caption_source'],'manual')
    def test_17_unsafe_dataset_delete(self):
        with self.assertRaises(RuntimeError):training.delete_dataset('../escape')
    def test_18_training_json_safe(self):self.assertIsNone(training._json_safe({'loss':float('nan')})['loss']);self.assertEqual(training._json_safe(Path('/tmp')), '/tmp')
    def test_19_training_recipes_sdxl(self):self.assertTrue(all(x['family']=='sdxl' for x in training.list_recipes()))
    def test_20_scheduler_default_restored(self):
        ns=extracted_functions('services/image_worker.py',{'set_scheduler'})
        class Scheduler:
            config={'test':1}
            @classmethod
            def from_config(cls,c,**kw):v=cls();v.config=c;return v
        p=types.SimpleNamespace(scheduler=Scheduler());ns['set_scheduler'](p,'default');p.scheduler.config={'test':2};ns['set_scheduler'](p,'default');self.assertEqual(p.scheduler.config,{'test':1})
    def test_21_namespace_normalization(self):
        ns=extracted_functions('services/image_worker.py',{'_text_encoder_has_legacy_text_model_prefix','_normalize_kohya_sdxl_for_transformers5'})
        flat=types.SimpleNamespace(named_modules=lambda:[('encoder.layers.0',None)])
        wrapped=types.SimpleNamespace(named_modules=lambda:[('text_model',None)])
        state={'lora_te1_text_model_encoder_layers_0_lora_down.weight':0,'lora_te2_text_model_encoder_layers_0_lora_up.weight':1}
        converted,changed=ns['_normalize_kohya_sdxl_for_transformers5'](types.SimpleNamespace(text_encoder=flat,text_encoder_2=wrapped),state)
        self.assertTrue(changed);self.assertIn('lora_te1_encoder_layers_0_lora_down.weight',converted);self.assertIn('lora_te2_text_model_encoder_layers_0_lora_up.weight',converted)
    def test_22_single_file_missing_config(self):
        from core.sdxl_config import single_file_config
        with self.assertRaises(RuntimeError):single_file_config()
    def test_23_no_forbidden_worker(self):self.assertEqual({p.stem for p in (ROOT/'services').glob('*_worker.py')},{'image_worker','identity_worker','training_worker'})
    def test_24_no_old_html_paths(self):self.assertNotIn('the'+'boss',(ROOT/'templates/index.html').read_text().lower())
    def test_25_html_ids_unique(self):
        import re
        ids=re.findall(r'\bid="([^"]+)"',(ROOT/'templates/index.html').read_text());self.assertEqual(len(ids),len(set(ids)))
    def test_26_no_video_view(self):self.assertNotIn('id="view-video"',(ROOT/'templates/index.html').read_text())
    def test_27_no_agent_view(self):self.assertNotIn('id="agentPanel"',(ROOT/'templates/index.html').read_text())
    def test_28_password_config_no_defaults(self):self.assertNotIn('"password":',(ROOT/'app.py').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
