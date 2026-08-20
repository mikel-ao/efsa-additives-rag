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
--all) -- se saltan si no está presente, mismo
patrón. Corren una consulta REAL contra el índice completo (67.827
chunks), no un mock -- verifican comportamiento real de recuperación,
no solo que el código no lance una excepción.

Los tests de `extract_entity_node` (Nodo 1) requieren `DEEPSEEK_API_KEY`
configurada -- se saltan si no está presente. A diferencia de los demás
tests de este archivo, estos SÍ hacen una llamada real y FACTURADA a la
API de DeepSeek en cada ejecución (coste mínimo, unas pocas decenas de
tokens de entrada/salida) -- no son gratis como los que solo dependen
de un recurso local ya descargado.

Los tests de `generate_answer_node` (Nodo 4) usan un `_StubLLMClient`
(implementa `LLMClient` sin llamar a ninguna API) que devuelve una
secuencia fija de `LLMResponse` -- no dependen de xlsx, Chroma ni
`DEEPSEEK_API_KEY`, y no gastan tokens reales. Existen específicamente
para codificar como test de regresión el bug de truncamiento silencioso
encontrado con una respuesta real sobre Shellac: antes de ese fix, un
`finish_reason == 'length'` se devolvía cortado a mitad de frase sin
ningún aviso.
"""

from pathlib import Path

import pytest

from efsa_rag.graph.llm_client import LLMClient, LLMResponse
from efsa_rag.graph.nodes import (
    DEFAULT_RETRIEVAL_K,
    EFSA_FOOD_ADDITIVES_URL,
    NODE_4_MAX_TOKENS,
    NODE_4_RETRY_MAX_TOKENS,
    NodeDependencies,
    RetrievedChunk,
    _build_user_prompt,
    _format_retrieved_chunks,
    _format_structured_result,
    _format_unresolved_substance_message,
    extract_entity_node,
    generate_answer_node,
    hybrid_retrieval_node,
)
from efsa_rag.ingestion.embedding_model import load_embedding_model
from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore, OpinionReference, SubstanceCandidate

CHROMA_PERSIST_DIR = Path(__file__).parent.parent / "data" / "chroma"
CHROMA_COLLECTION_NAME = "efsa_reevaluation_chunks"

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


def test_format_retrieved_chunks_empty_and_no_structured_result_reports_no_opinion_found():
    """Contrato actual (caso real "Olive leaf dry extract" -- ver
    test_openfoodtox_joins.py y CLAUDE.md): esta función solo se llama
    desde `_build_user_prompt` en ramas donde la sustancia YA se
    identificó (el caso de 0 candidatos usa
    `_format_unresolved_substance_message` en su lugar, nunca esta). Por
    eso, cuando `structured_result` es `None`, el mensaje no debe volver
    a culpar a la resolución de sustancia: una versión anterior decía
    "no se ha podido resolver de forma exacta la sustancia",
    condicionalmente falso -- cierto solo para el caso de 0 candidatos,
    pero reutilizado también aquí sin distinguir el contexto. Tampoco
    debe repetir el mensaje incondicionalmente falso "el corpus no está
    indexado" (nunca cierto).

    El mensaje tampoco debe contener ninguna frase que suene a "no se ha
    identificado la sustancia" (ni siquiera "en el corpus indexado",
    léxicamente parecida a la del mensaje de 0 candidatos) -- esa
    afirmación es específicamente falsa aquí, la sustancia SÍ se
    identificó. Debe afirmarlo explícitamente en su lugar."""
    for chunks in (None, []):
        text = _format_retrieved_chunks(chunks, structured_result=None)
        assert "no está indexado" not in text
        assert "resolver de forma exacta la sustancia" not in text
        assert "no se ha identificado" not in text.lower()
        assert "no se ha podido identificar" not in text.lower()
        assert "corpus indexado" not in text  # frase exclusiva del mensaje de 0 candidatos
        assert "no se ha encontrado ningún dictamen" in text
        assert "sí se identificó" in text.lower()


def test_format_retrieved_chunks_empty_but_structured_result_present_differs():
    """Causa distinta del caso de arriba -- el dictamen vigente SÍ se
    resolvió por OpenFoodTox, así que el mensaje no debe culpar a la
    resolución de sustancia (sería igual de engañoso en la dirección
    contraria)."""
    structured_result = OpinionReference(
        dossier_uuid="dossier-1",
        date_of_evaluation=None,
        title="Re-evaluation of some additive",
        doc_type="EFSA opinion",
        doi=None,
    )
    text = _format_retrieved_chunks([], structured_result=structured_result)
    assert "no está indexado" not in text
    assert "resolver de forma exacta la sustancia" not in text
    assert "no se han encontrado fragmentos narrativos indexados" in text


def test_build_user_prompt_olive_leaf_extract_real_case_does_not_self_contradict(
    store: OpenFoodToxStore,
):
    """Caso de regresión con datos reales, no construido a mano -- "Olive
    leaf dry extract from O. europaea L." (mismo caso ya probado en
    test_openfoodtox_joins.py::test_olive_leaf_extract_has_no_real_food_additive_opinion):
    resuelve por nombre EXACTO en SUB (1 candidato), pero su único
    dossier es de pienso animal -- current_reference_value_opinion da
    None, sin ningún dictamen alimentario real.

    Sin este fix, el prompt resultante se contradecía a sí mismo:
    "Sustancia identificada: Olive leaf dry extract..." seguido de un
    mensaje que afirmaba "no se ha podido resolver de forma exacta la
    sustancia mencionada en la pregunta" -- confirmado con una llamada
    real al pipeline completo (hybrid_retrieval_node + verify_currency_node
    + _build_user_prompt, sin mock). Este test bloquea que la
    contradicción vuelva a aparecer."""
    name = "Olive leaf dry extract from O. europaea L."
    candidates = store.resolve_substance_candidates(name)
    assert len(candidates) == 1, f"Se esperaba 1 candidato exacto, se obtuvo: {candidates!r}"
    assert candidates[0].match_type == "exact"

    result = store.current_reference_value_opinion(candidates[0].substance_uuid)
    assert result is None, "Precondición del caso: sin dictamen alimentario real"

    state = {
        "user_query": "Is olive leaf dry extract safe as a food additive?",
        "substance_name": name,
        "substance_candidates": candidates,
        "structured_results": {candidates[0].substance_uuid: None},
        "retrieved_chunks": [],
    }

    prompt = _build_user_prompt(state)

    assert f"Sustancia identificada: {name}" in prompt
    # La contradicción real que motivó el fix: la sustancia SÍ se
    # identificó (línea de arriba), así que el prompt NUNCA debe decir
    # que no pudo resolverse.
    assert "no se ha podido resolver de forma exacta la sustancia" not in prompt
    assert "no se ha encontrado ningún dictamen" in prompt
    assert "sí se identificó" in prompt.lower()
    # Tampoco debe quedar ninguna frase residual que suene a "no
    # identificada", ni la frase "corpus indexado" (léxicamente exclusiva
    # del mensaje de 0 candidatos) que podía inducir al LLM a mezclar los
    # dos mensajes al parafrasear.
    assert "no se ha identificado" not in prompt.lower()
    assert "no se ha podido identificar" not in prompt.lower()
    assert "corpus indexado" not in prompt


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

    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    collection = client.get_collection(CHROMA_COLLECTION_NAME)
    model = load_embedding_model()
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
        "substance_candidates": [
            SubstanceCandidate(aspartame_uuid, "Aspartame", "exact", 100.0)
        ],
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
    # no re-derivado -- aspartamo es tier 1 (ADI real).
    assert all(c.substance_resolution_tier == 1 for c in chunks)


def test_hybrid_retrieval_node_no_candidates_skips_chroma_entirely(chroma_deps: NodeDependencies):
    """Si el Nodo 1 no resolvió ningún candidato, el Nodo 2 debe dejar
    retrieved_chunks vacío SIN llamar a Chroma -- verificado pasando un
    vectorstore que lanzaría si se le llamara, para confirmar que de
    verdad no se invoca (no basta con que el resultado esté vacío por
    casualidad)."""

    class _ExplodingVectorStore:
        def query(self, *args, **kwargs):
            raise AssertionError("No debería llamarse a Chroma sin substance_candidates")

    deps = NodeDependencies(
        store=chroma_deps.store,
        vectorstore=_ExplodingVectorStore(),
        embedding_model=chroma_deps.embedding_model,
    )
    state = {"user_query": "¿Aspartamo es seguro?", "substance_candidates": []}

    new_state = hybrid_retrieval_node(state, deps)

    assert new_state["retrieved_chunks"] == []


def test_hybrid_retrieval_node_multiple_candidates_reduces_k_and_concatenates(
    chroma_deps: NodeDependencies,
):
    """Con 4 candidatos (caso real de tocoferol), el reparto de
    presupuesto debe dar k=3 por candidato (15 // 4 == 3, dentro de
    [MIN_K_PER_CANDIDATE, DEFAULT_RETRIEVAL_K]) y `retrieved_chunks` debe
    ser la concatenación de los 4, cada uno con su propio substance_uuid
    -- no solo los chunks del primero."""
    store = chroma_deps.store
    names = [
        "Delta-tocopherol",
        "Gamma-tocopherol",
        "DL-alpha-tocopherol",
        "Tocopherol-rich extract",
    ]
    candidates = []
    for name in names:
        uuid = store.substance_uuid_by_name(name)
        assert uuid is not None, f"{name!r} debería resolver en SUB"
        candidates.append(SubstanceCandidate(uuid, name, "fuzzy", 65.0))

    state = {
        "user_query": "safety assessment of tocopherols as food additives",
        "substance_candidates": candidates,
    }

    new_state = hybrid_retrieval_node(state, chroma_deps)
    chunks = new_state["retrieved_chunks"]

    seen_uuids = {c.substance_uuid for c in chunks}
    assert seen_uuids <= {c.substance_uuid for c in candidates}
    # Al menos 2 candidatos distintos deben haber aportado chunks -- no
    # basta con que la lista no esté vacía, confirma que de verdad se
    # consultó Chroma una vez por candidato, no solo el primero.
    assert len(seen_uuids) >= 2


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
    """Llamada real a la API de DeepSeek (no un mock), pregunta en
    inglés sobre aspartamo (el caso de referencia ya usado en el resto
    del proyecto -- aspartamo E951, test_openfoodtox_joins, Nodo 4). No
    se da por hecho que resuelva el UUID correcto solo porque el prompt
    parece razonable -- se verifica contra
    `store.substance_uuid_by_name("Aspartame")` directamente."""
    deps = NodeDependencies(store=store, llm_client=llm_client)
    state = {"user_query": "What is the ADI of aspartame and what study is it based on?"}

    new_state = extract_entity_node(state, deps)

    expected_uuid = store.substance_uuid_by_name("Aspartame")
    assert expected_uuid is not None

    assert new_state["substance_name"] is not None
    candidates = new_state["substance_candidates"]
    assert len(candidates) == 1
    assert candidates[0].substance_uuid == expected_uuid
    assert candidates[0].match_type == "exact"


def test_extract_entity_node_unrelated_query_resolves_to_none(store: OpenFoodToxStore, llm_client):
    """Pregunta sin ningún aditivo alimentario identificable -- el LLM
    debe responder NONE y el nodo debe dejar substance_name/uuid en
    None, no inventar una sustancia."""
    deps = NodeDependencies(store=store, llm_client=llm_client)
    state = {"user_query": "What time is it in Tokyo right now?"}

    new_state = extract_entity_node(state, deps)

    assert new_state["substance_name"] is None
    assert new_state["substance_candidates"] == []


# --------------------------------------------------------------------- #
# Nodo 4 -- generate_answer_node (truncamiento)
# --------------------------------------------------------------------- #


class _StubLLMClient(LLMClient):
    """Devuelve una secuencia fija de `LLMResponse`, una por llamada a
    `complete()` -- para forzar deterministamente un `finish_reason ==
    'length'` sin depender de que una llamada real trunque por
    casualidad ni gastar tokens reales. Registra los `max_tokens` de
    cada llamada para poder verificar que el reintento usa
    `NODE_4_RETRY_MAX_TOKENS`, no el tope normal."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(
        self,
        *,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append({"max_tokens": max_tokens, "temperature": temperature})
        if not self._responses:
            raise AssertionError(
                "generate_answer_node llamó a complete() más veces de las esperadas "
                "-- debe reintentar como mucho UNA vez, no en bucle"
            )
        return self._responses.pop(0)


