"""Escriptura determinista de fitxers de text (UTF-8 sense BOM, finals \\n)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence


def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as fh:
        for line in lines:
            if '\n' in line or '\r' in line:
                raise ValueError(f'línia amb salt de línia: {line!r}')
            fh.write(line + '\n')


def write_tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    def fmt(row):
        cells = [str(c) for c in row]
        for c in cells:
            if '\t' in c:
                raise ValueError(f'cel·la amb tabulador: {c!r}')
        if len(cells) != len(header):
            raise ValueError(f'fila amb {len(cells)} columnes, se n\'esperaven {len(header)}')
        return '\t'.join(cells)
    write_lines(path, ['\t'.join(header), *(fmt(r) for r in rows)])


def read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    lines = path.read_text(encoding='utf-8').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    header = lines[0].split('\t')
    return header, [ln.split('\t') for ln in lines[1:]]
