"""
Tests para los Nodos 2 y 4 (graph/nodes.py).

Los tests de `_format_structured_result` (tier 1/2 de ADI) requieren el
xlsx real de OpenFoodTox 3.0 en data/raw/ para tener un `OpinionReference`
real de cada categoría -- se saltan automáticamente si no está presente,
mismo patrón que tests/test_openfoodtox_joins.py.

Los tests de `_format_retrieved_chunks` (tier 3 de `RetrievedChunk`) NO
requieren el xlsx -- construyen el dataclass directamente, sin pasar por
Nodo 2.

Los tests de `hybrid_retrieval_node` (Nodo 2) requieren el índice Chroma
real ya poblado en data/chroma/ (ver scripts/build_chroma_index.py
--all, sesión 18-ago-2026) -- se saltan si no está presente, mismo
patrón. Corren una consulta REAL contra el índice completo (67.827
chunks), no un mock -- verifican comportamiento real de recuperación,
no solo que el código no lance una excepción.

Los tests de `extract_entity_node` (Nodo 1) requieren `DEEPSEEK_API_KEY`
configurada -- se saltan si no está presente. A diferencia de los demás
tests de este archivo, estos SÍ hacen una llamada real y FACTURADA a la
API de DeepSeek en cada ejecución (coste mínimo, unas pocas decenas de
tokens de entrada/salida) -- no son gratis como los que solo dependen
de un recurso local ya descargado.
"""

from pathlib import Path

import pytest

from efsa_rag.graph.nodes import (
    DEFAULT_RETRIEVAL_K,
    NodeDependencies,
    RetrievedChunk,
    _format_retrieved_chunks,
    _format_structured_result,
    extract_entity_node,
    hybrid_retrieval_node,
)
from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore

CHROMA_PERSIST_DIR = Path(__file__).parent.parent / "data" / "chroma"
CHROMA_COLLECTION_NAME = "efsa_reevaluation_chunks"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

XLSX_PATH = Path(__file__).parent.parent / "data" / "raw" / "OFT3_0_export_repository.xlsx"


@pytest.fixture(scope="module")
def store() -> OpenFoodToxStore:
    if not XLSX_PATH.exists():
        pytest.skip("Requiere el export real de OpenFoodTox en data/raw/ (no versionado)")
    return OpenFoodToxStore(XLSX_PATH)


def test_format_structured_result_tier1_cites_adi_normally(store: OpenFoodToxStore):
    """Tier 1 (ADI real, caso aspartamo) -- el texto debe citar el valor
    con normalidad, SIN el aviso de "no hay un valor numérico" (ese aviso
    es exclusivo del branch sin ADI).
    """
    substance_uuid = store.substance_uuid_by_name("Aspartame")
    assert substance_uuid is not None
    result = store.current_reference_value_opinion(substance_uuid)
    assert result is not None and result.adi_value is not None

    text = _format_structured_result(result)

    assert "- ADI: 40.0 mg/kg" in text or "- ADI: 40 mg/kg" in text
    assert "no hay un valor numérico" not in text


def test_format_structured_result_tier2_explains_absence_without_assuming_reason(
    store: OpenFoodToxStore,
):
    """Tier 2 (sustancia identificada, sin ADI -- patrón TiO2). El texto
    debe:
    1. Decir explícitamente que no hay ADI numérico.
    2. Mencionar AMBOS motivos posibles (favorable -- sin necesidad de
       límite -- y de preocupación -- p.ej. genotoxicidad) como ejemplos,
       no como el motivo real de ESTE caso.
    3. Instruir a NO asumir cuál aplica sin verificarlo en la
       justificación/discusión ya incluidas.

    Verificado con dióxido de titanio (E171): su dictamen vigente de 2021
    tiene adi_value=None porque EFSA no pudo establecer un ADI por
    preocupaciones de genotoxicidad -- pero el texto generado NO debe
    afirmarlo como un hecho universal para cualquier sustancia sin ADI
    (la mayoría de las 73 sustancias sin ADI del corpus lo son por el
    motivo contrario, ver CLAUDE.md "Hallazgos verificados").
    """
    substance_uuid = store.substance_uuid_by_name("Titanium dioxide")
    assert substance_uuid is not None
    result = store.current_reference_value_opinion(substance_uuid)
    assert result is not None and result.adi_value is None

    text = _format_structured_result(result)

    assert "no hay un valor numérico en los datos estructurados" in text
    assert "genotoxicidad" in text.lower()
    assert "no considerara necesario" in text.lower() or "innecesario" in text.lower()
    assert "no asumas cuál de los dos aplica" in text.lower()


