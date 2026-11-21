#!/usr/bin/env python3
"""Genera assets/lexicon/manifest.json, assets/credits/lexic.json i assets/licenses/.

El manifest recull les fonts fixades, la llicència, els recomptes i el SHA-256 de cada
fitxer generat d'assets/lexicon/. No inclou marques de temps: és reproduïble.

Ús: python3 -I tool/build_manifest.py [--dict-tools DIR] [--out-dir DIR] [--assets-dir DIR]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lexlib import config, tsv  # noqa: E402
from lexlib import normalize as N  # noqa: E402
from lexlib import sources as S  # noqa: E402
from lexlib.softcatala import DictToolsPaths  # noqa: E402

SCHEMA_VERSION = 1
SOFTCATALA_COPYRIGHT = ['Copyright (C) 2013- Jaume Ortolà',
                        'Copyright (C) 2002-2008 Joan Moratinos']
LGPL = 'LGPL-2.1-or-later'
CC = 'CC-BY-SA-4.0'
FILES = {
    # fitxer: (llicència, empaquetat a l'app)
    'accepted.tsv': (LGPL, True),
    'clues.tsv': (CC, True),
    'solutions.tsv': (LGPL, False),
    'blacklist.tsv': (LGPL, False),
}
CC_NOTICE = """Llicència Creative Commons Reconeixement-CompartirIgual 4.0 Internacional (CC BY-SA 4.0)

