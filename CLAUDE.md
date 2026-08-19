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
  (ej. iterar los 162 dictámenes, reintentos, pruebas de prompt) DEBE
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

## Hallazgos verificados (resumen — detalle completo en `docs/DECISIONES_VERIFICADAS.md`)

Cada punto de abajo es un resumen de 1-2 frases, en el mismo orden en que
aparece el hallazgo completo en `docs/DECISIONES_VERIFICADAS.md` (cifras
exactas, tablas, verificación contra las hojas reales, bloques de
corrección). No los redescubras ni los contradigas sin motivo — si algo
aquí te parece raro o incompleto, lee el detalle antes de asumir que es
un error.

- **Filtro de corpus:** dominio `food additives` + patrón de título de
  reevaluación (o rescate de dictámenes mal etiquetados con otro dominio)
  Y NOT regulación de pienso animal → **162 dictámenes únicos**
  (progresión 118→136→162, no repitas cifras antiguas como si fueran la
  actual). No uses `Domain.Regulation` como filtro principal.
- **Cobertura del corpus no está validada al 100%** contra una fuente
  oficial EFSA — trátalo como corpus de trabajo razonable, no como lista
  cerrada; el programa sigue activo en 2025-2026.
- **Cadena de joins para vigencia (Nodo 3):** `FLEX_SUM.ToxRefValues →
  DOSSIER_DOCS → DOSSIER`, filtrando `Type == 'EFSA opinion'` y tomando
  `MAX(fecha)`. Verificado con aspartamo (2013-11-28, correcto).
  `DOSSIER.Parent UUID` está vacío al 100% — no la uses para vigencia.
- **`current_reference_value_opinion` necesita filtrar también por
  dominio**, no solo por tipo de dictamen: sin ese filtro, un dictamen de
  otro programa regulatorio (pienso animal, aromas, contaminantes) puede
  ganar el `MAX(fecha)` — afecta a 29/102 sustancias (28,4%). Filtro
  correcto: dominio == `food additives` O (título con "food additive" Y
  "re-evaluation") — ni el dominio solo ni la frase de título sola
  bastan por separado (cada uno pierde o gana casos reales verificados).
- **Divergencia TiO2 investigada a fondo:** 7/233 sustancias (3,0%)
  tienen su dictamen realmente vigente fuera de `reevaluation_dossiers()`.
  Grupo A (6 sustancias, solo cobertura, dato correcto) — CERRADO,
  corpus 136→162. Grupo B (Sunset Yellow FCF, bug real: un dictamen de
  pienso animal desplazaba al alimentario) — CERRADO. Se probó y
  descartó un enfoque "híbrido puro" (sustancia-primero, sin patrón de
  título); se adoptó un "híbrido estrecho" para
  `current_reevaluation_corpus()` (sustituye, no une — 162→162).
- **No hay campo estructural de "vigente/superseded"** en el esquema —
  el heurístico de fecha+tipo es una aproximación, no una garantía. La
  detección de ambigüedad quedó DIFERIDA explícitamente (0/247 sustancias
  ambiguas a 90 días en el corpus actual, evidencia de prevalencia, no
  omisión).
- **Existe un servidor MCP público** (`mcp-openfoodtox`) sobre un dataset
  desactualizado (2023) — la diferenciación de este proyecto es el
  razonamiento LangGraph orquestado (Nodo 3), no exponer OpenFoodTox por
  MCP sin más.
- **`OtherReferenceValues.ReferenceToEFSAOpinion` NO es un enlace fiable**
  al dossier de origen pese al nombre — solo 8,3% de las filas con ADI lo
  tienen poblado. No lo uses como enlace principal ni como fallback.
- **`AcceptableDailyIntake.CriticalEndpoint` NO contiene el efecto
  crítico** pese al nombre — es un UUID a `END_STUDY_REC.HumanHealth`
  cuyos subcampos relevantes están vacíos en >97% de los casos resueltos.
  `JustificationAndComments` sigue siendo la mejor fuente disponible para
  `adi_justification`, pese a su 50% de tasa de relleno.
- **`END_SUM.Discussion.Discussion`:** párrafo corto cuando existe (media
  321 caracteres, máx. 954), enlace resuelto al 100%, cabe entero en el
  prompt del Nodo 4. Heurístico de boilerplate validado: `len < 280`
  caracteres O duplicado exacto entre ≥2 dossiers. Zona gris 280-650+
  caracteres sin señal limpia — ni longitud ni palabras clave separan de
  forma fiable discusión real de descripción regulatoria genérica ahí.
