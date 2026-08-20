"""
Tests para el servidor MCP (mcp/server.py).

Mismo patrón que los tests de truncamiento del Nodo 4
(tests/test_nodes.py::_StubLLMClient): se monkeypatchean
`answer_question`/`resolve_current_opinion` (los dos puntos de entrada
de graph/build.py que las herramientas MCP envuelven, ver CLAUDE.md
"Dos caminos de ejecución del grafo") con dobles deterministas -- no se
toca xlsx, Chroma ni ninguna API real, y no se gasta ni un token.

`server.list_tools()`/`server.call_tool()` son async -- sin
pytest-asyncio en el proyecto (no está en requirements.txt), se
invocan con `asyncio.run(...)` dentro de tests síncronos normales, en
vez de añadir una dependencia nueva solo para esto.

Las dos herramientas devuelven siempre
`{"candidates_found", "candidates_shown", "results": [...]}`, nunca un
objeto plano con un único candidato -- los tests cubren tanto el caso
de 1 elemento en `results` (el caso común) como el de 2+ candidatos.
"""

import asyncio
from datetime import date

import pytest

import efsa_rag.mcp.server as mcp_server
from efsa_rag.graph.build import AnswerResult, ReevaluationStatus
from efsa_rag.graph.nodes import RetrievedChunk
from efsa_rag.ingestion.openfoodtox import OpinionReference, SubstanceCandidate
from efsa_rag.mcp.server import SAFETY_NOTE, server


def _exploding(*_args, **_kwargs):
    """Doble que lanza si se le llama -- para afirmar que una
    herramienta NUNCA invoca el camino de ejecución de la otra (en
    particular, que get_reevaluation_status no pasa por answer_question/
    Nodo 4, ver CLAUDE.md)."""
    raise AssertionError("No debería haberse llamado a esta función en este camino")


ASPARTAME_OPINION = OpinionReference(
    dossier_uuid="dossier-aspartame",
    date_of_evaluation=date(2013, 11, 28),
    title="Scientific Opinion on the re-evaluation of aspartame (E 951) as a food additive",
    doc_type="EFSA opinion",
    doi="10.2903/j.efsa.2013.3496",
    adi_value=40.0,
    adi_unit="mg/kg bw/day",
    adi_justification="texto verbatim de JustificationAndComments",
    discussion_text="discusión narrativa real, no boilerplate",
    discussion_is_boilerplate=False,
)


def _call(tool_name: str, arguments: dict):
    return asyncio.run(server.call_tool(tool_name, arguments))


# --------------------------------------------------------------------- #
# list_tools() -- esquema
# --------------------------------------------------------------------- #


def test_list_tools_exposes_exactly_the_two_expected_tools_with_schema():
    """Nombres, descripción no vacía, y esquema de parámetros exacto
    (un único `substance: string` requerido) para las dos herramientas."""
    tools = asyncio.run(server.list_tools())
    tools_by_name = {t.name: t for t in tools}

    assert set(tools_by_name) == {"search_efsa_opinion", "get_reevaluation_status"}

    for tool in tools_by_name.values():
        assert tool.description  # no vacía

        schema = tool.input_schema
        assert schema["type"] == "object"
        assert schema["required"] == ["substance"]
        assert set(schema["properties"]) == {"substance"}
        assert schema["properties"]["substance"]["type"] == "string"
        assert schema["properties"]["substance"]["description"]  # no vacía

        # Salida ESTRUCTURADA (dict[str, Any], no dict a secas) -- el SDK
        # solo genera outputSchema con el tipo de retorno parametrizado.
        assert tool.output_schema is not None


# --------------------------------------------------------------------- #
# get_reevaluation_status -- sustancia conocida, sin pasar por el Nodo 4
# --------------------------------------------------------------------- #


ASPARTAME_CANDIDATE = SubstanceCandidate(
    substance_uuid="uuid-aspartame", chemical_name="Aspartame", match_type="exact", match_score=100.0
)


