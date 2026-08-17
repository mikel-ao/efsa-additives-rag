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
- La tabla de cobertura de `discussion_text` (32,2%, 38/73/7 dossiers)
  está calculada sobre el corpus de 118 previo al fix de dominio -- NO
  recalculada todavía sobre los 136 actuales. Podría cambiar la cifra
  ligeramente al incluir los 18 dictámenes rescatados.
- El campo `HumanHealthHazardCharacteristics.AcceptableDailyIntake.CriticalEndpoint`
  sigue investigado y descartado (ver CLAUDE.md) -- no se ha vuelto a
  tocar esta sesión.
- Nodo 2, Nodo 1 (lookup español/E-numbers), servidor MCP, deploy: sin
  cambios esta sesión.
