"""Regressions de la iteració 2 del QA de pipeline-lexic (B1, B2, m1, m2, m3, m5)."""
import collections
import re
import tempfile
import unittest
from pathlib import Path

import build_blacklist as B
import build_clues as C
import build_lexicon as L
from lexlib import config, tsv
from lexlib import normalize as N
from lexlib import softcatala as SC
from lexlib import wiktionary as W

LEX = config.LEXICON_DIR


def write(tmp: str, name: str, text: str) -> Path:
    path = Path(tmp) / name
    path.write_text(text, encoding='utf-8')
    return path


def page(title: str, body: str) -> W.WikiPage:
    return W.parse_ca_section(title, '== {{-ca-}} ==\n' + body)


class RootPrefixTest(unittest.TestCase):
    """B1: les arrels vetades es detecten també darrere d'un prefix o com a subcadena."""

    def rules(self, lines):
        with tempfile.TemporaryDirectory() as tmp:
            return B.load_roots(write(tmp, 'r.tsv', 'pattern\tlevel\treason\texcept\n'
                                      + ''.join(ln + '\n' for ln in lines)))

    def test_prefixed_derivatives(self):
        rules = self.rules(['merd\tabsolute\tescatològic\t',
                            'coll(on|ó$|ut$)\tabsolute\tmalsonant\t',
                            '(prostitu|bordell)\tsensitive\tprostitució\tesbordellar'])
        lemmas = ['emmerdar', 'desmerdegar', 'recollons', 'acollonir', 'collita', 'recollir',
                  'esbordellar', 'bordell', 'amerdar', 'casa']
        got = set(B.root_entries(rules, lemmas))
        self.assertEqual(got, {'emmerdar', 'desmerdegar', 'recollons', 'acollonir',
                               'bordell', 'amerdar'})

    def test_stem_must_be_long_enough(self):
        rules = self.rules(['cul$\tsensitive\tanatomia\t'])
        # «a» + «cul» deixaria una arrel de 3 lletres: no compta com a derivat
        self.assertEqual(set(B.root_entries(rules, ['cul', 'acul'])), {'cul'})

    def test_substring_rules(self):
        rules = self.rules(['~nifar\tsensitive\tdrogues\t'])
        self.assertTrue(rules[0].substring)
        self.assertEqual(set(B.root_entries(rules, ['esnifar', 'nifar', 'casa'])),
                         {'esnifar', 'nifar'})


class SecondarySenseSpreadTest(unittest.TestCase):
    """m2: un veto per accepció secundària no es propaga a altres lemes."""

    LT = [SC.LtEntry('pilota', 'pilota', 'NCFS000'), SC.LtEntry('pilotes', 'pilota', 'NCFP000'),
          SC.LtEntry('pilotes', 'pilotar', 'VMIP2S00'), SC.LtEntry('pilotar', 'pilotar', 'VMN0000'),
          SC.LtEntry('pilot', 'pilot', 'NCMS000'), SC.LtEntry('pilotes', 'pilot', 'NCMP000'),
          SC.LtEntry('mamar', 'mamar', 'VMN0000'), SC.LtEntry('mamà', 'mamar', 'VMIS3S00'),
          SC.LtEntry('mamà', 'mamà', 'NCFS000'), SC.LtEntry('mamen', 'mamar', 'VMIP3P00'),
          SC.LtEntry('figa', 'figa', 'NCFS000'), SC.LtEntry('figues', 'figa', 'NCFP000')]

    def run_propagation(self, vetoes):
        lemmas_of, forms_of = B.propagation_targets(self.LT)
        return {f: v.level for f, (v, _) in B.propagate(vetoes, lemmas_of, forms_of).items()}

    def test_auto_secondary_has_no_spread(self):
        p = page('pilotes', '=== Nom ===\n# Plural de pilota.\n'
                 '# {{marca|ca|vulgar}} Testicles.\n')
        got = B.auto_entries([p])
        self.assertEqual(got['pilotes'].level, 'sensitive')
        self.assertFalse(got['pilotes'].spread)

    def test_non_lemma_source_only_vetoes_itself(self):
        got = self.run_propagation({'pilotes': B.Veto('sensitive', 'x', spread=False)})
        self.assertEqual(got, {'pilotes': 'sensitive'})

    def test_shared_forms_are_not_vetoed(self):
        got = self.run_propagation({'mamar': B.Veto('sensitive', 'x', spread=False)})
        self.assertEqual(got, {'mamar': 'sensitive', 'mamen': 'sensitive'})

    def test_own_inflections_still_vetoed(self):
        got = self.run_propagation({'figa': B.Veto('sensitive', 'x', spread=False)})
        self.assertEqual(got, {'figa': 'sensitive', 'figues': 'sensitive'})

    def test_manual_vetoes_still_spread(self):
        got = self.run_propagation({'pilotes': B.Veto('sensitive', 'x')})
        self.assertIn('pilota', got)


