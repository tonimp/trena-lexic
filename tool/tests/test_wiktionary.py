import bz2
import tempfile
import unittest
from pathlib import Path

from lexlib import wiktionary as W
from tests.helpers import MINI_DUMP


class WiktionaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {p.title: p for p in W.iter_pages(MINI_DUMP)}

    def test_only_ca_main_namespace(self):
        self.assertIn('casa', self.pages)
        self.assertNotIn('mes', self.pages)  # només secció {{-es-}}
        self.assertNotIn('Viquidiccionari:Ajuda', self.pages)

    def test_senses_and_headers(self):
        casa = self.pages['casa']
        self.assertEqual([s.text for s in casa.senses],
                         ['[[edifici|Edifici]] destinat a [[habitatge]].', "Seu d'una entitat."])
        self.assertEqual(casa.senses[0].header, 'Nom')
        self.assertEqual(casa.senses[0].pos, 'N')
        self.assertEqual(self.pages['que'].senses[0].pos, 'C')

    def test_spanish_section_ignored(self):
        self.assertNotIn('Edificio.', [s.text for s in self.pages['casa'].senses])

    def test_form_of(self):
        self.assertTrue(all(s.is_form_of for s in self.pages['cases'].senses))
        self.assertEqual(self.pages['cases'].senses[1].header, 'Verb')

    def test_marks(self):
        bossa = self.pages['bossa']
        self.assertEqual(bossa.senses[0].marks, ())
        self.assertEqual(bossa.senses[1].marks, ('mallorquí', 'vulgar'))
        self.assertEqual(self.pages['puta'].senses[0].marks, ('ofensiu', 'vulgar'))
        self.assertEqual(self.pages['poma'].senses[0].marks, ('fruites',))

    def test_filter_titles_and_bz2(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'mini.xml.bz2'
            p.write_bytes(bz2.compress(MINI_DUMP.read_bytes()))
            titles = [pg.title for pg in W.iter_pages(p, titles={'gat', 'follia', 'mes'})]
        self.assertEqual(titles, ['gat', 'follia'])


if __name__ == '__main__':
    unittest.main()
