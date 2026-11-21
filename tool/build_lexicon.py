#!/usr/bin/env python3
"""Genera la llista blanca i les candidates a solució (spec lexicon-whitelist).

Sortides:
  assets/lexicon/accepted.tsv   clau[\\tgrafia|grafia…] per a cada clau acceptada (3–9 tokens)
  assets/lexicon/solutions.tsv  candidates a solució amb freqüència, rang i banda

Criteri normatiu: forma del diccionari LT de Softcatalà ∩ expansió del Hunspell general,
sense FORBIDDENWORD, sense etiquetes NP/Y/Z/F, fora d'exclusions.txt (TOTS i catalan),
variant verbal general/central. Les claus amb alguna forma `absolute` de la llista negra
no s'accepten; les candidates exclouen qualsevol nivell de la llista negra.

Ús: python3 -I tool/build_lexicon.py [--dict-tools DIR] [--blacklist FITXER] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lexlib import config, tsv  # noqa: E402
from lexlib import normalize as N  # noqa: E402
from lexlib import softcatala as SC  # noqa: E402

MIN_TOKENS, MAX_TOKENS = 3, 9
MIN_FREQ = 5
TERMINOLOGY_SOURCES = frozenset({'dsalut', 'UB', 'wiki'})
TERMINOLOGY_MIN_FREQ = 100
BANDS = ((1, 5000), (2, 12000), (3, 20000), (4, 25000), (5, 40000))
MAX_RANK = BANDS[-1][1]
KIND_ORDER = ('lemma', 'plural', 'femeni', 'femeni_plural')
POS_ORDER = ('S', 'C', 'D', 'P', 'V', 'N', 'A', 'R', 'I')
SOLUTIONS_HEADER = ('key', 'form', 'lemma', 'kind', 'pos', 'freq', 'rank', 'band', 'lemmas',
                    'verbs')
# `lemma` és l'atribució principal (la que dona `kind` i la pista); `lemmas` són TOTS els
# lemes possibles de la forma al diccionari LT (de qualsevol categoria i variant
# dialectal, també els verbs de què és una forma conjugada, gerundi o participi:
# `tocant` -> tocar, `toc` -> toc|tocar) i `verbs`, els lemes verbals d'entre aquests.
# El generador els fa servir per no posar al mateix puzle dues formes que comparteixin
# lema (`pobles`/`poble`, `queda`/`quedar`) — QA iteració 3, N3/G2/G4.

# Estrangerismes (D2 de l'informe de QA). Grafies impossibles en un mot català patrimonial
# o adaptat: k, w, y fora del dígraf ny, sh/ck/gh/th/ph/ch, dobles ff/tt/zz/pp/bb, oo, ee,
# finals -ss, -tz, q sense u, finals -ae/-ey/-oy/-ay i -ing sense cap accent (càmping o
# míting són adaptacions). Les excepcions revisades (fronteres de morfema com tot-hom,
# ales-hores, post-terme) són a tool/data/foreign_words.tsv.
FOREIGN_PATTERN = re.compile(
    r'[kw]|(?<!n)y|(?<!de)sh|ck|gh|th|ph|ch|ff|tt|zz|pp|(?<!su)bb|(?<![czrt])oo|'
    r'(?<![rd])ee(?!s$)|ss$|tz$|q(?![uü])|ae$|ey$|oy$|ay$')
ACCENTED = frozenset('àèéíïòóúü')
FOREIGN_SOURCES = frozenset({
    'esadir', 'anglès', 'english', 'English', 'anglicisme', 'italià', 'francès', 'alemany',
    'German', 'castellà', 'japonès', 'rus', 'noruec', 'basc', 'marca'})
BRAND_SOURCES = frozenset({'marca'})
# Anglicismes no adaptats (m5 del QA, iteració 2: `cool`, `online`, `email`): Softcatalà els
# recull amb aquestes fonts però no són al DIEC2; no s'accepten ni com a intent si no
# tenen una revisió manual a foreign_words.tsv (p. ex. `càmper`, DIEC2: sí).
ENGLISH_SOURCES = frozenset({'anglès', 'english', 'English', 'anglicisme'})
# Col·loquialismes no normatius (N2 del QA, iteració 3): Softcatalà recull amb la font
# `col·loquial` (sovint `DNV,col·loquial`) mots que el DIEC2 no admet (`tonto`, `poli`,
# `macarra`, `pasma`, `farra`, `cubata`, `químio`…). No s'accepten ni com a intent si no
# tenen una revisió manual a foreign_words.tsv (`canyer`, DIEC2: sí -> allow).
COLLOQUIAL_SOURCES = frozenset({'col·loquial', 'colloquial'})
FOREIGN_ACTIONS = ('allow', 'accept', 'no_solution', 'reject')
FOREIGN_HEADER = ['lemma', 'action', 'reason']
# Homògrafs de noms propis (D4): si la forma coincideix amb un antropònim o topònim del
# diccionari LT i la seva freqüència supera PROPER_RATIO vegades la de la forma germana
# més freqüent del mateix lema, el recompte prové sobretot del nom propi.
PROPER_RATIO = 10
# Homògrafs de noms propis per sota del llindar (m3 del QA, iteració 2: `figueres`, `reus`,
# `terrassa`): per al rànquing, la freqüència es limita a PROPER_CAP_LEMMA vegades la de la
# germana més freqüent si la forma és el lema, i a la de la germana més freqüent si és una
# flexió (un plural rarament és més freqüent que el singular). La columna `freq` de
# solutions.tsv conserva la freqüència real.
PROPER_CAP_LEMMA = 2
PROPER_ACTIONS = ('keep', 'exclude')
PROPER_HEADER = ['form', 'action', 'reason']
# Lemes retirats com a solució (canvi retirar-solucions-dubtoses): normatius i acceptats com
# a intent, però rars o enganyosos per a un jugador general. No són sensibles (no van a la
# llista negra) ni estrangers. S'apliquen DESPRÉS del rànquing: el lema i totes les
# flexions que hi tenen l'atribució principal (`lemma`) surten de solutions.tsv sense
# desplaçar el rang ni la banda de cap altra candidata (els rangs queden amb forats), de
# manera que els puzles que no les fan servir no canvien.
SOLUTION_EXCLUSION_ACTIONS = ('no_solution',)
SOLUTION_EXCLUSION_HEADER = ['lemma', 'action', 'reason']


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    key: str
    form: str
    lemma: str
    kind: str
    pos: str
    freq: int
    rank_freq: int | None = None  # freqüència per al rànquing (None = freq)
    lemmas: tuple[str, ...] = ()  # tots els lemes possibles (buit = només `lemma`)
    verbs: tuple[str, ...] = ()   # lemes verbals d'entre `lemmas`

    @property
    def all_lemmas(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.lemmas) | {self.lemma}))

    @property
    def ranking_freq(self) -> int:
        return self.freq if self.rank_freq is None else self.rank_freq


@dataclass
class Lexicon:
    normative: dict[str, set[tuple[str, str]]]   # forma -> {(lema, etiqueta)}
    accepted: dict[str, list[str]]               # clau -> grafies ordenades
    rejections: collections.Counter


def band_for_rank(rank: int) -> int | None:
    for band, limit in BANDS:
        if rank <= limit:
            return band
    return None


def pos_of(tag: str) -> str | None:
    """Etiqueta EAGLES -> pos de la candidata (D5)."""
    if tag.startswith('NC'):
        return 'N'
    if tag.startswith(('AQ', 'AO')):
        return 'A'
    c = tag[:1]
    return c if c in ('V', 'R', 'P', 'D', 'S', 'C', 'I') else None


def _gender_number(tag: str) -> tuple[str, str]:
    if tag.startswith('N'):
        return tag[2:3], tag[3:4]
    return tag[3:4], tag[4:5]  # adjectius: AQ0FS0


def normative_forms(entries: Iterable[SC.LtEntry], hunspell: set[str], ex_forms: set[str],
                    ex_lemmas: set[str]):
    """Aplica el criteri normatiu. Retorna (formes normatives, gèneres dels lemes, rebutjos)."""
    norm: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
    lemma_genders: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    rej: collections.Counter = collections.Counter()
    nfc_mismatch = []
    for e in entries:
        if e.form == e.lemma and e.tag[:1] in ('N', 'A'):
            lemma_genders[(e.lemma, e.tag[:1])].add(_gender_number(e.tag)[0])
        if SC.is_excluded_tag(e.tag):
            rej['etiqueta_np_y_z_f'] += 1
            continue
        if e.form in ex_forms or e.lemma in ex_lemmas:
            rej['exclusions_softcatala'] += 1
            continue
        if not SC.is_general_tag(e.tag):
            rej['verb_no_general'] += 1
            continue
        canon = N.canonicalize(e.form)
        if canon is not None and canon != unicodedata.normalize('NFC', e.form).lower():
            nfc_mismatch.append(e.form)
        if canon != e.form:
            rej['grafia_no_simple'] += 1
            continue
        if e.form not in hunspell:
            rej['absent_hunspell_general'] += 1
            continue
        norm[e.form].add((e.lemma, e.tag))
    if nfc_mismatch:
        raise BuildError(f'la normalització difereix de NFC per a: {nfc_mismatch[:20]}')
    return dict(norm), lemma_genders, rej


def accepted_keys(norm: dict[str, set], absolute_keys: set[str]):
    accepted: dict[str, set[str]] = collections.defaultdict(set)
    rej: collections.Counter = collections.Counter()
    for form in norm:
        key = N.grid_key(form)
        if not MIN_TOKENS <= len(key) <= MAX_TOKENS:
            rej['longitud_fora_3_9'] += 1
            continue
        if key in absolute_keys:
            rej['llista_negra_absolute'] += 1
            continue
        accepted[key].add(form)
    return {k: sorted(v) for k, v in accepted.items()}, rej


def accepted_lines(accepted: dict[str, list[str]]) -> list[str]:
    lines = []
    for key in sorted(accepted):
        sp = accepted[key]
        lines.append(key if sp == [N.trivial_spelling(key)] else key + '\t' + '|'.join(sp))
    return lines


def classify(form: str, analyses: set[tuple[str, str]], norm: dict, lemma_genders,
             freq: dict[str, int] | None = None):
    """Millor anàlisi candidata (kind, pos, lema) d'una forma, o None.

    Si la forma és ella mateixa un lema, té preferència (`des` és la preposició, no el
    plural de la lletra «de»). Si no, entre les flexions possibles es tria la del lema més
    freqüent (freqüència de la forma de citació del lema), de manera que `pobles`
    s'atribueix a `poble` i no a `pobla`, `espècies` a `espècie` i no a `espècia` i
    `negres` a `negre` i no a `negra` (QA iteració 3, N3). En cas d'empat, l'ordre és el de
    sempre: tipus (plural, femení…), categoria i lema alfabètic. Tots els lemes possibles
    es conserven a part (`form_lemmas`)."""
    freq = freq or {}
    options = []
    for lemma, tag in analyses:
        pos = pos_of(tag)
        if pos is None or lemma not in norm:
            continue
        if form == lemma:
            if pos == 'V' and tag[2:3] != 'N':
                continue  # només l'infinitiu com a lema verbal
            kind = 'lemma'
        elif pos in ('N', 'A'):
            gender, number = _gender_number(tag)
            genders = lemma_genders.get((lemma, tag[0]), set())
            fem = gender == 'F' and bool(genders) and 'F' not in genders
            if number == 'P':
                kind = 'femeni_plural' if fem else 'plural'
            elif fem:
                kind = 'femeni'
            else:
                continue
        else:
            continue
        self_lemma = kind == 'lemma'
        options.append((0 if self_lemma else 1, 0 if self_lemma else -freq.get(lemma, 0),
                        KIND_ORDER.index(kind), POS_ORDER.index(pos), lemma, kind, pos))
    if not options:
        return None
    *_, lemma, kind, pos = min(options)
    return kind, pos, lemma


def form_lemmas(analyses: set[tuple[str, str]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(tots els lemes, lemes verbals) de les anàlisis normatives d'una forma."""
    lemmas = sorted({lm for lm, _ in analyses})
    verbs = sorted({lm for lm, tag in analyses if tag.startswith('V')})
    return tuple(lemmas), tuple(verbs)


