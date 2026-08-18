"""
Ensamblado del grafo LangGraph completo -- Nodo 1 (extracción de
entidad) -> Nodo 2 (retrieval híbrido) -> Nodo 3 (verificación de
vigencia) -> Nodo 4 (generación), con una arista condicional para el
caso de que el Nodo 1 no resuelva `substance_uuid`.

Decisión de diseño explícita -- qué pasa si el Nodo 1 no resuelve
`substance_uuid` (LLM respondió NONE, o el nombre no coincidió exacto
en `SUB`, ver graph/nodes.py::extract_entity_node):

**El grafo SIGUE hasta el Nodo 4, no corta antes.** Pero NO llama al
Nodo 3 en ese caso -- `verify_currency_node` exige `substance_uuid` no
nulo y lanza `ValueError` si se le llama sin él (ver su código, sin
cambios aquí), así que sería un crash, no una respuesta degradada. La
arista condicional después del Nodo 2 decide: si hay
`substance_uuid`, va al Nodo 3 y de ahí al Nodo 4 (camino normal); si
no, salta el Nodo 3 y va DIRECTO al Nodo 4.

Por qué seguir hasta el Nodo 4 en vez de cortar antes: el Nodo 4 ya
está diseñado para degradar con gracia en ambos casos de falta de
datos --
- `structured_result` nunca se pone en el estado (el Nodo 3 no se
  llamó) -- `state.get("structured_result")` devuelve `None` exactamente
  igual que si el Nodo 3 lo hubiera puesto a `None` explícitamente
  (`GraphState` es un `TypedDict(total=False)`), y
  `_format_structured_result(None)` ya cubre ese caso con el mensaje
  "No se ha podido determinar un dictamen vigente..." (regla 4 de
  `NODE_4_GROUNDING_RULES`).
- `retrieved_chunks` queda vacío porque el Nodo 2 ya deja `[]` sin
  llamar a Chroma cuando no hay `substance_uuid` (ver
  `hybrid_retrieval_node`) -- `_format_retrieved_chunks([])` ya cubre
  ese caso.

Es decir: el Nodo 4 puede producir una respuesta coherente ("no he
podido identificar de qué aditivo hablas") sin que haga falta ningún
código nuevo aquí -- los Nodos 2 y 4 ya se diseñaron pensando en este
caso en sesiones anteriores. Cortar el grafo antes del Nodo 4 dejaría
al usuario sin ninguna respuesta en vez de una explicación útil, que es
peor experiencia y no ahorra ninguna llamada cara (el Nodo 1 ya se
llamó, que es la única llamada al LLM en el camino corto).

`vigencia_ambigua` (poblado solo por el Nodo 3) queda sin definir en el
camino corto -- verificado que ningún otro nodo lo lee, así que no hay
efecto secundario por saltárselo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from efsa_rag.graph.llm_client import build_default_client
from efsa_rag.graph.nodes import (
    GraphState,
    NodeDependencies,
    RetrievedChunk,
    extract_entity_node,
    generate_answer_node,
    hybrid_retrieval_node,
    verify_currency_node,
)
from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore, OpinionReference

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
XLSX_PATH = REPO_ROOT / "data" / "raw" / "OFT3_0_export_repository.xlsx"
CHROMA_PERSIST_DIR = REPO_ROOT / "data" / "chroma"
CHROMA_COLLECTION_NAME = "efsa_reevaluation_chunks"  # ver scripts/build_chroma_index.py
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


def _route_after_retrieval(state: GraphState) -> str:
    """Arista condicional -- ver el razonamiento completo en el
    docstring del módulo. Único punto de la orquestación que decide si
    el Nodo 3 se llama o no."""
    return "verify_currency" if state.get("substance_uuid") else "generate_answer"


def build_graph(deps: NodeDependencies) -> CompiledStateGraph:
    """Construye y compila el grafo para un `NodeDependencies` concreto
    -- los 4 nodos se registran como closures que capturan `deps`,
    porque las funciones de nodo (`graph/nodes.py`) toman
    `(state, deps)`, no solo `state`, y `StateGraph.add_node` espera
    una función de un único argumento (`state`). No se muta nada de
    `deps` al compilar -- se puede reconstruir el grafo con otro
    `NodeDependencies` (ej. otro backend de LLM) sin tocar esta
    función."""
    workflow = StateGraph(GraphState)

    workflow.add_node("extract_entity", lambda state: extract_entity_node(state, deps))
    workflow.add_node("hybrid_retrieval", lambda state: hybrid_retrieval_node(state, deps))
    workflow.add_node("verify_currency", lambda state: verify_currency_node(state, deps))
    workflow.add_node("generate_answer", lambda state: generate_answer_node(state, deps))

    workflow.set_entry_point("extract_entity")
    workflow.add_edge("extract_entity", "hybrid_retrieval")
    workflow.add_conditional_edges(
        "hybrid_retrieval",
        _route_after_retrieval,
        {"verify_currency": "verify_currency", "generate_answer": "generate_answer"},
    )
    workflow.add_edge("verify_currency", "generate_answer")
    workflow.add_edge("generate_answer", END)

    return workflow.compile()


def build_default_deps() -> NodeDependencies:
    """Instancia real de `NodeDependencies` -- store de OpenFoodTox,
    colección Chroma persistente ya poblada (ver
    scripts/build_chroma_index.py --all), modelo de embeddings (el
    MISMO usado para indexar) y cliente LLM (`build_default_client()`,
    ya existente en graph/llm_client.py -- lee `EFSA_RAG_LLM_BACKEND`
    del entorno, no se reinventa aquí).

    Carga recursos reales (modelo de embeddings, conexión a Chroma) --
    no llamar por consulta, ver `answer_question` para el cacheo."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    store = OpenFoodToxStore(XLSX_PATH)

    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    vectorstore = chroma_client.get_collection(CHROMA_COLLECTION_NAME)

    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    llm_client = build_default_client()

    return NodeDependencies(
        store=store,
        vectorstore=vectorstore,
        embedding_model=embedding_model,
        llm_client=llm_client,
    )