def _base_state(**overrides) -> dict:
    state = {
        "user_query": "What is the ADI of shellac and what study is it based on?",
        "substance_name": "Shellac",
        "substance_candidates": [],
        "structured_results": {},
        "retrieved_chunks": None,
    }
    state.update(overrides)
    return state


def test_generate_answer_node_retries_once_on_truncation_and_succeeds():
    """Primera pasada trunca (finish_reason == 'length', mismo síntoma
    exacto que el caso real de Shellac); la segunda pasada (reintento)
    termina sola. La respuesta final debe ser la del reintento, completa,
    SIN la nota de "[respuesta incompleta...]" -- el reintento cubrió el
    hueco, no hay que avisar de nada."""
    client = _StubLLMClient(
        [
            LLMResponse(
                text="El ADI de la goma laca es... (cortada a mitad de fra",
                input_tokens=500,
                output_tokens=800,
                model="stub",
                finish_reason="length",
            ),
            LLMResponse(
                text="El ADI de la goma laca no está establecido numéricamente. Conclusión completa.",
                input_tokens=500,
                output_tokens=845,
                model="stub",
                finish_reason="stop",
            ),
        ]
    )
    deps = NodeDependencies(store=None, llm_client=client)

    new_state = generate_answer_node(_base_state(), deps)

    assert new_state["answer"] == (
        "El ADI de la goma laca no está establecido numéricamente. Conclusión completa."
    )
    assert "[respuesta incompleta" not in new_state["answer"]
    assert len(client.calls) == 2
    assert client.calls[0]["max_tokens"] == NODE_4_MAX_TOKENS
    assert client.calls[1]["max_tokens"] == NODE_4_RETRY_MAX_TOKENS


