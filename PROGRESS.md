# PROGRESS.md

Registro de avance del proyecto, mantenido por sesión de trabajo. Ver
`CLAUDE.md` para el contexto de diseño completo y las restricciones no
negociables.

## 2026-08-16 — Sesión de diseño y scaffold inicial

**Decidido:**
- Scope: aditivos alimentarios en reevaluación, Reglamento UE 257/2010.
- Arquitectura: OpenFoodTox (estructurado) + PDFs (narrativo) → LangGraph
  4 nodos → servidor MCP + UI Streamlit.
- Corpus verificado: 118 dictámenes únicos, filtro por dominio + patrón
  de título (no por campo de regulación, ver CLAUDE.md). **Corregido en
  sesión posterior (16-ago-2026, ver más abajo): 136 -- el filtro de
  dominio a secas excluía 18 dictámenes reales mal etiquetados.**
- Cadena de joins del Nodo 3 verificada con caso aspartamo.
- Cliente LLM intercambiable, DeepSeek V4-Flash como backend de
  producción, Ollama como alternativa local documentada.
- Regla de comunicación de riesgo del Nodo 4 fijada como constante de
  código, no como sugerencia de prompt.
- Descartado explícitamente: integración de PubMed, refresco en tiempo
  real, cambio de dominio del proyecto.
- Modelo de despliegue: índice de Chroma horneado en el repo (Opción A),
  sin reindexado en caliente en producción.
- Protección de presupuesto: límite global diario en USD (real) + límite
  por IP (solo UX, no protección real).

**Implementado:**
- `ingestion/openfoodtox.py` completo.
- `graph/llm_client.py` completo (interfaz + DeepSeek + Ollama).
- `graph/nodes.py`: Nodo 3 y Nodo 1 implementados. Nodo 2 y Nodo 4
  pendientes de conectar (contratos definidos, `NotImplementedError`).
- `ui/app.py`: candado de refresco 24h + límites de consulta.
- Test de regresión del caso aspartamo (se salta sin el xlsx real).

**Pendiente / sin resolver (ver CLAUDE.md, sección "Estado del código"
para la lista completa y priorizada):**
- Nodo 4 sin conectar al LLM todavía.
- QA del corpus de 136 dictámenes contra fuente oficial no cerrado.
- Lookup de sustancias en Nodo 1 no maneja español ni E-numbers.
- Sin PDFs descargados, sin vector store, Nodo 2 bloqueado por esto.
- Sin servidor MCP.
- Sin desplegar.

## 2026-08-16 (sesión 2) — Conectar Nodo 4, ADI ligado al dossier vigente, fix de coste DeepSeek

**Contexto de partida de esta sesión:** `graph/llm_client.py`, que la
entrada anterior daba por "completo", no existía en el repo (ni
commiteado, ni en stash) -- se quedó sin llegar a `git add` en la sesión
anterior. `graph/nodes.py` ya importaba `LLMClient` desde ese módulo
inexistente sin commitear, así que el paquete daba `ImportError` al
arrancar esta sesión. El usuario recreó `llm_client.py` durante la
conversación (interfaz `LLMClient` + `DeepSeekClient` + `OllamaClient`,
igual que describe CLAUDE.md); a partir de ahí se conectó el Nodo 4.

**Implementado:**
- `graph/nodes.py::generate_answer_node` conectado a
  `deps.llm_client.complete(...)`. System prompt =
  `NODE_4_GROUNDING_RULES` (nuevo -- reglas de fundamentación: no
  inventar valores, citar siempre, degradar con gracia si
  `retrieved_chunks` viene vacío, admitir si no hay dictamen vigente) +
  `NODE_4_SAFETY_COMMUNICATION_RULES` (sin tocar). User prompt =
  `_build_user_prompt`, combina `user_query` + `substance_name` +
  `structured_result` formateado + `retrieved_chunks` (o aviso explícito
  de que el corpus de PDFs no está indexado si viene vacío).
- `ingestion/openfoodtox.py::current_reference_value_opinion` ampliado:
  además de los metadatos de citación, ahora extrae y devuelve el ADI
  (`adi_value` + `adi_unit`) y la justificación (`adi_justification`,
  texto libre de `JustificationAndComments`) ligados AL REGISTRO
  concreto de `FLEX_SUM.ToxRefValues` que originó el dossier identificado
  como vigente -- no un ADI cualquiera de la sustancia. No existe un
  campo estructural `CriticalEndpoint` separado confirmado; se usa
  `JustificationAndComments` como candidato más cercano, sin inventar un
  campo más específico.
  - Nombres de columna (`ADI_LOWER_VALUE_COLUMN`, `ADI_UNIT_COLUMN`,
    `ADI_JUSTIFICATION_COLUMN`) confirmados por el usuario de memoria de
    una sesión anterior, **no releídos carácter a carácter contra el
    xlsx real en esta sesión** (no había export en `data/raw/`). Test
    nuevo `test_flex_sum_toxref_has_expected_adi_columns` en
    `tests/test_openfoodtox_joins.py` valida esto automáticamente en
    cuanto el xlsx esté presente -- sigue en `SKIPPED` por ahora.
  - `test_aspartame_current_opinion_is_2013_reevaluation` ampliado:
    ahora también comprueba `adi_value == 40.0`, `adi_unit` contiene
    "mg/kg", `adi_justification` no vacío. También sigue `SKIPPED` sin
    el xlsx real.
