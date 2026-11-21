"""Lectors dels fitxers de text de Softcatalà catalan-dict-tools.

Només llegeix fitxers; no executa cap script del repositori.
Lògica migrada de tool/explore_lexicon.py.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class DictToolsPaths:
    root: Path

    @property
    def lt_dictionary(self) -> Path:
        return self.root / 'resultats/lt/diccionari.txt'

    @property
    def hunspell_dic(self) -> Path:
        return self.root / 'resultats/hunspell/catalan.dic'

    @property
    def hunspell_aff(self) -> Path:
        return self.root / 'resultats/hunspell/catalan.aff'

    @property
    def exclusions(self) -> Path:
        return self.root / 'fdic-to-hunspell/dades/exclusions.txt'

    @property
    def arrel(self) -> Path:
        return self.root / 'diccionari-arrel'

    @property
    def freq_forms(self) -> Path:
        return self.root / 'frequencies/frequencies-dict-forms.txt'

    @property
    def lgpl(self) -> Path:
        return self.root / 'lgpl-2.1.txt'

    @property
    def license(self) -> Path:
        return self.root / 'LICENSE'


_EXCLOU = re.compile(r'^#EXCLOU (FORMA|LEMA) DE (.*)$')


def load_exclusions(path: Path, variant: str = 'catalan') -> tuple[set[str], set[str]]:
    """Formes i lemes exclosos (seccions «TOTS» i de la variant indicada)."""
    forms: set[str] = set()
    lemmas: set[str] = set()
    mode = None
    for line in path.read_text(encoding='utf-8').splitlines():
        m = _EXCLOU.match(line.strip())
        if m:
            scope = m.group(2).strip()
            mode = m.group(1) if scope in ('TOTS', 'tots', variant) else None
            continue
        if line.startswith('#') or mode is None:
            continue
        w = line.split('#', 1)[0].strip()
        if w:
            (forms if mode == 'FORMA' else lemmas).add(w)
    return forms, lemmas


def expand_hunspell(dic: Path, aff: Path) -> tuple[set[str], set[str]]:
    """Expansió d'un nivell de sufixos del Hunspell (FLAG long).

    Els prefixos només generen apostrofació (l', d') i les classes de continuació
    només clítics, de manera que no calen per a formes simples. Retorna
    (formes permeses, formes FORBIDDENWORD).
    """
    sfx: dict[str, list] = collections.defaultdict(list)
    forbidden_flag = None
    for line in aff.read_text(encoding='utf-8').splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == 'FORBIDDENWORD' and len(p) >= 2:
            forbidden_flag = p[1]
        elif p[0] == 'SFX' and len(p) >= 5:
            flag, strip, add, cond = p[1], p[2], p[3], p[4]
            add = add.split('/', 1)[0]
            strip = '' if strip == '0' else strip
            add = '' if add == '0' else add
            sfx[flag].append((strip, add, None if cond == '.' else re.compile('(?:' + cond + ')$')))
    forms: set[str] = set()
    forbidden: set[str] = set()
    for line in dic.read_text(encoding='utf-8').splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        word, _, flags = line.partition('/')
        fl = [flags[i:i + 2] for i in range(0, len(flags), 2)]
        if forbidden_flag is not None and forbidden_flag in fl:
            forbidden.add(word)
            continue
        forms.add(word)
        for f in fl:
            for strip, add, cond in sfx.get(f, ()):
                if cond is not None and not cond.search(word):
                    continue
                if strip and not word.endswith(strip):
                    continue
                forms.add(word[:len(word) - len(strip)] + add)
    return forms - forbidden, forbidden


@dataclass(frozen=True)
class LtEntry:
    form: str
    lemma: str
    tag: str


_HOMONYM_INDEX = re.compile(r'_\d+$')


def iter_lt(path: Path) -> Iterator[LtEntry]:
    """Línies `forma lema ETIQUETA` del diccionari de LanguageTool.

    Els lemes homònims porten un índex (`nit_1`, `pau_2`); es treu perquè el lema
    coincideixi amb la seva forma (si no, `nit` o `pau` no serien mai candidates).
    """
    with path.open(encoding='utf-8') as fh:
        for line in fh:
            p = line.rstrip('\n').split(' ')
            if len(p) == 3 and all(p):
                yield LtEntry(p[0], _HOMONYM_INDEX.sub('', p[1]), p[2])


GENERAL_VERB_VARIANTS = frozenset('0CXY12')  # vegeu diccionari-arrel/README.md


def is_general_tag(tag: str) -> bool:
    """Fals per a formes verbals d'una variant no general/central."""
    if tag.startswith('V') and len(tag) >= 8:
        return tag[7] in GENERAL_VERB_VARIANTS
    return True


def is_excluded_tag(tag: str) -> bool:
    """Noms propis, abreviatures, números i signes."""
    return tag.startswith(('NP', 'Y', 'Z', 'F'))


_FONTS = re.compile(r'fonts?:\s*([^;#]*)')


def lemma_sources(arrel: Path) -> dict[str, set[str]]:
    """lema -> conjunt de fonts (camp `fonts:` dels fitxers *-fdic.txt actius)."""
    out: dict[str, set[str]] = {}
    for name in ('noms-fdic.txt', 'adjectius-fdic.txt', 'verbs-fdic.txt'):
        path = arrel / name
        if not path.exists():
            continue
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line or line.startswith('#') or '=' not in line:
                continue
            head, _, rest = line.partition('=')
            lemma = head.split(' ')[0]
            m = _FONTS.search(rest)
            vals = [s.strip() for s in m.group(1).split(',')] if m else []
            out.setdefault(lemma, set()).update(v for v in vals if v)
    return out


def load_frequencies(path: Path) -> dict[str, int]:
    """Fitxer `paraula, recompte` -> diccionari."""
    freq: dict[str, int] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        w, sep, n = line.rpartition(', ')
        if sep and w and n.strip().isdigit():
            freq[w] = int(n)
    return freq
