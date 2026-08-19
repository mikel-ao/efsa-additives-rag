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
    FUZZY_MATCH_LOW_THRESHOLD,
    OpenFoodToxStore,
)

# Sustancias del Grupo A (sesión 17-ago-2026, ver CLAUDE.md "Hallazgos
# verificados"): su dictamen vigente real no contiene "re-evaluation" en el
# título, así que quedaban fuera de reevaluation_dossiers() hasta el cierre
# del Grupo A (ADDITIONAL_REEVAL_TITLE_PATTERNS / SAFETY_ASSESSMENT_FOOD_ADDITIVE_PATTERN).
GROUP_A_SUBSTANCE_NAMES = (
    "Titanium dioxide",
    "Sodium propionate",
    "Beetroot Red, betanin",
    "Beta-carotene",
    "Beta-apo-8'-carotenal (C 30)",
    "Allura Red AC",
)

# Sustancias del "híbrido estrecho" (sesión 17-ago-2026, ver CLAUDE.md
# "Hallazgos verificados" -- diagnóstico del híbrido tras el cierre del
# Grupo A): tienen algún dossier en el corpus por patrón de título, pero
# su dictamen REALMENTE vigente (current_reference_value_opinion) es un
# documento DISTINTO, no capturado por ningún patrón. current_reevaluation_corpus()
# debe sustituir el documento viejo por el vigente para cada una, no
# añadir el vigente como entrada adicional (sustitución 1:1, no unión).
NARROW_HYBRID_SUBSTITUTIONS = {
    "Sunset Yellow FCF": (
        "Scientific Opinion on the re-evaluation of Sunset Yellow FCF (E 110) as a food additive",
        "Reconsideration of the temporary ADI and refined exposure assessment for Sunset Yellow FCF (E110)",
    ),
    "Sucrose esters of fatty acids": (
        "Scientific Opinion on the safety of sucrose esters of fatty acids prepared from "
        "vinyl esters of fatty acids and on the extension of use of sucrose esters of fatty "
        "acids in flavourings",
        "Refined exposure assessment of sucrose esters of fatty acids (E 473) from its use as a food additive",
    ),
    "Rosemary extract liquid of natural origin": (
        "Extension of use of extracts of rosemary (E 392) in fat-based spreads",
        "Refined exposure assessment of extracts of rosemary (E 392) from its use as food additive",
    ),
    "Steviol glycosides": (
        "Scientific opinion on the safety of the extension of use of steviol glycosides (E 960) as a food additive",
        "Safety of a proposed amendment of the specifications for steviol glycosides (E 960) as "
        "a food additive: to expand the list of steviol glycosides to all those identified in "
        "the leaves of Stevia Rebaudiana Bertoni",
    ),
    "Calcium lignosulphonate (40-65)": (
        "Statement on the safety of calcium lignosulphonate (40-65) as a food additive",
        "Scientific Opinion on the use of calcium lignosulphonate (40-65) as a carrier for "
        "vitamins and carotenoids",
    ),
    "Lycopene": (
        "Statement on the divergence between the risk assessment of lycopene by EFSA and the "
        "Joint FAO/WHO Expert Committee on Food Additives(JECFA)",
        "Use of lycopene as a food colour",
    ),
}

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


def test_sunset_yellow_current_opinion_excludes_feed_regulation_dossier(
    store: OpenFoodToxStore,
):
    """Caso de regresión del bug de Grupo B (sesión 17-ago-2026, ver
    CLAUDE.md): un dossier de 2022 sobre un aditivo de PIENSO ANIMAL
    ("Safety and efficacy of a feed additive consisting of Sunset Yellow
    FCF for cats and dogs, ornamental fish...") está mal etiquetado
    Domain.FoodDomain == 'food additives' pese a tener
    Domain.Regulation == 'Regulation (EC) No 1831/2003' (regulación de
    pienso animal, FEEDAP). Antes del fix, ganaba MAX(fecha) y
    desplazaba al dictamen alimentario real. Tras excluir por
    Domain.Regulation, el resultado esperado es el dictamen de 2014
    ("Reconsideration of the temporary ADI and refined exposure
    assessment for Sunset Yellow FCF (E110)") -- el 'EFSA opinion' de
    dominio alimentario más reciente tras la exclusión (más reciente que
    el de 2009, que sí lleva "re-evaluation" en el título pero fue
    reconsiderado/refinado por el de 2014).
    """
    substance_uuid = store.substance_uuid_by_name("Sunset Yellow FCF")
    assert substance_uuid is not None

    result = store.current_reference_value_opinion(substance_uuid)

    assert result is not None
    assert result.date_of_evaluation.isoformat().startswith("2014-06-26")
    assert "sunset yellow" in result.title.lower()
    assert "cats and dogs" not in result.title.lower()
    assert "feed additive" not in result.title.lower()


