# CLAUDE.md — efsa-additives-rag

Este documento existe para que no repitas trabajo de diseño ya hecho, ni
reviertas decisiones ya tomadas con datos reales. Léelo entero antes de
tocar código. Si algo aquí te parece mejorable, dilo y discútelo — no lo
cambies en silencio.

## Qué es este proyecto

RAG assistant sobre dictámenes de reevaluación de aditivos alimentarios
(EFSA, Reglamento UE 257/2010). Proyecto de portfolio del autor (química/
ciencia de alimentos, 6 años de investigación, patente, 30+ publicaciones,
en transición a Data Science/AI). La razón de ser del proyecto es la
diferenciación de dominio, no la ejecución técnica en sí — no lo conviertas
en un ejercicio genérico de "monté un RAG con LangGraph".

Documentación completa (objetivo, audiencia, stack, roadmap): `docs/efsa-rag-proyecto.html`.
Ábrelo y léelo también antes de empezar.

## Cómo trabajar en este repo

- **Verifica contra datos reales antes de implementar, no asumas el esquema.**
  Varias decisiones de este proyecto cambiaron cuando se inspeccionó el xlsx
  real de OpenFoodTox en vez de fiarse de la documentación pública (ver
  "Hallazgos verificados" abajo). Si vas a tocar `ingestion/openfoodtox.py`
  o el esquema de datos, inspecciona las hojas reales primero.
- **No metas scope creep.** Ya se descartó explícitamente: integrar PubMed
  (ver "Restricciones no negociables"), refresco en tiempo real del corpus,
  y ampliar el alcance más allá de aditivos en reevaluación bajo 257/2010.
  Si crees que algo debería añadirse, pregúntalo, no lo añadas.
- **Documenta las limitaciones, no las escondas.** El README y
  `docs/.../LIMITATIONS.md` existen para eso. Si implementas algo con una
  limitación conocida (ej. el heurístico del Nodo 3 no cubre todos los
  casos borde), anótalo ahí, no lo dejes como sorpresa.
- **Mantén actualizado `PROGRESS.md`** (en la raíz del repo) según avances.
  Ver instrucciones al final de este documento.
- **Cualquier script que llame al LLM en bucle o sobre un lote de elementos**
  (ej. iterar los 136 dictámenes, reintentos, pruebas de prompt) DEBE
  incluir un límite explícito de iteraciones y un modo `--dry-run` que
  muestre qué se va a llamar sin gastar tokens reales. La key de
  desarrollo tiene saldo prepago limitado (unos pocos euros) sin ningún
  candado automático como el que sí protege la demo desplegada
  (`ui/app.py` → `check_and_register_query`) -- un bucle mal acotado
  aquí sí puede agotar el saldo real. No lo des por sobreentendido en
  cada prompt: si vas a escribir un script así, añade el límite y el
  dry-run sin que haga falta que se te pida explícitamente.

## Restricciones no negociables

1. **Comunicación de riesgo del Nodo 4** (`graph/nodes.py` →
   `NODE_4_SAFETY_COMMUNICATION_RULES`): el ADI/TDI es un margen de
   seguridad (~×100 sobre el NOAEL), nunca un umbral de toxicidad.
   PROHIBIDO redactar "si se supera el ADI, se produce/puede producir
   [efecto]". Esta restricción va en el system prompt, no se deja a
   criterio del LLM en tiempo de ejecución. No la relajes ni la
   reformules sin discutirlo antes.

2. **No integrar PubMed ni ninguna fuente de literatura primaria** como
   contraste de las conclusiones EFSA. Se evaluó explícitamente y se
   descartó: mezclar un estudio individual con una conclusión regulatoria
   consensuada replica la estructura retórica de la desinformación
   alimentaria ("aunque el regulador dice X, hay estudios que dicen Y"),
   incluso si el LLM no falsea ningún dato. Si en el futuro se retoma,
   solo con literatura posterior a la fecha del dictamen vigente,
   etiquetada explícitamente como "no evaluada aún por el panel", nunca
   contrapuesta a la conclusión EFSA en el mismo párrafo.

