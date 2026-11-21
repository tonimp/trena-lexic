#!/usr/bin/env python3
"""Genera assets/lexicon/daurades.tsv i tool/reports/daurades.json (canvi OpenSpec
`paraules-daurades`, spec lexicon-golden).

Cada nivell del banc general (1–480) pot tenir una «paraula daurada»: una de les seves
paraules extra, triada per dades (design D2–D6) i revisada a mà (D8):

- Candidates («Candidatas de un nivel»): extres del puzle que són candidates de
  `solutions.tsv` amb `kind` = `lemma`, no homògrafes d'un plural o femení d'un altre lema
  (D33), de 4 lletres o més, amb pista a `clues.tsv`, sense veto de la llista negra a la forma,
  al lema ni a les paraules de la pista, fora d'`apres.tsv`, fora de
  `tool/data/daurades_exclusions.tsv` i amb una clau diferent de la de qualsevol solució.
- Elecció per bandes (D3): a les madeixes 1–4 i als nivells senars des de la 5, banda 3; als
  parells des de la 5, banda 4 o més; després l'altra banda ≥ 3, la 2 i la 1. Dins un esglaó:
  clau de 5 lletres o més, nom > adjectiu > verb > la resta, menor `rank` i grafia (D4).
- Sense repeticions (D5): un lema per banc; s'assignen primer els nivells amb menys
  candidates (i, a igualtat, el número de nivell).

La revisió (`tool/data/daurades_reviews.tsv`) no la comprova la construcció, sinó
`tool/tests/test_daurades.py`; `--todo` llista les files pendents o sobrants.

Ús:
    python3 -I tool/build_daurades.py [--out-dir DIR] [--puzzles-dir DIR] [--report FILE]
    python3 -I tool/build_daurades.py --todo
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_apres as A  # noqa: E402
from lexlib import config, tsv  # noqa: E402
from lexlib import normalize as N  # noqa: E402

HEADER = ('level', 'key', 'form', 'lemma', 'band')
EXCLUSIONS = config.DATA_DIR / 'daurades_exclusions.tsv'
REVIEWS = config.DATA_DIR / 'daurades_reviews.tsv'
EXCLUSIONS_HEADER = ['form', 'reason']
REVIEWS_HEADER = ['level', 'form', 'clue', 'verdict', 'note']
LEVELS_DIR = config.ASSETS_DIR / 'puzzles' / 'levels'
REPORT = config.TOOL_DIR / 'reports' / 'daurades.json'
MIN_KEY = 4          # lletres mínimes de la clau
LONG_KEY = 5         # preferència dins d'un esglaó (D4)
EARLY_MADEIXES = 4   # madeixes 1–4: sempre banda 3 (D3)
LEVELS_PER_MADEIXA = 30
POS_ORDER = {'N': 0, 'A': 1, 'V': 2}


class DauradesError(Exception):
    pass


@dataclass(frozen=True)
class Level:
    number: int
    madeixa: int
    grid_keys: frozenset[str]
    extras: tuple[str, ...]


@dataclass(frozen=True)
class Cand:
    key: str
    form: str
    lemma: str
    band: int
    pos: str
    rank: int


@dataclass(frozen=True)
class Golden:
    level: int
    key: str
    form: str
    lemma: str
    band: int


# --------------------------------------------------------------------------- lectura

def read_levels(levels_dir: Path) -> list[Level]:
    out: list[Level] = []
    for path in sorted(levels_dir.glob('*.json'), key=lambda p: p.name.encode()):
        data = json.loads(path.read_text(encoding='utf-8'))
        for p in data['puzzles']:
            out.append(Level(int(p['number']), int(p['madeixa']),
                             frozenset(w['key'] for w in p['words']), tuple(p['extras'])))
    out.sort(key=lambda lv: lv.number)
    numbers = [lv.number for lv in out]
    if len(set(numbers)) != len(numbers):
        raise DauradesError(f'{levels_dir}: números de nivell repetits')
    return out


def read_manual(path: Path, header: list[str]) -> list[tuple[int, list[str]]]:
    try:
        return A.read_manual(path, header)
    except A.ApresError as e:
        raise DauradesError(str(e)) from None


def read_exclusions(path: Path, extras: set[str]) -> dict[str, str]:
    """Forma -> motiu. Falla (fitxer:línia) si la forma no és canònica, està repetida, no té
    motiu o no és extra de cap nivell («Exclusión huérfana»)."""
    out: dict[str, str] = {}
    for n, (form, reason) in read_manual(path, EXCLUSIONS_HEADER):
        where = f'{path}:{n}'
        if N.canonicalize(form) != form:
            raise DauradesError(f'{where}: «{form}» no és una grafia canònica')
        if not reason.strip():
            raise DauradesError(f'{where}: «{form}» sense motiu')
        if form in out:
            raise DauradesError(f'{where}: «{form}» repetida')
        if form not in extras:
            raise DauradesError(f'{where}: «{form}» no és extra de cap nivell '
                                '(exclusió òrfena)')
        out[form] = reason
    return out


def read_apres(lexicon_dir: Path) -> set[str]:
    path = lexicon_dir / 'apres.tsv'
    if not path.exists():
        raise DauradesError(f'{path}: no existeix (cal executar abans build_apres.py)')
    _, rows = tsv.read_tsv(path)
    return {r[1] for r in rows}


# --------------------------------------------------------------------------- regles

def preferred_tier(level: Level, band: int) -> int:
    """Esglaó de preferència (0 = millor) de la banda d'una candidata en un nivell (D3)."""
    want3 = level.madeixa <= EARLY_MADEIXES or level.number % 2 == 1
    if (band == 3 and want3) or (band >= 4 and not want3):
        return 0
    if band >= 3:
        return 1
    return 2 if band == 2 else 3