def test_olive_leaf_extract_has_no_real_food_additive_opinion(store: OpenFoodToxStore):
    """Segundo caso del bug de Grupo B (sesión 17-ago-2026): "Olive leaf
    dry extract from O. europaea L." no tiene NINGÚN dictamen de aditivo
    alimentario real en el dataset -- su única fila en DOSSIER es un
    dossier de pienso animal ("...used as a sensory additive in feed for
    all animal species", 2020-01-28) mal etiquetado Domain.FoodDomain ==
    'food additives'. A diferencia de Sunset Yellow FCF, aquí no hay
    ningún dictamen alimentario real que "recuperar" tras excluir el de
    pienso animal -- el resultado correcto es None (sin dictamen
    vigente), no inventar relevancia alimentaria con el dossier de
    pienso. Nodo 3 (verify_currency_node) ya marca vigencia_ambigua=True
    en ese caso, y el Nodo 4 (_format_structured_result) ya devuelve un
    mensaje explícito de "no se ha podido determinar un dictamen
    vigente" en vez de simular que lo hay -- este test bloquea que un
    futuro cambio vuelva a colar el dossier de pienso animal como si
    fuera un dictamen alimentario válido.
    """
    substance_uuid = store.substance_uuid_by_name(
        "Olive leaf dry extract from O. europaea L."
    )
    assert substance_uuid is not None

    result = store.current_reference_value_opinion(substance_uuid)

    assert result is None


def test_reevaluation_corpus_is_approximately_expected_size(store: OpenFoodToxStore):
    """No es un test de igualdad exacta -- el corpus crece con el tiempo
    (programa de reevaluación sigue activo en 2026). Es una alarma de
    regresión: si el número cae muy por debajo de lo verificado en sesión
    17-ago-2026 (162, tras el cierre del Grupo A -- ver CLAUDE.md), algo
    se ha roto en el filtro, no en los datos de EFSA.

    Umbral subido de 110 a 130 al corregir 118->136 (sesión 16-ago-2026),
    y de 130 a 150 al corregir 136->162 (sesión 17-ago-2026, cierre del
    Grupo A): en ambos casos, con el umbral anterior el test seguía en
    verde aunque el fix correspondiente se rompiera del todo y el corpus
    volviera a caer al valor previo -- ya no protegía nada real.
    """
    unique_opinions = store.unique_reevaluation_opinions()
    assert len(unique_opinions) >= 150, (
        "El corpus de dictámenes de reevaluación es sospechosamente pequeño "
        "-- revisar si el filtro Domain.FoodDomain + 're-evaluation'/"
        "ADDITIONAL_REEVAL_TITLE_PATTERNS en título (o el rescate de "
        "dominio mal etiquetado, _is_mistagged_food_additive_reevaluation) "
        "sigue siendo válido para la versión del xlsx en uso."
    )


