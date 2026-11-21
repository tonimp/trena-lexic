# Datos léxicos de Trena: fuentes, criterios y reproducción

Documentación técnica del repositorio público de datos léxicos del juego Trena (resumen en
catalán en `README.md`). Describe solo lo que este repositorio construye y publica: la lista
blanca, las candidatas a solución, la lista negra, las pistas y el manifest. El banco de puzles
del juego no forma parte de este repositorio.

Regla de oro: ninguna palabra que no esté en la lista blanca generada (`accepted.tsv`) llega al
juego.

## 1. Fuentes, versiones y licencias

Fijadas en `tool/sources.lock.json`. La construcción nunca usa `HEAD` ni `latest`.

| Fuente | Versión fijada | Licencia | Uso |
|---|---|---|---|
| Softcatalà `catalan-dict-tools` (<https://github.com/Softcatala/catalan-dict-tools>) | commit `b00fcd9503cf290d5b4ef44c873b65667873593a` (2026-10-22T20:08:17+02:00) | GPL-2.0-o-posterior **o** LGPL-2.1-o-posterior (a elección). Copyright (C) 2013- Jaume Ortolà; (C) 2002-2008 Joan Moratinos | Lista blanca, flexión, frecuencias |
| Viquidiccionari (`cawiktionary`) | dump `20261001` (<https://dumps.wikimedia.org/cawiktionary/20261001/cawiktionary-20261001-pages-articles.xml.bz2>), 52 149 266 bytes, SHA-256 `70bbc80d1471f6f7369eefdfae6a3527279a0dd5f6ad22568fbf536adfe9c4e9` | CC BY-SA 4.0 | Pistas y marcas de uso (lista negra) |
| DIEC2 (<https://dlc.iec.cat>) | — | Copyright IEC | Solo consultas individuales de casos dudosos; se anota «DIEC2 (consulta individual <fecha>)» en el motivo de `tool/data/*.tsv`, nunca su contenido |

Las fuentes se tratan como **datos no fiables**: se descargan en `tool/.cache/` (ignorado por
git), solo se leen ficheros de texto, no se ejecuta ningún script suyo y todos los pasos Python
corren con `python3 -I` y solo la biblioteca estándar.

### Licencia de cada fichero

| Fichero | Licencia |
|---|---|
| `assets/lexicon/accepted.tsv`, `solutions.tsv`, `blacklist.tsv`, `apres.tsv`, `daurades.tsv`, `manifest.json` | LGPL-2.1-o-posterior (derivados de `catalan-dict-tools`) |
| `assets/lexicon/clues.tsv`, `assets/lexicon/seasons/*-clues.tsv`, `assets/lexicon/themes/*-clues.tsv` | CC BY-SA 4.0 (adaptación del Viquidiccionari y pistas de redacción propia) |
| `tool/data/clues_authored/`, `tool/data/clue_overrides.tsv`, `tool/data/seasons/*/clues.tsv`, `tool/data/themes/*/clues.tsv` | CC BY-SA 4.0 (redacción propia) |
| Programas y resto de datos de `tool/` y `test/` | LGPL-2.1-o-posterior |

Los textos de licencia están en `LICENSE` (LGPL-2.1) y `assets/licenses/`; los créditos que
muestra el juego, en `assets/credits/lexic.json`. Los datos de licencias distintas están en
ficheros separados.

## 2. Normalización y clave de cuadrícula

Implementación de referencia: `tool/lexlib/normalize.py`; vectores de prueba compartidos con el
juego en `test/data/normalization_vectors.json`.

Grafía canónica (`canonicalize`):
1. Apóstrofo tipográfico U+2019 → `'` (y después invalida).
2. Composición restringida: vocal + U+0300/U+0301/U+0308 y `c` + U+0327 → letra precompuesta
   (20 pares). No se usa NFC genérico; la construcción comprueba que, para todo el léxico, el
   resultado coincide con NFC.
3. Minúsculas con tabla propia (A–Z y `À È É Í Ï Ò Ó Ú Ü Ç`); cualquier otra letra → inválida.
4. `ŀ` (U+0140) y `Ŀ` (U+013F) → `l·`.
5. U+2027, U+2219, U+22C5 entre dos `l` → punto volado U+00B7.
6. Válida solo con `a–z à è é í ï ò ó ú ü ç` y `·` dentro de `l·l` (`l·l·l` es inválido).
   Apóstrofo, guion, espacio, dígitos, punto o letras ajenas → inválida.

Tokens: `l·l` = un token `L·L`; `à`→`A`; `è é`→`E`; `í ï`→`I`; `ò ó`→`O`; `ú ü`→`U`; `ç`→`Ç`
(letra propia, nunca `C`); el resto en mayúscula. `ll` sin punto son dos `L`.

Clave: un code point por token, `L·L` = U+013F `Ŀ` (`col·legi` → `COĿEGI`, 6 tokens). La
longitud de una palabra se mide en tokens. Los homógrafos normalizados comparten clave
(`mes`/`més` → `MES`).

## 3. Criterios de inclusión y exclusión

### 3.1 Lista blanca (`accepted.tsv`): intentos aceptados

Forma de `resultats/lt/diccionari.txt` que cumple todo:
- etiqueta no `NP*` (nombre propio), `Y` (abreviatura), `Z` (número) ni `F` (signo);
- ni forma ni lema en `fdic-to-hunspell/dades/exclusions.txt` (secciones `TOTS` y `catalan`);
- si es verbo, variante general (8.ª posición de la etiqueta en `[0CXY12]`);
- grafía ya canónica y válida (sin mayúsculas, apóstrofo, guion ni clíticos);
- presente en la expansión del Hunspell **general** `resultats/hunspell/catalan.{dic,aff}` y no
  `FORBIDDENWORD`;
- clave de 3 a 9 tokens;
- ninguna forma de su clave en la lista negra `absolute`;
- lema no extranjero: se rechazan los lemas con grafía no catalana (`FOREIGN_PATTERN` de
  `tool/build_lexicon.py`), las marcas comerciales, los lemas cuya fuente de Softcatalà es
  inglesa o coloquial, y los rechazos manuales de `tool/data/foreign_words.tsv` (`reject`).
  Excepciones revisadas en el mismo fichero: `allow` (palabra catalana con frontera de
  morfema: `tothom`, `aleshores`…) y `accept` (recogida por el DIEC2 con grafía extranjera:
  `whisky`, `jazz`, `pizza`…; válidas como intento, nunca como solución).

Los índices de homónimos del LT (`nit_1`) se eliminan al leer (`tool/lexlib/softcatala.py`).
Se admiten lemas, plurales, femeninos y formas verbales conjugadas generales. No se admiten
variantes valencianas o baleares ni entradas solo DNV en esta versión.

### 3.2 Candidatas a solución (`solutions.tsv`)

- Lemas de cualquier categoría (de los verbos, solo el infinitivo) y plurales y femeninos de
  nombres y adjetivos (`kind` = `lemma`, `plural`, `femeni`, `femeni_plural`), con su lema
  también normativo.
- En la lista blanca con la misma grafía; ni su clave ni su forma en la lista negra (ningún nivel).
- Frecuencia de la forma exacta (`frequencies/frequencies-dict-forms.txt`) ≥ 5; los lemas cuyas
  únicas fuentes sean `dsalut`, `UB` o `wiki`, ≥ 100.
- Sin grafía extranjera ni fuente de préstamo, salvo `allow` en `tool/data/foreign_words.tsv`;
  `no_solution` en ese fichero excluye préstamos sin grafía delatora.
- **Homógrafos de nombres propios**: si la forma coincide con un antropónimo o topónimo del LT y
  su frecuencia es ≥ 10 veces la de la forma hermana más frecuente del mismo lema, el recuento
  procede del nombre propio y la forma no es candidata. Excepciones revisadas en
  `tool/data/proper_nouns.tsv` (`keep`, `exclude`). Bajo ese umbral, la frecuencia usada para el
  rango se limita (la columna `freq` conserva la real).
- Rango global por frecuencia (empates por clave y grafía) y **banda de dificultad**:
  1 ≤ 5 000, 2 ≤ 12 000, 3 ≤ 20 000, 4 ≤ 25 000, 5 ≤ 40 000; rango > 40 000 no es candidata.
- Lema principal: si la forma es ella misma un lema, ese análisis; si no, el lema cuya forma de
  citación es más frecuente. `lemmas` conserva todos los lemas de la forma en el LT y `verbs`
  los verbales.
- Los lemas de `tool/data/solution_exclusions.tsv` y sus flexiones se retiran después del rango
  y la banda.

### 3.3 Lista negra (`blacklist.tsv`)

- `absolute`: insultos, sexuales explícitas, escatológicas, racistas u homófobas → ni intento ni
  solución. `sensitive`: sentido principal neutro con acepción vulgar o despectiva, o tema
  delicado (enfermedad grave, suicidio, violencia sexual, crimen y violencia extrema, ideologías
  totalitarias, esclavitud, drogas duras, anatomía sexual, prostitución) → intento sí, solución no.
- Automática: páginas del Viquidiccionari con marca `vulgar`, `vulgarisme`, `despectiu`,
  `pejoratiu`, `ofensiu`, `sexual` o `sexualitat`: `absolute` si está en la primera acepción
  catalana, `sensitive` si solo en posteriores. Lemas de Softcatalà con `vulgar` o `pejoratiu`
  en `fonts:` → `sensitive`.
- Familias derivativas: `tool/data/blacklist_roots.tsv` (`pattern`, `level`, `reason`,
  `except`): expresión regular anclada al inicio del lema que veta toda la familia, con
  excepciones para los homógrafos inocentes; cada regla se prueba también sobre el lema sin un
  prefijo derivativo (`a-`, `contra-`, `des-`, `em-`, `en-`, `es-`, `mal-`, `re-`, `sobre-`,
  `sub-`), y un patrón que empieza por `~` se busca como subcadena.
- Manual: `tool/data/blacklist_manual.tsv` (`form`, `level` = `absolute`/`sensitive`/`allow`,
  `reason` obligatorio). Prevalece sobre todo lo anterior; `allow` solo retira `sensitive`.
- Precedencia: fuentes de Softcatalà < marcas del Viquidiccionari < raíces < manual.
- Propagación con el LT completo: si la forma vetada es un lema, a todas sus formas; si no, a los
  lemas de los que es forma (salvo vetos por acepción secundaria y formas compartidas con otro
  lema no vetado, que bajan a `sensitive` o no se propagan).
- Nombres propios, siglas, abreviaturas, símbolos y formas no normativas ya quedan fuera por 3.1.

### 3.4 Pistas (`clues.tsv`)

- De la sección `{{-ca-}}` de la página del Viquidiccionari de la forma o de su lema, bajo un
  encabezado coherente con `pos`. Se toma la primera acepción seleccionable: no forma
  flexionada, no remisión, sin plantillas no reducibles ni marcas dialectales, de registro,
  arcaicas, ofensivas o figuradas.
- Limpieza: enlaces a su texto, plantillas, referencias, HTML y paréntesis fuera, mayúscula
  inicial, sin punto final, 8–80 caracteres, sin `[ ] { } | = < >`, apóstrofo tipográfico `’`.
- **Nunca revela la palabra**: se descarta si alguna palabra de la pista, normalizada a clave,
  coincide con la forma, el lema o cualquier forma del lema, o empieza por la raíz del lema
  (también por letras y quitando prefijos frecuentes); además, si contiene una palabra
  `absolute`, una palabra no normativa o anáforas («homònim», «accepció»…).
- Formas flexionadas sin pista propia: la del lema con prefijo «(plural) », «(femení) » o
  «(femení plural) », solo si la acepción del lema es representativa y la flexión está
  confirmada por el Viquidiccionari o por el LT.
- Ortografía automática (`fix_orthography`): diacríticos suprimidos en 2016, «amb la que» →
  «amb la qual», etc.
- Pasada de recuperación para las candidatas sin pista (recorte por un límite de oración seguro
  y otras categorías de la misma forma).
- Correcciones manuales: `tool/data/clue_overrides.tsv` (`replace`, `sense`, `drop`,
  `lemma_only`), que deben superar todos los filtros.
- **Pistas de redacción propia**: `tool/data/clues_authored/part-NN.tsv` (`form clue note`), con
  `source` = `pròpia`; prioridad corrección manual > Viquidiccionari > propia. Pasan los mismos
  filtros (longitud, no revelar la palabra ni su raíz, vocabulario normativo, ninguna palabra de
  la lista negra, etiqueta de flexión obligatoria según `kind`).
- **Pistas de contexto**: `tool/data/seasons/<id>/clues.tsv` y `tool/data/themes/<id>/clues.tsv`
  generan `assets/lexicon/seasons/<id>-clues.tsv` y `assets/lexicon/themes/<id>-clues.tsv`
  (redacción propia, mismos filtros; `note` = `excepció=etiqueta` declara un homógrafo cuya pista
  es la del nombre aunque el LT lo analice como flexión). En el juego tienen precedencia sobre la
  general dentro de su reto o temática.
- La ausencia de pista es válida: el juego desactiva la ayuda «Pista».

En este repositorio, las columnas `note` de las pistas de redacción propia y los comentarios de
esos ficheros se publican reducidos (solo la marca `excepció=etiqueta`): las notas de trabajo
hacían referencia a puzles concretos del banco. No intervienen en ninguna salida.

### 3.5 «Has après» y paraules daurades (`apres.tsv`, `daurades.tsv`)

Ambos ficheros se **seleccionan a partir del banco de puzles del juego**, que no forma parte de
este repositorio, y aquí se publican tal como los usa el juego:

- `apres.tsv`: palabras poco frecuentes (rareza > 8 000) que son solución de algún puzle del banco,
  con pista, fuera de la lista negra y de `tool/data/apres_exclusions.tsv`. El juego las usa para
  la tarjeta «Has après», con la definición de `clues.tsv`.
- `daurades.tsv`: para cada nivel, como máximo una de sus palabras extra (no solución), candidata
  con `kind` = `lemma`, con pista, fuera de la lista negra, de `apres.tsv` y de
  `tool/data/daurades_exclusions.tsv`.

Los programas que los generan (`tool/build_apres.py`, `tool/build_daurades.py`) y sus
exclusiones manuales se incluyen para documentar el criterio, pero necesitan el banco y no se
ejecutan aquí. `build_all.sh` comprueba que todas sus claves estén en `accepted.tsv` y no estén
en `blacklist.tsv`, y el manifest recoge sus sumas.

## 4. Formatos de `assets/lexicon/`

Todos UTF-8 sin BOM, finales `\n`, orden estable, sin marcas de tiempo.

- `accepted.tsv`: sin cabecera, una línea por clave ordenada por code point. `CLAVE` si la única
  grafía es la trivial, si no `CLAVE<TAB>grafía|grafía`. Ej.: `CASA	casa|casà`,
  `COĿEGI	col·legi|col·legí`.
- `solutions.tsv`: cabecera `key form lemma kind pos freq rank band lemmas verbs`, por `rank`.
- `blacklist.tsv`: cabecera `key form level reason`, por clave y grafía.
- `clues.tsv` y `seasons/`, `themes/`: cabecera `key form lemma clue source` (`source` = título
  de la página del Viquidiccionari o `pròpia`), por clave y grafía, una pista por grafía.
- `apres.tsv`: cabecera `key form lemma kind rarity`.
- `daurades.tsv`: cabecera `level key form lemma band`, una fila por nivel como máximo.
- `manifest.json`: `schema_version`, `normalization_version`, fuentes, y por fichero `sha256`,
  `bytes`, `lines`, `license`, `packaged`; `counts`; `lexicon_fingerprint` (SHA-256 de esquema,
  normalización, fuente de Softcatalà y entradas de `accepted.tsv`, `blacklist.tsv` y
  `solutions.tsv`; las pistas, `apres.tsv` y `daurades.tsv` no entran).

Los recuentos reales de cada versión están en `counts` de `manifest.json`.

## 5. Cómo reproducirlo

```
bash build_all.sh
```

Pasos (todos con `python3 -I`):

1. `tool/fetch_sources.py`: descarga o reutiliza `tool/.cache/` y verifica el commit de
   Softcatalà y el tamaño y SHA-256 del dump del Viquidiccionari.
2. `tool/build_blacklist.py` → `tool/build_lexicon.py` → `tool/build_clues.py` →
   `tool/build_manifest.py` (este último también escribe `assets/credits/lexic.json` y
   `assets/licenses/`).
3. Comprobación de `apres.tsv` y `daurades.tsv` contra la lista blanca y la lista negra.
4. Tests: `python3 -I -m unittest discover -s tool/tests -t tool`.
5. Segunda construcción en un directorio temporal y comparación de SHA-256: falla si no es
   reproducible.

Si no se ha modificado nada, `git status` no muestra cambios tras la construcción.

Actualizar las fuentes (acción explícita; revisar el diff del lock):

```
python3 -I tool/fetch_sources.py --update --dump-date AAAAMMDD
python3 -I tool/fetch_sources.py --update --softcatala-commit <sha completo>
```

Ficheros manuales (motivo obligatorio; la construcción falla si una entrada no es grafía
canónica, está duplicada o, en la lista negra y los extranjerismos, no existe en el LT):

| Fichero | Uso |
|---|---|
| `tool/data/blacklist_manual.tsv` | Vetos y `allow` por palabra |
| `tool/data/blacklist_roots.tsv` | Vetos por familia derivativa |
| `tool/data/foreign_words.tsv` | Extranjerismos: `allow`, `accept`, `no_solution`, `reject` |
| `tool/data/proper_nouns.tsv` | Homógrafos de nombres propios: `keep`, `exclude` |
| `tool/data/solution_exclusions.tsv` | Lemas retirados como solución |
| `tool/data/clue_overrides.tsv` | Correcciones de pistas |
| `tool/data/clues_authored/part-*.tsv` | Pistas de redacción propia |
| `tool/data/seasons/*/clues.tsv`, `tool/data/themes/*/clues.tsv` | Pistas de contexto |
| `tool/data/vocabulary_exceptions.tsv` | Nombres propios admitidos dentro de una pista |
| `tool/data/apres_exclusions.tsv`, `tool/data/daurades_exclusions.tsv`, `tool/data/daurades_reviews.tsv` | Exclusiones y revisión de §3.5 (no se usan en esta construcción) |

Regresiones: `test/data/forbidden_solutions.txt` lista formas que nunca pueden ser solución;
lo comprueba `tool/tests/test_real_lexicon.py`.

## 6. Versiones

Cada versión publicada de la app corresponde a una etiqueta de este repositorio con exactamente
los datos léxicos que incluye.
