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
  **[CORRECCIÓN, 18-ago-2026: esta línea es FALSA y lo era ya en el
  momento de escribirse -- Nodo 1 (`extract_entity_node`) era
  `raise NotImplementedError` en este mismo commit, igual que Nodo 2 y
  Nodo 4. Solo Nodo 3 tenía código real. Ver la entrada de corrección
  al final de este archivo, sesión 18-ago-2026 continuación 6, para el
  análisis completo -- no se ha reescrito esta línea para no borrar el
  rastro del error.]**
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

## 2026-08-17 (continuación 2) — 161/161 PDFs confirmados en disco, `.gitignore` corregido, investigación de licencia de los PDFs antes de indexar

**Contexto:** retomando tras reinicio. Confirmado en disco
(`ls data/raw/pdfs/ | wc -l`) que los 161 PDFs de la sesión anterior ya
están descargados y commiteados (`defd7b6`). Antes de empezar el
pipeline de chunking/embeddings/Chroma (pendiente #5), el usuario pidió
dos cosas: corregir `.gitignore` para que el índice de Chroma sí se
versione (coherente con la decisión "Opción A" ya tomada) e investigar
la licencia real de los PDFs, porque Chroma va a guardar el TEXTO de
los chunks, no solo embeddings -- si el repo es público, eso redistribuye
ese texto, y hace falta saber si la licencia lo permite antes de decidir.

**Implementado:**
- `.gitignore`: se probó eliminar la línea `data/chroma/` (petición
  inicial del usuario, ver más abajo por qué se revirtió) y se
  mantienen sin cambios las exclusiones de `data/raw/*.xlsx` y
  `data/raw/pdfs/`.

**Investigado (licencia de los 161 PDFs) -- hallazgo importante, deja
una decisión pendiente sin resolver, ver más abajo:**
- Escaneado el texto completo de los 161 PDFs (`pdftotext`) buscando
  menciones de "Creative Commons". Resultado: **no es uniforme, dos
  regímenes de licencia distintos según fecha de publicación.**
  - **82/161 (2016-2025):** llevan literalmente en el texto "This is an
    open access article under the terms of the Creative Commons
    Attribution-NoDerivs License, which permits use and distribution in
    any medium, provided the original work is properly cited and no
    modifications or adaptations are made." -- **CC BY-ND**, misma
    frase exacta en los 82, sin variante NC. Permite uso comercial y no
    comercial, pero solo "unchanged and in whole" -- no fragmentos.
  - **79/161 (2007-2016, con solape en 2016 -- el corte real es a
    mitad de año, no un cambio de año natural):** SIN ninguna mención
    de Creative Commons en ningún punto del texto. Contrastado contra
    la política oficial de la época (`EFSA Journal Editorial Policy`,
    13-feb-2013, descargada y leída directamente): su sección de
    copyright NO menciona Creative Commons en absoluto -- es una
    política propia de EFSA que autoriza reproducción para uso
    personal/educativo o difusión NO comercial con atribución, más
    restrictiva que CC BY-ND (no cubre uso comercial, y su alcance no
    contempla claramente "publicar en un repo público de GitHub").
    Confirmado por búsqueda web de forma independiente: el traslado del
    EFSA Journal a Wiley como editor (y la introducción de la licencia
    Creative Commons) ocurrió en 2016 -- coincide exactamente con el
    corte encontrado en el escaneo de texto.
- **Conclusión, sin decidir nada unilateralmente:** ninguno de los dos
  regímenes da un "sí" limpio a publicar el TEXTO de los chunks (no
  solo los embeddings numéricos) en un repo público sin restricción --
  el bloque más antiguo (49% del corpus) no tiene licencia abierta en
  absoluto, y el más reciente (51%) es CC BY-ND, que por su propia
  descripción oficial cubre redistribuir el artículo completo sin
  cambios, no fragmentos trocedados. Detalle completo, con las citas
  exactas de ambas fuentes primarias, en CLAUDE.md, "Hallazgos
  verificados". Añadida nota explícita en la decisión "Opción A" de
  CLAUDE.md señalando esta pregunta como abierta.

**Decisión tomada por el usuario, a la vista del hallazgo de
licencia:** `data/chroma/` se mantiene en `.gitignore` -- NO se
versiona en el repo público de GitHub. Razón explícita dada por el
usuario: no es precaución genérica, es la consecuencia directa de que
79/161 PDFs (49%, dictámenes 2007-2016) no tienen ninguna licencia
abierta, solo la política de copyright propia de EFSA (sin cobertura
clara de redistribución pública ni de uso comercial), y los otros
82/161 (CC BY-ND 2016-2025) están pensados para redistribuir el
artículo completo sin cambios, no fragmentos trocedados. El índice sí
se sigue empaquetando en la imagen/artefacto de **despliegue** (Opción
A se mantiene para eso), solo se excluye del repo fuente de GitHub --
son dos destinos distintos, no la misma decisión. `.gitignore` revertido
a incluir `data/chroma/` (el intento inicial de quitarla se deshizo).
CLAUDE.md actualizado en ambos sitios relevantes ("Hallazgos
verificados" y la decisión "Opción A") para que quede como decisión
tomada con motivo documentado, no como pendiente.

**Pendiente / sin resolver al cierre de esta entrada:**
- Pipeline de chunking/embeddings/Chroma (pendiente #5) sigue sin
  empezar -- ya desbloqueado en cuanto a destino del índice (decidido
  arriba), próximo paso lógico de la siguiente sesión.
- Sin cambios en Nodo 1, Nodo 2, servidor MCP, deploy esta sesión.

## 2026-08-17 (continuación 3) — Diagnóstico de estructura de PDFs + diseño de esquema de metadatos multi-sustancia, antes de escribir el chunker

**Contexto:** antes de empezar a escribir código de chunking/embeddings,
el usuario pidió dos cosas de diagnóstico y diseño puro (sin instalar ni
ejecutar nada de embeddings): (1) abrir 3 PDFs reales (uno corto, uno
largo, uno con `discussion_is_boilerplate=True`) y describir su
estructura; (2) proponer el esquema de metadatos para los 29 (cifra de
partida, corregida durante la sesión -- ver abajo) archivos que cubren
más de un E-number.

**Diagnóstico de estructura de PDFs (solo `pdftotext`/`pdfinfo`, sin
dependencias nuevas):**
- Corto: `sinE_10.2903_j.efsa.2011.1996.pdf` (5 pp., 41 KB, un
  "Statement") -- estructura mínima y estable: Abstract, TOC, Background,
  Terms of Reference, Evaluation, References, sin tablas.
- Largo: `E338-E343-E450_10.2903_j.efsa.2019.5674.pdf` (156 pp., 16 MB,
  grupo de fosfatos) -- jerarquía de encabezados numerados hasta 4
  niveles (`3.10.2.`), 12 tablas de datos. **Confirmado el riesgo que
  motivó la pregunta: `Table 5a` (exposición dietética, 7 grupos de
  población × 2 escenarios × percentil) se rompe mal con extracción de
  texto plano** -- encabezados de columna separados de sus valores
  numéricos sin marca de correspondencia, un splitter de texto plano la
  trocearía sin sentido tabular reconstruible.
- Mediano con `discussion_is_boilerplate=True`:
  `E507-E508-E509-E511_10.2903_j.efsa.2019.5751.pdf` (51 pp., 5,4 MB,
  grupo de cloruros). **Hallazgo no buscado:** el PDF tiene su propia
  sección `4. Discussion` con varios párrafos de razonamiento real, más
  rica que el campo corto `END_SUM.Discussion.Discussion` que sí está
  marcado como boilerplate para este dossier -- confirma que el
  pipeline de PDFs (pendiente #5) no es redundante con el campo
  `discussion_text` ya integrado (pendiente #3): son dos fuentes de
  discusión distintas, y `discussion_is_boilerplate=True` en el xlsx NO
  implica que el PDF tampoco tenga discusión sustantiva.

**Corrección de cifra encontrada al diseñar el mapeo sustancia→archivo:
no son 29/161 PDFs multi-E-number, son AL MENOS 36/161 (22%).** El
pendiente #5 contaba solo filas con `;` en la columna `e_number` del
checklist. Comparando el número de nombres en `sustancia` contra el
número de códigos en `e_number` para las 161 filas, 36 tienen recuentos
DISTINTOS -- incluye casos donde `e_number` no tiene `;` en absoluto
pero `sustancia` sí lista varios nombres (ej. E472a-f: 6 nombres de
sustancia, 1 solo código "E472A" en el checklist).

**Causa raíz investigada con las hojas reales (caso E472a-f, DOI
`10.2903/j.efsa.2020.6032`):** el título aparece en 6 filas DISTINTAS de
`DOSSIER`, cada una con su propio `Document UUID` que enlaza (vía
`DOSSIER_DOCS` → `FLEX_SUM.ToxRefValues.Parent UUID` → `SUB`) a
exactamente 1 de las 6 sustancias reales -- verificado resolviendo las 6
`Parent UUID` a 6 `ChemicalName` distintos en `SUB`, cada uno un
componente real de E472a-f. `unique_reevaluation_opinions()`/
`current_reevaluation_corpus()` deduplican por título, así que solo 1 de
las 6 filas sobrevive al corpus -- ni la columna `e_number` del
checklist (hereda el mismo problema) ni el join estructural desde el
`Document UUID` post-dedup en solitario capturan las 6.

**Técnica verificada que sí recupera las 6 sustancias completas (solo
verificada manualmente, NO implementada):** agrupar las filas de
`DOSSIER` por DOI/título ANTES del dedup, resolver el enlace toxref de
cada fila hermana por separado, tomar la UNIÓN de sustancias. Verificado
con E472a-f: cada una de las 6 filas hermanas resuelve individualmente a
1 sustancia real, la unión da las 6.

**Diseño de esquema de metadatos propuesto (solo diseño, nada
implementado):** para un chunk que sirve a N sustancias, indexarlo N
veces en Chroma (mismo texto/embedding, N entradas de metadato), cada
una con `substance_uuid`/`e_number`/`chemical_name` singulares
(exact-match eficiente en `where`) + `chunk_group_id` compartido entre
las N copias (para deduplicar en la app si una consulta toca más de una
sustancia del mismo dictamen) + `dossier_uuid`/`pdf_filename`/`doi`/
`section_heading`/`page_number`/`is_group_dossier`. Alternativa
descartada y documentada (un solo chunk con `substance_uuids`
delimitado por `;`): Chroma no filtra eficientemente sobre substring de
un campo delimitado, obligaría a sobre-recuperar y filtrar en Python; a
esta escala (161 PDFs) la duplicación de embeddings es barata y no hay
razón de rendimiento para preferir la alternativa.

Detalle completo (con las citas de las hojas y los UUIDs verificados) en
CLAUDE.md, "Hallazgos verificados". Pendiente #5 de "Estado del código"
actualizado con la cifra corregida (36, no 29).

**Pendiente / sin resolver al cierre de esta entrada:**
- **Ninguna implementación de chunking/embeddings/Chroma todavía** --
  esta sesión fue solo diagnóstico y diseño, tal como se pidió
  explícitamente.
- Decisión no zanjada: si las tablas grandes de exposición dietética se
  excluyen del RAG narrativo (el dato cuantitativo ya viene de
  OpenFoodTox) o si se intenta una extracción de tablas separada
  (`pdfplumber`/`camelot`) -- pendiente de decidir al escribir el
  chunker, no bloqueante para empezar con el texto narrativo.
- La técnica de "agrupar filas hermanas por DOI antes del dedup" para
  enumerar sustancias por archivo está verificada solo para el caso
  E472a-f -- no confirmada contra los otros 35 casos de mismatch antes
  de implementarla como función reutilizable.
- Sin cambios en Nodo 1, Nodo 2, servidor MCP, deploy esta sesión.

## 2026-08-17 (continuación 4) — Alcance completo del bug de deduplicación por título, comparación `current_reevaluation_corpus()` vs `unique_reevaluation_opinions()`

**Contexto:** la sesión anterior encontró el bug de deduplicación por
título con el caso E472a-f y estimó "36/161 archivos afectados"
comparando columnas del checklist. El usuario pidió cuantificar el
alcance REAL del bug (no solo E472a-f) directamente sobre las hojas, y
comparar si `current_reevaluation_corpus()` (el híbrido que ya resuelve
por sustancia) evita el problema o lo comparte -- con la sugerencia de
que, si lo evita, quizás la fuente correcta para el chunking sea esa
función en vez de reconstruir la lista desde el checklist. Solo
diagnóstico y comparación, sin implementar ningún fix.

**Metodología:** sobre `reevaluation_dossiers()` SIN deduplicar (338
filas, 162 títulos únicos), agrupado por título, comparando para cada
grupo con >1 fila DOSSIER la unión de sustancias enlazadas vía
`FLEX_SUM.ToxRefValues.Parent UUID` de TODAS las filas hermanas contra
lo visible solo a través de la fila que sobrevive el `drop_duplicates`.

**Corrección metodológica importante, encontrada investigando el caso
de nitritos (20 filas DOSSIER hermanas para el mismo título):** contar
ciegamente todos los `Parent UUID` enlazados da 20 "sustancias" -- pero
verificado con las hojas reales que **17 de esas 20 son compuestos
N-nitroso (sustancias de referencia toxicológica citadas en la
caracterización de peligro, no aditivos que el PDF cubra con su propio
E-number)**. Señal que las distingue, ya usada en otro punto del código
(`_adi_row_for_toxref_uuids`): las 3 sustancias reales (Sodium nitrite,
Potassium nitrite, Nitrites) tienen `Adi.lowerValue` poblado para esa
fila de `FLEX_SUM.ToxRefValues`; las 17 N-nitroso no (enlazadas vía
`OtherReferenceValues`, no vía ADI). Un recuento de sustancias sin este
filtro sobreestima sistemáticamente en dossiers de contaminantes.

**Cifra corregida, con el filtro de ADI aplicado:** 105/162 títulos
(65%) tienen exactamente 1 fila DOSSIER, sin ambigüedad. De los 57
títulos con >1 fila hermana, **solo 20 (12% del corpus) son
genuinamente multi-sustancia** (unión de sustancias con ADI propio >
1). Entre esos 20: 62 sustancias reales en total, de las cuales solo 16
son visibles a través de la fila superviviente del dedup -- **46
sustancias con ADI propio quedan invisibles**. Peores casos: tartratos
E334-E337+E354 (7 sustancias, 6 perdidas), glutamato E620-E625 (6
sustancias, 5 perdidas), ésteres de sorbitán E491-E495 (5 sustancias, 4
perdidas), colorantes caramelo E150a-d (5 sustancias, 4 perdidas).
E472a-f (5 perdidas) es uno más de la lista, no el peor caso.
Confirmado además que agrupar por DOI en vez de por título no cambia el
resultado (161 DOIs únicos vs 162 títulos únicos, única discrepancia ya
conocida: la errata de saccharin).

**Comparación pedida -- ¿`current_reevaluation_corpus()` evita el bug?
Verificado ejecutándolo, no solo leyendo el código:** **NO, lo hereda
intacto como DataFrame de salida.** Para el título de nitritos devuelve
exactamente 1 fila (igual que `unique_reevaluation_opinions()`), no 3
ni 20 -- porque parte de `base = unique_reevaluation_opinions()` y su
lógica de sustitución solo intercambia filas completas para 6 casos
puntuales (Grupo A/B), nunca expande un título a varias filas. **PERO**
el CÓDIGO de `current_reevaluation_corpus()` sí construye internamente,
como paso intermedio descartado, la enumeración de sustancias correcta
-- calcula `substance_uuids` a partir de `reevaluation_dossiers()` SIN
deduplicar (todas las filas hermanas), no del conjunto ya deduplicado
-- solo que ese paso se usa únicamente para decidir 6 sustituciones
puntuales y nunca se expone como resultado reutilizable.

**Conclusión, respondiendo directamente a la pregunta planteada:** la
solución no es arreglar `unique_reevaluation_opinions()` (colapsar a 1
fila por título es correcto para esa función -- cuenta documentos/PDFs,
no sustancias) ni usar `current_reevaluation_corpus()` como fuente
directa (su output tiene el mismo problema pese al nombre). **La
solución es extraer la TÉCNICA que ya usa internamente** (agrupar por
título/DOI sin deduplicar + filtrar por `Adi.lowerValue` no nulo +
unión) **como una función nueva y reutilizable**, ni reconstruir desde
las columnas del checklist (ninguna de las dos es fiable por sí sola --
`sustancia` sobre-reporta para nitritos sin el filtro de ADI, `e_number`
sub-reporta para E472a-f). Detalle completo, con las cifras exactas por
caso, en CLAUDE.md, "Hallazgos verificados". Pendiente #5 de "Estado
del código" actualizado con la cifra final (20 títulos / 46 sustancias,
no 29 ni 36).

**Corrección adicional hecha en esta sesión:** al insertar el bloque de
hallazgos de la sesión anterior, un `Edit` había borrado por accidente
el encabezado `## Decisiones de arquitectura ya tomadas` de CLAUDE.md
(el contenido seguía ahí, pero sin su título de sección) -- detectado y
corregido al hacer `grep` de todos los encabezados `##` del documento
antes de añadir contenido nuevo.

**Pendiente / sin resolver al cierre de esta entrada:**
- **Ninguna implementación todavía** -- esta sesión fue solo
  diagnóstico y comparación, tal como se pidió explícitamente. La
  función reutilizable de enumeración de sustancias por dossier queda
  como diseño verificado, no como código.
- Sin cambios en Nodo 1, Nodo 2, servidor MCP, deploy esta sesión.

## 2026-08-17 (continuación 5) — `substances_per_dossier()` implementado y verificado

**Contexto:** la sesión anterior dejó diseñada (sin implementar) la
técnica correcta para enumerar todas las sustancias de un dossier de
grupo. El usuario pidió extraerla como función pública reutilizable,
verificarla contra los 3 casos ya identificados (nitritos, tartratos,
glutamato) y añadir tests de regresión -- sin tocar
`unique_reevaluation_opinions()` ni `current_reevaluation_corpus()`.

**Implementado en `ingestion/openfoodtox.py`:**
- Nuevo dataclass `DossierSubstance` (`substance_uuid` + `chemical_name`).
- Nuevo método `OpenFoodToxStore.substances_per_dossier(corpus=None)` --
  para cada dossier de `corpus` (por defecto `current_reevaluation_corpus()`),
  agrupa todas las filas hermanas de `reevaluation_dossiers()` SIN
  deduplicar que comparten título (más la propia fila del dossier, para
  cubrir los 6 casos que `current_reevaluation_corpus()` sustituye y que
  no están bajo ningún título en `reevaluation_dossiers()`), resuelve el
  enlace de sustancia de cada una vía `FLEX_SUM.ToxRefValues`, filtra por
  `ADI_LOWER_VALUE_COLUMN` no nulo (mismo criterio que
  `_adi_row_for_toxref_uuids`, ya usado en otro punto del código) y
  devuelve la unión. Nueva constante `TOXREF_LINK_DOCUMENT_TYPES` para no
  duplicar el literal `("FLEXIBLE_SUMMARY", "ToxRefValues")` ya usado en
  `current_reevaluation_corpus()` -- esa función NO se ha tocado.
- **No se ha modificado ninguna línea de `unique_reevaluation_opinions()`
  ni `current_reevaluation_corpus()`** -- confirmado con `git diff`
  antes de dar la tarea por completa.

**Verificado contra el xlsx real, los 3 casos pedidos:**
- Nitritos → exactamente `{Nitrites, Potassium nitrite, Sodium nitrite}`
  -- los 17 compuestos N-nitroso quedan excluidos por el filtro de ADI.
- Tartratos → las 7 sales del grupo E334-E337+E354.
- Glutamato → las 6 sales del grupo E620-E625.
- **Corrección de expectativa encontrada al verificar:** el usuario
  esperaba "6" para tartratos y "5" para glutamato -- esas eran las
  cifras de sustancias PERDIDAS (invisibles tras el dedup) reportadas en
  la sesión anterior, no el total. El total real (lo que la función debe
  devolver) es 7 y 6 respectivamente -- confirmado contra las hojas antes
  de fijar los tests, no ajustado a la expectativa inicial.

**Tests de regresión nuevos en `tests/test_openfoodtox_joins.py`:**
`test_substances_per_dossier_nitrites_excludes_toxicological_references`,
`test_substances_per_dossier_tartrates_group_returns_all_seven`,
`test_substances_per_dossier_glutamates_group_returns_all_six` --
**15/15 tests pasan** (12 previos + 3 nuevos), ~58s de tiempo total de
ejecución.

**Hallazgo adicional al correr la función sobre el corpus completo (162
dossiers):** 99 dossiers no tienen ninguna sustancia con ADI propio
ligada -- verificado que al menos uno (dióxido de titanio E171) es un
caso legítimo, no un fallo: su dossier vigente de 2021 tiene
`adi_value=None` en `current_reference_value_opinion` porque EFSA no
pudo establecer un ADI por preocupaciones de genotoxicidad. **Límite de
alcance documentado, no resuelto en esta sesión:** para dossiers de
sustancia única sin ADI, `substances_per_dossier()` devuelve lista
vacía aunque la identidad de la sustancia no sea ambigua -- el chunking
tendrá que resolver esos casos por otra vía (`substance_uuid_by_name`
directamente), esta función está pensada para el caso multi-sustancia.

**Corrección de un error propio detectado durante esta sesión:** un
`Edit` de la sesión anterior había borrado por accidente el encabezado
`## Decisiones de arquitectura ya tomadas` de CLAUDE.md -- ya estaba
corregido antes de empezar esta sesión (arreglado en la continuación 4),
mencionado aquí solo para que quede trazado en qué sesión se detectó y
corrigió.

**Pendiente / sin resolver al cierre de esta entrada:**
- Rendimiento: `substances_per_dossier()` no cachea nada, ~27s para los
  162 dossiers del corpus completo -- aceptable para un script de
  indexación que se ejecuta una vez, no para uso repetido en un flujo
  interactivo. Memoizar si se acaba llamando así.
- El diseño del esquema de metadatos por chunk (indexar N veces, uno por
  sustancia, con `chunk_group_id` compartido) sigue siendo solo diseño --
  la función que lo alimenta ya existe, pero el chunker en sí no se ha
  empezado a escribir.
- Sin cambios en Nodo 1, Nodo 2, servidor MCP, deploy esta sesión.

## 2026-08-17 (continuación 6) — Desglose completo de los 99 dossiers sin sustancia con ADI, diseño de resolución en 3 niveles

**Contexto:** antes de escribir el chunker, el usuario pidió el listado
completo de los 99 dossiers donde `substances_per_dossier()` devuelve
lista vacía, cuántos son "TiO2-like" (sin ADI pero sustancia clara) vs.
cuántos necesitan de verdad `substance_uuid_by_name()`, y una propuesta
(sin implementar) de cómo el indexado va a resolver sustancia(s) para
los 162 dossiers combinando ambos caminos. Solo diagnóstico y diseño.

**Desglose de los 99 (verificado contra las hojas reales):**
- **73: sustancia única, sin ADI (patrón TiO2)** -- el enlace
  `Parent UUID` sigue existiendo y resuelve a exactamente 1 sustancia,
  simplemente sin `Adi.lowerValue` relleno (ADI "no establecida", común
  en gomas/ceras/colorantes minerales). Lista completa en CLAUDE.md,
  "Hallazgos verificados".
- **22: multi-sustancia, NINGUNA con ADI** -- dossiers de grupo
  genuinos (alginatos, celulosas [10 sustancias, el mayor], sulfatos de
  aluminio, cloruros, sacarina [antes del fix de agrupación, ver
  abajo], etc.) -- misma fiabilidad de identidad que los de Tier 1 con
  ADI, necesitan el mismo tratamiento de "N copias por chunk".
- **4: sin ningún enlace toxref en absoluto** -- coincide con el
  hallazgo ya documentado del "híbrido puro": sucralosa (statement),
  shellac, saccharin (variante de título sin la errata de espacio),
  statement genérico de "two recent scientific articles...".

**Corrección de diseño encontrada al investigar el caso de saccharin:**
agrupar las filas hermanas por DOI en vez de por TÍTULO (lo que hace
`substances_per_dossier()` hoy) resuelve el caso de saccharin sin
heurística -- las dos variantes de título (con/sin la errata de
espacio, mismo DOI) tienen 1 y 4 filas hermanas respectivamente si se
agrupa por título, pero comparten las 5 completas si se agrupa por DOI,
resolviendo las 4 sales de sacarina. **Verificado que cambiar la clave
de agrupación de título a DOI no cambia NINGÚN otro resultado ya
comprobado** (nitritos, tartratos, glutamato, y el resto de los 160
dossiers dan los mismos siblings por ambas claves) -- mejora
estrictamente más segura, propuesta pero no implementada.

**Con esa mejora, quedan solo 3/162 dossiers sin ningún enlace
estructural:** sucralosa, shellac, y el statement genérico. De estos,
`substance_uuid_by_name()` resuelve 2 limpiamente por nombre extraído
del título (Sucralose, Shellac). El tercero (statement genérico sobre
edulcorantes artificiales) NO menciona ninguna sustancia con E-number
en el título -- aunque probablemente es "sobre" aspartamo en el fondo,
inferirlo automáticamente del título sería una suposición editorial sin
precedente en los heurísticos ya usados en este proyecto. **Propuesta:
dejarlo sin sustancia estructurada, no forzar la inferencia.**

**Diseño de resolución en 3 niveles (propuesto, no implementado):**
1. Nivel 1: `substances_per_dossier()` tal como existe hoy (con ADI) --
   63/162 dossiers.
2. Nivel 2: la misma función con un parámetro nuevo `require_adi=False`
   -- mismo mecanismo estructural, sin diferencia de confianza en la
   identidad de la sustancia, resuelve 96/162 adicionales.
3. Nivel 3: `substance_uuid_by_name()` sobre nombre extraído del título,
   solo para los 3 casos restantes sin enlace -- resuelve 2 más.

**Cobertura total: 161/162 dossiers con al menos 1 sustancia resuelta,
1/162 sin sustancia estructurada a propósito** (el statement genérico).
Campo de metadato nuevo propuesto: `substance_resolution_tier`
(1/2/3) por cada entrada sustancia-chunk, para que el Nodo 4 pueda
distinguir "ADI real" de "sustancia identificada sin ADI" (coincide con
la comunicación de riesgo que el proyecto ya necesita para casos como
TiO2) de "identidad inferida por heurística de título, tratar con más
cuidado". Detalle completo, con el listado de los 73+22+4 dossiers, en
CLAUDE.md, "Hallazgos verificados".

**Pendiente / sin resolver al cierre de esta entrada:**
- **Nada implementado todavía** -- solo diagnóstico y diseño, tal como
  se pidió. `substances_per_dossier()` sigue con `require_adi` fijo
  (implícitamente `True`) y agrupación por título, no por DOI.
- El diseño de 3 niveles y el campo `substance_resolution_tier` quedan
  como especificación a implementar cuando se escriba el chunker.
- Sin cambios en Nodo 1, Nodo 2, servidor MCP, deploy esta sesión.

## 2026-08-17 (continuación 7) — Nodo 4 usa `substance_resolution_tier`: texto tier 1/2, contrato `RetrievedChunk` para tier 3

**Contexto:** antes de escribir el chunker, se pidió confirmar
explícitamente cómo el Nodo 4 iba a comunicar cada nivel de
`substance_resolution_tier` -- al revisar el código real
(`_format_structured_result`/`_format_retrieved_chunks`), el diseño de
la sesión anterior resultó incompleto: tier 1/2 ya tenía gancho en
código existente (`adi_value is None`), pero tier 3 necesitaba un
cambio de contrato (`retrieved_chunks` era `list[str]`, sin metadatos)
que no se había hecho explícito. Confirmado el planteamiento con el
usuario antes de implementar, en este orden: (1) tier 1/2, ya; (2)
documentar el contrato de `RetrievedChunk` en CLAUDE.md antes de
tocar código; (3) implementar el cambio de tipo ahora, aunque el Nodo 2
no exista todavía, para fijar el contrato de una vez.

**Implementado en `graph/nodes.py`:**
1. **Tier 1/2 -- `_format_structured_result`:** el branch `else` de
   `adi_line` (antes "ADI: no disponible en los datos estructurados")
   ahora explica que la ausencia de ADI puede deberse a motivos
   OPUESTOS (favorable -- sin necesidad de límite, frecuente en gomas/
   ceras -- o de preocupación -- ej. genotoxicidad, caso TiO2) e
   instruye a no asumir cuál aplica sin comprobarlo en
   `adi_justification`/`discussion_text`, ya incluidos en el mismo
   prompt. **Deliberadamente NO se generaliza "genotoxicidad" como
   motivo por defecto** -- verificado sobre las 73 sustancias
   tier-2 reales que la mayoría carece de ADI por el motivo contrario;
   un texto que sugiriera preocupación por defecto sería engañoso para
   ellas.
2. **Contrato `RetrievedChunk` documentado en CLAUDE.md** ("Decisiones
   de arquitectura ya tomadas") ANTES de tocar código, tal como se
   pidió -- razonamiento completo + firma exacta del dataclass.
3. **Tier 3 -- nuevo dataclass `RetrievedChunk`** (`text`,
   `substance_uuid`, `chemical_name`, `dossier_uuid`, `dossier_title`,
   `substance_resolution_tier`, `doi`/`section_heading`/`page_number`
   opcionales) sustituye a `list[str]` en
   `GraphState.retrieved_chunks`. `_format_retrieved_chunks` antepone
   un aviso inline SOLO cuando `substance_resolution_tier == 3` --
   mismo patrón que `discussion_line` (instrucción incrustada en el
   dato del prompt de usuario, sin tocar `NODE_4_GROUNDING_RULES`/
   `NODE_4_SAFETY_COMMUNICATION_RULES`). `hybrid_retrieval_node`
   (Nodo 2, sigue `NotImplementedError`) actualizado con un TODO
   explícito: cuando se implemente, DEBE producir `list[RetrievedChunk]`,
   nunca strings sueltos.

**Tests nuevos en `tests/test_nodes.py`** (archivo nuevo):
- Tier 1 con caso real (aspartamo, ADI=40) -- cita con normalidad, sin
  el aviso de "no hay valor numérico".
- Tier 2 con caso real (dióxido de titanio, adi_value=None) -- verifica
  que el texto menciona AMBOS motivos posibles como ejemplos (no como
  hecho de este caso) e instruye a no asumir.
- Tier 3 de `_format_retrieved_chunks` (sintético, sin xlsx) -- el
  aviso de "coincidencia de nombre en el título" aparece solo en el
  fragmento tier 3, no en tier 1 ni 2.
- Lista vacía de `retrieved_chunks` sigue explicando que el corpus no
  está indexado.
- **19/19 tests pasan** (15 previos de `test_openfoodtox_joins.py` + 4
  nuevos), ~77s de tiempo total.

**Pendiente / sin resolver al cierre de esta entrada:**
- El Nodo 2 (`hybrid_retrieval_node`) sigue sin implementar -- el
  contrato de salida (`list[RetrievedChunk]`) ya está fijado, pero
  nadie lo produce todavía.
- El resto del diseño de 3 niveles (`require_adi` como parámetro de
  `substances_per_dossier()`, agrupación por DOI en vez de título) del
  pendiente de la sesión anterior sigue sin implementar -- esta sesión
  se centró en el consumo del tier en el Nodo 4, no en la generación
  del tier en el indexado.
- Sin cambios en Nodo 1, servidor MCP, deploy esta sesión.

## 2026-08-17 (continuación 8) — PyPDFLoader vs PyMuPDFLoader, decisión con evidencia

**Contexto:** antes de escribir el chunker, se preguntó si ya se había
comparado PyPDFLoader vs PyMuPDFLoader sobre el PDF de fosfatos
(E338-E343-E450, 156 páginas, la Tabla 5a que se rompía con
`pdftotext`). No se había hecho -- solo diagnóstico con `pdftotext`
(poppler CLI) en sesiones anteriores, nunca con los loaders de
`langchain_community` que el pipeline va a usar de verdad. Hecha ahora,
solo comparación, sin implementar el chunker. `pymupdf` instalado en el
venv local para la prueba, no añadido a `requirements.txt` todavía.

**Resultado, con medidas concretas, no preferencia teórica:**
- **Velocidad:** PyMuPDFLoader ~8x más rápido (0,5s vs 4,2s para las
  156 páginas).
- **Fidelidad de texto -- diferencia decisiva:** PyPDFLoader inserta un
  espacio espurio en palabras con ligadura ﬁ/ﬂ del PDF ("scientific" →
  "scienti ﬁc"). Contado sobre 17 palabras conocidas por el problema:
  **402 palabras rotas en todo el documento con PyPDFLoader, 0 con
  PyMuPDFLoader.**
- **Tabla 5a específicamente:** ninguno de los dos loaders reconstruye
  la tabla como tabla -- ambos preservan el orden de lectura (7 valores
  por fila en el mismo orden que los 7 encabezados), pero PyPDFLoader
  agrupa cada fila en una sola línea (más resistente a que un splitter
  la corte por la mitad) mientras que PyMuPDFLoader pone cada celda en
  su propia línea (más expuesto a fragmentación de fila). Este trade-off
  de layout de tabla queda como problema de estrategia de chunking
  (chunks grandes alrededor de tablas, o excluirlas del RAG narrativo),
  no algo que la elección de loader resuelva.

**Decisión: PyMuPDFLoader como loader por defecto.** La fidelidad de
texto (0 vs 402 palabras rotas) y la velocidad pesan más que la
desventaja de fragmentación de tablas, que hay que mitigar a nivel de
chunking de todos modos independientemente del loader. Detalle completo
en CLAUDE.md, "Hallazgos verificados".

**Pendiente / sin resolver al cierre de esta entrada:**
- **No implementado en el pipeline todavía** -- añadir `pymupdf` a
  `requirements.txt` y usar `PyMuPDFLoader` es tarea de cuando se
  escriba el chunker, no de esta sesión.
- La estrategia de chunking alrededor de tablas (excluirlas del RAG
  narrativo vs. chunks grandes que las mantengan enteras) sigue sin
  decidir.
- Sin cambios en Nodo 1, Nodo 2, Nodo 4, servidor MCP, deploy esta
  sesión.

## 2026-08-17 (continuación 9) — Tratamiento de tablas en el chunking: Opción A, con evidencia de las tres opciones

**Contexto:** con PyMuPDFLoader ya decidido como loader, se pidió
recomendación (sin implementar) sobre cómo tratar las tablas del PDF en
el chunking -- tres opciones sobre la mesa: A) detectar y excluir del
texto narrativo (Node 4 ya tiene el dato cuantitativo de OpenFoodTox),
B) extraer aparte con librería especializada (`pdfplumber`/`camelot`),
C) aceptar la fragmentación confiando en que el contexto narrativo
alrededor compense. Se pidió explícitamente evidencia, no preferencia
teórica, y que ninguna opción se descartara por intuición.

**Evidencia 1 -- prevalencia real, no un caso raro:** escaneados los
161 PDFs con PyMuPDF (~23s). **146/161 (91%)** tienen al menos una
tabla, mediana de 7 por documento, hasta 23 en aspartamo.

**Evidencia 2 -- qué contienen, y que OpenFoodTox NO las cubre
(verificado, no asumido):** muestreadas 207 leyendas de tabla en 25
documentos al azar. Predominan MPLs, especificaciones de pureza,
grupos de población para exposición, "summary of dietary exposure" y
-- relevante para este proyecto -- "qualitative evaluation of
influence of uncertainties on the dietary exposure estimate". Un caso
(Red 2G, E128) tenía tablas de datos crudos de tumores/BMDL, base de
la derivación del ADI. `OpenFoodTox` solo aporta el ADI escalar +
justificación de texto libre -- nada del contenido de estas tablas
está en los campos estructurados. **El supuesto de partida de la
Opción A no era automáticamente cierto -- había que comprobarlo.**

**Evidencia 3 -- lo que sí sostiene la Opción A: la conclusión clave
suele estar ya en prosa en el Abstract (página 1).** Verificado
directamente en el PDF de fosfatos: el Abstract dice textualmente que
la exposición "ranged from 251 mg P/person per day in infants to
1,625... exceeded the proposed ADI for infants, toddlers and other
children" -- la conclusión de la Tabla 5a (página 42) ya está en la
página 1. Mismo patrón en el documento de cloruros. Verificado en 2
documentos, no en el corpus completo, pero consistente con estructura
estándar de abstract científico.

**Evidencia 4 -- Opción B probada de verdad, no descartada por
intuición.** Instalado `pdfplumber` (solo venv local, no en
`requirements.txt`) y ejecutado `extract_tables()` sobre la página de
la Tabla 5a. Resultado: reconstruye bien pares fila/columna dentro de
cada bloque, pero **fragmenta la tabla en 4 sub-tablas desconectadas**
y **pierde silenciosamente la columna "the elderly"** (6 de 7
columnas, sin ningún aviso de error) -- verificado contra la
extracción de texto plano de la misma tabla, que sí conserva las 7.
Con 1.137 tablas de layouts heterogéneos en el corpus, una solución de
producción exigiría reensamblado + validación por documento, con
riesgo demostrado (no hipotético) de perder datos en silencio.

**DECISIÓN: Opción A.** No por simplicidad -- porque la conclusión que
importa para este proyecto sobrevive en el Abstract sin la tabla
cruda, la Opción B tiene coste real y un fallo silencioso ya
demostrado, y la Opción C asume una compensación de contexto que en
la práctica viene de un chunk distinto (el Abstract), no de proximidad
real a la tabla fragmentada.

**Limitación aceptada explícitamente, no oculta:** se pierde el
desglose fino por subgrupo poblacional bajo cada escenario de
exposición -- aceptable para una herramienta de exploración de
literatura, no para una calculadora de exposición detallada (nunca fue
el objetivo del proyecto). Documentar en `LIMITATIONS.md` cuando se
implemente el chunker. Detalle completo, con las 4 evidencias
desarrolladas, en CLAUDE.md, "Hallazgos verificados".

**Pendiente / sin resolver al cierre de esta entrada:**
- **Nada implementado** -- ni la detección/exclusión de bloques de
  tabla, ni `pymupdf`/`pdfplumber` en `requirements.txt` (ambos solo en
  el venv local de esta sesión para las pruebas).
- Sin cambios en Nodo 1, Nodo 2, Nodo 4, servidor MCP, deploy esta
  sesión.

**Caso a vigilar anotado a posteriori (continuación 10), no bloqueante:**
Red 2G (E128) tiene tablas de datos crudos de tumores/BMDL -- base
PRIMARIA de la derivación del ADI, no un desglose secundario como MPLs
o exposición. La Evidencia 3 (Abstract restata la conclusión) solo se
verificó para tablas de exposición, no para este tipo de tabla -- es
plausible que un Abstract no recoja el mismo nivel de detalle
dosis-respuesta. **Si se hace QA manual del contenido narrativo del
Nodo 4 en el futuro, priorizar revisar este caso**
(`E128_10.2903_j.efsa.2007.515.pdf`) para confirmar si la Opción A deja
suficiente fundamento para el efecto crítico/NOAEL de esta sustancia.
Detalle en CLAUDE.md, "Hallazgos verificados".

## 2026-08-17 (continuación 11) — Splitter: `RecursiveCharacterTextSplitter` + `section_heading` vía fuente tipográfica, no vía regex

**Contexto:** con loader (PyMuPDFLoader) y tratamiento de tablas
(Opción A) ya decididos, se pidió verificar -- contra los mismos 3 PDFs
de referencia (corto/statement, largo/fosfatos, mediano/cloruros) -- si
la estructura de secciones es lo bastante consistente como para
justificar un splitter consciente de estructura, o si
`RecursiveCharacterTextSplitter` plano basta. Solo verificación, sin
implementar.

**Intento fallido, probado antes de descartarlo:** regex de encabezados
numerados sobre el texto plano de PyMuPDF. Un regex de una línea da 0
coincidencias en los 3 documentos -- `page.get_text()` (lo que expone
`PyMuPDFLoader`) separa el número del título en líneas distintas
(`"1.\nIntroduction\n..."`, no `"1. Introduction"`). Ampliando a
"número solo en su línea" sí aparece estructura real, pero con mucho
ruido: **725 coincidencias en el documento largo, 229 en el mediano** --
mayoría falsos positivos de números de página de pie de página y
artefactos de la tabla de contenidos.

**Señal que sí funciona, verificada en los 3 documentos:** tamaño y
familia de fuente (vía `page.get_text("dict")`, NO el texto plano)
distinguen encabezado de cuerpo de forma limpia -- 12pt fuente bold
para encabezados vs 10-11pt fuente regular para cuerpo, consistente en
los 3. La familia de fuente (variante bold) es más fiable que el
tamaño en puntos en solitario (un caso con versalitas hace variar el
tamaño dentro del mismo encabezado).

**Dos convenciones de encabezado distintas:** el statement corto usa 4
secciones planas en mayúsculas sin numeración (BACKGROUND/EVALUATION/
REFERENCES); los dos Scientific Opinion (fosfatos y cloruros) usan
jerarquía numerada idéntica hasta 4 niveles (`1.1.1.1`, `3.10.3`) --
misma plantilla EFSA Journal, no casualidad de un documento. Una
detección basada solo en numeración no cubriría el tipo Statement; la
señal de fuente sí generaliza a ambas, verificado.

**DECISIÓN:** `RecursiveCharacterTextSplitter` plano para los límites
de chunk (sin evidencia de que el regex numerado, poco fiable, mejore
sobre el splitter que ya respeta párrafos/frases). `section_heading`
como metadato aparte, extraído vía `get_text("dict")` -- relevante para
este proyecto porque el RAG se apoya en recuperar contenido de
secciones como "Discussion", no cualquier texto suelto.

**Nota importante para el chunker:** hace falta la API rica de PyMuPDF
(`get_text("dict")`), NO basta con `PyMuPDFLoader` de
`langchain_community` (solo expone texto plano, sin fuente) -- exige un
paso de extracción adicional con PyMuPDF directo, en paralelo al uso
del loader para el texto que alimenta al splitter. La lógica de
detección debe cubrir ambas convenciones de encabezado, no solo la
numerada. Detalle completo en CLAUDE.md, "Hallazgos verificados".

**Pendiente / sin resolver al cierre de esta entrada:**
- **Nada implementado** -- ni el splitter, ni la extracción de
  `section_heading`. Diseño verificado, pendiente de escribir con el
  resto del chunker.
- Sin cambios en Nodo 1, Nodo 2, Nodo 4, servidor MCP, deploy esta
  sesión.

## 2026-08-17 (continuación 12) — Pipeline de chunking implementado y validado en 5 PDF

**Contexto:** con loader, tratamiento de tablas, splitter y detección de
encabezados ya decididos (continuaciones 8-11), se pidió implementar el
pipeline completo -- extracción, detección de sección, exclusión de
tablas, troceo, resolución de sustancia en 3 niveles y ensamblado de
`RetrievedChunk` -- validado primero en modo `--dry-run`/`--limit`
(regla de CLAUDE.md sobre scripts en lote) sobre los 3 PDF de referencia
antes de tocar el corpus completo. Sin instalar nada nuevo (`pymupdf` y
`langchain-text-splitters` ya estaban en el venv de sesiones de prueba
anteriores, solo se añadieron a `requirements.txt` para reflejar que
ahora son dependencias reales del pipeline, no experimentos puntuales).

**Implementado:**
- `ingestion/pdf_naming.py` (nuevo): `clean_doi`/`e_numbers_from_title`/
  `destination_filename` extraídos de `scripts/generate_pdf_checklist.py`
  para que el chunker pueda mapear PDF -> fila del corpus con el mismo
  criterio, sin reimplementarlo. `generate_pdf_checklist.py` actualizado
  para importar de ahí -- verificado que el refactor es un no-op exacto
  (`diff` byte a byte del CSV regenerado contra el anterior).
- `openfoodtox.py::substances_per_dossier` -- nuevo parámetro
  `require_adi: bool = True` (Nivel 2 del diseño de 3 niveles, que
  seguía "propuesto, no implementado" desde la continuación 6). Default
  preserva el comportamiento anterior -- los 15 tests existentes siguen
  en verde.
- `ingestion/pdf_chunking.py` (nuevo): pipeline completo.
  - Extracción: PyMuPDF directo (`page.get_text("dict"/"blocks",
    textpage=tp)` sobre el MISMO textpage compartido -- verificado que
    `block_no` coincide 1:1 entre ambos modos, permite usar "blocks"
    para el texto y "dict" solo para decidir negrita).
  - **Hallazgo nuevo no anticipado en el diseño de continuación 11:**
    el modo "dict"/"rawdict" de PyMuPDF concatena palabras SIN espacio
    para varias fuentes bold incrustadas de estos PDF (glifo de espacio
    con avance cero en la fuente subseteada) --
    "Chemistryofphosphates" en vez de "Chemistry of phosphates".
    Confirmado que NO es un problema de espacios entre spans (gaps de
    bbox) sino de la fuente en sí (gaps intra-carácter también dan 0,
    los glifos están literalmente pegados). El modo "blocks" (mismo
    algoritmo de layout que la extracción de texto plano ya validada
    con 0 palabras rotas en la comparación PyPDFLoader-vs-PyMuPDFLoader)
    no tiene este problema -- por eso el texto de cada bloque sale de
    "blocks", nunca de "dict".
  - Detección de encabezado: fuente bold vía regex sobre el nombre de
    fuente (`bold|\.b(?:\+|$)`, case-insensitive) -- el bit `bold` del
    bitfield `flags` de PyMuPDF resultó SIEMPRE 0 para estas fuentes
    incrustadas/subseteadas (verificado: `flags=4` constante en fuentes
    bold y regular por igual), así que no es la señal fiable que
    parecía en el diseño de continuación 11 -- el nombre de fuente sí
    lo es.
  - Cabeceras/pies de página recurrentes (título del dictamen repetido
    en negrita en cada página, numeración de página, banner de descarga
    de Wiley) excluidos vía el mismo principio que
    `_discussion_boilerplate_texts` en `openfoodtox.py`: texto
    normalizado (dígitos fuera) que se repite en >=3 páginas distintas
    del mismo PDF no es contenido real. Verificado necesario -- sin
    esto, el título del dictamen repetido en negrita en casi todas las
    páginas se colaría como "encabezado de sección" en cada página.
  - Exclusión de tablas: `page.find_tables()` (bboxes) + patrón de
    leyenda `"Table N:"` anclado al inicio de bloque -- Opción A ya
    decidida.
  - Troceo: `RecursiveCharacterTextSplitter` (1000/150 por defecto, sin
    ajuste fino todavía) aplicado POR SECCIÓN (agrupada por el último
    encabezado visto, puede cruzar páginas) -- decisión de diseño de
    esta sesión, no estaba zanjada en continuación 11: mantiene
    `section_heading` exacto por chunk a costa de más chunks pequeños
    de los que daría trocear el documento entero de una vez (719 chunks
    para 156 páginas en el caso de fosfatos, con 164 secciones
    detectadas).
  - Resolución de sustancia: `resolve_dossier_substances` -- Nivel 1
    (`substances_per_dossier(require_adi=True)`) -> Nivel 2
    (`require_adi=False`) -> Nivel 3 (`_guess_substance_by_title`,
    coincidencia de nombre completo de palabra contra TODA la hoja
    `SUB`, se queda con el más largo si hay varios).
  - `RetrievedChunk`: un objeto por combinación (chunk, sustancia
    resuelta) -- implementa el esquema "N copias por chunk" ya
    diseñado en CLAUDE.md.
- `scripts/build_chunk_index.py` (nuevo): CLI con `--dry-run`
  (procesa solo los 3 PDF de referencia), `--limit N`, `--pdf
  <substring>`, y sin argumentos (mismo comportamiento que `--dry-run`,
  con aviso de cómo escalar) -- nunca procesa los 161 por accidente.
  `--save-preview <ruta>` opcional para volcar los chunks/metadatos a
  JSON, solo para inspección. No toca embeddings ni Chroma.

**Validado (dry-run + comprobaciones adicionales, sin procesar el corpus
completo):**
- Los 3 PDF de referencia (corto/statement, fosfatos, cloruros) +
  aspartamo E951 (`--pdf E951`) + 2 más vía `--limit 2` (quillaia E999,
  alginatos E400-404) -- 5 dossiers en total, sin errores.
- Cloruros -> 281 chunks, 4 sustancias tier 2 (sin ADI, coincide con lo
  ya documentado en CLAUDE.md), 1124 `RetrievedChunk`. Fosfatos -> 719
  chunks, 1 sustancia tier 1 (ADI de grupo único), 719 `RetrievedChunk`.
  Aspartamo -> 1033 chunks, 1 sustancia tier 1. Statement/sweeteners ->
  12 chunks, 0 sustancias resueltas por ningún nivel, 0 `RetrievedChunk`
  -- ver más abajo.
- **Exclusión de tablas verificada dos veces:** (1) smoke-test en el
  script (ningún chunk EMPIEZA con una leyenda "Table N:" -- primera
  versión del check usaba `re.search` sin anclar y daba falsos
  positivos sobre frases narrativas normales que mencionan una tabla
  por número, ej. "...summarised in Table 9.", corregido anclando al
  inicio del chunk); (2) verificación directa más fuerte contra el caso
  ya conocido de la Tabla 5a de fosfatos (CLAUDE.md, sesión de
  diagnóstico de tablas) -- confirmado que ni la leyenda ("Table 5a:
  Summary of dietary exposure...") ni una fila numérica real de esa
  tabla aparecen en ningún chunk generado.
- Flags de la CLI verificadas por separado: sin argumentos cae a los 3
  PDF de referencia con aviso; `--pdf E951` aísla un solo dossier;
  `--limit 2` procesa 2 dossiers correctamente.

**Decisión del usuario sobre el caso irresoluble (statement/sweeteners,
el único 1/162 sin sustancia por ningún nivel):** se mantiene el
comportamiento actual -- NO se le fuerza un `substance_uuid` vacío para
producir `RetrievedChunk`. Queda fuera del índice de retrieval POR
DISEÑO (misma disciplina que ya aplican los 3 niveles: preferir "sin
sustancia resuelta" a una identidad inferida sin respaldo real).
Documentado explícitamente en CLAUDE.md para que no se trate como una
laguna a rellenar más adelante.

**Pendiente / sin resolver al cierre de esta entrada:**
- **El corpus completo (161 PDF) no se ha procesado todavía** -- esta
  sesión validó el pipeline sobre 5 PDF a propósito, tal como se pidió
  ("un paso a la vez"). Antes de correrlo sobre los 161: decidir si
  vale la pena ajustar `chunk_size`/`chunk_overlap` (los 719 chunks de
  fosfatos para 156 páginas son más de lo que daría un troceo por
  documento completo en vez de por sección) y confirmar que no aparece
  ningún caso tier 3 real inesperado (los 2 casos conocidos,
  Sucralose/Shellac, no se han vuelto a probar explícitamente en esta
  sesión).
- **El paso de indexado en Chroma (embeddings + `chromadb`) sigue sin
  empezar** -- este pipeline produce `RetrievedChunk` en memoria a
  partir de un PDF, no un índice persistente. Es el siguiente paso
  lógico para desbloquear el Nodo 2 de verdad.
- Imprecisión cosmética observada, no bloqueante: títulos largos que
  envuelven en dos líneas a veces se detectan como dos bloques bold
  separados, dando un `section_heading` fragmentado para ese chunk
  concreto (ej. "chloride (E 511) as food additives" en vez del título
  completo) -- no pierde datos, solo hace menos legible esa etiqueta
  puntual.
- Sin cambios en Nodo 1, Nodo 2 (todavía `NotImplementedError`, ver
  arriba), Nodo 4, servidor MCP, deploy esta sesión.

## 2026-08-18 — Presupuesto de contexto del Nodo 4, filtro de longitud mínima, lote intermedio de 16 PDF, fix de guiones suaves

**Contexto:** antes de escalar el chunker a los 161 PDF, se pidió (1)
una estimación del presupuesto de contexto del Nodo 4 con chunks reales
(tamaño medio × k=3-5 recuperados), (2) un filtro de longitud mínima
para descartar chunks casi vacíos, y (3) validar el pipeline sobre un
lote intermedio de 15-20 PDF elegidos a propósito (no al azar) antes de
procesar el corpus completo.

**Presupuesto de contexto (sin tocar código, solo medición):** sobre los
2.559 chunks de los 6 PDF ya procesados -- media 704 caracteres/105
palabras por chunk, ~150-180 tokens estimados (dos métodos, sin
tokenizer real disponible: chars/4 y palabras/0,75, convergen). Con
k=3-5 chunks recuperados + system prompt del Nodo 4 (575 tokens,
medido) + bloque de `structured_result`: presupuesto total estimado
~1.250-2.000 tokens de entrada por consulta -- muy por debajo de
cualquier límite de contexto real, sin riesgo de truncamiento.
**Confirmado por el usuario contra la fuente de pricing real** (misma
tarifa punta/valle del 16-ago): con este contexto de `retrieved_chunks`
ya incluido, el coste sigue en ~$0,0005-0,0014/consulta, mismo orden de
magnitud que la estimación anterior (que se había medido con
`retrieved_chunks` vacío). CLAUDE.md actualizado con la cifra
recalculada.

**Implementado -- filtro de longitud mínima:**
`ingestion/pdf_chunking.py::split_sections` gana el parámetro
`min_chunk_length` (`MIN_CHUNK_LENGTH = 50` por defecto), descarta
cualquier chunk cuyo texto (sin espacios) quede por debajo del umbral
antes de que llegue a `TextChunk`/`RetrievedChunk`. Confirmado sobre los
2.559 chunks de los 6 PDF: **25 descartados (0,98%)** -- exactamente los
mismos 25 <50 caracteres ya medidos en la sesión anterior. Tras el
filtro: 2.534 chunks, media prácticamente sin cambios (704 -> 710,5
caracteres), mínimo 51 caracteres.

**Lote intermedio de 16 PDF, elegidos a propósito (no al azar) --
criterios cumplidos:** (1) al menos un caso de los "22 multi-sustancia
sin ADI" -- celulosas E460-469 (10 sustancias, todas tier 2); (2) al
menos un título largo susceptible de partirse en dos bloques bold --
tartratos E334-337+354, que además resultó ser uno de 8 casos, no 1;
(3) variedad de tamaño de documento, de 5 a 157 páginas; más 2 casos
tier 3 nunca antes probados con datos reales (Shellac, statement de
sucralosa). `--pdf` de `scripts/build_chunk_index.py` ampliado para
aceptar varios substrings separados por coma, para poder lanzar el
lote entero en una sola llamada.

**Resultado: 16 PDF, 4.753 chunks (tras el filtro de longitud mínima),
sin ningún crash, sin ninguna fuga de tabla, sin ningún dossier sin
sustancia resuelta más allá del 1/162 ya documentado como excluido por
diseño.** Tier 1: tartratos (7 sustancias), nitritos (3, con el mismo
filtro de compuestos N-nitroso funcionando correctamente), sorbatos (2),
dimetilpolisiloxano, sulfitos (grupo con UN solo ADI de grupo, mismo
patrón que fosfatos -- ver más abajo), luteína, acesulfamo K. Tier 2:
celulosas (10), β-caroteno, tragacanto, 4-hexilresorcinol, TiO2 (sin
ADI, esperado), silicatos de Na/K aluminio (2), eritritol. **Tier 3
validado por primera vez con datos reales: Shellac y sucralosa
(statement) resuelven correctamente por coincidencia de nombre en el
título** -- cerraba un hueco de validación explícitamente pendiente de
la sesión anterior.

**Hallazgo nuevo, real, arreglado en esta sesión -- guiones suaves
(U+00AD) incrustados literalmente en el texto extraído de los PDF más
recientes.** Verificado: Shellac (2024) y Acesulfame K (2025) tienen el
carácter en 198 y 474 bloques respectivamente (1.168 apariciones solo
en el de acesulfamo -- esencialmente todo el documento); CERO en todos
los PDF anteriores a 2024 comprobados (aspartamo 2013, cloruros 2019,
TiO2 2021) -- cambio real de plantilla de Wiley, no un problema
preexistente sin detectar. Sin arreglarlo, "Re-evaluation" salía como
"Re-\xadevaluation" en el texto de cada chunk de estos documentos. Fix:
`extract_raw_blocks` quita `\xad` del texto de cada bloque nada más
extraerlo, antes de deduplicación/detección de encabezado/troceo.
Verificado limpio tras el fix en ambos PDF afectados (0 apariciones
restantes, títulos legibles).

**Confirmado, a petición del usuario, NO arreglado a propósito --
título largo partido en dos bloques bold:** el problema cosmético ya
visto en cloruros/fosfatos resultó sistémico, no raro -- presente en 8
de los 16 PDF de este lote (tartratos, nitritos, sorbatos, celulosas,
dimetilpolisiloxano, sulfitos, silicatos, TiO2), todos de la plantilla
EFSA/Wiley anterior a 2024. **Trade-off confirmado con el fix de
guiones suaves de arriba:** los 2 PDF de la plantilla 2024+ (Shellac,
Acesulfame K) NO tienen el problema de título partido -- su título
largo se queda en un solo bloque pese a envolver 2 líneas -- pero sí
tienen (tenían) el problema de guiones suaves. Ninguna plantilla es
limpia en los dos frentes. Decisión del usuario: documentar como
limitación conocida de baja prioridad en CLAUDE.md, no arreglar ahora
-- solo afecta la etiqueta `section_heading` de un puñado de chunks al
inicio del documento, sin pérdida de datos, confirmado dos veces.
También documentado, sin investigar más: el statement de luteína
produjo un par de encabezados de sección raros ("level*", "reported
use"), misma clase de imprecisión cosmética (probablemente fragmentos
de leyenda/subtítulo en negrita fuera del bbox de tabla detectado).

**Pendiente / sin resolver al cierre de esta entrada:**
- El corpus completo (161 PDF) sigue sin procesarse -- 22 PDF
  validados hasta ahora (6 + 16), sin bloqueantes encontrados.
- El paso de indexado en Chroma (embeddings + `chromadb`) sigue sin
  empezar.
- Título partido en dos bloques bold: limitación conocida, no
  arreglada a propósito (ver CLAUDE.md).
- Encabezados raros del statement de luteína: anotados, no
  investigados a fondo.
- Sin cambios en Nodo 1, Nodo 2, Nodo 4, servidor MCP, deploy esta
  sesión.

## 2026-08-18 (continuación) — Corpus completo procesado (161/161), persistido a disco, alcance real del bug de guiones suaves corregido

**Contexto:** con el lote de 22 PDF validado sin bloqueantes, se pidió
procesar los 161 PDF completos -- por lotes con progreso visible, no en
una sola llamada silenciosa, parando y reportando si aparecía algún
error nuevo en vez de saltarlo. Antes de eso, dos verificaciones
pedidas explícitamente: (1) confirmar que el bug de guiones suaves no
aparece en ningún PDF fuera de los 2 ya encontrados, y (2) persistir el
resultado a disco antes de tocar embeddings, para no tener que
reprocesar los 161 PDF si el siguiente paso falla a mitad.

**Implementado en `scripts/build_chunk_index.py`:**
- `--all`: procesa los 161 dossiers en lotes de `BATCH_SIZE=20`, una
  línea corta por PDF (no el detalle completo de `--dry-run`/`--pdf`,
  inmanejable 161 veces) + un marcador `=== LOTE N/9 completo ===` al
  cierre de cada lote + un `=== RESUMEN FINAL ===` con total de chunks,
  distribución de sustancias por tier, PDF con 0 chunks y PDF sin
  ninguna sustancia resuelta. **Si un PDF concreto lanza una excepción
  no esperada, el script para inmediatamente (`sys.exit(1)`,
  traceback completo) -- no la traga ni sigue con el siguiente.**
- `--save-jsonl <ruta>`: persiste una línea JSON por (chunk, sustancia
  resuelta) -- mismos campos que `RetrievedChunk` más `pdf_filename` y
  `chunk_group_id` (nuevo, solo en la persistencia -- id compartido
  entre las N copias del mismo chunk, el esquema "N copias por chunk"
  ya diseñado en CLAUDE.md para Chroma). Escrito y `flush()` tras CADA
  dossier, no al final -- un fallo a mitad de la corrida deja intacto
  todo lo ya escrito.
- `--pdf` ampliado (ya en la sesión anterior) para aceptar varios
  substrings separados por coma.
- Lanzado con `Monitor` filtrando por los marcadores de lote/resumen/
  error (no por cada línea de PDF, serían 161 notificaciones) -- 9
  eventos de progreso + 1 resumen final, en vez de una espera ciega.

**Verificación 1 -- alcance real del bug de guiones suaves, CIFRA
CORREGIDA:** un escaneo del texto CRUDO (antes del fix, `page.get_text
("blocks")` directo) sobre los 161 PDF encontró **10 PDF afectados, no
2** -- el lote de 22 solo había incluido 2 por azar de la selección:
E1204 (2025, 310 apariciones), E174 (2025, 561), E472C (2025, 584),
E551 (2024, 919), E904/Shellac (2024, 463 -- ya conocido), E943A-E943B-
E944 (2025, 171), E950/Acesulfame K (2025, 1.357 -- ya conocido),
E954/sacarina (2024, 1.749), E961/neotamo (2025, 1.250), E968 (2023,
solo 8). Todos 2023-2025, cero en cualquier PDF anterior comprobado --
confirma que es un cambio de plantilla real, con un límite de fecha
más amplio de lo que se había visto (2023, no solo 2024+). **El fix ya
implementado en la sesión anterior es genérico (no específico de
ningún PDF) -- cubre los 10 sin tocar código**, verificado
explícitamente: 0 apariciones restantes en cada uno de los 10 tras
re-extraer con el fix aplicado.

**Hallazgo colateral, no buscado, mientras se investigaba el alcance
del bug anterior:** al usar la API de `pymupdf.TOOLS.mupdf_warnings()`
(la única forma de capturar los avisos de la librería MuPDF -- no
salen por `sys.stderr` de Python) para identificar qué PDF disparaba un
warning puntual ("No default Layer config", resultó ser
`E128_10.2903_j.efsa.2007.515.pdf` -- el mismo Red 2G ya señalado en
sesiones anteriores como caso a vigilar por sus tablas de BMDL/tumores,
coincidencia anotada pero no investigada más), se encontraron avisos de
MuPDF en la mayoría de los 161 PDF -- la mayoría benignos y ya
esperables para PDF con fuentes incrustadas/subseteadas ("freetype
could not find any cmaps", "repaired broken tree structure in
outline", "bogus font ascent/descent values"). **Uno más serio, nuevo,
no visto hasta ahora: "ActualText with no position. Text may be lost
or mispositioned."** -- aparece en los MISMOS 7 de los 10 PDF del
hallazgo de guiones suaves (E1204, E174-2025, E472C, E943A-E943B-E944,
E950, E961, E968-2023), 9-33 apariciones cada uno. Spot-check (solo 1
de los 7, Acesulfame K): el aviso solo sale en las páginas 1-2
(portada/lista de autores), no en el resto del documento (3-74), y la
densidad de caracteres extraídos por página (5.467 de media) no
muestra ninguna zona anómala -- consistente con que sea ruido de
etiquetas de accesibilidad en el membrete con espaciado de letras ya
visto ("S C I E N T I F I C O P I N I O N"), no pérdida de contenido
narrativo real. **NO verificado de forma rigurosa en los otros 6 PDF
afectados** -- anotado en CLAUDE.md como algo a revisar primero si
aparece contenido con lagunas raras en QA del Nodo 4 para cualquiera de
estos 7 documentos.

**Verificación 2 -- corpus completo procesado y persistido:**
`python scripts/build_chunk_index.py --all --save-jsonl
data/processed/chunks.jsonl` -- **161/161 dossiers, sin errores, sin
ningún PDF con 0 chunks, 35.991 chunks, 67.827 RetrievedChunk**.
Distribución de sustancias resueltas por tier (256 pares dossier-
sustancia): tier 1 = 105, tier 2 = 149, tier 3 = 2 (exactamente los 2
casos conocidos, Shellac y sucralosa statement -- ningún tier 3 nuevo
inesperado en todo el corpus). Un solo dossier sin sustancia resuelta,
el mismo 1/162 ya documentado (`sinE_10.2903_j.efsa.2011.1996.pdf`).
Cifras IDÉNTICAS a una corrida previa sin persistir (lanzada antes de
aplicar el fix ampliado a los 10 PDF -- confirma que quitar `\xad` no
cambia el número de chunks de forma perceptible, solo limpia el
texto).

**`data/processed/chunks.jsonl` verificado tras escribirse:** 67.827
líneas (coincide exacto con el total reportado), 85 MB, 160 dossiers
únicos representados (161 procesados menos el 1 sin sustancia
resuelta, que no aporta ninguna fila), recuento de tiers a nivel de
FILA (no de par dossier-sustancia): tier 1 = 29.782, tier 2 = 37.699,
tier 3 = 346 -- **346 coincide exacto con la suma de chunks de los 2
dossiers tier 3** (270 Shellac + 76 sucralosa statement), comprobación
de consistencia interna en verde. Ya está en `.gitignore`
(`data/processed/`), mismo motivo de licencia que `data/chroma/` --
texto literal de los PDF, ver la decisión de licencia en CLAUDE.md.

**CLAUDE.md actualizado:** cifra de guiones suaves corregida de 2 a 10
PDF (con la lista completa), nuevo hallazgo de `ActualText` documentado
sin investigar más, resumen del corpus completo + ubicación del JSONL
añadidos al pendiente #5 de "Estado del código".

**Pendiente / sin resolver al cierre de esta entrada:**
- El aviso `ActualText`/posible pérdida de texto: spot-check solo en 1
  de los 7 PDF afectados, no confirmado en los otros 6. No bloqueante
  (evidencia disponible apunta a ruido de portada, no a contenido
  narrativo perdido), pero anotado para revisar si aparece algo raro
  en QA del Nodo 4.
- El paso de indexado en Chroma (embeddings + `chromadb`) sigue sin
  empezar -- `data/processed/chunks.jsonl` es el material de partida
  para ese paso, ya persistido y verificado.
- Sin cambios en Nodo 1, Nodo 2, Nodo 4, servidor MCP, deploy esta
  sesión.

## 2026-08-18 (continuación 2) — Investigación completa del aviso ActualText en los 7 PDF afectados, cerrado sin pérdida de texto

**Contexto:** la sesión anterior dejó pendiente verificar el aviso de
MuPDF "ActualText with no position. Text may be lost or mispositioned"
en los 6 PDF que no se habían comprobado (solo se hizo spot-check de
Acesulfame K). Se pidió el mismo criterio en los 6 restantes: ¿se
limita a portada/membrete, o aparece en páginas de contenido real
(Discussion, resultados)? Si aparece en contenido real, identificar
cuál antes de seguir.

**Metodología:** para cada uno de los 6 PDF restantes (E1204, E174,
E472C, E943A-E943B-E944, E961, E968), se identificaron con
`pymupdf.TOOLS.mupdf_warnings()` las páginas EXACTAS donde salta el
aviso, se inspeccionó qué contenido hay en cada página, y para
cualquier página con contenido narrativo real (no portada/TOC/tabla de
apéndice) se leyó el TEXTO COMPLETO extraído buscando corrupción real
(frases cortadas, repeticiones, incoherencia) -- no solo densidad de
caracteres, que es un proxy más débil.

**Resultado: el patrón NO es "solo portada" en todos los casos, pero la
pregunta de fondo (¿se pierde texto?) se resuelve en NO para los 7.**
- E1204/pullulan y E472C/E943-E944: solo portada/CONTENTS/tabla de
  contenidos/tablas de apéndice -- ningún contenido narrativo marcado.
- E961/neotamo: portada + páginas 57-62, TODAS dentro de un apéndice de
  tablas (BMD/QSAR) -- verificada directamente la página 57 (marcada
  "sospechosa" por baja densidad de caracteres): es literalmente una
  tabla de datos QSAR, la baja densidad es esperable en una tabla, no
  pérdida -- y ese contenido se excluye igualmente del texto narrativo
  por Opción A.
- **E174/plata SÍ marca páginas de contenido narrativo real (12, 15,
  16) -- incluida la propia Sección 4 "DISCUSSION" completa.** Leído el
  texto íntegro de las 3 páginas: coherente, sin frases cortadas, sin
  repeticiones, con notas al pie y citas en su sitio.
- **E968/eritritol SÍ marca la página 41, Secciones 6 "CONCLUSIONS" y 7
  "RECOMMENDATION"** (incluye el ADI de 0,5 g/kg pc/día). Leído
  íntegro: coherente y completo.

**Conclusión, documentada en CLAUDE.md, caso CERRADO:** el aviso de
MuPDF no se traduce en pérdida de texto real en ninguno de los 7 PDF,
ni siquiera en las 2 páginas donde coincide con Discussion/Conclusions
reales -- probablemente lo dispara otro elemento con estilo especial en
esa misma página (nota al pie, subíndice, cabecera repetida) sin
afectar la prosa principal. No requiere exclusión de chunk ni revisión
manual. No reabrir sin evidencia nueva de contenido realmente perdido.

**Pendiente / sin resolver al cierre de esta entrada:**
- Ninguno relacionado con este hallazgo -- cerrado.
- El paso de indexado en Chroma (embeddings + `chromadb`) sigue sin
  empezar -- sigue siendo el siguiente paso lógico, ahora sin ningún
  hallazgo de calidad de texto pendiente de verificar.
- Sin cambios en Nodo 1, Nodo 2, Nodo 4, servidor MCP, deploy esta
  sesión.

## 2026-08-18 (continuación 3) — Diseño y prueba del indexado en Chroma: modelo, esquema de metadatos, lote de prueba

**Contexto:** siguiente paso tras persistir `chunks.jsonl` -- generar
embeddings y poblar Chroma. Se pidió (1) confirmar el modelo de
embeddings (`all-MiniLM-L6-v2` propuesto por defecto) y verificar que
se instala/descarga bien, (2) diseñar el esquema de metadatos a partir
de los campos de `RetrievedChunk`, y (3) probar con un lote pequeño
(200-300 chunks de aspartamo + tartratos) midiendo tiempo y proyectando
al corpus completo -- sin procesar los 67.827 todavía.

**Gap encontrado antes de diseñar el esquema:** el brief mencionaba
`e_number` como campo "que ya tiene `RetrievedChunk`" -- no es así, y
al verificarlo se confirmó que **`SUB` no tiene ningún campo de
E-number en absoluto** (columnas reales: `Document UUID`,
`Definition`, `Parent UUID`, `ChemicalName`, `OwnerLegalEntity`,
`ReferenceSubstance.ReferenceSubstance`,
`TypeOfSubstance.Composition[.Other]`, `TypeOfSubstance.Origin[.Other]`
-- confirmado sobre la fila de aspartamo). Esto cierra el pendiente #2
de CLAUDE.md (limitación de Nodo 1 con E-numbers), que llevaba abierto
desde el diseño original. Consultado el usuario: **decisión -- omitir
`e_number` del esquema de metadatos de Chroma**, no fabricar un mapeo
sustancia-E-number a partir del título del dossier (mismo problema que
ya se conoce: en dossiers de grupo como tartratos, 5 E-numbers en el
título no mapean 1:1 a las 7 sustancias resueltas). La resolución de
E-numbers en el Nodo 1 queda para una tabla auxiliar futura, separada
del índice de Chroma -- documentado explícitamente en CLAUDE.md.

**(1) Modelo de embeddings:** `sentence-transformers` (5.7.0) y
`chromadb` (1.5.9) ya estaban instalados en el venv -- no hizo falta
instalar nada. `all-MiniLM-L6-v2` se descarga y carga sin problemas
(3,4-7,7 s). **Hallazgo relevante: hay GPU disponible en este entorno**
(`model.device` -> `cuda:0`) -- anotado en CLAUDE.md que esto NO es
representativo de un despliegue gratuito solo-CPU, hay que remedir ahí
antes de dar la proyección por buena para producción.

**(2) Esquema de metadatos -- implementado en
`ingestion/chroma_index.py`:** `substance_uuid`, `chemical_name`,
`dossier_uuid`, `dossier_title`, `substance_resolution_tier` (int),
`doi`, `pdf_filename`, `chunk_group_id`, `is_group_dossier` (bool,
nuevo -- calculado contando sustancias distintas por `dossier_uuid`),
`section_heading` y `page_number` cuando no son `None`. **Verificado
directamente (no asumido): Chroma lanza `TypeError` con valores `None`
en metadatos** -- `section_heading` es `None` en 116/67.827 filas
(0,17%), así que la clave se OMITE en vez de escribir `None` -- y
Chroma SÍ admite metadatos con claves distintas entre documentos de la
misma colección, confirmado con una prueba directa. `doi` y
`page_number` no tuvieron ningún `None` en las 67.827 filas reales
(verificado), pero el código los trata con la misma cautela por si el
jsonl se regenera con datos distintos.

**(3) Lote de prueba -- `scripts/build_chroma_index.py --test-batch`:**
**Primer intento con un tope global de 300 filas cargó 300/300 de
tartratos y 0 de aspartamo** -- el orden de lectura del jsonl (el orden
en que `--all` procesó los PDF) hizo que tartratos llenara el lote
antes de llegar a aspartamo, dejando el lote no representativo del caso
"sustancia única" que se quería probar. Corregido: tope POR PDF (150 +
150), confirmado 150/150 en la re-ejecución.
- Embeddings: **435,5 chunks/s** sobre las 300 filas reales (GPU).
- Escritura en una colección Chroma EFÍMERA (en memoria, no toca
  `data/chroma/`): 0,39 s para 300 entradas.
- Verificación de filtro por metadato (`where substance_uuid=...`):
  funciona, devuelve el `chemical_name` correcto.
- **Consulta semántica de humo con una pregunta real** ("genotoxicity
  studies and safety assessment", no un embedding ya en la colección --
  ese caso trivial solo demuestra que texto idéntico da distancia 0,
  no que la búsqueda semántica funcione) -- distancias en rango real
  (0,75-0,93, no degenerado), resultados temáticamente correctos
  (chunks sobre genotoxicidad) y favoreciendo aspartamo sobre
  tartratos, plausible dado el histórico de escrutinio de genotoxicidad
  de aspartamo. Buena señal de que el pipeline completo (embedding +
  metadato + filtro + similitud) funciona de extremo a extremo antes
  de comprometerse a los 67.827.
- **Proyección para el corpus completo: ~2,6 min de embeddings + ~1,5
  min de escritura + carga del modelo ≈ 4,1 min en total, en GPU.**

**Pendiente / sin resolver al cierre de esta entrada:**
- **El corpus completo (67.827 filas) NO se ha indexado todavía** --
  esta sesión fue solo el lote de prueba, tal como se pidió
  explícitamente.
- La proyección de ~4,1 min asume GPU -- no representativa si el
  indexado real se hace en un entorno solo-CPU (ej. para preparar el
  índice horneado de despliegue, ver Opción A). Volver a medir en ese
  entorno antes de asumir el mismo tiempo.
- Falta implementar el indexado del corpus completo en una colección
  Chroma PERSISTENTE (`data/chroma/`) -- el script actual solo escribe
  en una colección efímera de prueba.
- Tabla auxiliar E-number -> substance_uuid para el Nodo 1: diseño
  propuesto, no implementada.
- Sin cambios en Nodo 1, Nodo 2, Nodo 4, servidor MCP, deploy esta
  sesión.

## 2026-08-18 (continuación 4) — Indexado completo de los 67.827 chunks en data/chroma/, verificado

**Contexto:** con el lote de prueba validado (435,5 chunks/s, esquema
de metadatos cerrado), se pidió indexar el corpus completo en la
colección persistente, confirmar el tiempo real (no solo la
proyección), correr consultas de verificación adicionales -- incluida
una específica sobre un caso ya conocido (TiO2) -- y documentar la
advertencia GPU-vs-CPU de cara al despliegue. Explícitamente NO tocar
el Nodo 2 todavía, solo confirmar que el índice completo quedó bien
poblado y es consultable.

**Implementado en `scripts/build_chroma_index.py`:**
- `--all`: indexa los 67.827 chunks completos en `data/chroma/`
  (cliente `chromadb.PersistentClient`, colección
  `efsa_reevaluation_chunks`) -- borra la colección si ya existía antes
  de reindexar (evita duplicados de una corrida previa; el reindexado
  es un rebuild completo, no incremental). Escribe en lotes de
  `min(client.get_max_batch_size(), 5000)` (5.461 real en esta versión
  de Chroma) -- Chroma tiene un límite de tamaño de lote por `add()`,
  verificado con la API en vez de asumir un número.
- `--verify`: conecta a la colección persistente YA creada (sin
  reindexar) y corre las consultas de verificación -- reutilizable en
  cualquier momento posterior sin tener que volver a lanzar `--all`.

**Ejecutado `--all` -- tiempo REAL medido, no proyección:**
- Carga del modelo: 3,4 s.
- Embeddings: **1,27 min a 887,3 chunks/s** -- más del doble de rápido
  que la tasa del lote de prueba (435,5 chunks/s). Causa: aquí se pasó
  `batch_size=256` explícito a `model.encode()`, frente al valor por
  defecto (32) usado implícitamente en la llamada del lote de prueba --
  mismo modelo, misma GPU, la diferencia es solo el tamaño de lote
  interno.
- Escritura en Chroma: 1,51 min.
- **TOTAL: 2,97 min** -- más rápido que la proyección de ~4,1 min hecha
  con el lote de 300 (por el motivo del `batch_size` de arriba, no por
  un error en la proyección).
- Verificado `collection.count() == 67827` tras escribir -- coincide
  exacto con el total esperado. 597 MB en disco
  (`data/chroma/chroma.sqlite3`).

**3 consultas de verificación sobre el índice COMPLETO (no el lote de
prueba), temas deliberadamente distintos:**
1. *"genotoxicity studies and safety assessment"* -- top 5 incluye la
   sección `4.3. Genotoxicity` del TiO2 vigente (E171, 2021) junto con
   contenido de sílice y eritritol.
2. *"why was titanium dioxide withdrawn as a food additive"* -- **los
   5 resultados vienen de los 2 dossiers de TiO2** (2016 y 2021),
   incluidas las secciones `1. Introduction` y `Summary` explicando la
   re-evaluación -- caso conocido pedido explícitamente como prueba,
   resultado correcto.
3. *"dietary exposure assessment uncertainties"* -- top 5 mezcla
   secciones "Uncertainty analysis" de 5 aditivos distintos
   (verificado contra `chemical_name`, no adivinado a ojo:
   poliglicerol poliricinoleato E476, octyl gallate E311,
   cochinilla/ácido carmínico E120, dimetil dicarbonato E242, dodecyl
   gallate E312) -- confirma que el pipeline generaliza a un tema
   distinto de genotoxicidad, no es un acierto aislado.

**CLAUDE.md actualizado:** pendiente #5 de "Estado del código" marcado
COMPLETADO (con la salvedad explícita de que conectar el índice al
Nodo 2 sigue sin hacerse, a propósito, no se pidió en esta sesión); el
bullet de modelo de embeddings en "Decisiones de arquitectura ya
tomadas" ampliado con el tiempo real, las 3 consultas de verificación,
y una advertencia explícita GPU-vs-CPU para el tiempo de
reconstrucción del índice de cara al despliegue (la Opción A construye
el índice en local/CI, que puede o no tener GPU -- no asumir que el
reindexado en el entorno de despliegue real tardará lo mismo que aquí).

**Pendiente / sin resolver al cierre de esta entrada:**
- **Nodo 2 (`hybrid_retrieval_node`) sigue en `NotImplementedError`,
  a propósito** -- se pidió explícitamente no tocarlo en esta sesión.
  El índice ya existe, está poblado y es consultable
  (`scripts/build_chroma_index.py --verify` lo confirma en cualquier
  momento), pero nada en el grafo LangGraph lo usa todavía. Ese es el
  siguiente paso lógico.
- Tiempo de reconstrucción del índice en un entorno solo-CPU: no
  medido, solo advertido -- medir en el entorno de despliegue real
  antes de asumir minutos similares a los 2,97 min de aquí.
- Tabla auxiliar E-number -> substance_uuid para el Nodo 1: sigue sin
  implementar (propuesta en la sesión anterior).
- Sin cambios en Nodo 1, Nodo 4, servidor MCP, deploy esta sesión.

## 2026-08-18 (continuación 5) — Nodo 2 (hybrid_retrieval_node) implementado y conectado a Chroma

**Contexto:** con Chroma poblado (67.827 chunks) y verificado, se pidió
implementar `hybrid_retrieval_node` -- tomar `substance_uuid` del Nodo
1, buscar en Chroma filtrado por esa sustancia con la pregunta del
usuario como query (k=3-5, el mismo rango del cálculo de presupuesto
de contexto), construir `RetrievedChunk` copiando `substance_resolution_tier`
tal cual de los metadatos (sin re-derivarlo), y dejar `retrieved_chunks`
vacío sin llamar a Chroma si no hay `substance_uuid`. Sin llamar al LLM
-- solo la parte de retrieval. Con test real de aspartamo antes de dar
por terminado.

**Implementado en `graph/nodes.py`:**
- `NodeDependencies` gana el campo `embedding_model` (además del ya
  existente `vectorstore`) -- ambos tipados como `object` a propósito,
  mismo principio de desacoplamiento ya aplicado a `LLMClient` (no
  atar `graph/nodes.py` a la API concreta de chromadb/
  sentence-transformers).
- `DEFAULT_RETRIEVAL_K = 5` -- extremo superior del rango k=3-5 del
  cálculo de presupuesto de contexto (ver sesión 18-ago-2026,
  continuación 3), elegido porque el presupuesto seguía siendo
  razonable ahí.
- `hybrid_retrieval_node`: si `substance_uuid` es `None`, devuelve
  `retrieved_chunks: []` de inmediato SIN tocar `deps.vectorstore` --
  verificado explícitamente en el test (ver abajo), no solo asumido.
  Si hay `substance_uuid`: embede `user_query` con
  `deps.embedding_model.encode(...)`, llama a
  `deps.vectorstore.query(query_embeddings=..., where={"substance_uuid":
  ...}, n_results=DEFAULT_RETRIEVAL_K)`, y construye `RetrievedChunk`
  copiando cada campo directamente de los metadatos devueltos por
  Chroma -- `substance_resolution_tier` incluido, sin volver a
  calcularlo.
- Nota de diseño sobre el brief original: se pidió "tomar
  substance_uuid... (o substance_name si el UUID no se resolvió)" --
  interpretado como qué inputs tiene disponibles el Nodo 2 en el
  estado, no como una instrucción de usar `substance_name` como filtro
  alternativo: Chroma no tiene ningún campo de metadato indexado por
  nombre libre de sustancia, y la instrucción posterior del mismo
  mensaje ("si substance_uuid es None... no llames a Chroma, deja
  retrieved_chunks vacío") es inequívoca y es la que se implementó.

**Tests nuevos en `tests/test_nodes.py`** (se saltan si `data/chroma/`
no existe, mismo patrón que los tests dependientes del xlsx):
- `test_hybrid_retrieval_node_aspartame_real_query`: consulta REAL
  ("What genotoxicity and carcinogenicity studies were considered for
  aspartame?", no genérica -- para no acertar por casualidad con un
  fragmento de portada sin `section_heading`, el 0,17% de chunks con
  ese campo en `None`) contra el índice completo de 67.827 chunks.
  Verifica: entre 1 y `DEFAULT_RETRIEVAL_K` resultados, TODOS con
  `substance_uuid` de aspartamo, TODOS con `chemical_name ==
  "Aspartame"`, TODOS con `section_heading` no vacío, TODOS con
  `substance_resolution_tier == 1` (aspartamo es tier 1, ADI real).
- `test_hybrid_retrieval_node_no_uuid_skips_chroma_entirely`: pasa un
  vectorstore de prueba que LANZA una excepción si se le llama --
  confirma que sin `substance_uuid` de verdad no se invoca a Chroma,
  no solo que el resultado da vacío por casualidad.
- **21/21 tests pasan** (19 previos + 2 nuevos), ~89 s de tiempo total.

**CLAUDE.md/PROGRESS.md actualizados:** "Estado del código" refleja el
Nodo 2 implementado (ya no `NotImplementedError`); el pendiente #5
(chunking/embeddings/Chroma) queda cerrado de extremo a extremo.

**Pendiente / sin resolver al cierre de esta entrada:**
- No se ha probado el flujo COMPLETO del grafo (Nodo 1 -> 2 -> 3 -> 4)
  en una sola ejecución -- cada nodo se ha probado por separado
  (Nodo 2 en esta sesión, Nodo 4 en sesiones anteriores). No se llamó
  al LLM en esta sesión, tal como se pidió explícitamente.
- Nodo 1 (extracción de entidad con LLM) sigue sin implementar --
  bloquea poder probar el grafo completo de extremo a extremo con una
  pregunta en lenguaje natural real (hoy hay que pasar `substance_uuid`
  a mano en el estado para probar el Nodo 2).
- Tabla auxiliar E-number -> substance_uuid para el Nodo 1: sigue
  sin implementar.
- `graph/build.py` (ensamblado del grafo LangGraph completo, wiring de
  `NodeDependencies` con las instancias reales de store/vectorstore/
  embedding_model/llm_client) sigue sin existir -- cada nodo se
  instancia a mano en los tests, no hay un punto de entrada único
  todavía.
- Servidor MCP, deploy: sin cambios esta sesión.

## 2026-08-18 (continuación 6) — CORRECCIÓN: Nodo 1 NUNCA estuvo implementado, error de documentación desde la sesión 1

**Contexto:** al cerrar la sesión anterior afirmé que "el Nodo 1 sigue
sin implementar", como si fuera un hecho ya conocido. El usuario señaló
correctamente que eso contradice varias entradas anteriores de este
mismo archivo y de CLAUDE.md que dan el Nodo 1 por implementado y
probado contra la API real -- y pidió verificar el estado REAL del
código directamente, no de memoria, y si de verdad no está
implementado, investigar cuándo se perdió.

**Verificado directamente contra el código, no de memoria:**
`extract_entity_node` en `src/efsa_rag/graph/nodes.py` es, ahora mismo:

```python
def extract_entity_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Identifica qué aditivo/E-number pregunta el usuario.

    TODO: llamada real al LLM con prompt corto (~200 tokens de entrada,
    ver estimación de coste en docs/). Placeholder de contrato.
    """
    raise NotImplementedError
```

Ningún `NODE_1_ENTITY_EXTRACTION_PROMPT` en todo `src/` (`grep -rn
"NODE_1"` no encuentra nada).

**No es una regresión -- nunca se implementó, en ningún commit.**
Comprobado el contenido EXACTO de `extract_entity_node` en los 3
commits del historial completo del repo (`c18ddc9` -- scaffold
inicial, `5bfc39d` -- sesión 2-3, `d30001c` -- sesiones 17-ago
continuación 2-11): **el placeholder es idéntico, carácter a carácter,
en los tres.** Nada se revirtió ni se perdió sin commitear -- el código
nunca tuvo una implementación real que perder.

**Origen del error, encontrado:** la primerísima entrada de este
archivo (sesión 2026-08-16, sección "Implementado") dice:

> `graph/nodes.py`: Nodo 3 y Nodo 1 implementados. Nodo 2 y Nodo 4
> pendientes de conectar (contratos definidos, `NotImplementedError`).

Esto era FALSO en el momento en que se escribió -- verificado que en
ESE MISMO commit (`c18ddc9`), Nodo 3 (`verify_currency_node`) sí tenía
código real (llama a `deps.store.current_reference_value_opinion(...)`,
lógica de `vigencia_ambigua`), pero Nodo 1 ya era
`raise NotImplementedError`, igual que Nodo 2 y Nodo 4. La frase
acreditó incorrectamente a Nodo 1 el trabajo que solo se había hecho en
Nodo 3 -- error de redacción en el momento de escribir el resumen de la
sesión, no un hecho que se volviera falso después.

**Por qué se sostuvo sin detectarse tantas sesiones:** esa primera
frase falsa sembró una cadena de menciones posteriores a una
"limitación conocida del Nodo 1" (coincidencia exacta de nombre en
inglés, no maneja español ni E-numbers) que en realidad describe
`OpenFoodToxStore.substance_uuid_by_name` (`ingestion/openfoodtox.py`)
-- una función que SÍ es real, SÍ está probada, y SÍ tiene esa
limitación exacta -- pero que nunca se llegó a conectar dentro de un
`extract_entity_node` real que la llamara desde una pregunta en
lenguaje natural. Cada mención posterior citaba una limitación real de
una pieza real, dando la impresión de que el nodo completo (la
orquestación LLM que decide qué sustancia pregunta el usuario) también
lo era. **No se ha encontrado ninguna afirmación de que el Nodo 1 se
probara contra la API real** -- buscado explícitamente en CLAUDE.md y
PROGRESS.md, no aparece esa afirmación en ningún sitio. La confusión
más probable es con el Nodo 4, que SÍ se probó contra la API real de
DeepSeek (caso aspartamo, sesión 2, 16-ago-2026) -- un hecho bien
documentado y fácil de confundir con el Nodo 1 porque los dos
"involucran al LLM" conceptualmente.

**Agravante encontrado en la sesión anterior (18-ago-2026, continuación
5), no antes de ahora: yo mismo repetí el error sin verificarlo.** Al
actualizar "Estado del código" de CLAUDE.md para reflejar el Nodo 2
recién implementado, escribí "Nodo 1 (extracción con LLM)... Nodo 4
(generación) implementados" extendiendo la lista ya existente sin
comprobar el Nodo 1 contra el código real -- hasta ahora, no había
motivo para dudar de una afirmación que llevaba sesiones repitiéndose.

**Corregido:**
- CLAUDE.md, "Estado del código": la frase que acreditaba el Nodo 1
  como implementado corregida para decir explícitamente que sigue
  siendo `raise NotImplementedError`, con la cita textual del código y
  la referencia a los 3 commits verificados.
- PROGRESS.md: la línea original de la sesión 1 (arriba, "Implementado")
  anotada con una corrección en línea (no reescrita -- no se borra el
  rastro del error) que apunta a esta entrada.

**Lección para próximas sesiones, no solo para este caso concreto:**
antes de afirmar el estado de un nodo/función en un resumen de cierre
de sesión, comprobar el código real (`grep`/`Read` directo), no asumir
que una afirmación repetida en sesiones anteriores sigue siendo cierta
solo porque nadie la cuestionó -- exactamente el fallo que produjo este
error y lo sostuvo.

**Pendiente / sin resolver al cierre de esta entrada:**
- **El Nodo 1 (`extract_entity_node`) sigue sin implementar de
  verdad** -- esto no cambió, solo se corrigió el registro. Sigue
  siendo el bloqueante real para probar el grafo completo con una
  pregunta en lenguaje natural.
- Todo lo demás sin cambios respecto a la entrada anterior.

## 2026-08-18 (continuación 7) — Nodo 1 (extract_entity_node): PRIMERA implementación real, no una continuación

**Contexto:** tras la corrección de la entrada anterior, se pidió
implementar el Nodo 1 de verdad -- `NODE_1_ENTITY_EXTRACTION_PROMPT`
(nombre que yo mismo había acuñado en la corrección anterior siguiendo
la convención `NODE_4_*` ya existente, NO porque estuviera ya
documentado en ningún sitio -- aclarado con el usuario antes de
diseñar el prompt, para no repetir el mismo tipo de error de dar algo
por hecho), llamada real al `llm_client`, resolución de
`substance_uuid` vía `OpenFoodToxStore.substance_uuid_by_name`, y un
test con una pregunta real de aspartamo en inglés contra la API real
-- explícitamente "no lo des por hecho sin probarlo esta vez".

**Implementado en `graph/nodes.py`:**
- `NODE_1_ENTITY_EXTRACTION_PROMPT`: pide al LLM el nombre químico
  canónico en inglés de la sustancia mencionada, en una sola línea sin
  explicación, o `NONE` si no hay ningún aditivo identificable. En
  inglés porque `substance_uuid_by_name` exige coincidencia EXACTA
  contra `SUB.ChemicalName` -- esa limitación (ya documentada, pendiente
  #2 de CLAUDE.md) NO se resuelve aquí, se hereda tal cual: si el LLM
  normaliza a un nombre razonable que no coincide carácter a carácter
  (ej. nombres compuestos como los de `SUB`), la resolución falla y
  `substance_uuid` queda en `None` a propósito, no es un bug.
- `extract_entity_node`: llama a `deps.llm_client.complete(...)` con
  `max_tokens=30` (un nombre, no una frase), limpia comillas/punto
  final de la respuesta, y resuelve el UUID con la función ya existente
  y ya probada -- sin re-implementar ni tocar esa función.

**Verificado con llamada REAL a la API de DeepSeek, no mockeado ni
asumido -- dos niveles de verificación:**
1. **Tests automatizados nuevos**
   (`tests/test_nodes.py::test_extract_entity_node_resolves_aspartame_from_real_english_query`
   y `test_extract_entity_node_unrelated_query_resolves_to_none`,
   se saltan sin `DEEPSEEK_API_KEY`) -- **23/23 tests pasan** (21
   previos + 2 nuevos), ~92 s de tiempo total. A diferencia del resto
   de tests del archivo (gratis una vez el recurso local existe),
   estos SÍ facturan una llamada real en cada ejecución -- documentado
   explícitamente en el docstring del archivo para que no se
   sorprenda quien los corra.
2. **Verificación manual adicional con 4 preguntas reales** (no solo
   las 2 del test automatizado), impresas y revisadas una a una antes
   de dar la implementación por terminada:
   - *"What is the ADI of aspartame and what study is it based on?"*
     -> `Aspartame`, UUID correcto.
   - *"Por qué se retiró el dióxido de titanio como aditivo?"*
     (español) -> `Titanium dioxide`, UUID correcto.
   - *"Is E 951 safe for children?"* (E-number) -> `Aspartame`, UUID
     correcto.
   - *"What time is it in Tokyo right now?"* (sin relación) ->
     `None`/`None` -- no inventa una sustancia.

   **Corrección explícita pedida por el usuario tras leer esta entrada:
   NO tratar esto como "limitación resuelta".** La función
   `substance_uuid_by_name` sigue exigiendo coincidencia EXACTA contra
   `SUB.ChemicalName` en inglés, sin ningún cambio. Lo único distinto
   es que el LLM normaliza español/E-numbers ANTES de llamarla, y
   acertó en estos 2 casos puntuales (1 en español, 1 con E-number) --
   una mitigación PARCIAL, verificada en un puñado de casos concretos,
   NO una batería de pruebas sistemática. No hay garantía de que
   acierte con nombres compuestos, E-numbers menos comunes o
   redacciones no probadas. CLAUDE.md corregido en el mismo sentido
   (pendiente #2 y el bullet de Nodo 1 en "Estado del código") -- ver
   ahí para el texto exacto que queda vigente.

**Esto es la PRIMERA implementación real de este nodo, no una
continuación de nada previo** -- ver la entrada de corrección anterior
(continuación 6): el nodo llevaba siendo `raise NotImplementedError`
desde el primer commit del repo, y ninguna sesión anterior lo había
tocado de verdad pese a que la documentación decía lo contrario.
CLAUDE.md actualizado en "Estado del código" para reflejar esto sin
ambigüedad.

**Pendiente / sin resolver al cierre de esta entrada:**
- No se ha probado el grafo completo de extremo a extremo (Nodo 1 -> 2
  -> 3 -> 4) en una sola ejecución con una pregunta real -- cada nodo
  sigue probado por separado. Con los 4 nodos ya implementados, este es
  el siguiente paso lógico natural.
- `graph/build.py` (ensamblado del grafo LangGraph, wiring de
  `NodeDependencies` con las instancias reales, y la lógica de
  orquestación de qué hacer cuando el Nodo 1 no resuelve
  `substance_uuid` -- ¿saltar Nodo 3 y responder solo con lo que el
  Nodo 2/4 puedan aportar, o pedir aclaración al usuario?) sigue sin
  existir.
- La limitación de coincidencia exacta de `substance_uuid_by_name`
  sigue sin resolverse a nivel estructural -- lo que cambió es que el
  LLM la esquiva en la práctica para nombres simples, no que la
  función en sí se haya vuelto más flexible. Un nombre compuesto o mal
  normalizado por el LLM seguiría fallando.
- Servidor MCP, deploy: sin cambios esta sesión.

## 2026-08-18 (continuación 8) — Auditoría general de CLAUDE.md/PROGRESS.md antes de graph/build.py

**Contexto:** tras la corrección del Nodo 1, el usuario pidió releer
CLAUDE.md y PROGRESS.md de cabo a rabo y verificar contra el código/
tests real CADA afirmación de "implementado", "probado", "funciona" o
similar -- no solo la ya encontrada del Nodo 1. Antes de escribir
`graph/build.py`, para no seguir construyendo sobre afirmaciones sin
verificar.

**Metodología:** lectura completa de ambos archivos (2.400 + 2.175
líneas), extracción de cada afirmación falsable, y verificación directa
contra el código real -- funciones sin `NotImplementedError`, suite de
tests completa corrida de cero, recuentos numéricos recalculados desde
el xlsx/jsonl/Chroma reales (no leídos de la documentación), existencia
de archivos/scripts, contenido real de PDFs.

**Verificado y CONFIRMADO sin discrepancia (lista completa):**
- Los 4 nodos del grafo tienen código real, ningún `NotImplementedError`
  salvo el método abstracto de `LLMClient` (esperado).
- Todos los métodos de `OpenFoodToxStore` tienen lógica real.
- Suite de tests completa: **23/23 pasan**, coincide con lo documentado.
- `current_reevaluation_corpus()` = 162, `unique_reevaluation_opinions()`
  = 162 -- coincide.
- Aspartamo: ADI 40.0 mg/kg pc/día, fecha 2013-11-28 -- coincide con el
  caso de referencia original.
- `data/processed/chunks.jsonl`: 67.827 líneas. Colección Chroma:
  67.827 entradas. Ambos exactos.
- 161 PDFs en disco, 161 filas en el checklist.
- PyPDFLoader vs PyMuPDFLoader en el PDF de fosfatos: **655.733 vs
  652.233 caracteres -- reproducido dígito a dígito.**
- `ui/app.py`: candado 24h + límite de consulta en dos capas, real y
  coincide con la descripción exacta (incluida la advertencia de que
  el límite por IP no es protección real).
- Los 5 scripts documentados existen; `probe_dossier_urls.py` y
  `probe_alternate_sources.py` tienen `--dry-run` + `MAX_ITEMS` tal
  como exige la regla de CLAUDE.md.
- `requirements.txt`/`.gitignore` coinciden con las decisiones
  documentadas.
- `mcp/` genuinamente vacía, `graph/build.py` genuinamente no existe,
  detección de ambigüedad del Nodo 3 genuinamente sigue siendo
  placeholder -- los 3 correctamente listados como pendientes, no
  sobre-reclamados.
- Licencia CC BY-ND post-2016 / sin licencia pre-2016: verificado en 2
  de 161 PDFs (2013 y 2024), ambos coinciden con el patrón documentado
  -- NO es una re-verificación completa de los 161, solo un spot-check.

**Dos discrepancias nuevas encontradas, corregidas con el mismo patrón
que el Nodo 1 (anotación en línea + explicación, sin borrar el
historial):**

1. **"146/161 (91%) PDFs con al menos una tabla" no se reproduce.**
   Re-escaneados los 161 PDFs con el mismo patrón (`Table N:`), en
   texto plano y en modo "blocks" (mismo resultado en los dos):
   **138/161 (86%)**. Probada una variante más laxa (sin exigir los
   dos puntos): 155/161 (96%) -- ninguna de las dos reproduce 146, que
   cae entre ambas sin que se haya podido identificar la variante de
   método que la produjo (el script original de esa sesión no quedó
   guardado). **Corregido en CLAUDE.md: la cifra original (146/161)
   queda anotada como NO VERIFICADA, no borrada -- la cifra vigente
   para cualquier razonamiento posterior es 138/161 (86%)**,
   re-confirmada en esta sesión. La conclusión que sostenía (las
   tablas son la norma, no el caso raro) sigue siendo válida con
   cualquiera de las tres cifras -- no cambia la decisión ya tomada
   (Opción A de tratamiento de tablas), solo el número citado.

2. **La prueba real del Nodo 4 contra la API es cierta pero está
   desactualizada -- no cubre el prompt tal como es hoy.** La llamada
   real de sesión 2 (16-ago-2026) se hizo contra una versión de
   `_format_structured_result` ANTERIOR a `discussion_text`/
   `discussion_is_boilerplate` (añadidos en sesión 3, mismo día) y
   anterior al texto de "motivos opuestos" para ADI sin valor (tier
   1/2, añadido en sesión 17-ago-2026 continuación 7) -- ambos
   confirmados presentes en el código actual, ninguno existía en el
   momento de esa prueba. `_format_retrieved_chunks` (aviso de tier 3)
   tampoco existía todavía. **Ninguna de las tres adiciones ha pasado
   nunca por una llamada real.** Más grave: como el Nodo 2 no existía
   hasta hoy, **todas las pruebas reales de este nodo se hicieron con
   `retrieved_chunks=[]`** -- el caso que de verdad importa (contexto
   narrativo real poblando el prompt) nunca se ha probado end-to-end
   contra la API real. Verificado además con `grep`: **no existe
   ningún test automatizado de `generate_answer_node`** -- a
   diferencia de los Nodos 1 y 2, esta verificación nunca se codificó
   como reproducible. **Corregido en CLAUDE.md** (bullet de Nodo 4 en
   "Estado del código" + nuevo pendiente #9): no tratar "Nodo 4
   probado contra la API real" como garantía vigente del comportamiento
   actual sin repetir la prueba con el prompt de hoy.

**Nada de lo encontrado en esta auditoría revierte trabajo ya hecho ni
invalida ninguna decisión de arquitectura tomada** -- son dos casos de
cifras/afirmaciones que necesitaban una nota de vigencia más precisa,
no errores que cambien una conclusión. Distinto del caso del Nodo 1
(que sí era una afirmación completamente falsa de un nodo que nunca
existió).

**Pendiente / sin resolver al cierre de esta entrada:**
- Nada nuevo generado por esta auditoría en sí -- las dos correcciones
  quedan como pendientes #9 (Nodo 4) y una nota en la Evidencia 1 del
  tratamiento de tablas (ya corregidas en CLAUDE.md, no acciones de
  código pendientes).
- Todo lo demás igual que la entrada anterior -- `graph/build.py`
  sigue siendo el siguiente paso.

## 2026-08-18 (continuación 9) — graph/build.py: grafo ensamblado y compilado, NO ejecutado todavía

**Contexto:** con los 4 nodos implementados, se pidió ensamblar
`graph/build.py` con `StateGraph` de LangGraph -- orden
extract_entity -> hybrid_retrieval -> verify_currency -> generate_answer,
decidiendo y documentando explícitamente qué pasa si el Nodo 1 no
resuelve `substance_uuid`, compilarlo y exponer `answer_question(query)`.
Explícitamente: sin llamar a la API todavía, solo mostrar
`get_graph().draw_mermaid()` para revisar la estructura antes de
ejecutar nada real.

**Decisión de diseño (la pedida explícitamente) -- qué pasa sin
`substance_uuid`:** el grafo sigue hasta el Nodo 4, no corta antes,
pero salta el Nodo 3 (que lanzaría `ValueError` sin `substance_uuid`,
sin tocar su código). Una única arista condicional después del Nodo 2
decide el camino. Razón: el Nodo 4 ya estaba diseñado en sesiones
anteriores para degradar con gracia con `structured_result=None` y
`retrieved_chunks=[]` -- seguir hasta ahí da una respuesta útil sin
código nuevo; cortar antes no ahorra nada (la única llamada cara, el
Nodo 1, ya se pagó) y deja al usuario sin respuesta.

**Implementado en `graph/build.py` (nuevo):**
- `build_graph(deps)`: los 4 nodos como closures que capturan `deps`
  (las funciones de nodo toman `(state, deps)`, `add_node` espera solo
  `state`) + la arista condicional descrita arriba.
- `build_default_deps()`: `NodeDependencies` real -- store del xlsx,
  colección Chroma persistente, `SentenceTransformer` (mismo modelo
  del indexado), y `build_default_client()` reutilizado de
  `graph/llm_client.py` (no duplicado).
- `answer_question(query: str) -> str`: punto de entrada pedido.
  `deps`/grafo cacheados a nivel de módulo (no pedido literalmente así,
  decisión propia para no recargar el modelo de embeddings ni reabrir
  Chroma en cada pregunta -- documentado en el código).
- Bloque `if __name__ == "__main__"`: compila con un
  `NodeDependencies` de relleno (todos los campos `None`) y dibuja el
  Mermaid -- seguro porque `deps` no se toca durante `compile()`/
  `get_graph()`, solo dentro de las funciones de nodo cuando el grafo
  se invoca de verdad.

**Verificado, sin tocar la API en ningún momento:**
- `python -m efsa_rag.graph.build` compila y dibuja el grafo. Salida
  Mermaid real:
  ```
  __start__ --> extract_entity;
  extract_entity --> hybrid_retrieval;
  hybrid_retrieval -.-> generate_answer;
  hybrid_retrieval -.-> verify_currency;
  verify_currency --> generate_answer;
  generate_answer --> __end__;
  ```
  Coincide exactamente con el diseño -- las dos aristas punteadas desde
  `hybrid_retrieval` son la arista condicional (camino normal vía
  `verify_currency`, camino corto directo a `generate_answer`).
- Suite de tests completa: **23/23 siguen pasando** con el módulo
  nuevo importado (~99 s).

**CLAUDE.md actualizado** con el diseño completo y la distinción
explícita entre "compilado y verificado estructuralmente" (esta
sesión) y "ejecutado con datos reales" (todavía no, a propósito).

**Pendiente / sin resolver al cierre de esta entrada:**
- **El grafo nunca se ha invocado de verdad** -- ni `answer_question(...)`
  ni `graph.invoke(...)` se han llamado con una pregunta real en esta
  sesión, tal como se pidió explícitamente. Es el siguiente paso lógico
  natural: una pregunta real de extremo a extremo (Nodo 1 -> 2 -> 3 ->
  4 en una sola ejecución), algo que hasta ahora solo se había probado
  nodo por nodo por separado.
- Todo lo demás sin cambios respecto a la entrada anterior (pendiente
  #9 de CLAUDE.md sobre re-probar el Nodo 4 con el prompt actual sigue
  abierto, independiente de este ensamblado).

## 2026-08-18 (continuación 10) — vigencia_ambigua marcado como reservado; diagnóstico de prevalencia de ambigüedad en el Nodo 3, diferido con evidencia

**Contexto:** antes de la primera ejecución real del grafo, se
preguntó qué pasa hoy si `verify_currency_node` encuentra un caso
ambiguo (varias `'EFSA opinion'` con fechas próximas). Respuesta dada
en el turno anterior: ni excepción ni manejo real, `MAX(fecha)` en
silencio, `vigencia_ambigua` no cubre ese caso pese al nombre y nadie
la lee. En paralelo se pidió arreglar esa señal engañosa, y por
separado, escanear el corpus real (primero tier 1, luego tier 2/3)
para decidir con datos si implementar la detección ahora o diferirla.

**Arreglado, sin cambiar comportamiento:** `GraphState.vigencia_ambigua`
y `verify_currency_node` -- comentarios y docstring reescritos para
decir explícitamente "RESERVADO, SIN EFECTO TODAVÍA", con las dos
razones (nadie lo lee; ni siquiera mide ambigüedad real, solo "cero
candidatos"). No se borró el campo -- sigue siendo el punto de
extensión reservado para cuando se implemente la detección real.
Verificado que el módulo sigue importando sin errores (solo
comentarios/docstrings, cero lógica tocada).

**Diagnóstico de prevalencia -- metodología:** replicado el filtrado
EXACTO de candidatos de `current_reference_value_opinion` (mismos
pasos: `VALID_OPINION_TYPES`, rescate de dominio, exclusión de pienso
animal) sin el pick final de `MAX(fecha)`, midiendo la distancia en
días entre el candidato ganador y el más cercano de los demás, para
cada sustancia con 2+ candidatos supervivientes. Verificado contra el
caso conocido de aspartamo antes de confiar en el método: reproduce
exactos los 4 candidatos esperados (2006, 2009×2, 2013, excluyendo el
statement de 2011). Umbral: 90 días (y 30 días para comparar) --
razonado en CLAUDE.md, pendiente #6.

**Tier 1 (94 sustancias con ADI resuelto, turno anterior):** 0
ambiguas a 90 ni a 30 días. Gap real más pequeño: 106 días
(Propane-1,2-diol).

**Tier 2/3 (153 sustancias adicionales, sin ADI numérico -- `require_adi=False`
menos las 94 de tier 1, más Shellac vía tier 3), esta sesión:** 125 con
un único candidato/fecha, 3 sin ningún candidato (caso ya manejado,
`current_reference_value_opinion` devuelve `None` y Node 4 ya lo
comunica -- no es ambigüedad), 25 con 2+ candidatos. **0 de esas 25
caen dentro de 90 días (ni de 30).** Gap más pequeño: 160 días
(Beetroot Red/betanin).

**Total combinado: 0/247 sustancias ambiguas, a 90 o a 30 días, en
todo el corpus con enlace estructural resoluble.** El gap real más
pequeño de todo el corpus es 106 días -- sin ningún caso cerca del
umbral que hiciera dudar de 90 días frente a 60 o 120.

**Documentado en CLAUDE.md como pendiente #6, DIFERIDO explícitamente
(no implementado, con la evidencia completa, el caveat de que es una
foto del corpus actual, y el razonamiento de por qué se difiere):**
impacto verificado = cero incidentes reales hasta hoy, frente a
trabajo con impacto YA conocido y pendiente (Nodo 4 sin re-probar con
el prompt actual -- pendiente #9; servidor MCP; deploy). El programa de
reevaluación sigue activo -- un futuro follow-up cercano en el tiempo a
un dictamen existente SÍ podría producir el caso ambiguo que hoy no
existe; este diagnóstico no lo descarta para siempre, solo confirma
que no ha pasado todavía. Si el corpus cambia, re-ejecutar el mismo
diagnóstico (no quedó guardado como script permanente -- investigación
puntual, replicable con el método descrito) antes de asumir que sigue
siendo seguro diferirlo.

**Pendiente / sin resolver al cierre de esta entrada:**
- Detección de ambigüedad real en el Nodo 3: sigue sin implementar, a
  propósito (diferido con evidencia, no por omisión).
- El grafo sigue sin invocarse con una pregunta real -- sigue siendo
  el siguiente paso lógico natural, ahora con este hueco conocido y
  aceptado explícitamente en vez de desconocido.
- Todo lo demás sin cambios respecto a la entrada anterior.

## 2026-08-18 (continuación 11) — Primera invocación real del grafo completo, auditoría de fundamentación (Soffritti), AnswerResult

**Contexto:** primera ejecución real de `answer_question(...)` de
extremo a extremo (Nodo 1 -> 2 -> 3 -> 4 en una sola llamada, con
Chroma real de por medio, no vacío) -- hasta ahora cada nodo solo se
había probado por separado. Pregunta: *"What is the ADI of aspartame
and what study is it based on?"*.

**Respuesta completa obtenida (pegada tal cual, sin resumir):**

> **Dictamen de referencia:**
> *Scientific Opinion on the re-evaluation of aspartame (E 951) as a food additive* – EFSA, 28 November 2013. DOI: 10.2903/j.efsa.2013.3496.
>
> **ADI de aspartame:** 40 mg/kg de peso corporal al día.
>
> **Estudio en el que se basa:** el contexto estructurado no especifica
> el estudio pivotal concreto. Los fragmentos narrativos mencionan
> estudios relevantes (estudios a corto plazo en adultos y adultos
> obesos, y el estudio de Soffritti et al. 2006), pero no identifican
> explícitamente cuál es el estudio pivotal del NOAEL.
>
> Cita textual de `JustificationAndComments`, aclaración del margen de
> seguridad (×100 sobre NOAEL, sin la frase prohibida de "si se supera
> el ADI"), y nota explícita de que los fragmentos no permiten
> identificar el estudio pivotal concreto.

**Verificación de fundamentación pedida antes de dar la respuesta por
buena:** ¿"Soffritti et al. 2006" aparece literalmente en algún
`retrieved_chunk`, o es conocimiento propio del modelo sin decirlo?
Reconstruida la llamada a `hybrid_retrieval_node` con el mismo
`substance_uuid`/query (en ese momento `answer_question` solo devolvía
el string, no había forma de inspeccionar los chunks directamente) --
**confirmado, aparece literalmente en el chunk 1** (página 32, sección
"2.7.1. Existing authorisations and evaluations of aspartame"):

```
of this study and the use of animals with a high infection rate, the COC considered that no valid
conclusions could be drawn from this study. Therefore, the COC agreed that the Soffritti et al. (2006)
study did not indicate a need for a review of the ADI for aspartame (COC, 2006).
```

También verificado el otro detalle citado ("adultos obesos") --
trazable al chunk 4 (página 92, "3.2.7.3. Repeat dose studies in
humans"). **Ambas menciones concretas de la respuesta están
fundamentadas en el contexto recuperado, no en conocimiento de
entrenamiento sin marcar** -- no hizo falta reforzar
`NODE_4_GROUNDING_RULES` con esta evidencia.

**Implementado tras esto -- `answer_question` cambia de contrato
(`-> str` a `-> AnswerResult`)**, para que auditar fundamentación no
requiera reconstruir el retrieval a mano la próxima vez:
- `AnswerResult` (dataclass, nuevo en `graph/build.py`): `answer: str`,
  `retrieved_chunks: list[RetrievedChunk]`,
  `structured_result: OpinionReference | None` -- los mismos objetos
  que vio el Nodo 4, leídos del estado final tras `.invoke(...)`, no
  una reconstrucción aparte. `answer` sigue siendo el texto final, esto
  lo acompaña, no lo sustituye.
- **Verificado con `grep` antes del cambio: no había ningún caller real
  que rompiera** (`ui/app.py`, tests, scripts -- ninguno usaba
  `answer_question` todavía, solo invocaciones manuales sueltas de
  sesiones de verificación).
- Re-verificado con una llamada real tras el cambio: `result.answer`,
  `result.structured_result` (ADI=40.0, fecha 2013-11-28,
  `discussion_is_boilerplate=True`) y `result.retrieved_chunks` (5
  chunks, mismo contenido y mismo orden que la reconstrucción manual
  anterior -- confirma que el retrieval es determinista para esta
  consulta) -- todo correcto.
- Suite de tests completa: **23/23 siguen pasando** (~94 s).

**CLAUDE.md actualizado:** contrato de `answer_question` corregido en
"Estado del código"; pendiente #9 (re-probar el Nodo 4 con el prompt
actual) marcado **PARCIALMENTE HECHO** -- esta consulta ejercitó
`retrieved_chunks` no vacío y `discussion_text`, pero NO el mensaje de
"motivos opuestos" para ADI tier 2 (aspartamo tiene ADI, no ejercita
esa rama) ni el aviso de tier 3 en `retrieved_chunks` (los 5 chunks de
aspartamo son tier 1) -- sigue sin existir un test automatizado de
`generate_answer_node`/`answer_question`.

**Pendiente / sin resolver al cierre de esta entrada:**
- Pendiente #9 solo parcialmente cerrado -- falta probar con una
  sustancia tier 2 (ej. TiO2) y una tier 3 (Shellac/sucralosa) para
  ejercitar las ramas de mensaje que aspartamo no toca.
- Sigue sin existir ningún test automatizado de `generate_answer_node`/
  `answer_question` -- toda la verificación de este nodo, en las 2
  sesiones donde se ha hecho, ha sido manual.
- Detección de ambigüedad en el Nodo 3: sigue diferida (sin cambios).
- Servidor MCP, deploy: sin cambios esta sesión.

## 2026-08-18 (continuación 12) — Bug real de truncamiento silencioso en el Nodo 4, arreglado; diagnóstico de fraseo de query en el Nodo 2

**Contexto:** dos consultas reales más pedidas para ejercitar tier 2
(TiO2) y tier 3 (Shellac) del Nodo 4. La respuesta de Shellac llegó
pegada tal cual, sin resumir -- y se notó a simple vista que terminaba
a mitad de frase, sin punto final. Antes de dar la validación del Nodo
4 por cerrada, se pidió confirmar la causa exacta (`finish_reason`) y,
si era truncamiento real, arreglarlo con dos cambios (subir
`max_tokens`, y sobre todo un chequeo explícito que nunca deje pasar
una respuesta cortada sin avisar). En paralelo, sin bloquear el fix:
diagnosticar por qué el retrieval de TiO2 no trajo contenido de
genotoxicidad pese a ser la conclusión central del dictamen de 2021.

**Dos consultas reales ejecutadas primero (TiO2, Shellac) -- resultado
completo pegado sin resumir en el turno correspondiente.** Confirmaron
los tiers esperados: TiO2 -> 5 chunks, todos tier 2 (`adi_value=None`,
`discussion_is_boilerplate=False`, discusión real presente); Shellac ->
5 chunks, todos tier 3, con el aviso de fiabilidad de tier 3
correctamente activado en el texto de respuesta ("identificados por
coincidencia de nombre... fiabilidad menor"). La respuesta de Shellac
cortada a mitad de frase, sin ningún aviso, fue lo que disparó el resto
de esta sesión.

**Confirmación de causa, ANTES de tocar nada (pedido explícitamente en
ese orden):** `LLMResponse` no exponía `finish_reason` -- campo nuevo
añadido a `graph/llm_client.py` (poblado desde
`response.choices[0].finish_reason` en `DeepSeekClient`, desde
`data.get("done_reason")` en `OllamaClient`, `None` si el backend no lo
expone). Reconstruido el mismo prompt de Shellac exacto y llamado a la
API con el `max_tokens=800` de entonces (sin cambiar nada más
todavía): **`finish_reason == 'length'`, `output_tokens == 800`
(el tope exacto) -- truncamiento real por límite de longitud, no otra
causa** (no filtro de contenido, no secuencia de parada).

**Fix implementado, dos partes, en `graph/nodes.py`:**
1. `NODE_4_MAX_TOKENS` subido de 800 a 2000 -- con "thinking" ya
   desactivado (decisión de sesiones anteriores, sin tocar), esto es
   presupuesto de texto de salida real, coste directo, no oculto.
2. `generate_answer_node` comprueba `response.finish_reason == "length"`
   explícitamente: si trunca con el tope normal, reintenta UNA vez con
   `NODE_4_RETRY_MAX_TOKENS = 3500`; si sigue truncada incluso así,
   añade `"\n\n[respuesta incompleta por límite de longitud]"` al
   final. Nunca se devuelve una respuesta cortada sin avisar.

**Verificado tras el fix, misma consulta de Shellac exacta:** con
`max_tokens=2000` la respuesta terminó sola (`finish_reason == 'stop'`)
en **845 tokens de salida** -- ni siquiera hizo falta el reintento --
y ahora cierra con un párrafo de "Conclusión" completo. Pegada la
respuesta completa en el turno correspondiente, sin resumir. Suite de
tests completa: **23/23 siguen pasando** (~96 s).

**Coste/consulta -- NO recalculado con precisión, honestidad explícita
sobre por qué:** la cifra vigente ($0,0005-0,0014/consulta) sigue
basada en ~365 tokens de salida (de la sesión del fix de "thinking",
16-ago-2026) -- el dato real medido ahora (845 tokens de salida para
una respuesta completa con desglose largo) es más del doble. No se
recalculó un $ preciso porque no hay una tarifa $/token de DeepSeek
verificada en esta sesión -- esa cifra la había aportado el usuario
contra una fuente de pricing externa en una sesión anterior, no algo
que este proyecto tenga memorizado. Documentado en CLAUDE.md como
pendiente explícito: recalcular con la tarifa real antes de dar el
presupuesto de 6-7€/mes por bueno con el tope de 2000 (y el peor caso
de 3500 si el reintento llega a dispararse).

**Diagnóstico de retrieval de TiO2 (solo investigación, nada
implementado, tal como se pidió):** comparadas dos consultas contra el
mismo `substance_uuid` de TiO2 -- "Why was titanium dioxide withdrawn
as a food additive?" (la original, sin contenido de genotoxicidad) vs.
"titanium dioxide genotoxicity concern conclusion" (reformulación
directa). **La reformulación trae como resultado #1 exactamente la
sección "4.3. Genotoxicity" (página 45)** -- confirma que el contenido
SÍ está bien chunked e indexado, es un problema de fraseo de la
pregunta original, no del índice: "withdrawn" no es un marco que el
propio dictamen use (es una reevaluación, no un anuncio de retirada),
así que la similitud de embeddings favoreció contenido superficial
(Introduction/Background/Summary) sobre la sección sustantiva.
**Hallazgo secundario no buscado:** incluso con la reformulación
mejor, 3 de los 5 resultados fueron fragmentos de "References"
(bibliografía que menciona "genotoxicity" en el título citado, no
razonamiento real) -- mismo tipo de ruido de baja calidad que ya
motivó excluir tablas del índice narrativo. Ninguno de los dos
hallazgos se implementó -- quedan como candidatos a mejora futura del
Nodo 2/chunker (reformulación de query, exclusión de "References"),
documentados en CLAUDE.md.

**Pendiente / sin resolver al cierre de esta entrada:**
- Coste/consulta con el nuevo `max_tokens=2000` sin recalcular con
  precisión -- falta la tarifa $/token real.
- Posible mejora de retrieval (reformulación de query en Nodo 1/2,
  exclusión de "References" del chunking) diagnosticada pero no
  implementada -- decisión de priorización pendiente.
- Sigue sin existir test automatizado de `generate_answer_node` --
  ahora sería el momento de codificar el caso de truncamiento como
  test de regresión (mock de `LLMClient` que devuelva
  `finish_reason="length"` la primera vez, para no depender de una
  llamada real que trunque por casualidad).
- Detección de ambigüedad en el Nodo 3: sigue diferida (sin cambios).
- Servidor MCP, deploy: sin cambios esta sesión.

## 2026-08-18 (continuación 13) — CLAUDE.md excedía el límite de 150k de Claude Code; reestructurado con docs/DECISIONES_VERIFICADAS.md

**Contexto:** `CLAUDE.md` llegó a 179.223 caracteres, por encima del
límite de 150k que Claude Code exige para cargarlo sin problema en cada
sesión. Se pidió reestructurar: mover el contenido evidencial extenso de
la sección "Hallazgos verificados" (tablas de datos, párrafos de
justificación completos, bloques `[CORRECCIÓN...]`) a un archivo nuevo,
conservando cada hallazgo íntegro -- nada resumido ni perdido, solo
movido -- y dejar en `CLAUDE.md` las restricciones no negociables tal
cual, un resumen de 1-2 frases por hallazgo con puntero al detalle, y
"Estado del código" sin tocar.

**Implementado:**
- `docs/DECISIONES_VERIFICADAS.md` (nuevo, 118.075 caracteres): el
  texto íntegro de "Hallazgos verificados" (23 hallazgos de nivel
  superior), con una cabecera explicando su relación con `CLAUDE.md` y
  cuándo consultarlo. **Verificado con `diff` que el contenido movido es
  byte a byte idéntico al original** -- no se resumió ni se reescribió
  nada al trasladarlo, solo se cortó del archivo original y se pegó con
  una cabecera nueva delante.
- `CLAUDE.md` reducido a 70.453 caracteres (de 179.223): restricciones
  no negociables intactas, "Hallazgos verificados" reemplazado por un
  resumen de 1-2 frases por cada uno de los 23 hallazgos (mismo orden
  que en el archivo nuevo, con puntero explícito a
  `docs/DECISIONES_VERIFICADAS.md`), "Decisiones de arquitectura ya
  tomadas" y "Estado del código" sin cambios.

**Objetivo de 30-40k NO alcanzado, señalado explícitamente al usuario en
vez de forzarlo en silencio:** 70.453 caracteres sigue por encima del
rango 30-40k pedido originalmente, porque "Estado del código" (43.253
caracteres) y "Decisiones de arquitectura" (14.620 caracteres) no
formaban parte del encargo (solo "Hallazgos verificados") y por sí
solas ya superan ese rango. Preguntado explícitamente si aplicar el
mismo tratamiento a esas dos secciones -- **el usuario eligió dejarlo en
70.453**, sin tocarlas más.

**Verificado al cierre de esta entrada (turno posterior, a petición
directa del usuario):** `CLAUDE.md` (70.453 caracteres) está muy por
debajo del límite real de 150k de Claude Code -- confirmado con `wc -c`
tras la reestructuración, no solo asumido por la aritmética de la resta.

**Pendiente / sin resolver al cierre de esta entrada:**
- Si `CLAUDE.md` vuelve a crecer con nuevas sesiones (como ya pasó una
  vez), la misma técnica (mover detalle evidencial a
  `docs/DECISIONES_VERIFICADAS.md`, dejar resumen + puntero) es el
  patrón a repetir -- no reinventar el enfoque.
- "Estado del código" y "Decisiones de arquitectura" siguen sin el
  mismo tratamiento -- decisión explícita de dejarlos así, no un
  descuido.

## 2026-08-18 (continuación 14) — Test de regresión para el truncamiento del Nodo 4

**Contexto:** pendiente señalado en la entrada de continuación 12 --
`generate_answer_node` seguía sin ningún test automatizado, toda su
verificación había sido manual (llamadas reales sueltas). Se pidió
cerrar ese hueco con un mock de `LLMClient`, sin gastar tokens reales.

**Implementado en `tests/test_nodes.py`:**
- `_StubLLMClient` (implementa `LLMClient.complete()`): devuelve una
  secuencia FIJA de `LLMResponse` pasada en el constructor, registra
  `max_tokens` de cada llamada, y lanza `AssertionError` si se le llama
  más veces de las que tiene respuestas preparadas -- esto último para
  que un test pueda afirmar "como mucho 2 llamadas" (nunca en bucle)
  simplemente dejándole solo 2 respuestas, sin un contador aparte.
- Tres tests nuevos, sección "Nodo 4 -- generate_answer_node":
  1. `test_generate_answer_node_retries_once_on_truncation_and_succeeds`
     -- primera respuesta `finish_reason='length'`, segunda `'stop'`.
     Verifica: la respuesta final es la del reintento (completa, sin la
     nota de truncamiento), 2 llamadas, la primera con
     `NODE_4_MAX_TOKENS` y la segunda con `NODE_4_RETRY_MAX_TOKENS`.
  2. `test_generate_answer_node_appends_notice_if_retry_also_truncates`
     -- ambas respuestas `'length'` (mismo síntoma que el caso real de
     Shellac que motivó el fix). Verifica: la nota
     `"[respuesta incompleta por límite de longitud]"` se añade al
     final, exactamente 2 llamadas (el stub lanzaría en una tercera,
     confirmando que el reintento es UNA vez, no un bucle).
  3. `test_generate_answer_node_no_retry_when_first_response_is_not_truncated`
     -- camino normal (`'stop'` a la primera). Verifica 1 sola llamada,
     sin nota añadida -- confirma que el fix no añade un reintento
     innecesario al caso común.
- `store=None` en `NodeDependencies` para los tres tests -- verificado
  leyendo `generate_answer_node` que no toca `deps.store` en ningún
  punto, así que no hace falta el xlsx real ni el fixture `store` (a
  diferencia de los tests de `_format_structured_result`/Nodo 2/Nodo 1
  ya existentes en este archivo, que sí lo requieren).

**Verificado:** los 3 tests nuevos pasan
(`pytest tests/test_nodes.py -v`, 9 passed + 2 skipped -- los 2
skipped son los de Nodo 1 que ya se saltaban antes por falta de
`DEEPSEEK_API_KEY`, sin relación con este cambio). Suite completa:
**24 passed, 2 skipped** (~91 s) -- ninguna regresión en los tests
existentes.

**Pendiente / sin resolver al cierre de esta entrada:**
- Recálculo de coste/consulta con `max_tokens=2000`/845 tokens de
  salida reales: NO se pudo completar -- ver la entrada siguiente,
  bloqueado por falta de la tarifa $/token real, que no está
  documentada en ningún sitio del repo pese a la instrucción de
  usarla "tal como está documentada en CLAUDE.md".
- Detección de ambigüedad en el Nodo 3, servidor MCP, deploy, mejora de
  retrieval del Nodo 2: sin cambios esta sesión.

## 2026-08-18 (continuación 15) — Recálculo real de coste/consulta, con la tarifa oficial de DeepSeek verificada

**Contexto:** la entrada anterior quedó bloqueada -- se pidió recalcular
el coste/consulta con `max_tokens=2000`/845 tokens de salida reales
"usando la tarifa de DeepSeek ya documentada en CLAUDE.md (16-ago,
punta/valle)", pero al buscarla, **CLAUDE.md solo documenta el
RESULTADO anterior ($0,0005-0,0014/consulta), nunca la tarifa $/token
subyacente** -- verificado con `grep` sobre `CLAUDE.md`,
`docs/DECISIONES_VERIFICADAS.md` y `PROGRESS.md`, cero coincidencias de
ninguna cifra de precio por millón de tokens. La cifra vigente hasta
ahora la había aportado el usuario contra una fuente externa en una
sesión anterior sin dejar la tarifa en sí registrada en el repo.

**Decisión: no fabricar una tarifa de memoria** -- inventar un número
de precio plausible violaría la misma disciplina que ya rige el resto
del proyecto ("verifica contra datos reales, no asumas el esquema", ver
CLAUDE.md "Cómo trabajar en este repo"). En vez de bloquear la tarea o
pedirle al usuario que repita un dato que ya dio una vez, se verificó la
tarifa oficial ACTUAL directamente:
- `WebFetch` contra `https://api-docs.deepseek.com/quick_start/pricing`
  (la documentación oficial de precios de DeepSeek, no un agregador de
  terceros) -- confirma modelo `deepseek-v4-flash` (el que usa este
  proyecto, `DeepSeekClient`): input cache-hit $0,007 (valle) / $0,014
  (punta) por millón de tokens; input cache-miss $0,22 / $0,44; output
  $0,66 / $1,32. "Punta" = 01:00-04:00 y 06:00-10:00 UTC, "valle" el
  resto, tarifa valle = mitad de la de punta -- confirmado en la propia
  página, coincide con la mecánica "punta/valle" ya mencionada en
  CLAUDE.md (aunque sin la cifra concreta hasta ahora). Contrastado
  además con un `WebSearch` previo (varios agregadores de terceros
  coinciden con la misma tabla) antes de confiar en un solo fetch.

**Cálculo, con datos ya medidos en sesiones anteriores (sin cambios en
esos números, solo se combinan con la tarifa nueva):**
- Input: ~1.250-2.000 tokens (system prompt 575 tokens medido +
  `retrieved_chunks`, k=3-5 chunks × ~150-180 tokens/chunk -- mismo
  presupuesto de contexto medido en la sesión de "Presupuesto de
  contexto del Nodo 4", sin cambios).
- Output: **845 tokens (medido de verdad, caso real Shellac,
  `finish_reason == 'stop'`)** -- no una estimación, el mismo dato ya
  registrado en la entrada de continuación 12.
- Input tratado como cache-miss (cota conservadora -- el system prompt
  SÍ podría beneficiarse del caché automático de DeepSeek en producción
  al repetirse entre consultas, pero el efecto sobre el total es
  pequeño: el output domina el coste porque su tarifa es ~3x la de
  input cache-miss).
- **Resultado: ~$0,0008/consulta en valle, ~$0,0020/consulta en
  punta** -- rango ~1,4-1,6x mayor que la cifra anterior
  ($0,0005-0,0014), consistente con que el output real más que se
  dobló (365→845) mientras el input no cambió.

**Hallazgo no buscado, verificado antes de darlo por bueno:** el valor
hardcoded `ESTIMATED_COST_PER_QUERY_USD = 0.002` en `ui/app.py` (el que
usa el candado de presupuesto real, `DAILY_HARD_COST_CEILING_USD =
0.35`) **sigue siendo válido** -- cae justo en el extremo superior
(punta) del rango recalculado, así que el candado sigue protegiendo con
el margen esperado en el caso normal, sin necesidad de tocar código.
**Caveat real señalado, no corregido (fuera de alcance de esta
sesión):** ese hardcoded es un valor fijo por consulta y no distingue
una consulta normal de una que dispara el reintento por truncamiento
(`NODE_4_RETRY_MAX_TOKENS = 3500`) -- el caso peor de reintento paga DOS
llamadas completas (hasta ~5.500 tokens de salida entre ambas),
~$0,004-0,009/consulta, 2-4,5x el hardcoded. No detectado como problema
real hoy (el reintento solo se paga en el caso raro), solo documentado
para no asumir que el candado cubre ese caso con el mismo margen que el
normal.

**Actualizado:**
- `CLAUDE.md`, "Decisiones de arquitectura ya tomadas" -- bloque
  "Precio LLM de referencia" reescrito con la tarifa citada, el cálculo,
  el hallazgo del hardcoded de `ui/app.py`, y el caveat del caso de
  reintento. Ya no queda marcado como "NO CERRADA".
- `docs/efsa-rag-proyecto.html` -- las cifras de ~$0,0006/consulta y
  ~500 tokens de salida (estimaciones previas a tener datos reales)
  corregidas a las cifras medidas/recalculadas (~$0,0008-0,0020,
  845 tokens de salida, ~5.000-13.000 consultas/mes con el mismo
  presupuesto de 6-7€/mes).

**Pendiente / sin resolver al cierre de esta entrada:**
- El caveat del caso de reintento (hardcoded no distingue coste
  normal de coste de reintento) queda solo documentado, no resuelto --
  no parece necesario mientras las respuestas truncadas sigan siendo
  raras, pero si `finish_reason == 'length'` empieza a verse con
  frecuencia real (no solo en el caso de prueba de Shellac), revisar si
  `ESTIMATED_COST_PER_QUERY_USD` necesita reflejar ese caso.
- Detección de ambigüedad en el Nodo 3, servidor MCP, deploy, mejora de
  retrieval del Nodo 2: sin cambios esta sesión.

## 2026-08-18 (continuación 16) — Servidor MCP implementado: search_efsa_opinion + get_reevaluation_status

**Contexto:** siguiente pendiente en orden (#7 de CLAUDE.md). Se pidió
implementar las dos herramientas del diseño original
(`docs/efsa-rag-proyecto.html`, paso 6 del roadmap) como wrappers finos
sobre `answer_question()`/el grafo compilado, sin reimplementar lógica,
y **mostrar el esquema de las dos herramientas para revisión antes de
escribir el servidor** -- no se escribió una línea de código del
servidor hasta tener el visto bueno.

**Esquema propuesto y revisado con el usuario antes de implementar:**
ambas con un único parámetro `substance: str` (nombre en lenguaje
natural, inglés o español, o E-number). `search_efsa_opinion` ->
respuesta narrativa fundamentada (wrapper de `answer_question`).
`get_reevaluation_status` -> estado estructurado (ADI/TDI, fecha, DOI,
sin prosa).

**Trade-off señalado ANTES de implementar, no descubierto después:**
tal como se diseñó al principio, ambas herramientas invocarían
`answer_question()` sin más -- lo que significa que
`get_reevaluation_status` pagaría la llamada cara al Nodo 4 (generación
LLM) aunque solo necesite los campos ya calculados por el Nodo 3, sin
LLM. Se preguntó explícitamente al usuario cómo resolverlo.

**Decisión del usuario: implementar un camino parcial del grafo (Nodo
1 + Nodo 3, sin Nodo 2 ni Nodo 4), condicionado a confirmar primero que
saltarse el Nodo 4 no compromete la restricción no negociable #1**
(comunicación de riesgo del ADI). Confirmación dada ANTES de escribir
el código, citando la fuente exacta:
`adi_justification = adi_row[ADI_JUSTIFICATION_COLUMN]`
(`ingestion/openfoodtox.py:745`) -- asignación directa desde la celda
del xlsx, sin ningún paso de LLM. La restricción #1 prohíbe que el LLM
**redacte** una frase que enmarque el ADI como umbral -- vive en el
system prompt del Nodo 4 porque solo ahí se compone prosa nueva. El
camino parcial nunca invoca un LLM para el ADI: números crudos +
cita textual de EFSA, el mismo campo que el Nodo 4 ya cita hoy dentro
de sus respuestas generadas.

**Implementado:**
- `graph/build.py`: `ReevaluationStatus` (dataclass) +
  `resolve_current_opinion(query) -> ReevaluationStatus` -- llama a
  `extract_entity_node`/`verify_currency_node` directamente (NO al
  grafo compilado, que siempre enruta al Nodo 4), reutilizando el mismo
  `_default_deps` cacheado que `answer_question`. Mismo guardia de
  `substance_uuid` ya usado en `_route_after_retrieval`, no una regla
  nueva.
- `AnswerResult` gana el campo `substance_name` (ya lo calculaba el
  Nodo 1, solo no se exponía) -- necesario para que
  `search_efsa_opinion` sepa qué sustancia se identificó sin releer
  `structured_result.title` (puede ser `None` aunque la sustancia SÍ se
  identificara -- señales distintas). Verificado con `grep` que
  `AnswerResult` solo se construye en un sitio (`answer_question`), sin
  otros callers que pudiera romper.
- `mcp/server.py` (nuevo): `MCPServer` (librería `mcp` -- versión real
  instalada 2.0.0, API `mcp.server.mcpserver.MCPServer`, DISTINTA de
  `mcp.server.fastmcp.FastMCP` de la 1.x que el pin `mcp>=1.0` de
  `requirements.txt` permitía instalar por error -- corregido a
  `mcp>=2.0`). Dos herramientas registradas con `@server.tool()`,
  parámetro `substance` vía `Annotated[str, Field(description=...)]`
  (verificado que genera el `inputSchema` JSON exacto ya revisado con
  el usuario). `get_reevaluation_status` añade `safety_note` -- una
  constante fija, NO generada por LLM, recordando que el ADI es margen
  de seguridad y no umbral -- defensa en profundidad para un cliente
  MCP externo que reciba estos números sin el contexto que el Nodo 4 sí
  da en sus respuestas narrativas.
- Ambas herramientas tipadas como `dict[str, Any]` (no `dict` a secas)
  -- **verificado explícitamente que esto es necesario** para que el
  SDK genere `outputSchema`/`structured_content`, probado con un caso
  mínimo antes de aplicarlo a las dos herramientas reales.

**Verificado (sin gastar tokens reales, con stubs de
`answer_question`/`resolve_current_opinion`):**
- `server.list_tools()` -- `inputSchema`/`outputSchema` de las dos
  herramientas coinciden exactamente con lo revisado con el usuario.
- `server.call_tool('get_reevaluation_status', ...)` con un
  `ReevaluationStatus` de aspartamo simulado -- `structured_content`
  correcto, todos los campos poblados.
- `server.call_tool('get_reevaluation_status', ...)` con sustancia NO
  identificada (`ReevaluationStatus` con todo en `None`) -- confirma
  que degrada con gracia: `substance_identified: null`,
  `dossier_found: false`, resto de campos `null`, `safety_note`
  presente igualmente -- nunca inventa un valor.
- `server.call_tool('search_efsa_opinion', ...)` con un `AnswerResult`
  simulado -- `structured_content` correcto (`substance_identified`,
  `answer`, `dossier_title`, `doi`, `retrieved_chunks_count`).
- Suite de tests completa tras los cambios en `graph/build.py`: **24
  passed, 2 skipped**, sin regresiones.

**Actualizado:** `CLAUDE.md` -- nueva entrada en "Decisiones de
arquitectura ya tomadas" ("Dos caminos de ejecución del grafo") con el
razonamiento completo de seguridad; `mcp/server.py` añadido a
"Implementado"; pendiente #7 marcado HECHO; `requirements.txt`
corregido (`mcp>=1.0` -> `mcp>=2.0`).

**Pendiente / sin resolver al cierre de esta entrada:**
- **Sin test automatizado en `tests/`** -- toda la verificación de esta
  sesión fue manual (con stubs, en la consola), mismo punto de partida
  que tuvo el Nodo 4 antes de que se le añadiera
  `test_generate_answer_node_*`. Candidato natural para una sesión
  futura si el servidor MCP se toca de nuevo.
- **Sin probar con un cliente MCP real** (Claude Desktop u otro) --
  solo `server.list_tools()`/`server.call_tool()` invocados
  directamente en Python. El transporte stdio (`server.run()` en
  `if __name__ == "__main__"`) no se ha ejercitado de verdad.
- `search_efsa_opinion` sigue pagando la llamada completa al Nodo 4
  (esperado, es su propósito -- respuesta narrativa) -- el ahorro de
  coste solo aplica a `get_reevaluation_status`.
- Detección de ambigüedad en el Nodo 3, deploy, mejora de retrieval del
  Nodo 2: sin cambios esta sesión.

## 2026-08-18 (continuación 17) — Test automatizado para el servidor MCP

**Contexto:** pendiente señalado al cierre de la entrada anterior --
`mcp/server.py` solo tenía verificación manual con stubs, sin nada en
`tests/`. Se pidió cerrarlo con el mismo patrón de stubs que
`test_nodes.py` usa para el truncamiento del Nodo 4 (`_StubLLMClient`),
sin gastar tokens reales, cubriendo como mínimo: esquema de
`list_tools()`, `get_reevaluation_status` con sustancia conocida sin
pasar por el Nodo 4, y degradación con gracia con sustancia no
identificada en ambas herramientas.

**Implementado -- `tests/test_mcp_server.py`, 6 tests:**
1. `test_list_tools_exposes_exactly_the_two_expected_tools_with_schema`
   -- nombres exactos, `inputSchema` (`substance: string`, único
   requerido), `outputSchema` presente en ambas.
2. `test_get_reevaluation_status_known_substance_returns_structured_json_without_node4`
   -- aspartamo (tier 1, con ADI) vía stub de `resolve_current_opinion`;
   `answer_question` dejado como `_exploding` (lanza `AssertionError`
   si se le llama) -- confirma en positivo, no por casualidad, que
   `get_reevaluation_status` nunca invoca el camino del Nodo 4.
3. `test_get_reevaluation_status_tier2_without_adi_reports_null_adi_not_invented`
   -- caso TiO2 (dictamen vigente, sin ADI numérico): `adi_value`/
   `adi_unit`/`adi_justification` deben ir `None`, nunca un valor
   inventado; `discussion_available` en `False` por boilerplate.
4. `test_search_efsa_opinion_known_substance_returns_narrative_answer`
   -- stub de `answer_question` con `AnswerResult` completo;
   `resolve_current_opinion` dejado como `_exploding` (simétrico al
   punto 2, confirma que search_efsa_opinion tampoco llama al camino
   parcial).
5. `test_get_reevaluation_status_unidentified_substance_degrades_gracefully`
   -- `ReevaluationStatus` con todo en `None` -- todos los campos de
   datos `None`/`False` explícitos, `safety_note` presente igualmente.
6. `test_search_efsa_opinion_unidentified_substance_degrades_gracefully`
   -- mismo caso para el camino completo.

**Detalles de implementación:**
- Sin `pytest-asyncio` en el proyecto (no está en `requirements.txt`)
  -- `list_tools()`/`call_tool()` son async, se invocan con
  `asyncio.run(...)` dentro de tests síncronos normales en vez de
  añadir una dependencia nueva solo para esto.
- `monkeypatch.setattr(mcp_server, "answer_question", ...)` /
  `"resolve_current_opinion"` -- parchea los nombres en el namespace
  del MÓDULO `efsa_rag.mcp.server` (donde las herramientas los buscan
  en tiempo de llamada), no en `efsa_rag.graph.build` -- mismo patrón
  verificado manualmente en la sesión anterior antes de escribir el
  test.
- `_exploding(*_args, **_kwargs)` reutilizable, mismo espíritu que
  `_ExplodingVectorStore` de `test_hybrid_retrieval_node_no_uuid_skips_chroma_entirely`
  en `test_nodes.py` -- afirmar en positivo que una ruta NO se toma, no
  solo que el resultado final sea el esperado.

**Verificado:** los 6 tests nuevos pasan en 1,36 s (sin red, sin xlsx,
sin Chroma). Suite completa: **30 passed, 2 skipped** (los 2 de
siempre, por falta de `DEEPSEEK_API_KEY`) -- sin regresiones.

**Actualizado:** `CLAUDE.md` -- el caveat "sin test automatizado" de la
entrada de `mcp/server.py` en "Implementado" sustituido por el detalle
de los 6 tests; pendiente #7 actualizado (ya no falta el test, solo
queda probar con un cliente MCP real).

**Pendiente / sin resolver al cierre de esta entrada:**
- Sigue sin probarse con un cliente MCP real (Claude Desktop u otro) --
  solo `list_tools()`/`call_tool()` invocados directamente en Python,
  ahora también en los tests, pero nunca a través del transporte stdio
  real (`server.run()`).
- Detección de ambigüedad en el Nodo 3, deploy, mejora de retrieval del
  Nodo 2: sin cambios esta sesión.

## 2026-08-18 (continuación 18) — Medición real de memoria: 1.870 MB, bloquea el deploy en el tier gratuito

**Contexto:** antes de intentar el deploy (pendiente #8), se pidió
medir el consumo de memoria REAL de la app completa en local -- Chroma
con los 67.827 chunks, el modelo de embeddings cargado, y el proceso de
Streamlit corriendo con una consulta real ya resuelta -- y avisar
explícitamente si se acercaba peligrosamente a 1 GB.

**Bloqueo encontrado antes de poder medir nada:** `ui/app.py` no
llamaba todavía a `answer_question()` (era un `TODO` literal) -- no
había forma de que una consulta real pasara por el proceso de
Streamlit. Preguntado al usuario cómo proceder; eligió conectar la UI
de forma permanente, manteniendo el candado de refresco y los límites
de consulta exactamente como estaban, aplicándose ANTES de la llamada
real.

**Implementado -- `ui/app.py`:** `_render_answer(query)` (import
perezoso de `graph.build.answer_question`, con `try/except` para no
tirar la sesión de Streamlit si la API falla) llamada SOLO si
`check_and_register_query()` devuelve `permitido=True` -- confirmado
explícitamente al usuario, releyendo `main()` línea a línea, que el
grafo nunca se invoca si el límite está agotado.

**Bug real encontrado y arreglado en el camino (no buscado, surgido al
intentar medir con `AppTest`):** `_get_client_ip()` podía devolver un
valor no-`str` (bajo el harness de test de Streamlit, probablemente
porque `session_info.request` no es una request HTTP real ahí), que
rompía `check_and_register_query()` -- `TypeError: keys must be str...
not MagicMock` al serializar el log de uso a JSON. El docstring ya
prometía degradar a `"unknown"` ante cualquier fallo; el `try/except`
capturaba excepciones pero no validaba el TIPO del valor devuelto en
el camino feliz. Arreglado con una comprobación de tipo explícita.

**Medición -- dos intentos, el primero falló, documentado igualmente
porque el diagnóstico en sí es información útil:**
1. `streamlit.testing.v1.AppTest` (sin necesitar navegador/Playwright,
   no instalados) -- cargó Streamlit, renderizó la app, cargó el
   modelo de embeddings, y se COLGÓ más allá de 180s. Diagnosticado
   antes de abandonar: red aislada a la API (2,4s, no es el problema),
   llamada directa completa a `answer_question()` fuera de `AppTest`
   (39s, funciona bien) -- apunta a que algo en `torch`/
   `sentence-transformers`/`chromadb` se comporta distinto fuera del
   hilo principal (`AppTest` ejecuta el script en un hilo dedicado),
   no investigado hasta la causa raíz exacta.
2. **Método final -- descomposición en dos medidas reales:** (a)
   `streamlit run` REAL como subproceso, sin consulta -- **63,2 MB**
   (coste base de Streamlit cargado). (b) proceso Python que importa
   `streamlit` + ejecuta el mismo camino que `_render_answer`
   (`build_default_deps()` + `build_graph()` + UNA consulta real de
   extremo a extremo, la pregunta de referencia de aspartamo) --
   **1.023,0 MB tras cargar Chroma+embeddings+xlsx+cliente LLM, 1.870,4
   MB tras la consulta real.** El paso [2] de `AppTest` (54,1 MB, app
   cargada sin consulta) fue consistente con la medida (a) del
   `streamlit run` real (63,2 MB) -- confirma que `AppTest` daba
   cifras fiables hasta donde llegó a funcionar, el problema era solo
   el cuelgue posterior.

**Desglose fino (sin gastar tokens, aparte, dos tablas):**
- `torch` (+455,7 MB) y `sentence_transformers` (+303,9 MB) solo en
  IMPORTS, antes de cargar ningún modelo -- el mayor contribuyente
  estructural, no depende de decisiones de este proyecto.
- Primera inferencia real de PyTorch (`model.encode()` de una query
  corta): **+410 MB** -- el salto más grande de toda la tabla, coste
  fijo de "warm-up" de PyTorch, no proporcional al tamaño del corpus
  ni al número de resultados pedidos.
- `collection.query()` de Chroma en sí (con o sin filtro `where`): ~2
  MB -- barato una vez todo está cargado.
- `OpenFoodToxStore` carga las hojas del xlsx de forma PEREZOSA, no al
  construirse -- la primera llamada real a
  `current_reference_value_opinion()` dispara ~193 MB de carga, dentro
  del Nodo 3, durante la consulta -- explica gran parte del salto de
  +847 MB medido en la consulta real de extremo a extremo (el resto,
  ~170-200 MB, no aislado con la misma precisión).

**Verificado con fuentes externas, no asumido:** Streamlit Community
Cloud, tier gratuito, límite de 1 GB de RAM por app (`WebSearch`,
varias fuentes independientes coincidentes).

**Conclusión, comunicada explícitamente tal como se pidió: 1.870 MB
medidos es ~87% por encima del límite de 1 GB -- no es un margen
ajustado, es un bloqueo real. El deploy en el tier gratuito tal como
está el sistema hoy fallaría por OOM.**

**Actualizado:** `CLAUDE.md` -- pendiente #8 marcado BLOQUEADO con el
resumen; nuevo hallazgo en "Hallazgos verificados" con puntero al
detalle completo en `docs/DECISIONES_VERIFICADAS.md`; entrada de
`ui/app.py` en "Implementado" actualizada (conectada al grafo + bug de
`_get_client_ip` arreglado).

**Limpieza:** proceso `streamlit run` de la medición matado al
terminar; `data/usage_log.json` (contaminado con 1 registro de prueba
de la sesión de `AppTest`) borrado -- se regenera limpio con
`_load_usage()` en el próximo uso real.

**Pendiente / sin resolver al cierre de esta entrada:**
- **Ninguna mitigación decidida ni implementada** para el problema de
  memoria -- candidatos sin evaluar: modelo de embeddings más ligero,
  evitar cargar `torch` completo (ej. `onnxruntime`), carga más
  selectiva de las hojas de OpenFoodTox, o subir de tier de hosting.
  Señalado al usuario para que decida antes de intentar el deploy.
- Causa raíz exacta del cuelgue de `AppTest` fuera del hilo principal:
  no investigada a fondo (había una alternativa más simple disponible).
- Suite de tests completa verificada sin regresiones tras los cambios
  de `ui/app.py` (30 passed, 2 skipped) -- sin test nuevo para
  `_render_answer`/`_get_client_ip` en `tests/` todavía (mismo patrón
  de hueco que otros nodos antes de que se les añadiera el suyo).
- Detección de ambigüedad en el Nodo 3, servidor MCP (transporte stdio
  real), mejora de retrieval del Nodo 2: sin cambios esta sesión.

## 2026-08-18 (continuación 19) — Backend de embeddings cambiado a ONNX int8; índice de Chroma reconstruido; pivote de plan de deploy a HF Spaces

**Contexto:** tras el bloqueo de memoria de la continuación 18
(1.870 MB, ~87% sobre el límite de 1 GB de Streamlit Community Cloud),
varios turnos de investigación e implementación real, resumidos aquí
en una sola entrada:

**1. HF Spaces investigado como alternativa de plataforma -- NUNCA
adoptado como plan activo, corregido en sesión 18-ago-2026 continuación
21 tras una afirmación incorrecta de Claude en esta misma entrada y en
la continuación 20.** Lo que sigue describe la INVESTIGACIÓN hecha en
su momento, no una decisión tomada -- **Streamlit Community Cloud
siguió siendo el plan de deploy activo todo este tiempo**, el usuario
nunca lo cambió. Se investigó HF Spaces (CPU Basic, 16 GB RAM -- cubre
los 1.870 MB con margen amplio, sin necesitar optimizar memoria por sí
solo) como posible alternativa si Streamlit Community Cloud resultaba
inviable por memoria. Se investigó el mecanismo real de deploy en HF
Spaces (README.md YAML, Dockerfile, secrets, empaquetado de Chroma vía
git-lfs o Dataset repo) -- **hallazgo: el SDK nativo `streamlit` está
deprecado desde 30-abr-2025 (hay que usar `sdk: docker`), y el SDK
`docker` en CPU Basic dejó de ser gratuito en cuentas free hacia el
8-24 jul-2026 (sin anuncio oficial, confirmado por múltiples hilos del
foro de HF, afecta también a cuentas ya existentes)** -- requeriría HF
PRO, $9/mes. Esto hace a HF Spaces bastante menos atractivo de lo que
parecía a primera vista, y es una de las razones por las que el plan
NUNCA se cambió en la práctica -- la otra parte de la corrección es que
Claude, en esta misma entrada y en la continuación 20, escribió "plan
de plataforma cambiado"/"pivotó a HF Spaces" como si fuera un hecho ya
decidido, cuando en realidad solo se había investigado como
alternativa. Ver la continuación 21 para la corrección completa y el
motivo por el que salió a la luz (el usuario lo señaló directamente al
pedir preparar el repo para un deploy real en Streamlit Community
Cloud).

**2. Investigación ONNX Runtime como backend alternativo a `torch`,
pedida explícitamente antes de comprometerse a tocar el pipeline:**
- Confirmado: `all-MiniLM-L6-v2` tiene 9 variantes ONNX publicadas en
  su repo oficial, de fp32 (90,4 MB) a int8 cuantizado (~23 MB).
- **Hallazgo central, verificado de la forma más directa posible
  (desinstalando `torch` del venv):** `sentence-transformers` (5.7.0)
  **no se puede ni importar sin `torch` instalado**, aunque se elija
  `backend="onnx"` -- revienta en
  `sentence_transformers/util/distributed.py` (`import
  torch.distributed as dist`, incondicional), antes de que el código
  llegue a elegir backend. `torch` reinstalado inmediatamente después
  para no dejar el venv roto.
- Medido en 3 procesos aislados (streamlit + sentence-transformers +
  una consulta, sin Chroma): torch (CUDA) 1.363,7 MB; onnx fp32
  1.019,7 MB (-25%); **onnx int8 924,7 MB (-32%)**. El ahorro no viene
  de evitar `torch` (sigue importado en los 3 casos) sino de evitar el
  "calentamiento" de la primera inferencia de PyTorch (~400 MB) --
  ONNX Runtime hace la inferencia real.

**3. Combinación torch CPU-only + ONNX int8, medida sobre el pipeline
COMPLETO (Streamlit + Chroma 67.827 chunks + una consulta real de
extremo a extremo), no solo aislada:**
- `torch` CPU-only instalado (`--index-url .../whl/cpu`) -- build
  191,8 MB descargado, frente al build CUDA bastante más pesado.
  `import torch` solo: 252 MB (CPU) vs ~456 MB (CUDA) en el
  experimento aislado anterior.
- Resultado del pipeline completo: **1.213,6 MB -- 189,6 MB (18%) por
  encima del límite de 1 GB.** Reducción real del 35% frente a los
  1.870,4 MB originales (torch CUDA + backend torch), pero no
  suficiente por sí sola para bajar de 1 GB.
- `torch` restaurado al build CUDA original al terminar (para no
  degradar silenciosamente el entorno de desarrollo local, que se
  beneficia de GPU para reindexados).
- Aviso técnico señalado en su momento: el índice de Chroma se había
  construido con el modelo fp32/torch original -- consultar con
  int8/onnx introducía un desajuste fp32/int8 entre chunks indexados y
  queries, no validado sistemáticamente más allá de una consulta de
  humo.

**4. Esta sesión -- IMPLEMENTADO de verdad, no solo medido:** se pidió
reconstruir el índice completo con el MISMO modelo ONNX int8 con el
que se consulta en producción, para eliminar el desajuste fp32/int8, y
verificar con la consulta de aspartamo tras la reconstrucción.

- **Nuevo módulo `ingestion/embedding_model.py`** -- único punto de la
  base de código que instancia `SentenceTransformer`, para que
  indexado y retrieval no puedan desincronizarse por editar una copia
  y olvidar la otra: `EMBEDDING_MODEL_REPO_ID =
  "sentence-transformers/all-MiniLM-L6-v2"`,
  `EMBEDDING_ONNX_FILE = "onnx/model_qint8_avx512_vnni.onnx"`,
  `load_embedding_model()`.
- **Actualizados los 3 sitios que antes instanciaban el modelo por
  separado** (verificado con `grep` que no quedó ninguno suelto):
  `scripts/build_chroma_index.py` (los 3 modos: `--test-batch`,
  `--all`, `--verify`), `graph/build.py::build_default_deps`, y el
  fixture `chroma_deps` de `tests/test_nodes.py`.
- **`requirements.txt`**: `sentence-transformers>=3.0` ->
  `sentence-transformers[onnx]>=3.0` (añade `optimum` + `onnxruntime`
  -- este último ya era dependencia transitiva de `chromadb`, no es
  100% peso nuevo).
- **Validado con `--test-batch` primero** (300 chunks, colección
  efímera, no toca `data/chroma/`) antes de comprometerse al
  reindexado completo -- resultados semánticamente correctos.
- **Reindexado completo ejecutado (`--all`, en segundo plano, ~22,4
  min reales -- más lento que los ~3 min con GPU+torch de la sesión
  original, esperado y aceptado por ser un paso offline):
  67.827/67.827 chunks escritos, verificado.** 3 consultas de
  verificación (genotoxicidad, TiO2, incertidumbre de exposición)
  temáticamente correctas, mismo patrón de calidad que con el índice
  anterior.
- **Verificación pedida explícitamente -- consulta de aspartamo
  end-to-end (`answer_question`, grafo completo, con el índice YA
  reconstruido):** ADI = 40 mg/kg bw/día (correcto), DOI correcto
  (10.2903/j.efsa.2013.3496), 5 chunks recuperados, todos "Aspartame"
  tier 1, respuesta coherente y con las reglas de comunicación de
  riesgo respetadas (margen de seguridad explicado correctamente, sin
  la frase prohibida). Pegada íntegra en el turno correspondiente.
- Suite de tests completa: **32 passed** (esta vez sin skips --
  `DEEPSEEK_API_KEY` estaba exportada en la sesión de shell, así que
  los tests del Nodo 1 también corrieron de verdad).

**Efecto secundario no buscado, anotado sin investigar más:** el
tamaño en disco de `data/chroma/` subió de 597 MB a **718 MB** (+20%)
tras la reconstrucción -- las embeddings de salida siguen siendo
float32 de 384 dims igual que antes (la cuantización int8 es interna
al modelo ONNX, no cambia el formato de lo que se almacena), así que
el aumento no se explica por eso; no se ha investigado la causa exacta
(¿fragmentación de SQLite al recrear la colección? ¿metadata
distinta?) -- no bloqueante, el disco no era la restricción que se
estaba optimizando.

**Pendiente / sin resolver al cierre de esta entrada:**
- El usuario todavía no ha confirmado si HF Spaces Docker en CPU Basic
  es viable en su cuenta (paso manual pendiente, ver punto 1).
- Con esta combinación (torch CPU-only + ONNX int8) el pipeline sigue
  ~190 MB por encima de 1 GB -- si en algún momento se retoma
  Streamlit Community Cloud como alternativa, hace falta una palanca
  más (candidatos no explorados: carga más selectiva de las hojas de
  OpenFoodTox en el Nodo 3, revisar si `langchain`/`langgraph` aportan
  peso evitable, seguir sin `torch` sería ideal pero no es viable con
  `sentence-transformers` tal como está).
- El torch CPU-only usado en la medición de la continuación anterior
  NO se ha dejado instalado -- el venv de desarrollo local sigue con
  el build CUDA. Si el deploy final necesita CPU-only (para ahorrar
  memoria en producción), hace falta decidir cómo se gestiona esa
  diferencia entre entorno de desarrollo (GPU, útil para reindexados)
  y entorno de producción (CPU-only, más ligero) -- probablemente vía
  `requirements.txt` distinto o un extra opcional, no resuelto aquí.
- Tamaño en disco de `data/chroma/` creció un 20% sin explicación
  investigada (ver arriba).
- Detección de ambigüedad en el Nodo 3, servidor MCP (transporte stdio
  real), mejora de retrieval del Nodo 2, verificación manual de HF
  Spaces: sin cambios/resolver esta sesión.

## 2026-08-18 (continuación 20) — `usecols` en OpenFoodToxStore; requirements.txt fija torch CPU-only; memoria re-medida: ~1.150-1.170 MB, sigue sobre 1 GB pero -60 MB

**Contexto:** siguiente palanca de memoria pendiente de la continuación
19 (que dejó el pipeline en 1.213,6 MB, ~190 MB sobre el límite de 1 GB
de Streamlit Community Cloud) -- las 5 hojas de `OpenFoodToxStore` se
cargaban completas con `pd.read_excel(..., header=0)`, reteniendo en
memoria muchas más columnas de las que el código llega a leer, durante
toda la vida del proceso (son `functools.cached_property`, no se
liberan).

**1. `usecols` implementado en las 5 hojas
(`src/efsa_rag/ingestion/openfoodtox.py`), por auditoría explícita, no
adivinada.** Antes de tocar código: `grep` de cada acceso `df["..."]` a
las 5 hojas dentro del propio módulo, MÁS los callers externos que
tocan las mismas hojas directamente vía las propiedades públicas
(`store.dossier`/`store.dossier_docs`/`store.sub`/`store.flex_sum_toxref`)
-- `scripts/generate_pdf_checklist.py`,
`ingestion/pdf_chunking.py` (incluida `_guess_substance_by_title`, el
camino de resolución de NIVEL 3 -- la rama menos obvia, con su propio
acceso a `SUB.ChemicalName`/`Document UUID`, señalada explícitamente
por el usuario como caso a no pasar por alto) y
`tests/test_openfoodtox_joins.py` (los 2 tests-canario que comprueban
que `ADI_*_COLUMN`/`DISCUSSION_COLUMN` siguen existiendo en la hoja
real). Verificado con `grep` sobre todo el repo que ningún otro caller
toca estas hojas por fuera de esos módulos.

- Nuevas constantes `DOSSIER_USECOLS` (7 columnas: `Document UUID`,
  `Domain.FoodDomain`, `Domain.Regulation`,
  `LiteratureReference.EFSAOutputTitle`, `LiteratureReference.Type`,
  `LiteratureReference.DateOfEvaluation`,
  `LiteratureReference.LinkToPersistentIdentifier`),
  `DOSSIER_DOCS_USECOLS` (3: `DOSSIER UUID`, `DOCUMENT UUID`,
  `DOCUMENT TYPE`), `SUB_USECOLS` (2: `Document UUID`,
  `ChemicalName`), `FLEX_SUM_TOXREF_USECOLS` (5: `Document UUID`,
  `Parent UUID` + los 3 `ADI_*_COLUMN` ya existentes),
  `END_SUM_USECOLS` (2: `Document UUID`, `DISCUSSION_COLUMN`).
- Las 5 `cached_property` (`dossier`, `dossier_docs`, `sub`,
  `flex_sum_toxref`, `end_sum`) pasan `usecols=` a `pd.read_excel`.

**2. Verificación, en dos capas, no solo "los tests pasan":**
- Suite completa contra el xlsx real: **30 passed, 2 skipped**
  (mismos 2 de siempre, `DEEPSEEK_API_KEY`) -- incluye explícitamente
  los tests de `require_adi=False` (nitritos/tartratos/glutamatos,
  Nivel 2) y los 2 tests-canario de columnas.
- **`_guess_substance_by_title` (Nivel 3, el camino que el usuario
  pidió no dar por sentado) probado a mano fuera de la suite**, caso
  Shellac: `resolve_dossier_substances(...)` sigue devolviendo
  `[('Shellac', tier=3)]` -- confirma que `SUB_USECOLS` no rompió esta
  rama.
- **`scripts/generate_pdf_checklist.py` re-ejecutado contra el xlsx
  real** (el otro caller externo con más superficie de columnas,
  `dossier_docs`+`sub`+`flex_sum_toxref`+`dossier` a la vez): salida
  (`data/pdf_download_checklist.csv`/`.md`, 161 filas) **byte-idéntica
  a la ya versionada en git** (`git diff --stat` vacío tras
  regenerar) -- confirma que ninguna columna necesaria quedó fuera.

**3. `requirements.txt` -- torch CPU-only fijado explícitamente
(pedido por el usuario a mitad de turno, no derivado de la medición de
memoria de esta sesión):** `--extra-index-url
https://download.pytorch.org/whl/cpu` + `torch==2.13.0+cpu` añadido
ANTES de la línea `sentence-transformers[onnx]>=3.0` (mismo
requirements.txt, mismo `pip install` -- el pin explícito de torch se
unifica con la resolución del extra `[onnx]`, que de otro modo tira de
torch sin restricción y resolvería al build CUDA por defecto de PyPI).
Versión `2.13.0` elegida porque es la que ya estaba instalada en el
venv de desarrollo (build CUDA, `2.13.0+cu130`) -- confirmado con `pip
index versions torch --index-url https://download.pytorch.org/whl/cpu`
que existe el build `2.13.0+cpu` correspondiente antes de fijarlo.
Motivo del pin: sin él, un `pip install -r requirements.txt` limpio en
el host de deploy resuelve el build con CUDA por defecto (arrastra
`nvidia-*-cu12`, mucho más pesado) -- exactamente el problema que la
continuación 19 tuvo que mitigar manualmente instalando CPU-only solo
para medir, y luego revirtiendo. Con este pin, el deploy real no
depende de que alguien lo recuerde a mano.
**El venv de desarrollo local NO se deja en CPU-only** -- se instaló
temporalmente para la medición del punto 4, y se restauró al build
CUDA original al terminar (`pip install --force-reinstall --no-deps
torch==2.13.0` no bastó por sí solo -- PEP 440 hace que `==2.13.0` sin
segmento local siga matcheando el `+cpu` ya instalado y no reinstale
nada; hizo falta `--force-reinstall` para que sí forzara la
reinstalación del build CUDA por defecto de PyPI). Verificado
`torch.__version__ == '2.13.0+cu130'` tras restaurar. Suite completa
vuelta a correr tras restaurar: 30 passed, 2 skipped, sin
regresiones.

**4. Memoria del pipeline completo re-medida, mismo método que
continuaciones 18/19** (proceso Python que importa `streamlit` +
`build_default_deps()` + `build_graph()` + una consulta real de
extremo a extremo, aspartamo, vía `/proc/self/status VmRSS`), con las
TRES optimizaciones activas a la vez (torch CPU-only, ONNX int8,
`usecols`):

| Punto de medición | RSS |
|---|---|
| Proceso arrancado | ~9 MB |
| Tras `import streamlit` | ~44,5 MB |
| Tras importar `graph.build` (sin invocar nada) | ~157,5 MB |
| **Tras `answer_question()` completo (1 consulta real)** | **~1.150-1.170 MB** (2 corridas: 1.149,9 y 1.169,0 MB) |

Verificado que la consulta en sí siguió siendo correcta durante la
medición (no solo que el proceso no petara): ADI = 40 mg/kg bw/día,
unidad correcta, 5 `retrieved_chunks`, respuesta con el DOI/dictamen
de 2013 correctos.

**Cifra final pedida explícitamente por el usuario -- frente al límite
de 1 GB (1.024 MB) de Streamlit Community Cloud: SIGUE POR ENCIMA,
~126-145 MB (12-14%) sobre el límite** (bajó de los 1.213,6 MB de la
continuación 19 a ~1.150-1.170 MB -- ahorro real de `usecols` de
~44-64 MB, dentro de lo esperado para 5 hojas de un xlsx de 22,6 MB
con bastantes columnas descartadas, no una solución completa por sí
sola). La variación entre las dos corridas (~19 MB) es ruido normal
(longitud de la respuesta del LLM, GC) -- no se ha investigado más
allá de confirmar que ambas corridas están en el mismo orden de
magnitud. **CONCLUSIÓN: el pipeline sigue sin caber en el tier
gratuito de Streamlit Community Cloud tal como está hoy** -- y
**Streamlit Community Cloud SIGUE siendo el destino de deploy activo**
(corrección hecha en continuación 21: el párrafo original de esta
entrada decía que el plan había "pivotado a HF Spaces", lo cual era
incorrecto -- HF Spaces solo se investigó como alternativa, nunca se
adoptó, ver la corrección completa en la entrada de la continuación 19
y en la 21). Con Streamlit Community Cloud como destino real, el gap
de ~126-145 MB sigue sin cerrar -- candidatos NO explorados todavía:
revisar peso de `langchain`/`langgraph`, o algo más agresivo como
servir el pipeline sin `sentence-transformers` (inference vía ONNX
Runtime + tokenizer directo, sin la capa de `SentenceTransformer` --
evaluado como posible palanca en la continuación 21, pero el usuario
decidió NO implementarlo por ahora y en su lugar intentar el deploy
real tal como está, para observar el comportamiento empírico en vez de
seguir optimizando en el vacío).

**Actualizado:** `CLAUDE.md` -- pendiente #8 con la cifra recalculada.

**Pendiente / sin resolver al cierre de esta entrada:**
- El gap de ~126-145 MB sobre 1 GB sigue sin cerrarse.
- Resto de pendientes sin cambios esta sesión (detección de
  ambigüedad Nodo 3, servidor MCP con transporte real, mejora de
  retrieval Nodo 2, causa del +20% en disco de `data/chroma/` --
  esto último SÍ se investigó y resolvió en la continuación 21, ver
  esa entrada).

## 2026-08-18 (continuación 21) — Corrección: Streamlit Community Cloud NUNCA dejó de ser el plan activo; causa del +20% en disco de Chroma encontrada y arreglada; preparación real del repo para el primer deploy (descarga de datos desde MEGA S4, sin git)

**Corrección, pedida directamente por el usuario -- tratar con la
misma seriedad que cualquier otro hallazgo, no como un simple typo:**
las continuaciones 19 y 20 de este documento (y la sección
correspondiente de `CLAUDE.md`, pendiente #8) afirmaban que el plan de
deploy había "cambiado"/"pivotado" de Streamlit Community Cloud a HF
Spaces. **Eso era incorrecto. El usuario nunca cambió el plan --
Streamlit Community Cloud siguió siendo el destino activo todo este
tiempo.** Lo que de verdad pasó en la continuación 19: HF Spaces se
investigó como alternativa POSIBLE (motivada por el bloqueo de memoria
de la continuación 18), se encontró que también tiene un bloqueo propio
(SDK docker de pago en cuentas free desde jul-2026), y ahí quedó --
nunca se ejecutó ningún cambio de plan real. Ambas entradas anteriores
se han corregido in situ (bloques de corrección, mismo patrón que la
corrección de la continuación 13 sobre el Nodo 4) en vez de reescribir
la historia -- el error de redacción de Claude queda documentado, no
borrado.

**Además, a mitad de turno, el usuario detuvo una segunda dirección
equivocada antes de que se ejecutara:** Claude había empezado a
preparar `data/chroma/` y el xlsx para subirlos a git vía Git LFS (en
un repo privado, para no violar la restricción de licencia de "no al
repo público"). El usuario paró esto explícitamente: **la decisión ya
tomada (ver CLAUDE.md, "Decisiones de arquitectura ya tomadas") es que
estos datos NUNCA van a ningún repo de GitHub, público o privado --
`data/chroma/` contiene texto literal de los chunks, no solo
embeddings, y la licencia de los PDFs (CC BY-ND para 2016-2025, sin
licencia abierta en absoluto para 2007-2016) no cubre eso bajo ningún
esquema de repo.** La ruta correcta, ya decidida por el usuario en
algún punto anterior no reflejado todavía en `CLAUDE.md`: los datos
viven en MEGA S4 (almacenamiento de objetos S3-compatible, incluido en
el plan MEGA Pro Lite del usuario) y se descargan en tiempo de
arranque del contenedor de deploy, nunca versionados. El repo de
GitHub se queda público y limpio.

**1. Causa del +20% en disco de `data/chroma/` (continuación 19, sin
investigar hasta ahora) -- encontrada y arreglada.** Verificado con SQL
directo contra `chroma.sqlite3` (tabla `segments`, columna `collection`
cruzada con `collections`): el segmento VECTOR vivo de la colección
`efsa_reevaluation_chunks` es el directorio `5cb4698b-...`; había un
SEGUNDO directorio (`1f380e8e-...`, 121 MB) que no aparece en ninguna
fila de `segments` -- huérfano de una reconstrucción anterior del
índice (probablemente el backend `torch`/fp32 original, sustituido por
ONNX int8 en la continuación 19 sin que `chromadb` limpiara el
directorio del segmento viejo al recrear la colección). Confirmado
huérfano ANTES de borrar, no solo por tamaño/fecha. Borrado
(`data/chroma` pasa de 719 MB a **598 MB**) y verificado después:
`collection.count() == 67827` sin cambios, una consulta real de
verificación (genotoxicidad de aspartamo) sigue devolviendo el chunk
correcto. Directamente relevante para el punto 3 de abajo -- 598 MB en
vez de 719 MB es lo que de verdad se sube a MEGA S4.

**2. Módulo nuevo `src/efsa_rag/deploy_assets.py` --
`ensure_deploy_assets_downloaded()`:** descarga el xlsx y un tarball de
`data/chroma/` desde MEGA S4 (boto3, API S3-compatible,
`addressing_style=path`, sig v4) SOLO si no están ya en disco -- en
desarrollo local (datos ya presentes) esta función no toca la red en
absoluto, verificado explícitamente (llamada real con los datos ya en
disco -> `False`, sin intentar construir el cliente S3 ni pedir
credenciales). Si faltan Y no hay credenciales configuradas, lanza
`RuntimeError` con un mensaje explícito de qué falta -- verificado
también explícitamente (simulando rutas inexistentes). Endpoint /
bucket / credenciales / región SIEMPRE por variable de entorno
(`MEGA_S4_ENDPOINT_URL`/`MEGA_S4_BUCKET`/`MEGA_S4_ACCESS_KEY_ID`/
`MEGA_S4_SECRET_ACCESS_KEY`/`MEGA_S4_REGION`), nunca hardcodeadas. El
formato de endpoint de MEGA S4 (`s3.<region>.s4.mega.io` o
`s3.<region>.megas4.com`, dos estilos de direccionamiento soportados)
se verificó contra `github.com/meganz/s4-specs` antes de escribir el
cliente, no se asumió.

**3. `scripts/upload_deploy_assets.py` (nuevo, manual, un solo uso por
el usuario con sus propias credenciales):** empaqueta `data/chroma/` en
un tarball y sube ambos objetos al bucket. `--dry-run` probado contra
los datos reales tras la limpieza del punto 1: **xlsx 21,5 MB, chroma 6
ficheros / 597,1 MB sin comprimir** -- confirma que el script localiza
y mide los ficheros correctos antes de comprometerse a implementar la
subida real (no ejecutada en esta sesión -- requiere las credenciales
reales de MEGA S4 del usuario, que Claude no tiene ni debe pedir por
chat).

**4. `ui/app.py::_render_answer`** llama a
`ensure_deploy_assets_downloaded()` justo antes de importar
`graph.build` (que es lo primero que intentaría abrir `data/chroma/` y
leer el xlsx), con su propio `try/except` y mensaje de error
diferenciado del de la generación de la respuesta -- mismo patrón de
degradación con gracia que el resto de la UI, no una excepción sin
capturar.

**5. `requirements.txt`** gana `boto3>=1.34`. **`.env.example`** gana
las 5 variables `MEGA_S4_*` con comentario explicando cuándo hacen
falta en local (casi nunca) y cómo se trasladan a Streamlit Community
Cloud (campo "Secrets", formato TOML, no `.env`).

**6. `README.md`** gana una sección "Deploy en Streamlit Community
Cloud" con los pasos concretos (subir datos con el script, crear la
app en share.streamlit.io, seleccionar Python en Advanced settings,
pegar Secrets) **más el riesgo de memoria conocido citado
explícitamente y sin suavizar** (~1.150-1.170 MB medidos vs. ~1 GB de
límite del tier gratuito, ver continuación 20) -- para que si el primer
intento de deploy falla por OOM, no se lea como un fallo de
configuración de este documento sino como el límite ya conocido.

**Investigado, verificado con fuentes externas actuales (no asumido) y
NO implementado, por decisión explícita del usuario cuando se le
preguntó -- reescribir el pipeline de embeddings para usar ONNX Runtime
directo (sin la capa de `sentence-transformers`/`SentenceTransformer`)
como palanca adicional de memoria:** el usuario decidió NO tocar esto
ahora y en su lugar intentar el deploy real tal como está, para
observar el comportamiento empírico. Queda como candidato futuro si el
deploy real confirma el bloqueo por memoria, no descartado, solo
diferido.

**Investigado con `WebSearch`/`WebFetch` contra la documentación
oficial vigente de Streamlit (no de memoria) antes de dar por buena
ninguna afirmación sobre el proceso de deploy:**
- Git LFS "simplemente funciona" con Streamlit Community Cloud sin
  cambios de código (no relevante ya para este proyecto tras el pivote
  a MEGA S4, pero se investigó ANTES de que el usuario corrigiera el
  rumbo -- dejado aquí por honestidad del proceso, no por utilidad).
- Los secretos pegados en el campo "Secrets" (formato TOML) se exponen
  automáticamente como `os.environ` ADEMÁS de `st.secrets` -- confirma
  que `os.environ["DEEPSEEK_API_KEY"]` (ya existente,
  `graph/llm_client.py`) y las nuevas `os.environ["MEGA_S4_*"]`
  funcionan sin ningún cambio de código, solo pegando el TOML correcto
  en el deploy.
- La versión de Python se selecciona en "Advanced settings" al crear
  la app (por defecto 3.12, todas las versiones mantenidas soportadas)
  -- no hace falta ningún `runtime.txt`; `pyproject.toml` ya declara
  `requires-python = ">=3.11"`, compatible.
- Tier gratuito: 1 app privada permitida (no relevante ya, el repo se
  queda público) + límite de RAM ~1 GB (ya conocido, re-confirmado) +
  las apps duermen tras 12h sin tráfico.

**Actualizado:** `CLAUDE.md` -- pendiente #8 corregido (Streamlit
Community Cloud como destino activo, sin la afirmación de pivote a HF
Spaces); nueva decisión de arquitectura documentada ("Deploy de datos
pesados vía MEGA S4, nunca en git").

**Verificado sin regresiones:** suite completa tras todos los cambios
de esta sesión (usecols + requirements.txt + deploy_assets.py +
ui/app.py): **30 passed, 2 skipped**, mismos 2 de siempre.

**Pendiente / sin resolver al cierre de esta entrada:**
- La subida real a MEGA S4 (`scripts/upload_deploy_assets.py` sin
  `--dry-run`) no se ha ejecutado -- necesita las credenciales reales
  del usuario, fuera del alcance de esta sesión.
- El primer deploy real en Streamlit Community Cloud no se ha
  intentado todavía -- pendiente de que el usuario lo haga desde su
  propia cuenta, como pidió explícitamente.
- El riesgo de memoria (~1.150-1.170 MB vs. ~1 GB) sigue sin
  resolverse -- el usuario decidió observarlo empíricamente en vez de
  seguir optimizando a ciegas.
- Resto de pendientes sin cambios esta sesión (detección de
  ambigüedad Nodo 3, servidor MCP con transporte real, mejora de
  retrieval Nodo 2).
