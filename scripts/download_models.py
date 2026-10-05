#!/usr/bin/env python3
"""Explicit official SDXL downloads. Never downloads Identity/face models."""
import argparse, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.runtime_env import initialize_environment, settings, MODELS_ROOT

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('kind',choices=['configs','base']);p.add_argument('--accept-license',action='store_true');a=p.parse_args()
    initialize_environment();cfg=settings()
    from huggingface_hub import snapshot_download,hf_hub_download
    patterns=['model_index.json','scheduler/*.json','text_encoder/config.json','text_encoder_2/config.json','tokenizer/*','tokenizer_2/*','unet/config.json','vae/config.json','LICENSE*','README.md']
    for repo,dest in [('stabilityai/stable-diffusion-xl-base-1.0',cfg['sdxl_config']),('diffusers/stable-diffusion-xl-1.0-inpainting-0.1',cfg['inpaint_config'])]:
        print('[CONFIG]',repo,'->',dest,flush=True)
        snapshot_download(repo_id=repo,local_dir=dest,allow_patterns=patterns)
    if a.kind=='base':
        if not a.accept_license:raise SystemExit('Read the SDXL CreativeML Open RAIL++-M license first. Then rerun with --accept-license. See docs/MODELS_AND_LICENSES.md.')
        print('[WEIGHTS] SDXL Base 1.0, several GB. No Identity models are included.',flush=True)
        hf_hub_download(repo_id='stabilityai/stable-diffusion-xl-base-1.0',filename='sd_xl_base_1.0.safetensors',local_dir=MODELS_ROOT/'SDXL')
    print('[OK] Finished.')
if __name__=='__main__':main()