- `graph/nodes.py::_format_structured_result` actualizado para incluir
  ADI y justificación en el bloque de contexto que se envía al LLM, con
  instrucción inline explícita de tratar `adi_justification` como cita
  textual, no como razonamiento propio del modelo.
- **Hallazgo de coste real, no solo de diseño:** llamando de verdad a la
  API con el prompt del Nodo 4 (caso aspartamo, datos de ADI ficticios
  para la prueba), la primera llamada con `max_tokens=800` (default)
  salió truncada/vacía. Causa raíz: DeepSeek V4 activa "thinking"
  (esfuerzo "high") por defecto, que consume `reasoning_content` contra
  el mismo `max_tokens` e ignora `temperature` silenciosamente. Fix:
  `DeepSeekClient.complete()` ahora pasa `extra_body={"thinking":
  {"type": "disabled"}}`. Repetido el mismo caso de prueba tras el fix:
  365 tokens de salida (antes 799 con thinking activo), respuesta
  completa dentro del default de 800, sin necesidad de subirlo, y
  cumpliendo los 4 criterios de revisión del usuario (sin frase
  prohibida de superar el ADI, margen de seguridad explicado como
  factor×NOAEL y no como umbral, justificación tratada como cita, y
  advertencia -- dada por mí, no por el modelo -- de que era un dato de
  ejemplo). Documentado en CLAUDE.md, sección "Decisiones de arquitectura
  ya tomadas", para que no se reactive sin darse cuenta del coste.
- CLAUDE.md actualizado: nuevo bullet sobre "thinking" desactivado +
  nota en el bullet de precio de referencia de que la estimación
  $0.001-0.002/consulta asume "thinking" desactivado (con "thinking"
  activo el coste real habría sido ~2-3x el estimado).

**Pendiente / sin resolver:**
- **Ninguno de los cambios de esta sesión está validado contra el xlsx
  real de OpenFoodTox** -- no había export en `data/raw/` en ningún
  momento de la sesión. Antes de confiar en `adi_value`/`adi_unit`/
  `adi_justification` para una demo real: colocar el xlsx en
  `data/raw/OFT3_0_export_repository.xlsx` y correr
  `pytest tests/test_openfoodtox_joins.py -v` -- si
  `test_flex_sum_toxref_has_expected_adi_columns` falla, corregir las
  constantes de columna en `ingestion/openfoodtox.py` antes de tocar
  nada más.
- CLAUDE.md, sección "Estado del código", quedó desactualizada por esta
  sesión (sigue diciendo que el Nodo 4 es `NotImplementedError` y que
  `llm_client.py` ya estaba completo desde antes) -- no se tocó esa
  sección porque no se pidió explícitamente, pero conviene refrescarla
  la próxima vez que se edite CLAUDE.md.
- Nodo 2 (retrieval híbrido) sigue sin implementar -- `retrieved_chunks`
  seguirá vacío en cualquier prueba real hasta que haya PDFs descargados
  + chunking + embeddings + Chroma. El Nodo 4 está diseñado para
  degradar con gracia en ese caso (ver `NODE_4_GROUNDING_RULES`), pero
  no se ha probado con fragmentos narrativos reales todavía.
- Nodo 1 (extracción de entidad) y su limitación de lookup en inglés
  exacto: sin cambios esta sesión.
- QA del corpus de 136 dictámenes (cifra corregida en la sesión
  siguiente, ver abajo), servidor MCP, deploy: sin cambios esta sesión,
  siguen pendientes como en la entrada anterior.

## 2026-08-16 (sesión 3) — discussion_text/is_boilerplate, bug de dominio mixto en Nodo 3, corpus 118→136

**Contexto de partida:** el usuario proporcionó el xlsx real de
OpenFoodTox en `data/raw/OFT3_0_export_repository.xlsx`, permitiendo por
primera vez validar contra datos reales todo lo construido en las
sesiones 1 y 2 sobre memoria/suposiciones.

**Implementado:**
- **Bug real encontrado y corregido en `ingestion/openfoodtox.py`:**
  las cuatro cargas de hoja usaban `pd.read_excel(..., header=1)`
  cuando la cabecera real está en la primera fila (`header=0`) --
  rompía cualquier acceso por nombre de columna. Relacionado:
  `LiteratureReference.DateOfEvaluation` llega como `str` 'YYYY-MM-DD',
  no `date`; se parsea ahora con `_parse_iso_date()`.
- **`OpinionReference` ampliado con `discussion_text` +
  `discussion_is_boilerplate`** (texto de `END_SUM.Discussion.Discussion`
  ligado al dossier vigente). Heurístico de boilerplate validado en
  datos: `len < 280` caracteres, O duplicado exacto del mismo texto en
  ≥2 dossiers distintos (detectado dinámicamente, no hardcodeado).
  Investigación completa documentada en CLAUDE.md, incluida la
  corrección de una estimación anterior propia (81% de cobertura
  narrativa real → 32,2% real, el detector de boilerplate usado antes
  era demasiado estrecho). `nodes.py::_format_structured_result`
  actualizado para omitir el texto si es boilerplate, o incluirlo con
  matización explícita de que no está confirmado como razonamiento
  científico si no lo es.
