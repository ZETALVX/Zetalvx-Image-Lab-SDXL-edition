import ast,io,json,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from core.identity_paths import identity_files,resolve_identity_paths,vendor_files

ROOT=Path(__file__).resolve().parents[1]
class IdentityPathsTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.p=Path(self.t.name);self.models=self.p/'edition/models';self.shared=self.p/'edition/shared';self.original=self.p/'CreatorStudio/models/Identity'
 def tearDown(self):self.t.cleanup()
 def put(self,p):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'x')
 def weights(self):
  for p in ['InstantID/ip-adapter.bin','InstantID/ControlNetModel/config.json','InstantID/ControlNetModel/diffusion_pytorch_model.safetensors','insightface/models/antelopev2/model.onnx','insightface/models/buffalo_l/model.onnx','inswapper_128.onnx']:self.put(self.original/p)
 def test_default_layout(self):
  s=resolve_identity_paths({},self.models,self.shared);self.assertEqual(s['instantid_root'],str(self.models/'Identity/InstantID'));self.assertEqual(s['vendor_root'],str(self.shared/'identity/vendor/InstantID'))
 def test_legacy_children_follow_external_parent(self):
  cfg={'identity_root':str(self.original),'identity_instantid_root':str(self.models/'Identity/InstantID'),'identity_insightface_root':str(self.models/'Identity/insightface'),'identity_swapper_model':str(self.models/'Identity/inswapper_128.onnx')};s=resolve_identity_paths(cfg,self.models,self.shared);self.assertEqual(s['instantid_root'],str(self.original/'InstantID'));self.assertEqual(s['swapper_path'],str(self.original/'inswapper_128.onnx'))
 def test_custom_children_respected(self):
  f=self.p/'other.onnx';s=resolve_identity_paths({'identity_root':str(self.original),'identity_swapper_model':str(f)},self.models,self.shared);self.assertEqual(s['swapper_path'],str(f))
 def test_complete_weights_do_not_imply_code(self):
  self.weights();s=identity_files({'identity_root':str(self.original)},self.models,self.shared);self.assertTrue(s['face_swap_files_ready']);self.assertTrue(s['instantid_adapter_ready']);self.assertFalse(s['instantid_files_ready']);self.assertTrue(s['vendor_missing'])
 def test_original_vendor_discovered_not_silently_executed(self):
  self.weights();v=self.original.parent.parent/'shared/identity/vendor/InstantID'
  for p in vendor_files(v):self.put(p)
  s=identity_files({'identity_root':str(self.original)},self.models,self.shared);self.assertFalse(s['vendor_ready']);self.assertTrue(any(c['path']==str(v) and c['complete'] for c in s['vendor_candidates']))
  s=identity_files({'identity_root':str(self.original),'identity_vendor':str(v)},self.models,self.shared);self.assertTrue(s['instantid_files_ready'])
 def test_normalize_face_pack_path(self):
  s=resolve_identity_paths({'identity_insightface_root':str(self.original/'insightface/models/antelopev2')},self.models,self.shared);self.assertEqual(s['insightface_root'],str(self.original/'insightface'))
 def test_normalize_models_folder(self):
  (self.original/'insightface/models/buffalo_l').mkdir(parents=True);s=resolve_identity_paths({'identity_insightface_root':str(self.original/'insightface/models')},self.models,self.shared);self.assertEqual(s['insightface_root'],str(self.original/'insightface'))
 def test_explicit_controlnet_filename(self):
  self.weights();p=self.original/'InstantID/ControlNetModel/diffusion_pytorch_model.safetensors';p.rename(p.with_name('wrong.safetensors'));s=identity_files({'identity_root':str(self.original)},self.models,self.shared);self.assertFalse(s['controlnet_weights_ready'])
 def test_signature_tracks_vendor_and_packs(self):
  a=resolve_identity_paths({},self.models,self.shared);b=resolve_identity_paths({'identity_vendor':str(self.p/'vendor')},self.models,self.shared);self.assertNotEqual(a['path_signature'],b['path_signature'])
 def test_pack_path_rejected(self):
  with self.assertRaises(ValueError):resolve_identity_paths({'swap_face_pack':'../../evil'},self.models,self.shared)
 def test_swapper_regression_no_undefined_pack(self):
  code=(ROOT/'services/identity_worker.py').read_text();fn=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='_load_swapper');module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));expected=object();seen=[];f=self.p/'swap.onnx';self.put(f)
  fake=types.SimpleNamespace(model_zoo=types.SimpleNamespace(get_model=lambda *a,**k:expected));scope={'cache':{'swapper':None},'SWAPPER_MODEL':f,'SWAP_FACE_PACK':'buffalo_l','FACE_ROOT':self.original/'insightface','_pack_ready':lambda p:seen.append(p) or True}
  with patch.dict(sys.modules,{'insightface':fake}):exec(compile(module,'worker-fragment','exec'),scope);self.assertIs(scope['_load_swapper'](),expected)
  self.assertEqual(seen,['buffalo_l'])
 def test_worker_refresh_at_admission(self):
  tree=ast.parse((ROOT/'services/identity_worker.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='generate');calls=[n.func.id for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)];self.assertIn('refresh_identity_paths',calls)
if __name__=='__main__':unittest.main()