3. **Esta es una herramienta de exploración de literatura regulatoria, no
   de asesoramiento regulatorio ni médico.** El sistema nunca debe emitir
   juicios de "seguro"/"no seguro" — solo citar lo que dice el dictamen.

## Hallazgos verificados (no los redescubras ni los contradigas sin motivo)

- **Filtro de corpus (cifra corregida en sesión 16-ago-2026, ver bullet
  de dominio mixto más abajo):** `Domain.FoodDomain == 'food additives'`
  + `'re-evaluation'` en `LiteratureReference.EFSAOutputTitle`
  (case-insensitive), **más el rescate de dictámenes reales mal
  etiquetados con otro dominio** (`_is_mistagged_food_additive_reevaluation`
  en `ingestion/openfoodtox.py`), da **136 dictámenes únicos** (tras
  deduplicar por título/DOI — una fila de `DOSSIER` por sustancia
  cubierta, no por dictamen). Sin el rescate de dominio daba 118 --
  cifra usada en el diseño original, ya superada, no la repitas como si
  fuera la actual. Filtrar por `Domain.Regulation == '257/2010'` da solo
  62 (infravalora el corpus real: la mayoría de reevaluaciones están
  etiquetadas con el reglamento marco 1333/2008, no con 257/2010). **No
  uses el campo de regulación como filtro principal.**
- **Cobertura del corpus NO está validada al 100%** contra una fuente
  oficial EFSA (no existe una tabla pública descargable para ese cruce).
  El programa sigue activo en 2025-2026 (follow-ups de plata E174,
  Patent Blue V E131, almidones modificados). Trátalo como corpus de
  trabajo razonable, no como lista cerrada.
- **Cadena de joins para vigencia (Nodo 3):**
  `FLEX_SUM.ToxRefValues` (Parent UUID = sustancia) → `DOSSIER_DOCS`
  (DOCUMENT UUID = Document UUID del ToxRefValues, DOCUMENT TYPE
  'FLEXIBLE_SUMMARY'/'ToxRefValues') → `DOSSIER` (DOSSIER UUID) → fecha/
  título/DOI. Filtrar `LiteratureReference.Type == 'EFSA opinion'`
  (excluir 'EFSA statement') antes de tomar `MAX(fecha)`. Verificado con
  aspartamo (E 951): 5 candidatos (2006, 2009×2, 2011 statement, 2013),
  resultado correcto = 2013-11-28. `Parent UUID` en la hoja `DOSSIER` está
  vacío en el 100% de las 11.613 filas — no uses esa hoja/campo para
  vigencia, la cadena correcta pasa por `FLEX_SUM.ToxRefValues`.
