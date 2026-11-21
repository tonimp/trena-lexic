import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import fetch_sources
from lexlib import sources as S

GOOD = {
    'softcatala': {'url': 'https://github.com/Softcatala/catalan-dict-tools.git',
                   'commit': 'b00fcd9503cf290d5b4ef44c873b65667873593a',
                   'commit_date': '2026-10-22T20:08:17+02:00', 'path': 'catalan-dict-tools'},
    'viquidiccionari': {'dump_date': '20261001', 'url': S.dump_url('20261001'),
                        'sha256': '0' * 64, 'size': 3,
                        'path': S.dump_relpath('20261001')},
}


class LockTest(unittest.TestCase):
    def test_repo_lock_is_valid(self):
        lock = S.load_lock()
        self.assertEqual(lock.softcatala.commit, 'b00fcd9503cf290d5b4ef44c873b65667873593a')
        self.assertEqual(lock.wiktionary.dump_date, '20261001')

    def test_parse_good(self):
        self.assertEqual(S.parse_lock(GOOD).wiktionary.size, 3)

    def bad(self, section, key, value):
        d = copy.deepcopy(GOOD)
        d[section][key] = value
        with self.assertRaises(S.LockError):
            S.parse_lock(d)

    def test_rejects_unpinned(self):
        self.bad('softcatala', 'commit', 'HEAD')
        self.bad('softcatala', 'commit', 'b00fcd9')
        self.bad('viquidiccionari', 'url',
                 'https://dumps.wikimedia.org/cawiktionary/latest/'
                 'cawiktionary-latest-pages-articles.xml.bz2')
        self.bad('viquidiccionari', 'dump_date', 'latest')
        self.bad('viquidiccionari', 'sha256', 'abc')
        self.bad('viquidiccionari', 'path', '../fora.bz2')

    def test_missing_field(self):
        d = copy.deepcopy(GOOD)
        del d['viquidiccionari']['sha256']
        with self.assertRaises(S.LockError):
            S.parse_lock(d)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'lock.json'
            S.write_lock(S.parse_lock(GOOD), p)
            self.assertEqual(json.loads(p.read_text()), GOOD)


class HashTest(unittest.TestCase):
    def test_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'f.bin'
            p.write_bytes(b'abc')
            good = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
            self.assertEqual(S.sha256_file(p), good)
            S.verify_sha256(p, good)
            with self.assertRaises(S.HashMismatch):
                S.verify_sha256(p, '0' * 64)

    def test_ensure_dump_rejects_altered_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            lock = S.parse_lock(GOOD)
            dump = lock.dump_path(cache)
            dump.parent.mkdir(parents=True)
            dump.write_bytes(b'abc')
            with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()):
                fetch_sources.ensure_dump(lock, cache)
            self.assertIn('SHA-256', str(cm.exception))

    def test_ensure_dump_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            d = copy.deepcopy(GOOD)
            d['viquidiccionari']['sha256'] = S.sha256_file(Path(__file__))
            lock = S.parse_lock(d)
            dump = lock.dump_path(cache)
            dump.parent.mkdir(parents=True)
            dump.write_bytes(Path(__file__).read_bytes())
            out = io.StringIO()
            with redirect_stdout(out):
                fetch_sources.ensure_dump(lock, cache)
            self.assertIn('reutilitzat', out.getvalue())

    def test_version_change_requires_update(self):
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            fetch_sources.main(['--dump-date', '20261101'])


if __name__ == '__main__':
    unittest.main()
