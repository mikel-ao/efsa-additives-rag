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
  - **Matiz añadido tras la investigación de licencia de los PDFs
    (sesión 17-ago-2026, ver "Hallazgos verificados"):** "empaquetado
    como parte del repo/imagen de despliegue" son dos destinos
    DISTINTOS, no lo mismo -- decisión tomada: el índice de Chroma
    (texto literal de los chunks, no solo embeddings) SÍ va en la
    imagen/artefacto de despliegue, pero NO en el repo público de
    GitHub (`data/chroma/` se queda en `.gitignore`). Motivo: casi la
    mitad del corpus (79/161, dictámenes 2007-2016) no tiene ninguna
    licencia abierta, solo la política de copyright propia de EFSA sin
    cobertura clara de redistribución pública; la otra mitad (CC BY-ND
    2016-2025) está pensada para el artículo completo sin cambios, no
    fragmentos. Si en el futuro se reabre esta decisión, hazlo con
    nueva evidencia de licencia, no por conveniencia de despliegue.
  - **Mecanismo concreto para Streamlit Community Cloud -- datos
    pesados del deploy vía MEGA S4, NUNCA en git (ni siquiera Git LFS
    en un repo privado), sesión 18-ago-2026 continuación 21.** A
    diferencia de un deploy Docker con imagen propia, Streamlit
    Community Cloud despliega DIRECTAMENTE desde un repo de git -- no
    hay un paso de "artefacto" separado del repo. La única forma de
    cumplir el matiz de arriba ("SÍ en el artefacto, NO en el repo
    público") sin meter los datos en ningún repo de GitHub es que la
    propia app los descargue en tiempo de arranque desde
    almacenamiento externo. Decisión del usuario: MEGA S4
    (almacenamiento de objetos S3-compatible, incluido en su plan MEGA
    Pro Lite) -- **NO Git LFS** (evaluado y descartado explícitamente
    por el usuario: aunque Git LFS "funciona" con Streamlit Community
    Cloud sin cambios de código, seguiría metiendo el texto con
    licencia restrictiva en el historial de git, que es justo lo que
    esta decisión prohíbe, repo privado o no).
    - `src/efsa_rag/deploy_assets.py::ensure_deploy_assets_downloaded()`
      -- descarga el xlsx y un tarball de `data/chroma/` vía boto3 SOLO
      si no están ya en disco (no toca la red en desarrollo local con
      los datos ya presentes, verificado). Credenciales/endpoint/bucket
      SIEMPRE por variable de entorno (`MEGA_S4_*`, ver
      `.env.example`), nunca hardcodeadas. Llamada desde
      `ui/app.py::_render_answer`, justo antes de tocar `graph.build`.
    - `scripts/upload_deploy_assets.py` -- script manual, un solo uso
      por sesión de reindexado, que el usuario ejecuta EN LOCAL con sus
      propias credenciales para poblar el bucket. No lo ejecuta Claude
      (no tiene ni debe pedir las credenciales reales).
    - Ver `README.md`, sección "Deploy en Streamlit Community Cloud",
      para los pasos completos, y `PROGRESS.md` continuación 21 para el
      detalle de la implementación y verificación.
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
- **`data/usage_log.json` NO va en git, igual que `data/last_update_check.txt`
  -- inconsistencia real corregida (sesión 19-ago-2026), no una
  hipótesis.** Ambos son el mismo tipo de archivo: contador de estado
  runtime, escrito por `ui/app.py`, que se autorreinicia según la fecha
  (`_load_usage()` descarta el contenido si `data.get("date") !=
  str(date.today())`). `last_update_check.txt` ya estaba en
  `.gitignore` desde el principio por este motivo; `usage_log.json` se
  había quedado trackeado con un valor fijo (`git ls-files` lo
  confirmaba), verificado ANTES de tocar nada -- no asumido por
  analogía. Comitear un snapshot de este archivo es activamente
  engañoso, no solo redundante: en producción (Streamlit Community
  Cloud, disco efímero -- ver "Opción A, índice horneado" más arriba)
  el valor comiteado se descarta en la primera consulta real del día de
  todos modos (el chequeo de fecha lo resetea), así que el número fijo
  en git nunca refleja el estado real de ningún entorno, ni local ni de
  producción -- solo genera diffs espurios cada vez que alguien corre
  la app en local (confirmado: dos verificaciones puntuales de UI en la
  misma sesión bastaron para ensuciar el archivo, sin tocar código).
  Sacado de git con `git rm --cached` (el archivo sigue en disco local,
  solo deja de trackearse) + añadido a `.gitignore` junto a
  `last_update_check.txt`.
- **Precio LLM de referencia (ajustar si cambia):** DeepSeek V4-Flash,
  **~$0.0008-0.0020 por consulta según franja horaria -- RECALCULADO
  Y CERRADO (sesión 18-ago-2026, continuación 15)** con la tarifa
  oficial vigente verificada directamente en
  `https://api-docs.deepseek.com/quick_start/pricing` (no una cifra
  heredada de una sesión anterior sin fuente citable, ver el motivo
  del recálculo más abajo): modelo `deepseek-v4-flash`, input cache-hit
  $0,007 (valle) / $0,014 (punta) por millón de tokens, input cache-miss
  $0,22 (valle) / $0,44 (punta), output $0,66 (valle) / $1,32 (punta) --
  "punta" = 01:00-04:00 y 06:00-10:00 UTC, "valle" el resto (tarifa
  valle = mitad de la de punta, confirmado en la propia página de
  pricing). Cálculo: input ~1.250-2.000 tokens (system prompt 575
  tokens medido + `retrieved_chunks`, k=3-5 chunks ~150-180
  tokens/chunk, mismo presupuesto ya medido en sesión anterior, sin
  cambios) + output **845 tokens (medido de verdad, no estimado --
  caso real Shellac, `finish_reason == 'stop'`, ver más abajo)**,
  asumiendo cache-miss en el input (cota conservadora; si el caché
  automático de DeepSeek para el system prompt repetido sí aplica en
  producción, el coste real baja un poco más, pero el efecto es
  pequeño porque el output domina el coste total -- ver el cálculo
  completo en `PROGRESS.md`, sesión 18-ago-2026 continuación 15).
  Rango resultante: ~$0,0008/consulta en valle, ~$0,0020/consulta en
  punta.
  - **Sustituye a la cifra anterior de $0,0005-0,0014/consulta**
    (basada en ~365 tokens de salida, de antes de subir
    `NODE_4_MAX_TOKENS` de 800 a 2000 -- ver el hallazgo de
    truncamiento del Nodo 4 resumido arriba) -- la nueva cifra es
    ~1,4-1,6x mayor, consistente con que el output real más que se
    dobló (365→845) pero el input no cambió y domina menos que el
    output en el total.
  - **El hardcoded `ESTIMATED_COST_PER_QUERY_USD = 0.002` en
    `ui/app.py` (candado de presupuesto real) SIGUE SIENDO VÁLIDO,
    verificado contra esta cifra, no solo asumido** -- cae justo en el
    extremo superior (punta) del rango recalculado, así que el candado
    de presupuesto real (`DAILY_HARD_COST_CEILING_USD = 0.35`) sigue
    protegiendo con el margen esperado en el caso normal. **Caveat
    real, no bloqueante:** ese hardcoded es un valor FIJO por consulta,
    y no distingue una consulta normal (~845 tokens de salida) de una
    que dispara el reintento por truncamiento (`NODE_4_RETRY_MAX_TOKENS
    = 3500`) -- el caso peor de reintento paga DOS llamadas completas
    (la truncada + el reintento), hasta ~5.500 tokens de salida en
    total entre ambas, ~$0,004-0,009/consulta -- 2-4,5x el hardcoded.
    Como el reintento solo se paga en el caso raro (la primera pasada
    ya se truncó), el promedio real debería seguir cerca del hardcoded
    salvo que las respuestas truncadas se vuelvan frecuentes -- no
    detectado como un problema real hoy, solo documentado para no
    asumir que el candado cubre ese caso con el mismo margen que el
    caso normal.
  - Presupuesto de referencia sin cambios en la conclusión: 6-7€/mes
    (`DAILY_HARD_COST_CEILING_USD = 0.35`/día × ~30 días) sigue
    cubriendo miles de consultas -- entre ~5.250/mes (todo en franja
    punta, cota inferior) y ~13.000/mes (todo en franja valle, cota
    superior) al nuevo coste por consulta, muy por encima de lo que un
    proyecto de portfolio necesita.
  - Se evaluó Kimi K2.6/K3 como alternativa: K2.6 es más caro que
    DeepSeek y con peor puntuación en benchmarks generales; K3 iguala
    casi a modelos de frontera pero a 15-20x el coste. Se mantiene
    DeepSeek por defecto. **Antes de cambiar de proveedor por
    benchmarks genéricos**, construir un set de 10-15 casos de prueba
    del Nodo 4 (con las reglas de comunicación de riesgo) y medir tasa
    de cumplimiento real, no decidir por índices de inteligencia
    genéricos que no miden eso.
  - **Esta estimación de coste asume "thinking" desactivado** (ver
    bullet de arriba). Medido en sesión con el mismo prompt del Nodo 4:
    799 tokens de salida con "thinking" activo (esfuerzo "high", casi
    todo `reasoning_content`) frente a 365 con "thinking" desactivado
    -- un desplegado con el default de DeepSeek sin darse cuenta habría
    corrido con un coste real notablemente mayor al estimado aquí, no
    por un cambio de precio del proveedor sino por un parámetro de la
    llamada.
- **Modelo de embeddings: `sentence-transformers/all-MiniLM-L6-v2`
  (384 dims, local) -- decidido y probado con datos reales (sesión
  18-ago-2026), no solo elegido por defecto teórico.**
  **ACTUALIZADO EN LA MISMA FECHA (sesión 18-ago-2026, más tarde): el
  backend de carga cambió de `torch` (por defecto) a ONNX + pesos int8
  cuantizados** -- decisión de memoria para el deploy, ver el bullet
  "Backend de embeddings: ONNX int8, no torch" más abajo para el
  razonamiento y las cifras. **Las cifras de esta entrada (597 MB en
  disco, 2,97 min de indexado, GPU) describen la corrida ORIGINAL con
  `torch` -- ya SUPERADA, el índice actual se reconstruyó con ONNX int8
  (718 MB en disco, ~22,4 min, CPU, ver el bullet de ONNX) -- no las
  repitas como si fueran las vigentes, se dejan aquí solo como
  registro de lo que se midió entonces.** Se descarga y
  carga sin problemas en el venv del proyecto (`sentence-transformers`
  ya en `requirements.txt`) -- 3,4-7,7 s de carga según si el modelo ya
  está en caché local.
  - **Entorno de esta sesión con GPU disponible** (`model.device` ->
    `cuda:0`). **ADVERTENCIA EXPLÍCITA PARA EL DESPLIEGUE, no lo des
    por descontado:** si se reconstruye el índice en un entorno sin GPU
    (ej. HF Spaces/Streamlit Cloud gratuito, ver la decisión de
    despliegue "Opción A" -- el índice de Chroma se construye en local
    y se empaqueta, no se reindexa en caliente en producción, pero
    "en local" puede seguir siendo un entorno sin GPU si el reindexado
    se hace desde otra máquina o CI) las cifras de abajo NO son
    representativas -- solo-CPU sería significativamente más lento, no
    medido en esta sesión. Volver a medir en el entorno real donde se
    reconstruya el índice antes de asumir minutos de reconstrucción
    similares a los de aquí. Esto importa en concreto para el flujo de
    "refresco" descrito en la decisión de despliegue: cada vez que se
    añadan dictámenes nuevos al corpus y haga falta reindexar antes de
    redeploy, el tiempo real dependerá de si esa reconstrucción corre
    con GPU o no.
  - **Lote de prueba (300 chunks, 150 aspartamo + 150 tartratos):
    435,5 chunks/s**, proyección lineal ~4,1 min para el corpus
    completo.
  - **CORPUS COMPLETO INDEXADO DE VERDAD (sesión 18-ago-2026,
    continuación 4) -- tiempo REAL, no proyección:** 67.827 chunks,
    **2,97 min en total** (3,4 s carga del modelo + 1,27 min embeddings
    a 887,3 chunks/s + 1,51 min escritura en Chroma) -- más rápido que
    la proyección de 4,1 min, principalmente porque `model.encode()`
    con `batch_size=256` explícito rinde casi el doble que el batch
    interno por defecto (32) usado implícitamente en la prueba de 300.
    Verificado `collection.count() == 67827` tras escribir. Persistido
    en `data/chroma/` (colección `efsa_reevaluation_chunks`, cliente
    `chromadb.PersistentClient`) -- **597 MB en disco**
    (`chroma.sqlite3`). Reindexar por completo BORRA la colección
    anterior primero (`scripts/build_chroma_index.py --all`, evita
    duplicados de una corrida previa) -- no es incremental, es un
    rebuild completo cada vez.
  - **Consultas de verificación sobre el índice completo (no el lote
    de prueba) -- 3 preguntas, temas distintos, todas con resultados
    temáticamente correctos:**
    1. *"genotoxicity studies and safety assessment"* -- top 5 incluye
       la sección `4.3. Genotoxicity` del TiO2 vigente (E171, 2021) y
       contenido de genotoxicidad de sílice/eritritol.
    2. *"why was titanium dioxide withdrawn as a food additive"* --
       **los 5 resultados son de los 2 dossiers de TiO2 (2016 y
       2021)**, incluida su sección `1. Introduction` y `Summary`
       explicando la re-evaluación -- caso conocido usado como prueba
       específica, resultado correcto.
    3. *"dietary exposure assessment uncertainties"* -- top 5 mezcla
       secciones "Uncertainty analysis" de 5 aditivos DISTINTOS
       (verificado contra `chemical_name`, no adivinado: poliglicerol
       poliricinoleato E476, octyl gallate E311, cochinilla/ácido
       carmínico E120, dimetil dicarbonato E242, dodecyl gallate E312)
       -- confirma que no es un acierto aislado del tema de
       genotoxicidad, generaliza a otro tema.
  - Verificado además, no asumido: Chroma lanza `TypeError` con valores
    `None` en metadatos (ver el ESQUEMA FINAL más abajo en "Hallazgos
    verificados") y SÍ admite claves de metadato distintas entre
    documentos de la misma colección.
- **Backend de embeddings: ONNX int8, no `torch` -- decisión de
  memoria para el deploy (sesión 18-ago-2026), con el índice de Chroma
  YA reconstruido con este backend, no solo decidido en teoría.** Motivo
  completo, cifras de cada alternativa probada, y el pivote de plan de
  deploy que lo motivó (Streamlit Community Cloud → HF Spaces → HF
  Spaces con Docker de pago descubierto → esta optimización de memoria
  como palanca adicional): `PROGRESS.md`, sesión 18-ago-2026,
  continuación 19 -- no repetido aquí para no duplicar el detalle.
  **Puntos que SÍ hace falta recordar al tocar este código:**
  - `torch` SIGUE siendo dependencia dura de `sentence-transformers`
    pase lo que pase -- verificado desinstalándolo, rompe el import
    incluso con `backend="onnx"`. El ahorro de ONNX no viene de evitar
    `torch`, viene de evitar el "calentamiento" de la primera
    inferencia de PyTorch (~400 MB) porque la inferencia real la hace
    ONNX Runtime.
  - **Único punto de la base de código que debe instanciar
    `SentenceTransformer`: `ingestion/embedding_model.py::load_embedding_model()`.**
    Indexado (`scripts/build_chroma_index.py`) y retrieval
    (`graph/build.py::build_default_deps`) lo llaman a los DOS -- si
    alguna vez se cambia el modelo/backend, cambiar solo ahí, nunca
    instanciar `SentenceTransformer` directamente en otro sitio (ya
    pasó una vez que index y query usaban backends distintos por
    accidente -- fp32/torch en el índice, int8/onnx en la consulta --
    antes de unificarlo con este módulo, ver PROGRESS.md).
  - `requirements.txt`: `sentence-transformers[onnx]`, no
    `sentence-transformers` a secas (añade `optimum` + `onnxruntime`).
  - Reindexado completo con este backend: ~22,4 min en CPU (sin GPU),
    frente a los ~3 min con GPU+torch de la corrida original -- más
    lento, aceptado porque es un paso offline que no cuenta contra el
    presupuesto de memoria del deploy.
  - `data/chroma/` pasó de 597 MB a 718 MB en disco tras reconstruir
    -- sin investigar la causa exacta (no es por las embeddings en sí,
    siguen siendo float32/384 dims igual que antes), no bloqueante.
- **Contrato Nodo 2 → Nodo 4 (`retrieved_chunks`): `RetrievedChunk`, no
  `list[str]` -- fijado en sesión 17-ago-2026 (continuación 7), ANTES de
  escribir el Nodo 2, precisamente para que quien lo escriba (aunque sea
  en otra sesión) no tenga que rehacer este contrato después.**
  `GraphState.retrieved_chunks` era `list[str]` -- texto plano, sin
  metadatos -- lo cual hacía IMPOSIBLE que el Nodo 4 supiera nada sobre
  la procedencia de un fragmento (qué sustancia, qué dossier, con qué
  fiabilidad se resolvió esa sustancia). Motivado directamente por el
  diseño de comunicación de riesgo por `substance_resolution_tier`
  (ver "Hallazgos verificados", diseño de resolución en 3 niveles) --
  el tier 3 (identidad de sustancia inferida por título, no por enlace
  estructural) solo puede comunicarse al LLM si el Nodo 2 lo transporta
  hasta el Nodo 4, y con `list[str]` no había dónde ponerlo.
  - **Nuevo dataclass `RetrievedChunk` en `graph/nodes.py`:**
    ```python
    @dataclass(frozen=True)
    class RetrievedChunk:
        text: str
        substance_uuid: str
        chemical_name: str
        dossier_uuid: str
        dossier_title: str
        substance_resolution_tier: int  # 1, 2 o 3 -- ver substances_per_dossier()
        doi: str | None = None
        section_heading: str | None = None
        page_number: int | None = None
    ```
    Campos que el Nodo 4 usa HOY (tras esta sesión): `text` y
    `substance_resolution_tier` (para el aviso inline en fragmentos
    tier 3, ver `_format_retrieved_chunks`). El resto (`chemical_name`,
    `dossier_uuid`, `dossier_title`, `doi`, `section_heading`,
    `page_number`) NO se consume todavía en ningún punto del código --
    se fijan ahora porque son la misma información que ya va a estar en
    los metadatos de cada chunk de Chroma (ver el esquema de metadatos
    diseñado en "Hallazgos verificados", `substance_uuid`/`e_number`/
    `chemical_name`/`chunk_group_id`/`dossier_uuid`/`pdf_filename`/
    `doi`/`section_heading`/`page_number`/`is_group_dossier`) -- el Nodo
    2, cuando se escriba, solo tiene que copiar esos campos de metadato
    de Chroma a `RetrievedChunk`, no inventar de dónde sacarlos.
    `is_group_dossier`/`e_number`/`pdf_filename`/`chunk_group_id` del
    esquema de Chroma NO están en `RetrievedChunk` -- no se ha
    encontrado todavía un uso en el Nodo 4 para ellos; añadirlos si
    aparece una necesidad concreta, no por simetría con el esquema de
    Chroma.
  - **`GraphState.retrieved_chunks: list[RetrievedChunk]`** (antes
    `list[str]`) -- cambio de tipo ya aplicado en `graph/nodes.py` en
    esta sesión, aunque el Nodo 2 (`hybrid_retrieval_node`) siga sin
    implementar (`NotImplementedError`). **Cuando se escriba el Nodo 2,
    DEBE devolver `list[RetrievedChunk]`, nunca strings sueltos** -- este
    contrato es la razón de ser de esta entrada del documento, no lo
    reabras sin motivo nuevo.
  - **`_format_retrieved_chunks` actualizado** para leer
    `substance_resolution_tier` de cada chunk y anteponer un aviso
    inline SOLO cuando `tier == 3` -- mismo patrón que ya usa
    `discussion_line` en `_format_structured_result` (instrucción
    incrustada en el propio dato del prompt de usuario, no una regla
    nueva en `NODE_4_GROUNDING_RULES`/`NODE_4_SAFETY_COMMUNICATION_RULES`,
    que NO se han tocado).
- **Resolución multi-candidato del Nodo 1 (sesión 19-ago-2026) --
  `GraphState.substance_uuid: str | None` sustituido por
  `substance_candidates: list[SubstanceCandidate]`, mismo tipo de cambio
  de contrato que la entrada de `retrieved_chunks` de arriba, no la
  reabras sin motivo nuevo.** Decisión de producto explícita del
  usuario: cuando `OpenFoodToxStore.resolve_substance_candidates` (nuevo
  método, exacto -> exacto normalizado por guion/espacio -> fuzzy
  restringido a las 246 sustancias resolubles del corpus) encuentra
  varios nombres razonablemente parecidos, el sistema nunca elige uno en
  silencio -- resuelve y presenta TODOS por separado. Detalle completo
  (calibración del umbral fuzzy, por qué se descartó la hipótesis del
  símbolo griego para tocoferol, presupuesto de `retrieved_chunks` con
  2+ candidatos, por qué MCP queda deliberadamente fuera) en "Hallazgos
  verificados", pendiente #2 de más abajo (ahora marcado RESUELTO).
- **Dos caminos de ejecución del grafo -- completo y parcial -- decisión
  tomada al implementar el servidor MCP (sesión 18-ago-2026):**
  `graph/build.py` expone dos puntos de entrada, no uno:
  - **Completo -- `answer_question(query) -> AnswerResult`:** Nodo 1 →
    2 → 3 → 4, el grafo compilado tal cual (`build_graph`). Usado por la
    herramienta MCP `search_efsa_opinion`. Produce prosa (el texto de
    `answer`), así que está sujeto a `NODE_4_SAFETY_COMMUNICATION_RULES`
    en tiempo de generación -- el único punto del sistema donde se
    compone lenguaje nuevo sobre el ADI, y por tanto el único que
    necesita esa restricción activa.
  - **Parcial -- `resolve_current_opinion(query) -> ReevaluationStatus`:**
    Nodo 1 + Nodo 3 únicamente, llamando a `extract_entity_node`/
    `verify_currency_node` directamente (NO al grafo compilado, que
    siempre enruta al Nodo 4) -- sin Nodo 2 (no hace falta
    `retrieved_chunks` para esto) ni Nodo 4 (no hace falta prosa
    generada, solo campos ya calculados por OpenFoodTox). Usado por la
    herramienta MCP `get_reevaluation_status`. Comparte el mismo
    `_default_deps` cacheado que `answer_question` -- llamar a una u
    otra función no recarga embeddings/Chroma/xlsx por separado.
  - **Por qué saltarse el Nodo 4 en el camino parcial NO compromete la
    restricción no negociable #1, verificado campo a campo antes de
    implementarlo, no asumido:** la restricción prohíbe que el LLM
    **redacte** una frase que enmarque el ADI como umbral ("si se
    supera el ADI, se produce/puede producir [efecto]") -- vive en el
    system prompt del Nodo 4 precisamente porque ahí es donde se
    compone prosa nueva. `ReevaluationStatus`/`OpinionReference` no
    pasan por ningún LLM para el ADI: `adi_value`/`adi_unit` son
    lectura directa de `FLEX_SUM.ToxRefValues` (números crudos, sin
    interpretar), `adi_justification` es
    `adi_row[ADI_JUSTIFICATION_COLUMN]` -- texto de EFSA citado tal
    cual, sin reformular (`ingestion/openfoodtox.py`) -- el MISMO campo
    que el Nodo 4 ya cita literalmente dentro de sus respuestas
    generadas hoy (`test_format_structured_result_tier1_cites_adi_normally`).
    Sin generación no hay redacción que pudiera violar la regla.
  - **Capa extra en el servidor MCP, no en `graph/build.py`:** el JSON
    que devuelve la herramienta `get_reevaluation_status` incluye un
    campo `safety_note` -- una constante de texto fija (NO generada por
    ningún LLM), recordando que el ADI es un margen de seguridad, no un
    umbral. No lo exige la restricción #1 (que solo rige redacción
    dentro del sistema), pero un cliente MCP externo que reciba estos
    números crudos podría componer la frase prohibida por su cuenta sin
    ese contexto -- defensa en profundidad, no una regla nueva del
    Nodo 4.

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
- `graph/nodes.py` — Nodo 2 (retrieval híbrido), Nodo 3 (determinista) y
  Nodo 4 (generación) implementados.
  **Nodo 1 (`extract_entity_node`) -- PRIMERA IMPLEMENTACIÓN REAL
  (sesión 18-ago-2026, continuación 7), NO una continuación de nada
  previo.** Hasta esta sesión era literalmente `raise NotImplementedError`
  desde el primer commit del repo, pese a documentación previa que
  decía lo contrario -- ver la corrección completa en PROGRESS.md
  (continuación 6) antes de esta entrada. Diseño e implementación:
  - `NODE_1_ENTITY_EXTRACTION_PROMPT` (nuevo, primera vez que existe):
    pide al LLM el nombre químico CANÓNICO EN INGLÉS de la sustancia
    mencionada en la pregunta -- una sola línea, sin explicación, o
    literalmente `NONE` si no identifica ningún aditivo. Necesario en
    inglés porque `OpenFoodToxStore.substance_uuid_by_name` exige
    coincidencia EXACTA contra `SUB.ChemicalName` (limitación conocida,
    pendiente #2 más abajo, NO resuelta por este nodo -- si el LLM
    normaliza a un nombre razonable que no coincide carácter a
    carácter con `SUB` (ej. nombres compuestos), la resolución falla y
    `substance_uuid` queda en `None`, comportamiento esperado).
  - `max_tokens=30` -- un nombre químico, no una frase.
  - **Probado con llamada REAL a la API de DeepSeek, no asumido ni
    mockeado** (`tests/test_nodes.py::test_extract_entity_node_resolves_aspartame_from_real_english_query`,
    pregunta en inglés sobre aspartamo -- el caso de referencia ya
    usado en el resto del proyecto -- verifica `substance_uuid` contra
    `store.substance_uuid_by_name("Aspartame")` directamente, no da el
    resultado por bueno solo porque el prompt parezca razonable) +
    `test_extract_entity_node_unrelated_query_resolves_to_none`
    (pregunta sin ningún aditivo -- confirma que no inventa una
    sustancia). Ambos tests hacen una llamada real y FACTURADA a la
    API en cada ejecución (a diferencia del resto de tests de este
    archivo, que son gratis una vez el recurso local existe) -- se
    saltan si `DEEPSEEK_API_KEY` no está configurada.
  - **Verificado además, a mano, con 4 preguntas reales antes de dar
    la implementación por buena** (no solo las 2 del test automatizado):
    inglés+aspartamo -> `Aspartame` (UUID correcto); español, "Por
    qué se retiró el dióxido de titanio como aditivo?" -> `Titanium
    dioxide` (UUID correcto); E-number "Is E 951 safe for children?"
    -> `Aspartame` (UUID correcto); pregunta sin relación ("What time
    is it in Tokyo") -> `None`/`None`, sin inventar.
    **La limitación de idioma español/E-numbers de
    `substance_uuid_by_name` (pendiente #2 más abajo) sigue SIN
    RESOLVER a nivel estructural -- NO la des por cerrada.** La función
    en sí sigue exigiendo coincidencia EXACTA contra `SUB.ChemicalName`
    en inglés, sin cambios. Lo único que cambió es que el LLM normaliza
    ANTES de llegar a esa función, y en los 4 casos puntuales probados
    (1 en español, 1 con E-number) acertó la traducción/normalización.
    Eso es **una mitigación parcial, verificada en un puñado de casos
    concretos, NO una batería de pruebas sistemática** -- no hay
    ninguna garantía de que el LLM acierte con nombres compuestos,
    E-numbers menos conocidos, o variantes de redacción no probadas
    todavía. Tratar como "probablemente ayuda en la mayoría de casos
    comunes", no como "el problema está resuelto" -- si en el futuro se
    quiere una garantía real, hace falta una batería de pruebas más
    amplia (o una solución estructural, ej. una tabla de sinónimos/
    traducciones curada) antes de confiar en esto para producción.
  - Si `substance_uuid` resuelve a `None` (LLM respondió `NONE`, o el
    nombre no coincide exacto en `SUB`), el resto del grafo ya lo
    maneja: Nodo 2 deja `retrieved_chunks` vacío sin llamar a Chroma;
    Nodo 3 espera `substance_uuid` no nulo y lanza `ValueError` si se
    le llama sin él -- decidir si llamarlo en ese caso es
    responsabilidad de la orquestación del grafo -- ver `graph/build.py`
    más abajo, implementado en la misma sesión que cierra este punto.
  Nodo 4 conecta `deps.llm_client.complete(...)` con system prompt =
  `NODE_4_GROUNDING_RULES` + `NODE_4_SAFETY_COMMUNICATION_RULES`;
  probado con llamada real a la API (caso aspartamo) cumpliendo las
  reglas de comunicación de riesgo -- este es el nodo que se probó
  contra la API real ya en sesión 2 (16-ago-2026), probablemente el
  origen de la confusión que atribuyó lo mismo al Nodo 1 sin serlo
  (ver la entrada de corrección en PROGRESS.md) -- ahora el Nodo 1
  TAMBIÉN está probado contra la API real por derecho propio, no por
  la misma prueba de otro nodo.
  **[CORRECCIÓN, sesión 18-ago-2026 (auditoría general): esta prueba
  real es cierta pero está DESACTUALIZADA -- no cubre el prompt tal
  como es hoy.** La llamada real de sesión 2 se hizo contra una
  versión de `_format_structured_result` anterior a que existieran
  `discussion_text`/`discussion_is_boilerplate` (añadidos en sesión 3,
  16-ago-2026) y anterior al texto de "motivos opuestos" para ADI sin
  valor numérico (tier 1/2, añadido en sesión 17-ago-2026 continuación
  7) -- ambos confirmados presentes en el código actual, ambos
  ausentes en el momento de esa prueba. `_format_retrieved_chunks` (el
  aviso de tier 3) tampoco existía todavía. **Ninguna de estas tres
  adiciones ha pasado nunca por una llamada real a la API.** Más
  importante: como el Nodo 2 no existía hasta la sesión de hoy,
  **todas las llamadas reales hechas a este nodo hasta ahora se
  hicieron con `retrieved_chunks=[]`** -- el caso de fragmentos
  narrativos reales poblando el prompt (el motivo de ser del Nodo 2)
  nunca se ha probado end-to-end con una llamada real. Y, verificado
  con `grep` en esta misma auditoría: **no existe ningún test
  automatizado de `generate_answer_node`** en `tests/` -- a diferencia
  del Nodo 1 y el Nodo 2, esta verificación nunca se codificó como
  reproducible, solo quedó como una sesión manual puntual de hace
  varios días. No tratar "Nodo 4 probado contra la API real" como una
  garantía vigente del comportamiento actual -- antes de confiar en
  ello para producción, hace falta repetir la prueba real con el
  prompt de hoy (incluido `retrieved_chunks` no vacío) y, si se quiere
  que sea reproducible, añadir un test automatizado como los de los
  Nodos 1 y 2.]**
  **Nodo 2 (`hybrid_retrieval_node`) IMPLEMENTADO (sesión 18-ago-2026,
  continuación 5) y probado con una consulta real contra el índice
  completo de Chroma (67.827 chunks, caso aspartamo).** Diseño:
  - Si `state["substance_uuid"]` es `None` (Nodo 1 no resolvió nada),
    NO se llama a Chroma en absoluto -- `retrieved_chunks` queda vacío
    directamente. Verificado con un vectorstore de prueba que lanza
    excepción si se le llama, para confirmar que de verdad no se
    invoca, no solo que el resultado da vacío por casualidad.
  - Si hay `substance_uuid`, se embede `user_query` con
    `deps.embedding_model` (el MISMO modelo usado para indexar,
    `all-MiniLM-L6-v2` -- pasado como dependencia, no cargado de nuevo
    en cada llamada) y se consulta `deps.vectorstore.query(...)`
    filtrando por `where={"substance_uuid": ...}` -- el único campo
    del esquema de metadatos con filtro exacto fiable (no hay
    `e_number`, y `substance_name` es texto libre del usuario, no una
    clave de índice).
  - `k = DEFAULT_RETRIEVAL_K = 5` -- el extremo superior del rango
    k=3-5 ya asumido en el cálculo de presupuesto de contexto del Nodo
    4 (ver PROGRESS.md sesión 18-ago-2026), elegido porque el
    presupuesto seguía siendo razonable ahí y da más contexto real.
  - `substance_resolution_tier` y el resto de campos de
    `RetrievedChunk` se copian TAL CUAL de los metadatos ya escritos
    al indexar -- no se re-derivan en el Nodo 2.
  - `NodeDependencies` ganó un campo nuevo, `embedding_model` (además
    de `vectorstore`, ya existente) -- ambos tipados como `object` a
    propósito, mismo principio que `LLMClient`: no acoplar
    `graph/nodes.py` a la API concreta de chromadb/sentence-transformers.
  - Probado con `tests/test_nodes.py::test_hybrid_retrieval_node_aspartame_real_query`
    (consulta real sobre genotoxicidad/carcinogenicidad de aspartamo,
    no un mock -- verifica que todos los chunks devueltos tienen el
    `substance_uuid` correcto, `chemical_name == "Aspartame"`,
    `section_heading` no vacío, y `substance_resolution_tier == 1`) y
    `test_hybrid_retrieval_node_no_uuid_skips_chroma_entirely`. Se
    saltan si `data/chroma/` no existe (mismo patrón que los tests que
    dependen del xlsx real).
  - **DIAGNÓSTICO (sesión 18-ago-2026, continuación 12, SOLO
    investigación, nada implementado): la calidad del retrieval es
    sensible al fraseo de la pregunta -- confirmado con TiO2, no
    asumido.** La consulta "Why was titanium dioxide withdrawn as a
    food additive?" NO recuperó ningún fragmento de la sección
    "4.3. Genotoxicity" (página 45) -- la sección que de hecho contiene
    la preocupación de seguridad central del dictamen de 2021 -- y en
    su lugar trajo Introduction/Background/Summary, contenido más
    regulatorio que sustantivo. Probada una reformulación más directa,
    "titanium dioxide genotoxicity concern conclusion": **el resultado
    #1 es exactamente esa sección (4.3. Genotoxicity)** -- confirma que
    el contenido SÍ está bien chunked e indexado, el problema es de
    fraseo de la pregunta original ("withdrawn" no es un marco que el
    propio dictamen use -- es una reevaluación, no un anuncio de
    retirada, así que la similitud de embeddings favoreció contenido
    superficial sobre la sección sustantiva). **Hallazgo secundario, no
    buscado:** incluso con la reformulación mejor, 3 de los 5
    resultados fueron fragmentos de la sección "References" (entradas
    bibliográficas que mencionan "genotoxicity" en el título del
    estudio citado, no razonamiento del panel) -- mismo tipo de ruido
    de baja calidad que ya motivó excluir tablas del índice narrativo
    (ver la decisión de Opción A). **No implementado nada de esto** --
    ni reformulación de query en el Nodo 1/2, ni exclusión de
    "References" del chunking -- queda como candidato a mejora futura
    del Nodo 2/chunker, no urgente pero real.
  El Nodo 4 sigue diseñado para degradar con gracia con
  `retrieved_chunks` vacío, y desde sesión 18-ago-2026 (continuación
  10-11) también se ha probado de extremo a extremo con
  `retrieved_chunks` reales poblados por el Nodo 2 en la misma
  ejecución (`answer_question`, ver `graph/build.py` más abajo).
  - **BUG REAL ENCONTRADO Y ARREGLADO (sesión 18-ago-2026, continuación
    12): truncamiento silencioso de la respuesta, sin ningún aviso al
    usuario.** Una respuesta real sobre Shellac (caso tier 3, con aviso
    de fiabilidad + desglose largo) se cortó a mitad de frase. Antes de
    tocar nada, se confirmó la causa exacta vía
    `response.choices[0].finish_reason` (expuesto ahora como
    `LLMResponse.finish_reason`, campo nuevo en `graph/llm_client.py`,
    antes no existía en la interfaz): **`finish_reason == 'length'`,
    `output_tokens == 800` (el tope exacto de entonces)** -- truncamiento
    real por `max_tokens`, no otra causa (no filtro de contenido, no
    secuencia de parada). El texto se devolvía al usuario tal cual,
    cortado, sin ninguna señal de que faltaba contenido.
  - **Fix, dos partes:** (1) `NODE_4_MAX_TOKENS` subido de 800 a 2000
    (`graph/nodes.py`) -- con "thinking" ya desactivado (ver más abajo),
    esto es presupuesto de texto de salida real, no overhead oculto de
    razonamiento, así que subirlo es coste directo -- ver el bullet de
    precio de referencia más arriba para la actualización pendiente de
    ese cálculo. (2) `generate_answer_node` ahora comprueba
    `response.finish_reason == "length"` explícitamente: si trunca,
    reintenta UNA vez con `NODE_4_RETRY_MAX_TOKENS = 3500`, y si sigue
    truncada incluso así, añade `"\n\n[respuesta incompleta por límite
    de longitud]"` al final -- nunca se devuelve una respuesta cortada
    sin avisar, pase lo que pase.
  - **Verificado tras el fix, misma consulta de Shellac:** con
    `max_tokens=2000`, la respuesta terminó sola
    (`finish_reason == 'stop'`) en **845 tokens de salida** -- ni
    siquiera hizo falta el reintento, y la respuesta ahora cierra con
    un párrafo de "Conclusión" completo, no cortado a mitad de frase.
    Suite de tests completa: 23/23 siguen pasando.
- **`graph/build.py` (nuevo, sesión 18-ago-2026, continuación 9) --
  ensamblado del grafo LangGraph completo, COMPILADO Y VERIFICADO
  ESTRUCTURALMENTE, NO ejecutado todavía con datos reales.** Distingue
  a propósito de otros bullets de esta lista: aquí "verificado" es
  "el grafo compila y su diagrama Mermaid tiene la forma esperada", no
  "se ha invocado con una pregunta real" -- eso queda explícitamente
  para la próxima sesión, no se hizo en esta a petición del usuario
  ("no llames a la API todavía").
  - `build_graph(deps: NodeDependencies) -> CompiledStateGraph`: los 4
    nodos registrados como closures que capturan `deps` (las funciones
    de nodo toman `(state, deps)`, `StateGraph.add_node` espera solo
    `state`). `extract_entity -> hybrid_retrieval ->` arista
    condicional `-> {verify_currency -> generate_answer} | {generate_answer}`.
  - **Decisión de diseño explícita -- qué pasa si el Nodo 1 no resuelve
    `substance_uuid`: el grafo SIGUE hasta el Nodo 4, no corta antes.**
    Pero salta el Nodo 3 (que lanzaría `ValueError` si se le llamara
    sin `substance_uuid`, sin cambios en su código) -- una única arista
    condicional justo después del Nodo 2 decide entre el camino normal
    (Nodo 3 -> Nodo 4) y el camino corto (directo a Nodo 4). Motivo de
    seguir hasta el Nodo 4 en vez de cortar: el Nodo 4 ya estaba
    diseñado para degradar con gracia en ambos huecos --
    `structured_result` no puesto en el estado se lee como `None`
    igual que si el Nodo 3 lo hubiera puesto explícitamente
    (`GraphState` es `TypedDict(total=False)`), y `retrieved_chunks`
    ya queda vacío por diseño del propio Nodo 2 sin `substance_uuid` --
    así que el Nodo 4 puede producir una respuesta útil ("no he podido
    identificar de qué aditivo hablas") sin código nuevo. Cortar antes
    dejaría al usuario sin respuesta y no ahorra nada (el Nodo 1, la
    única llamada cara del camino corto, ya se pagó). `vigencia_ambigua`
    (solo la pone el Nodo 3) queda sin definir en el camino corto --
    verificado que ningún otro nodo la lee, sin efecto secundario.
  - `build_default_deps()`: instancia real de `NodeDependencies` --
    `OpenFoodToxStore` sobre el xlsx, colección Chroma persistente
    (`data/chroma/`, `chromadb.PersistentClient`), `SentenceTransformer`
    (`all-MiniLM-L6-v2`, el mismo modelo del indexado) y
    `build_default_client()` (ya existente en `graph/llm_client.py`,
    reutilizado sin duplicar -- lee `EFSA_RAG_LLM_BACKEND` del entorno).
  - `answer_question(query: str) -> AnswerResult`: punto de entrada
    simple pedido explícitamente. `deps`/grafo cacheados a nivel de
    módulo (variables globales `_default_deps`/`_default_graph`,
    inicializadas en la primera llamada) -- decisión propia, no pedida
    literalmente así, para no recargar el modelo de embeddings ni
    reabrir Chroma en cada pregunta; documentado en el propio código
    por qué.
    - **CAMBIO DE CONTRATO (sesión 18-ago-2026, continuación 11):
      devuelve `AnswerResult` (dataclass: `answer: str`,
      `retrieved_chunks: list[RetrievedChunk]`,
      `structured_result: OpinionReference | None`), NO un `str` como
      en la versión original.** Motivo -- existe específicamente para
      poder AUDITAR FUNDAMENTACIÓN sin tener que reproducir el
      retrieval a mano: en una sesión de verificación real (misma
      sesión, antes de este cambio) se pidió confirmar si una mención
      concreta de la respuesta ("Soffritti et al. 2006") aparecía de
      verdad en algún `retrieved_chunk`, y como `answer_question` solo
      devolvía el string, hubo que reconstruir la llamada a
      `hybrid_retrieval_node` por separado con el mismo `substance_uuid`
      y query para poder inspeccionarlo -- funcionó (sí aparecía,
      chunk de la sección "2.7.1. Existing authorisations and
      evaluations of aspartame"), pero no debería hacer falta
      reproducir nada para verificar esto la próxima vez.
      `retrieved_chunks`/`structured_result` en `AnswerResult` son los
      MISMOS objetos que vio el Nodo 4 al construir el prompt (leídos
      del estado final tras `.invoke(...)`), no una reconstrucción
      aparte. `answer` sigue siendo el texto final -- esto no lo
      sustituye, lo acompaña. **Verificado sin callers reales que
      rompiera** (`grep` antes del cambio: ningún caller en
      `ui/app.py`, tests o scripts esperaba el `str` de antes -- solo
      invocaciones manuales sueltas de sesiones de verificación, nada
      persistido). Re-verificado con una llamada real tras el cambio:
      reproduce exactamente los mismos 5 `retrieved_chunks` que la
      reconstrucción manual anterior, mismo orden -- confirma que el
      retrieval es determinista para esta consulta.
  - **Verificado en esta sesión (sin tocar la API):** `python -m
    efsa_rag.graph.build` compila el grafo con un `NodeDependencies`
    de relleno (todos los campos `None` -- seguro porque `deps` solo
    se usa DENTRO de las funciones de nodo cuando el grafo se invoca de
    verdad, nunca durante `.compile()`/`.get_graph()`) y dibuja el
    Mermaid: `extract_entity -> hybrid_retrieval`, dos aristas
    punteadas (condicionales) desde `hybrid_retrieval` hacia
    `verify_currency` y hacia `generate_answer` directamente,
    `verify_currency -> generate_answer -> __end__` -- coincide
    exactamente con el diseño de arriba. Suite de tests completa
    (23/23) sigue en verde con el módulo nuevo importado.
  - **YA INVOCADO DE VERDAD (sesión 18-ago-2026, continuación 10):**
    `answer_question("What is the ADI of aspartame and what study is
    it based on?")` -- primera ejecución real de extremo a extremo
    (Nodo 1 -> 2 -> 3 -> 4 en una sola llamada), no solo por nodos
    separados. Respuesta completa, ADI/DOI/fecha correctos, cita
    textual de `adi_justification`, margen de seguridad explicado
    correctamente (sin la frase prohibida de "si se supera el ADI").
    Fundamentación de una mención concreta de la respuesta
    ("Soffritti et al. 2006") verificada contra `retrieved_chunks`
    real -- aparece literalmente en el chunk de la sección "2.7.1.
    Existing authorisations and evaluations of aspartame", confirmando
    que el Nodo 4 no mezcló esa mención con conocimiento propio del
    entrenamiento sin decirlo. Motivó el cambio de contrato de
    `answer_question` (ver el bullet de arriba, `AnswerResult`) para
    no tener que reproducir el retrieval a mano la próxima vez.
- `ui/app.py` — candado de refresco + límites de consulta, funcional.
  **Conectada al grafo (sesión 18-ago-2026):** `_render_answer` llama a
  `answer_question` (import perezoso -- no se paga el coste de
  Chroma/embeddings hasta la primera consulta real, no al arrancar la
  app), SIEMPRE después de `check_and_register_query()` -- si el límite
  está agotado, el grafo NUNCA se invoca (verificado leyendo `main()`,
  no solo asumido). **Bug real encontrado y arreglado en la misma
  sesión, al medir memoria con `AppTest`:** `_get_client_ip()` podía
  devolver un valor no-`str` (ej. bajo el harness de test de
  Streamlit) que rompía `check_and_register_query()` al usarse como
  clave de un dict antes de serializar a JSON -- el docstring ya
  prometía degradar a `"unknown"` en cualquier fallo, solo le faltaba
  validar el TIPO del resultado, no solo capturar excepciones.
- `tests/test_openfoodtox_joins.py` — test de regresión del caso
  aspartamo + test de columnas de ADI, **pasan los 3 contra el xlsx
  real** (antes se saltaban por no haber xlsx en `data/raw/`).
- **`mcp/server.py` (sesión 18-ago-2026) -- dos herramientas,
  `search_efsa_opinion` y `get_reevaluation_status`, wrappers finos
  sobre `answer_question`/`resolve_current_opinion` de `graph/build.py`
  (ver "Decisiones de arquitectura ya tomadas", "Dos caminos de
  ejecución del grafo", para el diseño completo y las garantías de
  seguridad).** Implementado con `mcp.server.mcpserver.MCPServer`
  (mcp>=2.0, API distinta de `mcp.server.fastmcp.FastMCP` de la 1.x --
  `requirements.txt` corregido de `mcp>=1.0` a `mcp>=2.0` tras verificar
  la versión real instalada, ver más abajo si aparece un
  `ModuleNotFoundError` al reinstalar con una 1.x vieja). Esquema de
  cada herramienta (un único parámetro `substance: str`, descripción vía
  `Annotated[str, Field(description=...)]`) revisado y aprobado por el
  usuario ANTES de escribir el servidor -- no improvisado durante la
  implementación. Ambas devuelven `dict[str, Any]` con salida
  ESTRUCTURADA (verificado que el tipo de retorno concreto es necesario
  para que el SDK genere `outputSchema` -- un `dict` a secas sin
  parámetros de tipo no lo genera, probado directamente).
  **`tests/test_mcp_server.py` (sesión 18-ago-2026, mismo día) -- 6
  tests, mismo patrón de stubs que `tests/test_nodes.py` para el
  truncamiento del Nodo 4 (sin xlsx/Chroma/API real, sin gastar
  tokens):** esquema de `list_tools()` (nombres, `inputSchema` con
  `substance` como único parámetro requerido, `outputSchema` presente
  en ambas); `get_reevaluation_status` con sustancia conocida tier 1
  (ADI real) y tier 2 (sin ADI, patrón TiO2 -- confirma que no se
  inventa un valor); `search_efsa_opinion` con sustancia conocida;
  degradación con gracia de ambas con sustancia no identificada. **Cada
  test que stubea una función deja la OTRA como `_exploding` (lanza si
  se le llama)** -- confirma en positivo que `get_reevaluation_status`
  nunca invoca `answer_question` (no paga el Nodo 4) y viceversa, no
  solo que el resultado sea el esperado por casualidad. Sin
  `pytest-asyncio` en el proyecto -- `list_tools()`/`call_tool()`
  (async) se invocan con `asyncio.run(...)` dentro de tests síncronos,
  para no añadir una dependencia nueva solo para esto. Suite completa:
  **30 passed, 2 skipped**, sin regresiones tras los cambios en
  `graph/build.py`.

Pendiente, en orden de menor a mayor incertidumbre:
1. QA del corpus de 162 dictámenes contra las calls for data activas
   conocidas (ribonucleótidos E626-635, ácido glucónico E574-579,
   aditivos en forma gaseosa).
2. Resolver la limitación conocida del Nodo 1: `substance_uuid_by_name`
   exige coincidencia exacta del nombre químico canónico en inglés — no
   maneja español ("aspartamo") ni E-numbers ("E 951") todavía.
   **VERIFICADO Y CERRADO (sesión 18-ago-2026, al diseñar el esquema de
   metadatos de Chroma): `SUB` NO tiene ningún campo de E-number
   consultable.** Columnas reales de la hoja: `Document UUID`,
   `Definition`, `Parent UUID`, `ChemicalName`, `OwnerLegalEntity`,
   `ReferenceSubstance.ReferenceSubstance`,
   `TypeOfSubstance.Composition[.Other]`,
   `TypeOfSubstance.Origin[.Other]` -- ninguna es un E-number,
   confirmado inspeccionando la fila de aspartamo. **Implicación para
   el fallback de E-numbers en el Nodo 1: no puede resolverse con un
   lookup directo contra `SUB`** -- la única fuente de E-numbers en
   todo el dataset es texto libre en `LiteratureReference.EFSAOutputTitle`
   (vía el mismo patrón `E_NUMBER_PATTERN`/`e_numbers_from_title` ya
   usado en `ingestion/pdf_naming.py` para el checklist de PDFs), y esa
   extracción es POR DOSSIER, no por sustancia -- un dossier de grupo
   (ej. tartratos, 5 E-numbers en el título, 7 sustancias resueltas
   vía `substances_per_dossier`, ver "Hallazgos verificados") no tiene
   un mapeo 1:1 fiable entre cada E-number citado y cada
   `substance_uuid`. **Diseño futuro propuesto, NO implementado:** una
   tabla auxiliar E-number -> `substance_uuid` derivada por separado
   (con su propia verificación de los casos multi-sustancia, mismo
   nivel de cuidado que el resto de heurísticos de título de este
   proyecto), consultada por el Nodo 1 -- NO como metadato de Chroma
   por chunk (decisión tomada explícitamente al diseñar el esquema de
   metadatos, ver "Hallazgos verificados": el índice de retrieval usa
   `chemical_name`/`substance_uuid`, no `e_number`, precisamente porque
   esta limitación existe y no hay que mezclar un dato no verificado a
   nivel de sustancia con los campos que sí lo son).
   **Esta limitación SIGUE ABIERTA a nivel estructural, no la trates
   como cerrada por el Nodo 1** (sesión 18-ago-2026, continuación 7,
   ver `graph/nodes.py` en "Estado del código" más arriba): el Nodo 1
   ya implementado pide al LLM que normalice español/E-numbers a
   inglés ANTES de llamar a `substance_uuid_by_name`, y acertó en los
   4 casos puntuales probados a mano (1 en español, 1 con E-number) --
   pero es una mitigación parcial dependiente de que el LLM acierte la
   normalización cada vez, verificada en un puñado de casos, NO una
   solución sistemática ni una batería de pruebas amplia. La función
   subyacente sigue sin poder resolver español/E-numbers por sí sola.
   La tabla auxiliar E-number -> `substance_uuid` propuesta arriba
   seguiría siendo la solución estructural si se necesita una garantía
   real, no solo "probablemente funciona para casos comunes".
   - **Variante MÁS ESPECÍFICA de esta misma limitación, diagnosticada
     con datos reales (sesión 19-ago-2026, caso tocoferol) -- distinta
     del problema de español/E-numbers de arriba, no la confundas con
     él:** el LLM del Nodo 1 puede producir un nombre canónico en
     inglés RAZONABLE y bien normalizado, y aun así no resolver, porque
     `SUB.ChemicalName` tiene varias filas casi-duplicadas para lo que
     un humano llamaría "la misma sustancia" -- con prefijos/sufijos
     que el LLM no tiene forma de adivinar. Caso real verificado con
     una llamada real a la API (3 preguntas, español e inglés, todas
     sobre tocoferol): el LLM devuelve consistentemente `"Tocopherol"`
     (genérico, sin prefijo) -- `substance_uuid_by_name("Tocopherol")`
     devuelve `None`, porque esa cadena exacta no existe en `SUB`. Pero
     la sustancia SÍ está en el programa, con contenido real e
     indexado: de las 7 variantes de nombre que sí existen en `SUB`
     para tocoferoles, **4 resuelven perfectamente** (`structured_result`
     completo + 5 `retrieved_chunks` cada una) -- `DL-alpha-tocopherol`,
     `Tocopherol-rich extract`, `Gamma-tocopherol`, `Delta-tocopherol`,
     todas apuntando correctamente al dictamen de grupo de 2015 (DOI
     `10.2903/j.efsa.2015.4247`) -- y 3 no resuelven nada (`beta-tocopherol`,
     `tocopherols, total`, `Alpha-tocopherol` con mayúscula, sin
     dictamen vinculado ni chunks). Confirma que NO es un bug de
     retrieval del Nodo 2 independiente de un fallo del Nodo 3 --
     ambos fallan a la vez porque comparten la misma causa raíz en el
     Nodo 1 (`graph/build.py` salta el Nodo 3 y deja `retrieved_chunks`
     vacío cuando `substance_uuid` no resuelve, ver "Dos caminos de
     ejecución del grafo" más abajo).
   - **Fix de mensaje YA APLICADO (mismo día, `graph/nodes.py`,
     `_format_retrieved_chunks`):** el texto que se mostraba con
     `retrieved_chunks` vacío afirmaba **"el corpus de PDFs todavía no
     está indexado"** -- FALSO (67.827 chunks reales, verificado
     repetidamente en sesiones anteriores) y engañoso sobre la causa
     real. Corregido a dos mensajes distintos según si
     `structured_result` también es `None`: si SÍ lo es, "no se ha
     podido resolver de forma exacta la sustancia mencionada en la
     pregunta" (el caso de tocoferol, diagnosticado arriba); si
     `structured_result` NO es `None` (el dictamen vigente sí se
     resolvió por OpenFoodTox pero esta sustancia concreta no tiene
     chunks indexados -- causa distinta, no diagnosticada a fondo
     todavía, ver pendiente más abajo), "no se han encontrado
     fragmentos narrativos indexados para esta sustancia concreta,
     aunque sí se resolvió el dictamen vigente". La regla 3 de
     `NODE_4_GROUNDING_RULES` (el system prompt del Nodo 4) tenía la
     MISMA causa falsa incrustada -- corregida también, para que el
     LLM no le siga repitiendo esa explicación inventada al usuario
     final aunque el dato ya venga bien formateado.
   - **Segundo caso real confirmado, mismo patrón, distinto matiz --
     Caramel colours / E150a (sesión 19-ago-2026, reportado por el
     usuario tras ver el mensaje viejo en el deploy real).**
     Verificado con `grep` en TODO el código fuente (no solo
     `nodes.py`): **no existe ningún segundo punto que genere el texto
     "todavía no está indexado"** -- el fix de arriba es el único
     lugar del código que lo producía, y ya no lo produce (confirmado
     además con una llamada real de extremo a extremo,
     `answer_question("Is E150a (Caramel colour) safe as a food
     additive?")`, que devuelve correctamente "no se ha podido
     resolver de forma exacta la sustancia..." con el código tal como
     está en este commit). El Nodo 1 normaliza consultas reales sobre
     E150a a `"Caramel colour"` o `"Caramel colour (plain)"` (probado
     con 3 preguntas reales, español e inglés) -- ninguna de las dos
     coincide con `SUB.ChemicalName`, que solo tiene `"Caramel
     colours"` (plural), `"Plain caramel"`, `"Ammonia caramel"`,
     `"Caustic sulphite caramel"`, `"Sulphite ammonia caramel"`.
     **Matiz importante frente a tocoferol: aquí las 5 variantes SÍ
     resuelven perfectamente** (mismo dictamen de grupo, "re-evaluation
     of caramel colours (E 150 a,b,c,d)", `structured_result` completo
     + 5 chunks cada una) -- a diferencia de tocoferol, donde solo 4 de
     7 variantes resolvían. Confirma que el fallo es 100% del Nodo 1
     (ninguna variante nombrada por el LLM coincide), no una mezcla de
     dato incompleto + resolución -- y refuerza el riesgo de falsos
     positivos ya anotado abajo para el fallback de substring: aquí
     TODAS las filas candidatas son "correctas" (mismo dictamen), así
     que un fallback ingenuo habría funcionado por casualidad en este
     caso concreto pero no en el de tocoferol -- no hay forma de saber
     de antemano cuál de los dos patrones aplica sin la batería de
     pruebas todavía no construida. **Si el usuario sigue viendo el
     texto viejo en el deploy real después de este commit, la causa
     más probable no es un bug de código -- es que la prueba se hizo
     antes de que el contenedor de Streamlit Cloud terminara de
     reiniciarse con el commit nuevo** (confirmar reproduciendo tras
     un "Reboot app" manual, no solo un nuevo push).
   - **Diseño futuro propuesto para la resolución en sí, NO
     implementado -- fallback de coincidencia por substring/prefijo
     cuando la exacta falla** (ej. si `"Tocopherol"` no resuelve,
     probar `SUB.ChemicalName` que contenga `"tocopherol"` como
     substring, case-insensitive): **riesgo real de falsos positivos
     que hay que resolver con cuidado antes de tocarlo, no es un
     cambio trivial.** Un substring genérico puede casar con MÁS de
     una fila (como ya pasa aquí: 7 filas contienen "tocopherol", con
     resultados MUY distintos -- 4 resuelven bien, 3 no resuelven
     nada, y no hay ninguna señal en el propio nombre para elegir
     automáticamente cuál de las 7 es "la correcta" para una pregunta
     genérica del usuario). Un fallback ingenuo (ej. "coge la primera
     coincidencia") podría resolver a una fila SIN dictamen vinculado
     igual de fácil que a una con él, sustituyendo un fallo visible
     (`None`, mensaje honesto) por un resultado incorrecto silencioso
     -- peor que el problema actual. Cualquier implementación futura
     necesita, como mínimo: (a) desambiguar entre múltiples matches de
     substring en vez de coger el primero a ciegas, (b) preferir filas
     que SÍ tengan un dictamen vinculado sobre las que no, y (c) una
     batería de pruebas sobre varios casos multi-variante reales --
     ahora hay 2 casos documentados (tocoferol: 4/7 variantes
     resuelven; Caramel colours/E150a: 5/5 resuelven), y los dos
     apuntan en direcciones opuestas sobre si "cualquier match" sería
     seguro, lo que confirma que hace falta una muestra bastante más
     amplia antes de confiar en ello -- ninguno de los tres puntos
     está diseñado todavía, esto es solo el problema y la idea de
     dirección, no una propuesta lista para implementar.
   - **RESUELTO (sesión 19-ago-2026, continuación posterior a lo de
     arriba) -- implementada la resolución multi-candidato, NO el
     fallback de substring "coge cualquier match" descartado arriba por
     riesgo de falso positivo silencioso.** Decisión de producto
     explícita del usuario, distinta de "elegir el mejor candidato":
     cuando hay varios nombres razonablemente parecidos, el sistema
     **nunca elige uno en silencio** -- resuelve y presenta TODOS los
     candidatos plausibles por separado (cada uno con su propio dictamen
     vigente y sus propios `retrieved_chunks`), dejando que el usuario
     identifique cuál buscaba. Esto es justo el (a)/(b) que el párrafo
     de arriba pedía como mínimo para cualquier implementación futura,
     resuelto de raíz: no hace falta desambiguar "cuál de las N es la
     correcta" ni preferir filas con dictamen vinculado sobre las que no
     -- se muestran todas, con su propio dato (o su propia ausencia de
     dato) cada una.
   - **Hipótesis del símbolo griego (α/β/γ vs. palabra latina) probada y
     DESCARTADA con datos reales, antes de implementar nada** -- el
     usuario sospechaba que el problema de tocoferol era de símbolo
     griego vs. palabra escrita; verificado que `SUB.ChemicalName` NO
     tiene NINGUNA fila de tocoferol con símbolo griego Unicode (las 7
     variantes reales usan palabra latina: `alpha`, `beta`, `Gamma`,
     `Delta`; solo 14/7.871 filas de TODO el dataset usan símbolos
     griegos, ninguna relevante aquí). **Causa real, verificada con 7
     llamadas reales al Nodo 1:** el LLM hyphena de forma inconsistente
     según si la pregunta del usuario ya trae guion -- `"alpha
     tocopherol"` (sin guion) -> `"Alpha tocopherol"` (sin guion, NO
     resuelve, `SUB` tiene `"Alpha-tocopherol"` con guion) vs.
     `"α-tocopherol"`/`"alfa-tocoferol"` (con guion o símbolo) ->
     siempre `"Alpha-tocopherol"` (con guion, SÍ resuelve). Inconsistente
     incluso entre casos similares (`"gamma tocopherol"` sin guion en la
     pregunta dio `"Gamma-tocopherol"` CON guion en la respuesta) -- no
     es un patrón fiable por sí solo, pero el fix de normalización
     espacio<->guion de abajo lo cubre sin necesidad de entenderlo del
     todo.
   - **Diseño final, implementado (`OpenFoodToxStore.resolve_substance_candidates`,
     `ingestion/openfoodtox.py`):** tres escalones, el primero que
     produzca resultado(s) gana:
     1. Exacto (case-insensitive) contra `SUB.ChemicalName` completo --
        tier `"exact"`, score 100. Corregido de paso un bug latente real
        encontrado en esta sesión: `SUB.ChemicalName` tiene 9 nombres
        duplicados con distinto UUID (ej. `"Sodium saccharin"` x2, SÍ
        dentro del universo de 246 resolubles) -- `substance_uuid_by_name`
        (sin cambios, sigue usándose como atajo de test) solo devolvía
        `matches.iloc[0]`, descartando el segundo en silencio;
        `resolve_substance_candidates` devuelve TODOS.
     2. Igual, probando `name.replace(" ", "-")` y
        `name.replace("-", " ")` como coincidencia exacta adicional --
        tier `"exact_normalized"`, score 100, el fix de tocoferol de
        arriba. Sigue siendo coincidencia EXACTA, cero riesgo de
        ambigüedad nuevo. Recupera 2 de los 3 variantes de tocoferol que
        antes no resolvían (`Alpha-tocopherol`, `beta-tocopherol`) --
        solo `"tocopherols, total"` sigue sin recuperarse por esta vía
        (no es un problema de guion/espacio).
     3. Fuzzy (`rapidfuzz.fuzz.ratio`, NO `WRatio` -- `WRatio` probado y
        descartado, da falsos positivos graves por coincidencia de
        substring, ej. `"Xylene"` -> `"Perfluorobutylethylene"` al
        81,82%) contra un universo RESTRINGIDO a las 246 sustancias con
        dictamen de reevaluación resoluble (`substances_per_dossier(require_adi=False)`
        sobre `current_reevaluation_corpus()`), NO el `SUB.ChemicalName`
        completo (7.871 filas, todos los dominios regulatorios de
        OpenFoodTox -- pesticidas, veterinaria, contaminantes). **Esto es
        una decisión de ALCANCE, no solo una optimización de ruido** --
        mismo tipo de contaminación cruzada de dominio que causó el bug
        real de Sunset Yellow FCF (Grupo B, ver "Hallazgos verificados"
        arriba): verificado que contra el universo completo, consultas
        sin relación real llegan a ~48% de similitud con sustancias de
        otros programas regulatorios. `FUZZY_MATCH_LOW_THRESHOLD = 60`,
        calibrado con datos reales (no a ciegas):
        - `"Tocopherol"` (salida REAL del Nodo 1 para preguntas
          genéricas de tocoferol): 69,23 Delta-tocopherol, 69,23
          Gamma-tocopherol, 62,07 DL-alpha-tocopherol, 60,61
          Tocopherol-rich extract -- los 4 caen sobre el umbral; 55,56
          Glycerol (sustancia real no relacionada) queda excluido.
        - `"plai caramel"` (typo real): 88,00 Plain caramel, 66,67
          Ammonia caramel, 61,11 Sulphite ammonia caramel -- los 3 caen
          sobre el umbral. **Trade-off conocido y aceptado, no oculto:**
          para un typo claro de una sola sustancia, este umbral también
          incluye sustancias reales de la misma familia -- no es un
          falso positivo inventado, pero sí más candidatos de los
          estrictamente necesarios. No se persigue un umbral "perfecto"
          sin más señal que un ratio de caracteres.
        - Consultas sin relación real (`"quantum flux capacitor"`,
          `"banana smoothie recipe"`, `"Xylene"`): máximo 46-57 sobre el
          universo restringido -- ninguna cruza el umbral. Cero falsos
          positivos verificados.
     El resultado final se ordena SIEMPRE con `_candidate_sort_key`
     (`(-match_score, chemical_name.lower())` -- score descendente,
     nombre alfabético ascendente como desempate) antes de devolverse,
     para que `candidates[0]` ("el candidato top", el usado por el
     contrato MCP de un único resultado y por `structured_result`
     singular de `AnswerResult`) sea determinista incluso con empate
     exacto de score -- verificado real con `"Tocopherol"`:
     Delta-tocopherol y Gamma-tocopherol empatan a 69,23, y el orden
     ("d" < "g") da siempre Delta-tocopherol primero.
   - **`GraphState` cambia de contrato (mismo nivel de decisión que la
     entrada "Contrato Nodo 2 -> Nodo 4" de arriba, no la reabras sin
     motivo nuevo):** `substance_uuid: str | None` ->
     `substance_candidates: list[SubstanceCandidate]` (+
     `candidates_truncated: bool`); `structured_result: OpinionReference
     | None` -> `structured_results: dict[str, OpinionReference | None]`
     (clave = `substance_uuid`); `vigencia_ambigua: bool` (global, ya
     documentado como reservado/sin consumidor) -> `currency_verification_incomplete:
     dict[str, bool]` (mismo cálculo, por candidato); campo `citation`
     ELIMINADO (verificado con `grep` que no tenía ningún consumidor
     real, estado muerto desde que se escribió). Los 4 nodos y
     `graph/build.py::_route_after_retrieval` tocados.
   - **Presupuesto de `retrieved_chunks` con 2+ candidatos, decisión
     explícita del usuario -- dos topes, nunca un reparto sin fondo**
     (`graph/nodes.py`): `TOTAL_CHUNK_BUDGET = 15`, `MIN_K_PER_CANDIDATE
     = 3` (nunca se diluye un candidato por debajo), `MAX_CANDIDATES_SHOWN
     = 5` (`ingestion/openfoodtox.py` -- si hay más candidatos, se
     muestran los 5 de mayor similitud y se anuncia explícitamente en el
     propio prompt de usuario del Nodo 4, nunca en silencio).
     `k_por_candidato = min(5, max(3, 15 // N_mostrados))` -- con 1
     candidato da k=5 (idéntico al comportamiento de antes de esta
     sesión, sin regresión).
   - **`_build_user_prompt` (Nodo 4) con 0 o 1 candidato produce
     EXACTAMENTE el mismo formato de prompt que antes de esta sesión**
     -- sin envoltorio de "candidato 1 de 1", para no regresar el
     comportamiento ya probado (caso aspartamo, Shellac). Con 2+, cada
     candidato se presenta en su propio bloque `=== Candidato N:
     {nombre} ===`, con una instrucción incrustada en el propio prompt
     de usuario (mismo patrón que el aviso de tier 3 ya existente, NO
     una regla nueva de `NODE_4_GROUNDING_RULES`/
     `NODE_4_SAFETY_COMMUNICATION_RULES`) pidiendo al LLM que no las
     fusione ni asuma cuál buscaba el usuario. Verificado con llamada
     real a la API (`answer_question("Is tocopherol safe as a food
     additive?")`): los 4 candidatos se presentan por separado, en el
     orden determinista esperado (Delta primero), cada uno con su propio
     bloque de ADI/justificación/discusión/fragmentos, y el texto final
     dice explícitamente "cuatro sustancias... no se ha asumido cuál de
     ellas buscaba el usuario" -- sin violar la restricción no
     negociable #1 (ningún candidato sin ADI numérico se describe como
     "no seguro").
   - **MCP (`mcp/server.py`) queda FUERA de este cambio, explícitamente
     -- pendiente aparte, no una omisión.** Sigue devolviendo un único
     resultado con el contrato JSON de siempre: `resolve_current_opinion`/
     `answer_question` (`graph/build.py`) toman `candidates[0]` (el
     candidato top, orden determinista) para rellenar `structured_result`
     singular -- verificado con una llamada MCP real
     (`get_reevaluation_status("aspartame")`) que el JSON de salida no
     cambió de forma. `AnswerResult` gana 2 campos ADITIVOS con default
     (`substance_candidates`, `structured_results`) para quien SÍ quiera
     ver todos los candidatos -- MCP no los usa. Diseño de un esquema
     multi-resultado dedicado para MCP queda como trabajo futuro, no
     decidido ni empezado. **Los 6 tests de `tests/test_mcp_server.py`
     pasan SIN haberse modificado ni una línea** (verificado con `git
     diff --stat` tras la implementación) -- si algún cambio futuro de
     `graph/build.py` los rompe, es señal de acoplamiento no detectado a
     investigar, no un efecto colateral a parchear sobre la marcha.
   - **RESUELTO (misma sesión, continuación posterior) -- el "trabajo
     futuro, no decidido ni empezado" de arriba SÍ se decidió e
     implementó.** `search_efsa_opinion`/`get_reevaluation_status`
     devuelven ahora SIEMPRE `{"candidates_found": N, "candidates_shown":
     M, "results": [...]}` -- 1 elemento en `results` en el caso común,
     N en el ambiguo, NUNCA un objeto plano con un único resultado
     elegido en silencio. Tres alternativas evaluadas antes de decidir
     (mismo nivel de detalle que otras decisiones de este documento):
     - **(A, elegida) array siempre.** **(B, descartada)** objeto único +
       campo `candidates` opcional solo si hay ambigüedad. **(C,
       descartada)** las dos herramientas intactas + una tercera
       herramienta nueva de desambiguación.
     - **Por qué A, no solo "no hay cliente real que proteger" --**
       verificado antes de decidir, no como excusa a posteriori:
       `server.list_tools()` real muestra que `output_schema` de ambas
       herramientas es `{"additionalProperties": true}`, SIN ningún
       campo declarado formalmente -- no hay contrato de esquema MCP
       que romper con ningún cambio de forma, la "ruptura de
       compatibilidad" es puramente sobre código de cliente hipotético,
       no sobre el protocolo en sí. **Pero el motivo de fondo para
       preferir A sobre B/C es otro, y es el que pesó más: B y C dejan
       la honestidad ante la ambigüedad como OPCIONAL para el
       consumidor** -- un cliente que no sepa mirar el campo
       `candidates` (B), o que nunca llame a la tercera herramienta de
       desambiguación (C), vuelve a elegir un candidato en silencio sin
       enterarse de que había otros -- exactamente el problema que el
       resto del sistema (Nodo 1-4) pasó esta sesión entera eliminando.
       **Con A, la honestidad es ESTRUCTURAL:** no existe ninguna forma
       de leer la respuesta sin toparse con el array `results` y su
       longitud real, sin que el cliente tenga que saber buscar un
       campo opcional o una herramienta aparte.
     - **Plumbing nuevo necesario, no solo cambiar `mcp/server.py`:**
       `GraphState.candidates_total_found: int` (`graph/nodes.py`,
       poblado en `extract_entity_node` -- el total ANTES del recorte a
       `MAX_CANDIDATES_SHOWN`, distinto de `candidates_truncated: bool`,
       que solo dice SI hubo recorte, no CUÁNTOS había). `AnswerResult`
       gana `candidates_total_found: int = 0` (aditivo). `ReevaluationStatus`
       (hasta ahora con la forma singular de siempre, `substance_uuid`/
       `structured_result`) gana los mismos 3 campos plurales que
       `AnswerResult` ya tenía (`substance_candidates`,
       `structured_results`, `candidates_total_found`) -- necesarios
       porque ahora es `get_reevaluation_status` quien los consume
       directamente, no solo un caller hipotético futuro.
     - **Forma final de `results[i]`:** `search_efsa_opinion` -- por
       candidato: `chemical_name`, `match_type`, `match_score`,
       `dossier_title`, `doi`, `retrieved_chunks_count` (contado por
       `substance_uuid` sobre `retrieved_chunks`, NO dividido a partes
       iguales -- cada candidato cuenta solo SUS propios chunks).
       `answer` se queda FUERA del array, a nivel superior -- sigue
       siendo un ÚNICO texto narrativo (el Nodo 4 ya trata cada
       candidato por separado dentro de esa misma prosa, ver
       `_build_user_prompt`) -- partirlo en N respuestas exigiría N
       llamadas al LLM, coste innecesario para lo que una sola
       generación bien diseñada ya resuelve. `get_reevaluation_status`
       -- por candidato: los mismos campos que antes tenía el objeto
       plano (`dossier_found`, `dossier_title`, `doi`,
       `date_of_evaluation`, `adi_value`, `adi_unit`,
       `adi_justification`, `discussion_available`) más
       `chemical_name`/`match_type`/`match_score` para identificar cada
       fila. `safety_note` se queda fuera del array en ambas (constante
       fija, no varía por candidato).
     - **Verificado con llamada MCP real, no solo con los tests --
       tocoferol, no solo aspartamo** (`get_reevaluation_status("tocopherol")`,
       vía `asyncio.run(server.call_tool(...))`, sin mock):
       `candidates_found: 4, candidates_shown: 4`, con las 4 variantes
       reales (Delta/Gamma/DL-alpha/Tocopherol-rich extract) en
       `results`, mismo orden determinista que el resto del sistema.
       `search_efsa_opinion("aspartame")` confirma la regresión: sigue
       dando `candidates_found: 1, candidates_shown: 1`, sin cambio de
       comportamiento para el caso común.
     - **`tests/test_mcp_server.py` reescrito por completo para la nueva
       forma** (los 6 tests existentes, más 2 nuevos para el caso de
       2+ candidatos, uno por herramienta) -- a diferencia de la sesión
       anterior, aquí SÍ se tocó el archivo a propósito, porque ahora sí
       es la forma del propio MCP la que cambió, no un efecto colateral
       de otro cambio.
   - Detalle completo de la implementación, calibración y verificación:
     `PROGRESS.md`, sesión 19-ago-2026.
   - **Hallazgo real tras implementar, SIN resolver -- pendiente aparte
     explícito, verificado con llamada real, no una suposición: el caso
     ORIGINAL que motivó todo este diseño ('plai caramel') NO llega a
     usar `resolve_substance_candidates` en el pipeline completo
     (`answer_question`).** `resolve_substance_candidates("plai
     caramel")` funciona exactamente como se calibró (`Plain caramel`
     88.0 como candidato top, verificado directamente contra el store)
     -- pero probado con 4 formulaciones distintas de pregunta en
     lenguaje natural ("What is plai caramel used for...", "Is plai
     caramel safe...", "Tell me about plai caramel", "What does the
     EFSA opinion say about plai caramel?"), el Nodo 1
     (`extract_entity_node`) devuelve `NONE` en las 4 -- nunca propone
     ningún `substance_name`, así que `resolve_substance_candidates`
     nunca se llama (`extract_entity_node` solo la invoca `if
     substance_name else []`). Causa probable: la regla 4 del prompt del
     Nodo 1 (`NODE_1_ENTITY_EXTRACTION_PROMPT`, `graph/nodes.py`) --
     "No inventes un nombre si no estás razonablemente seguro -- en ese
     caso, responde NONE en vez de adivinar" -- filtra typos agresivos
     (una palabra que no reconoce como ningún nombre químico plausible)
     ANTES de que puedan llegar a la capa de fuzzy matching de esta
     sesión, que está diseñada precisamente para tolerar typos.
     **Contraste real con los typos que SÍ funcionan de extremo a
     extremo** (ver PROGRESS.md, sesión 19-ago-2026): "asprtame"/
     "Aspartam" sí resuelven porque el Nodo 1 SÍ propone un nombre (algo
     como "Aspartame", con la ortografía ya corregida por el propio
     LLM) -- el fuzzy matching downstream nunca hace falta invocarlo
     para esos casos, así que no son una prueba real de que la capa de
     esta sesión sea alcanzable desde una pregunta de usuario con un
     typo que el LLM no sepa corregir por su cuenta. "plai caramel" es
     el caso contrario: un typo lo bastante agresivo (o una sustancia lo
     bastante poco conocida por el LLM) para que el Nodo 1 no se atreva
     a proponer nada.
     **NO arreglado en esta sesión -- a propósito, decisión del
     usuario.** La solución PROBABLE a futuro (NO diseñada ni
     implementada, solo la dirección): relajar la regla 4 del Nodo 1
     para que proponga un nombre con menor confianza cuando la pregunta
     suena claramente a nombre de aditivo (aunque no lo reconozca con
     certeza), confiando en que el fuzzy matching downstream ya
     implementado filtre lo irrelevante (ver el umbral
     `FUZZY_MATCH_LOW_THRESHOLD` y el universo restringido a 246
     sustancias, ambos ya diseñados para absorber ruido). **Esto es un
     cambio de PROMPT del Nodo 1, con su propio riesgo de calibración
     (relajar la regla 4 puede aumentar falsos positivos de sustancias
     inventadas para preguntas que de verdad no mencionan ningún
     aditivo -- el motivo original de que la regla exista) -- no es una
     extensión trivial de lo de hoy, necesita su propia batería de
     pruebas antes de tocarse.** Si se retoma, verificar primero cuántas
     preguntas reales caen en este hueco (typo agresivo + Nodo 1
     rechaza) antes de relajar la regla a ciegas.
   - **Investigación de continuación (misma sesión, 19-ago-2026) --
     prompt relajado probado con llamadas reales, NO puesto en
     producción por decisión explícita del usuario ("no toques
     NODE_1_ENTITY_EXTRACTION_PROMPT en producción con esta muestra tan
     pequeña"). Marcado de PRIORIDAD BAJA, no bloqueante -- caso más
     idiosincrático que sistémico, ver por qué abajo.** Resultados
     completos de las dos baterías de prueba (5 typos + 6 preguntas sin
     sustancia, cada una con el prompt actual y una versión relajada de
     la regla 4) en el historial de la sesión, no repetidos aquí en
     detalle -- resumen de lo que importa para decisiones futuras:
     - **El fallo de "plai caramel" es sensible al FRASEO, no solo a la
       regla 4 -- mismo patrón ya diagnosticado (y tampoco resuelto
       todavía) para el Nodo 2 con TiO2/genotoxicidad más arriba (ver
       "DIAGNÓSTICO... la calidad del retrieval es sensible al fraseo
       de la pregunta").** Con el prompt ACTUAL sin cambios, la frase
       pelada `"plai caramel"` SÍ resuelve a `"Plain caramel"`; la MISMA
       cadena embebida en una pregunta completa ("What is plai caramel
       used for as a food additive?") da `NONE`, reproducido 2/2 veces
       de forma determinista (`temperature=0.0`). No es que la regla 4
       sea intrínsecamente incapaz de tolerar este typo -- es que el
       contexto de la frase completa cambia la respuesta.
     - **"plai caramel" NO es representativo de una clase amplia de
       typos rotos -- de 5 typos probados en forma de pregunta completa
       (`asprtame`, `titanum doxide`, `sorbik acid`, `xanthum gumm`,
       `plai caramel`), 4 YA resolvían bien con el prompt ACTUAL sin
       ningún cambio.** Solo "plai caramel" falla -- hipótesis no
       verificada más allá de la observación: "caramel" es una palabra
       común en inglés (a diferencia de "aspartame"/"titanium dioxide",
       más claramente nombres químicos), lo que puede hacer que el LLM
       dude más de si la pregunta se refiere a un aditivo concreto
       cuando está embebida en una frase completa.
     - **El prompt relajado SÍ elimina el `NONE`, pero no da el nombre
       esperado -- generaliza al nombre de GRUPO, no a la sal
       específica.** Para "plai caramel" en pregunta completa, propone
       `"Caramel colour"` (no `"Plain caramel"`), que
       `resolve_substance_candidates` resuelve a un único candidato
       confiado (`"Caramel colours"`, fuzzy 96,55) -- verificado que
       `"Caramel colours"` y `"Plain caramel"` apuntan al MISMO
       dictamen (mismo título, "re-evaluation of caramel colours (E 150
       a,b,c,d)", filas hermanas del mismo dossier de grupo con
       `Document UUID` distinto). Funcionalmente el usuario llegaría al
       contenido correcto, aunque no a la sal E150a concreta que
       nombró.
     - **Sin regresión detectada en los 6 casos de "sin sustancia"
       probados** (español e inglés, incluida "aditivos en general"
       sin nombrar ninguno -- el caso más parecido a un falso positivo
       posible): el prompt relajado sigue devolviendo `NONE` en los 6,
       igual que el actual. Dentro de esta muestra pequeña, el riesgo
       que motivó no tocar la regla a la ligera (inventar sustancias
       para preguntas sin ninguna) no se materializó -- pero la muestra
       (6 casos) es demasiado pequeña para tratarlo como garantía.
     - **Diseño futuro PREFERIBLE, según el usuario, sobre relajar la
       regla 4 globalmente -- NO diseñado en detalle, solo la
       dirección:** en vez de cambiar el umbral de confianza del Nodo 1
       para TODAS las preguntas (con el riesgo de calibración ya
       anotado arriba), una SEGUNDA PASADA aislada del Nodo 1 -- solo
       cuando la primera pasada da `NONE` pero la pregunta contiene
       palabras que podrían ser un nombre de sustancia mal escrito --
       que reformule/aísle esa entidad concreta antes de decidir. Mismo
       principio de intervención dirigida (no un cambio global) que se
       consideró para el caso de TiO2 en el Nodo 2 -- **ojo, ese caso
       tampoco tiene la reformulación implementada todavía, sigue
       siendo "diagnosticado, no resuelto" según su propia entrada más
       arriba** -- no lo trates como un precedente ya funcionando, es
       la misma clase de solución propuesta y sin construir en los dos
       sitios. Ninguna parte de esta segunda pasada (cuándo disparar,
       cómo aislar la entidad, qué prompt usar) está diseñada todavía.
   - **IMPLEMENTADO (misma sesión, 19-ago-2026, continuación posterior):
     mensaje honesto de "sustancia no identificada" cuando
     `substance_candidates` está vacío -- no bloqueado por la
     investigación de arriba (que sigue sin resolver), es un fix
     independiente del texto que se muestra en ese caso, no de la
     resolución en sí.**
     - **Decisión: enlace FIJO a la página de aditivos de EFSA, NO un
       buscador con parámetro.** Se investigó primero
       `https://www.efsa.europa.eu/en/search?query={término}` -- el
       parámetro `query=` es real (reaparece en los enlaces internos
       del propio sitio, y `curl` confirma que solo `/en/search`
       específicamente da 403 de CloudFront, no el resto del dominio) --
       pero **el usuario lo verificó en un navegador real y confirmó que
       NO filtra de verdad**: muestra el mismo listado genérico
       ("Results 1-10 of 18734", títulos sin relación con la sustancia)
       tanto para "aspartame" como para una cadena sin sentido -- SPA
       cuyo filtrado real (si existe) depende de JavaScript del lado
       del cliente que ni la verificación automatizada de esta sesión
       ni, según el usuario, el navegador real, mostraron funcionando.
       **Descartado.** En su lugar: `EFSA_FOOD_ADDITIVES_URL =
       "https://www.efsa.europa.eu/en/topics/topic/food-additives"`
       (`graph/nodes.py`) -- la página general de aditivos alimentarios
       de EFSA, verificada con `curl` (HTTP 200, sin bloqueo) y con
       `WebFetch` (landing page real, cita la cifra de 315 sustancias
       pre-2009 en reevaluación -- misma cifra ya verificada y citada
       en el README de este proyecto -- con enlaces a OpenEFSA y a
       dictámenes del EFSA Journal).
     - **Texto del mensaje, deliberadamente SIN la afirmación "esta
       sustancia no tiene reevaluaciones recientes"** -- esa frase no es
       verificable por el sistema y podría ser FALSA: el caso real
       "plai caramel" de esta misma sesión demostró que la sustancia SÍ
       existía y SÍ tenía un dictamen vigente indexado (Plain caramel,
       parte del grupo E150a-d) -- el fallo fue de RESOLUCIÓN DE NOMBRE
       (ver el punto de arriba, sensibilidad al fraseo del Nodo 1), no
       de ausencia real de reevaluación. Mensaje nuevo, honesto sobre la
       incertidumbre: "No se ha podido identificar esta sustancia
       dentro del corpus indexado (aditivos en reevaluación bajo el
       Reglamento UE 257/2010); puede que esté fuera de ese alcance, o
       que el nombre no se haya reconocido correctamente. Para buscar
       directamente en las fuentes de EFSA: [enlace fijo], usando el
       término "[query del usuario tal cual]"."
     - **El término incluido es `user_query` (la pregunta completa tal
       como la escribió el usuario), NO `substance_name`** (la
       propuesta normalizada/traducida del LLM del Nodo 1) -- decisión
       deliberada: en el caso donde este mensaje aplica,
       `substance_name` por definición no resolvió nada (o ni siquiera
       existe, si el Nodo 1 respondió `NONE`), así que mostrarlo en vez
       del texto original arriesgaría presentar al usuario un nombre
       que ni él escribió ni el sistema pudo verificar, como si fuera
       fiable. Verificado con llamada real
       (`answer_question("What is plai caramel used for as a food
       additive?")`): la respuesta final incluye el enlace fijo y cita
       la pregunta completa del usuario tal cual, sin reformularla.
     - **Implementación acotada a propósito, sin tocar el caso de 1
       candidato:** nueva función `_format_unresolved_substance_message`
       (`graph/nodes.py`), usada SOLO cuando `substance_candidates` está
       vacío (`_build_user_prompt`, ahora con 3 ramas explícitas: 0
       candidatos / 1 candidato / 2+ candidatos, en vez de agrupar 0 y 1
       juntos como antes). El mensaje genérico interno YA EXISTENTE de
       `_format_retrieved_chunks` (para "chunks vacíos +
       structured_result None") se mantiene SIN CAMBIOS -- sigue
       usándose para el caso distinto de un candidato SÍ identificado
       (1 o dentro de 2+) cuyo dictamen concreto no resuelve, donde el
       mensaje de "no se ha podido identificar la sustancia" no
       aplicaría con propiedad (la sustancia SÍ se identificó). Ese otro
       mensaje tiene una inconsistencia latente preexistente
       (potencialmente engañoso en ese caso concreto, ya presente antes
       de esta sesión) que NO se tocó aquí -- fuera de alcance de lo
       pedido, no una omisión.
   - **RESUELTO (misma sesión, continuación posterior) -- la
     inconsistencia latente de arriba SÍ se arregló, con un caso real
     verificado, no en abstracto.** Caso real usado:
     `"Olive leaf dry extract from O. europaea L."` -- ya documentado
     como caso de regresión en `test_openfoodtox_joins.py` desde la
     sesión 17-ago-2026 (`test_olive_leaf_extract_has_no_real_food_additive_opinion`):
     resuelve por nombre EXACTO en `SUB` (`substance_candidates` con 1
     elemento, tier `"exact"`), pero su única fila en `DOSSIER` es un
     dossier de PIENSO ANIMAL -- tras excluirlo por dominio,
     `current_reference_value_opinion` da `None`, sin ningún dictamen
     alimentario real. Probado con el pipeline real completo
     (`hybrid_retrieval_node` + `verify_currency_node` +
     `_build_user_prompt`, sin mock, contra el store y Chroma reales)
     ANTES de escribir el fix, para confirmar el bug en vivo, no solo en
     teoría: el prompt resultante se contradecía a sí mismo -- la línea
     `"Sustancia identificada: Olive leaf dry extract..."` aparecía
     justo encima de un mensaje que afirmaba `"no se ha podido resolver
     de forma exacta la sustancia mencionada en la pregunta"`.
     - **Distinción entre los DOS tipos de bug de mensaje cazados esta
       semana en este mismo archivo de nodos (`graph/nodes.py`) --
       relacionados pero de naturaleza distinta, no confundirlos:**
       1. **Incondicionalmente falso** (el bug de "el corpus de PDFs
          todavía no está indexado", sesión 19-ago-2026 anterior, caso
          tocoferol/E150a): el mensaje afirma algo que NUNCA es cierto
          en ningún contexto de la aplicación (el corpus SIEMPRE tiene
          67.827 chunks indexados) -- el fix fue cambiar el texto en sí,
          sin tocar la lógica de cuándo se dispara.
       2. **Condicionalmente falso por reutilización sin contexto**
          (este bug, "Olive leaf dry extract"): el mensaje ERA cierto en
          el contexto para el que se escribió originalmente (0
          candidatos -- "no se ha podido resolver... la sustancia"), y
          SIGUE siendo cierto ahí, pero la misma función
          (`_format_retrieved_chunks`) se reutilizaba sin distinguir ese
          caso del de "sí hay candidato, pero sin dictamen concreto" --
          donde la MISMA frase pasa a ser falsa. El fix real no fue solo
          cambiar el texto, fue separar los DOS CONTEXTOS que antes
          compartían una función: `_build_user_prompt` con 0 candidatos
          ahora usa `_format_unresolved_substance_message` (nunca
          `_format_retrieved_chunks`); `_format_retrieved_chunks` en sí
          se documentó con la precondición explícita de que solo se
          llama hoy cuando YA hay un candidato identificado, y su propio
          mensaje se corrigió para dejar de asumir lo contrario.
     - **Lección para el patrón general, más allá de este caso
       concreto:** un mensaje de error/degradación escrito para UN
       contexto específico (aquí, "0 candidatos") puede volverse
       engañoso si la misma función que lo produce se reutiliza después
       para un contexto distinto (aquí, "candidato identificado, sin
       dictamen") sin que la función sepa distinguirlos. No basta con
       revisar si un mensaje es cierto en abstracto -- hay que revisar
       en qué contextos REALES se dispara hoy (grep de callers, no
       suposición) antes de darlo por seguro.
     - Verificado también con una llamada real de extremo a extremo,
       incluida la generación del Nodo 4 (`generate_answer_node` con
       `llm_client` real, sin mock): la respuesta final nombra la
       sustancia correctamente y dice honestamente que no se encontró
       ningún dictamen vigente para ella en el corpus, sin ninguna
       contradicción con el nombre ya identificado.
     - Test de regresión con este caso exacto:
       `tests/test_nodes.py::test_build_user_prompt_olive_leaf_extract_real_case_does_not_self_contradict`
       (usa el `store` real, mismo patrón que los demás tests de casos
       reales conocidos de este proyecto -- no un mock).
3. **Integrar `END_SUM.Discussion.Discussion` en `OpinionReference`**,
   con el heurístico de detección de boilerplate ya validado en datos
   (ver "Hallazgos verificados": `len < 280` caracteres O duplicado
   exacto entre ≥2 dossiers distintos → boilerplate). **Prioridad
   movida por delante de la descarga de PDFs y el pipeline de
   chunking/embeddings/Chroma** (antes puntos 3-4, ver nota más abajo).
4. **Descarga MANUAL asistida por checklist de los PDFs (161
   dictámenes únicos -- ver "Hallazgos verificados", el corpus de 162
   tiene un duplicado real por errata de título)** -- ya NO es "escribir
   un script de descarga": las 3 fuentes probadas (Wiley directo,
   `efsa.europa.eu`, PubMed Central) bloquean peticiones automatizadas
   (ver "Hallazgos verificados"), así que la descarga es manual vía
   navegador normal. Checklist ya generado:
   `data/pdf_download_checklist.csv` /
   `data/pdf_download_checklist.md` (script:
   `scripts/generate_pdf_checklist.py`, re-ejecutar si el corpus
   cambia). Queda: descargar los 161 PDFs a mano y marcar la columna
   `descargado` según se avance -- trabajo del usuario, no de Claude en
   sesión.
5. Pipeline de chunking + embeddings locales (`sentence-transformers`) +
   Chroma — esto desbloquea el Nodo 2 (retrieval híbrido).
   **A tener en cuenta en el diseño del mapeo sustancia→archivo -- CIFRA
   CORREGIDA DOS VECES, no repitas ninguna de las anteriores: NO son 29
   (recuento inicial por `;` en `e_number` del checklist), NI 36
   (recuento intermedio por mismatch de columnas del checklist,
   sesión 17-ago-2026 continuación 2) -- la cifra validada con las
   hojas reales y filtrando por ADI real (sesión 17-ago-2026
   continuación 3) es: **20 títulos del corpus de 162 (12%) son
   genuinamente multi-sustancia, con 46 sustancias con ADI propio
   invisibles si solo se mira la fila superviviente del dedup por
   título.** Ni las columnas del checklist ni el `Document UUID` post-
   dedup de `unique_reevaluation_opinions()`/`current_reevaluation_corpus()`
   son fuente fiable -- ver "Hallazgos verificados" para la técnica
   verificada que sí recupera la lista completa (agrupar por título/DOI
   SIN deduplicar + filtrar por `Adi.lowerValue` no nulo + unión), y
   para por qué `current_reevaluation_corpus()` NO resuelve esto pese
   al nombre (su output tiene el mismo problema; solo su código interno
   usa la técnica correcta, sin exponerla).** No asumir un archivo por
   E-number 1:1 al indexar -- el chunking/vector store necesita poder
   resolver "¿en qué PDF(s) está la sustancia X?" como una relación
   muchos-a-uno (una sustancia -> un archivo, pero un archivo ->
   potencialmente varias sustancias).
   **RESUELTO (sesión 17-ago-2026, continuación 5):** la técnica ya está
   extraída como `OpenFoodToxStore.substances_per_dossier()` en
   `ingestion/openfoodtox.py`, con 3 tests de regresión verificados
   contra el xlsx real (nitritos/tartratos/glutamato).
   **Cobertura de los 99 dossiers que esa función deja vacíos --
   diagnosticada y diseñada, TODAVÍA NO implementada (continuación 6):**
   ver "Hallazgos verificados" para el desglose completo (73 sustancia
   única sin ADI tipo TiO2, 22 multi-sustancia sin ADI, 3 sin ningún
   enlace estructural tras arreglar la agrupación por DOI en vez de por
   título) y el diseño de resolución en 3 niveles (Nivel 1 = con ADI,
   Nivel 2 = mismo enlace sin exigir ADI, Nivel 3 =
   `substance_uuid_by_name()`/coincidencia de nombre en título) que
   cubre 161 de 162 dossiers, dejando 1 sin sustancia estructurada a
   propósito -- ese 1/162 (statement/sweeteners) se queda fuera del
   índice de retrieval POR DISEÑO, decisión confirmada por el usuario,
   ver el bullet "DECISIÓN TOMADA sobre el 1/162..." más arriba.
   **IMPLEMENTADO (sesión 17-ago-2026, continuación 12) --
   `ingestion/pdf_chunking.py`:** extracción de texto vía PyMuPDF
   directo (no el wrapper `PyMuPDFLoader`, necesita bbox/fuente por span
   -- ver el módulo para el hallazgo nuevo de esta sesión sobre pérdida
   de espacios en modo "dict" para ciertas fuentes bold incrustadas),
   detección de `section_heading` vía fuente tipográfica (cubre ambas
   convenciones, numerada y plana en mayúsculas), exclusión de tablas
   (bbox de `page.find_tables()` + patrón de leyenda "Table N:"),
   troceo con `RecursiveCharacterTextSplitter` por sección, y
   resolución de sustancia en 3 niveles
   (`resolve_dossier_substances`, con `substances_per_dossier(require_adi=...)`
   ya implementado con el parámetro que aquí seguía "propuesto").
   Script de ejecución: `scripts/build_chunk_index.py` (`--dry-run`/
   `--limit`/`--pdf`, no toca embeddings ni Chroma). Validado sobre 5
   PDF (los 3 de referencia + aspartamo E951 + 2 más vía `--limit 2`) --
   ver PROGRESS.md para el detalle de la sesión.
   **CORPUS COMPLETO PROCESADO (sesión 18-ago-2026): 161/161 PDF, sin
   errores, sin ningún PDF con 0 chunks.** 35.991 chunks, 67.827
   `RetrievedChunk` (dossier-sustancia-chunk); distribución de
   sustancias resueltas por tier (a nivel dossier-sustancia, 256 pares
   en total): tier 1 (con ADI) 105, tier 2 (enlace sin ADI) 149, tier 3
   (nombre en título) 2 -- exactamente los 2 casos conocidos
   (Shellac, sucralosa statement), ningún tier 3 nuevo inesperado. Un
   solo dossier sin sustancia resuelta, el mismo 1/162 ya documentado
   como excluido por diseño (`sinE_10.2903_j.efsa.2011.1996.pdf`).
   **Persistido en `data/processed/chunks.jsonl`** (gitignored, mismo
   motivo de licencia que `data/chroma/` -- texto literal de los PDF,
   ver la decisión de licencia más arriba): 67.827 líneas JSON, una por
   (chunk, sustancia resuelta), con campos de `RetrievedChunk` +
   `pdf_filename` + `chunk_group_id` (id compartido entre las N copias
   del mismo chunk que sirven a distintas sustancias -- el mismo
   esquema "N copias por chunk" ya diseñado para Chroma, ver
   "Hallazgos verificados"). Generado con
   `python scripts/build_chunk_index.py --all --save-jsonl
   data/processed/chunks.jsonl` -- `_run_all` escribe y hace `flush()`
   tras cada dossier, así que un fallo a mitad de la corrida (o del
   siguiente paso, embeddings) no obliga a reprocesar los PDF ya
   hechos. Existe también `--save-preview` (JSON con ejemplos, para
   inspección puntual, no pensado para el corpus completo -- usar
   `--save-jsonl` para eso).
   **Embeddings/Chroma -- COMPLETADO (sesión 18-ago-2026): corpus
   completo indexado y verificado en `data/chroma/`.**
   `ingestion/chroma_index.py` convierte filas de `chunks.jsonl` a
   entradas de Chroma (`to_chroma_metadata`, `chroma_id`,
   `compute_is_group_dossier`) -- esquema SIN `e_number`, ver el
   bullet de "Hallazgos verificados" "ESQUEMA FINAL, IMPLEMENTADO"
   para el porqué. `scripts/build_chroma_index.py` tiene 3 modos:
   `--test-batch` (300 chunks, colección efímera en memoria, para
   validar el diseño sin comprometerse al corpus completo),
   `--all` (indexa los 67.827 en la colección PERSISTENTE, borrando
   cualquier colección previa del mismo nombre antes -- no es
   incremental), `--verify` (conecta a la colección persistente ya
   creada y corre las consultas de verificación, sin reindexar --
   útil para comprobar el índice en cualquier momento posterior).
   **Corpus completo indexado de verdad, no solo proyectado:** 67.827
   chunks, 2,97 min reales, `collection.count() == 67827` verificado,
   597 MB en disco (`data/chroma/chroma.sqlite3`, colección
   `efsa_reevaluation_chunks`). 3 consultas de verificación con temas
   distintos (genotoxicidad, un caso específico conocido -- por qué se
   retiró TiO2 como aditivo, generaliza a incertidumbre de exposición
   dietética) -- las 3 con resultados temáticamente correctos, ver el
   detalle completo en el bullet de modelo de embeddings en
   "Decisiones de arquitectura ya tomadas" (incluida la advertencia
   GPU-vs-CPU para el tiempo de reconstrucción en despliegue).
   **RECONSTRUIDO con otro backend (sesión 18-ago-2026, misma fecha,
   más tarde) -- las cifras del párrafo anterior (597 MB, 2,97 min,
   GPU) quedan SUPERADAS, no las repitas como vigentes.** Nuevo módulo
   `ingestion/embedding_model.py::load_embedding_model()` -- backend
   ONNX + pesos int8, único punto de la base de código que instancia
   `SentenceTransformer` (ver el bullet "Backend de embeddings: ONNX
   int8, no torch" en "Decisiones de arquitectura ya tomadas" para el
   razonamiento completo, y `PROGRESS.md` continuación 19 para el
   detalle). Índice reconstruido de verdad: 67.827/67.827 chunks,
   ~22,4 min (CPU, sin GPU), 718 MB en disco. Verificado con las
   mismas 3 consultas de verificación (mismo patrón de calidad) y con
   una consulta real de extremo a extremo sobre aspartamo vía
   `answer_question` (ADI=40, DOI correcto, 5 chunks tier 1) -- para
   confirmar que indexado y retrieval usan ahora el MISMO backend, sin
   el desajuste fp32/int8 que existía antes de este cambio.
   **Nodo 2 (`hybrid_retrieval_node`) CONECTADO A CHROMA (sesión
   18-ago-2026, continuación 5)** -- ver `graph/nodes.py` en la lista
   de arriba para el detalle de diseño e implementación. Este punto
   (pendiente #5 de esta lista) queda completo de extremo a extremo:
   chunking -> embeddings -> índice Chroma -> Nodo 2 consultándolo.
6. **Detección de ambigüedad en el Nodo 3 -- DIFERIDO explícitamente
   (sesión 18-ago-2026), con evidencia de prevalencia, no implementado
   todavía y sin fecha de retomarlo salvo que cambie la evidencia.**
   Contexto completo: antes de la primera ejecución real del grafo
   ensamblado (`graph/build.py`), se auditó qué pasa hoy si
   `verify_currency_node` encuentra un caso ambiguo (varias
   `'EFSA opinion'` con fechas próximas, título no concluyente) --
   respuesta: **ni excepción ni manejo real, se elige `MAX(fecha)` en
   silencio, sin ninguna señal hacia el llamador** (`vigencia_ambigua`
   NO cubre este caso pese al nombre -- ver el comentario en
   `GraphState`/`verify_currency_node`, corregido en esta misma sesión
   para que no parezca protección real). Antes de decidir si
   implementarlo ahora o después, se pidió un diagnóstico de
   prevalencia sobre el corpus real completo.
   - **Metodología:** replicado el filtrado EXACTO de candidatos de
     `current_reference_value_opinion` (mismos pasos: `VALID_OPINION_TYPES`,
     rescate de dominio mal-etiquetado, exclusión de pienso animal),
     pero sin el pick final de `MAX(fecha)` -- en su lugar, para cada
     sustancia con 2+ candidatos supervivientes, se mide la distancia
     en días entre el candidato ganador (el que `MAX(fecha)` elegiría)
     y el más cercano de los demás. **Umbral de "ambiguo": 90 días**
     (probado también a 30 días, mismo resultado en ambos) -- elegido
     porque los dictámenes EFSA son eventos de adopción puntuales y
     fechados; una separación de 3+ meses es muy improbable que sea un
     artefacto del mismo evento (corrigendum, enmienda) y mucho más
     probable que sea un paso regulatorio genuinamente distinto.
     Metodología verificada contra el caso conocido de aspartamo antes
     de confiar en ella: reproduce exactamente los 4 candidatos
     esperados (2006, 2009×2, 2013 -- excluye correctamente el
     statement de 2011).
   - **Universo escaneado: 247 sustancias con enlace estructural
     resoluble en el corpus de reevaluación -- prácticamente todo el
     espacio de preguntas que el Nodo 3 puede responder hoy con el
     corpus actual, no una muestra.**
     - **Tier 1 (94 sustancias, con ADI resuelto):** 74 con un único
       candidato superviviente (ambigüedad estructuralmente imposible),
       0 sin ningún candidato, 20 con 2+ candidatos. **0 de esas 20
       caen dentro de 90 días** (ni de 30). El gap más pequeño de las
       94: **106 días** (Propane-1,2-diol, 2 candidatos) -- el segundo
       más pequeño, 182 días (Steviol glycosides, 7 candidatos). El
       resto, 280+ días, la mayoría 900+ días (2,5+ años -- ej. las 6
       sales de glutamato, todas a 924 días).
     - **Tier 2/3 (153 sustancias adicionales, sin ADI numérico --
       `require_adi=False` menos las 94 de tier 1, más Shellac vía
       tier 3):** 125 con un único candidato o una sola fecha
       parseable, 3 sin ningún candidato tras los filtros (caso ya
       manejado -- `current_reference_value_opinion` devuelve `None`,
       Node 4 ya lo comunica explícitamente, no es el caso de
       ambigüedad), 25 con 2+ candidatos. **0 de esas 25 caen dentro
       de 90 días** (ni de 30). El gap más pequeño: **160 días**
       (Beetroot Red/betanin, 2 candidatos) -- el resto, 246+ días.
     - **Total combinado: 0/247 sustancias ambiguas a 90 días, 0/247 a
       30 días.** El gap real más pequeño de TODO el corpus es 106
       días -- ningún caso cerca del umbral que hiciera dudar de la
       elección de 90 días sobre, digamos, 60 o 120.
   - **CAVEAT EXPLÍCITO, no ocultar: esto es una foto del corpus tal
     como está hoy (162 dictámenes, export de OpenFoodTox usado en
     este proyecto), no una garantía permanente.** El programa de
     reevaluación sigue activo (ver "Hallazgos verificados" más
     arriba, sección de cobertura del corpus -- follow-ups de plata
     E174, Patent Blue V E131, almidones modificados, entre otros
     conocidos en curso). Un futuro follow-up publicado cerca en el
     tiempo de un dictamen ya existente para la misma sustancia SÍ
     podría producir el caso ambiguo que hoy no existe -- este
     diagnóstico no lo descarta para siempre, solo confirma que no ha
     pasado todavía con los datos disponibles.
   - **Por qué se difiere, no por qué no importa:** impacto
     verificado = cero incidentes reales hasta hoy, frente a trabajo
     con impacto YA conocido y pendiente en esta misma lista (Nodo 4
     sin re-probar contra la API con el prompt actual -- pendiente #9;
     servidor MCP sin empezar -- pendiente #7; deploy -- pendiente #8).
     Implementar detección de ambigüedad ahora sería trabajo especulativo
     sobre un caso con prevalencia empírica de 0/247 en vez de sobre
     huecos con impacto ya confirmado. Si el corpus cambia
     (nuevos follow-ups) o aparece un caso real, re-ejecutar este mismo
     diagnóstico (no hay script permanente guardado -- fue una
     investigación puntual, replicable con el mismo método descrito
     arriba) antes de decidir si sigue siendo seguro diferirlo.
7. ~~Servidor MCP (`mcp/`, carpeta vacía todavía).~~ **HECHO (sesión
   18-ago-2026)** -- ver "Implementado" arriba (`mcp/server.py` +
   `tests/test_mcp_server.py`, 6 tests con stubs, 30/30 en verde). Sigue
   sin probarse con un cliente MCP real (Claude Desktop u otro) -- solo
   `server.list_tools()`/`server.call_tool()` invocados directamente en
   Python, tanto en la sesión de implementación como en los tests.
8. Deploy siguiendo la Opción A descrita arriba, en **Streamlit
   Community Cloud -- este ha sido el plan activo en TODO momento, no
   ha cambiado nunca.** **CORRECCIÓN (sesión 18-ago-2026, continuación
   21):** una versión anterior de esta entrada afirmó que el plan
   "cambió"/"pivotó" a HF Spaces -- eso era incorrecto, un error de
   redacción de Claude que el usuario corrigió directamente. HF Spaces
   solo se INVESTIGÓ como alternativa posible (motivado por el bloqueo
   de memoria medido en continuación 18), nunca se adoptó. Ver
   PROGRESS.md, continuaciones 19-21, para el detalle completo
   (incluida la corrección explícita in situ en la propia continuación
   19). **EN CURSO, NO CERRADO -- memoria parcialmente optimizada,
   repo preparado para un primer intento de deploy real, ese intento
   todavía no se ha hecho:**
   - Backend de embeddings cambiado a ONNX int8 (ver el bullet
     correspondiente en "Decisiones de arquitectura ya tomadas") --
     reduce el consumo medido de 1.870 MB a ~1.214 MB (combinado con
     `torch` CPU-only).
   - **`usecols` añadido a las 5 hojas de `OpenFoodToxStore` (sesión
     18-ago-2026, continuación 20) -- palanca de memoria adicional,
     medida sobre el pipeline completo, no solo sobre la carga del
     xlsx aislada.** Reduce el consumo medido de ~1.214 MB a
     **~1.150-1.170 MB** (2 corridas, mismo método de medición que las
     cifras anteriores) -- ahorro real de ~44-64 MB. **SIGUE ~126-145
     MB (12-14%) por encima del límite de ~1 GB de Streamlit Community
     Cloud** -- riesgo real y sin cerrar de cara al primer deploy.
     Investigada una palanca adicional (reescribir el pipeline de
     embeddings sobre ONNX Runtime directo, sin la capa de
     `sentence-transformers`) -- **el usuario decidió explícitamente NO
     implementarla todavía**, prefiriendo intentar el deploy real
     primero y observar el comportamiento empírico. Detalle completo
     de la auditoría de columnas (verificada contra cada caller real,
     no adivinada) y de la medición en `PROGRESS.md`, continuación 20.
   - **`requirements.txt` fija `torch==2.13.0+cpu` explícitamente**
     (vía `--extra-index-url https://download.pytorch.org/whl/cpu`,
     sesión 18-ago-2026, continuación 20) -- para que un `pip install
     -r requirements.txt` limpio en el host de deploy instale la
     versión ligera por defecto, sin depender de que alguien lo
     recuerde a mano. **El venv de desarrollo local SIGUE con el build
     CUDA** (`2.13.0+cu130`, instalado a mano, útil para reindexados
     rápidos) -- este pin de `requirements.txt` no lo cambia
     automáticamente; solo un entorno nuevo instalado desde cero (como
     el deploy) se lleva el build CPU-only. Con esto, el punto
     pendiente de "cómo gestionar la diferencia dev(GPU)/prod(CPU)" de
     la entrada anterior queda resuelto: `requirements.txt` es la
     única fuente, prod la sigue al pie de la letra, dev se desvía a
     propósito y a mano.
   - **Repo preparado para el primer intento de deploy real (sesión
     18-ago-2026, continuación 21) -- ver la nueva decisión de
     arquitectura "Datos pesados del deploy vía MEGA S4, nunca en git"
     más abajo, y `README.md` sección "Deploy en Streamlit Community
     Cloud" para los pasos exactos.** `src/efsa_rag/deploy_assets.py`
     (descarga xlsx + índice de Chroma desde MEGA S4 en el arranque,
     solo si no están ya en disco) +
     `scripts/upload_deploy_assets.py` (sube ambos, manual, un uso, con
     las credenciales del usuario) + `ui/app.py` conectado a esa
     descarga antes de tocar `graph.build`. La subida real a MEGA S4 y
     el primer deploy en share.streamlit.io quedan pendientes de que
     el usuario los haga desde su propia cuenta -- fuera del alcance de
     lo que Claude puede ejecutar (credenciales/cuenta del usuario).
     **El riesgo de memoria de arriba (~126-145 MB sobre el límite)
     sigue sin resolver** -- el primer deploy real puede fallar por OOM
     en la primera consulta; eso es un resultado esperado a día de
     hoy, no una sorpresa si ocurre.
9. **Re-probar el Nodo 4 con llamada real a la API usando el prompt
   actual -- PARCIALMENTE HECHO (sesión 18-ago-2026, continuación 10),
   no cerrar del todo.** `answer_question(...)` de extremo a extremo
   con aspartamo SÍ ejercitó `retrieved_chunks` NO vacío (5 fragmentos
   reales) y el campo `discussion_text` (con
   `discussion_is_boilerplate=True` para este caso concreto,
   correctamente omitido del texto citado). **NO ejercitó** el mensaje
   de "motivos opuestos" para ADI sin valor (aspartamo SÍ tiene ADI,
   camino tier 1 -- haría falta una consulta sobre una sustancia tier 2,
   ej. TiO2, para probar esa rama) ni el aviso de tier 3 en
   `_format_retrieved_chunks` (los 5 fragmentos de aspartamo son todos
   tier 1 -- haría falta una consulta sobre Shellac o el statement de
   sucralosa para ejercitar esa rama). Sigue sin existir ningún test
   automatizado de `generate_answer_node`/`answer_question` en
   `tests/test_nodes.py` (mismo patrón que los Nodos 1 y 2) -- solo
   verificación manual puntual hasta ahora, en las dos sesiones donde
   se ha probado (16-ago-2026 y 18-ago-2026).

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
dossiers distintos. Recalculada tres veces al cambiar el corpus: 118
(pre-fix de dominio) dio 32,2% (38/118); 136 (tras el rescate de
dominio, sesión 16-ago-2026) dio 29,4% (40/136) -- los 18 dossiers
rescatados por ese fix aportan sobre todo boilerplate (14 de 18 caen en
"toda la discusión es boilerplate"), así que el porcentaje bajó un poco
al ampliar el corpus, aunque el número absoluto de dossiers con
contenido no-boilerplate subió (38→40); **recalculada de nuevo tras el
cierre del Grupo A (sesión 17-ago-2026, corpus 136→162) da 25,3%
(41/162)** -- de los 26 dictámenes nuevos que entraron con el cierre
del Grupo A ("extension of use", "statement on", "reconsideration of
the ADI", "safety assessment... as a food additive"), 25 aportan solo
boilerplate y únicamente 1 aporta contenido no-boilerplate nuevo, así
que el porcentaje vuelve a bajar por el mismo mecanismo que la vez
anterior (documentos más cortos/específicos, no reevaluaciones
completas) aunque el número absoluto sube otra vez (40→41). Cifra
vigente, sobre los 162 dictámenes de reevaluación:

| Categoría | Dossiers (sobre 162) |
|---|---|
| Sin ninguna fila de `Discussion` en `END_SUM` | 9 (5,6%) |
| Con discusión, pero TODAS las filas son boilerplate | 112 (69,1%) |
| Con al menos una fila NO marcada como boilerplate | **41 (25,3%)** |

**Ese 25,3% es "no probado como boilerplate", no "confirmado como
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

Con esa salvedad, el 25,3% (o el subconjunto de ese 25,3% que resulte
genuinamente sustantivo) sigue siendo contenido narrativo real -- no
solo metadatos de citación -- sin depender de nada del pipeline de
PDFs. Esto permite un Nodo 4 con algo de contenido narrativo genuino
(no solo ADI + cita) mucho antes de tener PDFs descargados o Chroma
montado, aunque a menor escala de lo que se pensó inicialmente. El
pipeline de PDFs + RAG completo (puntos 4-5) sigue siendo necesario
para preguntas que requieran más profundidad de la que cabe en ese
párrafo -- y ahora también para el 74,7% de dossiers donde
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
