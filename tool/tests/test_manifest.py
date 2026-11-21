import json
import re
import unittest

import build_manifest as M
from lexlib import config
from lexlib import sources as S
from tests import pipeline_fixture as PF

# Paraules no catalanes que no han d'aparèixer en textos visibles (auditoria bàsica).
NON_CATALAN = re.compile(r'\b(commit|the|and|of|license|with|from|words|de la palabra|'
                         r'definiciones|colaboradores|licencia|palabras)\b', re.I)


def check_manifest(test: unittest.TestCase, lexicon_dir):
    m = json.loads((lexicon_dir / 'manifest.json').read_text(encoding='utf-8'))
    test.assertEqual(m['schema_version'], M.SCHEMA_VERSION)
    for name, entry in m['files'].items():
        path = lexicon_dir / name
        test.assertEqual(S.sha256_file(path), entry['sha256'], name)
        data = path.read_bytes()
        test.assertEqual(len(data), entry['bytes'], name)
        test.assertEqual(data.count(b'\n'), entry['lines'], name)
        test.assertFalse(data.startswith(b'\xef\xbb\xbf'), f'{name} amb BOM')
        test.assertNotIn(b'\r', data, name)
    c = m['counts']
    test.assertEqual(c['accepted_keys'], m['files']['accepted.tsv']['lines'])
    test.assertEqual(c['solutions'], m['files']['solutions.tsv']['lines'] - 1)
    test.assertEqual(c['clues'], m['files']['clues.tsv']['lines'] - 1)
    test.assertEqual(c['blacklist_forms'], m['files']['blacklist.tsv']['lines'] - 1)
    test.assertEqual(sum(c['solutions_by_band'].values()), c['solutions'])
    test.assertEqual(sum(c['blacklist_by_level'].values()), c['blacklist_forms'])
    test.assertEqual(m['files']['clues.tsv']['license'], 'CC-BY-SA-4.0')
    test.assertEqual(m['files']['accepted.tsv']['license'], 'LGPL-2.1-or-later')
    test.assertFalse(m['files']['blacklist.tsv']['packaged'])
    return m


def check_credits(test: unittest.TestCase, path):
    cr = json.loads(path.read_text(encoding='utf-8'))
    by_id = {e['id']: e for e in cr['entries']}
    vq = by_id['viquidiccionari']
    test.assertEqual(vq['text'], 'Definicions: Viquidiccionari, col·laboradors del Viquidiccionari.')
    test.assertEqual(vq['license'], 'CC BY-SA 4.0')
    test.assertTrue(vq['license_url'].startswith('https://creativecommons.org/licenses/by-sa/4.0'))
    test.assertEqual(vq['dump_date'], S.load_lock().wiktionary.dump_date)
    sc = by_id['softcatala']
    test.assertEqual(sc['name'], 'Softcatalà – catalan-dict-tools')
    test.assertEqual(sc['license'], 'LGPL-2.1 o posterior')
    lock = S.load_lock().softcatala
    d = lock.commit_date[:10]
    test.assertEqual(sc['version'],
                     f'revisió {lock.commit[:7]} del {d[8:10]}/{d[5:7]}/{d[0:4]}')
    test.assertRegex(vq['version'], r'^bolcat del \d\d/\d\d/\d{4}$')
    test.assertTrue(any('Jaume Ortolà' in x for x in sc['copyright']))
    for e in cr['entries']:
        for field in ('text', 'note', 'version', 'license'):
            test.assertIsNone(NON_CATALAN.search(e[field]), f'{e["id"]}.{field}: {e[field]}')


class FixtureManifestTest(unittest.TestCase):
    def test_manifest_and_credits(self):
        out = PF.built('manifest')
        check_manifest(self, out)
        check_credits(self, out / 'assets' / 'credits' / 'lexic.json')
        self.assertTrue((out / 'assets' / 'licenses' / 'LGPL-2.1.txt').exists())
        self.assertIn('CC BY-SA 4.0', (out / 'assets' / 'licenses' / 'CC-BY-SA-4.0.txt')
                      .read_text(encoding='utf-8'))

    def test_detects_manual_edit(self):
        out = PF.built('manifest')
        m = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        self.assertNotEqual(m['files']['accepted.tsv']['sha256'],
                            S.sha256_file(out / 'solutions.tsv'))


class RealAssetsTest(unittest.TestCase):
    def test_real_manifest(self):
        if not (config.LEXICON_DIR / 'manifest.json').exists():
            self.skipTest('assets no generats')
        check_manifest(self, config.LEXICON_DIR)
        check_credits(self, config.ASSETS_DIR / 'credits' / 'lexic.json')


class PrefixAuditTest(unittest.TestCase):
    def test_prefixes_are_catalan(self):
        import build_clues as C
        self.assertEqual(set(C.PREFIX.values()),
                         {'(plural) ', '(femení) ', '(femení plural) '})


if __name__ == '__main__':
    unittest.main()