# Cacheados a nivel de módulo -- `build_default_deps()` carga un modelo
# de embeddings y abre una conexión a Chroma, recursos costosos de
# recrear en cada pregunta. `answer_question` los inicializa una única
# vez (primera llamada) y reutiliza el grafo ya compilado en las
# siguientes. Si se necesitan unos `deps`/grafo distintos (tests, otro
# backend), usar `build_graph(deps)` directamente en vez de
# `answer_question`.
_default_deps: NodeDependencies | None = None
_default_graph: CompiledStateGraph | None = None


@dataclass(frozen=True)
class AnswerResult:
    """Salida de `answer_question` -- el texto de respuesta MÁS el
    contexto que lo fundamentó, para poder auditar fundamentación sin
    tener que reproducir el retrieval a mano (ver CLAUDE.md, "Decisiones
    de arquitectura ya tomadas" -- motivado directamente por una sesión
    de auditoría real donde hubo que reconstruir `retrieved_chunks` con
    una llamada aparte a `hybrid_retrieval_node` porque `answer_question`
    solo devolvía el string).

    `answer` sigue siendo el texto final de cara al usuario -- esto NO
    lo sustituye, lo acompaña. `retrieved_chunks` y `structured_result`
    son exactamente los mismos objetos que vio el Nodo 4 al construir el
    prompt (no una reconstrucción aparte) -- tomados directamente del
    estado final del grafo tras `.invoke(...)`."""

    answer: str
    retrieved_chunks: list[RetrievedChunk]
    structured_result: OpinionReference | None


def answer_question(query: str) -> AnswerResult:
    """Punto de entrada simple: pregunta en lenguaje natural ->
    `AnswerResult` (respuesta + contexto de fundamentación). Inicializa
    `NodeDependencies` reales (una sola vez, cacheado) y ejecuta el
    grafo completo.

    Devuelve `AnswerResult`, NO un `str` -- cambio de contrato (sesión
    18-ago-2026, continuación 11) respecto a la versión anterior de esta
    función. Verificado con `grep` antes del cambio: no había ningún
    caller real en el repo (`ui/app.py`, tests, scripts) que esperase el
    `str` de antes -- solo invocaciones manuales sueltas en sesiones de
    verificación, no código persistido. Si en el futuro `ui/app.py` u
    otro caller empieza a usar esta función, debe leer `.answer`, no
    tratar el resultado como string directamente."""
    global _default_deps, _default_graph

    if _default_deps is None:
        _default_deps = build_default_deps()
    if _default_graph is None:
        _default_graph = build_graph(_default_deps)

    result = _default_graph.invoke({"user_query": query})
    return AnswerResult(
        answer=result["answer"],
        retrieved_chunks=result.get("retrieved_chunks") or [],
        structured_result=result.get("structured_result"),
    )


if __name__ == "__main__":
    # Solo dibuja la estructura del grafo (Mermaid) -- NO llama a
    # ningún LLM ni toca Chroma/xlsx. `NodeDependencies` con todos los
    # campos en None basta para compilar y dibujar: `deps` solo se usa
    # DENTRO de las funciones de nodo cuando el grafo se invoca de
    # verdad (`.invoke(...)`), nunca durante `.compile()`/`.get_graph()`.
    placeholder_deps = NodeDependencies(store=None, vectorstore=None, embedding_model=None, llm_client=None)
    graph = build_graph(placeholder_deps)
    print(graph.get_graph().draw_mermaid())