def preference(level: Level, c: Cand) -> tuple:
    return (preferred_tier(level, c.band), 0 if len(c.key) >= LONG_KEY else 1,
            POS_ORDER.get(c.pos[:1], 3), c.rank, c.form.encode())


def inflected_homograph(row: list[str]) -> bool:
    """D33: la grafia també és una forma flexionada (plural o femení) d'un altre lema nominal:
    `lemmas` de `solutions.tsv` amb un lema diferent de la forma que no és un verb de `verbs`
    («tirs», plural de «tir»). Les homògrafes d'una forma verbal («boira», «compra») sí que
    poden ser daurades: la pista és la del nom."""
    form = row[1]
    lemmas = {x for x in row[8].split('|') if x}
    verbs = {x for x in row[9].split('|') if x}
    return bool(lemmas - verbs - {form})


def candidates(lex: A.Lexicon, level: Level, apres: set[str], exclusions: dict[str, str],
               discards: dict[str, set[str]]) -> list[Cand]:
    out: list[Cand] = []
    for form in level.extras:
        key = N.grid_key(form)
        row = lex.solutions.get((key, form)) if key else None
        if row is None or row[3] != 'lemma':
            discards['no_lema_candidat'].add(form)
            continue
        if inflected_homograph(row):
            discards['homograf_flexionat'].add(form)
            continue
        if len(key) < MIN_KEY:
            discards['curta'].add(form)
            continue
        clue = lex.clues.get(form)
        if clue is None:
            discards['sense_pista'].add(form)
            continue
        lemma = row[2]
        if lex.vetoed(form) or lex.vetoed(lemma):
            discards['veto_forma_o_lema'].add(form)
            continue
        if not lex.accepted_spelling(form) or not lex.accepted_spelling(lemma):
            discards['fora_de_la_llista_blanca'].add(form)
            continue
        if A.clue_keys(clue.text) & lex.blacklist_keys:
            discards['veto_definicio'].add(form)
            continue
        if form in apres:
            discards['has_apres'].add(form)
            continue
        if key in level.grid_keys:
            discards['clau_de_solucio'].add(form)
            continue
        if form in exclusions:
            discards['exclusio_manual'].add(form)
            continue
        out.append(Cand(key, form, lemma, int(row[7]), row[4], int(row[6])))
    return out


def choose(levels: list[Level], cands: dict[int, list[Cand]]) -> dict[int, Golden]:
    """Assignació sense lemes repetits (D5)."""
    by_number = {lv.number: lv for lv in levels}
    used: set[str] = set()
    out: dict[int, Golden] = {}
    for n in sorted(cands, key=lambda n: (len(cands[n]), n)):
        lv = by_number[n]
        opts = sorted((c for c in cands[n] if c.lemma not in used),
                      key=lambda c: preference(lv, c))
        if opts:
            c = opts[0]
            used.add(c.lemma)
            out[n] = Golden(n, c.key, c.form, c.lemma, c.band)
    return out


# --------------------------------------------------------------------------- revisió

def review_rows(golden: dict[int, Golden], lex: A.Lexicon) -> list[tuple[str, str, str]]:
    """(nivell, forma, pista publicada) que ha de tenir daurades_reviews.tsv, per nivell."""
    return [(str(g.level), g.form, lex.clues[g.form].text)
            for g in sorted(golden.values(), key=lambda g: g.level)]


def read_reviews(path: Path = REVIEWS) -> list[tuple[int, list[str]]]:
    return read_manual(path, REVIEWS_HEADER)


def review_problems(want: list[tuple[str, str, str]],
                    reviews: list[tuple[int, list[str]]]) -> list[str]:
    """Problemes del registre respecte de les files que calen («Revisión registrada de las
    daurades»): pendents, sobrants, repetides, veredicte diferent d'`ok` i pista diferent."""
    out: list[str] = []
    have: dict[tuple[str, str], list[str]] = {}
    for n, r in reviews:
        k = (r[0], r[1])
        if k in have:
            out.append(f'línia {n}: {r[1]} (nivell {r[0]}) repetida')
        have[k] = r
        if r[3] != 'ok':
            out.append(f'línia {n}: {r[1]} (nivell {r[0]}) amb veredicte «{r[3]}», no «ok»')
    wanted = {(lv, f): clue for lv, f, clue in want}
    for (lv, f), clue in wanted.items():
        r = have.get((lv, f))
        if r is None:
            out.append(f'pendent de revisió: nivell {lv}: {f}: {clue}')
        elif r[2] != clue:
            out.append(f'pista canviada després de revisar-la: nivell {lv}: {f}: '
                       f'revisada «{r[2]}», publicada «{clue}»')
    for lv, f in sorted(set(have) - set(wanted), key=lambda k: (int(k[0]) if k[0].isdigit()
                                                                 else 0, k[1])):
        out.append(f'sobra la revisió de {f} (nivell {lv}): no és la daurada del nivell')
    return out