- **Wiley bloqueado por Cloudflare** (403 + challenge JS) para descarga
  directa de PDFs — verificado que no es un fallo de script; ningún
  cliente HTTP simple (`requests`/`curl`) puede resolver el challenge.
- **`efsa.europa.eu` es solo un alias que redirige a Wiley** (mismo
  bloqueo Cloudflare) — no es una fuente independiente para PDFs.
- **PubMed Central (PMC) es parcialmente viable pero no fiable sin
  verificación:** falsos positivos al buscar PMCID por DOI (solo 2/5
  correctos), necesita `curl` en vez de `requests` (fingerprinting
  TLS/HTTP), y bloqueos intermitentes tipo reCAPTCHA incluso cuando el
  resto funciona.
- **DECISIÓN: descarga MANUAL de PDFs vía navegador normal**, no
  automatizada — ninguna de las 3 fuentes probadas (Wiley, efsa.europa.eu,
  PMC) permite descarga automatizada fiable. Checklist generado por
  `scripts/generate_pdf_checklist.py` (161 PDFs únicos, no 162 — hay un
  duplicado real por errata de título en el caso de sacarina).
- **Licencia real de los 161 PDFs NO es uniforme, varía por fecha:**
  79/161 (2007-2016) sin ninguna licencia abierta (solo copyright EFSA
  restrictivo); 82/161 (2016-2025) CC BY-ND (pensada para el artículo
  completo sin cambios, no para fragmentos). Decisión tomada por el
  usuario: `data/chroma/` se queda en `.gitignore`, nunca va al repo
  público de GitHub — sí se empaqueta en el artefacto de despliegue.
- **Estructura real de los PDFs** (verificada abriendo 3 documentos
  completos): los "Statement" cortos tienen estructura mínima estable;
  los "Scientific Opinion" largos tienen jerarquía de encabezados
  numerados hasta 4 niveles; las tablas de exposición dietética se
  rompen mal con extracción de texto plano (`pdftotext`).
- **PyMuPDFLoader elegido sobre PyPDFLoader** con evidencia medida, no
  teórica: 0 vs 402 palabras rotas por ligaduras tipográficas, ~8x más
  rápido en el documento largo de prueba (156 páginas). Ninguno de los
  dos reconstruye tablas como tablas.
- **DECISIÓN: Opción A para tablas — detectarlas y excluirlas del texto
  narrativo troceado**, no extraerlas aparte (`pdfplumber` probado y
  descartado: fragmenta y pierde columnas sin avisar) ni aceptar la
  fragmentación sin más. La conclusión clave de una tabla suele estar ya
  en prosa en el Abstract. Limitación aceptada explícitamente: se pierde
  el desglose fino por subgrupo poblacional de exposición.
- **DECISIÓN: splitter plano (`RecursiveCharacterTextSplitter`) para los
  límites de chunk + `section_heading` como metadato aparte**, extraído
  vía tamaño/familia tipográfica con la API rica de PyMuPDF
  (`get_text("dict")`) — un regex sobre texto plano da demasiado ruido
  (725+ falsos positivos en el documento de prueba) y `PyMuPDFLoader` no
  expone la fuente necesaria para esta señal.
- **Chunker implementado (`ingestion/pdf_chunking.py`) y validado sobre
  el corpus completo de 161 PDFs.** Dos hallazgos de calidad de texto:
  guiones suaves (`\xad`) corrompiendo el texto — arreglados de forma
  genérica (afecta a 10/161 PDFs, plantilla Wiley 2023-2025); título
  largo partido en dos bloques bold — limitación cosmética de baja
  prioridad, documentada y NO arreglada a propósito (sin pérdida de
  datos, solo afecta la etiqueta `section_heading` de un puñado de
  chunks).
