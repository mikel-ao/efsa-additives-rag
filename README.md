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

## Aviso

Herramienta de exploración de literatura regulatoria, no de asesoramiento
regulatorio ni médico.