def candidates(norm, lemma_genders, accepted, blacklist_keys, blacklist_forms, freq,
               sources, foreign: ForeignPolicy | None = None,
               proper_forms: set[str] = frozenset(), proper_manual: dict[str, str] | None = None,
               lt_forms_of: dict[str, set[str]] | None = None,
               lt_analyses: dict[str, set[tuple[str, str]]] | None = None,
               ) -> tuple[list[tuple[Candidate, int, int]], collections.Counter]:
    rej: collections.Counter = collections.Counter()
    proper_manual = proper_manual or {}
    lt_forms_of = lt_forms_of or {}
    lt_analyses = lt_analyses or {}
    cands: list[Candidate] = []
    for form in sorted(norm):
        key = N.grid_key(form)
        if key not in accepted:
            continue
        cl = classify(form, norm[form], norm, lemma_genders, freq)
        if cl is None:
            rej['no_lema_ni_flexio_nominal'] += 1
            continue
        kind, pos, lemma = cl
        if key in blacklist_keys or form in blacklist_forms or lemma in blacklist_forms:
            rej['llista_negra'] += 1
            continue
        f = freq.get(form, 0)
        if f < MIN_FREQ:
            rej['freq_menor_5'] += 1
            continue
        src = sources.get(lemma, set())
        if src and src <= TERMINOLOGY_SOURCES and f < TERMINOLOGY_MIN_FREQ:
            rej['terminologia_poc_frequent'] += 1
            continue
        if foreign is not None and foreign.no_solution(form, lemma):
            rej['estranger_o_grafia_no_catalana'] += 1
            continue
        pm = proper_manual.get(form)
        if pm == 'exclude' or (pm is None and pos in ('N', 'A') and form in proper_forms
                               and proper_dominated(form, lemma, freq,
                                                    lt_forms_of.get(lemma, set()))):
            rej['homograf_nom_propi'] += 1
            continue
        rank_f = None
        if pm is None and pos in ('N', 'A') and form in proper_forms:
            rank_f = proper_capped_freq(form, lemma, freq, lt_forms_of.get(lemma, set()))
            if rank_f < f:
                rej['info_homograf_nom_propi_rebaixat'] += 1
        lemmas, verbs = form_lemmas(norm[form] | lt_analyses.get(form, set()))
        cands.append(Candidate(key, form, lemma, kind, pos, f, rank_f, lemmas, verbs))
    return rank_candidates(cands, rej)