def test_group_a_substances_current_opinion_is_in_reevaluation_corpus(
    store: OpenFoodToxStore,
):
    """Caso de regresión del cierre del Grupo A (sesión 17-ago-2026, ver
    CLAUDE.md): antes de ampliar reevaluation_dossiers() con
    ADDITIONAL_REEVAL_TITLE_PATTERNS / SAFETY_ASSESSMENT_FOOD_ADDITIVE_PATTERN,
    el dictamen vigente real de estas 6 sustancias (devuelto por
    current_reference_value_opinion, que nunca exigió "re-evaluation" en
    el título) no estaba en el corpus que define reevaluation_dossiers()
    -- title patterns como "extension of use", "statement on",
    "reconsideration of the ADI" o "safety assessment... as a food
    additive" no se reconocían como sinónimos válidos. Este test bloquea
    que una futura regresión del filtro vuelva a excluirlas.
    """
    corpus_uuids = set(store.reevaluation_dossiers()["Document UUID"])

    for name in GROUP_A_SUBSTANCE_NAMES:
        substance_uuid = store.substance_uuid_by_name(name)
        assert substance_uuid is not None, f"Sustancia no encontrada: {name!r}"

        result = store.current_reference_value_opinion(substance_uuid)
        assert result is not None, f"Sin dictamen vigente para {name!r}"
        assert result.dossier_uuid in corpus_uuids, (
            f"El dictamen vigente de {name!r} ({result.title!r}) no está "
            "en reevaluation_dossiers() -- el fix de cierre del Grupo A "
            "se ha roto."
        )


def test_current_reevaluation_corpus_is_same_size_as_title_corpus(
    store: OpenFoodToxStore,
):
    """current_reevaluation_corpus() sustituye 6 documentos (ver
    NARROW_HYBRID_SUBSTITUTIONS), no los añade -- el tamaño final debe
    seguir siendo 162, igual que unique_reevaluation_opinions(). Si este
    test empieza a fallar con 168, la sustitución se ha roto y ha vuelto
    a comportarse como una unión de conjuntos (bug ya corregido una vez
    en sesión 17-ago-2026, ver CLAUDE.md). Si falla con un número mucho
    más bajo (p.ej. 143), la comprobación de "ya capturado por el filtro
    de título" está usando el conjunto YA DEDUPLICADO por título en vez
    del conjunto completo -- un dictamen de grupo (varias filas DOSSIER
    con el mismo título, distinto Document UUID) da un falso negativo y
    se sustituyen de más documentos que sí seguían vigentes (otro bug ya
    corregido una vez, mismo día).
    """
    title_corpus = store.unique_reevaluation_opinions()
    final_corpus = store.current_reevaluation_corpus()

    assert len(final_corpus) == len(title_corpus), (
        f"current_reevaluation_corpus() devolvió {len(final_corpus)} "
        f"dictámenes, se esperaban {len(title_corpus)} (mismo tamaño que "
        "unique_reevaluation_opinions() -- sustitución 1:1, no unión ni "
        "sobre-poda)."
    )


def test_current_reevaluation_corpus_substitutes_narrow_hybrid_cases(
    store: OpenFoodToxStore,
):
    """Para cada una de las 6 sustancias del híbrido estrecho (sesión
    17-ago-2026), current_reevaluation_corpus() debe contener el
    dictamen vigente real y NO el documento viejo que
    unique_reevaluation_opinions() tenía para esa sustancia -- una
    sustitución explícita, no una entrada añadida junto a la vieja.
    """
    final_titles = set(
        store.current_reevaluation_corpus()["LiteratureReference.EFSAOutputTitle"]
    )

    for substance_name, (old_title, new_title) in NARROW_HYBRID_SUBSTITUTIONS.items():
        assert new_title in final_titles, (
            f"{substance_name!r}: falta el dictamen vigente real "
            f"({new_title!r}) en current_reevaluation_corpus()."
        )
        assert old_title not in final_titles, (
            f"{substance_name!r}: el documento viejo ({old_title!r}) "
            "sigue en current_reevaluation_corpus() -- debía haber sido "
            "sustituido, no coexistir con el vigente."
        )


