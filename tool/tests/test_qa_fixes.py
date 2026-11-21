"""Tests de les correccions de l'informe de QA de pipeline-lexic (D1–D5) sobre fixtures."""
import collections
import tempfile
import unittest
from pathlib import Path

import build_blacklist as B
import build_clues as C
import build_lexicon as L
from lexlib import softcatala as SC
from lexlib import wiktionary as W
from tests.helpers import DICT_TOOLS, MINI_DUMP

P = SC.DictToolsPaths(DICT_TOOLS)


def write(tmp: str, name: str, text: str) -> Path:
    path = Path(tmp) / name
    path.write_text(text, encoding='utf-8')
    return path


class RootVetoTest(unittest.TestCase):
    """D1: veto per família derivativa."""

    def rules(self, lines: list[str]) -> list[B.RootRule]:
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, 'roots.tsv', 'pattern\tlevel\treason\texcept\n'
                         + ''.join(ln + '\n' for ln in lines))
            return B.load_roots(path)

    def test_prefix_family_and_exceptions(self):
        rules = self.rules(['# comentari', 'merd\tabsolute\tescatològic\t',
                            'put(a|eria|ot)$\tabsolute\tmalsonant\t',
                            'pix(?!el)\tsensitive\tescatològic lleu\tpixota'])
        lemmas = ['merda', 'merder', 'merdós', 'puta', 'puteria', 'putrefacció', 'putatiu',
                  'pixar', 'pixum', 'pixota', 'pixelar', 'casa']
        got = {lm: v.level for lm, v in B.root_entries(rules, lemmas).items()}
        self.assertEqual(got, {'merda': 'absolute', 'merder': 'absolute',
                               'merdós': 'absolute', 'puta': 'absolute',
                               'puteria': 'absolute', 'pixar': 'sensitive',
                               'pixum': 'sensitive'})

    def test_most_severe_rule_wins(self):
        rules = self.rules(['cabr\tsensitive\tfamília\t', 'cabronada$\tabsolute\tinsult\t'])
        got = B.root_entries(rules, ['cabronada', 'cabrejar'])
        self.assertEqual(got['cabronada'].level, 'absolute')
        self.assertEqual(got['cabrejar'].level, 'sensitive')

    def test_invalid_rules(self):
        for line in ('merd\tdolent\tmotiu\t', 'merd\tabsolute\t\t', '(\tabsolute\tmotiu\t',
                     'merd\tabsolute'):
            with self.assertRaises(B.BlacklistError, msg=line):
                self.rules([line])

    def test_build_propagates_root_veto_to_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            manual = write(tmp, 'manual.tsv', 'form\tlevel\treason\n')
            roots = write(tmp, 'roots.tsv', 'pattern\tlevel\treason\texcept\n'
                          'col·leg\tsensitive\tprova de família\t\n')
            rows = {r[1]: r for r in B.build(P, MINI_DUMP, manual, roots)}
        self.assertEqual(rows['col·legi'][2], 'sensitive')
        self.assertEqual(rows['col·legis'][2], 'sensitive')
        self.assertIn('arrel /col·leg/', rows['col·legis'][3])

    def test_manual_overrides_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            manual = write(tmp, 'manual.tsv', 'form\tlevel\treason\n'
                           'col·legi\tabsolute\tprova manual\n')
            roots = write(tmp, 'roots.tsv', 'pattern\tlevel\treason\texcept\n'
                          'col·leg\tsensitive\tprova\t\n')
            rows = {r[1]: r for r in B.build(P, MINI_DUMP, manual, roots)}
        self.assertEqual(rows['col·legi'][2], 'absolute')

    def test_offensive_sources(self):
        got = B.source_entries({'malparit': {'LT', 'vulgar'}, 'casa': {'LT'},
                                'beneit': {'pejoratiu'}})
        self.assertEqual(sorted(got), ['beneit', 'malparit'])
        self.assertTrue(all(v.level == 'sensitive' for v in got.values()))


