import os
from pathlib import Path
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]

class Release37StaticTests(unittest.TestCase):
    def test_settings_contains_desktop_and_firewall_controls(self):
        html=(ROOT/'templates/index.html').read_text(encoding='utf-8')
        for marker in ('desktopShortcutPanel','desktopShortcutAdd','desktopShortcutRemove','networkFirewallCard','networkFirewallFix'):
            self.assertIn(marker,html)

    def test_firewall_endpoints_present(self):
        app=(ROOT/'app.py').read_text(encoding='utf-8')
        self.assertIn("/api/network/firewall/configure",app)
        self.assertIn("/api/desktop-shortcut",app)

    def test_dedicated_app_icons_present(self):
        self.assertTrue((ROOT/'static/zetalvx-app.ico').is_file())
        self.assertTrue((ROOT/'static/zetalvx-app.png').is_file())
        self.assertGreater((ROOT/'static/zetalvx-app.ico').stat().st_size,1000)

    def test_linux_firewall_status_is_non_mutating(self):
        from core import network_access
        if os.name=='nt': self.skipTest('POSIX-only contract')
        d=network_access.firewall_status(8298,'/tmp/python')
        self.assertFalse(d['supported'])
        self.assertFalse(d['needs_fix'])
        with self.assertRaises(RuntimeError):
            network_access.configure_firewall(8298)

    def test_windows_status_detects_conflict_from_mocked_powershell(self):
        from core import network_access
        payload={
            'supported':True,'platform':'windows','rule_name':network_access.RULE_NAME,'port':8298,
            'program':'C:/Python/python.exe','rule_present':True,'rule_enabled':True,'rule_action':'Allow',
            'rule_profile':'Any','rule_port':'8298','remote_address':'LocalSubnet','network_profile':'Public',
            'conflicting_blocks':{'name':'block1','display_name':'python.exe','profile':'Public','program':'C:/Python/python.exe'}
        }
        with mock.patch.object(network_access.os,'name','nt'), mock.patch.object(network_access,'_ps_json',return_value=payload):
            d=network_access.firewall_status(8298,'C:/Python/python.exe')
        self.assertTrue(d['rule_ok'])
        self.assertTrue(d['needs_fix'])
        self.assertEqual(len(d['conflicting_blocks']),1)

if __name__=='__main__': unittest.main()