def test_generate_answer_node_appends_notice_if_retry_also_truncates():
    """Si incluso el reintento con más presupuesto sigue truncado, el
    nodo NUNCA debe devolver el texto cortado sin avisar (el bug real
    encontrado con Shellac antes de este fix) -- debe reintentar
    exactamente UNA vez (no en bucle, verificado por `_StubLLMClient`
    lanzando si se le llama una tercera vez) y añadir la nota visible al
    final."""
    client = _StubLLMClient(
        [
            LLMResponse(
                text="Primera pasada cortada",
                input_tokens=500,
                output_tokens=800,
                model="stub",
                finish_reason="length",
            ),
            LLMResponse(
                text="Segunda pasada (reintento) también cortada",
                input_tokens=500,
                output_tokens=3500,
                model="stub",
                finish_reason="length",
            ),
        ]
    )
    deps = NodeDependencies(store=None, llm_client=client)

    new_state = generate_answer_node(_base_state(), deps)

    assert new_state["answer"] == (
        "Segunda pasada (reintento) también cortada\n\n"
        "[respuesta incompleta por límite de longitud]"
    )
    assert len(client.calls) == 2
    assert client.calls[1]["max_tokens"] == NODE_4_RETRY_MAX_TOKENS


def test_generate_answer_node_no_retry_when_first_response_is_not_truncated():
    """Camino normal (sin truncamiento) -- una sola llamada, sin
    reintento ni nota añadida. Confirma que el fix no introduce un
    reintento innecesario en el caso común."""
    client = _StubLLMClient(
        [
            LLMResponse(
                text="Respuesta completa sin truncar.",
                input_tokens=500,
                output_tokens=200,
                model="stub",
                finish_reason="stop",
            ),
        ]
    )
    deps = NodeDependencies(store=None, llm_client=client)

    new_state = generate_answer_node(_base_state(), deps)

    assert new_state["answer"] == "Respuesta completa sin truncar."
    assert len(client.calls) == 1
    assert client.calls[0]["max_tokens"] == NODE_4_MAX_TOKENS


