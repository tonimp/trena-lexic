"""Normalització i tokenització de grafies catalanes (spec lexicon-normalization).

Implementació de referència. La implementació Dart (lib/core/lexicon/normalization.dart)
fa servir exactament les mateixes taules; els vectors compartits de
test/data/normalization_vectors.json garanteixen que coincideixen.

Passos de `canonicalize`:
  1. U+2019 -> «'» (després serà invàlid, però es normalitza abans de validar).
  2. Composició restringida: lletra base + marca combinant (U+0300, U+0301, U+0308,
     U+0327) -> lletra precomposta de l'alfabet admès. Qualsevol altra marca
     combinant queda tal qual i invalida l'entrada al pas 6.
  3. Minúscules amb una taula pròpia (ASCII + lletres catalanes); la resta de
     caràcters es mantenen i, si no són de l'alfabet, invaliden l'entrada.
  4. ŀ (U+0140) i Ŀ (U+013F) -> «l·».
  5. Separadors U+2027, U+2219, U+22C5 entre dues «l» -> punt volat U+00B7.
  6. Validació: només a-z, à è é í ï ò ó ú ü ç i el punt volat dins de «l·l»
     (sense compartir cap «l»: «l·l·l» és invàlid).
"""
from __future__ import annotations

NORMALIZATION_VERSION = 1

MIDDLE_DOT = '·'
KEY_LL = 'Ŀ'  # Ŀ: un code point per al token L·L a la clau
TOKEN_LL = 'L' + MIDDLE_DOT + 'L'

# (lletra base, marca combinant) -> lletra precomposta
COMPOSE = {
    ('a', '̀'): 'à', ('e', '̀'): 'è', ('e', '́'): 'é',
    ('i', '́'): 'í', ('i', '̈'): 'ï', ('o', '̀'): 'ò',
    ('o', '́'): 'ó', ('u', '́'): 'ú', ('u', '̈'): 'ü',
    ('c', '̧'): 'ç',
    ('A', '̀'): 'À', ('E', '̀'): 'È', ('E', '́'): 'É',
    ('I', '́'): 'Í', ('I', '̈'): 'Ï', ('O', '̀'): 'Ò',
    ('O', '́'): 'Ó', ('U', '́'): 'Ú', ('U', '̈'): 'Ü',
    ('C', '̧'): 'Ç',
}

# Majúscula -> minúscula (només aquestes; mai str.lower()).
LOWER = {chr(c): chr(c + 32) for c in range(ord('A'), ord('Z') + 1)}
LOWER.update({
    'À': 'à', 'È': 'è', 'É': 'é', 'Í': 'í',
    'Ï': 'ï', 'Ò': 'ò', 'Ó': 'ó', 'Ú': 'ú',
    'Ü': 'ü', 'Ç': 'ç',
})

LL_COMPOSED = ('ŀ', 'Ŀ')  # ŀ, Ŀ -> «l·»
DOT_LIKE = ('‧', '∙', '⋅')

# Lletra canònica -> token de graella
TOKEN_OF = {chr(c): chr(c - 32) for c in range(ord('a'), ord('z') + 1)}
TOKEN_OF.update({
    'à': 'A', 'è': 'E', 'é': 'E', 'í': 'I', 'ï': 'I',
    'ò': 'O', 'ó': 'O', 'ú': 'U', 'ü': 'U', 'ç': 'Ç',
})


def _compose(s: str) -> str:
    out: list[str] = []
    for ch in s:
        if out and (out[-1], ch) in COMPOSE:
            out[-1] = COMPOSE[(out[-1], ch)]
        else:
            out.append(ch)
    return ''.join(out)


def _tokens_of_canonical(s: str) -> list[str] | None:
    tokens: list[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch == 'l' and i + 2 < n and s[i + 1] == MIDDLE_DOT and s[i + 2] == 'l':
            tokens.append(TOKEN_LL)
            i += 3
            continue
        t = TOKEN_OF.get(ch)
        if t is None:
            return None
        tokens.append(t)
        i += 1
    return tokens or None


def canonicalize(text: str) -> str | None:
    """Grafia canònica o None si l'entrada no és una grafia vàlida."""
    s = text.replace('’', "'")
    s = _compose(s)
    s = ''.join(LOWER.get(ch, ch) for ch in s)
    for ch in LL_COMPOSED:
        s = s.replace(ch, 'l' + MIDDLE_DOT)
    if any(d in s for d in DOT_LIKE):
        chars = list(s)
        for i, ch in enumerate(chars):
            if ch in DOT_LIKE and 0 < i < len(chars) - 1 \
                    and chars[i - 1] == 'l' and chars[i + 1] == 'l':
                chars[i] = MIDDLE_DOT
        s = ''.join(chars)
    if _tokens_of_canonical(s) is None:
        return None
    return s


def tokenize(text: str) -> list[str] | None:
    canon = canonicalize(text)
    return None if canon is None else _tokens_of_canonical(canon)


def grid_key(text: str) -> str | None:
    tokens = tokenize(text)
    if tokens is None:
        return None
    return ''.join(KEY_LL if t == TOKEN_LL else t for t in tokens)


def token_label(token: str) -> str:
    """Etiqueta visible d'un token o caràcter de clau («L·L» per a Ŀ)."""
    return TOKEN_LL if token in (KEY_LL, TOKEN_LL) else token


def key_tokens(key: str) -> list[str]:
    return [token_label(c) for c in key]


def trivial_spelling(key: str) -> str:
    """Grafia trivial d'una clau: minúscules i Ŀ -> l·l."""
    return ''.join('l' + MIDDLE_DOT + 'l' if c == KEY_LL else
                   ('ç' if c == 'Ç' else c.lower()) for c in key)