def test_current_reevaluation_corpus_keeps_substances_already_well_represented(
    store: OpenFoodToxStore,
):
    """Sustancias cuyo dictamen vigente YA está en el corpus por otro
    patrón de título (p.ej. titanio E171: "re-evaluation" de 2016 +
    "safety assessment...as a food additive" de 2021, ambos ya en el
    corpus) NO deben perder su documento histórico -- solo se sustituye
    cuando el vigente real está genuinamente ausente. Bloquea la
    regresión encontrada en sesión 17-ago-2026 donde una primera versión
    de current_reevaluation_corpus() sobre-podaba el corpus a 143
    quitando documentos históricos legítimos de sustancias como titanio,
    Allura Red AC o ácido sórbico que ya tenían su vigente representado.
    """
    final_titles = set(
        store.current_reevaluation_corpus()["LiteratureReference.EFSAOutputTitle"]
    )

    still_expected_titles = (
        "Re-evaluation of titanium dioxide (E 171) as a food additive",
        "Safety assessment of titanium dioxide (E171) as a food additive",
        "Scientific Opinion on the re-evaluation of Allura Red AC (E 129) as a food additive",
        "Statement on Allura Red AC and other sulphonated mono azo dyes authorised as food and feed additives.",
    )
    for title in still_expected_titles:
        assert title in final_titles, (
            f"{title!r} desapareció de current_reevaluation_corpus() -- "
            "no debía tocarse, su sustancia ya tenía el vigente "
            "representado por otro patrón de título."
        )


# substances_per_dossier() (sesión 17-ago-2026, continuación 4) -- extraído
# del paso intermedio que current_reevaluation_corpus() ya calculaba y
# descartaba internamente. Casos de regresión ver CLAUDE.md, "Hallazgos
# verificados": nitritos prueba la exclusión de sustancias de referencia
# toxicológica sin ADI propio (los 17 compuestos N-nitroso NO deben
# aparecer); tartratos y glutamato prueban que se recuperan TODAS las
# sustancias de un dictamen de grupo, no solo la que sobrevive el
# drop_duplicates por título de unique_reevaluation_opinions().
#
# OJO al leer los números: en el diagnóstico de la sesión anterior se
# reportaron "6 perdidas" (tartratos) y "5 perdidas" (glutamato) -- esas
# cifras son sustancias INVISIBLES tras el dedup (unión menos la 1 que
# sobrevive), no el total. El total real (lo que debe devolver esta
# función) es 7 para tartratos y 6 para glutamato -- verificado contra las
# hojas reales antes de fijar estos tests, no una suposición.


def test_substances_per_dossier_nitrites_excludes_toxicological_references(
    store: OpenFoodToxStore,
):
    """El dictamen de nitritos tiene 20 filas DOSSIER hermanas con el
    mismo título, pero solo 3 son sustancias con ADI propio (Nitrites,
    Potassium nitrite, Sodium nitrite) -- las otras 17 son compuestos
    N-nitroso (N-nitrosodimetilamina y similares) enlazados vía
    FLEX_SUM.ToxRefValues.OtherReferenceValues como referencia
    toxicológica dentro de la caracterización de peligro, sin ADI propio
    para ese enlace. Deben quedar excluidos, no contarse como "sustancias
    del dossier".
    """
    corpus = store.current_reevaluation_corpus()
    row = corpus[
        corpus["LiteratureReference.EFSAOutputTitle"]
        == "Re-evaluation of potassium nitrite (E 249) and sodium nitrite (E 250) as food additives"
    ].iloc[0]

    mapping = store.substances_per_dossier(corpus)
    names = {s.chemical_name for s in mapping[row["Document UUID"]]}

    assert names == {"Nitrites", "Potassium nitrite", "Sodium nitrite"}, (
        f"Se esperaban exactamente 3 sustancias con ADI propio, se obtuvo: {names!r} "
        "-- si aparece algún compuesto N-nitroso, el filtro por ADI_LOWER_VALUE_COLUMN "
        "se ha roto."
    )