class ForeignTest(unittest.TestCase):
    """D2: estrangerismes no adaptats i marques."""

    def test_pattern(self):
        flagged = ['lady', 'miss', 'staff', 'whatsapp', 'kleenex', 'walkman', 'jacuzzi',
                   'light', 'look', 'office', 'feeling', 'bloom', 'pack', 'hashtag', 'wifi',
                   'bushel', 'ring', 'sexy', 'hertz', 'thriller', 'cheddar']
        for w in flagged:
            self.assertIsNotNone(L.foreign_pattern(w), w)
        catalan = ['any', 'lluny', 'company', 'canyella', 'deshonra', 'càmping', 'míting',
                   'idees', 'àrees', 'reeixir', 'cooperar', 'zoo', 'subbase', 'qüestió',
                   'quilòmetre', 'casa', 'col·legi', 'exhaurir', 'pàrquing']
        for w in catalan:
            self.assertIsNone(L.foreign_pattern(w), w)

    def test_policy(self):
        pol = L.ForeignPolicy(
            {'fanta': {'marca'}, 'hipster': {'esadir'}, 'comandant': {'esadir'},
             'whisky': {'LT'}, 'casa': {'LT'}},
            {'comandant': 'allow', 'whisky': 'accept', 'tothom': 'allow', 'hipster': 'reject'})
        self.assertEqual(pol.rejected('fanta'), 'marca_comercial')
        self.assertEqual(pol.rejected('lady'), 'grafia_no_catalana')
        self.assertEqual(pol.rejected('hipster'), 'estranger_manual')
        self.assertIsNone(pol.rejected('whisky'))
        self.assertIsNone(pol.rejected('tothom'))
        self.assertIsNone(pol.rejected('casa'))
        self.assertTrue(pol.no_solution('whisky', 'whisky'))
        self.assertFalse(pol.no_solution('comandant', 'comandant'))
        self.assertFalse(pol.no_solution('tothom', 'tothom'))
        self.assertFalse(pol.no_solution('casa', 'casa'))

    def test_drop_rejected_keeps_innocent_homographs(self):
        pol = L.ForeignPolicy({}, {'miss': 'reject'})
        norm = {'miss': {('miss', 'NCFS000')}, 'pack': {('pack', 'NCMS000')},
                'casa': {('casa', 'NCFS000')}, 'dual': {('dual', 'AQ0CS0'),
                                                         ('lady', 'NCFS000')}}
        rej = collections.Counter()
        out = L.drop_rejected_lemmas(norm, pol, rej)
        self.assertEqual(sorted(out), ['casa', 'dual'])
        self.assertEqual(out['dual'], {('dual', 'AQ0CS0')})
        self.assertEqual(rej['estranger_manual'], 1)
        self.assertEqual(rej['grafia_no_catalana'], 2)

    def test_actions_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = write(tmp, 'f.tsv', 'lemma\taction\treason\n# comentari\n'
                       'lady\treject\tno és al DIEC2\n')
            self.assertEqual(L.load_actions(ok, L.FOREIGN_HEADER, L.FOREIGN_ACTIONS),
                             {'lady': 'reject'})
            for body in ('lady\tesborrar\tmotiu\n', 'lady\treject\t\n', 'Lady\treject\tm\n',
                         'lady\treject\tm\nlady\tallow\tm\n'):
                bad = write(tmp, 'b.tsv', 'lemma\taction\treason\n' + body)
                with self.assertRaises(L.BuildError, msg=body):
                    L.load_actions(bad, L.FOREIGN_HEADER, L.FOREIGN_ACTIONS)
        self.assertEqual(L.load_actions(None, L.FOREIGN_HEADER, L.FOREIGN_ACTIONS), {})


class ProperNounTest(unittest.TestCase):
    """D4: homògrafs de noms propis."""

    def test_proper_forms(self):
        entries = [SC.LtEntry('Henry', 'Henry', 'NPMSSP0'), SC.LtEntry('Andes', 'Andes',
                                                                         'NPCPG00'),
                   SC.LtEntry('Google', 'Google', 'NPCSO00'), SC.LtEntry('casa', 'casa',
                                                                         'NCFS000')]
        self.assertEqual(L.proper_noun_forms(entries), {'henry', 'andes'})

    def test_dominated(self):
        freq = {'henry': 3555, 'henrys': 2, 'rosa': 9000, 'roses': 4000, 'nord': 30000}
        self.assertTrue(L.proper_dominated('henry', 'henry', freq, {'henry', 'henrys'}))
        self.assertFalse(L.proper_dominated('rosa', 'rosa', freq, {'rosa', 'roses'}))
        self.assertTrue(L.proper_dominated('nord', 'nord', freq, {'nord'}))

    def test_candidates_exclusion_and_keep(self):
        norm = {'henry': {('henry', 'NCMS000')}, 'henrys': {('henry', 'NCMP000')},
                'nord': {('nord', 'NCMS000')}, 'gat': {('gat', 'NCMS000')}}
        freq = {'henry': 3555, 'henrys': 2, 'nord': 30000, 'gat': 50}
        acc = {'HENRY': ['henry'], 'HENRYS': ['henrys'], 'NORD': ['nord'], 'GAT': ['gat']}
        forms_of = {'henry': {'henry', 'henrys'}, 'nord': {'nord'}, 'gat': {'gat'}}
        ranked, rej = L.candidates(norm, {}, acc, set(), set(), freq, {}, None,
                                   {'henry', 'nord', 'gat'}, {'nord': 'keep',
                                                              'gat': 'exclude'}, forms_of)
        self.assertEqual([c.form for c, _, _ in ranked], ['nord'])
        self.assertEqual(rej['homograf_nom_propi'], 2)