- **Mapeo sustancia→archivo para PDFs multi-E-number y bug de
  deduplicación por título:** al menos 36/161 PDFs (22%) cubren más de
  una sustancia sin que ninguna columna del checklist lo refleje solo;
  20/162 títulos del corpus (12%) son genuinamente multi-sustancia, con
  46 sustancias con ADI propio invisibles si solo se mira la fila
  superviviente del dedup. Extraído como
  `OpenFoodToxStore.substances_per_dossier()`, con resolución de
  sustancia en 3 niveles (con ADI / mismo enlace sin ADI / heurístico de
  nombre en título — `resolve_dossier_substances` en
  `ingestion/pdf_chunking.py`) que cubre 161/162 dossiers. Esquema de
  metadatos de Chroma implementado sin `e_number` (sin fuente fiable a
  nivel de sustancia, solo por dossier) — `substance_uuid` +
  `chemical_name` son el identificador fiable por chunk, con "N copias
  por chunk" para chunks que sirven a varias sustancias.
- **CONSUMO DE MEMORIA MEDIDO -- BLOQUEA el deploy en el tier gratuito
  de Streamlit Community Cloud tal como está hoy (sesión 18-ago-2026):**
  el proceso completo (Streamlit + Chroma con los 67.827 chunks +
  modelo de embeddings + una consulta real de extremo a extremo) usa
  **~1.870 MB de RAM**, casi el doble del límite de 1 GB del tier
  gratuito (confirmado por fuentes externas actuales, no asumido). El
  salto más grande (~410 MB) es el "warm-up" de PyTorch en su primera
  inferencia real, no algo proporcional al tamaño del corpus. Detalle
  completo del desglose (qué componente aporta cuánto, y las opciones
  de mitigación NO implementadas todavía) en
  `docs/DECISIONES_VERIFICADAS.md`.

## Decisiones de arquitectura (resumen — detalle completo en `docs/DECISIONES_VERIFICADAS.md`)

Cada punto de abajo es un resumen de una frase por decisión, en el mismo
orden en que aparece el razonamiento completo en
`docs/DECISIONES_VERIFICADAS.md` (alternativas evaluadas y descartadas,
cifras de calibración, verificación con llamadas reales). No las
reabras sin motivo nuevo — si algo aquí te parece mejorable, lee el
detalle antes de asumir que es un error.

- **Separación estructurado/narrativo:** OpenFoodTox (xlsx) para todo
  lo cuantificable (ADI/TDI, fechas, DOIs) vía queries deterministas
  sin LLM; PDFs + RAG solo para el contenido narrativo que no está en
  campos estructurados.
- **Cliente LLM intercambiable** (`graph/llm_client.py`): interfaz
  `LLMClient` con `DeepSeekClient` (producción) y `OllamaClient`
  (alternativa local) — no acoples los nodos del grafo a un proveedor
  concreto.
- **Modo "thinking" de DeepSeek V4 desactivado explícitamente**
  (`extra_body={"thinking": {"type": "disabled"}}`): con thinking
  activo, `reasoning_content` consume el mismo presupuesto de
  `max_tokens` que el texto final (verificado: 799/800 tokens
  gastados en razonamiento, respuesta truncada) y `temperature` se
  ignora — no lo reactives sin volver a medir coste y truncamiento.
- **Despliegue — Opción A, índice horneado:** el índice de Chroma se
  construye en local y se empaqueta en el artefacto de despliegue
  (read-only en producción, no se reindexa en caliente); los datos
  pesados (xlsx + Chroma) SÍ van al artefacto de deploy pero NUNCA al
  repo público de GitHub (licencia de los PDFs no lo permite, ni
  siquiera vía Git LFS) — se descargan en el arranque desde MEGA S4
  (`deploy_assets.py::ensure_deploy_assets_downloaded()`).
- **Candado de refresco de 24h** (`ui/app.py`, `LOCK_FILE`): protege
  cómputo del hosting, no presupuesto de API — archivo server-side,
  compartido por todos los usuarios del día.
- **Límites de consulta** (`check_and_register_query`): dos capas
  independientes — límite GLOBAL diario en USD estimados (protección
  real de presupuesto) y límite por IP (solo mejora de UX, NO
  protección real).
- **`data/usage_log.json` NO va en git**, igual que
  `data/last_update_check.txt`: es un contador runtime que se
  autorreinicia por fecha — comitear un snapshot es activamente
  engañoso, no solo redundante.
- **Precio LLM de referencia:** DeepSeek V4-Flash, ~$0,0008-0,0020 por
  consulta según franja horaria (verificado contra la tarifa oficial
  vigente) — presupuesto de 6-7€/mes cubre miles de consultas;
  reajustar si cambia el proveedor o el precio.