- **`current_reference_value_opinion` necesita filtrar también por dominio,
  no solo por `Type == 'EFSA opinion'`** (bug encontrado y corregido en
  sesión 16-ago-2026, `ingestion/openfoodtox.py`). Sin este filtro,
  `MAX(fecha)` puede elegir un dictamen de OTRO programa regulatorio
  (pienso animal FEEDAP, aromas/flavourings, contaminantes de procesado)
  para la misma sustancia química -- verificado con propil galato (E
  310): compite un dictamen de aditivo alimentario (2014-04-01,
  `Domain.FoodDomain == 'food additives'`) contra uno de seguridad como
  aditivo de pienso animal (2020-03-17, `Domain.FoodDomain ==
  'technological additives'`), y sin filtro gana el segundo. **No es un
  caso aislado: 29 de 102 sustancias del corpus de reevaluación (28,4%)
  tienen candidatos de dominio mixto.**
  - Filtro correcto: `Domain.FoodDomain == FOOD_DOMAIN_VALUE` **O**
    (título contiene `FOOD_ADDITIVE_TITLE_PHRASE` ("food additive") Y
    `REEVAL_TITLE_MARKER` ("re-evaluation")) -- MISMA CLASE DE RIESGO que
    el filtro de corpus de arriba, aproximación verificada contra los
    casos conocidos, no garantía estructural.
  - **El filtro de dominio a secas (sin la rama de título) NO basta**:
    de las 29 sustancias afectadas, 24 son genuinamente de otro programa
    y el filtro de dominio solo ya las excluye correctamente -- pero 5
    (plata E 174, sílice E 551, goma garrofín E 410, goma xantana E 415,
    ésteres cítricos de mono/diglicéridos E 472c) son dictámenes de
    aditivo alimentario reales y vigentes, mal etiquetados
    `Domain.FoodDomain == 'other:'` en vez de `'food additives'` --
    filtrar solo por dominio los descartaría y volvería a un dictamen
    antiguo ya superado (regresión, no fix). El caso de plata (E 174,
    follow-up 2025-03-06) ya estaba mencionado arriba como programa
    activo -- este es el mecanismo concreto por el que se perdería si no
    se maneja con cuidado.
  - **Tampoco basta con exigir solo la frase "food additive" en el
    título, sin exigir también "re-evaluation"**: 1.360 dictámenes de
    Flavouring Group Evaluation (dominio `flavourings`) también
    contienen "food additive" en el título, porque el panel que los
    evalúa se llama literalmente "Panel on Food Additives, Flavourings,
    Processing Aids and Materials in Contact with Food (AFC)" -- la
    frase aparece por el nombre del comité, no porque el dictamen sea
    una reevaluación de aditivo. Verificado que exigir ambas frases a la
    vez no captura ninguno de esos falsos positivos.
  - Tests de regresión en `tests/test_openfoodtox_joins.py`: propil
    galato (bloquea que vuelva a colarse un candidato de dominio ajeno)
    y plata (bloquea que el fix se vuelva demasiado estricto y excluya
    un follow-up real mal etiquetado).
  - **Resuelto en la misma sesión (16-ago-2026):** el mismo problema de
    fondo (dictámenes reales etiquetados `Domain.FoodDomain == 'other:'`)
    afectaba también a `reevaluation_dossiers()`/`unique_reevaluation_opinions()`
    -- el filtro del CORPUS, no solo la elección de "vigente" por
    sustancia. Se extrajo la lógica de rescate a una función compartida
    (`_is_mistagged_food_additive_reevaluation`, usada por ambas
    funciones) para no repetir la divergencia que ya se había dado una
    vez. **18 dictámenes de reevaluación de aditivos alimentarios
    reales** (acesulfamo K E950, sacarina E954, eritritol E968, neotamo
    E961, plata E174 y 13 más) estaban excluidos del corpus por este
    motivo -- **corpus corregido: 118 → 136**, validado contra el xlsx
    completo sin falsos positivos de otros dominios (verificado
    especialmente contra los 1.360 dictámenes de `flavourings` que ya
    habían dado problemas antes). Cifra actualizada en todo el
    documento, en `PROGRESS.md`, `docs/efsa-rag-proyecto.html` y el
    umbral del test de regresión del corpus.
  - **IMPORTANTE -- unificar NO significa exigir el mismo predicado
    completo en los dos sitios.** Se probó exigir también
    `REEVAL_TITLE_MARKER` en la rama de dominio correcto de
    `current_reference_value_opinion` (para unificarla del todo con
    `reevaluation_dossiers()`) y se descartó: rompía el caso del dióxido
    de titanio (E 171) -- el dictamen que de hecho concluyó que ya no es
    seguro como aditivo (2021-03-25, "Safety assessment of titanium
    dioxide (E171) as a food additive", dominio correcto) no contiene la
    palabra "re-evaluation", así que exigirla habría hecho perder ese
    dictamen a favor de uno de 2016 ya superado. Lo compartido entre las
    dos funciones es solo el rescate de mal-etiquetado, no el predicado
    completo -- ver el comentario largo en `ingestion/openfoodtox.py`
    antes de intentar unificar más.
- **No hay campo estructural de "vigente/superseded"** en ningún sitio del
  esquema. El heurístico de fecha+tipo es una aproximación razonable, no
  una garantía — puede fallar si hay dos 'EFSA opinion' del mismo tipo con
  fechas muy próximas sin que el título aclare cuál sustituye a cuál. La
  detección de esa ambigüedad (para decidir cuándo caer a un fallback de
  LLM sobre el texto del PDF) está marcada como TODO en
  `verify_currency_node`, no implementada todavía.
- **Existe un servidor MCP público** (`mcp-openfoodtox`) que ya expone
  OpenFoodTox por MCP, sobre un dataset desactualizado (2023). La
  diferenciación de este proyecto NO puede ser "expongo OpenFoodTox por
  MCP" — tiene que ser el razonamiento LangGraph orquestado (en particular
  el Nodo 3), que ese servidor no hace.