# --------------------------------------------------------------------------- informe

def report(levels, cands, golden, discards, exclusions) -> dict:
    madeixes = sorted({lv.madeixa for lv in levels})
    by_m = {str(m): {'levels': sum(1 for lv in levels if lv.madeixa == m),
                     'golden': sum(1 for lv in levels
                                   if lv.madeixa == m and lv.number in golden)}
            for m in madeixes}
    by_number = {lv.number: lv for lv in levels}
    tiers = collections.Counter(preferred_tier(by_number[g.level], g.band)
                                for g in golden.values())
    return {
        'schema': 1,
        'levels': len(levels),
        'levels_with_candidates': sum(1 for n in cands if cands[n]),
        'golden': len(golden),
        'golden_by_band': {str(k): v for k, v in sorted(collections.Counter(
            g.band for g in golden.values()).items())},
        'golden_by_band_group': {
            '1-2': sum(1 for g in golden.values() if g.band <= 2),
            '3': sum(1 for g in golden.values() if g.band == 3),
            '4+': sum(1 for g in golden.values() if g.band >= 4)},
        'golden_by_tier': {str(k): v for k, v in sorted(tiers.items())},
        'golden_by_length': {str(k): v for k, v in sorted(collections.Counter(
            len(g.key) for g in golden.values()).items())},
        'golden_by_madeixa': by_m,
        'levels_without_golden': [lv.number for lv in levels if lv.number not in golden],
        'candidates_per_level': {str(k): v for k, v in sorted(collections.Counter(
            len(c) for c in cands.values()).items())},
        'exclusions': len(exclusions),
        'discarded_forms': {k: len(v) for k, v in sorted(discards.items())},
    }


# --------------------------------------------------------------------------- main

def build(lexicon_dir: Path, levels_dir: Path, exclusions_path: Path = EXCLUSIONS):
    lex = A.Lexicon(lexicon_dir)
    levels = read_levels(levels_dir)
    extras = {f for lv in levels for f in lv.extras}
    exclusions = read_exclusions(exclusions_path, extras)
    apres = read_apres(lexicon_dir)
    discards: dict[str, set[str]] = collections.defaultdict(set)
    cands = {lv.number: candidates(lex, lv, apres, exclusions, discards) for lv in levels}
    golden = choose(levels, cands)
    rep = report(levels, cands, golden, discards, exclusions)
    return lex, levels, cands, golden, rep


def write(out_dir: Path, golden: dict[int, Golden]) -> Path:
    path = out_dir / 'daurades.tsv'
    tsv.write_tsv(path, HEADER, [(g.level, g.key, g.form, g.lemma, g.band)
                                 for g in sorted(golden.values(), key=lambda g: g.level)])
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Genera daurades.tsv (paraules daurades)')
    ap.add_argument('--out-dir', type=Path, default=config.LEXICON_DIR)
    ap.add_argument('--puzzles-dir', type=Path, default=config.ASSETS_DIR / 'puzzles',
                    help='carpeta del banc (es llegeix només levels/)')
    ap.add_argument('--exclusions', type=Path, default=EXCLUSIONS)
    ap.add_argument('--report', type=Path, default=REPORT)
    ap.add_argument('--todo', action='store_true',
                    help='mostra les files de revisió pendents o sobrants (no escriu res)')
    a = ap.parse_args(argv)
    try:
        lex, levels, cands, golden, rep = build(a.out_dir, a.puzzles_dir / 'levels',
                                                a.exclusions)
    except DauradesError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1
    if a.todo:
        want = review_rows(golden, lex)
        have = {(r[0], r[1]): r for _, r in read_reviews()} if REVIEWS.exists() else {}
        for lv, form, clue in want:
            r = have.get((lv, form))
            if r is None or r[2] != clue:
                g = golden[int(lv)]
                c = next(c for c in cands[int(lv)] if c.form == form)
                print('\t'.join((lv, form, clue, f'b{g.band}', c.pos, str(c.rank),
                                 f'n={len(cands[int(lv)])}')))
        wanted = {(lv, f) for lv, f, _ in want}
        for k in sorted(set(have) - wanted):
            print(f'SOBRA\t{k[0]}\t{k[1]}', file=sys.stderr)
        return 0
    path = write(a.out_dir, golden)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'[daurades] {path.name}: {len(golden)} de {len(levels)} nivells; '
          f'bandes {rep["golden_by_band_group"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
