"""
Tests para el Nodo 4 (graph/nodes.py) -- formateo del contexto que se
envía al LLM.

Los tests de `_format_structured_result` (tier 1/2 de ADI) requieren el
xlsx real de OpenFoodTox 3.0 en data/raw/ para tener un `OpinionReference`
real de cada categoría -- se saltan automáticamente si no está presente,
mismo patrón que tests/test_openfoodtox_joins.py.

Los tests de `_format_retrieved_chunks` (tier 3 de `RetrievedChunk`) NO
requieren el xlsx -- construyen el dataclass directamente, sin pasar por
Nodo 2 (que sigue sin implementar).
"""

from pathlib import Path

import pytest

from efsa_rag.graph.nodes import (
    RetrievedChunk,
    _format_retrieved_chunks,
    _format_structured_result,
)
from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore

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
