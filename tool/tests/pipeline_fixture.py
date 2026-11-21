"""Executa el pipeline sobre les fixtures en un directori temporal (compartit pels tests)."""
import contextlib
import io
import tempfile
from functools import lru_cache
from pathlib import Path

import build_blacklist
import build_lexicon
from tests.helpers import DICT_TOOLS, MINI_DUMP

_TMP = tempfile.TemporaryDirectory()
OUT = Path(_TMP.name)
MANUAL_LINES = ['gat\tallow\tprova: cap marca automàtica']
# Fitxers manuals de les fixtures (els de tool/data/ són per al lèxic real).
DATA_FILES = {
    'roots': 'pattern\tlevel\treason\texcept\n',
    'foreign': 'lemma\taction\treason\n',
    'proper': 'form\taction\treason\n',
    'overrides': 'form\taction\tvalue\treason\n',
    'solution_exclusions': 'lemma\taction\treason\n',
}


def data_file(name: str) -> str:
    path = OUT / f'{name}.tsv'
    if not path.exists():
        path.write_text(DATA_FILES[name], encoding='utf-8')
    return str(path)


@lru_cache(maxsize=None)
def built(stage: str = 'lexicon') -> Path:
    manual = OUT / 'manual.tsv'
    manual.write_text('form\tlevel\treason\n' + ''.join(ln + '\n' for ln in MANUAL_LINES),
                      encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()):
        build_blacklist.main(['--dict-tools', str(DICT_TOOLS), '--dump', str(MINI_DUMP),
                              '--manual', str(manual), '--roots', data_file('roots'),
                              '--out-dir', str(OUT)])
        if stage in ('lexicon', 'clues', 'manifest'):
            build_lexicon.main(['--dict-tools', str(DICT_TOOLS), '--out-dir', str(OUT),
                                '--foreign', data_file('foreign'),
                                '--proper', data_file('proper'),
                                '--solution-exclusions', data_file('solution_exclusions')])
        if stage in ('clues', 'manifest'):
            import build_clues
            build_clues.main(['--dict-tools', str(DICT_TOOLS), '--dump', str(MINI_DUMP),
                              '--out-dir', str(OUT), '--overrides', data_file('overrides'),
                              '--authored', str(OUT / 'clues_authored'),
                              '--seasons', str(OUT / 'seasons_data'),
                              '--themes', str(OUT / 'themes_data')])
        if stage == 'manifest':
            import build_manifest
            build_manifest.main(['--dict-tools', str(DICT_TOOLS), '--out-dir', str(OUT),
                                 '--assets-dir', str(OUT / 'assets')])
    return OUT


def accepted() -> dict[str, list[str] | None]:
    out = {}
    for line in (built() / 'accepted.tsv').read_text(encoding='utf-8').splitlines():
        key, _, sp = line.partition('\t')
        out[key] = sp.split('|') if sp else None
    return out


def solutions() -> dict[str, dict[str, str]]:
    lines = (built() / 'solutions.tsv').read_text(encoding='utf-8').splitlines()
    header = lines[0].split('\t')
    return {r[1]: dict(zip(header, r)) for r in (ln.split('\t') for ln in lines[1:])}
