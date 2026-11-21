#!/usr/bin/env python3
"""Descarrega i verifica les fonts lèxiques fixades a tool/sources.lock.json.

- Softcatalà catalan-dict-tools: clon superficial al commit fixat (git fetch + checkout).
- Viquidiccionari: bolcat fetxat, verificat amb SHA-256.
Si les fonts ja són a la memòria cau en la versió fixada, no es tornen a descarregar.
No s'executa cap fitxer de les fonts: només git i lectura de fitxers.

Ús:
    python3 -I tool/fetch_sources.py
    python3 -I tool/fetch_sources.py --update [--softcatala-commit SHA] [--dump-date AAAAMMDD]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lexlib import sources as S  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def ensure_softcatala(lock: S.Lock, cache: Path) -> str:
    sc = lock.softcatala
    repo = lock.softcatala_dir(cache)
    if not (repo / '.git').exists():
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, 'init', '-q')
        _git(repo, 'remote', 'add', 'origin', sc.url)
    head = _git(repo, 'rev-parse', 'HEAD') if _has_head(repo) else ''
    action = 'reutilitzat'
    if head != sc.commit:
        print(f'[fetch] Softcatalà: descarregant commit {sc.commit}…', flush=True)
        _git(repo, 'fetch', '-q', '--depth', '1', 'origin', sc.commit)
        _git(repo, '-c', 'advice.detachedHead=false', 'checkout', '-q', '--force', sc.commit)
        action = 'descarregat'
    head = _git(repo, 'rev-parse', 'HEAD')
    if head != sc.commit:
        raise SystemExit(f'ERROR: Softcatalà és a {head}, s\'esperava {sc.commit}')
    dirty = _git(repo, 'status', '--porcelain', '--untracked-files=no')
    if dirty:
        raise SystemExit(f'ERROR: la còpia de Softcatalà a {repo} té canvis locals:\n{dirty}')
    date = _git(repo, 'show', '-s', '--format=%cI', 'HEAD')
    if sc.commit_date and date != sc.commit_date:
        raise SystemExit(f'ERROR: data del commit {date} diferent de la del bloqueig '
                         f'{sc.commit_date}')
    print(f'[fetch] Softcatalà {sc.commit[:12]} ({date}): {action}')
    return date


def _has_head(repo: Path) -> bool:
    r = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', '-q', 'HEAD'],
                       capture_output=True, text=True)
    return r.returncode == 0


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + '.part')
    print(f'[fetch] descarregant {url}…', flush=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'trena-lexic-pipeline/1.0'})
    with urllib.request.urlopen(req, timeout=120) as resp, part.open('wb') as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    part.replace(dest)


def ensure_dump(lock: S.Lock, cache: Path) -> None:
    wk = lock.wiktionary
    path = lock.dump_path(cache)
    action = 'reutilitzat'
    if not path.exists():
        download(wk.url, path)
        action = 'descarregat'
    try:
        S.verify_sha256(path, wk.sha256)
    except S.HashMismatch as e:
        raise SystemExit(f'ERROR: {e}') from None
    print(f'[fetch] Viquidiccionari {wk.dump_date} (SHA-256 {wk.sha256[:12]}…): {action}')


def update_lock(lock: S.Lock, cache: Path, commit: str | None, dump_date: str | None,
                lock_path: Path) -> S.Lock:
    sc, wk = lock.softcatala, lock.wiktionary
    if commit:
        sc = replace(sc, commit=commit, commit_date='')
        tmp = S.Lock(sc, wk)
        sc = replace(sc, commit_date=ensure_softcatala(tmp, cache))
    if dump_date:
        path = cache / S.dump_relpath(dump_date)
        if not path.exists():
            download(S.dump_url(dump_date), path)
        wk = S.WiktionaryLock(dump_date, S.dump_url(dump_date), S.sha256_file(path),
                              path.stat().st_size, S.dump_relpath(dump_date))
    new = S.parse_lock(S.lock_to_dict(S.Lock(sc, wk)))
    S.write_lock(new, lock_path)
    print(f'[fetch] fitxer de bloqueig actualitzat: {lock_path}')
    return new


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--lock', type=Path, default=S.DEFAULT_LOCK)
    ap.add_argument('--cache', type=Path, default=S.DEFAULT_CACHE)
    ap.add_argument('--update', action='store_true',
                    help='reescriu el fitxer de bloqueig amb les versions indicades')
    ap.add_argument('--softcatala-commit')
    ap.add_argument('--dump-date')
    a = ap.parse_args(argv)
    try:
        lock = S.load_lock(a.lock)
    except S.LockError as e:
        raise SystemExit(f'ERROR: {e}') from None
    if a.update:
        if not (a.softcatala_commit or a.dump_date):
            raise SystemExit('ERROR: --update necessita --softcatala-commit o --dump-date')
        lock = update_lock(lock, a.cache, a.softcatala_commit, a.dump_date, a.lock)
    elif a.softcatala_commit or a.dump_date:
        raise SystemExit('ERROR: per canviar versions cal --update explícit')
    ensure_softcatala(lock, a.cache)
    ensure_dump(lock, a.cache)
    return 0


if __name__ == '__main__':
    sys.exit(main())
