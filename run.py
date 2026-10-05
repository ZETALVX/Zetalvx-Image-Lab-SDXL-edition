#!/usr/bin/env python3
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.24; Apache-2.0; see CHANGELOG.md.
"""Source dispatcher for Zetalvx Image Lab - SDXL Edition 0.1.0.24 (Apache-2.0)."""
import importlib, sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
TARGETS={'launcher':'launcher','web':'app','image':'services.image_worker',
 'identity':'services.identity_worker','training':'services.training_worker',
 'transformers':'vision.transformers_worker','child':'vision.child_exec',
 'identity-code':'scripts.prepare_identity_code','models':'scripts.download_models',
 'preflight':'core.commercial_preflight'}
if len(sys.argv)<2 or sys.argv[1] not in TARGETS:
    raise SystemExit('Expected component: '+', '.join(TARGETS))
component=sys.argv.pop(1)
try:
    if component in {'image','identity','training','transformers'}:
        from core.runtime_security import require_reviewed_torch
        require_reviewed_torch()
    importlib.import_module(TARGETS[component]).main()
except (RuntimeError,ValueError,OSError) as e: print('[ERROR]',e,file=sys.stderr);sys.exit(1)
