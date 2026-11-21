"""Lector en streaming del bolcat del Viquidiccionari (secció {{-ca-}}).

Fa servir bz2 + xml.etree.ElementTree.iterparse netejant els elements per tenir
memòria acotada. Només interpreta text: no executa res del bolcat.
"""
from __future__ import annotations

import bz2
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

CA_SECTION = re.compile(r'^==\s*\{\{-ca-\}\}\s*==[ \t]*$(.*?)(?=^==[^=]|\Z)', re.M | re.S)
HEADER = re.compile(r'^(={3,})\s*(.*?)\s*\1\s*$', re.M)
SENSE = re.compile(r'^#(?![:*#])\s*(.*?)\s*$', re.M)
MARK = re.compile(r'\{\{marca(?:-nocat)?\|ca\|([^{}]*)\}\}')
FORM_OF = re.compile(
    r'\{\{\s*(ca-forma-conj|forma-[a-z-]*|forma|sense accepcions|manquen accepcions)\s*[|}]')
# Remissió a la forma base: {{forma-p|ca|mà}}, {{forma-f|ca|[[nu]]/[[nuu]]}}.
FORM_TARGET = re.compile(r'\{\{\s*forma-([a-z]+)\|ca\|([^{}|]+)')
# Plantilla de capçalera de la secció: {{ca-nom|m|f=}}, {{ca-adj-forma|f}}…
HEAD = re.compile(r'^\{\{\s*(ca-[a-z-]+)\s*((?:\|[^{}]*)?)\}\}', re.M)

# Encapçalament de categoria -> pos de les candidates (D5)
HEADER_POS = {
    'nom': 'N', 'adjectiu': 'A', 'verb': 'V', 'adverbi': 'R', 'pronom': 'P',
    'article': 'D', 'determinant': 'D', 'numeral': 'D', 'preposició': 'S',
    'conjunció': 'C', 'interjecció': 'I',
}


@dataclass
class Sense:
    header: str
    text: str
    marks: tuple[str, ...]
    head: str = ''  # plantilla de capçalera de la secció (`ca-nom|m|f=`), o ''

    @property
    def form_targets(self) -> tuple[tuple[str, str], ...]:
        """(tipus, forma base) de les remissions {{forma-…|ca|…}} de l'accepció."""
        out = []
        for kind, target in FORM_TARGET.findall(self.text):
            for t in re.sub(r'\[\[([^\[\]|]*)(?:\|[^\[\]]*)?\]\]', r'\1', target).split('/'):
                if t.strip():
                    out.append((kind, t.strip()))
        return tuple(out)

    @property
    def masculine_only(self) -> bool:
        """Cert si la secció és d'un nom només masculí ({{ca-nom|m}} sense `f=`)."""
        name, _, params = self.head.partition('|')
        if name != 'ca-nom':
            return False
        args = [a.strip() for a in params.split('|')] if params else []
        gender = next((a for a in args if '=' not in a), '')
        return gender in ('m', 'mp') and not any(a.startswith('f=') or a.startswith('f2=')
                                                  for a in args)

    @property
    def is_form_of(self) -> bool:
        return bool(FORM_OF.search(self.text))

    @property
    def pos(self) -> str | None:
        return HEADER_POS.get(self.header.lower())


@dataclass
class WikiPage:
    title: str
    senses: list[Sense] = field(default_factory=list)


def parse_marks(text: str) -> tuple[str, ...]:
    out: list[str] = []
    for group in MARK.findall(text):
        for v in group.split('|'):
            v = v.strip().lower()
            if v and v != '_' and '=' not in v:
                out.append(v)
    return tuple(out)


def parse_ca_section(title: str, wikitext: str) -> WikiPage | None:
    m = CA_SECTION.search(wikitext)
    if not m:
        return None
    sec = m.group(1)
    page = WikiPage(title)
    headers = [(h.start(), h.end(), h.group(2)) for h in HEADER.finditer(sec)]
    for i, (_, end, name) in enumerate(headers):
        body = sec[end: headers[i + 1][0] if i + 1 < len(headers) else len(sec)]
        hm = HEAD.search(body)
        head = (hm.group(1) + hm.group(2)) if hm else ''
        for s in SENSE.findall(body):
            page.senses.append(Sense(name, s, parse_marks(s), head))
    return page


def _open(path: Path):
    return bz2.open(path, 'rb') if path.suffix == '.bz2' else path.open('rb')


def iter_pages(path: Path, titles: Iterable[str] | None = None) -> Iterator[WikiPage]:
    """Pàgines de l'espai principal amb secció catalana (opcionalment filtrades)."""
    wanted = set(titles) if titles is not None else None
    with _open(path) as fh:
        context = ET.iterparse(fh, events=('start', 'end'))
        _, root = next(context)
        for event, el in context:
            if event != 'end' or not el.tag.endswith('}page'):
                continue
            ns = el.tag[:-len('page')]
            if el.findtext(ns + 'ns') == '0':
                title = el.findtext(ns + 'title') or ''
                if wanted is None or title in wanted:
                    text = el.findtext(f'{ns}revision/{ns}text') or ''
                    page = parse_ca_section(title, text)
                    if page is not None:
                        yield page
            el.clear()
            root.clear()
