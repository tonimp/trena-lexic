#!/usr/bin/env python3
"""Genera assets/lexicon/clues.tsv a partir del Viquidiccionari (spec lexicon-clues).

Per a cada candidata de solutions.tsv tria la primera accepció catalana vàlida de la
pàgina de la forma o del seu lema, la neteja (text pla, 8–80 caràcters) i la descarta si
revela la paraula o la seva arrel, o si conté paraules vetades o fora del lèxic normatiu.
Les pistes de formes flexionades sense pista pròpia reutilitzen la del lema amb el prefix
«(plural) », «(femení) » o «(femení plural) ».

Llicència de la sortida: CC BY-SA 4.0 (Viquidiccionari, col·laboradors del Viquidiccionari).

Ús: python3 -I tool/build_clues.py [--dict-tools DIR] [--dump FITXER] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_lexicon as L  # noqa: E402
from lexlib import config, tsv  # noqa: E402
from lexlib import normalize as N  # noqa: E402
from lexlib import softcatala as SC  # noqa: E402
from lexlib import wiktionary as W  # noqa: E402

HEADER = ('key', 'form', 'lemma', 'clue', 'source')
MIN_LEN, MAX_LEN = 8, 80
PREFIX = {'plural': '(plural) ', 'femeni': '(femení) ', 'femeni_plural': '(femení plural) '}

# Marques que invaliden una accepció com a pista (dialectals, de registre, arcaiques,
# manlleus i ofensives). Inclou les de la spec i altres variants dialectals.
SKIP_MARKS = frozenset({
    'balear', 'valencià', 'alguerès', 'col·loquial', 'arcaic', 'antic', 'obsolet',
    'castellanisme', 'vulgar', 'vulgarisme', 'despectiu', 'pejoratiu', 'ofensiu', 'sexual',
    'sexualitat', 'mallorquí', 'menorquí', 'eivissenc', 'septentrional', 'nord-occidental',
    'occidental', 'tortosí', 'tarragoní', 'rossellonès', 'ribagorçà', 'pallarès', 'dialectal',
    'anglicisme', 'gal·licisme', 'italianisme', 'barbarisme', 'argot', 'infantil', 'desusat',
    'en desús', 'rar', 'poc usat', 'baleàric', 'nord-català', 'lleidatà', 'apitxat',
    'figurat', 'figuradament', 'per extensió',
})
# Referències a altres accepcions o paraules: la pista no s'entén sola.
ANAPHORA = re.compile(r'\b(homònim|homònima|accepció|anterior|esmentat|esmentada)\b', re.I)
REMISSION = re.compile(
    r'^(variant|vegeu|forma|plural|femen[ií]|masculí|grafia|sinònim|abreviatura|sigla|'
    r'símbol|participi|gerundi|infinitiu|antònim|diminutiu|augmentatiu|superlatiu)\b', re.I)
# Plantilles que es poden eliminar o reduir al seu text; qualsevol altra descarta l'accepció.
_DROP_TEMPLATES = re.compile(r'\{\{\s*(q|g|categoritza|ca-sil)\s*(\|[^{}]*)?\}\}')
_TEXT_TEMPLATES = re.compile(r'\{\{\s*(w|m|e-propi)\s*\|([^{}]*)\}\}')
_REF = re.compile(r'<ref[^>/]*/>|<ref[^>]*>.*?</ref>', re.S | re.I)
_TAG = re.compile(r'<[^>]+>')
_ENTITY = re.compile(r'&[a-z]+;|&#\d+;')
_MARCA = re.compile(r'\{\{marca(?:-nocat)?\|[^{}]*\}\}')
_LINK = re.compile(r'\[\[([^\[\]|]*)(?:\|([^\[\]]*))?\]\]')
_PARENS = re.compile(r'\s*\([^()]*\)')
_FORBIDDEN_CHARS = re.compile(r'[\[\]{}|=<>]')
_ETC = re.compile(r',?\s*\betc\.?\s*$')  # «…, etc.» final: s'elimina (abreviatura)
# Paraules d'una pista per al filtre (idèntic a test/lexicon_test.dart).
WORD = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿĿŀ·]+')


@dataclass(frozen=True)
class ClueRow:
    key: str
    form: str
    lemma: str
    clue: str
    source: str


def _text_template(m: re.Match) -> str:
    params = [p for p in m.group(2).split('|') if '=' not in p]
    if m.group(1) in ('m', 'e-propi') and params and params[0] == 'ca':
        params = params[1:]
    return params[-1] if params else ''


def _link(m: re.Match) -> str:
    target, text = m.group(1), m.group(2)
    if ':' in target:
        return '\x00'  # fitxers, categories, interviquis: invàlid
    return text if text is not None else target


def clean_sense(text: str) -> str | None:
    """Accepció en wikitext -> text pla (sense límit de longitud), o None si l'accepció no
    és seleccionable (plantilles no reduïbles, remissions, fitxers)."""
    s = _REF.sub('', text)
    s = _MARCA.sub('', s)
    s = _DROP_TEMPLATES.sub('', s)
    s = _TEXT_TEMPLATES.sub(_text_template, s)
    if '{{' in s or '}}' in s:
        return None
    s = _LINK.sub(_link, s)
    if '\x00' in s:
        return None
    s = _TAG.sub('', s)
    s = _ENTITY.sub(' ', s)
    s = s.replace("'''", '').replace("''", '')
    s = _PARENS.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\s+([,.;:])', r'\1', s)
    s = _ETC.sub('', s).strip(' .;:,')
    if not s or REMISSION.match(s) or s.lower().startswith(('per extensió', 'figuradament')):
        return None
    return s[0].upper() + s[1:]


# Retall per oració (ampliacio-pistes D2): límits on una definició llarga es pot tallar
# sense canviar-ne el sentit (el gènere i la primera diferència: «Mamífer de la família
# dels suids, d’estatura baixa…» -> «Mamífer de la família dels suids»).
CLAUSE_BOUNDARY = re.compile(r'\. |, | que | on | i que | el qual | la qual | els quals | les quals ')
MIN_CLAUSE = 20
# Paraules gramaticals amb què no pot acabar un retall («Objecte format per»).
DANGLING = frozenset(
    'a al als amb de del dels d en el els la les l i o ni per pel pels que com sense sobre '
    'sota entre fins cap un una uns unes seu seva seus seves molt més menys tan tant '
    # antecedents que demanen la subordinada («de manera que», «allò que», «en el moment
    # que»)
    'allò això aquell aquella aquells aquelles manera mode moment punt fet cas tal així '
    'abans després mentre ja sempre tot tota tots totes cosa coses quan on qual '
    'mitjançant segons durant contra vers envers des excepte llevat tret destinat destinada '
    'dedicat dedicada no però sinó si ni quan fi'.split())
# Comparatius que demanen el segon terme («molt més llarga que…», «la meitat que…»).
COMPARATIVE = frozenset('més menys tan tant millor pitjor major menor doble meitat '
                        'mateix mateixa altre altra'.split())
# Inicis de definició que fan de context i no es poden separar de la resta («En un
# castell de tres o cinc, …», «Qualsevol dels elements, …»).
CONTEXT_START = re.compile(r'^(En|A|Al|Als|Dins|Segons|Per|Amb|Qualsevol|Cadascun|Cadascuna|'
                           r'Cada|Antigament|Especialment|Generalment)\b')


_INFINITIVE = re.compile(r'(ar|er|ir|re)$')


def clause_cut(text: str, verb_forms: set[str] | frozenset[str] = frozenset(),
               nominal_forms: set[str] | frozenset[str] = frozenset()) -> str | None:
    """Primer tros de 20–80 caràcters acabat abans d’un límit d’oració (`CLAUSE_BOUNDARY`).
    Si el límit no és un punt, el tros no pot tenir cometes obertes ni «:», ni acabar en
    paraula gramatical o en un infinitiu que no sigui també nom o adjectiu
    (`nominal_forms`: «circular» sí, «fabricar» no), ni deixar un comparatiu sense segon
    terme o una relativa «que» sense cap verb (`verb_forms`); None si no n’hi ha cap."""
    if CONTEXT_START.match(text):
        return None
    fallback = None  # tall just abans d’una enumeració, si no n’hi ha cap de millor
    for m in CLAUSE_BOUNDARY.finditer(text):
        head = text[:m.start()].rstrip(' ,;:')
        if len(head) > MAX_LEN:
            return fallback
        if len(head) < MIN_CLAUSE:
            continue
        if m.group(0) == '. ':
            return head  # fi de frase: la primera frase és completa
        last = re.split(r"[\s’']", head)[-1].lower()
        tail = {w.lower() for w in head.split()[-3:]}
        if (last in DANGLING or head.count('«') != head.count('»') or ':' in head
                or len(head.split()) < 3 or (m.group(0) == ' que ' and tail & COMPARATIVE)
                or 'que,' in head or (last in verb_forms and last not in nominal_forms
                                      and _INFINITIVE.search(last))
                or (text.startswith('Dit ') and ' que ' not in head)
                or ('entre' in tail and not {'i', 'o'} & set(head.split()[-2:]) and
                    ' i ' not in head.rsplit('entre', 1)[1])
                or (head.split()[-2:-1] == ['que'] and last in verb_forms
                    and last not in nominal_forms)):
            continue
        if verb_forms and ' que ' in f' {head} ':
            rel = f' {head} '.rsplit(' que ', 1)[1]
            if not any(w.lower() in verb_forms for w in re.split(r"[\s’',]+", rel)):
                continue  # «Dany que una malaltia»
        if m.group(0) == ', ' and {'i', 'o', 'ni'} & set(text[m.end():].split()[:2]):
            # enumeració («de pare, mare o tots dos»): millor incloure-la si hi cap
            fallback = fallback or head
            continue
        return head
    return fallback


def shorten(text: str, cut: bool = False,
            verb_forms: set[str] | frozenset[str] = frozenset(),
            nominal_forms: set[str] | frozenset[str] = frozenset()) -> str | None:
    """Aplica el límit de 8–80 caràcters: retalla pel primer «;» i, amb `cut` (passada de
    recuperació), si encara és massa llarga, pel primer límit d’oració (`clause_cut`)."""
    s = text
    if len(s) > MAX_LEN and ';' in s:
        s = s.split(';', 1)[0].strip(' .;:,')
    if len(s) > MAX_LEN:
        s = clause_cut(s, verb_forms, nominal_forms) if cut else None
        if s is None:
            return None
    if not MIN_LEN <= len(s) <= MAX_LEN or _FORBIDDEN_CHARS.search(s):
        return None
    return s


def root_of(key: str) -> str:
    n = len(key)
    if n >= 6:
        return key[:-2]
    if n >= 4:
        return key[:-1]
    return key


def clue_words(clue: str) -> list[str]:
    return [w.strip('·') for w in WORD.findall(clue) if w.strip('·')]


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


# Prefixos que no han d'amagar l'arrel (il·legal/legal, renebot/besnebot, instaurar/restaurar).
# El mateix conjunt és a test/support/lexicon_integrity.dart.
REVEAL_PREFIXES = ('BES', 'CONTRA', 'SOBRE', 'ANTI', 'DES', 'DIS', 'IL', 'IM', 'IN', 'IR',
                   'RE', 'EM', 'EN', 'DE', 'PRE', 'SUB')
MIN_CORE = 5


def letters(key: str) -> str:
    """Clau -> lletres de comparació: el token L·L compta com a dues L i Ç com a C."""
    return key.replace(N.KEY_LL, 'LL').replace('Ç', 'C')


def cores(key: str) -> set[str]:
    """Lletres de la clau i, si en té, la clau sense un prefix (amb ≥ MIN_CORE lletres)."""
    k = letters(key)
    out = {k}
    for p in REVEAL_PREFIXES:
        if k.startswith(p) and len(k) - len(p) >= MIN_CORE:
            out.add(k[len(p):])
    return out


def _common_suffix(a: str, b: str) -> int:
    return _common_prefix(a[::-1], b[::-1])


def basic_reveal(word_key: str, lemma_key: str, forbidden: set[str]) -> bool:
    """Regla compartida amb el test Dart: clau prohibida (forma, lema o formes del lema), o
    paraula que comença per l'arrel del lema, comparant també per lletres i sense prefixos."""
    if word_key in forbidden or word_key.startswith(root_of(lemma_key)):
        return True
    for wc in cores(word_key):
        for lc in cores(lemma_key):
            if wc == lc or wc.startswith(root_of(lc)) or lc.startswith(root_of(wc)) and \
                    len(wc) >= MIN_CORE:
                return True
    return False


