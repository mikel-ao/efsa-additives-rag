# efsa-additives-rag

Asistente RAG sobre dictámenes regulatorios de reevaluación de aditivos
alimentarios (EFSA, Reglamento UE 257/2010).

Documentación completa (objetivo, audiencia, arquitectura, stack, roadmap,
limitaciones conocidas): [`docs/efsa-rag-proyecto.html`](docs/efsa-rag-proyecto.html)
-- ábrelo en el navegador.

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
  umbral de toxicidad).
- `src/efsa_rag/mcp/server.py` -- servidor MCP con dos herramientas
  (`search_efsa_opinion`, `get_reevaluation_status`) -- probado en
  aislamiento, todavía no con un cliente MCP real (Claude Desktop u
  otro).
- `src/efsa_rag/ui/app.py` -- demo Streamlit: candado de refresco 24h,
  límites de consulta por presupuesto diario, y descarga de los datos
  pesados desde MEGA S4 en el arranque (ver "Deploy" más abajo).

Pendiente (detalle completo y prioridad real en `CLAUDE.md`, no en
ningún `ROADMAP.md` -- ese archivo no existe en este repo): QA del
corpus de 162 dictámenes contra las calls for data activas, resolución
más robusta de nombre de sustancia en el Nodo 1 (español, E-numbers, y
variantes con prefijo/sufijo del mismo nombre -- mitigado
parcialmente, sin cerrar), detección de ambigüedad en el Nodo 3
(diferida a propósito, 0 casos ambiguos detectados sobre 247 sustancias
hasta hoy), y el primer deploy real en Streamlit Community Cloud (ver
el riesgo de memoria documentado en la sección de deploy).

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

**Riesgo conocido, no resuelto, documentado a propósito (no lo des por
sorpresa si el primer intento falla) -- ver CLAUDE.md/PROGRESS.md,
sesión 18-ago-2026, continuaciones 18-21 para el detalle completo de
la medición:** el pipeline completo (Streamlit + Chroma + modelo de
embeddings + una consulta real) mide **~1.150-1.170 MB de RAM**, por
encima del límite de ~1 GB del tier gratuito de Streamlit Community
Cloud -- con las tres optimizaciones ya aplicadas (ONNX int8, torch
CPU-only, `usecols` en `OpenFoodToxStore`). El primer intento de deploy
real puede fallar por OOM en la primera consulta; si eso pasa, no es un
fallo de configuración de este documento, es el límite de memoria ya
conocido y sin cerrar.

## Aviso

Herramienta de exploración de literatura regulatoria, no de asesoramiento
regulatorio ni médico.