def rank_candidates(cands: list[Candidate], rej: collections.Counter | None = None,
                    max_rank: int = MAX_RANK):
    rej = rej if rej is not None else collections.Counter()
    ordered = sorted(cands, key=lambda c: (-c.ranking_freq, c.key, c.form))
    out = []
    for i, c in enumerate(ordered, start=1):
        if i > max_rank:
            rej['rang_superior_40000'] += 1
            continue
        out.append((c, i, band_for_rank(i)))
    return out, rej


def drop_excluded_solutions(ranked, excluded: dict[str, str], rej: collections.Counter):
    """Treu les candidates retirades (lema o grafia a `excluded`) conservant els rangs."""
    out = []
    for c, rank, band in ranked:
        if c.lemma in excluded or c.form in excluded:
            rej['exclusio_solucio_manual'] += 1
            continue
        out.append((c, rank, band))
    return out


def check_solutions(ranked, accepted, blacklist_keys, blacklist_forms) -> None:
    errors = []
    for c, rank, band in ranked:
        if N.grid_key(c.form) != c.key:
            errors.append(f'{c.form}: clau incoherent')
        if c.form not in accepted.get(c.key, ()):
            errors.append(f'{c.form}: no és a la llista blanca')
        if c.key in blacklist_keys or c.form in blacklist_forms:
            errors.append(f'{c.form}: és a la llista negra')
        if band != band_for_rank(rank) or band is None:
            errors.append(f'{c.form}: banda incoherent')
    if errors:
        raise BuildError('candidates invàlides: ' + '; '.join(errors[:20]))


