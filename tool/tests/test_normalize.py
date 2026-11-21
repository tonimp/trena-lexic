import json
import unicodedata
import unittest
from pathlib import Path

from lexlib import normalize as N

REPO = Path(__file__).resolve().parents[2]
VECTORS = REPO / 'test' / 'data' / 'normalization_vectors.json'


class VectorsTest(unittest.TestCase):
    def setUp(self):
        self.vectors = json.loads(VECTORS.read_text(encoding='utf-8'))

    def test_minimum_cases(self):
        self.assertGreaterEqual(len(self.vectors), 40)

    def test_vectors(self):
        for v in self.vectors:
            with self.subTest(input=v['input'], note=v['note']):
                self.assertEqual(N.canonicalize(v['input']), v['canonical'])
                self.assertEqual(N.tokenize(v['input']), v['tokens'])
                self.assertEqual(N.grid_key(v['input']), v['key'])
                key = N.grid_key(v['input'])
                self.assertEqual(None if key is None else len(key), v['length'])

    def test_idempotent(self):
        for v in self.vectors:
            c = N.canonicalize(v['input'])
            if c is None:
                continue
            with self.subTest(input=v['input']):
                self.assertEqual(N.canonicalize(c), c)
                self.assertEqual(N.grid_key(c), N.grid_key(v['input']))

    def test_matches_nfc_for_valid(self):
        # La composició restringida equival a NFC per a les entrades vàlides.
        for v in self.vectors:
            c = N.canonicalize(v['input'])
            if c is None:
                continue
            with self.subTest(input=v['input']):
                self.assertEqual(c, unicodedata.normalize('NFC', c))


class HelpersTest(unittest.TestCase):
    def test_token_label(self):
        self.assertEqual(N.token_label('Ŀ'), 'L·L')
        self.assertEqual(N.token_label('A'), 'A')
        self.assertEqual(N.key_tokens('COĿEGI'), ['C', 'O', 'L·L', 'E', 'G', 'I'])

    def test_trivial_spelling(self):
        self.assertEqual(N.trivial_spelling('COĿEGI'), 'col·legi')
        self.assertEqual(N.trivial_spelling('CAÇA'), 'caça')

    def test_keys_distinct(self):
        self.assertNotEqual(N.grid_key('caça'), N.grid_key('casa'))
        self.assertNotEqual(N.grid_key('caça'), N.grid_key('caca'))


if __name__ == '__main__':
    unittest.main()