- **Modelo de embeddings:** `sentence-transformers/all-MiniLM-L6-v2`
  (384 dims, local) — corpus completo indexado (67.827 chunks) y
  verificado con consultas temáticas reales, no solo con una prueba
  puntual.
- **Backend de embeddings: ONNX + pesos int8, no `torch` puro** —
  decisión de memoria para el deploy (evita el "warm-up" de PyTorch,
  ~400 MB, en la primera inferencia). Único punto de la base de código
  que debe instanciar `SentenceTransformer`:
  `ingestion/embedding_model.py::load_embedding_model()` — no
  instanciarlo directamente en ningún otro sitio.
- **Contrato Nodo 2 → Nodo 4:** `retrieved_chunks: list[RetrievedChunk]`
  (dataclass con metadatos — sustancia, dossier, tier de resolución),
  nunca `list[str]` — el Nodo 4 necesita saber la procedencia y
  fiabilidad de cada fragmento, no solo su texto.
- **Resolución multi-candidato del Nodo 1:**
  `GraphState.substance_candidates: list[SubstanceCandidate]` (nunca
  un único `substance_uuid`) — cuando varios nombres de
  `SUB.ChemicalName` son razonablemente parecidos a la sustancia
  mencionada (exacto → normalizado por guion/espacio → fuzzy
  restringido a las 246 sustancias resolubles del corpus), el sistema
  nunca elige uno en silencio: resuelve y presenta todos por separado.
- **Dos caminos de ejecución del grafo:** completo
  (`answer_question`, Nodo 1→2→3→4, usado por la herramienta MCP
  `search_efsa_opinion`, el único punto que genera prosa nueva y por
  tanto el único sujeto a `NODE_4_SAFETY_COMMUNICATION_RULES`) y
  parcial (`resolve_current_opinion`, Nodo 1+3 únicamente, usado por
  `get_reevaluation_status`) — saltarse el Nodo 4 en el camino parcial
  no compromete la restricción no negociable #1 porque no hay
  generación de lenguaje ahí, solo campos crudos de OpenFoodTox.
- **Esquema MCP: array de resultados siempre, nunca un objeto
  singular** (`search_efsa_opinion`/`get_reevaluation_status` →
  `{"candidates_found", "candidates_shown", "results": [...]}`) —
  misma disciplina de no elegir un candidato en silencio, llevada al
  contrato del servidor MCP; la honestidad ante la ambigüedad queda
  así estructural, no opcional para el cliente.

## Estado del código (resumen — detalle histórico completo en `docs/DECISIONES_VERIFICADAS.md`)

Lista compacta del estado actual, sin narrativa de sesión a sesión. El
histórico completo (bugs encontrados y corregidos, verificación con
llamadas reales, análisis de cada punto pendiente tal como se escribió
en su momento) vive en `docs/DECISIONES_VERIFICADAS.md`.

**Implementado y con lógica real (no placeholder):**
- `ingestion/openfoodtox.py` — cadena de joins completa para ADI/TDI,
  vigencia y resolución de sustancias (incluida
  `resolve_substance_candidates`, multi-candidato), validada contra
  el xlsx real de OpenFoodTox 3.0.
- `graph/llm_client.py` — `LLMClient` + `DeepSeekClient` (thinking
  desactivado) + `OllamaClient`.
- `graph/nodes.py` — los 4 nodos del grafo:
  - Nodo 1 (`extract_entity_node`) — extracción de sustancia vía LLM
    + resolución multi-candidato; probado con llamadas reales
    (inglés, español, E-numbers).
  - Nodo 2 (`hybrid_retrieval_node`) — retrieval híbrido sobre Chroma
    (67.827 chunks), con presupuesto de chunks repartido entre
    candidatos; probado con consultas reales.
  - Nodo 3 (`verify_currency_node`) — determinista, sin LLM.
  - Nodo 4 (`generate_answer_node`) — generación con las reglas de
    comunicación de riesgo del ADI; protegido contra truncamiento
    silencioso (reintento + aviso explícito si persiste); presenta
    2+ candidatos por separado sin fusionarlos.
- `graph/build.py` — grafo LangGraph ensamblado y compilado;
  `answer_question`/`resolve_current_opinion` como puntos de entrada
  (completo/parcial, ver "Decisiones de arquitectura"); `AnswerResult`
  expone `retrieved_chunks`/`structured_results`/`substance_candidates`
  para auditar fundamentación sin reproducir el retrieval a mano.