def foreign_pattern(form: str) -> str | None:
    """Seqüència gràfica no catalana de la forma, o None."""
    m = FOREIGN_PATTERN.search(form)
    if m:
        return m.group(0)
    if form.endswith('ing') and not ACCENTED.intersection(form):
        return 'ing'
    return None


def load_actions(path: Path | None, header: list[str], actions: tuple[str, ...]):
    """Fitxer manual `paraula\tacció\tmotiu` -> {paraula: acció}."""
    if path is None or not path.exists():
        return {}
    got, rows = tsv.read_tsv(path)
    if got != header:
        raise BuildError(f'{path}: capçalera inesperada {got}')
    out: dict[str, str] = {}
    for n, row in enumerate(rows, start=2):
        if not row or row == [''] or row[0].startswith('#'):
            continue
        if len(row) != 3 or not row[2].strip():
            raise BuildError(f'{path}:{n}: calen 3 columnes i motiu: {row}')
        word, action = row[0].strip(), row[1].strip()
        if action not in actions:
            raise BuildError(f'{path}:{n}: acció desconeguda {action!r}')
        if N.canonicalize(word) != word:
            raise BuildError(f'{path}:{n}: «{word}» no és una grafia canònica')
        if word in out:
            raise BuildError(f'{path}:{n}: «{word}» duplicada')
        out[word] = action
    return out


