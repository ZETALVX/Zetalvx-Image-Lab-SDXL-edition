#!/usr/bin/env python3
"""Small dependency/CUDA/Identity smoke check; no models or network downloads.
Uses the same private loader-path helper and ONNX smoke shape as the supplied installer.
This does not certify image generation, training quality or model licences.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--backend',choices=['cpu','cu126'],required=True);p.add_argument('--child',action='store_true',help=argparse.SUPPRESS);a=p.parse_args()
    if not a.child:
        from core.private_cuda_env import private_cuda_env
        env=private_cuda_env(Path(sys.executable));env['PYTHONDONTWRITEBYTECODE']='1'
        return subprocess.call([sys.executable,str(Path(__file__).resolve()),'--backend',a.backend,'--child'],env=env,cwd=ROOT)
    from core.runtime_security import require_reviewed_torch
    require_reviewed_torch()
    import torch, diffusers, transformers, cv2, onnx, scipy, skimage, einops, insightface
    from insightface.app import FaceAnalysis
    import onnxruntime as ort
    from onnx import helper, TensorProto
    if a.backend=='cu126' and not torch.cuda.is_available():raise RuntimeError('CUDA was selected but is unavailable; no CPU fallback was accepted.')
    device='cuda' if a.backend=='cu126' else 'cpu'
    result=(torch.ones(1,device=device)+1).item()
    if result!=2:raise RuntimeError('Tiny Torch operation failed.')
    x=helper.make_tensor_value_info('x',TensorProto.FLOAT,[1]);y=helper.make_tensor_value_info('y',TensorProto.FLOAT,[1])
    g=helper.make_graph([helper.make_node('Identity',['x'],['y'])],'source-ort-smoke',[x],[y])
    m=helper.make_model(g,opset_imports=[helper.make_operatorsetid('',17)]);m.ir_version=10
    provider='CUDAExecutionProvider' if a.backend=='cu126' else 'CPUExecutionProvider'
    providers=ort.get_available_providers()
    if provider not in providers:raise RuntimeError('Missing ONNX provider: '+provider)
    session=ort.InferenceSession(m.SerializeToString(),providers=[provider] if device=='cpu' else [provider,'CPUExecutionProvider'])
    if session.get_providers()[0]!=provider:raise RuntimeError('Selected ONNX provider did not initialize.')
    import numpy as np
    outputs=session.run(None,{'x':np.array([1.0],dtype=np.float32)})
    if float(outputs[0][0])!=1.0:raise RuntimeError('Tiny ONNX operation failed.')
    print(json.dumps({'ok':True,'torch':torch.__version__,'diffusers':diffusers.__version__,'transformers':transformers.__version__,
        'device':device,'onnxruntime':ort.__version__,'providers':session.get_providers(),'models_loaded':False,'generation_training_validated':False},indent=2))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:print('[ERROR]',type(exc).__name__+':',exc,file=sys.stderr);raise SystemExit(1)
