"""
Modelo de embeddings compartido entre el indexado offline
(`scripts/build_chroma_index.py`) y el retrieval online (Nodo 2,
`graph/build.py`). Ambos DEBEN usar exactamente el mismo backend y el
mismo archivo de pesos -- si no coinciden, el espacio vectorial de las
queries en tiempo de consulta no coincide con el de los chunks ya
indexados (ver CLAUDE.md/PROGRESS.md para el desajuste fp32/int8 que
motivó esta restricción).

Backend ONNX + pesos int8 cuantizados, no el backend `torch` por
defecto -- decisión de memoria: mide ~32% menos RAM que `torch` en el
experimento aislado, y `torch` sigue siendo dependencia dura del
paquete `sentence-transformers` de todas formas (el import de la
librería falla incluso queriendo usar solo el backend ONNX si `torch`
no está instalado) -- el ahorro viene de evitar el "calentamiento"
de la primera inferencia de PyTorch en tiempo de consulta, no de dejar
de cargar `torch`. Requiere el extra `sentence-transformers[onnx]`
instalado (`optimum` + `onnxruntime` -- este último ya es dependencia
transitiva de `chromadb`, no es 100% peso nuevo).
"""

from __future__ import annotations

EMBEDDING_MODEL_REPO_ID = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_ONNX_FILE = "onnx/model_qint8_avx512_vnni.onnx"
EMBEDDING_DIMS = 384


def load_embedding_model():
    """Instancia el modelo de embeddings con el backend/archivo
    acordados -- único punto de la base de código donde se construye un
    `SentenceTransformer`, para que el indexado y el retrieval no
    puedan desincronizarse por editar una copia y olvidar la otra."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        EMBEDDING_MODEL_REPO_ID,
        backend="onnx",
        model_kwargs={"file_name": EMBEDDING_ONNX_FILE},
    )