def reveals(clue: str, form: str, lemma: str, lemma_forms: set[str],
            strict: bool = True) -> str | None:
    """Paraula de la pista que revela la resposta, o None.

    Regla de la spec (`basic_reveal`): clau igual a la de la forma, el lema o qualsevol
    forma del lema, o que comenci per l'arrel del lema; també comparant per lletres
    (L·L = LL, Ç = C) i després de treure un prefix (il·legal/legal, renebot/besnebot).
    Amb `strict` (per defecte en el build) també es descarten les paraules que:
    comparteixen ≥ 4 lletres inicials amb el lema (`armar`/`armament`); tenen les 4
    primeres lletres dins del lema (`ajustar`/`reajustar`); contenen el lema sencer;
    comparteixen 3 lletres inicials i la més curta en té com a molt 5 (`ordre`/`ordenar`);
    o comparteixen un final de ≥ max(5, longitud − 3) lletres (`emprendre`/`reprendre`).
    """
    forbidden = {N.grid_key(x) for x in ({form, lemma} | lemma_forms)} - {None}
    lk = N.grid_key(lemma)
    for w in clue_words(clue):
        k = N.grid_key(w)
        if k is None:
            continue
        if basic_reveal(k, lk, forbidden):
            return w
        if strict:
            fk, fl = letters(k), letters(lk)
            cp = _common_prefix(fk, fl)
            short = min(len(fk), len(fl))
            if (cp >= 4 or (len(fk) >= 4 and fk[:4] in fl) or (len(fl) >= 4 and fl in fk)
                    or (cp >= 3 and len(fk) >= 4 and len(fl) >= 4 and short <= 5)
                    or (short >= 5 and _common_suffix(fk, fl) >= max(5, len(fl) - 3))):
                return w
    return None