def test_format_retrieved_chunks_flags_tier3_with_confidence_caveat():
    """Un chunk con substance_resolution_tier == 3 (identidad de
    sustancia inferida por título, sin enlace estructural) debe llevar un
    aviso inline explícito; uno con tier 1 o 2 (enlace estructural
    confirmado, con o sin ADI) no debe llevarlo.
    """
    chunks = [
        RetrievedChunk(
            text="Fragmento con enlace estructural confirmado.",
            substance_uuid="uuid-1",
            chemical_name="Sodium nitrite",
            dossier_uuid="dossier-1",
            dossier_title="Re-evaluation of sodium nitrite",
            substance_resolution_tier=1,
        ),
        RetrievedChunk(
            text="Fragmento de un dossier sin ADI pero identidad clara.",
            substance_uuid="uuid-2",
            chemical_name="Titanium dioxide",
            dossier_uuid="dossier-2",
            dossier_title="Safety assessment of titanium dioxide",
            substance_resolution_tier=2,
        ),
        RetrievedChunk(
            text="Fragmento identificado solo por coincidencia de título.",
            substance_uuid="uuid-3",
            chemical_name="Sucralose",
            dossier_uuid="dossier-3",
            dossier_title="Statement on the validity of the conclusions of a mouse "
            "carcinogenicity study on sucralose",
            substance_resolution_tier=3,
        ),
    ]

    formatted = _format_retrieved_chunks(chunks)

    tier1_block, tier2_block, tier3_block = (
        formatted.split("[fragmento 1]")[1].split("[fragmento 2]")[0],
        formatted.split("[fragmento 2]")[1].split("[fragmento 3]")[0],
        formatted.split("[fragmento 3]")[1],
    )
    assert "coincidencia de nombre en el título" not in tier1_block
    assert "coincidencia de nombre en el título" not in tier2_block
    assert "coincidencia de nombre en el título" in tier3_block


def test_format_retrieved_chunks_empty_list_explains_missing_corpus():
    assert "no está indexado" in _format_retrieved_chunks(None)
    assert "no está indexado" in _format_retrieved_chunks([])


# --------------------------------------------------------------------- #
# Nodo 2 -- hybrid_retrieval_node
# --------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def chroma_deps(store: OpenFoodToxStore) -> NodeDependencies:
    if not CHROMA_PERSIST_DIR.exists():
        pytest.skip(
            "Requiere el índice Chroma real en data/chroma/ (no versionado, ver "
            "scripts/build_chroma_index.py --all)"
        )
    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    collection = client.get_collection(CHROMA_COLLECTION_NAME)
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return NodeDependencies(store=store, vectorstore=collection, embedding_model=model)