- **Bug de dominio mixto en `current_reference_value_opinion`,
  encontrado y corregido:** el heurístico `MAX(fecha)` no filtraba por
  `Domain.FoodDomain`, así que para una sustancia con candidatos
  'EFSA opinion' de dos programas regulatorios distintos (ej. propil
  gallato E 310: aditivo alimentario 2014 vs. seguridad como aditivo de
  PIENSO ANIMAL 2020, FEEDAP), podía devolver el dictamen equivocado.
  Verificado que no era un caso aislado: 29 de 102 sustancias del
  corpus de reevaluación (28,4%) tenían candidatos de dominio mixto.
  Fix: filtrar por `Domain.FoodDomain == 'food additives'` O rescate de
  dictámenes reales mal etiquetados (título contiene "food additive" Y
  "re-evaluation" a la vez -- ninguna de las dos frases sola es segura,
  ver más abajo). Lógica extraída a una función compartida
  (`_is_mistagged_food_additive_reevaluation`) usada tanto aquí como en
  `reevaluation_dossiers()`, para no repetir la divergencia entre las
  dos implementaciones que ya se había dado una vez.
  - Tests de regresión nuevos: propil galato (bloquea que vuelva un
    candidato de dominio ajeno) y plata E 174 (bloquea que el fix se
    vuelva demasiado estricto y excluya un follow-up real mal
    etiquetado -- ver punto siguiente).
  - **Casi-error evitado antes de aplicar el fix, verificado con datos:**
    un filtro más simple (exigir "food additive" en el título, sin más)
    habría sido inseguro -- 1.360 dictámenes de Flavouring Group
    Evaluation contienen esa frase por el nombre del panel evaluador
    ("Panel on Food Additives, Flavourings..."), sin ser reevaluaciones
    de aditivos. Y forzar "re-evaluation" también en la rama de dominio
    ya correcto habría roto el caso del dióxido de titanio (E 171): el
    dictamen que de hecho lo declaró no seguro (2021, dominio correcto)
    no contiene esa palabra. Ambos descartados solo tras comprobarlo
    contra el corpus completo, no por intuición.
- **Corpus corregido: 118 → 136 dictámenes de reevaluación.** El mismo
  problema de dominio mal etiquetado afectaba a
  `reevaluation_dossiers()`/`unique_reevaluation_opinions()` -- 18
  dictámenes reales (acesulfamo K E950, sacarina E954, eritritol E968,
  neotamo E961, plata E174 y 13 más) quedaban fuera del corpus de 118
  por el mismo motivo. Validado contra el xlsx completo sin falsos
  positivos de dominio (distribución del corpus resultante: 118 'food
  additives' + 16 'other:' + 1 'nutrient sources' + 1 sin dominio = 136,
  cero de 'flavourings'/'feed'). Cifra actualizada en CLAUDE.md,
  `docs/efsa-rag-proyecto.html`, este archivo, y el umbral del test de
  regresión del corpus.

**Pendiente / sin resolver:**
- ~~La tabla de cobertura de `discussion_text` recalculada sobre 136~~ --
  **cerrado.** Recalculada sobre el corpus corregido de 136: 29,4%
  (40/136) con al menos una fila no marcada como boilerplate, 64,0%
  (87/136) solo boilerplate, 6,6% (9/136) sin ninguna fila de
  `Discussion`. Documentado en CLAUDE.md ("Estado del código" y
  "Hallazgos verificados"). La cifra de 32,2% mencionada más arriba en
  esta misma entrada era la del corpus de 118 pre-fix, ya superada.
- **Investigación pendiente, pedida por el usuario al final de la
  sesión 3 y NO realizada todavía** (verificado en esta sesión: no hay
  commit, script, test ni entrada de PROGRESS.md posterior que la
  cubra -- solo quedó documentado el caso puntual, no la investigación
  agregada): cuántas sustancias más del corpus de 136, además del
  dióxido de titanio (E 171), tienen la misma divergencia entre
  `current_reference_value_opinion` (dictamen vigente correcto, sin
  exigir `REEVAL_TITLE_MARKER` en el título) y `reevaluation_dossiers()`
  (que sí exige esa palabra y por tanto puede estar usando como
  "dictamen del corpus" una versión superada de una sustancia cuyo
  dictamen vigente real no contiene "re-evaluation"). Pendiente: escribir
  un script/test que, para cada sustancia del corpus, compare el
  `DOSSIER UUID` que devuelve `current_reference_value_opinion` contra
  el que aparece en `reevaluation_dossiers()`, y cuente los casos en que
  difieren.
- El campo `HumanHealthHazardCharacteristics.AcceptableDailyIntake.CriticalEndpoint`
  sigue investigado y descartado (ver CLAUDE.md) -- no se ha vuelto a
  tocar esta sesión.
- Nodo 2, Nodo 1 (lookup español/E-numbers), servidor MCP, deploy: sin
  cambios esta sesión.

## 2026-08-17 — Investigación de alcance de la divergencia TiO2

**Contexto de partida:** al final de la sesión anterior quedó pendiente
(y sin hacer, confirmado al revisar el commit único que cubre las
sesiones 2-3, el comentario en `ingestion/openfoodtox.py` y CLAUDE.md --
ninguno tenía el recuento agregado) investigar cuántas sustancias más
del corpus tienen la misma divergencia que dióxido de titanio (E171)
entre `current_reference_value_opinion()` y `reevaluation_dossiers()`.