class RevealQaTest(unittest.TestCase):
    """D3: l'arrel no s'amaga darrere del L·L ni d'un prefix."""

    CASES = [
        ('No legal, contrari a la llei', 'il·legal', 'legal'),
        ('Que no és lògic', 'il·lògic', 'lògic'),
        ('Que no és legítim', 'il·legítim', 'legítim'),
        ('Besnebot', 'renebot', 'Besnebot'),
        ('Tornar a emprendre', 'reprendre', 'emprendre'),
        ('Establir; tornar a restaurar', 'instaurar', 'restaurar'),
    ]

    def test_basic_rule(self):
        for clue, form, word in self.CASES:
            self.assertEqual(C.reveals(clue, form, form, set(), strict=False), word, form)

    def test_strict_rule(self):
        for clue, form, word in self.CASES + [
                ('Que no es pot llegir', 'il·legible', 'llegir'),
                ('Arranjar en un ordre', 'ordenar', 'ordre')]:
            self.assertEqual(C.reveals(clue, form, form, set()), word, form)

    def test_no_false_positive(self):
        self.assertIsNone(C.reveals('Edifici destinat a habitatge', 'casa', 'casa', set()))
        self.assertIsNone(C.reveals('Qualitat de feliç', 'capacitat', 'capacitat', set()))
        self.assertIsNone(C.reveals('Que no és permès per la llei', 'il·legal', 'il·legal',
                                    set()))

    def test_letters_and_cores(self):
        self.assertEqual(C.letters('IĿEGAL'), 'ILLEGAL')
        self.assertIn('LEGAL', C.cores('IĿEGAL'))
        self.assertIn('NEBOT', C.cores('BESNEBOT'))
        self.assertEqual(C.cores('REIS'), {'REIS'})  # el nucli ha de tenir ≥ 5 lletres


def page(title: str, body: str) -> W.WikiPage:
    return W.parse_ca_section(title, '== {{-ca-}} ==\n' + body)


