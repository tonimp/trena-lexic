# Dades lèxiques de Trena

Aquest repositori conté les dades lèxiques del joc de paraules Trena i les eines que les
generen. Les llistes de paraules deriven del diccionari `catalan-dict-tools` de Softcatalà,
que segueix la normativa de l’Institut d’Estudis Catalans, i les pistes deriven de les
definicions del Viquidiccionari o són de redacció pròpia.

Es publica per complir la llicència LGPL de les dades de Softcatalà: qualsevol persona pot
obtenir, modificar i tornar a generar les dades que fa servir el joc, i substituir-les a
l’aplicació per una versió modificada.

## Contingut

| Ruta | Contingut |
|---|---|
| `assets/lexicon/accepted.tsv` | Llista blanca: totes les formes que el joc accepta com a intent |
| `assets/lexicon/solutions.tsv` | Candidates a solució, amb freqüència i banda de dificultat |
| `assets/lexicon/blacklist.tsv` | Llista negra: formes vetades (malsonants, ofensives, sensibles…) |
| `assets/lexicon/clues.tsv` | Pistes de les paraules (columna `source`: pàgina del Viquidiccionari o `pròpia`) |
| `assets/lexicon/seasons/`, `assets/lexicon/themes/` | Pistes dels reptes de temporada i de les temàtiques |
| `assets/lexicon/apres.tsv` | Paraules poc freqüents de la targeta «Has après» |
| `assets/lexicon/daurades.tsv` | Paraules daurades dels nivells |
| `assets/lexicon/manifest.json` | Versions de les fonts, recomptes i sumes de verificació de cada fitxer |
| `assets/credits/lexic.json` | Crèdits i llicències tal com els mostra el joc |
| `assets/licenses/` | Textos de les llicències |
| `tool/` | Programes del procés, dades d’entrada revisades a mà (`tool/data/`) i tests |
| `test/data/` | Vectors de normalització i formes que mai no poden ser solució |
| `docs/LEXIC.md` | Documentació tècnica (en castellà): fonts, criteris d’inclusió i d’exclusió, normalització, formats i reproducció |

## Llicències

| Fitxers | Llicència |
|---|---|
| `accepted.tsv`, `solutions.tsv`, `blacklist.tsv`, `apres.tsv`, `daurades.tsv` i `manifest.json` (dins d’`assets/lexicon/`), i la mostra de `tool/tests/fixtures/dict-tools/` | LGPL 2.1 o posterior (obra derivada de `catalan-dict-tools`; vegeu `LICENSE`) |
| `assets/lexicon/clues.tsv` i les pistes de `assets/lexicon/seasons/` i `assets/lexicon/themes/` | CC BY-SA 4.0 (vegeu `assets/licenses/CC-BY-SA-4.0.txt`) |
| Pistes de redacció pròpia i correccions de pistes: `tool/data/clues_authored/`, `tool/data/clue_overrides.tsv`, els `clues.tsv` de `tool/data/seasons/` i `tool/data/themes/`, i la revisió `tool/data/daurades_reviews.tsv` | CC BY-SA 4.0 |
| `tool/tests/fixtures/mini-dump.xml` (mostra del Viquidiccionari) | CC BY-SA 4.0 |
| Programes i la resta de fitxers | LGPL 2.1 o posterior (vegeu `LICENSE`) |

Fonts i autoria:

- Softcatalà, `catalan-dict-tools`: llista de paraules, flexió i freqüències. Avisos de
  drets d’autor originals: `Copyright (C) 2013- Jaume Ortolà` i
  `Copyright (C) 2002-2008 Joan Moratinos`. Es distribueix sota la GPL 2.0 o posterior o bé
  la LGPL 2.1 o posterior, a elecció; aquestes dades fan servir la LGPL 2.1 o posterior.
  <https://github.com/Softcatala/catalan-dict-tools>
- Viquidiccionari, obra dels col·laboradors del Viquidiccionari, sota CC BY-SA 4.0. Les pistes
  en són una adaptació automàtica (text netejat i escurçat) i es comparteixen sota la mateixa
  llicència. <https://ca.wiktionary.org/>
- Les pistes amb la font `pròpia` són de redacció original per al joc, escrites sense copiar
  cap diccionari, i es comparteixen també sota CC BY-SA 4.0.

La revisió de `catalan-dict-tools` i la data del bolcat del Viquidiccionari que s’han fet
servir són a `tool/sources.lock.json` i a `assets/lexicon/manifest.json`.

## Com es tornen a generar les dades

Cal `python3` (només la biblioteca estàndard, sense cap paquet addicional; s’ha provat amb
la versió 3.15), `git`, `bash` i connexió a internet per a la primera descàrrega.

```
bash build_all.sh
```

El procés:

1. Descarrega les fonts a `tool/.cache/` (que no es versiona) i les comprova contra
   `tool/sources.lock.json`: el diccionari de Softcatalà es fixa per la revisió de `git` i el
   bolcat del Viquidiccionari per la mida i la suma `SHA-256`. Si no coincideixen, s’atura.
2. Genera la llista negra, la llista blanca i les candidates a solució, les pistes i el
   manifest dins d’`assets/lexicon/`, i també `assets/credits/lexic.json` i `assets/licenses/`.
3. Comprova que les paraules d’`apres.tsv` i `daurades.tsv` siguin a la llista blanca i no
   siguin a la llista negra.
4. Executa els tests (`python3 -I -m unittest discover -s tool/tests -t tool`).
5. Torna a fer la construcció en un directori temporal i comprova que el resultat sigui
   idèntic byte a byte.

Si no s’ha modificat res, després del procés `git status` no ha de mostrar cap canvi. Cap
pas no executa cap fitxer de les fonts descarregades: només se’n llegeixen les dades.

Per modificar les dades, editeu els fitxers de `tool/data/` (cada entrada porta el motiu) i
torneu a executar `bash build_all.sh`. La documentació de cada fitxer és a `docs/LEXIC.md`.
Les notes de treball de les pistes de redacció pròpia es publiquen reduïdes (només hi queda la
marca `excepció=etiqueta`, l’única que fa servir el procés), perquè feien referència a puzles
concrets del joc.

### Paraules de «Has après» i paraules daurades

`assets/lexicon/apres.tsv` i `assets/lexicon/daurades.tsv` es trien a partir del banc de
puzles del joc, que no forma part d’aquest repositori perquè conté les solucions dels reptes
futurs. Es publiquen tal com els fa servir el joc, juntament amb els programes que els
generen (`tool/build_apres.py` i `tool/build_daurades.py`) i les exclusions i revisions
manuals de `tool/data/`. Aquí no es regeneren: el procés només en comprova la coherència amb
la llista blanca i en recull les sumes de verificació al manifest.

## Versions

Cada versió publicada de l’aplicació Trena correspon a una etiqueta d’aquest repositori
(per exemple, `v1.0.0`) que conté exactament les dades lèxiques que porta aquesta versió.
Per substituir-les a l’aplicació, cal reemplaçar els fitxers equivalents d’`assets/lexicon/`
del paquet del joc.