- `ui/app.py` — candado de refresco 24h + límites de consulta +
  conectado al grafo (import perezoso) + descarga de datos pesados
  desde MEGA S4 en el arranque + preguntas de ejemplo en español.
- `mcp/server.py` — dos herramientas (`search_efsa_opinion`,
  `get_reevaluation_status`), esquema de salida siempre array de
  resultados (ver "Decisiones de arquitectura").
- Pipeline de ingesta de PDFs completo: 161/161 PDFs descargados
  (checklist manual, `scripts/generate_pdf_checklist.py`),
  troceados (`ingestion/pdf_chunking.py`, resolución de sustancia en
  3 niveles) e indexados en Chroma (`ingestion/chroma_index.py`,
  backend ONNX int8) — 67.827 chunks persistidos.
- **Deploy real en Streamlit Community Cloud — funcionando en
  producción** (primer deploy exitoso, requirió tres optimizaciones
  de memoria + ajustes de configuración, ver README.md sección
  "Deploy" y `docs/DECISIONES_VERIFICADAS.md` para el proceso
  completo), verificado con consultas reales (aspartamo, tocoferol
  multi-candidato, TiO2, sustancia no encontrada).
- `tests/` — 48 tests (`test_openfoodtox_joins.py`,
  `test_nodes.py`, `test_mcp_server.py`), 2 se saltan sin
  `data/raw/*.xlsx`/`data/chroma/` reales en disco.

**Pendiente, en orden de menor a mayor incertidumbre:**
1. QA del corpus de 162 dictámenes contra las calls for data activas
   conocidas (ribonucleótidos E626-635, ácido glucónico E574-579,
   aditivos en forma gaseosa) — no iniciado.
2. Resolución de nombre del Nodo 1 sin garantía estructural en dos
   frentes: (a) español/E-numbers depende de que el LLM traduzca bien
   antes de resolver — no existe una tabla auxiliar E-number →
   `substance_uuid` (`SUB` no tiene campo de E-number consultable); (b)
   typo agresivo o nombre poco conocido dentro de una pregunta completa
   (caso "plai caramel" — el LLM responde `NONE` antes de que la
   resolución multi-candidato pueda intervenir), diagnosticado, sin
   arreglar a propósito; dirección propuesta (segunda pasada dirigida
   del Nodo 1) sin diseñar en detalle.
3. Detección de ambigüedad en el Nodo 3 (dos `'EFSA opinion'` con
   fechas próximas sin que el título aclare cuál sustituye a cuál) —
   **diferida explícitamente**, con evidencia de prevalencia: 0/247
   sustancias ambiguas a 90 días en el corpus actual. Re-evaluar si
   el corpus cambia (nuevos follow-ups) o aparece un caso real.
4. Servidor MCP sin verificar con un cliente MCP real (Claude Desktop
   u otro) — solo `server.call_tool()` invocado directamente en
   Python hasta ahora.
5. Nodo 4 sin test automatizado end-to-end con API real y
   `retrieved_chunks` no vacío (sí hay tests con stubs para el
   truncamiento, `test_generate_answer_node_*` en `test_nodes.py`) —
   ni tampoco hay ningún test automatizado de `ui/app.py`, solo
   verificación manual puntual con `streamlit.testing.v1.AppTest` en
   cada sesión que lo toca.
6. `FUZZY_MATCH_LOW_THRESHOLD = 60` (resolución multi-candidato)
   calibrado contra un puñado de casos reales conocidos (tocoferol,
   caramelo, E150a), no contra una batería exhaustiva — re-tunear si
   aparecen más casos reales de typo/nombre genérico en producción.
7. Memoria del proceso en producción no re-medida tras el deploy
   real — la medición aislada previa al deploy (~1.150-1.170 MB) sigue
   por encima del límite nominal de ~1 GB del tier gratuito, aunque el
   deploy real funciona pese a esa cifra (ver README.md).

## Mantenimiento de PROGRESS.md

Mantén un archivo `PROGRESS.md` en la raíz del repo, editándolo (no
recreándolo) a medida que avances. Formato: una entrada por sesión de
trabajo, con fecha, qué se implementó/decidió, y qué quedó pendiente o
sin resolver. Sé tan honesto ahí como este documento lo es contigo:
si algo quedó a medias, dilo explícitamente, no lo des por hecho.