class OverrideAndQualityTest(unittest.TestCase):
    """D5: correccions manuals, apòstrof tipogràfic i accepcions poc representatives."""

    LEX = {'part', 'de', 'la', 'que', 'es', 'diposita', 'al', 'fons', 'del', 'seu',
           'recipient', 'estudis', 'per', 'obtenir', 'un', 'títol', 'ruta', 'marítima',
           'boira', 'poc', 'espessa', 'cosa', 'diu', 'fer', 'riure', 'professió', 'l',
           'aigua', 'mar', 'massa', 'salada', 'sòlida', 'una'}

    def builder(self, pages, overrides=None, forms_of=None):
        # nominal_lemmas buit: cap forma no és ambigua al diccionari LT (B2, iteració 2)
        return C.ClueBuilder({p.title: p for p in pages}, forms_of or {}, set(), self.LEX,
                             overrides, nominal_lemmas={})

    def test_load_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = write(tmp, 'o.tsv', 'form\taction\tvalue\treason\n# comentari\n'
                       'carrera\treplace\tEstudis per obtenir un títol\tQA\n'
                       'esment\tsense\t3\tQA\nles\tdrop\t\tarticle\n')
            got = C.load_overrides(ok)
            self.assertEqual(got['esment'], C.Override('sense', '3'))
            self.assertEqual(got['les'].action, 'drop')
            for body in ('x\tsense\ttres\tm\n', 'x\treplace\t\tm\n', 'x\tposar\tv\tm\n',
                         'x\tdrop\t\t\n'):
                bad = write(tmp, 'b.tsv', 'form\taction\tvalue\treason\n' + body)
                with self.assertRaises(L.BuildError, msg=body):
                    C.load_overrides(bad)

    def test_replace_applies_to_inflected_forms(self):
        p = page('carrera', '=== Nom ===\n# [[ruta|Ruta]] marítima.\n')
        cb = self.builder([p], {'carrera': C.Override(
            'replace', 'Estudis per obtenir un títol de professió')})
        self.assertEqual(cb.clue_for('carrera', 'carrera', 'lemma', 'N')[0],
                         'Estudis per obtenir un títol de professió')
        self.assertEqual(cb.clue_for('carreres', 'carrera', 'plural', 'N'),
                         ('(plural) Estudis per obtenir un títol de professió', 'carrera'))

    def test_sense_and_drop(self):
        p = page('broma', '=== Nom ===\n# Boira poc espessa.\n# Cosa que es diu per fer riure.\n')
        cb = self.builder([p], {'broma': C.Override('sense', '2'),
                                'bromes': C.Override('drop', '')})
        self.assertEqual(cb.clue_for('broma', 'broma', 'lemma', 'N')[0],
                         'Cosa que es diu per fer riure')
        self.assertIsNone(cb.clue_for('bromes', 'broma', 'plural', 'N'))

    def test_invalid_override_is_reported(self):
        p = page('broma', '=== Nom ===\n# Boira poc espessa.\n')
        cb = self.builder([p], {'broma': C.Override('replace', 'Broma pesada de debò')})
        self.assertIsNone(cb.clue_for('broma', 'broma', 'lemma', 'N'))
        self.assertEqual(len(cb.override_errors), 1)

    def test_typographic_apostrophe(self):
        p = page('sediment', "=== Nom ===\n# Part sòlida d'una aigua.\n")
        cb = self.builder([p])
        clue = cb.clue_for('sediment', 'sediment', 'lemma', 'N')[0]
        self.assertEqual(clue, 'Part sòlida d’una aigua')
        self.assertNotIn("'", clue)

    def test_unrepresentative_sense_not_reused_for_inflection(self):
        # la primera accepció porta una marca temàtica: a la primera passada no es reutilitza
        # per al plural; la passada de recuperació (ampliacio-pistes D2) l'accepta perquè
        # continua sent la primera accepció de la categoria
        p = page('mar', '=== Nom ===\n# {{marca|ca|nàutica}} Massa d\'aigua salada.\n')
        cb = self.builder([p])
        self.assertIsNotNone(cb.clue_for('mar', 'mar', 'lemma', 'N'))
        self.assertEqual(cb.clue_for('mars', 'mar', 'plural', 'N'),
                         ('(plural) Massa d’aigua salada', 'mar'))
        self.assertEqual(cb.rejections['accepcio_poc_representativa_per_a_flexio'], 1)
        self.assertEqual(cb.recovered['segona_passada'], 1)

    def test_secondary_sense_never_reused_for_inflection(self):
        # una accepció que no és la primera de la categoria no es reutilitza mai
        p = page('mar', '=== Nom ===\n# {{marca|ca|balear}} Llac.\n# Massa d\'aigua salada.\n')
        cb = self.builder([p])
        self.assertIsNone(cb.clue_for('mars', 'mar', 'plural', 'N'))

    def test_lemma_only(self):
        p = page('mar', "=== Nom ===\n# Massa d'aigua salada.\n")
        cb = self.builder([p], {'mar': C.Override('lemma_only', '')})
        self.assertIsNotNone(cb.clue_for('mar', 'mar', 'lemma', 'N'))
        self.assertIsNone(cb.clue_for('mars', 'mar', 'plural', 'N'))

    def test_numbers_and_elements_not_reused(self):
        p = page('cent', '=== Nom ===\n# Xifra i nombre 100.\n')
        cb = self.builder([p])
        self.assertIsNone(cb.clue_for('cents', 'cent', 'plural', 'N'))


class HomonymIndexTest(unittest.TestCase):
    def test_index_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, 'd.txt', 'nit nit_1 NCFS000\nnits nit_1 NCFP000\n'
                         'pau pau_2 NCMS000\ncasa casa NCFS000\n')
            self.assertEqual([e.lemma for e in SC.iter_lt(path)], ['nit', 'nit', 'pau', 'casa'])


if __name__ == '__main__':
    unittest.main()
