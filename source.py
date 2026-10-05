#!/usr/bin/env python3
"""Manual-source entry point. No installer, dependency downloads or PATH changes.
Added in source-1.0-rc1; Apache-2.0. See LICENSE and NOTICE.
"""
from __future__ import annotations
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def source_home() -> Path:
    from core.platform_support import default_data_root
    installed_home = default_data_root().expanduser().resolve()
    default = installed_home.with_name(installed_home.name + '-Source')
    home = Path(os.environ.get('SDXL_STUDIO_HOME', str(default))).expanduser().resolve()
    if home == installed_home or home == ROOT or home in ROOT.parents or ROOT in home.parents:
        raise ValueError('Use a separate source data directory, outside the checkout and the packaged installation.')
    if any((home/name).exists() or (home/name).is_symlink()
           for name in ('.zetalvx-install.json', 'install-state.json', 'current', 'previous')):
        raise ValueError('This directory belongs to a managed installation. Source mode will not modify it.')
    return home


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    home = source_home()
    if args == ['home']:
        print(home)
        return 0
    if args and args[0] in ('desktop', '_serve'):
        raise ValueError('Use source.py start/stop/status; packaged desktop installation is not included.')
    os.environ['SDXL_STUDIO_HOME'] = str(home)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    # The existing launcher and worker code is unchanged. Workers inherit this home.
    from launcher import main as launcher_main
    sys.argv = [str(ROOT/'launcher.py'), *(args or ['--help'])]
    launcher_main()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print('[ERROR]', exc, file=sys.stderr)
        raise SystemExit(2)