def test_substances_per_dossier_tartrates_group_returns_all_seven(
    store: OpenFoodToxStore,
):
    """El título de tartratos (E 334-E 337, E 354) genera 7 filas DOSSIER
    hermanas -- una por sal -- pero unique_reevaluation_opinions() solo
    conserva 1 tras deduplicar por título. substances_per_dossier() debe
    recuperar las 7, no solo la ligada a la fila superviviente.
    """
    corpus = store.current_reevaluation_corpus()
    row = corpus[
        corpus["LiteratureReference.EFSAOutputTitle"]
        == (
            "Re-evaluation of L(+)-tartaric acid (E 334), sodium tartrates (E 335), "
            "potassium tartrates (E 336), potassium sodium tartrate (E 337) and "
            "calcium tartrate (E 354) as food additives"
        )
    ].iloc[0]

    mapping = store.substances_per_dossier(corpus)
    names = {s.chemical_name for s in mapping[row["Document UUID"]]}

    assert names == {
        "Tartaric acid (L(+)-)",
        "Sodium tartrates",
        "Potassium tartrates",
        "Potassium acid tartrate",
        "Sodium potassium tartrate",
        "Calcium tartrate",
        "Monosodium tartrate",
    }, f"Se esperaban las 7 sales del grupo de tartratos, se obtuvo: {names!r}"


def test_substances_per_dossier_glutamates_group_returns_all_six(
    store: OpenFoodToxStore,
):
    """El título de glutamatos (E 620-E 625) genera varias filas DOSSIER
    hermanas -- substances_per_dossier() debe recuperar las 6 sales con
    ADI propio, no solo la de la fila superviviente del dedup.
    """
    corpus = store.current_reevaluation_corpus()
    row = corpus[
        corpus["LiteratureReference.EFSAOutputTitle"]
        == (
            "Re-evaluation of glutamic acid (E 620), sodium glutamate (E 621), "
            "potassium glutamate (E 622), calcium glutamate (E 623), ammonium "
            "glutamate (E 624) and magnesium glutamate (E 625) as food additives"
        )
    ].iloc[0]

    mapping = store.substances_per_dossier(corpus)
    names = {s.chemical_name for s in mapping[row["Document UUID"]]}

    assert names == {
        "Glutamic acid",
        "Monosodium L-Glutamate",
        "Monopotassium L-glutamate",
        "Calcium di-L-glutamate",
        "Monoammonium L-glutamate",
        "Magnesium diglutamate",
    }, f"Se esperaban las 6 sales del grupo de glutamatos, se obtuvo: {names!r}"


# --------------------------------------------------------------------- #
# resolve_substance_candidates() -- resolución multi-candidato (sesión
# 19-ago-2026, ver CLAUDE.md, diseño de resolución multi-candidato).
# Los números de score citados en los asserts vienen de la calibración
# real contra el universo de 246 sustancias resolubles hecha en esa
# sesión -- si cambian, es señal de que el universo o el corpus
# cambiaron, no que el test esté mal.
# --------------------------------------------------------------------- #


def test_resolve_substance_candidates_exact_match_unchanged(store: OpenFoodToxStore):
    """Un nombre exacto sigue resolviendo a un único candidato tier
    "exact", score 100 -- mismo comportamiento que substance_uuid_by_name
    de siempre, sin regresión."""
    candidates = store.resolve_substance_candidates("Aspartame")

    assert len(candidates) == 1
    assert candidates[0].match_type == "exact"
    assert candidates[0].match_score == 100.0
    assert candidates[0].substance_uuid == store.substance_uuid_by_name("Aspartame")


def test_resolve_substance_candidates_normalizes_hyphen_space_mismatch(
    store: OpenFoodToxStore,
):
    """Diagnóstico de tocoferol (sesión 19-ago-2026): la hipótesis del
    símbolo griego (alpha/beta/gamma vs. α/β/γ) se probó y se descartó
    con datos reales -- SUB no tiene ninguna fila de tocoferol con
    símbolo griego. La causa real es que el Nodo 1 (LLM) hyphena de
    forma inconsistente ("Alpha tocopherol" sin guion, mientras SUB solo
    tiene "Alpha-tocopherol" con guion). Este test fija el fix de
    normalización espacio<->guion como coincidencia EXACTA adicional,
    sin fuzzy."""
    for query, expected_name in (
        ("Alpha tocopherol", "Alpha-tocopherol"),
        ("Beta tocopherol", "beta-tocopherol"),
    ):
        candidates = store.resolve_substance_candidates(query)
        assert len(candidates) == 1, f"{query!r} -> {candidates!r}"
        assert candidates[0].match_type == "exact_normalized"
        assert candidates[0].match_score == 100.0
        assert candidates[0].chemical_name == expected_name