- **`HumanHealthHazardCharacteristics.OtherReferenceValues.ReferenceToEFSAOpinion`
  (FLEX_SUM.ToxRefValues) NO es un enlace fiable al dossier de origen,
  pese a lo que sugiere el nombre.** Apunta en teoría al UUID del
  dossier que originó el valor de referencia -- un atajo directo que
  ahorraría el join `DOCUMENT UUID → DOSSIER_DOCS → DOSSIER UUID` que
  usa `current_reference_value_opinion`. Vacío en los 5 registros de ADI
  de aspartamo verificados en el diseño original. Comprobado en sesión
  (16-ago-2026) que no fue mala suerte con aspartamo: **solo 8,3% de las
  filas de `FLEX_SUM.ToxRefValues` con `adi_value` no nulo lo tienen
  poblado (84/1007)** -- genuinamente disperso, no una excepción del
  caso de prueba. **No lo uses como enlace principal ni como fallback
  primario.** El enlace fiable sigue siendo el que ya usa
  `current_reference_value_opinion`: `Document UUID` (del registro de
  ADI) → `DOSSIER_DOCS` → `DOSSIER UUID` → `DOSSIER`.
- **`HumanHealthHazardCharacteristics.AcceptableDailyIntake.CriticalEndpoint`
  (FLEX_SUM.ToxRefValues) NO contiene el efecto crítico, pese al nombre.**
  Mismo patrón de fondo que con `ReferenceToEFSAOpinion` arriba: un campo
  bien poblado no garantiza que contenga lo que su nombre sugiere —
  verifica el contenido real antes de usarlo, no solo la tasa de
  relleno.
  Investigado y descartado como fuente de `adi_justification` (sesión
  16-ago-2026):
  - Es un `Reference field` / `Link to document (single)` a
    `ENDPOINT_STUDY_RECORD` (confirmado en la hoja `DATA_DICTIONARY`),
    no texto ni categoría — un UUID que apunta a otro registro en
    `END_STUDY_REC.HumanHealth`.
  - Poblado en el 86,9% de las filas de `FLEX_SUM.ToxRefValues` con
    `adi_value` no nulo (875/1007) — mejor tasa que
    `JustificationAndComments` (50%, 504/1007) — pero vacío en las 5
    filas del caso aspartamo.
  - El UUID resuelve al 100% contra `END_STUDY_REC.HumanHealth`, pero
    los subcampos que sí describirían el efecto real
    (`TargetSystemOrganToxicity.Organ`,
    `TargetSystemOrganToxicity.CriticalEffectsObserved`) están vacíos en
    >97% de esos registros resueltos (2,5% y 1,0% de relleno
    respectivamente). Lo único consistentemente poblado es
    `AdministrativeData.Endpoint` (100%, una categoría genérica de tipo
    de estudio, ej. "chronic toxicity: other route") y la especie
    (97,9%) — no el efecto crítico en sí.
  - `Document UUID` no es clave única en `END_STUDY_REC.HumanHealth`:
    los 875 UUIDs de `CriticalEndpoint` resuelven a 1.862 filas (~2,1
    filas por UUID), así que integrarlo exigiría además resolver esa
    ambigüedad de clave.
  - **Conclusión: `JustificationAndComments` sigue siendo el mejor
    candidato disponible para `adi_justification`** pese a su menor
    tasa de relleno (50%) — porque cuando está poblado es texto
    descriptivo real (ver caso aspartamo en `ingestion/openfoodtox.py`),
    no una categoría genérica. No reabrir esto sin nueva evidencia.