# --------------------------------------------------------------------- #
# Nodo 4 -- _build_user_prompt con candidatos múltiples
# --------------------------------------------------------------------- #


def _fake_candidate(chemical_name: str, score: float, uuid: str) -> SubstanceCandidate:
    return SubstanceCandidate(uuid, chemical_name, "fuzzy", score)


def _fake_opinion(uuid: str, title: str) -> OpinionReference:
    return OpinionReference(
        dossier_uuid=uuid, date_of_evaluation=None, title=title, doc_type="EFSA opinion", doi=None
    )


def test_build_user_prompt_single_candidate_matches_legacy_format():
    """Con 0 o 1 candidato, el prompt debe seguir el mismo formato de
    siempre (sin envoltorio de "candidato 1 de N") -- regresión contra
    el comportamiento ya probado con datos reales (aspartamo,
    Shellac)."""
    candidate = _fake_candidate("Aspartame", 100.0, "uuid-aspartame")
    state = {
        "user_query": "What is the ADI of aspartame?",
        "substance_name": "Aspartame",
        "substance_candidates": [candidate],
        "structured_results": {"uuid-aspartame": _fake_opinion("uuid-aspartame", "Re-eval of aspartame")},
        "retrieved_chunks": [],
    }

    prompt = _build_user_prompt(state)

    assert "=== Candidato" not in prompt
    assert "Se han identificado" not in prompt
    assert "Sustancia identificada: Aspartame" in prompt
    assert "Re-eval of aspartame" in prompt


