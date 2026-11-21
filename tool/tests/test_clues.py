import unittest

import build_clues as C
from lexlib import wiktionary as W
from tests import pipeline_fixture as PF


def clues() -> dict[str, dict[str, str]]:
    lines = (PF.built('clues') / 'clues.tsv').read_text(encoding='utf-8').splitlines()
    header = lines[0].split('\t')
    return {r[1]: dict(zip(header, r)) for r in (ln.split('\t') for ln in lines[1:])}


class CleanTest(unittest.TestCase):
    def test_links(self):
        self.assertEqual(C.clean_sense('[[edifici|Edifici]] destinat a [[habitatge]].'),
                         'Edifici destinat a habitatge')

    def test_templates(self):
        self.assertEqual(C.clean_sense('Animal {{q|domèstic}} que borda.'), 'Animal que borda')
        self.assertEqual(C.clean_sense('Relatiu a {{w|Santa Eugènia (municipi)|Santa Eugènia}}.'),
                         'Relatiu a Santa Eugènia')
        self.assertIsNone(C.clean_sense('{{sinònim|ca|fita}}'))
        self.assertIsNone(C.clean_sense('{{def-meta|Usat només en l’expressió}}'))
        self.assertEqual(C.clean_sense("{{marca|ca|botànica}} ''Herba'' alta."), 'Herba alta')

    def test_html_and_refs(self):
        self.assertEqual(C.clean_sense('Fruit de la [[pomera]].<ref>{{R:DIEC}}</ref>'),
                         'Fruit de la pomera')
        self.assertEqual(C.clean_sense('Peix <small>gros</small> de mar'), 'Peix gros de mar')

    def test_parentheses_removed(self):
        self.assertEqual(C.clean_sense("Mamífer felí (''Felis catus''), domèstic."),
                         'Mamífer felí, domèstic')

    def test_remissions(self):
        for s in ('Variant de [[gat]].', 'Vegeu [[gats]].', 'Forma de [[casa]].',
                  'Plural de [[casa]].', 'Femení de [[gat]].', '[[File:x.jpg]] Gat'):
            with self.subTest(s=s):
                self.assertIsNone(C.clean_sense(s))

    def test_length(self):
        self.assertIsNone(C.shorten('x' * 140))
        self.assertIsNone(C.shorten('Curt'))
        long_semicolon = 'Lloc on resideix una persona; ' + 'construcció ' * 10
        self.assertEqual(C.shorten(long_semicolon), 'Lloc on resideix una persona')
        self.assertIsNone(C.shorten('x' * 90 + '; resta'))