**Investigado (solo diagnóstico, sin tocar código todavía):**
- De 233 sustancias del corpus con ADI/TDI ligado a un dossier de
  `reevaluation_dossiers()`, **7 (3,0%) divergen** -- ver CLAUDE.md,
  "Hallazgos verificados", para la lista completa y los patrones de
  título.
- **6 son solo laguna de cobertura del corpus** (dato de ADI/vigencia
  correcto, dominio y regulación correctos, simplemente el título no
  contiene "re-evaluation" así que `reevaluation_dossiers()` no los
  cuenta como parte de los 136): titanio E171, propionato sódico E281,
  rojo remolacha E162, beta-caroteno E160a, beta-apo-8'-carotenal
  E160e, Allura Red AC E129.
- **1 es un bug real de Nodo 3, no solo de cobertura: Sunset Yellow FCF
  (E110).** El dossier que gana por `MAX(fecha)` es de 2022, sobre un
  aditivo de PIENSO ANIMAL ("for cats and dogs, ornamental fish...",
  `Domain.Regulation == 'Regulation (EC) No 1831/2003'`) pero mal
  etiquetado `Domain.FoodDomain == 'food additives'` -- el filtro
  actual no lo detecta porque solo mira `Domain.FoodDomain`. Devolvería
  al usuario un ADI/dictamen del contexto regulatorio equivocado
  (pienso animal, no alimentación humana), no solo un dictamen viejo.

**Alcance del bug de Sunset Yellow FCF investigado y cerrado (misma
sesión):** escaneadas las 507 filas de `DOSSIER` con
`Domain.FoodDomain == 'food additives'` en todo el dataset (no solo las
233 sustancias con ADI ligado al corpus). Solo **2 filas (0,4%)**
tienen señal de mal-etiquetado inverso (`Domain.Regulation` de pienso
animal `1831/2003` + lenguaje de especies animales en el título --
ambas señales coinciden en las mismas 2 filas, ninguna añade casos por
separado), y **las dos materializan el bug de verdad** (ganan
`MAX(fecha)` para su sustancia):
1. Sunset Yellow FCF (E110) -- ya descrito arriba.
2. **Nuevo: "Olive leaf dry extract from O. europaea L."** -- a
   diferencia de Sunset Yellow FCF, esta sustancia no tiene NINGÚN
   dictamen alimentario real en el dataset -- su única fila en
   `DOSSIER` es el dossier de pienso animal mal etiquetado. No es un
   caso de "dictamen real desplazado", sino de una sustancia que no es
   un aditivo alimentario en absoluto pudiendo presentarse como tal si
   se consulta por nombre exacto.
- Verificación adicional (título con la palabra suelta "feed", sin
  exigir coincidencia de regulación): no aparecen más filas aparte de
  estas 2 y las 5 del Statement de Allura Red AC (que es Grupo A, no
  Grupo B -- regulación y dominio correctos, solo le falta el marcador
  de título).
- **Conclusión: el patrón inverso es real pero raro (2/507, 0,4%), no
  sistémico** como el mistag en la otra dirección (18 dossiers
  rescatados). Documentado en CLAUDE.md, "Hallazgos verificados".

