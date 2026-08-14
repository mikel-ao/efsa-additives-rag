"""
Test de regresión para la cadena de joins del Nodo 3 (vigencia).

Requiere el xlsx real de OpenFoodTox 3.0 en data/raw/. Se marca `skip`
automáticamente si no está presente, para no romper CI sin el dataset
(22.6 MB, no se versiona en el repo).

Caso de referencia: aspartamo (E 951). Verificado manualmente el
2026-08-14 durante el diseño del proyecto:
  5 registros de ADI (40 mg/kg pc/día, sin cambios) enlazan a dictámenes de
  2006-05-03, 2009-01-29, 2009-03-19, 2011-02-25 (statement) y 2013-11-28.
  El resultado esperado, filtrando por Type == 'EFSA opinion' y tomando
  MAX(fecha), es el dictamen de 2013-11-28 (re-evaluation of aspartame).
"""

from pathlib import Path

import pytest

from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore

XLSX_PATH = Path(__file__).parent.parent / "data" / "raw" / "OFT3_0_export_repository.xlsx"

pytestmark = pytest.mark.skipif(
    not XLSX_PATH.exists(),
    reason="Requiere el export real de OpenFoodTox en data/raw/ (no versionado)",
)


@pytest.fixture(scope="module")
def store() -> OpenFoodToxStore:
    return OpenFoodToxStore(XLSX_PATH)


def test_aspartame_current_opinion_is_2013_reevaluation(store: OpenFoodToxStore):
    substance_uuid = store.substance_uuid_by_name("Aspartame")
    assert substance_uuid is not None

    result = store.current_reference_value_opinion(substance_uuid)

    assert result is not None
    assert result.date_of_evaluation.isoformat().startswith("2013-11-28")
    assert "re-evaluation" in result.title.lower()
    assert result.doc_type == "EFSA opinion"


def test_reevaluation_corpus_is_approximately_expected_size(store: OpenFoodToxStore):
    """No es un test de igualdad exacta -- el corpus crece con el tiempo
    (programa de reevaluación sigue activo en 2026). Es una alarma de
    regresión: si el número cae muy por debajo de lo verificado en el
    diseño (118), algo se ha roto en el filtro, no en los datos de EFSA.
    """
    unique_opinions = store.unique_reevaluation_opinions()
    assert len(unique_opinions) >= 110, (
        "El corpus de dictámenes de reevaluación es sospechosamente pequeño "
        "-- revisar si el filtro Domain.FoodDomain + 're-evaluation' en "
        "título sigue siendo válido para la versión del xlsx en uso."
    )