class InheritanceTest(unittest.TestCase):
    """B2: la pista del lema només s'hereta si la flexió és d'aquest lema i categoria."""

    LEX = {'referit', 'als', 'animals', 'dòcil', 'extremitats', 'del', 'braç', 'model',
           'marc', 'per', 'a', 'tallar', 'objectes', 'amo', 'd', 'una', 'fàbrica', 'filla',
           'dels', 'mateixos', 'pares', 'fill', 'de', 'la', 'mateixa', 'mare', 'campanya',
           'naval', 'natural', 'còrsega', 'planta', 'superior', 'edifici', 'plural', 'un'}

    def builder(self, pages, overrides=None, forms_of=None, nominal=None):
        return C.ClueBuilder({p.title: p for p in pages}, forms_of or {}, set(), self.LEX,
                             overrides, nominal_lemmas=nominal)

    def test_labelled_lemma_override_not_inherited(self):
        mans = page('mans', '=== Adjectiu ===\n{{ca-adj|m}}\n\n# Referit als animals, dòcil.\n'
                    '=== Nom ===\n{{ca-nom-forma|fp}}\n\n# {{forma-p|ca|mà}}\n')
        mansa = page('mansa', '=== Adjectiu ===\n{{ca-adj-forma|f}}\n\n# {{forma-f|ca|mans}}\n')
        ov = {'mans': C.Override('replace', '(plural) Extremitats del braç')}
        cb = self.builder([mans, mansa], ov)
        self.assertEqual(cb.clue_for('mans', 'mans', 'lemma', 'A')[0],
                         '(plural) Extremitats del braç')
        self.assertEqual(cb.clue_for('mansa', 'mans', 'femeni', 'A'),
                         ('(femení) Referit als animals, dòcil', 'mans'))

    def test_form_page_of_other_lemma_blocks_inheritance(self):
        lemma = page('cors', '=== Nom ===\n{{ca-nom|m|f=}}\n\n# Natural de Còrsega.\n')
        other = page('corsos', '=== Nom ===\n{{ca-nom-forma|mp}}\n\n# {{forma-p|ca|cor}}\n')
        cb = self.builder([lemma, other], nominal={})
        self.assertIsNone(cb.clue_for('corsos', 'cors', 'plural', 'N'))
        self.assertEqual(cb.rejections['flexio_no_confirmada'], 1)

    def test_masculine_only_section_skipped_for_feminine(self):
        patro = page('patró', '=== Nom ===\n{{ca-nom|m}}\n\n# Model, marc per a tallar objectes.\n'
                     '=== Nom ===\n{{ca-nom|m|f=}}\n\n# Amo d\'una fàbrica.\n')
        patrona = page('patrona', '=== Nom ===\n{{ca-nom-forma|f}}\n\n# {{forma-f|ca|patró}}\n')
        cb = self.builder([patro, patrona])
        self.assertEqual(cb.clue_for('patrona', 'patró', 'femeni', 'N'),
                         ('(femení) Amo d’una fàbrica', 'patró'))
        self.assertEqual(cb.clue_for('patró', 'patró', 'lemma', 'N')[0],
                         'Model, marc per a tallar objectes')

    def test_masculine_only_homograph_sections(self):
        cors = page('cors', '=== Nom ===\n{{ca-nom|m|id=1}}\n\n# Campanya naval.\n'
                    '=== Adjectiu ===\n{{ca-adj|m}}\n\n# Natural de Còrsega.\n'
                    '=== Nom ===\n{{ca-nom|m|f=|id=2}}\n\n# Natural de Còrsega.\n')
        corsa = page('corsa', '=== Nom ===\n{{ca-nom-forma|f}}\n\n# {{forma-f|ca|cors}}\n')
        cb = self.builder([cors, corsa])
        clue = cb.clue_for('corsa', 'cors', 'femeni', 'N')
        self.assertTrue(clue is None or 'Campanya' not in clue[0])

    def test_feminine_of_masculine_noun_uses_adjective(self):
        tort = page('tort', '=== Adjectiu ===\n{{ca-adj|m|f=torta}}\n\n# Que no és recte.\n'
                    '=== Nom ===\n{{ca-nom|m}}\n\n# Perjudici causat.\n')
        torta = page('torta', '=== Adjectiu ===\n{{ca-adj-forma|f}}\n\n# {{forma-f|ca|tort}}\n')
        cb = C.ClueBuilder({'tort': tort, 'torta': torta}, {}, set(),
                           {'que', 'no', 'és', 'recte', 'perjudici', 'causat'})
        self.assertEqual(cb.clue_for('torta', 'tort', 'femeni', 'N'),
                         ('(femení) Que no és recte', 'tort'))

    def test_feminine_plural_via_feminine_page(self):
        germa = page('germà', '=== Nom ===\n{{ca-nom|m|f=}}\n\n# Fill de la mateixa mare.\n')
        germana = page('germana', '=== Nom ===\n{{ca-nom-forma|f}}\n\n'
                       '# Filla dels mateixos pares.\n')
        germanes = page('germanes', '=== Nom ===\n{{ca-nom-forma|fp}}\n\n'
                        '# {{forma-p|ca|germana}}\n')
        cb = self.builder([germa, germana, germanes],
                          forms_of={'germà': {'germà', 'germana', 'germanes', 'germans'}})
        self.assertEqual(cb.clue_for('germanes', 'germà', 'femeni_plural', 'N'),
                         ('(plural) Filla dels mateixos pares', 'germana'))

    def test_no_page_requires_unambiguous_lt(self):
        pis = page('pis', '=== Nom ===\n{{ca-nom|m}}\n\n# Planta superior d\'un edifici.\n')
        self.assertIsNone(self.builder([pis]).clue_for('pisos', 'pis', 'plural', 'N'))
        cb = self.builder([pis], nominal={'pisos': {'pis'}, 'pis': {'pis'}})
        self.assertEqual(cb.clue_for('pisos', 'pis', 'plural', 'N')[0],
                         '(plural) Planta superior d’un edifici')
        cb = self.builder([pis], nominal={'pisos': {'pis', 'piso'}, 'pis': {'pis'}})
        self.assertIsNone(cb.clue_for('pisos', 'pis', 'plural', 'N'))

    def test_combine_label(self):
        self.assertEqual(C.combine_label('plural', 'X'), '(plural) X')
        self.assertEqual(C.combine_label('plural', '(femení) X'), '(femení plural) X')
        self.assertEqual(C.combine_label('femeni_plural', '(femení) X'), '(femení plural) X')
        self.assertIsNone(C.combine_label('plural', '(plural) X'))
        self.assertIsNone(C.combine_label('femeni', '(plural) X'))
        self.assertIsNone(C.combine_label('femeni_plural', '(plural) X'))

    def test_sense_head_and_targets(self):
        p = page('nua', '=== Adjectiu ===\n{{ca-adj-forma|f}}\n\n# {{forma-f|ca|[[nu]]/[[nuu]]}}\n')
        self.assertEqual(p.senses[0].head, 'ca-adj-forma|f')
        self.assertEqual(p.senses[0].form_targets, (('f', 'nu'), ('f', 'nuu')))
        self.assertTrue(page('a', '=== Nom ===\n{{ca-nom|m}}\n# x\n').senses[0].masculine_only)
        for head in ('ca-nom|m|f=', 'ca-nom|mf', 'ca-nom|m|f=gata', 'ca-nom|f'):
            s = page('a', '=== Nom ===\n{{' + head + '}}\n# x\n').senses[0]
            self.assertFalse(s.masculine_only, head)


