# efsa-additives-rag

[![Python](https://img.shields.io/badge/Python-black?style=for-the-badge&logo=python&logoColor=3776AB)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-black?style=for-the-badge&logo=langchain&logoColor=7FC8FF)](https://www.langchain.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-black?style=for-the-badge&logo=langgraph&logoColor=7FC8FF)](https://www.langchain.com/langgraph)
[![Streamlit](https://img.shields.io/badge/Streamlit-black?style=for-the-badge&logo=streamlit&logoColor=FF4B4B)](https://streamlit.io/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-black?style=for-the-badge)](https://www.trychroma.com/)
[![MCP](https://img.shields.io/badge/MCP-black?style=for-the-badge&logo=modelcontextprotocol&logoColor=white)](https://modelcontextprotocol.io/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-black?style=for-the-badge&logo=deepseek&logoColor=5786FE)](https://www.deepseek.com/)

**Índice**
- [Alcance](#alcance)
- [Estado actual](#estado-actual)
- [Setup](#setup)
- [Deploy en Streamlit Community Cloud](#deploy-en-streamlit-community-cloud)
- [Aviso](#aviso)

Asistente RAG sobre dictámenes regulatorios de reevaluación de aditivos
alimentarios (EFSA, Reglamento UE 257/2010).

**Arquitectura:** RAG orquestado con LangGraph -- 4 nodos con
enrutamiento condicional (extracción de entidad -> retrieval híbrido ->
verificación de vigencia -> generación). El grafo compila a un flujo
fijo con una única bifurcación condicional (si el Nodo 1 no resuelve
ninguna sustancia, se salta el Nodo 3) -- no es un sistema agéntico con
bucle de decisión abierto: ningún nodo decide en tiempo de ejecución
qué herramientas invocar o en qué orden, la secuencia está fijada de
antemano.

**Demo pública:** [efsa-additives-rag.streamlit.app](https://efsa-additives-rag.streamlit.app/)

## Alcance

Este proyecto cubre **exclusivamente** aditivos alimentarios en reevaluación
bajo el Reglamento (UE) n.º 257/2010 -- no pienso animal, no aromas, no
contaminantes, ningún otro programa regulatorio de EFSA.

- **315** aditivos alimentarios son elegibles para este programa: los
  aprobados en la Unión Europea antes del 20 de enero de 2009 (fuente:
  [EFSA, "Food additives"](https://www.efsa.europa.eu/en/topics/topic/food-additives)
  -- "the 315 food additives that were approved in the EU before 20 January
  2009").
- **162** dictámenes únicos identifica el corpus de este proyecto dentro de
  ese programa (filtro `Domain.FoodDomain == 'food additives'` + patrón de
  título de reevaluación, más rescate de dictámenes mal etiquetados con otro
  dominio -- ver `CLAUDE.md`, "Hallazgos verificados"). Es un corpus de
  trabajo, **no validado al 100 % contra una lista oficial cerrada de
  EFSA** -- el programa sigue activo (hay calls for data en curso no
  cubiertas todavía: ribonucleótidos E 626-635, ácido glucónico E 574-579,
  aditivos en forma gaseosa).
- **161** de esos 162 dictámenes corresponden a PDFs únicos ya descargados,
  troceados e indexados (162 menos 1 duplicado real por errata de título --
  el caso de sacarina) -- **67.827 fragmentos narrativos** en el índice de
  retrieval (Chroma), sobre 161/161 PDF procesados sin errores.
- **247** sustancias del corpus tienen un enlace estructural resoluble a un
  dictamen vigente (la unidad comparable con las 315 elegibles: sustancia,
  no documento -- un solo dictamen puede cubrir varias sustancias a la vez,
  ver `CLAUDE.md`).

Estas cifras no se conflacionan entre sí a propósito: "dictámenes",
"PDFs" y "sustancias" son unidades de conteo distintas en este proyecto
-- ver `CLAUDE.md` si necesitas la cadena de joins exacta detrás de cada
una.

## Estado actual

Grafo completo implementado y ejecutado de extremo a extremo (Nodo 1 --
extracción de entidad -> Nodo 2 -- retrieval híbrido -> Nodo 3 --
verificación de vigencia -> Nodo 4 -- generación), probado con
consultas reales, no solo con mocks:
- `src/efsa_rag/ingestion/openfoodtox.py` -- cadena de joins
  determinista para ADI/TDI, vigencia y resolución de sustancias por
  dossier, verificada contra el xlsx real de OpenFoodTox 3.0.
- `src/efsa_rag/ingestion/pdf_chunking.py` +
  `src/efsa_rag/ingestion/chroma_index.py` -- los 161 PDFs del corpus
  troceados, embebidos (`sentence-transformers`, backend ONNX int8) e
  indexados en Chroma (ver "Alcance" arriba para las cifras exactas).
- `src/efsa_rag/graph/nodes.py` + `src/efsa_rag/graph/build.py` -- los
  4 nodos LangGraph conectados y compilados, incluida la restricción
  de comunicación de riesgo del Nodo 4 (el ADI nunca se redacta como
  umbral de toxicidad) y la resolución multi-candidato del Nodo 1:
  cuando varios nombres de `SUB.ChemicalName` son razonablemente
  parecidos a la sustancia mencionada en la pregunta (fuzzy matching
  con `rapidfuzz`, restringido a las 246 sustancias con dictamen
  resoluble del corpus, más normalización de guion/espacio para casos
  como "Alpha tocopherol" vs. "Alpha-tocopherol"), el sistema nunca
  elige uno en silencio -- resuelve y presenta todos los candidatos
  plausibles por separado, cada uno con su propio dictamen vigente y
  sus propios fragmentos narrativos, dejando que el usuario identifique
  cuál buscaba.
- `src/efsa_rag/mcp/server.py` -- servidor MCP con dos herramientas
  (`search_efsa_opinion`, `get_reevaluation_status`), ambas con esquema
  de salida rediseñado a **array de resultados siempre**
  (`{"candidates_found", "candidates_shown", "results": [...]}`) --
  nunca un objeto singular con un candidato elegido en silencio,
  consistente con la disciplina de resolución multi-candidato de
  arriba. Probado en aislamiento, todavía no con un cliente MCP real
  (Claude Desktop u otro).
- `src/efsa_rag/ui/app.py` -- demo Streamlit: candado de refresco 24h,
  límites de consulta por presupuesto diario, y descarga de los datos
  pesados desde MEGA S4 en el arranque (ver "Deploy" más abajo).

Pendiente (detalle completo y prioridad real en `CLAUDE.md`, no en
ningún `ROADMAP.md` -- ese archivo no existe en este repo): QA del
corpus de 162 dictámenes contra las calls for data activas; casos de
typo agresivo o nombre poco conocido que el Nodo 1 rechaza identificar
del todo antes de que la resolución multi-candidato pueda intervenir
(ej. "plai caramel" dentro de una pregunta completa -- el LLM responde
`NONE` sin proponer ningún nombre, así que el fuzzy matching nunca
llega a invocarse); y detección de ambigüedad en el Nodo 3 (diferida a
propósito, 0 casos ambiguos detectados sobre 247 sustancias hasta hoy).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # rellenar DEEPSEEK_API_KEY

# Descargar manualmente el export de OpenFoodTox 3.0 desde Zenodo
# (dataset "OpenFoodTox 3.0", ~22.6 MB) y colocarlo en:
#   data/raw/OFT3_0_export_repository.xlsx

pytest  # los tests de joins se saltan automáticamente sin el xlsx
```

## Deploy en Streamlit Community Cloud

**La demo está desplegada y funcionando en producción:**
[efsa-additives-rag.streamlit.app](https://efsa-additives-rag.streamlit.app/)
(primer deploy exitoso, 18-ago-2026). Verificado con consultas reales
en producción, no solo en local: ADI de aspartamo (caso de referencia
tier 1), resolución multi-candidato de tocoferol (4 candidatos
presentados por separado, sin fusionarlos), dióxido de titanio (TiO2,
caso conocido de reevaluación), y sustancias no identificadas por el
corpus (mensaje honesto, sin afirmar falsamente que "el corpus todavía
no está indexado" -- ver `CLAUDE.md`, pendiente #2).

El repo de GitHub se queda público y sin datos pesados (`data/raw/*.xlsx`,
`data/chroma/`, `data/processed/` siguen en `.gitignore`) -- casi la mitad
del corpus de PDFs no tiene licencia abierta y la otra mitad (CC BY-ND) no
permite redistribuir fragmentos, así que esos datos nunca van a git, ni
siquiera vía Git LFS en un repo privado (ver CLAUDE.md, "Decisiones de
arquitectura ya tomadas"). En su lugar, la app los descarga sola desde
almacenamiento externo (MEGA S4, API S3-compatible) la primera vez que
alguien hace una consulta real tras un arranque del contenedor.

**Paso 1 -- subir los datos a tu bucket (una vez, y cada vez que
reindexes en local):**

```bash
export MEGA_S4_ENDPOINT_URL=...   # ver help.mega.io/megas4/setup-guides/mega-s4-endpoint-urls
export MEGA_S4_BUCKET=...
export MEGA_S4_ACCESS_KEY_ID=...
export MEGA_S4_SECRET_ACCESS_KEY=...
export MEGA_S4_REGION=...          # si tu endpoint lo requiere

python scripts/upload_deploy_assets.py --dry-run   # revisa qué se subiría
python scripts/upload_deploy_assets.py              # sube de verdad (~600 MB)
```

**Paso 2 -- crear la app en [share.streamlit.io](https://share.streamlit.io):**
1. "Create app" -> selecciona el repo, la rama, y como archivo de
   entrada `src/efsa_rag/ui/app.py`.
2. "Advanced settings" -> Python 3.12 (o el que tengas fijado en
   `pyproject.toml`, `>=3.11`).
3. "Advanced settings" -> "Secrets": pega el contenido de tu
   `secrets.toml` (formato TOML, no `.env`) con las mismas claves que
   `.env.example`:
   ```toml
   DEEPSEEK_API_KEY = "..."
   MEGA_S4_ENDPOINT_URL = "..."
   MEGA_S4_BUCKET = "..."
   MEGA_S4_ACCESS_KEY_ID = "..."
   MEGA_S4_SECRET_ACCESS_KEY = "..."
   MEGA_S4_REGION = "..."
   ```
   Streamlit expone estas claves como `os.environ` automáticamente --
   el código las lee tal cual (`os.environ["DEEPSEEK_API_KEY"]`,
   `efsa_rag/deploy_assets.py`), no hace falta ningún cambio de código
   para que esto funcione.
4. Deploy.

**Llegar a un deploy que arrancara y respondiera de verdad exigió tres
optimizaciones de memoria reales, medidas antes de aplicarlas, no
teóricas:**
- Backend de embeddings cambiado a ONNX + pesos int8 (en vez del
  "calentamiento" de PyTorch en la primera inferencia, ~400 MB por sí
  solo) -- ver "Backend de embeddings: ONNX int8, no torch" en
  `CLAUDE.md`.
- `torch` fijado a su build CPU-only (`torch==2.13.0+cpu`) vía
  environment markers en `requirements.txt` (`sys_platform == "linux"`),
  para que el pin se aplique en el entorno de deploy sin depender de
  que alguien recuerde comentarlo/descomentarlo a mano por plataforma.
- `usecols` explícito en las 5 hojas que carga `OpenFoodToxStore` --
  evita traer a memoria columnas del xlsx que ningún caller usa.

**Y varios ajustes de configuración**, distintos de la optimización de
memoria, encontrados con el arranque real fallando y diagnosticados
antes de corregir (no adivinados):
- `deploy_assets.py` no cargaba `.env` -- `load_dotenv(dotenv_path=...)`
  explícito añadido, porque las credenciales de MEGA S4 no se leían
  solas en una máquina nueva sin nada exportado a mano en la terminal
  (sin efecto en el propio Streamlit Cloud, donde las credenciales
  llegan vía "Secrets" como variables de entorno reales, no por `.env`).
- `-e .` añadido a `requirements.txt` -- Streamlit Community Cloud solo
  ejecuta `pip install -r requirements.txt` al desplegar, sin ningún
  paso equivalente al `pip install -e .` que sí se hace en desarrollo
  local; sin esto, `import efsa_rag` fallaba en el arranque
  (`ModuleNotFoundError`) antes incluso de intentar cargar el grafo.

El proceso completo, con las cifras de memoria medidas en cada paso y
cada bug encontrado en el camino, está documentado con detalle en
`CLAUDE.md` y `PROGRESS.md` si quieres reproducirlo o entender por qué
cada pieza está donde está.

**Nota de honestidad sobre la medición de memoria que motivó las
optimizaciones de arriba:** medida de forma aislada en local (Streamlit
+ Chroma + modelo de embeddings + una consulta real, sin el resto de la
infraestructura de Streamlit Cloud alrededor), el pipeline llegó a
~1.150-1.170 MB, por encima del límite nominal de ~1 GB del tier
gratuito -- una señal de riesgo real en su momento, no descartada a la
ligera. El deploy real terminó arrancando y respondiendo consultas sin
problema pese a esa cifra, lo que sugiere que la medición aislada no es
1:1 representativa del límite aplicado en producción. No se ha vuelto a
medir memoria dentro del propio contenedor de producción -- si en el
futuro empieza a fallar por OOM bajo más carga, ese es el primer sitio
a mirar.

## Aviso

Herramienta de exploración de literatura regulatoria, no de asesoramiento
regulatorio ni médico.
