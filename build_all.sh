#!/usr/bin/env bash
# Orquestrador del repositori públic de dades lèxiques de Trena (vegeu README.md).
#   fonts -> blacklist -> lexicon -> clues -> manifest -> comprovació d'apres/daurades
#   -> tests Python -> segona construcció en un directori temporal i comparació de SHA-256.
# `apres.tsv` i `daurades.tsv` es publiquen tal com els genera el joc: es trien a partir del
# banc de puzles, que no forma part d'aquest repositori, i aquí només es comprova que siguin
# coherents amb la llista blanca regenerada.
# Tots els passos Python s'executen amb `python3 -I`; no s'executa cap fitxer de
# tool/.cache/ (les fonts són dades no fiables).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$REPO_DIR/tool"
PY=(python3 -I)
OUT="$REPO_DIR/assets/lexicon"
ASSETS="$REPO_DIR/assets"

build() {
  local out="$1" assets="$2"
  "${PY[@]}" "$TOOL_DIR/build_blacklist.py" --out-dir "$out"
  "${PY[@]}" "$TOOL_DIR/build_lexicon.py" --out-dir "$out"
  "${PY[@]}" "$TOOL_DIR/build_clues.py" --out-dir "$out"
  "${PY[@]}" "$TOOL_DIR/build_manifest.py" --out-dir "$out" --assets-dir "$assets"
}

check_published() {
  # Cada paraula d'apres.tsv i daurades.tsv ha de ser a la llista blanca (accepted.tsv) i
  # no pot ser a la llista negra.
  "${PY[@]}" - "$1" <<'PYEOF'
import sys
from pathlib import Path

d = Path(sys.argv[1])
accepted = {line.split('\t')[0] for line in
            (d / 'accepted.tsv').read_text(encoding='utf-8').splitlines() if line}
black = {line.split('\t')[0] for line in
         (d / 'blacklist.tsv').read_text(encoding='utf-8').splitlines()[1:] if line}
bad = []
for name in ('apres.tsv', 'daurades.tsv'):
    lines = (d / name).read_text(encoding='utf-8').splitlines()
    col = lines[0].split('\t').index('key')
    for n, line in enumerate(lines[1:], start=2):
        key = line.split('\t')[col]
        if key not in accepted or key in black:
            bad.append(f'{name}:{n}: {key}')
if bad:
    sys.exit('Paraules publicades fora de la llista blanca o a la llista negra:\n  '
             + '\n  '.join(bad))
print('  apres.tsv i daurades.tsv: coherents amb accepted.tsv i blacklist.tsv')
PYEOF
}

echo "== 1. Fonts"
"${PY[@]}" "$TOOL_DIR/fetch_sources.py"

echo "== 2. Construcció"
build "$OUT" "$ASSETS"
check_published "$OUT"

echo "== 3. Tests Python"
(cd "$REPO_DIR" && "${PY[@]}" -m unittest discover -s tool/tests -t tool)

echo "== 4. Reproductibilitat"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/assets/lexicon"
cp "$OUT/apres.tsv" "$OUT/daurades.tsv" "$TMP/assets/lexicon/"
build "$TMP/assets/lexicon" "$TMP/assets" > /dev/null
status=0
for f in accepted.tsv solutions.tsv blacklist.tsv clues.tsv manifest.json \
         $(cd "$OUT" && ls seasons/*-clues.tsv themes/*-clues.tsv 2>/dev/null); do
  a="$(shasum -a 256 "$OUT/$f" | cut -d' ' -f1)"
  b="$(shasum -a 256 "$TMP/assets/lexicon/$f" | cut -d' ' -f1)"
  if [[ "$a" == "$b" ]]; then
    echo "  igual  $a  $f"
  else
    echo "  DIFERENT  $f ($a != $b)"; status=1
  fi
done
for f in credits/lexic.json licenses/LGPL-2.1.txt licenses/CC-BY-SA-4.0.txt; do
  cmp -s "$ASSETS/$f" "$TMP/assets/$f" || { echo "  DIFERENT  $f"; status=1; }
done
if [[ $status -ne 0 ]]; then
  echo "ERROR: la construcció no és reproduïble" >&2
  exit 1
fi
echo "== Fet: assets/lexicon regenerat i reproduïble"
echo "   Comproveu amb «git status» que no hi ha canvis respecte de la versió publicada."