def test_get_reevaluation_status_known_substance_returns_structured_json_without_node4(
    monkeypatch: pytest.MonkeyPatch,
):
    """Sustancia conocida (aspartamo, stub, 1 candidato) -- `results`
    debe tener exactamente 1 elemento, con los campos de OpinionReference
    tal cual, sin reformular. `answer_question` se deja como
    `_exploding`: si get_reevaluation_status pasara por el Nodo 4 (el
    camino completo), este test fallaría con un AssertionError en vez de
    con una aserción sobre el JSON -- confirma que el camino parcial
    (Nodo 1 + Nodo 3) es de verdad el que se ejecuta."""
    monkeypatch.setattr(
        mcp_server,
        "resolve_current_opinion",
        lambda query: ReevaluationStatus(
            substance_name="Aspartame",
            substance_uuid="uuid-aspartame",
            structured_result=ASPARTAME_OPINION,
            substance_candidates=[ASPARTAME_CANDIDATE],
            structured_results={"uuid-aspartame": ASPARTAME_OPINION},
            candidates_total_found=1,
        ),
    )
    monkeypatch.setattr(mcp_server, "answer_question", _exploding)

    result = _call("get_reevaluation_status", {"substance": "aspartamo"})

    assert result.is_error is False
    assert result.structured_content == {
        "candidates_found": 1,
        "candidates_shown": 1,
        "substance_identified": "Aspartame",
        "safety_note": SAFETY_NOTE,
        "results": [
            {
                "chemical_name": "Aspartame",
                "match_type": "exact",
                "match_score": 100.0,
                "dossier_found": True,
                "dossier_title": ASPARTAME_OPINION.title,
                "doi": "10.2903/j.efsa.2013.3496",
                "date_of_evaluation": "2013-11-28",
                "adi_value": 40.0,
                "adi_unit": "mg/kg bw/day",
                "adi_justification": "texto verbatim de JustificationAndComments",
                "discussion_available": True,
            }
        ],
    }


def test_get_reevaluation_status_tier2_without_adi_reports_null_adi_not_invented(
    monkeypatch: pytest.MonkeyPatch,
):
    """Caso tier 2 (sustancia identificada, dictamen vigente, pero SIN
    ADI numérico -- patrón TiO2, ver CLAUDE.md) -- adi_value/adi_unit/
    adi_justification deben ir `None`, nunca un valor inventado; el
    resto de metadatos del dossier (título, DOI, fecha) sí presentes."""
    tio2_opinion = OpinionReference(
        dossier_uuid="dossier-tio2",
        date_of_evaluation=date(2021, 3, 25),
        title="Safety assessment of titanium dioxide (E171) as a food additive",
        doc_type="EFSA opinion",
        doi="10.2903/j.efsa.2021.6585",
        adi_value=None,
        adi_unit=None,
        adi_justification=None,
        discussion_text="párrafo corto",
        discussion_is_boilerplate=True,
    )
    tio2_candidate = SubstanceCandidate(
        substance_uuid="uuid-tio2", chemical_name="Titanium dioxide", match_type="exact", match_score=100.0
    )
    monkeypatch.setattr(
        mcp_server,
        "resolve_current_opinion",
        lambda query: ReevaluationStatus(
            substance_name="Titanium dioxide",
            substance_uuid="uuid-tio2",
            structured_result=tio2_opinion,
            substance_candidates=[tio2_candidate],
            structured_results={"uuid-tio2": tio2_opinion},
            candidates_total_found=1,
        ),
    )
    monkeypatch.setattr(mcp_server, "answer_question", _exploding)

    result = _call("get_reevaluation_status", {"substance": "titanium dioxide"})

    assert result.structured_content["candidates_shown"] == 1
    item = result.structured_content["results"][0]
    assert item["chemical_name"] == "Titanium dioxide"
    assert item["dossier_found"] is True
    assert item["adi_value"] is None
    assert item["adi_unit"] is None
    assert item["adi_justification"] is None
    assert item["discussion_available"] is False  # boilerplate
    assert item["doi"] == "10.2903/j.efsa.2021.6585"


# --------------------------------------------------------------------- #
# search_efsa_opinion -- sustancia conocida, usa answer_question
# --------------------------------------------------------------------- #