- **`END_SUM.Discussion.Discussion` -- enlace, tasa de relleno real y
  heurístico de boilerplate (investigado sesión 16-ago-2026, ver
  también "Estado del código" para las cifras corregidas de
  cobertura):**
  - Enlace: mismo patrón que `current_reference_value_opinion` --
    `END_SUM.Document UUID` → `DOSSIER_DOCS` (con `DOCUMENT TYPE ==
    'ENDPOINT_SUMMARY'`, no `'FLEXIBLE_SUMMARY'`) → `DOSSIER UUID` →
    `DOSSIER`. Resuelve al 100%. Cada dictamen de reevaluación enlaza
    típicamente a ~2 filas de `END_SUM`
    (`Carcinogenicity_EU_PPP` + `GeneticToxicity`, a veces también
    `Toxicokinetics`).
  - Longitud: siempre un párrafo corto cuando existe (media 321
    caracteres / ~51 palabras, máximo 954 caracteres / ~157 palabras --
    recalculado sobre el corpus corregido de 136 dictámenes, cifra
    anterior de 336/54 sobre los 118 pre-fix ligeramente desactualizada,
    el máximo no cambia) -- cabe entero en el prompt del Nodo 4, no hace
    falta chunking para este campo concreto.
  - **Heurístico de boilerplate validado sin excepciones encontradas:**
    `len(texto) < 280` caracteres **O** el texto es un duplicado exacto
    del mismo `Discussion.Discussion` en ≥2 `DOSSIER UUID` distintos
    (calculado dinámicamente sobre los datos, no una lista hardcodeada
    de strings). Un prefijo textual (p.ej. "Following a request from
    the European Commission") NO sirve como heurístico -- ese prefijo
    aparece tanto en boilerplate puro (209 car.) como en discusión
    sustantiva (932-954 car.). Tampoco basta un umbral de longitud
    simple más alto: existe un párrafo administrativo sobre el
    Reglamento 257/2010 que se repite literalmente en 9 dossiers
    distintos con 518-703 caracteres -- más largo que cualquier umbral
    razonable, y aun así puro boilerplate; solo la detección de
    duplicado cross-dossier lo captura.
  - **Zona gris sin señal limpia (280-650+ caracteres, no cubierta por
    el heurístico):** ni la longitud ni un listado de palabras clave
    (`concluded`/`considered`/`noted`/`agreed`, probado y descartado
    por dar falsos positivos) separan de forma fiable la discusión de
    incertidumbre real de la descripción regulatoria genérica dentro
    de este rango. Ejemplo: el texto de polisorbatos (E 432-E436, 621
    car.) no es boilerplate según el heurístico, pero tampoco contiene
    razonamiento del panel -- solo enumera qué sustancias cubre el
    dictamen. Frente a esto, ejemplos reales SÍ sustantivos en ese
    mismo rango de longitud: octyl gallate (E 311, 595 car.) y ácido
    ascórbico (E 300-302, 636 car.) sí incluyen razonamiento real del
    panel ("was not provided with a newly submitted dossier... noted
    that not all original studies... were available").

## Decisiones de arquitectura ya tomadas (no las reabras sin motivo nuevo)

- **Separación estructurado/narrativo:** OpenFoodTox (xlsx) para todo lo
  cuantificable (ADI/TDI/NOAEL, fechas, DOIs) vía queries deterministas,
  sin LLM. PDFs + RAG solo para el contenido narrativo (discusión de
  incertidumbre, razonamiento del panel) que no está en campos
  estructurados.
- **Cliente LLM intercambiable** (`graph/llm_client.py`): interfaz
  `LLMClient` con `DeepSeekClient` (producción, modelo
  `deepseek-v4-flash`) y `OllamaClient` (alternativa local opcional,
  coste cero, calidad menor — no es el backend por defecto). Selección
  vía `EFSA_RAG_LLM_BACKEND` en el entorno. No acoples los nodos del
  grafo a un proveedor concreto.
- **Modo "thinking" de DeepSeek V4 desactivado explícitamente**
  (`DeepSeekClient.complete()`, `extra_body={"thinking": {"type":
  "disabled"}}`): DeepSeek V4 lo activa por defecto con esfuerzo "high".
  Verificado en sesión (16-ago-2026, caso aspartamo/Nodo 4): con
  "thinking" activo, `reasoning_content` consume presupuesto del mismo
  `max_tokens` que el texto final -- en una prueba real se gastaron 799
  de 800 tokens en razonamiento, dejando la respuesta truncada/vacía. Y
  con "thinking" activo, `temperature` se ignora silenciosamente (no
  hace nada, ni siquiera con `temperature=0.0`). Desactivarlo restaura
  el comportamiento determinista esperado y evita el riesgo de
  truncamiento con el `max_tokens=800` por defecto. **No lo reactives
  sin volver a medir coste y truncamiento** -- si en el futuro se
  necesita razonamiento explícito para algún nodo, hazlo opt-in por
  nodo, no como default global del cliente.
- **Despliegue — Opción A, índice horneado:** el índice de Chroma se
  construye en local y se empaqueta como parte del repo/imagen de
  despliegue (read-only en producción), no se reindexa en caliente desde
  la demo pública. El botón de refresco en la UI comprueba novedades y
  avisa, no reindexa en producción. Redeploy manual tras reindexar en
  local. Motivo: el hosting gratuito (HF Spaces / Streamlit Community
  Cloud) tiene almacenamiento efímero — un índice construido en caliente
  se puede perder en un reinicio de contenedor.
- **Candado de refresco de 24h** (`ui/app.py`, `LOCK_FILE`): protege
  cómputo del hosting, NO presupuesto de API (el botón no llama al LLM).
  Es un archivo server-side, no session_state — compartido por todos los
  usuarios del día, no por sesión de navegador.
- **Límites de consulta** (`ui/app.py`, `check_and_register_query`): dos
  capas independientes — límite GLOBAL diario en USD estimados (la
  protección real de presupuesto, infalible porque es server-side) y
  límite por IP (mejora de UX, NO es protección real: usa una API interna
  no estable de Streamlit y las IPs se comparten/cambian con facilidad).
  No confundas una capa con la otra al documentar o modificar esto.
- **Precio LLM de referencia (ajustar si cambia):** DeepSeek V4-Flash,
  ~$0.001-0.002 por consulta según franja horaria (precios actualizados
  16-ago-2026 con tarifas punta/valle). Presupuesto de referencia:
  6-7€/mes cubre miles de consultas incluso en el peor caso. Se evaluó
  Kimi K2.6/K3 como alternativa: K2.6 es más caro que DeepSeek y con peor
  puntuación en benchmarks generales; K3 iguala casi a modelos de
  frontera pero a 15-20x el coste. Se mantiene DeepSeek por defecto.
  **Antes de cambiar de proveedor por benchmarks genéricos**, construir
  un set de 10-15 casos de prueba del Nodo 4 (con las reglas de
  comunicación de riesgo) y medir tasa de cumplimiento real, no decidir
  por índices de inteligencia genéricos que no miden eso.
  **Esta estimación de coste asume "thinking" desactivado** (ver bullet
  de arriba). Medido en sesión con el mismo prompt del Nodo 4: 799
  tokens de salida con "thinking" activo (esfuerzo "high", casi todo
  `reasoning_content`) frente a 365 con "thinking" desactivado -- un
  desplegado con el default de DeepSeek sin darse cuenta habría corrido
  con un coste real ~2-3x el estimado aquí, no por un cambio de precio
  del proveedor sino por un parámetro de la llamada.

## Estado del código (a fecha de este documento)

Implementado y con lógica real (no placeholder):
- `ingestion/openfoodtox.py` — cadena de joins completa, incluyendo ADI
  (`adi_value` + `adi_unit`) y justificación (`adi_justification`)
  ligados al registro de `FLEX_SUM.ToxRefValues` del dossier vigente
  concreto, no a cualquier ADI de la sustancia. **Validado contra el
  xlsx real** (`data/raw/OFT3_0_export_repository.xlsx`, sesión
  16-ago-2026): caso aspartamo da ADI = 40 mg/kg bw/day, fecha
  2013-11-28, tipo 'EFSA opinion' — coincide con el valor conocido.
  - **Bug corregido en esta sesión, no antes:** las cuatro cargas de
    hoja (`dossier`, `dossier_docs`, `sub`, `flex_sum_toxref`) usaban
    `pd.read_excel(..., header=1)`. La cabecera real está en la
    primera fila de cada hoja (verificado con `openpyxl`,
    `min_row=1`), no en la segunda — con `header=1`, pandas se saltaba
    la cabecera real y usaba la primera fila de datos (UUIDs, números)
    como nombres de columna, lo que rompía cualquier acceso por
    nombre. Corregido a `header=0` en las cuatro hojas.
  - Hallazgo relacionado, también de esta sesión:
    `LiteratureReference.DateOfEvaluation` llega de pandas como `str`
    `'YYYY-MM-DD'` (celda de Excel formateada como texto), no como
    `date`/`Timestamp` — `current_reference_value_opinion` ahora lo
    parsea con `_parse_iso_date()` antes de construir
    `OpinionReference` para cumplir su tipo `date | None`.
- `graph/llm_client.py` — interfaz `LLMClient` + `DeepSeekClient`
  (con "thinking" explícitamente desactivado, ver "Decisiones de
  arquitectura ya tomadas") + `OllamaClient`.
- `graph/nodes.py` — Nodo 1 (extracción con LLM), Nodo 3 (determinista)
  y Nodo 4 (generación) implementados. Nodo 4 conecta
  `deps.llm_client.complete(...)` con system prompt =
  `NODE_4_GROUNDING_RULES` + `NODE_4_SAFETY_COMMUNICATION_RULES`;
  probado con llamada real a la API (caso aspartamo) cumpliendo las
  reglas de comunicación de riesgo. Nodo 2 (retrieval híbrido) sigue
  siendo un contrato con `NotImplementedError` — bloqueado por no
  existir todavía el vector store (ver pendiente 4-5 abajo). El Nodo 4
  está diseñado para degradar con gracia con `retrieved_chunks` vacío
  mientras tanto, pero no se ha probado con fragmentos narrativos
  reales.
- `ui/app.py` — candado de refresco + límites de consulta, funcional.
- `tests/test_openfoodtox_joins.py` — test de regresión del caso
  aspartamo + test de columnas de ADI, **pasan los 3 contra el xlsx
  real** (antes se saltaban por no haber xlsx en `data/raw/`).

Pendiente, en orden de menor a mayor incertidumbre:
1. QA del corpus de 136 dictámenes contra las calls for data activas
   conocidas (ribonucleótidos E626-635, ácido glucónico E574-579,
   aditivos en forma gaseosa).
2. Resolver la limitación conocida del Nodo 1: `substance_uuid_by_name`
   exige coincidencia exacta del nombre químico canónico en inglés — no
   maneja español ("aspartamo") ni E-numbers ("E 951") todavía. Falta
   verificar si `SUB` tiene un campo de E-number consultable antes de
   implementar un fallback.
3. **Integrar `END_SUM.Discussion.Discussion` en `OpinionReference`**,
   con el heurístico de detección de boilerplate ya validado en datos
   (ver "Hallazgos verificados": `len < 280` caracteres O duplicado
   exacto entre ≥2 dossiers distintos → boilerplate). **Prioridad
   movida por delante de la descarga de PDFs y el pipeline de
   chunking/embeddings/Chroma** (antes puntos 3-4, ver nota más abajo).
4. Descarga de los PDFs de los 136 dictámenes.
5. Pipeline de chunking + embeddings locales (`sentence-transformers`) +
   Chroma — esto desbloquea el Nodo 2 (retrieval híbrido).
6. Detección de ambigüedad en el Nodo 3 (ver "Hallazgos verificados").
7. Servidor MCP (`mcp/`, carpeta vacía todavía).
8. Deploy siguiendo la Opción A descrita arriba.

**Por qué el punto 3 pasa por delante de PDFs/chunking/Chroma:**
`Discussion.Discussion` (hoja `END_SUM`, enlace verificado con el mismo
patrón `Document UUID → DOSSIER_DOCS → DOSSIER` que ya usa
`current_reference_value_opinion`) es un párrafo corto (máx. ~157
palabras) que cabe entero en `OpinionReference`/el prompt del Nodo 4 sin
chunking ni vector store, y no depende de nada del pipeline de PDFs.
**Corrección (16-ago-2026): la cifra de cobertura real es 29,4%, no el
81% estimado en una medición anterior de esta misma sesión** -- ese 81%
usaba un detector de boilerplate demasiado estrecho (solo el prefijo
literal "Following a request from..." + `len < 320`), que no capturaba
variantes de la misma frase de mandato con otra redacción ni el párrafo
administrativo sobre el Reglamento 257/2010 que se repite igual en 9
dossiers distintos. Recalculada dos veces: primero sobre el corpus de
118 (pre-fix de dominio) dio 32,2% (38/118); **recalculada de nuevo
sobre el corpus corregido de 136 da 29,4% (40/136)** -- los 18 dossiers
rescatados por el fix de dominio aportan sobre todo boilerplate (14 de
18 caen en "toda la discusión es boilerplate"), así que el porcentaje
baja un poco al ampliar el corpus, aunque el número absoluto de
dossiers con contenido no-boilerplate sube (38→40). Cifra vigente,
sobre los 136 dictámenes de reevaluación:

| Categoría | Dossiers |
|---|---|
| Sin ninguna fila de `Discussion` en `END_SUM` | 9 (6,6%) |
| Con discusión, pero TODAS las filas son boilerplate | 87 (64,0%) |
| Con al menos una fila NO marcada como boilerplate | **40 (29,4%)** |

**Ese 29,4% es "no probado como boilerplate", no "confirmado como
razonamiento científico sustantivo"** -- no lo trates como si lo fuera.
Ni la longitud ni un listado de palabras clave (`concluded`,
`considered`, `noted`, etc. -- probado y descartado, da falsos
positivos) separan de forma fiable, dentro de esa franja, la discusión
de incertidumbre real de la descripción regulatoria genérica. Ejemplo
de zona gris: el texto de polisorbatos (E 432-E436, 621 caracteres) no
es boilerplate según el heurístico (no es corto, no está duplicado
cross-dossier), pero tampoco contiene razonamiento del panel -- solo
lista qué sustancias cubre el dictamen y que "Polysorbates (E 432-E 436)
are authorised as food additives in the European Union (EU)". Esta
imprecisión residual es una limitación conocida del campo, no un bug a
resolver antes de integrarlo -- documentar en LIMITATIONS.md cuando se
implemente, no ocultarla.

Con esa salvedad, el 29,4% (o el subconjunto de ese 29,4% que resulte
genuinamente sustantivo) sigue siendo contenido narrativo real -- no
solo metadatos de citación -- sin depender de nada del pipeline de
PDFs. Esto permite un Nodo 4 con algo de contenido narrativo genuino
(no solo ADI + cita) mucho antes de tener PDFs descargados o Chroma
montado, aunque a menor escala de lo que se pensó inicialmente. El
pipeline de PDFs + RAG completo (puntos 4-5) sigue siendo necesario
para preguntas que requieran más profundidad de la que cabe en ese
párrafo -- y ahora también para el 70,6% de dossiers donde
`Discussion.Discussion` no aporta nada -- pero no es bloqueante para
tener una demo funcional con algo de contenido narrativo real.

(Investigado y descartado: `CriticalEndpoint` como fuente de efecto
crítico estructurado — ver "Hallazgos verificados". No es una tarea
pendiente, es una decisión ya tomada.)

## Mantenimiento de PROGRESS.md

Mantén un archivo `PROGRESS.md` en la raíz del repo, editándolo (no
recreándolo) a medida que avances. Formato: una entrada por sesión de
trabajo, con fecha, qué se implementó/decidió, y qué quedó pendiente o
sin resolver. Sé tan honesto ahí como este documento lo es contigo:
si algo quedó a medias, dilo explícitamente, no lo des por hecho.