Les pistes del fitxer assets/lexicon/clues.tsv són una adaptació automàtica (text netejat i
escurçat) de definicions del Viquidiccionari (https://ca.wiktionary.org/), obra dels
col·laboradors del Viquidiccionari, publicades sota aquesta llicència. L’adaptació es
distribueix sota la mateixa llicència. Les pistes amb la font «pròpia» són de redacció
original de Trena i es distribueixen també sota aquesta llicència, igual que les pistes dels
reptes de temporada i de les temàtiques{seasons}.

Resum de la llicència: https://creativecommons.org/licenses/by-sa/4.0/deed.ca
Text legal complet: https://creativecommons.org/licenses/by-sa/4.0/legalcode
(reproduït a continuació en la versió original en anglès)

"""

# Text legal original (https://creativecommons.org/licenses/by-sa/4.0/legalcode.txt).
CC_LEGALCODE = Path(__file__).resolve().parent / 'data' / 'licenses' / 'CC-BY-SA-4.0-legalcode.txt'



def cc_notice(out_dir: Path) -> str:
    """Avís de la llicència CC BY-SA amb la llista explícita de fitxers de pistes de
    temporada (un fitxer nou sense regenerar l'avís no queda cobert: el test ho detecta)."""
    files = [f'assets/lexicon/{n}' for n in season_clue_files(out_dir)]
    return CC_NOTICE.replace('{seasons}', f' ({", ".join(files)})' if files else '')


def sha256_bytes(path: Path) -> str:
    return S.sha256_file(path)


def file_entry(path: Path, license_id: str, packaged: bool) -> dict:
    data = path.read_bytes()
    return {
        'sha256': sha256_bytes(path),
        'bytes': len(data),
        'lines': data.count(b'\n'),
        'license': license_id,
        'packaged': packaged,
    }


def counts(out_dir: Path) -> dict:
    accepted_lines = (out_dir / 'accepted.tsv').read_text(encoding='utf-8').splitlines()
    forms = 0
    for line in accepted_lines:
        _, _, sp = line.partition('\t')
        forms += len(sp.split('|')) if sp else 1
    _, sol = tsv.read_tsv(out_dir / 'solutions.tsv')
    _, bl = tsv.read_tsv(out_dir / 'blacklist.tsv')
    _, cl = tsv.read_tsv(out_dir / 'clues.tsv')
    band_of = {(r[0], r[1]): r[7] for r in sol}
    extra = {}
    if (out_dir / APRES).exists():
        extra['apres'] = len(tsv.read_tsv(out_dir / APRES)[1])
    if (out_dir / DAURADES).exists():
        extra['daurades'] = len(tsv.read_tsv(out_dir / DAURADES)[1])
    return {
        'accepted_keys': len(accepted_lines),
        'accepted_forms': forms,
        'solutions': len(sol),
        'solutions_by_band': dict(sorted(collections.Counter(r[7] for r in sol).items())),
        'blacklist_forms': len(bl),
        'blacklist_by_level': dict(sorted(collections.Counter(r[2] for r in bl).items())),
        'clues': len(cl),
        'clues_by_band': dict(sorted(collections.Counter(band_of[(r[0], r[1])]
                                                         for r in cl).items())),
        **extra,
    }


APRES = 'apres.tsv'  # paraules de «Has après» (has-apres D3); no entra a l'empremta del lèxic
DAURADES = 'daurades.tsv'  # paraules daurades (paraules-daurades D1); fora de l'empremta
SEASON_CLUES_DIR = 'seasons'  # assets/lexicon/seasons/<id>-clues.tsv (temporada-nadal D5)


THEME_CLUES_DIR = 'themes'  # assets/lexicon/themes/<id>-clues.tsv (madeixes-tematiques D12)


def _clue_files(out_dir: Path, sub: str) -> list[str]:
    d = out_dir / sub
    return sorted(f'{sub}/{p.name}' for p in d.glob('*-clues.tsv')) if d.is_dir() else []


def season_clue_files(out_dir: Path) -> list[str]:
    """Pistes pròpies de context: les de temporada i les de les temàtiques."""
    return _clue_files(out_dir, SEASON_CLUES_DIR) + _clue_files(out_dir, THEME_CLUES_DIR)


def files_of(out_dir: Path) -> dict[str, tuple[str, bool]]:
    """Fitxers del manifest: els fixos i les pistes de temporada (CC BY-SA, empaquetades).
    Les pistes de temporada no entren a `lexicon_fingerprint` (no són paraules)."""
    out = dict(FILES)
    out.update({name: (CC, True) for name in season_clue_files(out_dir)})
    if (out_dir / APRES).exists():
        out[APRES] = (LGPL, True)
    if (out_dir / DAURADES).exists():
        out[DAURADES] = (LGPL, True)
    return out


# Fitxers que determinen les paraules jugables (no les pistes): l'empremta del lèxic que
# guarden els puzles (`generator.lexicon`) només en depèn (ampliacio-pistes D5).
WORD_FILES = ('accepted.tsv', 'blacklist.tsv', 'solutions.tsv')


def lexicon_fingerprint(m: dict) -> str:
    """SHA-256 del JSON canònic de la part del manifest que afecta les paraules: esquema,
    normalització, font de Softcatalà i entrades d'`accepted`, `blacklist` i `solutions`.
    No inclou `clues.tsv` ni el Viquidiccionari: canviar les pistes no invalida el banc."""
    core = {
        'schema_version': m['schema_version'],
        'normalization_version': m['normalization_version'],
        'softcatala': m['sources']['softcatala'],
        'files': {f: m['files'][f] for f in WORD_FILES},
    }
    data = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def manifest(lock: S.Lock, out_dir: Path) -> dict:
    m = _manifest(lock, out_dir)
    m['lexicon_fingerprint'] = lexicon_fingerprint(m)
    return m


def _manifest(lock: S.Lock, out_dir: Path) -> dict:
    sc, wk = lock.softcatala, lock.wiktionary
    return {
        'schema_version': SCHEMA_VERSION,
        'normalization_version': N.NORMALIZATION_VERSION,
        'sources': {
            'softcatala': {'name': 'Softcatalà catalan-dict-tools', 'url': sc.url,
                           'commit': sc.commit, 'commit_date': sc.commit_date,
                           'license': 'GPL-2.0-or-later OR LGPL-2.1-or-later',
                           'copyright': SOFTCATALA_COPYRIGHT},
            'viquidiccionari': {'name': 'Viquidiccionari (cawiktionary)', 'url': wk.url,
                                'dump_date': wk.dump_date, 'sha256': wk.sha256,
                                'license': CC},
        },
        'files': {name: file_entry(out_dir / name, lic, packaged)
                  for name, (lic, packaged) in sorted(files_of(out_dir).items())},
        'counts': counts(out_dir),
    }


AUTHORED_SOURCE = 'pròpia'  # columna `source` de les pistes de redacció pròpia


def catalan_int(n: int) -> str:
    """Enter amb el separador de milers català (punt): 1011 -> «1.011»."""
    return f'{n:,}'.replace(',', '.')


def authored_count(out_dir: Path | None) -> int:
    if out_dir is None or not (out_dir / 'clues.tsv').exists():
        return 0
    _, rows = tsv.read_tsv(out_dir / 'clues.tsv')
    return sum(1 for r in rows if r[4] == AUTHORED_SOURCE)


def season_clue_count(out_dir: Path | None, sub: str = SEASON_CLUES_DIR) -> int:
    if out_dir is None:
        return 0
    return sum(len(tsv.read_tsv(out_dir / name)[1]) for name in _clue_files(out_dir, sub))


def credits(lock: S.Lock, out_dir: Path | None = None) -> dict:
    sc, wk = lock.softcatala, lock.wiktionary
    d = wk.dump_date
    # Dates visibles en format únic dd/mm/aaaa (com a la resta de l’app).
    dump_date = f'{d[6:8]}/{d[4:6]}/{d[0:4]}'
    c = sc.commit_date[:10]
    commit_date = f'{c[8:10]}/{c[5:7]}/{c[0:4]}'
    return {
        'title': 'Dades lèxiques',
        'entries': [
            {
                'id': 'softcatala',
                'name': 'Softcatalà – catalan-dict-tools',
                'text': 'Llista de paraules, flexió i freqüències: Softcatalà – catalan-dict-tools.',
                'copyright': SOFTCATALA_COPYRIGHT,
                'license': 'LGPL-2.1 o posterior',
                'license_url': 'https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html',
                'license_file': 'assets/licenses/LGPL-2.1.txt',
                'source_url': 'https://github.com/Softcatala/catalan-dict-tools',
                'version': f'revisió {sc.commit[:7]} del {commit_date}',
                'note': 'Les dades derivades (llista de paraules acceptades, llista de paraules '
                        'poc freqüents de «Has après» i llista de paraules daurades) es '
                        'distribueixen sota la mateixa '
                        'llicència i es poden regenerar amb les eines del projecte.',
                # Fitxers LGPL empaquetats (has-apres: apres.tsv; paraules-daurades: daurades.tsv;
                # coberts pel test de crèdits).
                'assets': ['assets/lexicon/accepted.tsv', f'assets/lexicon/{APRES}',
                           f'assets/lexicon/{DAURADES}', 'assets/lexicon/manifest.json'],
            },
            {
                'id': 'viquidiccionari',
                'name': 'Viquidiccionari',
                'text': 'Definicions: Viquidiccionari, col·laboradors del Viquidiccionari.',
                'license': 'CC BY-SA 4.0',
                'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/deed.ca',
                'license_file': 'assets/licenses/CC-BY-SA-4.0.txt',
                'source_url': 'https://ca.wiktionary.org/',
                'version': f'bolcat del {dump_date}',
                'dump_date': d,
                'note': 'Les pistes són una adaptació automàtica (text netejat i escurçat) de '
                        'les definicions originals i es comparteixen sota la mateixa llicència.',
                'assets': ['assets/lexicon/clues.tsv'],
            },
            {
                'id': 'pistes-propies',
                'name': 'Pistes de redacció pròpia',
                'text': 'Pistes escrites per a Trena per a les paraules que el '
                        'Viquidiccionari no cobreix o no defineix prou bé per a un joc.',
                'license': 'CC BY-SA 4.0',
                'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/deed.ca',
                'license_file': 'assets/licenses/CC-BY-SA-4.0.txt',
                'version': f'{catalan_int(authored_count(out_dir))} pistes',
                'note': 'Són definicions breves de redacció original, escrites sense copiar cap '
                        'diccionari i revisades amb els mateixos filtres que la resta de pistes. '
                        'Inclouen també les '
                        f'{catalan_int(season_clue_count(out_dir))} pistes dels reptes de '
                        'temporada' + (
                            f' i les {catalan_int(season_clue_count(out_dir, THEME_CLUES_DIR))} '
                            'de les temàtiques' if _clue_files(out_dir, THEME_CLUES_DIR)
                            else '') + '. Es comparteixen sota la mateixa llicència que el fitxer de '
                        'pistes.',
                'assets': ['assets/lexicon/clues.tsv',
                           *(f'assets/lexicon/{n}' for n in season_clue_files(out_dir))]
                if out_dir is not None else ['assets/lexicon/clues.tsv'],
            },
        ],
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build(lock: S.Lock, dt: DictToolsPaths, out_dir: Path, assets_dir: Path) -> dict:
    lic = assets_dir / 'licenses'
    lic.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(dt.lgpl, lic / 'LGPL-2.1.txt')
    (lic / 'CC-BY-SA-4.0.txt').write_text(
        cc_notice(out_dir) + CC_LEGALCODE.read_text(encoding='utf-8'), encoding='utf-8')
    write_json(assets_dir / 'credits' / 'lexic.json', credits(lock, out_dir))
    m = manifest(lock, out_dir)
    write_json(out_dir / 'manifest.json', m)
    return m


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Genera el manifest i els crèdits')
    ap.add_argument('--lock', type=Path, default=S.DEFAULT_LOCK)
    ap.add_argument('--dict-tools', type=Path)
    ap.add_argument('--out-dir', type=Path, default=config.LEXICON_DIR)
    ap.add_argument('--assets-dir', type=Path, default=config.ASSETS_DIR)
    a = ap.parse_args(argv)
    lock = S.load_lock(a.lock)
    dt = DictToolsPaths(a.dict_tools) if a.dict_tools else config.default_dict_tools()
    m = build(lock, dt, a.out_dir, a.assets_dir)
    print(f"[manifest] {json.dumps(m['counts'], ensure_ascii=False)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