def test_search_efsa_opinion_known_substance_returns_narrative_answer(
    monkeypatch: pytest.MonkeyPatch,
):
    """Sustancia conocida -- el JSON debe incluir la respuesta narrativa
    (`answer`, ya fundamentada/citada por el Nodo 4 dentro del stub) más
    los metadatos de cita. `resolve_current_opinion` se deja como
    `_exploding` -- search_efsa_opinion no debería llamarlo, es el
    camino completo el que se ejecuta, no el parcial."""
    chunk = RetrievedChunk(
        text="fragmento narrativo real",
        substance_uuid="uuid-aspartame",
        chemical_name="Aspartame",
        dossier_uuid="dossier-aspartame",
        dossier_title=ASPARTAME_OPINION.title,
        substance_resolution_tier=1,
    )
    monkeypatch.setattr(
        mcp_server,
        "answer_question",
        lambda query: AnswerResult(
            answer="El ADI de aspartamo es 40 mg/kg pc/día, según el dictamen de 2013...",
            retrieved_chunks=[chunk],
            structured_result=ASPARTAME_OPINION,
            substance_name="Aspartame",
            substance_candidates=[ASPARTAME_CANDIDATE],
            structured_results={"uuid-aspartame": ASPARTAME_OPINION},
            candidates_total_found=1,
        ),
    )
    monkeypatch.setattr(mcp_server, "resolve_current_opinion", _exploding)

    result = _call("search_efsa_opinion", {"substance": "aspartame"})

    assert result.is_error is False
    assert result.structured_content == {
        "candidates_found": 1,
        "candidates_shown": 1,
        "substance_identified": "Aspartame",
        "answer": "El ADI de aspartamo es 40 mg/kg pc/día, según el dictamen de 2013...",
        "results": [
            {
                "chemical_name": "Aspartame",
                "match_type": "exact",
                "match_score": 100.0,
                "dossier_title": ASPARTAME_OPINION.title,
                "doi": "10.2903/j.efsa.2013.3496",
                "retrieved_chunks_count": 1,
            }
        ],
    }


# --------------------------------------------------------------------- #
# Sustancia NO identificada -- degradación con gracia en ambas
# --------------------------------------------------------------------- #


def test_get_reevaluation_status_unidentified_substance_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
):
    """El Nodo 1 no resolvió ninguna sustancia (LLM respondió NONE, o no
    hubo ningún candidato ni exacto, ni normalizado, ni fuzzy) --
    `results` debe venir VACÍO (`[]`), `candidates_found`/
    `candidates_shown` en 0, NUNCA un error ni un valor inventado.
    `safety_note` se mantiene igualmente (constante fija, no depende de
    haber identificado nada)."""
    monkeypatch.setattr(
        mcp_server,
        "resolve_current_opinion",
        lambda query: ReevaluationStatus(substance_name=None, substance_uuid=None, structured_result=None),
    )
    monkeypatch.setattr(mcp_server, "answer_question", _exploding)

    result = _call("get_reevaluation_status", {"substance": "esto no es un aditivo"})

    assert result.is_error is False
    assert result.structured_content == {
        "candidates_found": 0,
        "candidates_shown": 0,
        "substance_identified": None,
        "safety_note": SAFETY_NOTE,
        "results": [],
    }


def test_search_efsa_opinion_unidentified_substance_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
):
    """Mismo caso para el camino completo -- el Nodo 4 ya está diseñado
    para producir un mensaje de "no identificado" en vez de fallar (ver
    graph/build.py, `answer_question`/`_route_after_retrieval`); aquí
    solo se comprueba que el wrapper MCP no rompe ese contrato al
    empaquetar el resultado. `results` vacío, no un campo `None`
    aislado."""
    monkeypatch.setattr(
        mcp_server,
        "answer_question",
        lambda query: AnswerResult(
            answer="No he podido identificar de qué aditivo alimentario hablas.",
            retrieved_chunks=[],
            structured_result=None,
            substance_name=None,
        ),
    )
    monkeypatch.setattr(mcp_server, "resolve_current_opinion", _exploding)

    result = _call("search_efsa_opinion", {"substance": "esto no es un aditivo"})

    assert result.is_error is False
    assert result.structured_content == {
        "candidates_found": 0,
        "candidates_shown": 0,
        "substance_identified": None,
        "answer": "No he podido identificar de qué aditivo alimentario hablas.",
        "results": [],
    }


# --------------------------------------------------------------------- #
# Candidatos múltiples -- decisión de producto explícita: `results`
# NUNCA elige uno en silencio (ver CLAUDE.md, "Opción A" del rediseño).
# --------------------------------------------------------------------- #


DELTA_TOCOPHEROL_OPINION = OpinionReference(
    dossier_uuid="dossier-tocopherols",
    date_of_evaluation=date(2015, 9, 9),
    title=(
        "Scientific Opinion on the re-evaluation of tocopherol-rich extract (E 306), "
        "alpha-tocopherol (E 307), gamma-tocopherol (E 308) and delta-tocopherol (E 309) "
        "as food additives"
    ),
    doc_type="EFSA opinion",
    doi="10.2903/j.efsa.2015.4247",
    adi_value=None,
    adi_unit=None,
    adi_justification=None,
    discussion_text=None,
    discussion_is_boilerplate=False,
)
GAMMA_TOCOPHEROL_OPINION = OpinionReference(
    dossier_uuid="dossier-tocopherols",
    date_of_evaluation=date(2015, 9, 9),
    title=DELTA_TOCOPHEROL_OPINION.title,
    doc_type="EFSA opinion",
    doi="10.2903/j.efsa.2015.4247",
    adi_value=None,
    adi_unit=None,
    adi_justification=None,
    discussion_text=None,
    discussion_is_boilerplate=False,
)
DELTA_CANDIDATE = SubstanceCandidate(
    substance_uuid="uuid-delta", chemical_name="Delta-tocopherol", match_type="fuzzy", match_score=69.23
)
GAMMA_CANDIDATE = SubstanceCandidate(
    substance_uuid="uuid-gamma", chemical_name="Gamma-tocopherol", match_type="fuzzy", match_score=69.23
)


