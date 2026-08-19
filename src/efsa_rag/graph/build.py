"""
Ensamblado del grafo LangGraph completo -- Nodo 1 (extracción de
entidad) -> Nodo 2 (retrieval híbrido) -> Nodo 3 (verificación de
vigencia) -> Nodo 4 (generación), con una arista condicional para el
caso de que el Nodo 1 no resuelva ningún candidato en
`substance_candidates`.

Decisión de diseño explícita -- qué pasa si el Nodo 1 no resuelve
ningún candidato (LLM respondió NONE, o el nombre no coincidió con
NINGÚN candidato -- ni exacto, ni normalizado, ni fuzzy -- ver
graph/nodes.py::extract_entity_node y
OpenFoodToxStore.resolve_substance_candidates):

**El grafo SIGUE hasta el Nodo 4, no corta antes.** Pero NO llama al
Nodo 3 en ese caso -- `verify_currency_node` exige al menos un candidato
y lanza `ValueError` si se le llama sin ninguno (ver su código, sin
cambios aquí), así que sería un crash, no una respuesta degradada. La
arista condicional después del Nodo 2 decide: si `substance_candidates`
no está vacío, va al Nodo 3 y de ahí al Nodo 4 (camino normal); si está
vacío, salta el Nodo 3 y va DIRECTO al Nodo 4.

Por qué seguir hasta el Nodo 4 en vez de cortar antes: el Nodo 4 ya
está diseñado para degradar con gracia en ambos casos de falta de
datos --
- `structured_results` nunca se pone en el estado (el Nodo 3 no se
  llamó) -- `state.get("structured_results")` devuelve `None`
  exactamente igual que si el Nodo 3 lo hubiera puesto a `{}`
  explícitamente (`GraphState` es un `TypedDict(total=False)`), y
  `_build_user_prompt` con `substance_candidates` vacío ya cubre ese
  caso con el mensaje "No se ha podido determinar un dictamen
  vigente..." (regla 4 de `NODE_4_GROUNDING_RULES`).
- `retrieved_chunks` queda vacío porque el Nodo 2 ya deja `[]` sin
  llamar a Chroma cuando `substance_candidates` está vacío (ver
  `hybrid_retrieval_node`) -- `_format_retrieved_chunks([])` ya cubre
  ese caso.

Es decir: el Nodo 4 puede producir una respuesta coherente ("no he
podido identificar de qué aditivo hablas") sin que haga falta ningún
código nuevo aquí -- los Nodos 2 y 4 ya se diseñaron pensando en este
caso en sesiones anteriores. Cortar el grafo antes del Nodo 4 dejaría
al usuario sin ninguna respuesta en vez de una explicación útil, que es
peor experiencia y no ahorra ninguna llamada cara (el Nodo 1 ya se
llamó, que es la única llamada al LLM en el camino corto).

`currency_verification_incomplete` (poblado solo por el Nodo 3) queda
sin definir en el camino corto -- verificado que ningún otro nodo lo
lee, así que no hay efecto secundario por saltárselo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
from efsa_rag.ingestion.embedding_model import load_embedding_model
from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore, OpinionReference, SubstanceCandidate

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
XLSX_PATH = REPO_ROOT / "data" / "raw" / "OFT3_0_export_repository.xlsx"
CHROMA_PERSIST_DIR = REPO_ROOT / "data" / "chroma"
CHROMA_COLLECTION_NAME = "efsa_reevaluation_chunks"  # ver scripts/build_chroma_index.py


def _route_after_retrieval(state: GraphState) -> str:
    """Arista condicional -- ver el razonamiento completo en el
    docstring del módulo. Único punto de la orquestación que decide si
    el Nodo 3 se llama o no."""
    return "verify_currency" if state.get("substance_candidates") else "generate_answer"


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
    no llamar por consulta, ver `answer_question` para el cacheo.

    Modelo de embeddings vía `load_embedding_model()`
    (`ingestion/embedding_model.py`) -- backend ONNX + int8, DEBE
    coincidir con el que usó `scripts/build_chroma_index.py` para
    poblar la colección, o las queries no viven en el mismo espacio
    vectorial que los chunks indexados. Ver ese módulo para el porqué."""
    import chromadb

    store = OpenFoodToxStore(XLSX_PATH)

    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    vectorstore = chroma_client.get_collection(CHROMA_COLLECTION_NAME)

    embedding_model = load_embedding_model()

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
    lo sustituye, lo acompaña. `retrieved_chunks`, `structured_result` y
    `substance_name` son exactamente los mismos valores que vio/produjo
    el grafo (no una reconstrucción aparte) -- tomados directamente del
    estado final tras `.invoke(...)`.

    `substance_name` añadido (sesión 18-ago-2026, al implementar el
    servidor MCP) -- ya lo calculaba el Nodo 1 y quedaba en el estado
    del grafo, solo no se exponía aquí. Necesario para que un caller
    (ej. la herramienta MCP `search_efsa_opinion`) sepa qué sustancia se
    identificó sin tener que releer `structured_result.title` (que
    puede ser `None` si no hay dictamen vigente, aunque la sustancia SÍ
    se haya identificado -- son señales distintas, no intercambiables).

    `substance_candidates`/`structured_results` AÑADIDOS (sesión
    19-ago-2026, resolución multi-candidato) -- CAMPOS ADITIVOS con
    default, colocados DESPUÉS de los 4 campos originales a propósito:
    el servidor MCP (`mcp/server.py`) queda deliberadamente FUERA de este
    cambio (ver CLAUDE.md, pendiente explícito) y sigue construyendo/
    consumiendo `AnswerResult` con el contrato de un único resultado --
    `tests/test_mcp_server.py` construye `AnswerResult(...)` directamente
    y NO debía tocarse. `structured_result` (singular) sigue poblado,
    ahora con el candidato top (`candidates[0]`, ya ordenado de forma
    determinista por `_candidate_sort_key` -- ver
    `OpenFoodToxStore.resolve_substance_candidates`) para mantener ese
    contrato con cero cambios visibles cuando solo hay 1 candidato. Un
    caller que SÍ quiera ver todos los candidatos (no el MCP, que se
    queda con el campo singular) usa estos dos campos nuevos en vez de
    reconstruir el retrieval a mano -- mismo principio que motivó esta
    clase en origen."""

    answer: str
    retrieved_chunks: list[RetrievedChunk]
    structured_result: OpinionReference | None
    substance_name: str | None
    substance_candidates: list[SubstanceCandidate] = field(default_factory=list)
    structured_results: dict[str, OpinionReference | None] = field(default_factory=dict)


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
    tratar el resultado como string directamente.

    `structured_result` (singular, compatibilidad MCP) se rellena con el
    candidato top de `substance_candidates` -- ver el docstring de
    `AnswerResult`."""
    global _default_deps, _default_graph

    if _default_deps is None:
        _default_deps = build_default_deps()
    if _default_graph is None:
        _default_graph = build_graph(_default_deps)

    result = _default_graph.invoke({"user_query": query})
    candidates = result.get("substance_candidates") or []
    structured_results = result.get("structured_results") or {}
    top_structured = structured_results.get(candidates[0].substance_uuid) if candidates else None

    return AnswerResult(
        answer=result["answer"],
        retrieved_chunks=result.get("retrieved_chunks") or [],
        structured_result=top_structured,
        substance_name=result.get("substance_name"),
        substance_candidates=candidates,
        structured_results=structured_results,
    )


