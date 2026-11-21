import collections
import unittest

import build_lexicon as L
from lexlib import normalize as N
from tests import pipeline_fixture as PF


def spellings(acc, key):
    sp = acc[key]
    return [N.trivial_spelling(key)] if sp is None else sp


class WhitelistTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acc = PF.accepted()
        cls.forms = {f for k in cls.acc for f in spellings(cls.acc, k)}

    def test_barbarism_excluded(self):
        self.assertNotIn('barco', self.forms)

    def test_proper_noun_and_abbreviation_excluded(self):
        self.assertNotIn('GIRONA', self.acc)
        self.assertNotIn('ETC', self.acc)

    def test_non_general_accent_excluded(self):
        self.assertIn('anglès', self.forms)
        self.assertNotIn('anglés', self.forms)

    def test_non_central_verb_excluded(self):
        self.assertNotIn('cante', self.forms)       # variant valenciana (V)
        self.assertNotIn('cantàreu', self.forms)    # només amb variant 3
        self.assertIn('canto', self.forms)          # variant central (C)

    def test_forbidden_hunspell_excluded(self):
        self.assertNotIn('aixo', self.forms)

    def test_conjugated_accepted(self):
        self.assertEqual(spellings(self.acc, N.grid_key('cantàvem')), ['cantàvem'])
        self.assertIn('cantéssiu', self.forms)     # imperfet de subjuntiu central (2)
        self.assertNotIn('cantàssiu', self.forms)  # terminacions -àssiu (4), no centrals

    def test_length_and_clitics(self):
        self.assertNotIn('OU', self.acc)
        self.assertFalse(any('-' in f for f in self.forms))

    def test_line_format(self):
        lines = (PF.built() / 'accepted.tsv').read_text(encoding='utf-8').splitlines()
        self.assertIn('CASA', lines)
        self.assertIn('MES\tmes|més', lines)
        self.assertIn('COĿEGI', lines)
        self.assertIn('CAFE\tcafè', lines)
        keys = [ln.split('\t')[0] for ln in lines]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(spellings(self.acc, 'COĿEGI'), ['col·legi'])

    def test_ll_distinct(self):
        self.assertIn('COLLITA', self.acc)

    def test_blacklist_effect(self):
        self.assertNotIn('MALPARIT', self.acc)
        self.assertNotIn('MALPARIDA', self.acc)
        self.assertNotIn('PUTES', self.acc)
        self.assertIn('BOSSA', self.acc)  # sensitive: acceptada


class SolutionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acc = PF.accepted()
        cls.sol = PF.solutions()

    def test_plural_and_feminine(self):
        self.assertEqual((self.sol['cases']['kind'], self.sol['cases']['lemma']), ('plural', 'casa'))
        self.assertEqual(self.sol['gata']['kind'], 'femeni')
        self.assertEqual(self.sol['gates']['kind'], 'femeni_plural')
        self.assertEqual(self.sol['gats']['kind'], 'plural')
        self.assertEqual(self.sol['casa']['kind'], 'lemma')
        self.assertEqual(self.sol['cantar']['pos'], 'V')
        self.assertEqual(self.sol['que']['pos'], 'C')

    def test_conjugated_not_solution(self):
        self.assertNotIn('cantéssiu', self.sol)
        self.assertNotIn('cantàvem', self.sol)

    def test_blacklisted_not_solution(self):
        for f in ('bossa', 'bosses', 'poma', 'puta', 'malparit'):
            self.assertNotIn(f, self.sol)

    def test_frequency_and_terminology(self):
        self.assertNotIn('gos', self.sol)          # freq 4
        self.assertNotIn('anticòs', self.sol)      # només dsalut, freq 30
        self.assertIn('edifici', self.sol)         # LT+dsalut
        self.assertIn('folla', self.sol)           # freq 5 (límit)

    def test_rows(self):
        lines = (PF.built() / 'solutions.tsv').read_text(encoding='utf-8').splitlines()
        self.assertEqual(lines[0].split('\t'), list(L.SOLUTIONS_HEADER))
        ranks = []
        for ln in lines[1:]:
            r = ln.split('\t')
            self.assertEqual(len(r), 10)
            self.assertIn(r[2], r[8].split('|'))
            self.assertTrue(set(filter(None, r[9].split('|'))) <= set(r[8].split('|')))
            self.assertEqual(N.grid_key(r[1]), r[0])
            self.assertIn(r[1], spellings(self.acc, r[0]))
            self.assertEqual(int(r[7]), L.band_for_rank(int(r[6])))
            ranks.append(int(r[6]))
        self.assertEqual(ranks, list(range(1, len(ranks) + 1)))

    def test_solution_exclusions_keep_ranks(self):
        # retirar-solucions-dubtoses: el lema i les seves flexions surten sense moure rangs.
        cands = [L.Candidate('CASA', 'casa', 'casa', 'lemma', 'N', 30),
                 L.Candidate('SETA', 'seta', 'seta', 'lemma', 'N', 20),
                 L.Candidate('SETES', 'setes', 'seta', 'plural', 'N', 15),
                 L.Candidate('MES', 'mes', 'mes', 'lemma', 'N', 10)]
        ranked, rej = L.rank_candidates(cands)
        kept = L.drop_excluded_solutions(ranked, {'seta': 'no_solution'}, rej)
        self.assertEqual([(c.form, r) for c, r, _ in kept], [('casa', 1), ('mes', 4)])
        self.assertEqual(rej['exclusio_solucio_manual'], 2)

    def test_ties_by_key_and_form(self):
        cands = [L.Candidate('MES', 'més', 'més', 'lemma', 'R', 10),
                 L.Candidate('MES', 'mes', 'mes', 'lemma', 'N', 10),
                 L.Candidate('CASA', 'casa', 'casa', 'lemma', 'N', 10)]
        ranked, _ = L.rank_candidates(cands)
        self.assertEqual([c.form for c, _, _ in ranked], ['casa', 'mes', 'més'])


class BandsTest(unittest.TestCase):
    def test_band_limits(self):
        self.assertEqual(L.band_for_rank(1200), 1)
        self.assertEqual(L.band_for_rank(5000), 1)
        self.assertEqual(L.band_for_rank(5001), 2)
        self.assertEqual(L.band_for_rank(12000), 2)
        self.assertEqual(L.band_for_rank(20000), 3)
        self.assertEqual(L.band_for_rank(25000), 4)
        self.assertEqual(L.band_for_rank(40000), 5)
        self.assertIsNone(L.band_for_rank(40001))

    def test_rank_40001_dropped(self):
        cands = [L.Candidate(f'K{i:05d}', f'k{i:05d}', 'x', 'lemma', 'N', 100000 - i)
                 for i in range(40001)]
        rej = collections.Counter()
        ranked, rej = L.rank_candidates(cands, rej)
        self.assertEqual(len(ranked), 40000)
        self.assertEqual(ranked[-1][1:], (40000, 5))
        self.assertEqual(rej['rang_superior_40000'], 1)

    def test_check_solutions_aborts(self):
        ranked = [(L.Candidate('INVENTADA', 'inventada', 'inventada', 'lemma', 'N', 50), 1, 1)]
        with self.assertRaises(L.BuildError) as cm:
            L.check_solutions(ranked, {'CASA': ['casa']}, set(), set())
        self.assertIn('inventada', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