def test_hybrid_retrieval_node_aspartame_real_query(chroma_deps: NodeDependencies):
    """Consulta real sobre aspartamo (query específica de contenido
    narrativo, no genérica -- para no acertar por casualidad con un
    fragmento de portada/citación sin section_heading, ver el 0,17% de
    chunks con section_heading=None en el corpus real). Verifica: (1)
    devuelve chunks (no vacío), (2) como mucho DEFAULT_RETRIEVAL_K
    (k=5), (3) TODOS con el substance_uuid correcto de aspartamo (el
    filtro `where` de Chroma funciona de verdad, no solo por
    casualidad), (4) TODOS con section_heading no vacío."""
    aspartame_uuid = chroma_deps.store.substance_uuid_by_name("Aspartame")
    assert aspartame_uuid is not None

    state = {
        "user_query": "What genotoxicity and carcinogenicity studies were considered for aspartame?",
        "substance_uuid": aspartame_uuid,
    }

    new_state = hybrid_retrieval_node(state, chroma_deps)
    chunks = new_state["retrieved_chunks"]

    assert 0 < len(chunks) <= DEFAULT_RETRIEVAL_K
    assert all(isinstance(c, RetrievedChunk) for c in chunks)
    assert all(c.substance_uuid == aspartame_uuid for c in chunks)
    assert all(c.chemical_name == "Aspartame" for c in chunks)
    assert all(c.section_heading for c in chunks)  # no vacío ni None
    assert all(c.text.strip() for c in chunks)
    # substance_resolution_tier copiado tal cual del metadato indexado,
    # no re-derivado -- aspartamo es tier 1 (ADI real), verificado en
    # sesiones anteriores.
    assert all(c.substance_resolution_tier == 1 for c in chunks)


def test_hybrid_retrieval_node_no_uuid_skips_chroma_entirely(chroma_deps: NodeDependencies):
    """Si el Nodo 1 no resolvió substance_uuid, el Nodo 2 debe dejar
    retrieved_chunks vacío SIN llamar a Chroma -- verificado pasando un
    vectorstore que lanzaría si se le llamara, para confirmar que de
    verdad no se invoca (no basta con que el resultado esté vacío por
    casualidad)."""

    class _ExplodingVectorStore:
        def query(self, *args, **kwargs):
            raise AssertionError("No debería llamarse a Chroma sin substance_uuid")

    deps = NodeDependencies(
        store=chroma_deps.store,
        vectorstore=_ExplodingVectorStore(),
        embedding_model=chroma_deps.embedding_model,
    )
    state = {"user_query": "¿Aspartamo es seguro?", "substance_uuid": None}

    new_state = hybrid_retrieval_node(state, deps)

    assert new_state["retrieved_chunks"] == []


# --------------------------------------------------------------------- #
# Nodo 1 -- extract_entity_node
# --------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def llm_client():
    import os

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("Requiere DEEPSEEK_API_KEY configurada (ver .env) para la llamada real a la API")
    from efsa_rag.graph.llm_client import DeepSeekClient

    return DeepSeekClient()


def test_extract_entity_node_resolves_aspartame_from_real_english_query(
    store: OpenFoodToxStore, llm_client
):
    """PRIMERA prueba real de este nodo -- llamada REAL a la API de
    DeepSeek (no un mock), pregunta en inglés sobre aspartamo (el caso
    de referencia ya usado en el resto del proyecto -- aspartamo E951,
    test_openfoodtox_joins, Nodo 4). No se da por hecho que resuelva el
    UUID correcto solo porque el prompt parece razonable -- se verifica
    contra `store.substance_uuid_by_name("Aspartame")` directamente."""
    deps = NodeDependencies(store=store, llm_client=llm_client)
    state = {"user_query": "What is the ADI of aspartame and what study is it based on?"}

    new_state = extract_entity_node(state, deps)

    expected_uuid = store.substance_uuid_by_name("Aspartame")
    assert expected_uuid is not None

    assert new_state["substance_name"] is not None
    assert new_state["substance_uuid"] == expected_uuid


def test_extract_entity_node_unrelated_query_resolves_to_none(store: OpenFoodToxStore, llm_client):
    """Pregunta sin ningún aditivo alimentario identificable -- el LLM
    debe responder NONE y el nodo debe dejar substance_name/uuid en
    None, no inventar una sustancia."""
    deps = NodeDependencies(store=store, llm_client=llm_client)
    state = {"user_query": "What time is it in Tokyo right now?"}

    new_state = extract_entity_node(state, deps)

    assert new_state["substance_name"] is None
    assert new_state["substance_uuid"] is None
