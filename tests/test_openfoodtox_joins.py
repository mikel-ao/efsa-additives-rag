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

from efsa_rag.ingestion.openfoodtox import (
    ADI_JUSTIFICATION_COLUMN,
    ADI_LOWER_VALUE_COLUMN,
    ADI_UNIT_COLUMN,
    DISCUSSION_COLUMN,
    OpenFoodToxStore,
)

XLSX_PATH = Path(__file__).parent.parent / "data" / "raw" / "OFT3_0_export_repository.xlsx"

pytestmark = pytest.mark.skipif(
    not XLSX_PATH.exists(),
    reason="Requiere el export real de OpenFoodTox en data/raw/ (no versionado)",
)


@pytest.fixture(scope="module")
def store() -> OpenFoodToxStore:
    return OpenFoodToxStore(XLSX_PATH)


def test_flex_sum_toxref_has_expected_adi_columns(store: OpenFoodToxStore):
    """Los nombres de columna de ADI se confirmaron de memoria en una
    sesión anterior (no releídos carácter a carácter contra el xlsx real
    hasta que este test corrió con el archivo presente). Si esto falla,
    el nombre real difiere -- corregir las constantes en
    ingestion/openfoodtox.py, no este test.
    """
    columns = set(store.flex_sum_toxref.columns)
    for expected in (ADI_LOWER_VALUE_COLUMN, ADI_UNIT_COLUMN, ADI_JUSTIFICATION_COLUMN):
        assert expected in columns, (
            f"Columna esperada {expected!r} no está en FLEX_SUM.ToxRefValues -- "
            f"columnas reales disponibles: {sorted(columns)}"
        )


def test_end_sum_has_expected_discussion_column(store: OpenFoodToxStore):
    columns = set(store.end_sum.columns)
    assert DISCUSSION_COLUMN in columns, (
        f"Columna esperada {DISCUSSION_COLUMN!r} no está en END_SUM -- "
        f"columnas reales disponibles: {sorted(columns)}"
    )


def test_aspartame_current_opinion_is_2013_reevaluation(store: OpenFoodToxStore):
    substance_uuid = store.substance_uuid_by_name("Aspartame")
    assert substance_uuid is not None

    result = store.current_reference_value_opinion(substance_uuid)

    assert result is not None
    assert result.date_of_evaluation.isoformat().startswith("2013-11-28")
    assert "re-evaluation" in result.title.lower()
    assert result.doc_type == "EFSA opinion"

    # ADI conocido para aspartamo: 40 mg/kg pc/día, sin cambios entre
    # reevaluaciones -- debe venir ligado al dossier de 2013 concreto, no a
    # cualquier registro de ADI de la sustancia.
    assert result.adi_value == pytest.approx(40.0)
    assert result.adi_unit is not None and "mg/kg" in result.adi_unit.lower()
    assert result.adi_justification not in (None, "")

    # La discusión narrativa de aspartamo (dossier 2013) es solo la frase
    # de apertura del mandato (267 caracteres, sin razonamiento del panel)
    # -- debe detectarse como boilerplate, no citarse como si fuera
    # discusión sustantiva.
    assert result.discussion_text is not None
    assert result.discussion_is_boilerplate is True


def test_propyl_gallate_current_opinion_excludes_animal_feed_dossier(store: OpenFoodToxStore):
    """Caso de regresión del bug de dominio mixto (sesión 16-ago-2026):
    propil galato tiene 2 candidatos 'EFSA opinion' -- el dictamen real de
    aditivo alimentario (E 310, 2014-04-01, Domain.FoodDomain ==
    'food additives') y un dictamen de seguridad como aditivo de PIENSO
    ANIMAL (2020-03-17, FEEDAP, Domain.FoodDomain == 'technological
    additives'), sin relación con el uso alimentario. Antes del fix,
    MAX(fecha) sin filtrar por dominio devolvía el de pienso animal --
    contexto regulatorio completamente distinto para la misma sustancia.
    """
    substance_uuid = store.substance_uuid_by_name("Propyl gallate")
    assert substance_uuid is not None

    result = store.current_reference_value_opinion(substance_uuid)

    assert result is not None
    assert result.date_of_evaluation.isoformat().startswith("2014-04-01")
    assert "food additive" in result.title.lower()
    assert "animal species" not in result.title.lower()


def test_silver_current_opinion_includes_mistagged_domain_followup(store: OpenFoodToxStore):
    """Caso de regresión de la CASI-regresión (sesión 16-ago-2026): la
    plata (E 174) tiene un follow-up de reevaluación real y vigente
    (2025-03-06, "Follow-up of the re-evaluation of silver (E 174) as a
    food additive") etiquetado Domain.FoodDomain == 'other:' en vez de
    'food additives' -- ya mencionado en CLAUDE.md como programa activo.
    Filtrar candidatos solo por Domain.FoodDomain == 'food additives' (sin
    la rama de título) descartaría este follow-up y devolvería el dictamen
    de 2015-12-10, ya superado. Este test bloquea esa regresión.
    """
    substance_uuid = store.substance_uuid_by_name("Silver (Ag)")
    assert substance_uuid is not None

    result = store.current_reference_value_opinion(substance_uuid)

    assert result is not None
    assert result.date_of_evaluation.isoformat().startswith("2025-03-06")
    assert "follow-up" in result.title.lower()
    assert "silver" in result.title.lower()


def test_reevaluation_corpus_is_approximately_expected_size(store: OpenFoodToxStore):
    """No es un test de igualdad exacta -- el corpus crece con el tiempo
    (programa de reevaluación sigue activo en 2026). Es una alarma de
    regresión: si el número cae muy por debajo de lo verificado en sesión
    16-ago-2026 (136, tras corregir el filtro de dominio -- ver
    CLAUDE.md), algo se ha roto en el filtro, no en los datos de EFSA.

    Umbral subido de 110 a 130 al corregir 118->136: con 110 el test
    seguía en verde aunque el fix de dominio se rompiera del todo y el
    corpus volviera a caer a 118 -- ya no protegía nada real.
    """
    unique_opinions = store.unique_reevaluation_opinions()
    assert len(unique_opinions) >= 130, (
        "El corpus de dictámenes de reevaluación es sospechosamente pequeño "
        "-- revisar si el filtro Domain.FoodDomain + 're-evaluation' en "
        "título (o el rescate de dominio mal etiquetado,"
        " _is_mistagged_food_additive_reevaluation) sigue siendo válido "
        "para la versión del xlsx en uso."
    )