# Pronoms febles enclítics («fer-lo», «treure’n», «posar-s’hi»): no són formes soltes del
# lèxic i no s’han de comprovar com a paraules (ampliacio-pistes D2).
HYPHEN_CLITICS = re.compile(
    r"(?:-(?:los|les|lo|la|li|hi|ho|ne|en|nos|vos|us|me|te|se|m|t|s|n|l)(?![A-Za-zÀ-ÿ·])"
    r"|[’'](?:hi|ho|n|l|m|t|s|en|ls|ns)(?![A-Za-zÀ-ÿ·]))+")


def bad_word(clue: str, absolute_forms: set[str], lexicon_forms: set[str],
             proper_nouns: set[str] | None = None) -> str | None:
    """Paraula vetada (absolute) o desconeguda al lèxic normatiu; None si totes són bones.

    Una paraula en majúscula dins de la frase es tracta com a nom propi: s'accepta sempre
    si `proper_nouns` és None (definicions del Viquidiccionari) o només si hi és (pistes
    de redacció pròpia, com `tool/check_vocabulary.py`)."""
    words = clue_words(HYPHEN_CLITICS.sub('', clue))
    for i, w in enumerate(words):
        c = N.canonicalize(w)
        if c is not None and c in absolute_forms:
            return w
        if len(w) == 1:
            continue  # l', d', s' separats per l'apòstrof
        if c is None or c not in lexicon_forms:
            if w[0].isupper() and i > 0 and (proper_nouns is None or w in proper_nouns):
                continue  # nom propi dins de la frase
            return w
    return None


OVERRIDE_HEADER = ['form', 'action', 'value', 'reason']
# Definicions que no tenen sentit amb el prefix «(plural) » (elements químics, xifres).
NOT_REUSABLE = ('Element químic', 'Xifra i nombre', 'Nombre que', 'Numeral que')
OVERRIDE_ACTIONS = ('replace', 'sense', 'drop', 'lemma_only')
APOSTROPHE = '’'  # apòstrof tipogràfic, com a la interfície (docs/DECISIONS.md)


@dataclass(frozen=True)
class Override:
    action: str
    value: str


def load_overrides(path: Path | None) -> dict[str, Override]:
    """Correccions manuals de pistes (tool/data/clue_overrides.tsv):
    replace = pista reescrita (`value`); sense = número (1, 2…) de l'accepció de la pàgina
    que s'ha de fer servir; drop = sense pista; lemma_only = la pista del lema no es
    reutilitza per a les formes flexionades."""
    if path is None or not path.exists():
        return {}
    header, rows = tsv.read_tsv(path)
    if header != OVERRIDE_HEADER:
        raise L.BuildError(f'{path}: capçalera inesperada {header}')
    out: dict[str, Override] = {}
    for n, row in enumerate(rows, start=2):
        if not row or row == [''] or row[0].startswith('#'):
            continue
        if len(row) != 4 or not row[3].strip():
            raise L.BuildError(f'{path}:{n}: calen 4 columnes i motiu: {row}')
        form, action, value = row[0].strip(), row[1].strip(), row[2].strip()
        if action not in OVERRIDE_ACTIONS:
            raise L.BuildError(f'{path}:{n}: acció desconeguda {action!r}')
        if action == 'sense' and not value.isdigit():
            raise L.BuildError(f'{path}:{n}: `sense` necessita un número d\'accepció')
        if action == 'replace' and not value:
            raise L.BuildError(f'{path}:{n}: `replace` sense text')
        if form in out:
            raise L.BuildError(f'{path}:{n}: «{form}» duplicada')
        out[form] = Override(action, value)
    return out


def typographic(clue: str) -> str:
    return clue.replace("'", APOSTROPHE)


# Correccions ortogràfiques i gramaticals automàtiques (m1 del QA, iteració 2). Només
# regles sense ambigüitat; tool/tests/test_clue_orthography.py comprova que cap pista
# generada no conté els patrons d'error.
DIACRITICS_2016 = {  # accents diacrítics suprimits per la normativa de 2016 (IEC)
    'dóna': 'dona', 'dónes': 'dones', 'dóno': 'dono', 'sóc': 'soc', 'véns': 'vens',
    'vénen': 'venen', 'fóra': 'fora', 'móra': 'mora', 'féu': 'feu',
    'nét': 'net', 'néts': 'nets', 'bóta': 'bota', 'bótes': 'botes', 'cóc': 'coc',
    'cócs': 'cocs', 'mòlt': 'molt',
}
_DIACRITIC = re.compile(r'\b(' + '|'.join(sorted(DIACRITICS_2016, key=len, reverse=True))
                        + r')\b', re.I)
_PREP_ART_QUE = re.compile(
    r'\b(amb|en|per|sobre|sota|contra|sense|mitjançant) (la|el|les|els) que\b')
_A_ON = re.compile(r'(?<![Cc]ap )\ba on\b')
_QUE_LI_AGRADA = re.compile(r'\b([Qq])ue (no )?li (agrad[a-z]*|plau|plauen)\b')
_PER_QUE = re.compile(r'(?<!^)(?<!\bel )\bper (què|que)\b')
_MES = re.compile(r'\b([Mm])es\b(?! (de|del|d’|d\'|i)\b)(?=\s+\w)')
_ES = re.compile(r"\b([Ee])s ([\wà-üŀ·]+)")
_CLITICS = frozenset({'hi', 'ho', 'li', 'n', 'en', 'l', 'els', 'les', 'la', 'lo', 'ne'})


