"""Pistes de temporada de Nadal (temporada-nadal, tasques 6.1–6.2)."""
import json
import unittest

import build_clues as BC
import build_manifest as BM
from lexlib import config, tsv

SRC = config.DATA_DIR / 'seasons' / 'nadal' / 'clues.tsv'
OUT = config.LEXICON_DIR / 'seasons' / 'nadal-clues.tsv'
MISLEADING = ('tió', 'mag', 'mags', 'capó', 'pilota', 'mirra', 'panera', 'cotilló', 'presents')


class SeasonCluesSourceTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = BC.load_season_clues(config.DATA_DIR / 'seasons')['nadal']

    def test_misleading_homographs_have_a_season_clue(self):
        for f in MISLEADING:
            self.assertIn(f, self.rows, f)

    def test_label_exception_only_for_declared_forms(self):
        excepted = sorted(f for f, (_, note, _) in self.rows.items()
                          if BC.LABEL_EXCEPTION in note)
        self.assertEqual(excepted, ['parada'])
        # `parades` s'hi afegeix per a Sant Jordi (temporada-sant-jordi 1.8) i `molles` per a
        # la temàtica Cuina (madeixes-tematiques, QA M5).
        self.assertEqual(BC.LABEL_EXCEPTION_FORMS, frozenset({'parada', 'parades', 'molles'}))

    def test_no_escatological_forms(self):
        for f in ('caganer', 'caganers', 'cagatió', 'cagar', 'llufa'):
            self.assertNotIn(f, self.rows)

    def test_typography(self):
        for f, (clue, _, where) in self.rows.items():
            self.assertNotIn("'", clue, where)
            self.assertFalse(clue.endswith('.'), where)


@unittest.skipUnless(OUT.exists(), 'pistes de temporada no generades')
class SeasonCluesPackagedTest(unittest.TestCase):

    def test_packaged_equals_source(self):
        header, rows = tsv.read_tsv(OUT)
        self.assertEqual(header, list(BC.HEADER))
        got = {r[1]: r[3] for r in rows}
        want = {f: c for f, (c, _, _) in
                BC.load_season_clues(config.DATA_DIR / 'seasons')['nadal'].items()}
        self.assertEqual(got, want)
        self.assertEqual({r[4] for r in rows}, {'pròpia'})
        self.assertEqual([(r[0], r[1]) for r in rows], sorted((r[0], r[1]) for r in rows))

    def test_manifest_lists_it_outside_the_fingerprint(self):
        m = json.loads((config.LEXICON_DIR / 'manifest.json').read_text(encoding='utf-8'))
        e = m['files']['seasons/nadal-clues.tsv']
        self.assertEqual((e['license'], e['packaged']), ('CC-BY-SA-4.0', True))
        self.assertEqual(BM.lexicon_fingerprint(m), m['lexicon_fingerprint'])
        self.assertNotIn('seasons/nadal-clues.tsv', BM.WORD_FILES)
        m2 = json.loads(json.dumps(m))
        m2['files']['seasons/nadal-clues.tsv']['sha256'] = '0' * 64
        self.assertEqual(BM.lexicon_fingerprint(m2), m['lexicon_fingerprint'])

    def test_licence_notice_lists_the_file(self):
        notice = (config.ASSETS_DIR / 'licenses' / 'CC-BY-SA-4.0.txt').read_text(encoding='utf-8')
        self.assertIn('assets/lexicon/seasons/nadal-clues.tsv', notice)


if __name__ == '__main__':
    unittest.main()
