#!/usr/bin/env python3
"""CLI/installer entry point: same managed, transactional code installer as the GUI."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.runtime_env import initialize_environment
from core.identity_code import CodeInstaller, CodeInstallError, REPO, REVISION, CODE_FILES

def main():
    initialize_environment()
    result=CodeInstaller().prepare()
    print('[OK]',result['message'])
    print('Code:',result['target'])
if __name__=='__main__':
    try:main()
    except (OSError,ValueError) as e:print('[ERROR]',e,file=sys.stderr);sys.exit(1)
