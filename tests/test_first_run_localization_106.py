# Source export: cache-buster expectation aligned to unchanged Windows 1.0.16 input templates (1.0.18).
import json,re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LANGS={'en','it','es','fr','de','pt','ru','zh','ja','ko','tr','ar'}
class FirstRunLocalization106(unittest.TestCase):
    def test_locale_entries_complete(self):
        js=(ROOT/'static/first-run-locale.js').read_text(encoding='utf-8')
        payload=re.search(r'const entries=(\[.*\]);\nC\.entries',js,re.S).group(1)
        entries=json.loads(payload)
        self.assertGreaterEqual(len(entries),10)
        for e in entries:
            self.assertEqual(set(e['text']),LANGS,e['sources'][0])
            for k,v in e['text'].items(): self.assertTrue(v.strip(),(e['sources'][0],k))
    def test_template_has_no_fixed_bilingual_or_italian_setup_copy(self):
        s=(ROOT/'templates/first_run.html').read_text(encoding='utf-8')
        self.assertIn('/static/first-run-locale.js?v=1.0.18',s)
        self.assertNotIn('Codice per configurare un altro dispositivo / Setup code for another device',s)
        self.assertNotIn('Valido 20 minuti',s)
        self.assertNotIn('Stai configurando da un altro dispositivo',s)
        self.assertIn('<b>Setup code for another device</b>',s)
        self.assertIn('<code data-no-i18n>{{ setup_code_display }}</code>',s)
    def test_title_localizes(self):
        js=(ROOT/'static/first-run-locale.js').read_text(encoding='utf-8')
        self.assertIn("window.addEventListener('languagechange',title)",js)
        self.assertIn("window.ZI18n.t('First setup')",js)
if __name__=='__main__': unittest.main()