def fix_orthography(clue: str, verb_forms: set[str] | frozenset[str] = frozenset()) -> str:
    """Corregeix errors freqüents de les definicions:
    - accents diacrítics suprimits el 2016 (`dóna` -> `dona`, `sóc` -> `soc`);
    - relatiu amb preposició i article (`amb la que` -> `amb la qual`);
    - `a on` relatiu -> `on` (llevat de `cap a on`);
    - `que (no) li agrada` -> `a qui (no) agrada`;
    - `per què` / `per que` final dins la frase -> `perquè`;
    - `mes` adverbi -> `més` (no davant de `de`, `del`, `i`: `mes de l’any`);
    - `es` davant d'una paraula que no és cap forma verbal ni pronom feble -> `és`
      (només si es coneixen les formes verbals: `que es poc comunicatiu`)."""
    def diac(m: re.Match) -> str:
        w = m.group(1)
        fixed = DIACRITICS_2016[w.lower()]
        return fixed[0].upper() + fixed[1:] if w[0].isupper() else fixed

    s = _DIACRITIC.sub(diac, clue)
    s = _PREP_ART_QUE.sub(lambda m: f'{m.group(1)} {m.group(2)} '
                          + ('quals' if m.group(2) in ('les', 'els') else 'qual'), s)
    s = _A_ON.sub('on', s)
    s = _QUE_LI_AGRADA.sub(lambda m: ('A' if m.group(1) == 'Q' else 'a') + ' qui '
                           + (m.group(2) or '') + m.group(3), s)
    s = _PER_QUE.sub('perquè', s)
    s = _MES.sub(lambda m: m.group(1) + 'és', s)
    if verb_forms:
        def es(m: re.Match) -> str:
            nxt = m.group(2).lower()
            if nxt in _CLITICS or nxt in verb_forms:
                return m.group(0)
            return ('É' if m.group(1) == 'E' else 'é') + 's ' + m.group(2)
        s = _ES.sub(es, s)
    return s