def test_get_reevaluation_status_multiple_candidates_returns_all_in_results(
    monkeypatch: pytest.MonkeyPatch,
):
    """Con 2 candidatos (tocoferol), `results` debe traer los 2, ninguno
    elegido en silencio como "el" resultado."""
    monkeypatch.setattr(
        mcp_server,
        "resolve_current_opinion",
        lambda query: ReevaluationStatus(
            substance_name="Tocopherol",
            substance_uuid="uuid-delta",
            structured_result=DELTA_TOCOPHEROL_OPINION,
            substance_candidates=[DELTA_CANDIDATE, GAMMA_CANDIDATE],
            structured_results={
                "uuid-delta": DELTA_TOCOPHEROL_OPINION,
                "uuid-gamma": GAMMA_TOCOPHEROL_OPINION,
            },
            candidates_total_found=2,
        ),
    )
    monkeypatch.setattr(mcp_server, "answer_question", _exploding)

    result = _call("get_reevaluation_status", {"substance": "tocopherol"})

    assert result.structured_content["candidates_found"] == 2
    assert result.structured_content["candidates_shown"] == 2
    names = [item["chemical_name"] for item in result.structured_content["results"]]
    assert names == ["Delta-tocopherol", "Gamma-tocopherol"]


def test_search_efsa_opinion_multiple_candidates_returns_all_in_results(
    monkeypatch: pytest.MonkeyPatch,
):
    """Mismo caso para el camino completo -- `results` con 2 entradas,
    `answer` sigue siendo un único texto narrativo compartido (ya trata
    cada candidato por separado internamente, ver
    graph/nodes.py::_build_user_prompt)."""
    chunk_delta = RetrievedChunk(
        text="fragmento de delta-tocoferol",
        substance_uuid="uuid-delta",
        chemical_name="Delta-tocopherol",
        dossier_uuid="dossier-tocopherols",
        dossier_title=DELTA_TOCOPHEROL_OPINION.title,
        substance_resolution_tier=1,
    )
    chunk_gamma = RetrievedChunk(
        text="fragmento de gamma-tocoferol",
        substance_uuid="uuid-gamma",
        chemical_name="Gamma-tocopherol",
        dossier_uuid="dossier-tocopherols",
        dossier_title=DELTA_TOCOPHEROL_OPINION.title,
        substance_resolution_tier=1,
    )
    monkeypatch.setattr(
        mcp_server,
        "answer_question",
        lambda query: AnswerResult(
            answer="Se han identificado 2 sustancias... (presentadas por separado)",
            retrieved_chunks=[chunk_delta, chunk_gamma],
            structured_result=DELTA_TOCOPHEROL_OPINION,
            substance_name="Tocopherol",
            substance_candidates=[DELTA_CANDIDATE, GAMMA_CANDIDATE],
            structured_results={
                "uuid-delta": DELTA_TOCOPHEROL_OPINION,
                "uuid-gamma": GAMMA_TOCOPHEROL_OPINION,
            },
            candidates_total_found=2,
        ),
    )
    monkeypatch.setattr(mcp_server, "resolve_current_opinion", _exploding)

    result = _call("search_efsa_opinion", {"substance": "tocopherol"})

    assert result.structured_content["candidates_found"] == 2
    assert result.structured_content["candidates_shown"] == 2
    results = result.structured_content["results"]
    assert [item["chemical_name"] for item in results] == ["Delta-tocopherol", "Gamma-tocopherol"]
    # Cada candidato solo cuenta SUS PROPIOS chunks, no los de todos.
    assert results[0]["retrieved_chunks_count"] == 1
    assert results[1]["retrieved_chunks_count"] == 1
    # `answer` es un único texto compartido, no se duplica ni se parte.
    assert result.structured_content["answer"] == "Se han identificado 2 sustancias... (presentadas por separado)"
