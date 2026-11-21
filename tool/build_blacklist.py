#!/usr/bin/env python3
"""Genera assets/lexicon/blacklist.tsv (spec lexicon-blacklist).

Combina la llista manual tool/data/blacklist_manual.tsv amb les marques d'ús del
Viquidiccionari i propaga cada veto al lema i a totes les seves formes segons el
diccionari LT de Softcatalà.

Ús: python3 -I tool/build_blacklist.py [--dict-tools DIR] [--dump FITXER] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lexlib import config, tsv  # noqa: E402
from lexlib import normalize as N  # noqa: E402
from lexlib import softcatala as SC  # noqa: E402
from lexlib import wiktionary as W  # noqa: E402

LEVELS = ('absolute', 'sensitive')
MANUAL_LEVELS = ('absolute', 'sensitive', 'allow')
OFFENSIVE_MARKS = ('vulgar', 'vulgarisme', 'despectiu', 'pejoratiu', 'ofensiu', 'sexual',
                   'sexualitat')
HEADER = ('key', 'form', 'level', 'reason')
ROOTS_HEADER = ['pattern', 'level', 'reason', 'except']
# Prefixos derivatius que no han d'amagar una arrel vetada (B1 del QA, iteració 2).
ROOT_PREFIXES = ('a', 'contra', 'des', 'em', 'en', 'es', 'mal', 're', 'sobre', 'sub')
MIN_STEM = 4
# Fonts del camp `fonts:` de Softcatalà que marquen un lema com a malsonant.
OFFENSIVE_SOURCES = frozenset({'vulgar', 'pejoratiu'})


class BlacklistError(ValueError):
    pass


@dataclass(frozen=True)
class Veto:
    level: str
    reason: str
    # False per als vetos d'una accepció secundària del Viquidiccionari: només afecten la
    # pàgina marcada i les formes del seu lema que no comparteix cap altre lema (m2 del
    # QA, iteració 2: `pilotes` no veta `pilota`, `pilot` ni `pilotar`).
    spread: bool = True


def offensive_mark(marks: Iterable[str]) -> str | None:
    """Primera marca ofensiva (també dins de «sovint despectiu», «matís pejoratiu»…)."""
    for m in marks:
        for word in m.replace(',', ' ').split():
            if word in OFFENSIVE_MARKS:
                return word
    return None


def auto_entries(pages: Iterable[W.WikiPage]) -> dict[str, Veto]:
    """Vetos automàtics: marca a la 1a accepció -> absolute; només a posteriors -> sensitive."""
    out: dict[str, Veto] = {}
    for page in pages:
        if not page.senses or N.canonicalize(page.title) != page.title:
            continue
        first = offensive_mark(page.senses[0].marks)
        if first:
            out[page.title] = Veto('absolute', f'viquidiccionari:{first}')
            continue
        later = next((m for s in page.senses[1:] if (m := offensive_mark(s.marks))), None)
        if later:
            out[page.title] = Veto('sensitive', f'viquidiccionari:{later} (accepció secundària)',
                                   spread=False)
    return out


def load_manual(path: Path) -> dict[str, Veto]:
    header, rows = tsv.read_tsv(path)
    if header != ['form', 'level', 'reason']:
        raise BlacklistError(f'{path}: capçalera inesperada {header}')
    out: dict[str, Veto] = {}
    for n, row in enumerate(rows, start=2):
        if not row or row == ['']:
            continue
        if len(row) != 3:
            raise BlacklistError(f'{path}:{n}: calen 3 columnes: {row}')
        form, level, reason = (c.strip() for c in row)
        if level not in MANUAL_LEVELS:
            raise BlacklistError(f'{path}:{n}: nivell desconegut {level!r} per a «{form}»')
        if not reason:
            raise BlacklistError(f'{path}:{n}: entrada manual sense motiu: «{form}»')
        if N.canonicalize(form) != form:
            raise BlacklistError(f'{path}:{n}: «{form}» no és una grafia canònica')
        if form in out:
            raise BlacklistError(f'{path}:{n}: «{form}» duplicada')
        out[form] = Veto(level, f'manual: {reason}')
    return out


@dataclass(frozen=True)
class RootRule:
    pattern: re.Pattern
    level: str
    reason: str
    exceptions: frozenset[str]
    substring: bool = False

    def matches(self, lemma: str) -> bool:
        """Cert si el lema pertany a la família: coincidència a l'inici del lema, a l'inici
        del lema sense un prefix derivatiu (`emmerdar`, `recollons`, `desfollar`) o, amb
        `substring` (patró escrit amb `~` al davant), en qualsevol posició."""
        if lemma in self.exceptions:
            return False
        if self.substring:
            return self.pattern.search(lemma) is not None
        if self.pattern.match(lemma):
            return True
        return any(lemma.startswith(p) and len(lemma) - len(p) >= MIN_STEM
                   and self.pattern.match(lemma[len(p):]) for p in ROOT_PREFIXES)


def load_roots(path: Path | None) -> list[RootRule]:
    """Regles de veto per arrel (família derivativa): `pattern` és una expressió regular
    ancorada al començament del lema (o del lema sense un prefix de ROOT_PREFIXES); si
    comença per `~`, es busca com a subcadena en qualsevol posició. `except` llista
    (separats per `|`) els lemes que hi coincideixen però no pertanyen a la família
    (homògrafs innocents)."""
    if path is None or not path.exists():
        return []
    header, rows = tsv.read_tsv(path)
    if header != ROOTS_HEADER:
        raise BlacklistError(f'{path}: capçalera inesperada {header}')
    out = []
    for n, row in enumerate(rows, start=2):
        if not row or row == [''] or row[0].startswith('#'):
            continue
        if len(row) != 4:
            raise BlacklistError(f'{path}:{n}: calen 4 columnes: {row}')
        pattern, level, reason, exc = (c.strip() for c in row)
        if level not in LEVELS:
            raise BlacklistError(f'{path}:{n}: nivell desconegut {level!r}')
        if not reason:
            raise BlacklistError(f'{path}:{n}: regla sense motiu: «{pattern}»')
        substring = pattern.startswith('~')
        try:
            rx = re.compile(pattern[1:] if substring else pattern)
        except re.error as e:
            raise BlacklistError(f'{path}:{n}: expressió invàlida {pattern!r}: {e}') from None
        out.append(RootRule(rx, level, reason, frozenset(x for x in exc.split('|') if x),
                            substring))
    return out


def root_entries(rules: list[RootRule], lemmas: Iterable[str]) -> dict[str, Veto]:
    """Vetos per arrel sobre els lemes del diccionari (el més greu si n'hi ha diversos)."""
    rank = {'absolute': 2, 'sensitive': 1}
    out: dict[str, Veto] = {}
    for lemma in sorted(set(lemmas)):
        if N.canonicalize(lemma) != lemma:
            continue
        for r in rules:
            if not r.matches(lemma):
                continue
            prev = out.get(lemma)
            if prev is None or rank[r.level] > rank[prev.level]:
                out[lemma] = Veto(r.level, f'arrel /{r.pattern.pattern}/: {r.reason}')
    return out


def source_entries(sources: dict[str, set[str]]) -> dict[str, Veto]:
    """Lemes que Softcatalà marca com a vulgars o pejoratius al camp `fonts:` -> sensitive."""
    out = {}
    for lemma, src in sorted(sources.items()):
        hit = sorted(src & OFFENSIVE_SOURCES)
        if hit and N.canonicalize(lemma) == lemma:
            out[lemma] = Veto('sensitive', f'softcatalà:fonts {hit[0]}')
    return out


def merge(auto: dict[str, Veto], manual: dict[str, Veto]) -> dict[str, Veto]:
    """La llista manual preval; `allow` només retira vetos automàtics `sensitive`."""
    merged = dict(auto)
    for form, veto in manual.items():
        if veto.level == 'allow':
            prev = auto.get(form)
            if prev is not None and prev.level == 'absolute':
                raise BlacklistError(
                    f'«{form}»: `allow` no pot retirar un veto absolute ({prev.reason})')
            merged.pop(form, None)
        else:
            merged[form] = veto
    return merged


def propagation_targets(entries: Iterable[SC.LtEntry]):
    """(forma -> {(lema, etiqueta)}, lema -> formes) del diccionari LT complet."""
    lemmas_of: dict[str, set[tuple[str, str]]] = defaultdict(set)
    forms_of: dict[str, set[str]] = defaultdict(set)
    for e in entries:
        lemmas_of[e.form].add((e.lemma, e.tag))
        forms_of[e.lemma].add(e.form)
    return lemmas_of, forms_of


def propagate(vetoes: dict[str, Veto], lemmas_of, forms_of) -> dict[str, tuple[Veto, str]]:
    """Aplica cada veto a la forma, al seu lema i a totes les formes del lema.

    - Si la forma vetada és ella mateixa un lema, només es propaga a les formes d'aquest
      lema (no als lemes dels quals és homògrafa: `busca` no veta `buscar`).
    - Els vetos sense `spread` (accepció secundària) no es propaguen als lemes d'una forma
      que no és lema, ni a formes que també pertanyen a un altre lema.
    - Una forma propagada que també és forma no verbal d'un lema no vetat (homògraf
      innocent, p. ex. `foto` de `fotre` i del nom `foto`) rep com a màxim el nivell
      `sensitive`: es continua acceptant com a intent però mai no és solució. Els
      homògrafs només verbals (participi `malparida` de `malparir`) no rebaixen el veto.
    """
    rank = {'absolute': 2, 'sensitive': 1}
    out: dict[str, tuple[Veto, str]] = {}
    targets = {s: ({s} if s in forms_of else
                   {lm for lm, _ in lemmas_of.get(s, ())} if vetoes[s].spread else set())
               for s in vetoes}
    vetoed_lemmas = set(vetoes) | {lm for ls in targets.values() for lm in ls}

    def put(form: str, veto: Veto, source: str):
        prev = out.get(form)
        if prev is None or (rank[veto.level], source == form, -len(source), source) > \
                (rank[prev[0].level], prev[1] == form, -len(prev[1]), prev[1]):
            out[form] = (veto, source)

    for source in sorted(vetoes):
        veto = vetoes[source]
        put(source, veto, source)
        for lemma in sorted(targets[source]):
            for f in sorted(forms_of.get(lemma, set()) | {lemma}):
                if f == source:
                    continue
                if not veto.spread and any(lm != lemma for lm, _ in lemmas_of.get(f, ())):
                    continue  # forma compartida amb un altre lema (`mamà` de `mamar`)
                innocent = sorted(lm for lm, tag in lemmas_of.get(f, ())
                                  if lm not in vetoed_lemmas and not tag.startswith('V'))
                if innocent and veto.level == 'absolute':
                    put(f, Veto('sensitive', f'{veto.reason}; homògraf de «{innocent[0]}»'),
                        source)
                else:
                    put(f, veto, source)
    return out


def build_rows(propagated: dict[str, tuple[Veto, str]]) -> list[tuple[str, str, str, str]]:
    rows = []
    for form, (veto, source) in propagated.items():
        canon = N.canonicalize(form)
        if canon is None or canon != form:
            continue  # formes amb apòstrof, guionet, majúscules…: mai jugables
        key = N.grid_key(form)
        reason = veto.reason if source == form else f'{veto.reason} [de «{source}»]'
        rows.append((key, form, veto.level, reason))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def build(dict_tools: SC.DictToolsPaths, dump: Path, manual_path: Path,
          roots_path: Path | None = None) -> list[tuple]:
    lt = list(SC.iter_lt(dict_tools.lt_dictionary))
    lemmas_of, forms_of = propagation_targets(lt)
    manual = load_manual(manual_path)
    missing = sorted(f for f in manual if f not in lemmas_of)
    if missing:
        raise BlacklistError(f'formes de la llista manual absents del diccionari LT: {missing}')
    auto = {f: v for f, v in auto_entries(W.iter_pages(dump)).items() if f in lemmas_of}
    # Ordre de precedència (de menys a més): fonts de Softcatalà, marques del
    # Viquidiccionari, regles per arrel i llista manual.
    common = {e.lemma for e in lt if not SC.is_excluded_tag(e.tag)}
    derived = source_entries({lm: s for lm, s in SC.lemma_sources(dict_tools.arrel).items()
                              if lm in common})
    derived.update(auto)
    for lemma, veto in root_entries(load_roots(roots_path), common).items():
        prev = derived.get(lemma)
        if prev is None or prev.level != 'absolute' or veto.level == 'absolute':
            derived[lemma] = veto
    return build_rows(propagate(merge(derived, manual), lemmas_of, forms_of))


def read_blacklist(path: Path) -> list[dict[str, str]]:
    header, rows = tsv.read_tsv(path)
    if tuple(header) != HEADER:
        raise BlacklistError(f'{path}: capçalera inesperada {header}')
    return [dict(zip(HEADER, r)) for r in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Genera la llista negra')
    ap.add_argument('--dict-tools', type=Path)
    ap.add_argument('--dump', type=Path)
    ap.add_argument('--manual', type=Path, default=config.DATA_DIR / 'blacklist_manual.tsv')
    ap.add_argument('--roots', type=Path, default=config.DATA_DIR / 'blacklist_roots.tsv')
    ap.add_argument('--out-dir', type=Path, default=config.LEXICON_DIR)
    a = ap.parse_args(argv)
    dt = SC.DictToolsPaths(a.dict_tools) if a.dict_tools else config.default_dict_tools()
    dump = a.dump or config.default_dump()
    try:
        rows = build(dt, dump, a.manual, a.roots)
    except BlacklistError as e:
        raise SystemExit(f'ERROR: {e}') from None
    tsv.write_tsv(a.out_dir / 'blacklist.tsv', HEADER, rows)
    n_abs = sum(r[2] == 'absolute' for r in rows)
    print(f'[blacklist] {len(rows)} formes ({n_abs} absolute, {len(rows) - n_abs} sensitive)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