class ClueBuilder:
    def __init__(self, pages: dict[str, W.WikiPage], forms_of: dict[str, set[str]],
                 absolute_forms: set[str], lexicon_forms: set[str],
                 overrides: dict[str, Override] | None = None,
                 verb_forms: set[str] | frozenset[str] = frozenset(),
                 nominal_lemmas: dict[str, set[str]] | None = None,
                 categories: dict[tuple[str, str], tuple[str, ...]] | None = None):
        self.pages = pages
        # (forma, lema) -> categories (pos) d’aquesta anàlisi segons el diccionari LT
        self.categories = categories or {}
        self.recovered: collections.Counter = collections.Counter()
        self.recover = False  # segona passada (recuperació) de clue_for
        self.verb_forms = verb_forms
        # forma -> lemes dels quals és forma nominal (N/A) segons el diccionari LT; si no
        # es dona, cap forma sense pàgina pròpia no hereta la pista del lema
        self.nominal_lemmas = nominal_lemmas
        self.nominal_forms = frozenset(nominal_lemmas or ())
        self.forms_of = forms_of
        self.absolute_forms = absolute_forms
        self.lexicon_forms = lexicon_forms
        self.overrides = overrides or {}
        self.used_overrides: set[str] = set()
        self.override_errors: list[str] = []
        self.rejections: collections.Counter = collections.Counter()

    def acceptable(self, clue: str, form: str, lemma: str) -> bool:
        if not MIN_LEN <= len(clue) <= MAX_LEN:
            self.rejections['longitud'] += 1
            return False
        if ANAPHORA.search(clue):
            self.rejections['remet_a_una_altra_accepcio'] += 1
            return False
        if reveals(clue, form, lemma, self.forms_of.get(lemma, set())):
            self.rejections['revela_paraula_o_arrel'] += 1
            return False
        if bad_word(clue, self.absolute_forms, self.lexicon_forms):
            self.rejections['paraula_vetada_o_desconeguda'] += 1
            return False
        return True

    def select(self, title: str, pos: str, feminine: bool = False,
               plural: bool = False) -> tuple[str, bool] | None:
        """(text net, representativa) de la primera accepció seleccionable (spec: selecció
        de l'accepció). És representativa si és la primera accepció d'aquesta categoria de
        la pàgina i no porta cap marca (ni tan sols temàtica).

        Amb `feminine` (pista heretada per una forma femenina) se salten les seccions de
        noms només masculins (`{{ca-nom|m}}` sense `f=`: `patró` «model») i les accepcions
        marcades com a masculines; amb `plural`, les marcades com a singulars."""
        page = self.pages.get(title)
        if page is None:
            return None
        first = True
        for sense in page.senses:
            if sense.is_form_of or sense.pos != pos:
                continue
            if feminine and (sense.masculine_only or any('masculí' in m for m in sense.marks)):
                self.rejections['accepcio_nomes_masculina'] += 1
                continue
            if plural and any('singular' in m for m in sense.marks):
                self.rejections['accepcio_nomes_singular'] += 1
                continue
            if any(m in SKIP_MARKS for m in sense.marks):
                self.rejections['marca_dialectal_o_registre'] += 1
                first = False
                continue
            text = clean_sense(sense.text)
            if text is None:
                self.rejections['plantilla_o_remissio'] += 1
                first = False
                continue
            # en la passada de recuperació, una marca temàtica («botànica», «anatomia»)
            # no impedeix que la primera accepció es reutilitzi en les flexions
            return text, first and (self.recover or not sense.marks)
        return None

    def select_sense(self, title: str, pos: str) -> str | None:
        sel = self.select(title, pos)
        return None if sel is None else sel[0]

    def _override_clue(self, title: str, form: str, lemma: str) -> str | None:
        """Pista d'una correcció manual (replace o sense); ha de superar tots els filtres."""
        ov = self.overrides[title]
        self.used_overrides.add(title)
        if ov.action == 'replace':
            clue = ov.value
        else:
            page = self.pages.get(title)
            idx = int(ov.value) - 1
            if page is None or not 0 <= idx < len(page.senses):
                raise L.BuildError(f'correcció de «{title}»: no hi ha l\'accepció {ov.value}')
            text = clean_sense(page.senses[idx].text)
            clue = shorten(text) if text is not None else None
            if clue is None:
                raise L.BuildError(f'correcció de «{title}»: l\'accepció {ov.value} no és vàlida')
        if not self.acceptable(clue, form, lemma):
            why = (reveals(clue, form, lemma, self.forms_of.get(lemma, set()))
                   or bad_word(clue, self.absolute_forms, self.lexicon_forms) or 'longitud')
            err = f'«{title}» -> «{clue}» ({why})'
            if err not in self.override_errors:
                self.override_errors.append(err)
            return None
        return clue

    def own_clue(self, title: str, form: str, lemma: str, pos: str,
                 representative: bool = False, feminine: bool = False,
                 plural: bool = False, use_overrides: bool = True) -> str | None:
        """Pista de l'accepció seleccionada; si no supera els filtres no se'n busca cap altra
        (les accepcions posteriors solen ser secundàries o figurades). Amb `representative`
        (reutilització per a una forma flexionada) cal que l'accepció sigui representativa."""
        ov = self.overrides.get(title) if use_overrides else None
        if ov is not None and ov.action in ('replace', 'sense'):
            return self._override_clue(title, form, lemma)
        if ov is not None and ov.action == 'drop':
            self.used_overrides.add(title)
            return None
        if ov is not None and ov.action == 'lemma_only' and representative:
            self.used_overrides.add(title)
            return None
        sel = self.select(title, pos, feminine, plural)
        if sel is None:
            return None
        text, is_repr = sel
        if representative and (not is_repr or text.startswith(NOT_REUSABLE)):
            self.rejections['accepcio_poc_representativa_per_a_flexio'] += 1
            return None
        clue = shorten(text, cut=self.recover, verb_forms=self.verb_forms,
                       nominal_forms=self.nominal_forms)
        if clue is None:
            self.rejections['longitud'] += 1
            return None
        if self.recover:
            # l’ortografia es corregeix abans dels filtres («dóna» -> «dona» és al lèxic)
            clue = fix_orthography(typographic(clue), self.verb_forms)
        return clue if self.acceptable(clue, form, lemma) else None

    def clue_for(self, form: str, lemma: str, kind: str, pos: str) -> tuple[str, str] | None:
        res = self._clue_for(form, lemma, kind, pos)
        if res is None:
            # ampliacio-pistes D2: recuperació només per a les candidates sense pista (les
            # pistes existents no canvien): 1) retall per oració de les definicions massa
            # llargues; 2) si la categoria de la candidata (`alt` és N per POS_ORDER) no
            # dona pista, les altres categories que el diccionari LT dona a la mateixa
            # anàlisi (forma, lema), en l’ordre de la pàgina del Viquidiccionari
            self.recover = True
            counted = self.rejections.copy()  # els motius de rebuig són els de la 1a passada
            try:
                res = self._clue_for(form, lemma, kind, pos)
                if res is not None:
                    self.recovered['segona_passada'] += 1
                for alt in ([] if res else self.alternative_pos(form, lemma, kind, pos)):
                    res = self._clue_for(form, lemma, kind, alt)
                    if res is not None:
                        self.recovered['altra_categoria'] += 1
                        break
            finally:
                self.recover = False
                self.rejections = counted
        return None if res is None else (
            fix_orthography(typographic(res[0]), self.verb_forms), res[1])

    def alternative_pos(self, form: str, lemma: str, kind: str, pos: str) -> list[str]:
        allowed = self.categories.get((form, lemma), ())
        if kind != 'lemma':
            allowed = tuple(p for p in allowed if p in NOMINAL)
        page = self.pages.get(form if kind == 'lemma' else lemma)
        order = []
        for sense in (page.senses if page else ()):
            if sense.pos and sense.pos not in order and not sense.is_form_of:
                order.append(sense.pos)
        return [p for p in order if p != pos and p in allowed]

    def _clue_for(self, form: str, lemma: str, kind: str, pos: str) -> tuple[str, str] | None:
        if self.overrides.get(form, Override('', '')).action == 'drop':
            self.used_overrides.add(form)
            return None
        own = self.own_clue(form, form, lemma, pos)
        if own is not None:
            return own, form
        if kind not in PREFIX:
            return None
        # B2 del QA (iteració 2): la pista del lema només s'hereta si el Viquidiccionari
        # confirma que la forma és una flexió d'aquest lema i d'aquesta categoria (`mansa`
        # és el femení de l'adjectiu `mans`, no una forma de `mà`).
        chain = self.form_chain(form, pos)
        # `germanes` -> plural de `germana` (pàgina pròpia), que és forma de `germà` (LT)
        if lemma not in chain and any(via == 'p' and mid in self.forms_of.get(lemma, ())
                                      for mid, via in chain.items()):
            chain[lemma] = ''
        if lemma not in chain and not (not self.has_nominal_section(form)
                                       and self.unambiguous(form, lemma)):
            self.rejections['flexio_no_confirmada'] += 1
            return None
        feminine = kind in ('femeni', 'femeni_plural')
        plural = kind in ('plural', 'femeni_plural')
        # femení plural amb pàgina pròpia del femení singular (`germanes` -> `germana`)
        if kind == 'femeni_plural':
            for mid, via in chain.items():
                if mid != lemma and via == 'p' and chain.get(lemma) is not None:
                    base = self.own_clue(mid, mid, lemma, pos, representative=True,
                                         plural=True)
                    res = self._inherited('plural', base, form, lemma)
                    if res is not None:
                        return res, mid
        base = self.own_clue(lemma, lemma, lemma, pos, representative=True,
                             feminine=feminine, plural=plural)
        if base is None and feminine and pos == 'N':
            # femení d'un nom només masculí amb adjectiu homògraf (`estranya`, `torta`): la
            # forma femenina és la de l'adjectiu
            base = self.own_clue(lemma, lemma, lemma, 'A', representative=True,
                                 feminine=feminine, plural=plural)
        res = self._inherited(kind, base, form, lemma)
        if res is None and base is not None and self._is_labelled(base):
            # pista manual del lema amb etiqueta de flexió incompatible (`mans` «(plural)
            # Extremitats…» per a `mansa`): es prova l'accepció del Viquidiccionari
            base = self.own_clue(lemma, lemma, lemma, pos, representative=True,
                                 feminine=feminine, plural=plural, use_overrides=False)
            res = self._inherited(kind, base, form, lemma)
        return None if res is None else (res, lemma)

    @staticmethod
    def _is_labelled(clue: str) -> bool:
        return LABEL.match(clue) is not None

    def _inherited(self, kind: str, base: str | None, form: str, lemma: str) -> str | None:
        """Pista heretada amb l'etiqueta de flexió, o None si no és vàlida."""
        if base is None:
            return None
        clue = combine_label(kind, base)
        if clue is None:
            self.rejections['etiqueta_de_flexio_incompatible'] += 1
            return None
        definition = clue[LABEL.match(clue).end():]
        # el prefix és text propi: els filtres es tornen a aplicar a la definició
        # respecte de la forma, i la longitud a la pista completa
        if len(clue) > MAX_LEN:
            self.rejections['longitud'] += 1
        elif reveals(clue, form, lemma, self.forms_of.get(lemma, set())):
            self.rejections['revela_paraula_o_arrel'] += 1  # p. ex. «(femení)» a femenina
        elif self.acceptable(definition, form, lemma):
            return clue
        return None

    def has_nominal_section(self, form: str) -> bool:
        page = self.pages.get(form)
        return page is not None and any(s.pos in NOMINAL for s in page.senses)

    def unambiguous(self, form: str, lemma: str) -> bool:
        """Sense pàgina nominal de la forma al Viquidiccionari, la pista del lema només
        s'hereta si, segons el diccionari LT, la forma només és flexió nominal d'aquest
        lema i el lema no és flexió nominal de cap altre (`mans` és plural de `mà`)."""
        if self.nominal_lemmas is None:
            return False
        return (self.nominal_lemmas.get(form, {lemma}) <= {lemma}
                and self.nominal_lemmas.get(lemma, {lemma}) <= {lemma})

    def form_chain(self, form: str, pos: str, max_hops: int = 3) -> dict[str, str]:
        """Formes base a què remet la pàgina de la forma ({{forma-f|ca|…}}, {{forma-p|ca|…}})
        en seccions nominals (nom o adjectiu, si la candidata també ho és), seguint fins a
        `max_hops` remissions (`germanes` -> `germana` -> `germà`). Valor: tipus de la
        remissió directa (`p`, `f`…) per a les formes a un sol pas, '' per a les altres."""
        ok = NOMINAL if pos in NOMINAL else {pos}
        out: dict[str, str] = {}
        frontier = [form]
        for hop in range(max_hops):
            nxt = []
            for title in frontier:
                page = self.pages.get(title)
                if page is None:
                    continue
                for sense in page.senses:
                    if sense.pos not in ok:
                        continue
                    for k, target in sense.form_targets:
                        if target not in out and target != form:
                            out[target] = k if hop == 0 else ''
                            nxt.append(target)
            frontier = nxt
        return out


