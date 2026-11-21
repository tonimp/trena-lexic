import tempfile
import unittest
from pathlib import Path

import build_blacklist as B
from lexlib import config
from lexlib import softcatala as SC
from lexlib import wiktionary as W
from tests.helpers import DICT_TOOLS, MINI_DUMP

P = SC.DictToolsPaths(DICT_TOOLS)


def manual_file(tmp: str, lines: list[str]) -> Path:
    p = Path(tmp) / 'manual.tsv'
    p.write_text('form\tlevel\treason\n' + ''.join(ln + '\n' for ln in lines), encoding='utf-8')
    return p


def build(lines: list[str]) -> dict[str, tuple[str, str, str]]:
    with tempfile.TemporaryDirectory() as tmp:
        rows = B.build(P, MINI_DUMP, manual_file(tmp, lines))
    return {r[1]: (r[0], r[2], r[3]) for r in rows}


class AutoMarksTest(unittest.TestCase):
    def test_offensive_mark(self):
        self.assertEqual(B.offensive_mark(['mallorquí', 'vulgar']), 'vulgar')
        self.assertEqual(B.offensive_mark(['sovint despectiu']), 'despectiu')
        self.assertIsNone(B.offensive_mark(['vulgarment', 'figurat']))

    def test_first_and_later_senses(self):
        auto = B.auto_entries(W.iter_pages(MINI_DUMP))
        self.assertEqual(auto['malparit'], B.Veto('absolute', 'viquidiccionari:vulgar'))
        self.assertEqual(auto['puta'].level, 'absolute')
        self.assertEqual(auto['poma'].level, 'sensitive')
        self.assertEqual(auto['bossa'].level, 'sensitive')
        self.assertNotIn('casa', auto)


class BuildTest(unittest.TestCase):
    def test_levels_and_propagation(self):
        bl = build([])
        self.assertEqual(bl['malparit'][1], 'absolute')
        self.assertEqual(bl['malparida'][1], 'absolute')  # forma del lema malparit
        self.assertNotIn('malparir', bl)  # homògraf verbal: no es veta el lema malparir
        self.assertEqual(bl['malparida'][1], 'absolute')  # participi homògraf no rebaixa
        self.assertEqual(bl['putes'][1], 'absolute')
        self.assertIn('[de «puta»]', bl['putes'][2])
        self.assertEqual(bl['bossa'][1], 'sensitive')
        self.assertEqual(bl['bosses'][1], 'sensitive')
        self.assertEqual(bl['poma'][0], 'POMA')

    def test_allow_removes_sensitive(self):
        bl = build(['poma\tallow\tsentit principal neutre'])
        self.assertNotIn('poma', bl)
        self.assertNotIn('pomes', bl)

    def test_allow_cannot_remove_absolute(self):
        with self.assertRaises(B.BlacklistError) as cm:
            build(['malparit\tallow\tprova'])
        self.assertIn('malparit', str(cm.exception))

    def test_reason_required(self):
        with self.assertRaises(B.BlacklistError) as cm:
            build(['gat\tsensitive\t'])
        self.assertIn('gat', str(cm.exception))

    def test_unknown_level(self):
        with self.assertRaises(B.BlacklistError):
            build(['gat\tmolt\tprova'])

    def test_manual_overrides_auto(self):
        bl = build(['puta\tsensitive\tprova de rebaixa manual', 'gat\tabsolute\tprova'])
        self.assertEqual(bl['puta'][1], 'sensitive')
        self.assertEqual(bl['gats'][1], 'absolute')
        self.assertEqual(bl['gates'][1], 'absolute')

    def test_manual_form_must_exist(self):
        with self.assertRaises(B.BlacklistError) as cm:
            build(['inexistentíssim\tabsolute\tprova'])
        self.assertIn('inexistentíssim', str(cm.exception))

    def test_innocent_homograph_downgraded(self):
        lt = [SC.LtEntry('foto', 'foto', 'NCFS000'), SC.LtEntry('foto', 'fotre', 'VMIP1S0C'),
              SC.LtEntry('fotre', 'fotre', 'VMN0000'), SC.LtEntry('fots', 'fotre', 'VMIP2S00')]
        lemmas_of, forms_of = B.propagation_targets(lt)
        out = B.propagate({'fotre': B.Veto('absolute', 'x')}, lemmas_of, forms_of)
        self.assertEqual(out['fots'][0].level, 'absolute')
        self.assertEqual(out['foto'][0].level, 'sensitive')

    def test_output_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rc = B.main(['--dict-tools', str(DICT_TOOLS), '--dump', str(MINI_DUMP),
                         '--manual', str(manual_file(tmp, [])), '--out-dir', str(out)])
            self.assertEqual(rc, 0)
            text = (out / 'blacklist.tsv').read_text(encoding='utf-8')
            rows = B.read_blacklist(out / 'blacklist.tsv')
        self.assertTrue(text.startswith('key\tform\tlevel\treason\n'))
        keys = [(r['key'], r['form']) for r in rows]
        self.assertEqual(keys, sorted(keys))


class RealManualListTest(unittest.TestCase):
    """La llista manual real: format vàlid i formes presents al diccionari LT."""

    def test_manual_format(self):
        manual = B.load_manual(config.DATA_DIR / 'blacklist_manual.tsv')
        self.assertGreater(len(manual), 100)

    def test_manual_forms_in_lt(self):
        try:
            dt = config.default_dict_tools()
        except Exception:  # pragma: no cover
            self.skipTest('sense fitxer de bloqueig')
        if not dt.lt_dictionary.exists():
            self.skipTest('fonts no descarregades (tool/fetch_sources.py)')
        forms = {e.form for e in SC.iter_lt(dt.lt_dictionary)}
        manual = B.load_manual(config.DATA_DIR / 'blacklist_manual.tsv')
        self.assertEqual(sorted(f for f in manual if f not in forms), [])


if __name__ == '__main__':
    unittest.main()