class RevealTest(unittest.TestCase):
    def test_root(self):
        self.assertEqual(C.root_of('FOLLIA'), 'FOLL')
        self.assertEqual(C.root_of('CASA'), 'CAS')
        self.assertEqual(C.root_of('GAT'), 'GAT')
        self.assertEqual(C.reveals('Qualitat de foll', 'follia', 'follia', set()), 'foll')

    def test_literal_and_forms(self):
        self.assertEqual(C.reveals('Felí com els gats', 'gat', 'gat', {'gats'}), 'gats')
        self.assertEqual(C.reveals('(plural) Animal com el gat', 'gats', 'gat', set()), 'gat')

    def test_accents_do_not_hide(self):
        self.assertEqual(C.reveals('Beguda de CAFE torrat', 'cafè', 'cafè', set()), 'CAFE')

    def test_strict_rules(self):
        self.assertEqual(C.reveals('Acció de lacerar', 'laceració', 'laceració', set()), 'lacerar')
        self.assertEqual(C.reveals('Tornar a ajustar', 'reajustar', 'reajustar', set()), 'ajustar')
        # sense el prefix re- la regla bàsica (també la del test Dart) ja ho detecta
        self.assertEqual(C.reveals('Tornar a ajustar', 'reajustar', 'reajustar', set(),
                                   strict=False), 'ajustar')
        self.assertIsNone(C.reveals('Fer més just', 'reajustar', 'reajustar', set(),
                                    strict=False))
        self.assertEqual(C.reveals("Acció d'armar-se", 'armament', 'armament', set()), 'armar')
        self.assertEqual(C.reveals("Qualitat d'atroç", 'atrocitat', 'atrocitat', set()), 'atroç')
        self.assertEqual(C.reveals('Suavitzar', 'assuavir', 'assuavir', set()), 'Suavitzar')
        self.assertIsNone(C.reveals('Edifici destinat a habitatge', 'casa', 'casa', {'cases'}))
        self.assertIsNone(C.reveals('Qualitat del que és atroç', 'bondat', 'bondat', set()))

    def test_anaphora(self):
        cb = C.ClueBuilder({}, {}, set(), {'que', 'té', 'el', 'material', 'homònim'})
        self.assertFalse(cb.acceptable('Que té el material homònim', 'fluid', 'fluid'))

    def test_bad_words(self):
        lex = {'persona', 'dolenta', 'molt'}
        self.assertEqual(C.bad_word('Persona malparida', {'malparida'}, lex | {'malparida'}),
                         'malparida')
        self.assertEqual(C.bad_word('Persona molt bonica', set(), lex), 'bonica')
        self.assertIsNone(C.bad_word("Persona d'Olot molt dolenta", set(), lex))


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clues = clues()
        cls.sol = PF.solutions()

    def test_noun(self):
        self.assertEqual(self.clues['casa']['clue'], 'Edifici destinat a habitatge')
        self.assertEqual(self.clues['casa']['source'], 'casa')

    def test_other_language_section(self):
        self.assertIn('mes', self.sol)
        self.assertNotIn('mes', self.clues)

    def test_dialectal_first_sense(self):
        # la primera accepció (dialectal) se salta; la segona revela l'arrel (re-collits)
        self.assertIn('collita', self.sol)
        self.assertNotIn('collita', self.clues)

    def test_only_remissions(self):
        self.assertNotIn('mamífer', self.clues)

    def test_semicolon_cut_and_too_long(self):
        self.assertEqual(self.clues['habitatge']['clue'],
                         'Lloc on resideix una persona o una família de manera estable')
        self.assertIn('edifici', self.sol)
        self.assertNotIn('edifici', self.clues)

    def test_reveal_filters(self):
        for f in ('follia', 'gat', 'cafè'):
            self.assertIn(f, self.sol)
            self.assertNotIn(f, self.clues)

    def test_inflected_prefix(self):
        self.assertEqual(self.clues['cases']['clue'], '(plural) Edifici destinat a habitatge')
        self.assertEqual(self.clues['cases']['source'], 'casa')
        self.assertEqual(self.clues['cases']['lemma'], 'casa')
        self.assertEqual(self.clues['col·legis']['clue'], '(plural) Establiment d’ensenyament')

    def test_conjunction_pos(self):
        self.assertEqual(self.clues['que']['clue'], 'Introdueix una oració subordinada')

    def test_every_clue_is_candidate(self):
        for form, row in self.clues.items():
            self.assertIn(form, self.sol)
            self.assertEqual(self.sol[form]['key'], row['key'])

    def test_orphan_fails(self):
        with self.assertRaises(Exception):
            C.check_clues([C.ClueRow('XYZ', 'xyz', 'xyz', 'Pista inventada', 'xyz')], [])

    def test_prefix_cannot_reveal(self):
        page = W.parse_ca_section('femení', '== {{-ca-}} ==\n=== Adjectiu ===\n# De les dones.\n')
        cb = C.ClueBuilder({'femení': page}, {'femení': {'femenina'}}, set(),
                           {'de', 'les', 'dones'})
        self.assertIsNone(cb.clue_for('femenina', 'femení', 'femeni', 'A'))

    def test_absolute_word_skips_sense(self):
        page = W.parse_ca_section('prova', '== {{-ca-}} ==\n=== Nom ===\n# Persona malparida.\n')
        cb = C.ClueBuilder({'prova': page}, {}, {'malparida'}, {'persona', 'malparida'})
        self.assertIsNone(cb.clue_for('prova', 'prova', 'lemma', 'N'))


if __name__ == '__main__':
    unittest.main()
