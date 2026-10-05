#!/usr/bin/env python3
"""Detached SDXL Base/config completion worker.

Runs in the SDXL runtime, survives browser/web-server restarts and only fills
missing official SDXL configuration/tokenizer files or the official Base 1.0
checkpoint when no usable checkpoint is already configured/present.
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',required=True)
    parser.add_argument('--job-id',required=True)
    args=parser.parse_args()
    os.environ['SDXL_STUDIO_HOME']=str(Path(args.home).expanduser().absolute())
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))

    from core import file_lock
    from core.runtime_env import initialize_environment, SHARED_ROOT, MODELS_ROOT, settings, atomic_json
    from core.model_policy import SDXL_REPO, SDXL_FILE
    from core.model_registry import model_by_id, update_model
    from core.sdxl_assets import asset_status, BASE_ALLOW_PATTERNS, INPAINT_REPO

    initialize_environment()
    state_file=SHARED_ROOT/'config/sdxl_base_install.json'
    lock_file=SHARED_ROOT/'run/sdxl-base-install.lock'
    log_file=SHARED_ROOT/'logs/sdxl-base-install.log'
    lock_file.parent.mkdir(parents=True,exist_ok=True)
    log_file.parent.mkdir(parents=True,exist_ok=True)

    def state(**fields):
        try:d=json.loads(state_file.read_text(encoding='utf-8'))
        except (OSError,ValueError):d={}
        if d.get('id') not in (None,args.job_id):
            raise RuntimeError('A newer SDXL install request replaced this job.')
        d.update(id=args.job_id,updated_at=time.time(),**fields)
        atomic_json(state_file,d)
        return d

    def log(msg):
        stamp=time.strftime('%Y-%m-%d %H:%M:%S')
        with log_file.open('a',encoding='utf-8') as f:f.write(f'[{stamp}] {msg}\n')

    with lock_file.open('a+b') as lock:
        try:file_lock.flock(lock,file_lock.LOCK_EX|file_lock.LOCK_NB)
        except BlockingIOError:
            state(status='failed',stage='failed',message='Another SDXL download is already running.',error='lock-held')
            return 2
        try:
            from huggingface_hub import snapshot_download, hf_hub_download
            model=model_by_id('sdxl') or {}; cfg_model=model.get('config') or {}
            initial=asset_status(cfg_model)
            state(status='running',stage='checking',completed=0,total=3,message='Checking existing SDXL files…',error='',assets=initial)
            log('Checking existing files')
            cfg=settings()
            completed=0

            if initial['base_config']['ready']:
                completed+=1;log('Base config/tokenizers already present')
            else:
                state(status='running',stage='base-config',completed=completed,total=3,message='Downloading missing SDXL config/tokenizers…',current_task='base_config',assets=asset_status(cfg_model))
                log('Downloading missing SDXL base config/tokenizers')
                snapshot_download(repo_id=SDXL_REPO,local_dir=Path(cfg['sdxl_config']).expanduser(),allow_patterns=BASE_ALLOW_PATTERNS)
                completed+=1

            mid=asset_status((model_by_id('sdxl') or {}).get('config') or {})
            if mid['inpaint_config']['ready']:
                completed+=1;log('Inpaint config/tokenizers already present')
            else:
                state(status='running',stage='inpaint-config',completed=completed,total=3,message='Downloading missing inpaint config/tokenizers…',current_task='inpaint_config',assets=mid)
                log('Downloading missing inpaint config/tokenizers')
                snapshot_download(repo_id=INPAINT_REPO,local_dir=Path(cfg['inpaint_config']).expanduser(),allow_patterns=BASE_ALLOW_PATTERNS)
                completed+=1

            current_cfg=(model_by_id('sdxl') or {}).get('config') or {}
            before_weight=asset_status(current_cfg)
            if before_weight['checkpoint']['ready']:
                completed+=1;log('Usable checkpoint already present; no Base weight download required')
            elif before_weight['checkpoint'].get('default_exists'):
                default=Path(before_weight['checkpoint']['default_path'])
                update_model('sdxl',{'config':{'checkpoint':str(default)}})
                completed+=1;log('Official Base checkpoint already present; repaired active checkpoint path without downloading weights')
            else:
                state(status='running',stage='checkpoint',completed=completed,total=3,message='Downloading missing SDXL Base 1.0 checkpoint…',current_task='checkpoint',assets=before_weight)
                log('Downloading missing official SDXL Base 1.0 checkpoint')
                dest=MODELS_ROOT/'SDXL';dest.mkdir(parents=True,exist_ok=True)
                hf_hub_download(repo_id=SDXL_REPO,filename=SDXL_FILE,local_dir=dest)
                default=dest/SDXL_FILE
                if default.is_file():update_model('sdxl',{'config':{'checkpoint':str(default)}})
                completed+=1

            final_cfg=(model_by_id('sdxl') or {}).get('config') or {}
            final=asset_status(final_cfg)
            if not final['ready']:
                raise RuntimeError('Download ended but one or more required SDXL components are still missing: '+', '.join(final['missing_labels']))
            state(status='completed',stage='ready',completed=3,total=3,message='SDXL ready. All required files are present.',current_task='',assets=final,error='')
            log('Completed successfully')
            return 0
        except Exception as exc:
            try:assets=asset_status((model_by_id('sdxl') or {}).get('config') or {})
            except Exception:assets={}
            msg=str(exc)[:1800]
            state(status='failed',stage='failed',message='SDXL setup did not complete. Existing files were preserved.',error=msg,assets=assets)
            log('FAILED: '+msg)
            return 1
        finally:
            try:file_lock.flock(lock,file_lock.LOCK_UN)
            except Exception:pass


if __name__=='__main__':
    raise SystemExit(main())