class OrthographyTest(unittest.TestCase):
    """m1: correccions automàtiques de les pistes."""

    CASES = {
        'Que no parla o que es poc comunicatiu': 'Que no parla o que és poc comunicatiu',
        'Que es fa servir': 'Que es fa servir',
        'Que es pot menjar': 'Que es pot menjar',
        'Repartir en parts mes petites': 'Repartir en parts més petites',
        'Quart mes de l’any': 'Quart mes de l’any',
        'Mes del calendari hebreu': 'Mes del calendari hebreu',
        'Vareta amb la que marca el ritme': 'Vareta amb la qual marca el ritme',
        'Búnquer en el que hi ha armes': 'Búnquer en el qual hi ha armes',
        'Llocs en els que es viu': 'Llocs en els quals es viu',
        'Arribar al lloc a on li convé': 'Arribar al lloc on li convé',
        'Cap a on va': 'Cap a on va',
        'Que no li agrada el tracte': 'A qui no agrada el tracte',
        'Persona que li agrada menjar': 'Persona a qui agrada menjar',
        'Fer el necessari per què no succeeixi': 'Fer el necessari perquè no succeeixi',
        'Per què ho fa': 'Per què ho fa',
        'Motiu, el perquè': 'Motiu, el perquè',
        'Ell dóna': 'Ell dona',
        'Sóc així': 'Soc així',
    }

    def test_cases(self):
        verbs = {'fa', 'pot', 'parla', 'viu', 'marca', 'va'}
        for src, want in self.CASES.items():
            self.assertEqual(C.fix_orthography(src, verbs), want, src)

    def test_es_needs_verb_list(self):
        self.assertEqual(C.fix_orthography('Que es poc'), 'Que es poc')