**Fix de Grupo B implementado (misma sesión, tras el diagnóstico):**
`current_reference_value_opinion` (`ingestion/openfoodtox.py`) ahora
excluye de los candidatos cualquier dossier cuyo `Domain.Regulation`
contenga `"1831/2003"` (regulación de pienso animal, FEEDAP) --
constante `ANIMAL_FEED_REGULATION_MARKER` -- independientemente de
`Domain.FoodDomain`. Señal estructural en vez de texto de título,
verificada con los dos casos reales:
- Sunset Yellow FCF (E110): pasa a resolver al dictamen de 2014-06-26
  ("Reconsideration of the temporary ADI and refined exposure
  assessment...") en vez del dossier de pienso animal de 2022.
- "Olive leaf dry extract from O. europaea L.": pasa a devolver `None`
  (correcto -- no tiene ningún dictamen alimentario real). El manejo de
  `None` aguas abajo (Nodo 3 marca `vigencia_ambigua=True`, Nodo 4
  responde explícitamente que no hay dictamen vigente en vez de
  inventar relevancia) ya estaba bien implementado, no hizo falta
  reforzarlo.
- 2 tests de regresión nuevos en `tests/test_openfoodtox_joins.py`
  (`test_sunset_yellow_current_opinion_excludes_feed_regulation_dossier`,
  `test_olive_leaf_extract_has_no_real_food_additive_opinion`). Los 6
  tests previos siguen en verde -- **8/8 pasan** tras el fix.
- Detalle completo (incluida la justificación de por qué 2014 y no 2009
  para Sunset Yellow FCF) en CLAUDE.md, "Hallazgos verificados".

**Grupo A cerrado (misma sesión, tras el fix del Grupo B):** para cada
uno de los 4 patrones de título identificados como sinónimos de
"re-evaluation" (`"extension of use"`, `"statement on"`,
`"reconsideration of the ADI"`, `"safety assessment... as a food
additive"`), se probó su alcance de falsos positivos contra las 11.613
filas COMPLETAS de `DOSSIER` (no solo dentro de `food additives`) antes
de aceptarlo:
- `"extension of use"`: 42 en todo el dataset, con fugas reales a novel
  foods (Reglamento (UE) 2015/2283) y pienso animal si no se acota.
- `"statement on"`: 62-75 en todo el dataset, el más amplio -- fugas
  reales a pesticidas, contaminantes de procesado, materiales en
  contacto con alimentos y `flavourings` si no se acota.
- `"reconsideration of the ADI"`: 1 en todo el dataset (beta-apo-8'-
  carotenal) -- sin riesgo.
- `"safety assessment... as a food additive"`: 3 filas / 2 títulos
  únicos en todo el dataset (TiO2 + un caso nuevo, aceites minerales) --
  sin riesgo.

**Los 4, combinados con `Domain.FoodDomain == 'food additives'` Y NOT
`Domain.Regulation` contiene `'1831/2003'` (misma exclusión del fix del
Grupo B), quedan sin ninguna fuga de dominio ajeno** -- verificado sin
overlap con las filas ya capturadas por el filtro anterior, así que la
exclusión no cambia ningún resultado previo. Implementados en
`ingestion/openfoodtox.py` como `ADDITIONAL_REEVAL_TITLE_PATTERNS` +
`SAFETY_ASSESSMENT_FOOD_ADDITIVE_PATTERN`, usados en
`reevaluation_dossiers()`.

**Corpus recalculado: 136 → 162 dictámenes únicos.** Verificado que los
6 dictámenes vigentes del Grupo A (TiO2, propionato sódico, rojo
remolacha, beta-caroteno, beta-apo-8'-carotenal, Allura Red AC) quedan
ahora dentro del corpus. Cifra actualizada en CLAUDE.md,
`docs/efsa-rag-proyecto.html` y el umbral del test de tamaño del corpus
(130 → 150). Nuevo test de regresión
`test_group_a_substances_current_opinion_is_in_reevaluation_corpus` en
`tests/test_openfoodtox_joins.py` -- **9/9 tests pasan** tras ambos
fixes (Grupo A + Grupo B) de esta sesión.

**Tabla de cobertura de `discussion_text` recalculada (misma sesión,
tras el cierre del Grupo A):** sobre los 162 dictámenes, **25,3%
(41/162)** tienen al menos una fila de `Discussion.Discussion` no
marcada como boilerplate -- baja desde 29,4% (40/136) porque 25 de los
26 dictámenes nuevos que entraron con el cierre del Grupo A aportan
solo boilerplate (solo 1 aporta contenido no-boilerplate nuevo), mismo
mecanismo que la vez anterior (118→136 también bajó el porcentaje
aunque subiera el número absoluto). Desglose completo: 9 (5,6%) sin
ninguna fila de `Discussion`, 112 (69,1%) con discusión pero toda
boilerplate, 41 (25,3%) con al menos una fila sustantiva. Actualizado
en CLAUDE.md, "Estado del código".

**Verificado el caso límite de "sucrose esters...in flavourings" (misma
sesión, a petición del usuario antes de dar el Grupo A por cerrado):**
es un VERDADERO POSITIVO, no un falso positivo de dominio `flavourings`
-- confirmado con `Domain.FoodDomain == 'food additives'` (fila única,
sin duplicado en `flavourings`), `Domain.ExpertGroup == 'EFSA ANS'` (el
panel de aditivos, no CEF/flavourings), regulación real (178/2002), y
sustancia confirmada como "Sucrose esters of fatty acids" (E473), un
aditivo alimentario real. La palabra "flavourings" en el título describe
el USO propuesto (extender el uso a preparados aromatizantes), no el
panel evaluador. No hace falta excluirlo.

**Al verificarlo se encontró un problema más importante: el enfoque de
patrones de título tiene un límite estructural (whack-a-mole
confirmado empíricamente).** E473 resultó tener sus 4 dictámenes reales
(2004, 2010, 2012, 2017) SIN la palabra "re-evaluation" en ninguno --
el vigente real (2017, "Refined exposure assessment...") no coincide
con ningún patrón aceptado (dice "refined", no "safety", assessment).
Ampliando la comprobación, se encontraron **6 sustancias en total**
donde la sustancia SÍ tiene algún dossier en el corpus de 162, pero su
dictamen REALMENTE vigente (`current_reference_value_opinion`) no está
capturado:

| Sustancia | Vigente real no capturado | Por qué falla el patrón |
|---|---|---|
| Sucrose esters of fatty acids (E473) | 2017, "Refined exposure assessment..." | "refined", no "safety" assessment |
| **Sunset Yellow FCF (E110)** | 2014, "Reconsideration of the **temporary** ADI..." | "temporary" insertado rompe el substring `"reconsideration of the adi"` |
| Rosemary extract liquid (E392) | 2018, "Refined exposure assessment..." | mismo problema que E473 |
| Steviol glycosides (E960) | 2020, "...amendment of the specifications..." | frase distinta, sin patrón |
| Calcium lignosulphonate (40-65) | 2010, "...carrier for vitamins and carotenoids" | frase distinta, dudoso si es aditivo |
| Lycopene | 2008, "Use of lycopene as a food colour" | frase distinta, sin patrón |

Notable: Sunset Yellow FCF es la misma sustancia arreglada en el fix
del Grupo B de esta sesión -- el fix corrigió que ya no gane el
dossier de pienso animal, pero el documento que debería ganar tras esa
corrección (2014) sigue sin estar en el corpus. **Confirma que seguir
añadiendo patrones de título uno a uno no converge** -- cada patrón
nuevo revela una variante de redacción distinta, incluida una
regresión parcial sobre un caso ya arreglado.

**Diagnóstico del enfoque híbrido (sustancia-primero, sin patrón de
título) -- probado, NO adoptado:** se probó redefinir el corpus como
"un documento por sustancia, el vigente según `current_reference_value_opinion`
(dominio `food additives` + NOT regulación pienso animal, sin exigir
ningún patrón de título)" en vez de filtrar filas de `DOSSIER` por
título. Resultado sobre las 4.476 sustancias con algún registro
ADI/TDI en todo el dataset:
- 317 sustancias resuelven un vigente con ese filtro (186 documentos
  únicos por título) -- **muy por encima de las 162 del corpus actual
  y del programa real de reevaluación.**
- Comparado con el corpus de 162 por título: 130 en común, **56 SOLO
  en el híbrido, 32 SOLO en el corpus de 162 (el híbrido los pierde).**
- **De las 56 nuevas, solo 6 son los casos genuinos de la tabla de
  arriba -- las ~50 restantes son dictámenes de PRIMERA autorización o
  cambio de especificación de aditivos que NUNCA fueron parte del
  programa de reevaluación** (Advantame, Monk fruit extract, buffered
  vinegar, green tea catechins, monacolins en arroz de levadura roja,
  Ephedra, cloruro de metacrilato, trimagnesio dicitrato, formaldehído
  como conservante, decenas de "Opinion... on a request from the
  Commission related to..." del panel AFC antiguo -- primeras
  autorizaciones bajo Directivas pre-1333/2008, no reevaluaciones).
- **De las 32 que el híbrido pierde, la mayoría son reevaluaciones
  reales y centrales del programa** -- goma acacia E414, lecitinas
  E322, goma garrofín E410, PGPR E476, propano-1,2-diol E1520,
  sacarina E954, goma laca E904, sílice E551, **el "Re-evaluation of
  titanium dioxide (E171)" de 2016 original** (TiO2 sigue en el
  híbrido, pero solo vía su documento de 2021, no el de 2016), goma
  xantana E415, Allura Red AC E129, Indigo Carmine E132, **el
  "re-evaluation" de 2009 original de Sunset Yellow FCF**, rojo
  remolacha E162, beta-apo-8'-carotenal E160e, luteína E161b, plata
  E174 -- el híbrido, al quedarse con un solo documento por sustancia
  (el más reciente), pierde estructuralmente los documentos de
  reevaluación históricos/superados en cuanto existe un documento más
  reciente sin la palabra "re-evaluation" para esa misma sustancia.
- **Conclusión: el híbrido tal como está especificado NO es un
  sustituto viable del filtro por patrón de título.** Cambia un hueco
  pequeño y bien caracterizado (6 sustancias con vigente sin capturar)
  por una regresión mucho mayor: pierde 32 documentos de reevaluación
  centrales y gana ~50 documentos de fuera de alcance (primeras
  autorizaciones, no reevaluaciones bajo 257/2010 -- justo lo que el
  filtro de título existe para excluir). No implementado, ningún
  cambio de código en esta investigación -- solo diagnóstico, tal como
  se pidió.

**Decisión tomada e implementada (misma sesión, opción "b" de las tres
sobre la mesa): híbrido estrecho como complemento con SUSTITUCIÓN, no
unión.** Antes de implementar, se pidió el desglose de los 32 que el
híbrido puro perdía:
- **26 reemplazos correctos** (la sustancia reaparece en el híbrido con
  otro documento, ej. TiO2 2016→2021).
- **1 mixto** ("Statement on nitrites in meat products": Nitrites se
  reemplaza bien, Nitrate no resuelve nada -- su único candidato de
  dominio correcto es un `EFSA statement`, excluido por diseño).
- **1 pérdida real** ("Iodized ethyl esters of poppy seed oil": la
  sustancia solo tiene un `EFSA statement`, nunca un `EFSA opinion` --
  comportamiento correcto, no un defecto).
- **4 sin sustancia ligada vía toxref** (no clasificables).

Ninguno de estos reveló un defecto nuevo -- son diferencias de diseño
ya existentes entre `reevaluation_dossiers()` (no filtra `Type`) y
`current_reference_value_opinion` (sí exige `'EFSA opinion'`).

**Híbrido estrecho probado** (sustancias ya ligadas al corpus de 162
por toxref, no las 4.476 del dataset completo): 246 sustancias → 136
documentos únicos, 130 en común, exactamente los 6 casos esperados como
nuevos, **cero sustancias fuera de alcance** (estructuralmente
imposible, el universo de entrada ya viene acotado por el corpus
existente).

**Corrección crítica antes de implementar (pedida explícitamente por el
usuario):** unir sin más (162 ∪ 6) da 168, NO 162 -- las 6 sustancias
del híbrido estrecho YA tenían un documento distinto en el corpus para
esa misma sustancia (Sunset Yellow FCF: 2009; sucrose esters: 2010;
rosemary: extension of use; steviol glycosides: extension of use;
calcium lignosulphonate: statement; lycopene: statement). Es una
sustitución 1:1, no una unión -- **162 → 162**, 6 documentos
sustituidos, no 6 añadidos. Verificado que cada sustitución es 1:1 sin
cobertura colateral (ningún dossier viejo compartido con otra
sustancia).

**Implementado:** `OpenFoodToxStore.current_reevaluation_corpus()` en
`ingestion/openfoodtox.py` -- corpus final recomendado para la descarga
de PDFs. Dos bugs de implementación encontrados y corregidos ANTES de
fijar la versión final (ninguno llegó a quedar commiteado por
separado):
1. Primera versión demasiado agresiva: sustituía cualquier dossier que
   no fuera vigente para NINGUNA de sus sustancias, sin comprobar si ya
   coexistía con el vigente real vía OTRO patrón de título -- sobre-podó
   el corpus a 143, perdiendo historial legítimo (ej. TiO2 2016,
   Allura Red AC, ácido sórbico, luteína -- todos ya representados por
   su vigente vía otro patrón, no debían tocarse).
2. Tras corregir eso, seguían sustituyéndose de más -- causa:
   `unique_reevaluation_opinions()` deduplica por TÍTULO, no por
   `Document UUID`; un dictamen de grupo genera varias filas DOSSIER con
   el mismo título y distinto UUID, y `drop_duplicates` descarta todas
   menos una. Comparar contra ese conjunto ya deduplicado daba un falso
   "no capturado" para sustancias cuyo enlace resolvía a una UUID
   descartada por el dedup. Corregido usando el conjunto COMPLETO sin
   deduplicar para esa comprobación.

**Verificado tras ambos fixes: 162 → 162, exactamente las 6
sustituciones esperadas** (tabla completa en CLAUDE.md), nada más
tocado. 3 tests de regresión nuevos en `tests/test_openfoodtox_joins.py`
-- **12/12 tests pasan**. `unique_reevaluation_opinions()` no se toca
ni se deprecia, sigue siendo el corpus "crudo" por patrón de título;
`current_reevaluation_corpus()` es la función recomendada para la
descarga de PDFs (pendiente #4 de CLAUDE.md, actualizado para
referenciarla).

**Pendiente / sin resolver al cierre de esta entrada:**
- Sin cambios en Nodo 2, Nodo 1, servidor MCP, deploy esta sesión.

## 2026-08-17 (continuación) — Arranque de la descarga de PDFs, Wiley descartado como fuente directa

**Contexto:** con `current_reevaluation_corpus()` cerrado, se empezó el
pendiente #4 (descarga de PDFs). Antes de escribir el descargador
completo, se pidió un script de sondeo `--dry-run` (script nuevo:
`scripts/probe_dossier_urls.py`, respeta la regla de CLAUDE.md de
límite explícito + pausa entre peticiones para scripts en lote) sobre
5 DOIs de ejemplo (aspartamo E 951 + 4 más de `current_reevaluation_corpus()`),
para ver a qué URL resuelve cada DOI y qué tipo de contenido devuelve
antes de comprometerse a una implementación.

**Encontrado: Wiley bloquea las 5 peticiones de prueba, no es ruido.**
Los DOIs resuelven bien vía `doi.org` a
`https://onlinelibrary.wiley.com/doi/<doi>`, pero las 5 devuelven `403`
con cabecera `cf-mitigated: challenge` -- un desafío activo de
Cloudflare que requiere ejecución de JS, no resoluble con
`requests`/`curl` sin importar las cabeceras (probado también con
User-Agent de navegador real, mismo resultado; `robots.txt` de Wiley
tampoco lo explica -- el path `/doi/` no está en `Disallow`).
Documentado en CLAUDE.md, "Hallazgos verificados", con el resultado
completo del sondeo.

**Pendiente / en curso al cierre de esta entrada:** investigando dos
rutas alternativas antes de considerar un navegador headless
(Playwright/Selenium, más frágil y con más zona gris de ToS que una
petición HTTP simple):
1. `efsa.europa.eu/en/efsajournal/pub/<referencia>` -- páginas propias
   de EFSA por dictamen. Falta averiguar cómo se deriva esa
   "referencia" a partir del DOI o título ya disponibles (no parece
   una transformación directa del DOI), y si esa página aloja el PDF
   directamente sin redirigir a Wiley.
2. PubMed Central (`pmc.ncbi.nlm.nih.gov`) -- posibles copias espejo
   de EFSA Journal bajo licencia CC BY-ND. Falta comprobar si se puede
   buscar por DOI/título vía la API de Entrez/PMC para encontrar el
   PMCID correspondiente, y si el PDF completo es descargable desde
   ahí sin bloqueo.

**Investigadas ambas rutas (script nuevo: `scripts/probe_alternate_sources.py`,
mismo estilo dry-run + límite + pausa que el anterior), con los mismos
5 DOIs de prueba:**

- **`efsa.europa.eu` descartado.** La "referencia" de
  `efsa.europa.eu/en/efsajournal/pub/<referencia>` es el último
  segmento numérico del DOI (confirmado con el caso real de aspartamo
  por búsqueda web antes de asumirlo). Pero la URL resultante hace
  `301 redirect` a `efsa.onlinelibrary.wiley.com/doi/<doi>` -- un
  subdominio de Wiley distinto pero con el MISMO bloqueo (`403` +
  `cf-mitigated: challenge`). No es una fuente independiente, es un
  alias que redirige a Wiley.
- **PubMed Central: parcialmente viable, pero NO fiable sin más
  trabajo.** Tres problemas encontrados, cada uno relevante por
  separado:
  1. La búsqueda de PMCID por DOI (ESearch `[DOI]`) da falsos
     positivos -- de los 5 DOIs de prueba, solo 2 PMCIDs encontrados
     correspondían realmente al documento solicitado al verificar
     `citation_doi` en la página. El caso de aspartamo (referencia del
     proyecto) apuntó a un artículo de Scientific Reports 2025 sobre
     cálculos renales sin relación real; el de Quillaia extract apuntó
     a un documento real pero equivocado (follow-up 2024, no el
     dictamen 2019 pedido).
  2. Cuando el PMCID es correcto, la página SÍ es accesible -- pero
     solo con `curl`, no con `requests` de Python, para la misma URL y
     el mismo User-Agent (403 consistente con `requests`, 200
     consistente con `curl`; descartado que sea HTTP/1.1 vs HTTP/2).
     Necesitaría `curl` por subproceso o una librería con fingerprint
     TLS equivalente (`curl_cffi`), no `requests` a secas.
  3. Incluso así, no es 100% estable -- 1 de los 5 PMCIDs devolvió una
     página de reCAPTCHA en vez del artículo, sin determinar la causa.

**Conclusión de esta sesión: ninguna de las tres rutas probadas hasta
ahora (Wiley directo, `efsa.europa.eu`, PMC) es una solución limpia.**
Wiley está bloqueado sin excepción. PMC es parcialmente accesible pero
con cobertura incompleta y riesgo de falsos positivos que exigen
verificación por DOI antes de confiar en cualquier resultado. Detalle
completo en CLAUDE.md, "Hallazgos verificados".

**Decisión tomada (misma sesión, cierre de la exploración automatizada):
descarga MANUAL vía navegador normal, no automatizada.** De las 3
fuentes probadas (Wiley directo, `efsa.europa.eu`, PMC), ninguna
permite descarga automatizada fiable -- resumen: Wiley bloquea con
*challenge* de Cloudflare sin excepción; `efsa.europa.eu` solo
redirige a la misma Wiley; PMC tiene falsos positivos de búsqueda por
DOI, exige `curl` en vez de `requests`, y aun así da captcha
intermitente. El bloqueo es específico de peticiones automatizadas --
un navegador con sesión humana normal no debería toparse con el mismo
*challenge*. Se descarta explícitamente un navegador headless
(Playwright/Selenium): más frágil, zona gris de ToS, y 162 documentos
(una vez cada uno) no justifican esa complejidad frente a descarga
manual asistida por checklist.

**Roadmap actualizado:** el paso 2 (`docs/efsa-rag-proyecto.html`, antes
"Descarga y organización de PDFs" / "script de descarga") pasa a
"Descarga manual asistida por checklist". Mismo cambio reflejado en
CLAUDE.md, pendiente #4 de "Estado del código".

**Checklist generado:** script nuevo `scripts/generate_pdf_checklist.py`
(sin peticiones de red, solo lee el xlsx) produce
`data/pdf_download_checklist.csv` y `data/pdf_download_checklist.md`
con columnas sustancia(s), E-number(s), DOI, título, nombre de archivo
de destino esperado (`<E-numbers>_<DOI saneado>.pdf`) y `descargado`
vacía para que el usuario marque progreso.

**Dos hallazgos de calidad de datos encontrados al generar el
checklist** (no vistos en las fases anteriores de esta sesión):
1. `LiteratureReference.LinkToPersistentIdentifier` no es consistente
   en el xlsx -- 147 filas con prefijo `"doi:"`, 15 con `"doi. org/"`
   (con espacio, sin dos puntos). Normalizado anclando en el propio
   DOI (`10\.\d+/...`), no en el prefijo.
2. **El corpus de 162 tiene un duplicado real -- son 161 documentos
   únicos, no 162.** "Re-evaluation of saccharin and its sodium,
   potassium and calcium salts (E 954)..." aparece dos veces en el
   xlsx con el MISMO DOI, por una variante de título con una errata de
   espacio ("and calcium salts" / "andcalcium salts") --
   `reevaluation_dossiers()`/`unique_reevaluation_opinions()`
   deduplican por texto exacto de título, así que la errata cuela como
   fila adicional. El checklist deduplica por DOI antes de escribir
   (161 filas), prefiriendo la fila con sustancia resuelta vía toxref
   -- que resultó ser la de la errata, no la del título "correcto",
   verificado antes de decidir cuál descartar. **No corregido en
   `current_reevaluation_corpus()` en esta sesión** (el checklist ya
   lo maneja correctamente; deduplicar por DOI en el corpus en sí
   queda como mejora pendiente, no bloqueante).

Detalle completo de las 3 fuentes investigadas y ambos hallazgos en
CLAUDE.md, "Hallazgos verificados".

**Pendiente / sin resolver al cierre de esta entrada:**
- Descarga real de los 161 PDFs -- trabajo manual del usuario, no
  completado en esta sesión (obviamente).
- Deduplicar por DOI en `current_reevaluation_corpus()`/
  `unique_reevaluation_opinions()` en vez de por título -- mejora
  pendiente, no bloqueante (el checklist ya compensa el caso conocido).
- Sin cambios en Nodo 1, Nodo 2, servidor MCP, deploy esta sesión.