@dataclass
class ForeignPolicy:
    sources: dict[str, set[str]]
    # lema -> allow (català, pot ser solució) | accept (normatiu segons el DIEC2 però amb
    # grafia estrangera: intent vàlid, mai solució) | no_solution | reject
    manual: dict[str, str]

    def rejected(self, lemma: str) -> str | None:
        """Motiu per no acceptar el lema ni com a intent (manlleu no normatiu o marca)."""
        action = self.manual.get(lemma)
        if action == 'reject':
            return 'estranger_manual'
        if action is not None:
            return None
        if self.sources.get(lemma, set()) & BRAND_SOURCES:
            return 'marca_comercial'
        if self.sources.get(lemma, set()) & ENGLISH_SOURCES:
            return 'anglicisme_no_normatiu'
        if self.sources.get(lemma, set()) & COLLOQUIAL_SOURCES:
            return 'col·loquial_no_normatiu'
        if foreign_pattern(lemma):
            return 'grafia_no_catalana'
        return None

    def no_solution(self, form: str, lemma: str) -> bool:
        """Cert si la candidata té grafia o font estrangera i no s'ha revisat com a català."""
        action = self.manual.get(lemma)
        if action == 'allow':
            return False
        return bool(action in ('accept', 'no_solution') or foreign_pattern(form)
                    or foreign_pattern(lemma)
                    or self.sources.get(lemma, set()) & FOREIGN_SOURCES)


def proper_noun_forms(entries: Iterable[SC.LtEntry]) -> set[str]:
    """Grafies canòniques d'antropònims (NP..SP) i topònims (NP..G) del diccionari LT."""
    out = set()
    for e in entries:
        if e.tag.startswith('NP') and e.tag[4:5] in ('S', 'G'):
            c = N.canonicalize(e.form)
            if c is not None:
                out.add(c)
    return out


def proper_dominated(form: str, lemma: str, freq: dict[str, int], siblings: set[str]) -> bool:
    """Cert si la freqüència de la forma és PROPER_RATIO vegades la de la germana més
    freqüent (o no en té cap): el recompte prové del nom propi homògraf."""
    best = max((freq.get(f, 0) for f in siblings if f != form), default=0)
    return freq.get(form, 0) >= PROPER_RATIO * max(best, 1)


def proper_capped_freq(form: str, lemma: str, freq: dict[str, int],
                       siblings: set[str]) -> int:
    """Freqüència de rànquing d'un homògraf de nom propi (vegeu PROPER_CAP_LEMMA)."""
    f = freq.get(form, 0)
    best = max((freq.get(x, 0) for x in siblings if x != form), default=0)
    if best == 0:
        return f
    return min(f, PROPER_CAP_LEMMA * best if form == lemma else best)


def read_blacklist(path: Path):
    header, rows = tsv.read_tsv(path)
    if header != ['key', 'form', 'level', 'reason']:
        raise BuildError(f'{path}: capçalera inesperada {header}')
    return [dict(zip(header, r)) for r in rows]


def drop_rejected_lemmas(norm: dict[str, set[tuple[str, str]]], foreign: ForeignPolicy,
                         rej: collections.Counter) -> dict[str, set[tuple[str, str]]]:
    """Treu les anàlisis de lemes estrangers no normatius; la forma només desapareix si no
    li queda cap anàlisi d'un altre lema."""
    out = {}
    for form, analyses in norm.items():
        keep = set()
        for lemma, tag in analyses:
            reason = foreign.rejected(lemma)
            if reason is None:
                keep.add((lemma, tag))
            else:
                rej[reason] += 1
        if keep:
            out[form] = keep
    return out