class LexiconRulesTest(unittest.TestCase):
    """m3 i m5."""

    def test_proper_capped_freq(self):
        freq = {'figueres': 1994, 'figuera': 629, 'terrassa': 4751, 'terrasses': 548,
                'casa': 50000, 'cases': 9000, 'sol': 300}
        self.assertEqual(L.proper_capped_freq('figueres', 'figuera', freq,
                                              {'figuera', 'figueres'}), 629)
        self.assertEqual(L.proper_capped_freq('terrassa', 'terrassa', freq,
                                              {'terrassa', 'terrasses'}), 1096)
        self.assertEqual(L.proper_capped_freq('casa', 'casa', freq, {'casa', 'cases'}), 18000)
        self.assertEqual(L.proper_capped_freq('sol', 'sol', freq, {'sol'}), 300)

    def test_capped_freq_only_changes_rank(self):
        a = L.Candidate('AAA', 'aaa', 'aaa', 'lemma', 'N', 100, 10)
        b = L.Candidate('BBB', 'bbb', 'bbb', 'lemma', 'N', 50)
        ranked, _ = L.rank_candidates([a, b])
        self.assertEqual([c.form for c, _, _ in ranked], ['bbb', 'aaa'])
        self.assertEqual(ranked[1][0].freq, 100)

    def test_english_sources_rejected(self):
        fp = L.ForeignPolicy({'cool': {'English'}, 'càmper': {'anglès'}, 'casa': set()},
                             {'càmper': 'allow'})
        self.assertEqual(fp.rejected('cool'), 'anglicisme_no_normatiu')
        self.assertIsNone(fp.rejected('càmper'))
        self.assertIsNone(fp.rejected('casa'))


