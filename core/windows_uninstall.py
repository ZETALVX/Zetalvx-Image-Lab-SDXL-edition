"""Native Windows uninstall launch: no Python runner/venv PID handoff.

The authenticated HTTP boundary still validates the plan and holds lifecycle
locks during launch. The independent OS process stops the app and removes it.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import time
from pathlib import Path
from core.install_layout import atomic_json
from core.platform_support import process_start

ENGINE = 'native-powershell-v1'

def powershell_executable() -> str:
    root = os.environ.get('SystemRoot', r'C:\Windows')
    return str(Path(root) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe')

def launch(plan: dict, source: Path, report_dir: Path, job_id: str):
    """Return the actual PowerShell Popen and its OS creation identity."""
    source, report_dir = Path(source), Path(report_dir)
    home = Path(plan['home']).resolve()
    destination = report_dir.resolve()
    if destination == home or home in destination.parents:
        raise ValueError('Uninstall helper must run outside the installation.')
    for src, dst in [('uninstall_windows.ps1', 'cleanup.ps1'), ('uninstall_tree.cs', 'uninstall_tree.cs')]:
        shutil.copy2(source / 'scripts' / src, report_dir / dst)
    spec = {**plan, 'schema': 'zetalvx.native-uninstall.v1', 'id': job_id,
            'gui': True, 'recover_legacy': False}
    atomic_json(report_dir / 'spec.json', spec)
    # A real Windows PowerShell process (not venv python.exe -> another python.exe).
    # Logging and progress are written by the TEMP helper itself, including errors.
    process = subprocess.Popen(
        [powershell_executable(), '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
         '-File', str(report_dir / 'cleanup.ps1'), '-SpecPath', str(report_dir / 'spec.json')],
        cwd=report_dir, close_fds=True, creationflags=0x00000010,  # CREATE_NEW_CONSOLE
    )
    identity = None
    for _ in range(40):
        identity = process_start(process.pid)
        if identity:
            break
        if process.poll() is not None:
            break
        time.sleep(.05)
    if not identity:
        try:
            process.terminate()
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
        raise RuntimeError('Cannot track native uninstall helper. Report: ' + str(report_dir))
    return process, identity
