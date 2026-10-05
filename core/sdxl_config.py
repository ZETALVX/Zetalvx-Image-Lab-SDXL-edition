from pathlib import Path
from core.runtime_env import settings

def single_file_config(inpaint=False):
    cfg=settings();p=Path(cfg['inpaint_config' if inpaint else 'sdxl_config']).expanduser()
    if not (p/'model_index.json').is_file():
        raise RuntimeError('SDXL configuration/tokenizers missing. Run creator-sdxl download-configs once (downloads configs only, not model weights).')
    return str(p)
