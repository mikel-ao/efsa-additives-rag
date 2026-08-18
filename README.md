# efsa-additives-rag

Asistente RAG sobre dictámenes regulatorios de reevaluación de aditivos
alimentarios (EFSA, Reglamento UE 257/2010).

Documentación completa (objetivo, audiencia, arquitectura, stack, roadmap,
limitaciones conocidas): [`docs/efsa-rag-proyecto.html`](docs/efsa-rag-proyecto.html)
-- ábrelo en el navegador.

## Estado actual

Scaffold inicial. Lógica ya verificada e implementada:
- `src/efsa_rag/ingestion/openfoodtox.py` -- cadena de joins determinista
  para el Nodo 3 (vigencia), verificada con el caso aspartamo (E 951).
- `src/efsa_rag/graph/nodes.py` -- contratos de los 4 nodos LangGraph,
  con la restricción de comunicación de riesgo del Nodo 4 ya fijada.
- `src/efsa_rag/ui/app.py` -- UI Streamlit con candado de refresco 24h.

Pendiente (ver docs/ -> ROADMAP.md): QA final del corpus, descarga de
PDFs, pipeline de chunking/embeddings, conexión real al LLM (DeepSeek),
servidor MCP.

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
