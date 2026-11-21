"""Lectura i validació del fitxer de bloqueig de fonts (tool/sources.lock.json)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = TOOL_DIR.parent
DEFAULT_LOCK = TOOL_DIR / 'sources.lock.json'
DEFAULT_CACHE = TOOL_DIR / '.cache'

_SHA1 = re.compile(r'^[0-9a-f]{40}$')
_SHA256 = re.compile(r'^[0-9a-f]{64}$')
_DATE = re.compile(r'^\d{8}$')


class LockError(ValueError):
    pass


class HashMismatch(RuntimeError):
    pass


@dataclass(frozen=True)
class SoftcatalaLock:
    url: str
    commit: str
    commit_date: str
    path: str


@dataclass(frozen=True)
class WiktionaryLock:
    dump_date: str
    url: str
    sha256: str
    size: int
    path: str


@dataclass(frozen=True)
class Lock:
    softcatala: SoftcatalaLock
    wiktionary: WiktionaryLock

    def softcatala_dir(self, cache: Path) -> Path:
        return cache / self.softcatala.path

    def dump_path(self, cache: Path) -> Path:
        return cache / self.wiktionary.path


def dump_url(date: str) -> str:
    return (f'https://dumps.wikimedia.org/cawiktionary/{date}/'
            f'cawiktionary-{date}-pages-articles.xml.bz2')


def dump_relpath(date: str) -> str:
    return f'viquidiccionari/cawiktionary-{date}-pages-articles.xml.bz2'


def parse_lock(data: dict) -> Lock:
    try:
        s = data['softcatala']
        w = data['viquidiccionari']
        sc = SoftcatalaLock(s['url'], s['commit'], s['commit_date'], s['path'])
        wk = WiktionaryLock(w['dump_date'], w['url'], w['sha256'], int(w['size']), w['path'])
    except (KeyError, TypeError) as e:
        raise LockError(f'fitxer de bloqueig incomplet: falta {e}') from e
    if not _SHA1.match(sc.commit):
        raise LockError(f'commit de Softcatalà no fixat (cal un SHA complet): {sc.commit!r}')
    if not _DATE.match(wk.dump_date):
        raise LockError(f'data de bolcat no vàlida: {wk.dump_date!r}')
    if 'latest' in wk.url or wk.url != dump_url(wk.dump_date):
        raise LockError(f'URL del bolcat no fixada a la data {wk.dump_date}: {wk.url}')
    if not _SHA256.match(wk.sha256):
        raise LockError(f'SHA-256 del bolcat no vàlid: {wk.sha256!r}')
    for p in (sc.path, wk.path):
        if p.startswith('/') or '..' in Path(p).parts:
            raise LockError(f'camí de memòria cau no relatiu: {p}')
    return Lock(sc, wk)


def load_lock(path: Path = DEFAULT_LOCK) -> Lock:
    return parse_lock(json.loads(path.read_text(encoding='utf-8')))


def lock_to_dict(lock: Lock) -> dict:
    s, w = lock.softcatala, lock.wiktionary
    return {
        'softcatala': {'url': s.url, 'commit': s.commit, 'commit_date': s.commit_date,
                       'path': s.path},
        'viquidiccionari': {'dump_date': w.dump_date, 'url': w.url, 'sha256': w.sha256,
                            'size': w.size, 'path': w.path},
    }


def write_lock(lock: Lock, path: Path = DEFAULT_LOCK) -> None:
    path.write_text(json.dumps(lock_to_dict(lock), indent=2, ensure_ascii=False) + '\n',
                    encoding='utf-8')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise HashMismatch(f'SHA-256 de {path} no coincideix amb el fitxer de bloqueig: '
                           f'esperat {expected}, obtingut {actual}')