LABEL = re.compile(r'^\((femení plural|femení|plural)\) ')
NOMINAL = frozenset({'N', 'A'})


def combine_label(kind: str, base: str) -> str | None:
    """Afegeix l'etiqueta de flexió a la pista del lema. Si la pista del lema ja en porta
    una (correcció manual de `blanca`: «(femení) …»), només es combina «(femení)» amb un
    plural («(femení plural)»); qualsevol altra combinació no és vàlida (una etiqueta
    «(plural)» vol dir que el lema és homògraf d'un plural d'un altre mot: `mans`)."""
    m = LABEL.match(base)
    if m is None:
        return PREFIX[kind] + base
    if m.group(1) == 'femení' and kind in ('plural', 'femeni_plural'):
        return PREFIX['femeni_plural'] + base[m.end():]
    return None


def read_solutions(path: Path) -> list[dict[str, str]]:
    header, rows = tsv.read_tsv(path)
    if tuple(header) != L.SOLUTIONS_HEADER:
        raise L.BuildError(f'{path}: capçalera inesperada {header}')
    return [dict(zip(header, r)) for r in rows]


# --- Pistes de redacció pròpia (ampliacio-pistes) -----------------------------------------
AUTHORED_HEADER = ['form', 'clue', 'note']
AUTHORED_SOURCE = 'pròpia'
AUTHORED_GLOB = 'part-*.tsv'
LABEL_OF_KIND = {'plural': '(plural) ', 'femeni': '(femení) ',
                 'femeni_plural': '(femení plural) '}


@dataclass(frozen=True)
class Authored:
    form: str
    clue: str
    where: str  # fitxer:línia


def load_authored(directory: Path | None) -> dict[str, Authored]:
    """Pistes de redacció pròpia: `tool/data/clues_authored/part-NN.tsv` (columnes `form`,
    `clue`, `note` opcional; línies `#` de comentari). Una forma només pot aparèixer una
    vegada en tot el directori."""
    if directory is None or not directory.is_dir():
        return {}
    out: dict[str, Authored] = {}
    for path in sorted(directory.glob(AUTHORED_GLOB)):
        header, rows = tsv.read_tsv(path)
        if header != AUTHORED_HEADER:
            raise L.BuildError(f'{path}: capçalera inesperada {header}; '
                               f'se n\'esperava {AUTHORED_HEADER}')
        for n, row in enumerate(rows, start=2):
            if not row or row == [''] or row[0].startswith('#'):
                continue
            where = f'{path.name}:{n}'
            if len(row) != 3:
                raise L.BuildError(f'{where}: calen 3 columnes (form, clue, note): {row}')
            form, clue = row[0], row[1]
            if form != form.strip() or not form:
                raise L.BuildError(f'{where}: forma buida o amb espais: {form!r}')
            if form in out:
                raise L.BuildError(f'{where}: «{form}» ja és a {out[form].where}')
            out[form] = Authored(form, clue, where)
    return out


def authored_error(clue: str, form: str, lemma: str, kind: str, cb: 'ClueBuilder',
                   vetoed_forms: set[str], proper_nouns: set[str]) -> str | None:
    """Motiu pel qual una pista pròpia no és vàlida, o None. Són els filtres de les pistes
    del Viquidiccionari (longitud, remissions, no revelar la paraula ni l'arrel, vocabulari
    normatiu) més les regles d'estil de docs/LEXIC.md: text pla, majúscula inicial, sense
    punt final, apòstrof tipogràfic, cometes «», cap paraula de la llista negra (cap
    nivell), ortografia corregida i etiqueta de flexió coherent amb el tipus."""
    if clue != clue.strip() or '  ' in clue:
        return 'espais sobrers'
    if not MIN_LEN <= len(clue) <= MAX_LEN:
        return f'longitud {len(clue)} (cal 8–80)'
    if "'" in clue:
        return 'apòstrof recte (cal «’»)'
    if re.search(r'["“”]', clue):
        return 'cometes (cal «»)'
    if _FORBIDDEN_CHARS.search(clue):
        return 'caràcters de marcatge'
    if clue.endswith('.'):
        return 'punt final'
    label = LABEL.match(clue)
    want = LABEL_OF_KIND.get(kind)
    if want is not None and (label is None or label.group(0) != want):
        return f'cal començar amb «{want.strip()}»'
    if want is None and label is not None:
        return 'etiqueta de flexió en un lema'
    body = clue[label.end():] if label else clue
    if not body[:1].isupper():
        return 'majúscula inicial'
    if ANAPHORA.search(clue):
        return 'remet a una altra accepció'
    w = reveals(body, form, lemma, cb.forms_of.get(lemma, set()))
    if w:
        return f'revela la paraula o l’arrel («{w}»)'
    w = bad_word(body, cb.absolute_forms, cb.lexicon_forms, proper_nouns)
    if w:
        return f'paraula fora del lèxic normatiu («{w}»)'
    for word in clue_words(body):
        c = N.canonicalize(word)
        if c is not None and c in vetoed_forms:
            return f'paraula de la llista negra («{word}»)'
    if fix_orthography(clue, cb.verb_forms) != clue:
        return f'ortografia: «{fix_orthography(clue, cb.verb_forms)}»'
    return None


