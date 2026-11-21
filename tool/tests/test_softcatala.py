import unittest

from lexlib import softcatala as SC
from tests.helpers import DICT_TOOLS

P = SC.DictToolsPaths(DICT_TOOLS)


class SoftcatalaTest(unittest.TestCase):
    def test_exclusions(self):
        forms, lemmas = SC.load_exclusions(P.exclusions)
        self.assertIn('barco', forms)
        self.assertNotIn('gat', forms)  # només a catalan-valencia
        self.assertEqual(lemmas, set())

    def test_hunspell(self):
        forms, forbidden = SC.expand_hunspell(P.hunspell_dic, P.hunspell_aff)
        for f in ('casa', 'cases', 'gat', 'gata', 'gats', 'gates', 'mesos', 'putes'):
            self.assertIn(f, forms)
        self.assertNotIn('anglés', forms)
        self.assertNotIn('aixo', forms)
        self.assertEqual(forbidden, {'aixo'})

    def test_lt(self):
        entries = list(SC.iter_lt(P.lt_dictionary))
        self.assertIn(SC.LtEntry('cases', 'casa', 'NCFP000'), entries)
        self.assertGreater(len(entries), 40)

    def test_tags(self):
        self.assertTrue(SC.is_general_tag('VMIP1S0C'))
        self.assertTrue(SC.is_general_tag('VMSI2P04'.replace('4', '2')))
        self.assertFalse(SC.is_general_tag('VMSP3S0V'))
        self.assertFalse(SC.is_general_tag('VMSI2P03'))
        self.assertTrue(SC.is_general_tag('NCFS000'))
        for t in ('NPCSG00', 'Y', 'Zp', 'Fs'):
            self.assertTrue(SC.is_excluded_tag(t))
        self.assertFalse(SC.is_excluded_tag('NCMS000'))

    def test_sources(self):
        src = SC.lemma_sources(P.arrel)
        self.assertEqual(src['anticòs'], {'dsalut'})
        self.assertEqual(src['gat'], {'LT'})
        self.assertEqual(src['edifici'], {'LT', 'dsalut'})
        self.assertNotIn('#intima', src)
        self.assertNotIn('intima', src)

    def test_frequencies(self):
        freq = SC.load_frequencies(P.freq_forms)
        self.assertEqual(freq['que'], 900000)
        self.assertEqual(freq['col·legi'], 2500)


if __name__ == '__main__':
    unittest.main()