# Formes de la iteració 2 que no poden ser mai solució (també a
# test/data/forbidden_solutions.txt) i formes comunes que s'han de recuperar.
B1_FORBIDDEN = ('emmerdar', 'recollons', 'bagasser', 'onanisme', 'onanista', 'coital',
                'zoofília', 'incestuós', 'libidinós', 'copulatiu', 'cànnabis', 'esnifar',
                'libido', 'lasciva', 'lascives', 'luxúria', 'concubina', 'hitlerià',
                'genocida', 'genocides', 'diarreic', 'agitanat', 'agitanada')
M2_RECOVERED = ('pilota', 'pilot', 'pilotar', 'mamà', 'conca', 'tara', 'fava', 'figa',
                'pebrot', 'cigala')


@unittest.skipUnless((LEX / 'clues.tsv').exists(), 'assets/lexicon/ no generat')
class RealIter2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, rows = tsv.read_tsv(LEX / 'solutions.tsv')
        cls.sol = {r[1]: r for r in rows}
        _, rows = tsv.read_tsv(LEX / 'clues.tsv')
        cls.clues = {r[1]: r[3] for r in rows}
        cls.accepted = set()
        for line in (LEX / 'accepted.tsv').read_text(encoding='utf-8').splitlines():
            key, _, sp = line.partition('\t')
            cls.accepted.update(sp.split('|') if sp else [N.trivial_spelling(key)])

    def test_b1_not_solutions(self):
        self.assertEqual(sorted(set(B1_FORBIDDEN) & set(self.sol)), [])

    def test_m2_recovered(self):
        self.assertEqual(sorted(set(M2_RECOVERED) - set(self.sol)), [])
        self.assertNotIn('hòstia', self.sol)

    def test_b2_homograph_clues(self):
        for form, bad in (('mansa', 'Extremitats'), ('manses', 'Extremitats'),
                          ('corsa', 'Òrgans'), ('corses', 'Òrgans'), ('corsos', 'Òrgans'),
                          ('patrona', 'Model'), ('patrones', 'Model')):
            self.assertNotIn(bad, self.clues.get(form, ''), form)

    def test_no_duplicated_labels(self):
        bad = [f for f, c in self.clues.items() if re.match(r'^\([^)]*\) \(', c)]
        self.assertEqual(bad, [])

    def test_orthography_patterns(self):
        pats = [re.compile(p) for p in (
            r'\b(amb|en|per|sobre|sota|contra|sense) (la|el|les|els) que\b',
            r'(?<![Cc]ap )\ba on\b', r'\b[Qq]ue (no )?li agrad', r'\b[Mm]es (?!de\b|del\b|d’)\w',
            r'\b(dóna|dónes|sóc|véns|vénen|fóra|féu)\b', r'\bque es poc\b',
            r'(?<!^)(?<!\bel )\bper (què|que)\b')]
        bad = [(f, c) for f, c in self.clues.items() if any(p.search(c) for p in pats)]
        self.assertEqual(bad, [])

    def test_m3_toponyms_not_band_1(self):
        for form in ('figueres', 'reus', 'terrassa'):
            if form in self.sol:
                self.assertGreater(int(self.sol[form][7]), 1, form)

    def test_m5_english_not_accepted(self):
        for w in ('cool', 'supercool', 'crooner', 'online', 'email'):
            self.assertNotIn(w, self.accepted, w)
        self.assertIn('càmper', self.accepted)


if __name__ == '__main__':
    unittest.main()