def build(dt: SC.DictToolsPaths, blacklist_path: Path, out_dir: Path,
          foreign_path: Path | None = None, proper_path: Path | None = None,
          solution_exclusions_path: Path | None = None) -> dict:
    ex_forms, ex_lemmas = SC.load_exclusions(dt.exclusions)
    hunspell, _ = SC.expand_hunspell(dt.hunspell_dic, dt.hunspell_aff)
    lt = list(SC.iter_lt(dt.lt_dictionary))
    norm, lemma_genders, rej = normative_forms(lt, hunspell, ex_forms, ex_lemmas)
    sources = SC.lemma_sources(dt.arrel)
    foreign_manual = load_actions(foreign_path, FOREIGN_HEADER, FOREIGN_ACTIONS)
    lt_lemmas = {e.lemma for e in lt if not SC.is_excluded_tag(e.tag)}
    unknown = sorted(set(foreign_manual) - lt_lemmas)
    if unknown:
        raise BuildError(f'{foreign_path}: lemes absents del diccionari LT: {unknown}')
    foreign = ForeignPolicy(sources, foreign_manual)
    norm = drop_rejected_lemmas(norm, foreign, rej)
    lt_forms_of: dict[str, set[str]] = collections.defaultdict(set)
    lt_analyses: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
    for e in lt:
        if not SC.is_excluded_tag(e.tag):
            lt_forms_of[e.lemma].add(e.form)
            lt_analyses[e.form].add((e.lemma, e.tag))
    bl = read_blacklist(blacklist_path)
    absolute_keys = {r['key'] for r in bl if r['level'] == 'absolute'}
    bl_keys = {r['key'] for r in bl}
    bl_forms = {r['form'] for r in bl}
    accepted, rej2 = accepted_keys(norm, absolute_keys)
    rej.update(rej2)
    ranked, rej3 = candidates(norm, lemma_genders, accepted, bl_keys, bl_forms,
                              SC.load_frequencies(dt.freq_forms), sources, foreign,
                              proper_noun_forms(lt),
                              load_actions(proper_path, PROPER_HEADER, PROPER_ACTIONS),
                              lt_forms_of, lt_analyses)
    excluded = load_actions(solution_exclusions_path, SOLUTION_EXCLUSION_HEADER,
                            SOLUTION_EXCLUSION_ACTIONS)
    unknown = sorted(set(excluded) - lt_lemmas)
    if unknown:
        raise BuildError(f'{solution_exclusions_path}: lemes absents del diccionari LT: {unknown}')
    ranked = drop_excluded_solutions(ranked, excluded, rej3)
    check_solutions(ranked, accepted, bl_keys, bl_forms)
    tsv.write_lines(out_dir / 'accepted.tsv', accepted_lines(accepted))
    tsv.write_tsv(out_dir / 'solutions.tsv', SOLUTIONS_HEADER,
                  [(c.key, c.form, c.lemma, c.kind, c.pos, c.freq, r, b, '|'.join(c.all_lemmas),
                    '|'.join(c.verbs)) for c, r, b in ranked])
    return {
        'normative_forms': len(norm),
        'accepted_keys': len(accepted),
        'accepted_forms': sum(len(v) for v in accepted.values()),
        'solutions': len(ranked),
        'solutions_by_band': dict(sorted(collections.Counter(b for _, _, b in ranked).items())),
        'whitelist_rejections': dict(sorted(rej.items())),
        'candidate_rejections': dict(sorted(rej3.items())),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Genera la llista blanca i les candidates')
    ap.add_argument('--dict-tools', type=Path)
    ap.add_argument('--blacklist', type=Path)
    ap.add_argument('--foreign', type=Path, default=config.DATA_DIR / 'foreign_words.tsv')
    ap.add_argument('--proper', type=Path, default=config.DATA_DIR / 'proper_nouns.tsv')
    ap.add_argument('--solution-exclusions', type=Path,
                    default=config.DATA_DIR / 'solution_exclusions.tsv')
    ap.add_argument('--out-dir', type=Path, default=config.LEXICON_DIR)
    a = ap.parse_args(argv)
    dt = SC.DictToolsPaths(a.dict_tools) if a.dict_tools else config.default_dict_tools()
    try:
        stats = build(dt, a.blacklist or a.out_dir / 'blacklist.tsv', a.out_dir,
                      a.foreign, a.proper, a.solution_exclusions)
    except BuildError as e:
        raise SystemExit(f'ERROR: {e}') from None
    for k, v in stats.items():
        print(f'[lexicon] {k}: {v}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
