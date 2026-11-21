#!/usr/bin/env python3
"""Genera assets/lexicon/apres.tsv i tool/reports/apres.json (canvi OpenSpec `has-apres`).

`apres.tsv` és la llista de grafies que poden sortir a la targeta «Has après» (design.md D3):
solucions (`words[]`) del banc de puzles (nivells, Trenes del dia i reptes de temporada) que són
candidates de `solutions.tsv`, amb raresa > 8.000 (raresa = el menor rang entre la forma i el seu
lema), pista en cada context on són solució, sense cap clau de la llista negra (qualsevol nivell)
a la forma, al lema ni a les paraules de cap de les seves definicions, i fora de
`tool/data/apres_exclusions.tsv`.

El fitxer no porta cap text de definició: l'app la llegeix del mateix índex que l'ajuda «Pista».
L'informe `tool/reports/apres.json` recull els recomptes, els descarts per motiu i quants puzles
de cada banc tenen targeta (mateixa selecció que l'app, `select_card`).

Ús:
    python3 -I tool/build_apres.py [--out-dir DIR] [--puzzles-dir DIR] [--report FILE]
    python3 -I tool/build_apres.py --todo   # files de revisió pendents (apres_reviews.tsv)
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_clues as BC  # noqa: E402
from lexlib import config, tsv  # noqa: E402
from lexlib import normalize as N  # noqa: E402

HEADER = ('key', 'form', 'lemma', 'kind', 'rarity')
THRESHOLD = 8000            # raresa estrictament superior (D1)
REVIEW_SPLIT = 12000        # les de raresa > 12.000 ja es van revisar com a pista
GENERAL = 'general'         # context del banc general (nivells i Trenes del dia)
MAX_ENTRIES = {'levels': 2, 'daily': 3, 'season': 3, 'theme': 2}   # D7 (tema: com els nivells)
EXCLUSIONS = config.DATA_DIR / 'apres_exclusions.tsv'
REVIEWS = config.DATA_DIR / 'apres_reviews.tsv'
EXCLUSIONS_HEADER = ['form', 'reason']
REVIEWS_HEADER = ['form', 'context', 'verdict', 'clue', 'note']
PUZZLES_DIR = config.ASSETS_DIR / 'puzzles'
REPORT = config.TOOL_DIR / 'reports' / 'apres.json'


class ApresError(Exception):
    pass


@dataclass(frozen=True)
class Word:
    key: str
    form: str


@dataclass(frozen=True)
class Puzzle:
    id: str
    bank: str        # `levels`, `daily` o `<temporada>-<any>`
    kind: str        # `levels`, `daily` o `season`
    context: str     # `general` o l'id de la temporada (`nadal`)
    words: tuple[Word, ...]


@dataclass(frozen=True)
class Clue:
    text: str
    source: str


# --------------------------------------------------------------------------- lectura

def read_bank(puzzles_dir: Path) -> list[Puzzle]:
    """Tots els puzles d'`assets/puzzles/` en ordre de fitxer (camí) i de posició."""
    out: list[Puzzle] = []
    for path in sorted(puzzles_dir.rglob('*.json'),
                       key=lambda p: p.relative_to(puzzles_dir).as_posix().encode()):
        rel = path.relative_to(puzzles_dir).parts
        if rel[0] == 'llampec':
            continue  # Trena llampec (trena-llampec): sense «Has après» (partida sense ajudes)
        data = json.loads(path.read_text(encoding='utf-8'))
        if rel[0] == 'themes':
            # temàtiques (madeixes-tematiques): context = id del tema, amb les seves pistes
            theme = data['theme']
            bank, kind, context = f'tema-{theme}', 'theme', theme
        elif rel[0] == 'seasons':
            season = data['season']
            bank, kind, context = f'{season}-{data["year"]}', 'season', season
        elif rel[0] in ('levels', 'daily'):
            bank, kind, context = rel[0], rel[0], GENERAL
        else:
            raise ApresError(f'{path}: directori de puzles no previst')
        for p in data['puzzles']:
            words = tuple(Word(w['key'], w['form']) for w in p['words'])
            out.append(Puzzle(p['id'], bank, kind, context, words))
    return out