# --- Pistes de temporada (temporada-nadal D5) -------------------------------------------
SEASONS_DATA = config.DATA_DIR / 'seasons'
SEASON_CLUES = 'clues.tsv'          # tool/data/seasons/<id>/clues.tsv (form, clue, note)
SEASON_OUT_DIR = 'seasons'          # assets/lexicon/seasons/<id>-clues.tsv
# Excepció declarada (`note` = «excepció=etiqueta»): homògrafs amb `kind` flexionat al LT
# la pista de temporada dels quals és la del nom (`parada`, femení de «parat» al LT, és el
# lloc de venda de la fira). Només per a les formes d'aquesta llista.
LABEL_EXCEPTION = 'excepció=etiqueta'
# `molles`: plural del nom «molla» a Cuina (madeixes-tematiques, QA M5).
LABEL_EXCEPTION_FORMS = frozenset({'parada', 'parades', 'molles'})


THEMES_DATA = config.DATA_DIR / 'themes'
THEME_OUT_DIR = 'themes'            # assets/lexicon/themes/<id>-clues.tsv (madeixes-tematiques D12)


def load_season_clues(seasons_dir: Path | None, prefix: str = 'seasons'
                      ) -> dict[str, dict[str, tuple[str, str, str]]]:
    """id de temporada (o de temàtica, amb `prefix` = `themes`) -> forma -> (pista, nota,
    fitxer:línia)."""
    out: dict[str, dict[str, tuple[str, str, str]]] = {}
    if seasons_dir is None or not seasons_dir.is_dir():
        return out
    for d in sorted(p for p in seasons_dir.iterdir() if p.is_dir()):
        path = d / SEASON_CLUES
        if not path.exists():
            continue
        header, rows = tsv.read_tsv(path)
        if header != AUTHORED_HEADER:
            raise L.BuildError(f'{path}: capçalera inesperada {header}; '
                               f'se n\'esperava {AUTHORED_HEADER}')
        got: dict[str, tuple[str, str, str]] = {}
        for n, row in enumerate(rows, start=2):
            if not row or row == [''] or row[0].startswith('#'):
                continue
            where = f'{prefix}/{d.name}/{SEASON_CLUES}:{n}'
            if len(row) != 3:
                raise L.BuildError(f'{where}: calen 3 columnes (form, clue, note): {row}')
            form, clue, note = row
            if not form or form != form.strip():
                raise L.BuildError(f'{where}: forma buida o amb espais: {form!r}')
            if form in got:
                raise L.BuildError(f'{where}: «{form}» ja és a {got[form][2]}')
            got[form] = (clue, note, where)
        out[d.name] = got
    return out


def build_season_clues(season_clues, by_form: dict[str, dict[str, str]], cb: 'ClueBuilder',
                       vetoed_forms: set[str], proper_nouns: set[str]
                       ) -> dict[str, list[ClueRow]]:
    """Valida les pistes de temporada amb els filtres de les pistes pròpies (també quan la
    forma ja té pista general: la de temporada té precedència dins dels reptes)."""
    errors: list[str] = []
    out: dict[str, list[ClueRow]] = {}
    for sid, rows in sorted(season_clues.items()):
        built = []
        for form, (clue, note, where) in sorted(rows.items()):
            s = by_form.get(form)
            if s is None:
                errors.append(f'{where} «{form}»: no és candidata a solució')
                continue
            kind = s['kind']
            if LABEL_EXCEPTION in note:
                if form not in LABEL_EXCEPTION_FORMS:
                    errors.append(f'{where} «{form}»: excepció d\'etiqueta no declarada')
                    continue
                kind = 'lemma'
            why = authored_error(clue, form, s['lemma'], kind, cb, vetoed_forms, proper_nouns)
            if why:
                errors.append(f'{where} «{form}» -> «{clue}»: {why}')
                continue
            built.append(ClueRow(s['key'], form, s['lemma'], clue, AUTHORED_SOURCE))
        built.sort(key=lambda r: (r.key, r.form))
        out[sid] = built
    if errors:
        raise L.BuildError(f'{len(errors)} pistes de temporada no superen els filtres:\n  '
                           + '\n  '.join(sorted(errors)))
    return out