@dataclass(frozen=True)
class ReevaluationStatus:
    """Salida de `resolve_current_opinion` -- el camino PARCIAL del
    grafo (Nodo 1 + Nodo 3, sin Nodo 2 ni Nodo 4). Ver CLAUDE.md,
    "Decisiones de arquitectura ya tomadas", para el porqué de este
    segundo camino de ejecución y qué garantía de seguridad sostiene
    (ninguno de estos campos pasa por un LLM: `substance_name` es
    normalización determinista + resolución exacta contra `SUB`
    -- salvo la propia llamada al LLM del Nodo 1 para identificar la
    sustancia, que no compone nada sobre el ADI -- y `structured_result`
    es lectura directa de OpenFoodTox, igual que en `AnswerResult`)."""

    substance_name: str | None
    substance_uuid: str | None
    structured_result: OpinionReference | None


def resolve_current_opinion(query: str) -> ReevaluationStatus:
    """Camino PARCIAL del grafo: Nodo 1 (extracción de entidad) + Nodo 3
    (verificación de vigencia determinista contra OpenFoodTox), sin
    Nodo 2 (retrieval narrativo -- no hace falta, esta función no
    necesita `retrieved_chunks`) ni Nodo 4 (generación LLM -- tampoco
    hace falta, esta función no produce prosa, solo campos ya
    calculados por OpenFoodTox).

    NO usa el grafo compilado (`build_graph`/`_default_graph`) porque
    ese grafo siempre enruta hacia el Nodo 4 -- se llaman los nodos 1 y
    3 directamente, reutilizando su lógica tal cual (sin reimplementar
    nada de `graph/nodes.py`), solo con una orquestación más corta.
    Reutiliza el MISMO `_default_deps` cacheado que `answer_question`
    -- compartido a nivel de módulo, así que llamar a esta función
    primero (o después) no recarga el modelo de embeddings ni reabre
    Chroma ni el xlsx.

    Réplica exacta del guardia ya usado en `_route_after_retrieval`
    para decidir si se llama al Nodo 3 (si el Nodo 1 no resolvió ningún
    `substance_candidates`, `verify_currency_node` lanzaría `ValueError`
    si se le llamara) -- mismo criterio, no una regla nueva.

    Con 2+ candidatos, el Nodo 3 ya calcula TODOS (coste ya pagado, no se
    duplica) pero esta función devuelve solo el candidato top
    (`candidates[0]`, orden determinista vía `_candidate_sort_key`) --
    ver CLAUDE.md, MCP (`mcp/server.py`) queda deliberadamente fuera del
    cambio de resolución multi-candidato y sigue con el contrato de un
    único resultado.
    """
    global _default_deps

    if _default_deps is None:
        _default_deps = build_default_deps()

    state = extract_entity_node({"user_query": query}, _default_deps)
    candidates = state.get("substance_candidates") or []
    if not candidates:
        return ReevaluationStatus(
            substance_name=state.get("substance_name"), substance_uuid=None, structured_result=None
        )

    state = verify_currency_node(state, _default_deps)
    top = candidates[0]
    structured_results = state.get("structured_results") or {}
    return ReevaluationStatus(
        substance_name=state.get("substance_name"),
        substance_uuid=top.substance_uuid,
        structured_result=structured_results.get(top.substance_uuid),
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