def test_resolve_substance_candidates_typo_resolves_via_fuzzy(store: OpenFoodToxStore):
    """Typo real ('plai caramel' por 'Plain caramel') -- debe resolver
    vía fuzzy, con 'Plain caramel' como candidato de mayor score."""
    candidates = store.resolve_substance_candidates("plai caramel")

    assert candidates, "Se esperaba al menos 1 candidato fuzzy"
    assert all(c.match_type == "fuzzy" for c in candidates)
    assert candidates[0].chemical_name == "Plain caramel"
    assert candidates[0].match_score == pytest.approx(88.0, abs=0.5)


def test_resolve_substance_candidates_generic_tocopherol_returns_multiple(
    store: OpenFoodToxStore,
):
    """'Tocopherol' (salida REAL del Nodo 1 para preguntas genéricas de
    tocoferol, verificado con llamada real a la API en esta sesión) no
    coincide con ninguna de las 7 filas reales de SUB (todas con
    prefijo) -- debe devolver VARIOS candidatos plausibles, nunca elegir
    uno en silencio. Los 4 esperados son los mismos 4 de la calibración
    real de esta sesión."""
    candidates = store.resolve_substance_candidates("Tocopherol")
    names = {c.chemical_name for c in candidates}

    assert names == {
        "Delta-tocopherol",
        "Gamma-tocopherol",
        "DL-alpha-tocopherol",
        "Tocopherol-rich extract",
    }
    assert all(c.match_type == "fuzzy" for c in candidates)
    assert all(c.match_score >= FUZZY_MATCH_LOW_THRESHOLD for c in candidates)
    # "Glycerol" (sustancia real no relacionada) debe quedar excluido --
    # verificado en la calibración que da 55,56, por debajo del umbral.
    assert "Glycerol" not in names


def test_resolve_substance_candidates_tocopherol_tie_break_is_deterministic(
    store: OpenFoodToxStore,
):
    """Desempate determinista (_candidate_sort_key, ver CLAUDE.md, punto
    5 del diseño de resolución multi-candidato): Delta-tocopherol y
    Gamma-tocopherol empatan EXACTO a score (69,23, verificado en la
    calibración real) -- el orden debe ser siempre el mismo, con
    Delta-tocopherol primero (orden alfabético del nombre como
    desempate, "d" < "g"). Repetido varias veces para confirmar que no
    es un orden accidental de un único run."""
    for _ in range(3):
        candidates = store.resolve_substance_candidates("Tocopherol")
        assert candidates[0].chemical_name == "Delta-tocopherol"
        assert candidates[1].chemical_name == "Gamma-tocopherol"
        assert candidates[0].match_score == candidates[1].match_score


def test_resolve_substance_candidates_unrelated_query_returns_empty(
    store: OpenFoodToxStore,
):
    """Consultas sin relación real con ninguna sustancia del corpus deben
    devolver una lista vacía -- cero falsos positivos, verificado en la
    calibración real (máximo 46-57 sobre el universo restringido, por
    debajo del umbral de 60)."""
    for query in ("quantum flux capacitor", "banana smoothie recipe"):
        assert store.resolve_substance_candidates(query) == []


def test_resolve_substance_candidates_recovers_duplicate_chemical_name(
    store: OpenFoodToxStore,
):
    """Bug latente corregido en esta sesión: SUB.ChemicalName tiene 9
    nombres duplicados con distinto UUID -- 'Sodium saccharin' es uno de
    ellos y SÍ está en el universo de 246 sustancias resolubles.
    substance_uuid_by_name (sin cambios) solo devuelve el primero;
    resolve_substance_candidates debe devolver AMBOS."""
    candidates = store.resolve_substance_candidates("Sodium saccharin")

    assert len(candidates) == 2
    assert all(c.match_type == "exact" for c in candidates)
    assert len({c.substance_uuid for c in candidates}) == 2