def build(dt: SC.DictToolsPaths, dump: Path, out_dir: Path,
          overrides_path: Path | None = None, authored_dir: Path | None = None,
          exceptions_path: Path | None = None, seasons_dir: Path | None = None,
          themes_dir: Path | None = None) -> dict:
    solutions = read_solutions(out_dir / 'solutions.tsv')
    blacklist = L.read_blacklist(out_dir / 'blacklist.tsv')
    absolute_forms = {r['form'] for r in blacklist if r['level'] == 'absolute'}
    ex_forms, ex_lemmas = SC.load_exclusions(dt.exclusions)
    hunspell, _ = SC.expand_hunspell(dt.hunspell_dic, dt.hunspell_aff)
    lt = list(SC.iter_lt(dt.lt_dictionary))
    norm, _, _ = L.normative_forms(lt, hunspell, ex_forms, ex_lemmas)
    forms_of: dict[str, set[str]] = collections.defaultdict(set)
    for e in lt:
        forms_of[e.lemma].add(e.form)
    titles = {s['form'] for s in solutions} | {s['lemma'] for s in solutions}
    # pàgines intermèdies de les remissions (`germana` per a `germanes`)
    titles |= {f for s in solutions for f in forms_of.get(s['lemma'], ())}
    pages = {p.title: p for p in W.iter_pages(dump, titles=titles)}
    overrides = load_overrides(overrides_path)
    verb_forms = {e.form.lower() for e in lt if e.tag.startswith('V')}
    nominal_lemmas: dict[str, set[str]] = collections.defaultdict(set)
    for e in lt:
        if e.tag[:1] in ('N', 'A') and not SC.is_excluded_tag(e.tag):
            nominal_lemmas[e.form].add(e.lemma)
    categories: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for form, analyses in norm.items():
        for lemma, tag in sorted(analyses):
            pos = L.pos_of(tag)
            if pos is None or (pos == 'V' and (form != lemma or tag[2:3] != 'N')):
                continue  # només l'infinitiu representa un verb
            if pos not in categories[(form, lemma)]:
                categories[(form, lemma)].append(pos)
    cb = ClueBuilder(pages, forms_of, absolute_forms, set(norm), overrides, verb_forms,
                     dict(nominal_lemmas), {k: tuple(v) for k, v in categories.items()})
    authored = load_authored(authored_dir)
    vetoed_forms = {r['form'] for r in blacklist}
    # noms propis: els del diccionari LT (etiqueta NP) i els revisats de check_vocabulary
    proper_nouns = load_proper_nouns(exceptions_path) | {e.form for e in lt
                                                         if e.tag.startswith('NP')}
    by_form = {s['form']: s for s in solutions}
    unknown = sorted(f'{a.where} «{a.form}»' for a in authored.values()
                     if a.form not in by_form)
    if unknown:
        raise L.BuildError('pistes pròpies de formes que no són candidates a solució: '
                           + '; '.join(unknown[:20]))
    rows = []
    by_band: collections.Counter = collections.Counter()
    shadowed: list[str] = []
    authored_errors: list[str] = []
    n_authored = 0
    for s in solutions:
        res = cb.clue_for(s['form'], s['lemma'], s['kind'], s['pos'])
        a = authored.get(s['form'])
        if res is not None and a is not None:
            shadowed.append(s['form'])  # prioritat: correcció > Viquidiccionari > pròpia
        elif res is None and a is not None:
            why = authored_error(a.clue, s['form'], s['lemma'], s['kind'], cb,
                                 vetoed_forms, proper_nouns)
            if why:
                authored_errors.append(f'{a.where} «{a.form}» -> «{a.clue}»: {why}')
                continue
            res = (a.clue, AUTHORED_SOURCE)
            n_authored += 1
        if res is not None:
            rows.append(ClueRow(s['key'], s['form'], s['lemma'], res[0], res[1]))
            by_band[s['band']] += 1
    if cb.override_errors:
        raise L.BuildError('correccions de pistes que no superen els filtres: '
                           + '; '.join(sorted(set(cb.override_errors))))
    if authored_errors:
        raise L.BuildError(f'{len(authored_errors)} pistes pròpies no superen els filtres:\n  '
                           + '\n  '.join(sorted(authored_errors)))
    rows.sort(key=lambda r: (r.key, r.form))
    check_clues(rows, solutions)
    seasons = build_season_clues(load_season_clues(seasons_dir), by_form, cb, vetoed_forms,
                                 proper_nouns)
    tsv.write_tsv(out_dir / 'clues.tsv', HEADER,
                  [(r.key, r.form, r.lemma, r.clue, r.source) for r in rows])
    sdir = out_dir / SEASON_OUT_DIR
    for old in sorted(sdir.glob('*-clues.tsv')) if sdir.is_dir() else []:
        if old.name[:-len('-clues.tsv')] not in seasons:
            old.unlink()
    for sid, srows in seasons.items():
        check_clues(srows, solutions)
        sdir.mkdir(parents=True, exist_ok=True)
        tsv.write_tsv(sdir / f'{sid}-clues.tsv', HEADER,
                      [(r.key, r.form, r.lemma, r.clue, r.source) for r in srows])
    # Pistes pròpies de les temàtiques (madeixes-tematiques D12): mateixos filtres.
    themes = build_season_clues(load_season_clues(themes_dir, 'themes'), by_form, cb,
                                vetoed_forms, proper_nouns)
    tdir = out_dir / THEME_OUT_DIR
    for old in sorted(tdir.glob('*-clues.tsv')) if tdir.is_dir() else []:
        if old.name[:-len('-clues.tsv')] not in themes:
            old.unlink()
    for tid, trows in themes.items():
        check_clues(trows, solutions)
        tdir.mkdir(parents=True, exist_ok=True)
        tsv.write_tsv(tdir / f'{tid}-clues.tsv', HEADER,
                      [(r.key, r.form, r.lemma, r.clue, r.source) for r in trows])
    totals = collections.Counter(s['band'] for s in solutions)
    return {
        'clues': len(rows),
        'coverage_by_band': {b: f'{by_band[b]}/{totals[b]}' for b in sorted(totals)},
        'authored': n_authored,
        'authored_shadowed': sorted(shadowed),
        'recovered': dict(sorted(cb.recovered.items())),
        'rejections': dict(sorted(cb.rejections.items())),
        'overrides_unused': sorted(set(overrides) - cb.used_overrides),
        'season_clues': {sid: len(r) for sid, r in seasons.items()},
        'theme_clues': {tid: len(r) for tid, r in themes.items()},
    }


def load_proper_nouns(path: Path | None) -> set[str]:
    """Noms propis i sigles revisats (`tool/data/vocabulary_exceptions.tsv`, primera
    columna) que una pista pròpia pot contenir en majúscula."""
    if path is None or not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        word = line.split('#', 1)[0].split('\t', 1)[0].strip()
        if word and word != 'paraula':
            out.add(word)
    return out


def check_clues(rows: list[ClueRow], solutions: list[dict[str, str]]) -> None:
    cands = {(s['key'], s['form']) for s in solutions}
    orphans = [r.form for r in rows if (r.key, r.form) not in cands]
    if orphans:
        raise L.BuildError(f'pistes sense candidata: {orphans[:20]}')
    seen = collections.Counter((r.key, r.form) for r in rows)
    dups = [k for k, n in seen.items() if n > 1]
    if dups:
        raise L.BuildError(f'més d\'una pista per grafia: {dups[:20]}')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Genera les pistes')
    ap.add_argument('--dict-tools', type=Path)
    ap.add_argument('--dump', type=Path)
    ap.add_argument('--overrides', type=Path, default=config.DATA_DIR / 'clue_overrides.tsv')
    ap.add_argument('--authored', type=Path, default=config.DATA_DIR / 'clues_authored',
                    help='directori de pistes de redacció pròpia (part-*.tsv)')
    ap.add_argument('--exceptions', type=Path,
                    default=config.DATA_DIR / 'vocabulary_exceptions.tsv')
    ap.add_argument('--seasons', type=Path, default=SEASONS_DATA,
                    help='dades de temporada (tool/data/seasons/<id>/clues.tsv)')
    ap.add_argument('--themes', type=Path, default=THEMES_DATA,
                    help='dades de les temàtiques (tool/data/themes/<id>/clues.tsv)')
    ap.add_argument('--out-dir', type=Path, default=config.LEXICON_DIR)
    a = ap.parse_args(argv)
    dt = SC.DictToolsPaths(a.dict_tools) if a.dict_tools else config.default_dict_tools()
    try:
        stats = build(dt, a.dump or config.default_dump(), a.out_dir, a.overrides,
                      a.authored, a.exceptions, a.seasons, a.themes)
    except L.BuildError as e:
        raise SystemExit(f'ERROR: {e}') from None
    for k, v in stats.items():
        print(f'[clues] {k}: {v}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