def test_build_user_prompt_multiple_candidates_presents_each_separately():
    """Con 2+ candidatos (caso real de tocoferol), el prompt debe
    presentar cada uno en su propio bloque, con su nombre, e instruir a
    no fusionarlos -- decisión de producto explícita: nunca elegir uno
    en silencio."""
    candidates = [
        _fake_candidate("Delta-tocopherol", 69.23, "uuid-delta"),
        _fake_candidate("Gamma-tocopherol", 69.23, "uuid-gamma"),
    ]
    state = {
        "user_query": "Is tocopherol safe as a food additive?",
        "substance_name": "Tocopherol",
        "substance_candidates": candidates,
        "structured_results": {
            "uuid-delta": _fake_opinion("uuid-delta", "Re-eval of Delta-tocopherol"),
            "uuid-gamma": _fake_opinion("uuid-gamma", "Re-eval of Gamma-tocopherol"),
        },
        "retrieved_chunks": [],
        "candidates_truncated": False,
    }

    prompt = _build_user_prompt(state)

    assert "Se han identificado 2 sustancias" in prompt
    assert "=== Candidato 1: Delta-tocopherol" in prompt
    assert "=== Candidato 2: Gamma-tocopherol" in prompt
    assert "Re-eval of Delta-tocopherol" in prompt
    assert "Re-eval of Gamma-tocopherol" in prompt
    assert "sin fusionarlas" in prompt
    assert "Hay más de" not in prompt  # candidates_truncated=False


def test_build_user_prompt_truncated_candidates_announces_it_explicitly():
    """Si `candidates_truncated` es True, el prompt debe anunciarlo
    explícitamente -- nunca en silencio."""
    candidates = [_fake_candidate("Delta-tocopherol", 69.23, "uuid-delta"), _fake_candidate(
        "Gamma-tocopherol", 69.23, "uuid-gamma"
    )]
    state = {
        "user_query": "Is tocopherol safe?",
        "substance_name": "Tocopherol",
        "substance_candidates": candidates,
        "structured_results": {},
        "retrieved_chunks": [],
        "candidates_truncated": True,
    }

    prompt = _build_user_prompt(state)

    assert "Hay más de" in prompt
    assert "se muestran las" in prompt


# --------------------------------------------------------------------- #
# Nodo 4 -- mensaje de sustancia no identificada (caso real "plai
# caramel": la sustancia SÍ existe y SÍ tiene dictamen
# vigente, el fallo fue de resolución de nombre, no de ausencia real --
# el mensaje NO debe afirmar "esta sustancia no tiene reevaluaciones
# recientes" (no verificable, potencialmente falso).
# --------------------------------------------------------------------- #


def test_format_unresolved_substance_message_includes_fixed_efsa_link_and_verbatim_query():
    """El mensaje debe incluir el enlace FIJO a EFSA (no un buscador con
    parámetro -- descartado tras verificarse en navegador real que no
    filtra) y el texto de la pregunta del usuario TAL CUAL, sin
    reformular."""
    raw_query = "¿Para qué se usa el plai caramel como aditivo??? typo aposta"
    message = _format_unresolved_substance_message(raw_query)

    assert EFSA_FOOD_ADDITIVES_URL in message
    assert raw_query in message  # verbatim, no reformulado ni corregido
    assert "esta sustancia no tiene reevaluaciones recientes" not in message.lower()
    assert "no se ha podido identificar esta sustancia" in message.lower()


def test_build_user_prompt_no_candidates_uses_unresolved_substance_message():
    """Con `substance_candidates` vacío, `_build_user_prompt` debe usar
    `_format_unresolved_substance_message` (enlace EFSA + query verbatim)
    en vez del mensaje genérico interno de `_format_retrieved_chunks` --
    y el texto de la pregunta original debe aparecer sin cambios."""
    raw_query = "What is plai caramel used for as a food additive?"
    state = {
        "user_query": raw_query,
        "substance_name": None,
        "substance_candidates": [],
        "structured_results": {},
        "retrieved_chunks": None,
    }

    prompt = _build_user_prompt(state)

    assert EFSA_FOOD_ADDITIVES_URL in prompt
    assert raw_query in prompt
    assert "no se ha podido identificar esta sustancia" in prompt.lower()
    assert "esta sustancia no tiene reevaluaciones recientes" not in prompt.lower()


def test_build_user_prompt_single_candidate_does_not_use_unresolved_message():
    """Con exactamente 1 candidato identificado (aunque su dictamen no
    resuelva), el mensaje de "no se ha podido identificar" NO debe
    aparecer -- la sustancia SÍ se identificó, solo falta el dictamen."""
    candidate = _fake_candidate("Aspartame", 100.0, "uuid-aspartame")
    state = {
        "user_query": "What is the ADI of aspartame?",
        "substance_name": "Aspartame",
        "substance_candidates": [candidate],
        "structured_results": {"uuid-aspartame": None},
        "retrieved_chunks": [],
    }

    prompt = _build_user_prompt(state)

    assert "no se ha podido identificar esta sustancia" not in prompt.lower()
    assert EFSA_FOOD_ADDITIVES_URL not in prompt
