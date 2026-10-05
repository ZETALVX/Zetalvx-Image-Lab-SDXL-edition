"""File.Replace regression. Native execution is reported as skipped without PowerShell."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('powershell.exe') or shutil.which('pwsh')

class WindowsUninstallAtomic116(unittest.TestCase):
    def helper(self):
        text = (ROOT / 'scripts/uninstall_windows.ps1').read_text(encoding='utf-8')
        return text.split('function Write-JsonAtomic', 1)[1].split('function Write-CleanupProgress', 1)[0]

    def test_replace_passes_clr_null_not_empty_string(self):
        body = self.helper()
        self.assertIn('[IO.File]::Replace($Tmp, $Path, [System.Management.Automation.Language.NullString]::Value)', body)
        self.assertNotIn('[IO.File]::Replace($Tmp, $Path, $null)', body)
        self.assertEqual(body.count('[IO.File]::Replace('), 1)

    def test_atomic_write_and_temp_cleanup_retained(self):
        body = self.helper()
        self.assertIn('[IO.File]::WriteAllText($Tmp, $Text, (New-Object Text.UTF8Encoding($false)))', body)
        self.assertIn('else { [IO.File]::Move($Tmp, $Path) }', body)
        self.assertIn('finally { if ([IO.File]::Exists($Tmp)) { [IO.File]::Delete($Tmp) } }', body)
        self.assertNotIn('[IO.File]::Delete($Path)', body)
        self.assertNotIn('[IO.File]::WriteAllText($Path', body)

    def test_package_version_identifiers_agree(self):
        version = json.loads((ROOT / 'UPDATE_PACKAGE.json').read_text())['version']
        for name in ('BUILD_PROVENANCE.json', 'RELEASE_STATUS.json'):
            self.assertEqual(json.loads((ROOT / name).read_text())['version'], version)
        for name in ('core/install_layout.py', 'core/runtime_env.py'):
            self.assertEqual(re.search(r"^VERSION = '([^']+)'", (ROOT / name).read_text(), re.M).group(1), version)

    @unittest.skipUnless(POWERSHELL, 'PowerShell unavailable: JSON overwrite regression NOT executed')
    def test_real_powershell_json_overwrites(self):
        subprocess.run([
            POWERSHELL, '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(ROOT / 'tests/test_windows_uninstall_atomic_116.ps1'),
        ], check=True, timeout=45)

if __name__ == '__main__':
    unittest.main()
