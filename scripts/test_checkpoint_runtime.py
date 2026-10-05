#!/usr/bin/env python3
"""Actual CPU checkpoint validator smoke; run in the AI runtime (not the web test suite)."""
import json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.runtime_security import require_reviewed_torch

def main():
    version=require_reviewed_torch()
    import torch
    from core.training_manager import _run_tensor_validator
    with tempfile.TemporaryDirectory() as tmp:
        good=Path(tmp)/'good.pt';custom=Path(tmp)/'custom.pt';nonfinite=Path(tmp)/'nonfinite.pt'
        torch.save({'tensor':torch.arange(6,dtype=torch.float32)},good)
        torch.save({'custom':SimpleNamespace(x=1)},custom)
        torch.save({'tensor':torch.tensor([float('nan')])},nonfinite)
        with patch('core.platform_support.venv_python',return_value=Path(sys.executable)):
            valid=_run_tensor_validator(['torch',good],timeout=60)
            rejected=_run_tensor_validator(['torch',custom],timeout=60)
            nan=_run_tensor_validator(['torch',nonfinite],timeout=60)
        assert valid['valid'] and valid['parameters']==6,valid
        assert not rejected['valid'] and rejected.get('error'),rejected
        assert not nan['valid'] and nan['nan_values']==1,nan
        print(json.dumps({'torch':version,'device':'cpu','checks_passed':3,
            'valid_tensor_checkpoint':True,'custom_pickle_object_rejected':True,
            'nan_checkpoint_rejected':True,'gpu_validated':False},indent=2))
if __name__=='__main__':main()
