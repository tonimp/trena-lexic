"""Regressions sobre el lèxic real (assets/lexicon/ i tool/data/); s'ometen si no hi és."""
import re
import unittest

import build_blacklist as B
import build_clues as C
import build_lexicon as L
from lexlib import config, tsv
from lexlib import normalize as N

LEX = config.LEXICON_DIR
FORBIDDEN = config.REPO_DIR / 'test' / 'data' / 'forbidden_solutions.txt'


def forbidden_forms() -> list[str]:
    return [ln.strip() for ln in FORBIDDEN.read_text(encoding='utf-8').splitlines()
            if ln.strip() and not ln.startswith('#')]


def accepted_spellings() -> dict[str, list[str]]:
    out = {}
    for line in (LEX / 'accepted.tsv').read_text(encoding='utf-8').splitlines():
        key, _, sp = line.partition('\t')
        out[key] = sp.split('|') if sp else [N.trivial_spelling(key)]
    return out


@unittest.skipUnless((LEX / 'solutions.tsv').exists(), 'assets/lexicon/ no generat')
class RealLexiconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, rows = tsv.read_tsv(LEX / 'solutions.tsv')
        cls.solutions = {r[1] for r in rows}
        cls.solution_lemmas = {r[1]: r[2] for r in rows}
        _, rows = tsv.read_tsv(LEX / 'clues.tsv')
        cls.clues = {r[1]: r[3] for r in rows}
        cls.accepted = accepted_spellings()

    def test_forbidden_never_solution(self):
        forms = forbidden_forms()
        self.assertGreater(len(forms), 80)
        for f in forms:
            self.assertEqual(N.canonicalize(f), f, f)
        self.assertEqual(sorted(set(forms) & self.solutions), [])

    def test_solution_exclusions(self):
        # retirar-solucions-dubtoses: intent vàlid, mai solució, i rànquing de la resta intacte.
        excluded = L.load_actions(config.DATA_DIR / 'solution_exclusions.tsv',
                                  L.SOLUTION_EXCLUSION_HEADER, L.SOLUTION_EXCLUSION_ACTIONS)
        self.assertEqual(len(excluded), 11)
        for lemma in excluded:
            self.assertIn(lemma, self.accepted.get(N.grid_key(lemma), []), lemma)
            self.assertNotIn(lemma, self.solutions, lemma)
            self.assertNotIn(lemma, set(self.solution_lemmas.values()), lemma)
        _, rows = tsv.read_tsv(LEX / 'solutions.tsv')
        ranks = [int(r[6]) for r in rows]
        self.assertEqual(ranks, sorted(set(ranks)), 'rangs repetits o desordenats')

    def test_rejected_foreign_not_accepted(self):
        manual = L.load_actions(config.DATA_DIR / 'foreign_words.tsv', L.FOREIGN_HEADER,
                                L.FOREIGN_ACTIONS)
        for lemma in ('lady', 'miss', 'staff', 'whatsapp', 'pokémon', 'bushel', 'kleenex'):
            self.assertNotIn(lemma, self.accepted.get(N.grid_key(lemma), []), lemma)
        for lemma, action in manual.items():
            if action == 'reject':
                self.assertNotIn(lemma, self.accepted.get(N.grid_key(lemma), []), lemma)
            if action in ('accept', 'no_solution', 'reject'):
                self.assertNotIn(lemma, set(self.solution_lemmas.values()), lemma)

    def test_no_solution_has_foreign_spelling(self):
        manual = L.load_actions(config.DATA_DIR / 'foreign_words.tsv', L.FOREIGN_HEADER,
                                L.FOREIGN_ACTIONS)
        allowed = {lm for lm, a in manual.items() if a == 'allow'}
        bad = sorted(f for f, lm in self.solution_lemmas.items()
                     if L.foreign_pattern(f) and lm not in allowed)
        self.assertEqual(bad, [])

    def test_clues_typographic_and_no_reveal(self):
        _, rows = tsv.read_tsv(LEX / 'clues.tsv')
        for key, form, lemma, clue, _ in rows:
            self.assertNotIn("'", clue, form)
            self.assertIsNone(C.reveals(clue.removeprefix('(femení plural) ')
                                        .removeprefix('(femení) ').removeprefix('(plural) '),
                                        form, lemma, set(), strict=False), form)

    def test_qa_clue_fixes(self):
        self.assertNotIn('il·legal', self.clues)
        self.assertNotIn('il·lògic', self.clues)
        self.assertNotIn('renebot', self.clues)
        self.assertNotIn('Ruta marítima', self.clues.get('carreres', ''))
        self.assertIn('per part de', self.clues['arrestar'])
        self.assertIn('fins a la', self.clues['infància'])
        wrong = re.compile(r'\b(per par|dels seu|de d’|fins la|fins el|fins les|fins els)\b')
        for form, clue in self.clues.items():
            self.assertIsNone(wrong.search(clue), f'{form}: {clue}')

    def test_data_files_parse(self):
        rules = B.load_roots(config.DATA_DIR / 'blacklist_roots.tsv')
        self.assertGreater(len(rules), 30)
        L.load_actions(config.DATA_DIR / 'proper_nouns.tsv', L.PROPER_HEADER, L.PROPER_ACTIONS)
        overrides = C.load_overrides(config.DATA_DIR / 'clue_overrides.tsv')
        for form in overrides:
            self.assertEqual(N.canonicalize(form), form, form)

    def test_common_homographs_kept(self):
        for f in ('rosa', 'mar', 'pau', 'sol', 'nit', 'nord', 'casa'):
            self.assertIn(f, self.solutions, f)


if __name__ == '__main__':
    unittest.main()