def read_clues(path: Path) -> dict[str, Clue]:
    _, rows = tsv.read_tsv(path)
    return {r[1]: Clue(r[3], r[4]) for r in rows}


def read_season_clues(lexicon_dir: Path) -> dict[str, dict[str, Clue]]:
    """Pistes de context: temporades (`seasons/`) i temàtiques (`themes/`), per id."""
    out: dict[str, dict[str, Clue]] = {}
    for sub in ('seasons', 'themes'):
        d = lexicon_dir / sub
        if d.is_dir():
            out.update({p.name[:-len('-clues.tsv')]: read_clues(p)
                        for p in sorted(d.glob('*-clues.tsv'))})
    return out


def read_accepted(path: Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        key, _, sp = line.partition('\t')
        out[key] = set(sp.split('|')) if sp else {N.trivial_spelling(key)}
    return out


def read_manual(path: Path, header: list[str]) -> list[tuple[int, list[str]]]:
    """Files (número de línia, cel·les) d'un TSV manual amb capçalera i comentaris `#`."""
    if not path.exists():
        raise ApresError(f'{path}: no existeix')
    lines = path.read_text(encoding='utf-8').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    if not lines or lines[0].split('\t') != header:
        raise ApresError(f'{path}:1: capçalera esperada {" ".join(header)}')
    out = []
    for n, line in enumerate(lines[1:], start=2):
        if not line.strip() or line.startswith('#'):
            continue
        cells = line.split('\t')
        if len(cells) != len(header):
            raise ApresError(f'{path}:{n}: {len(cells)} columnes, se n’esperaven {len(header)}')
        out.append((n, cells))
    return out


def read_exclusions(path: Path, bank_forms: set[str]) -> dict[str, str]:
    """Forma -> motiu. Falla (fitxer:línia) si la forma no és canònica, està repetida, no té
    motiu o no és solució de cap puzle del banc (exclusió òrfena)."""
    out: dict[str, str] = {}
    for n, (form, reason) in read_manual(path, EXCLUSIONS_HEADER):
        where = f'{path}:{n}'
        if N.canonicalize(form) != form:
            raise ApresError(f'{where}: «{form}» no és una grafia canònica')
        if not reason.strip():
            raise ApresError(f'{where}: «{form}» sense motiu')
        if form in out:
            raise ApresError(f'{where}: «{form}» repetida')
        if form not in bank_forms:
            raise ApresError(f'{where}: «{form}» no és solució de cap puzle del banc '
                             '(exclusió òrfena)')
        out[form] = reason
    return out


# --------------------------------------------------------------------------- regles

def strip_label(clue: str) -> str:
    """Definició sense l'etiqueta inicial «(plural) », «(femení) » o «(femení plural) »."""
    return BC.LABEL.sub('', clue, count=1)


def clue_keys(clue: str) -> set[str]:
    """Claus de les paraules d'una definició (mateixa normalització que el filtre de pistes)."""
    out = set()
    for w in BC.clue_words(clue):
        k = N.grid_key(w)
        if k:
            out.add(k)
    return out


class Lexicon:
    """Dades d'`assets/lexicon/` que fan servir les regles."""

    def __init__(self, lexicon_dir: Path):
        _, sol = tsv.read_tsv(lexicon_dir / 'solutions.tsv')
        self.solutions: dict[tuple[str, str], list[str]] = {(r[0], r[1]): r for r in sol}
        self.rank_of_form: dict[str, int] = {}
        for r in sol:
            rank = int(r[6])
            self.rank_of_form[r[1]] = min(rank, self.rank_of_form.get(r[1], rank))
        _, bl = tsv.read_tsv(lexicon_dir / 'blacklist.tsv')
        self.blacklist_keys = {r[0] for r in bl}
        self.blacklist_forms = {r[1] for r in bl}
        self.accepted = read_accepted(lexicon_dir / 'accepted.tsv')
        self.clues = read_clues(lexicon_dir / 'clues.tsv')
        self.season_clues = read_season_clues(lexicon_dir)

    def rarity(self, key: str, form: str) -> int:
        """min(rang de la forma, rang del lema si el lema és candidata) (D1)."""
        row = self.solutions[(key, form)]
        rank = int(row[6])
        lemma_rank = self.rank_of_form.get(row[2])
        return rank if lemma_rank is None else min(rank, lemma_rank)

    def clue(self, form: str, context: str) -> Clue | None:
        """Pista que mostraria l'ajuda «Pista» (spec hint-clues): primer la de temporada."""
        if context != GENERAL:
            c = self.season_clues.get(context, {}).get(form)
            if c is not None:
                return c
        return self.clues.get(form)

    def vetoed(self, form: str) -> bool:
        k = N.grid_key(form)
        return form in self.blacklist_forms or (k is not None and k in self.blacklist_keys)

    def accepted_spelling(self, form: str) -> bool:
        k = N.grid_key(form)
        return k is not None and form in self.accepted.get(k, ())


@dataclass(frozen=True)
class Entry:
    key: str
    form: str
    lemma: str
    kind: str
    rarity: int


def evaluate(lex: Lexicon, bank: list[Puzzle], exclusions: dict[str, str]):
    """(entrades elegibles, descarts {motiu: [(forma, detall)]}, contextos per forma)."""
    contexts: dict[Word, set[str]] = collections.defaultdict(set)
    for p in bank:
        for w in p.words:
            contexts[w].add(p.context)
    entries: list[Entry] = []
    discards: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    frequent = 0
    for w in sorted(contexts, key=lambda w: (w.key, w.form)):
        row = lex.solutions.get((w.key, w.form))
        if row is None:
            discards['no_candidata'].append((w.form, ''))
            continue
        rarity = lex.rarity(w.key, w.form)
        if rarity <= THRESHOLD:
            frequent += 1
            continue
        lemma, kind = row[2], row[3]
        if lex.vetoed(w.form) or lex.vetoed(lemma):
            discards['veto_forma_o_lema'].append((w.form, lemma))
            continue
        if not lex.accepted_spelling(w.form) or not lex.accepted_spelling(lemma):
            discards['fora_de_la_llista_blanca'].append((w.form, lemma))
            continue
        ctxs = sorted(contexts[w])
        clues = {c: lex.clue(w.form, c) for c in ctxs}
        missing = [c for c, cl in clues.items() if cl is None]
        if missing:
            discards['sense_pista'].append((w.form, ','.join(missing)))
            continue
        bad = sorted({k for cl in clues.values() for k in clue_keys(cl.text)
                      if k in lex.blacklist_keys})
        if bad:
            discards['veto_definicio'].append((w.form, ','.join(bad)))
            continue
        if w.form in exclusions:
            discards['exclusio_manual'].append((w.form, exclusions[w.form]))
            continue
        entries.append(Entry(w.key, w.form, lemma, kind, rarity))
    return entries, discards, frequent, contexts


@dataclass(frozen=True)
class CardEntry:
    form: str
    lemma: str
    definition: str
    source: str


def select_card(p: Puzzle, apres: dict[str, Entry], lex: Lexicon) -> list[CardEntry]:
    """Selecció de la targeta (spec learned-words), la mateixa que fa l'app: candidates per
    raresa descendent i ordre a `words[]`; fora les que tenen a la definició la clau d'una altra
    solució del puzle; un lema i una definició per targeta; màxim segons la pantalla."""
    cands = [(i, w) for i, w in enumerate(p.words) if w.form in apres]
    cands.sort(key=lambda iw: (-apres[iw[1].form].rarity, iw[0]))
    out: list[CardEntry] = []
    lemmas: set[str] = set()
    defs: set[str] = set()
    for i, w in cands:
        clue = lex.clue(w.form, p.context)
        if clue is None:
            continue
        definition = strip_label(clue.text)
        others = {o.key for j, o in enumerate(p.words) if j != i}
        if clue_keys(definition) & others:
            continue
        e = apres[w.form]
        if e.lemma in lemmas or definition in defs:
            continue
        lemmas.add(e.lemma)
        defs.add(definition)
        out.append(CardEntry(w.form, e.lemma, definition, clue.source))
        if len(out) == MAX_ENTRIES[p.kind]:
            break
    return out


SIMILAR = 0.25   # semblança màxima (Jaccard) entre dues definicions d'una mateixa targeta


def definition_overlap(a: str, b: str) -> float:
    """Jaccard de les paraules de ≥ 4 lletres de dues definicions (sinònims com llau/allau).
    No és una regla del selector de l'app: el test exigeix que cap targeta del banc la superi i
    els casos es resolen amb una exclusió (QA has-apres O8)."""
    wa = {w.lower() for w in BC.clue_words(a) if len(w) >= 4}
    wb = {w.lower() for w in BC.clue_words(b) if len(w) >= 4}
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def review_rows(entries: list[Entry], contexts, lex: Lexicon) -> list[tuple[str, str, str]]:
    """(forma, context, pista publicada) que ha de tenir apres_reviews.tsv, en ordre."""
    out = []
    for e in sorted(entries, key=lambda e: (e.key, e.form)):
        for c in sorted(contexts[Word(e.key, e.form)]):
            out.append((e.form, c, lex.clue(e.form, c).text))
    return out


def read_reviews(path: Path = REVIEWS) -> list[tuple[int, list[str]]]:
    return read_manual(path, REVIEWS_HEADER)


def review_problems(want: list[tuple[str, str, str]],
                    reviews: list[tuple[int, list[str]]]) -> list[str]:
    """Problemes del registre de revisió respecte de les files que calen (spec lexicon-learned,
    «Revisió registrada»): pendents, sobrants, repetides, veredicte diferent d'`ok` i pista
    revisada diferent de la publicada. Llista buida si tot quadra."""
    out: list[str] = []
    have: dict[tuple[str, str], list[str]] = {}
    for n, r in reviews:
        k = (r[0], r[1])
        if k in have:
            out.append(f'línia {n}: {r[0]} ({r[1]}) repetida')
        have[k] = r
        if r[2] != 'ok':
            out.append(f'línia {n}: {r[0]} ({r[1]}) amb veredicte «{r[2]}», no «ok»')
    wanted = {(f, c): clue for f, c, clue in want}
    for (f, c), clue in wanted.items():
        r = have.get((f, c))
        if r is None:
            out.append(f'pendent de revisió: {f} ({c}): {clue}')
        elif r[3] != clue:
            out.append(f'pista canviada després de revisar-la: {f} ({c}): '
                       f'revisada «{r[3]}», publicada «{clue}»')
    for f, c in sorted(set(have) - set(wanted)):
        out.append(f'sobra la revisió de {f} ({c}): no és a apres.tsv en aquest context')
    return out


# --------------------------------------------------------------------------- informe

def report(entries, discards, frequent, bank, lex, apres) -> dict:
    banks: dict[str, dict] = {}
    for p in bank:
        b = banks.setdefault(p.bank, {'puzzles': 0, 'with_card': 0, 'entries': 0,
                                      'by_size': collections.Counter(),
                                      'dropped_other_solution': 0})
        card = select_card(p, apres, lex)
        b['puzzles'] += 1
        b['by_size'][len(card)] += 1
        if card:
            b['with_card'] += 1
            b['entries'] += len(card)
        # candidates descartades per contenir una altra solució del puzle
        for i, w in enumerate(p.words):
            if w.form in apres:
                cl = lex.clue(w.form, p.context)
                others = {o.key for j, o in enumerate(p.words) if j != i}
                if cl is not None and clue_keys(strip_label(cl.text)) & others:
                    b['dropped_other_solution'] += 1
    for b in banks.values():
        b['by_size'] = {str(k): v for k, v in sorted(b['by_size'].items())}
        b['percent_with_card'] = round(100 * b['with_card'] / b['puzzles'], 1)
    sources = collections.Counter()
    for e in entries:
        cl = lex.clues.get(e.form)
        sources['pròpia' if cl is None or cl.source == 'pròpia' else 'viquidiccionari'] += 1
    return {
        'schema': 1,
        'threshold': THRESHOLD,
        'eligible': len(entries),
        'eligible_by_kind': dict(sorted(collections.Counter(e.kind for e in entries).items())),
        'eligible_by_rarity': {
            f'{THRESHOLD + 1}-{REVIEW_SPLIT}': sum(1 for e in entries
                                                   if e.rarity <= REVIEW_SPLIT),
            f'>{REVIEW_SPLIT}': sum(1 for e in entries if e.rarity > REVIEW_SPLIT),
        },
        'eligible_general_clue_source': dict(sorted(sources.items())),
        'bank_solutions_frequent': frequent,
        'discards': {k: len(v) for k, v in sorted(discards.items())},
        'discarded': {k: [{'form': f, 'detail': d} for f, d in v]
                      for k, v in sorted(discards.items())},
        'banks': dict(sorted(banks.items())),
    }


# --------------------------------------------------------------------------- main

def build(lexicon_dir: Path, puzzles_dir: Path, exclusions_path: Path = EXCLUSIONS):
    lex = Lexicon(lexicon_dir)
    bank = read_bank(puzzles_dir)
    bank_forms = {w.form for p in bank for w in p.words}
    exclusions = read_exclusions(exclusions_path, bank_forms)
    entries, discards, frequent, contexts = evaluate(lex, bank, exclusions)
    apres = {e.form: e for e in entries}
    if len(apres) != len(entries):
        raise ApresError('grafia repetida a apres.tsv')
    rep = report(entries, discards, frequent, bank, lex, apres)
    return lex, bank, entries, contexts, rep


def write(out_dir: Path, entries: list[Entry]) -> Path:
    path = out_dir / 'apres.tsv'
    tsv.write_tsv(path, HEADER, [(e.key, e.form, e.lemma, e.kind, e.rarity)
                                 for e in sorted(entries, key=lambda e: (e.key, e.form))])
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Genera apres.tsv («Has après»)')
    ap.add_argument('--out-dir', type=Path, default=config.LEXICON_DIR)
    ap.add_argument('--puzzles-dir', type=Path, default=PUZZLES_DIR)
    ap.add_argument('--exclusions', type=Path, default=EXCLUSIONS)
    ap.add_argument('--report', type=Path, default=REPORT)
    ap.add_argument('--todo', action='store_true',
                    help='mostra les files de revisió que falten o sobren (no escriu res)')
    a = ap.parse_args(argv)
    try:
        lex, _, entries, contexts, rep = build(a.out_dir, a.puzzles_dir, a.exclusions)
    except ApresError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1
    if a.todo:
        want = review_rows(entries, contexts, lex)
        have = {(r[0], r[1]): r for _, r in read_reviews()} if REVIEWS.exists() else {}
        for form, ctx, clue in want:
            r = have.get((form, ctx))
            if r is None or r[3] != clue:
                e = next(x for x in entries if x.form == form)
                print('\t'.join((form, ctx, clue, e.kind, e.lemma, str(e.rarity))))
        wanted = {(f, c) for f, c, _ in want}
        for k in sorted(set(have) - wanted):
            print(f'SOBRA\t{k[0]}\t{k[1]}', file=sys.stderr)
        return 0
    path = write(a.out_dir, entries)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {b: f'{v["with_card"]}/{v["puzzles"]}' for b, v in rep['banks'].items()}
    print(f'[apres] {path.name}: {len(entries)} grafies; amb targeta {summary}; '
          f'descarts {rep["discards"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
