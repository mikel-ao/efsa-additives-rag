"""
Ingesta y consultas deterministas sobre OpenFoodTox 3.0 (EFSA, Zenodo).

Cadena de joins verificada manualmente con el caso aspartamo (E 951):
    FLEX_SUM.ToxRefValues --Document UUID--> DOSSIER_DOCS --DOSSIER UUID--> DOSSIER

Resultado confirmado: MAX(fecha) filtrado por Type == 'EFSA opinion' devuelve
correctamente el dictamen de reevaluación de 2013-11-28, entre 5 dictámenes
candidatos (2006, 2009 x2, 2011 statement, 2013).

Ver docs/efsa-rag-proyecto.html -> ARCHITECTURE.md para el razonamiento completo.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

# Filtro de corpus verificado: filtrar solo por Domain.Regulation infravalora
# el corpus real (62 filas vs. 278 reales) porque la mayoría de reevaluaciones
# están etiquetadas con el reglamento marco 1333/2008, no con el 257/2010.
FOOD_DOMAIN_VALUE = "food additives"
REEVAL_TITLE_MARKER = "re-evaluation"
FOOD_ADDITIVE_TITLE_PHRASE = "food additive"

# Heurístico de rescate COMPARTIDO por reevaluation_dossiers() y por el
# filtro de candidatos de current_reference_value_opinion -- extraído a una
# única función (_is_mistagged_food_additive_reevaluation, más abajo) tras
# detectar que las dos implementaciones habían divergido una vez ya
# (sesión 16-ago-2026). MISMA CLASE DE RIESGO que el filtro de corpus de
# arriba: aproximación verificada contra los casos conocidos, no garantía
# estructural.
#
# Domain.FoodDomain == FOOD_DOMAIN_VALUE por sí solo no basta: hay
# follow-ups reales de aditivos alimentarios (plata E 174 2025, sílice
# E 551, goma garrofín E 410, goma xantana E 415, ésteres cítricos E 472c,
# acesulfamo K E 950, sacarina E 954, eritritol E 968, neotamo E 961, y
# 9 más -- 18 en total, verificados) etiquetados Domain.FoodDomain ==
# 'other:' (o 'nutrient sources', o vacío) en vez de 'food additives'.
# Filtrar solo por dominio los descartaría.
#
# NO basta con exigir solo FOOD_ADDITIVE_TITLE_PHRASE en el título: 1.360
# dictámenes de Flavouring Group Evaluation (dominio 'flavourings') también
# contienen "food additive" en el título porque el panel que los evalúa se
# llama literalmente "Panel on Food Additives, Flavourings, Processing Aids
# and Materials in Contact with Food (AFC)" -- la frase aparece por el
# nombre del comité, no porque el dictamen sea una reevaluación de aditivo.
# Exigir FOOD_ADDITIVE_TITLE_PHRASE junto con REEVAL_TITLE_MARKER sí es
# seguro: verificado que ningún dictamen de dominio 'flavourings'/'feed'/
# equivalentes contiene ambas frases a la vez.
#
# IMPORTANTE -- este rescate NO sustituye por sí solo el filtro de dominio
# correcto en current_reference_value_opinion: esa función confía en
# Domain.FoodDomain == FOOD_DOMAIN_VALUE sin exigir además
# REEVAL_TITLE_MARKER, a propósito. Verificado con dióxido de titanio
# (E 171): el dictamen que de hecho concluyó que ya no es seguro como
# aditivo ("Safety assessment of titanium dioxide (E171) as a food
# additive", 2021-03-25, domain correcto) NO contiene la palabra
# "re-evaluation" -- exigirla ahí habría hecho perder ese dictamen a favor
# de uno de 2016 ya superado. reevaluation_dossiers() sí exige
# REEVAL_TITLE_MARKER siempre porque su propósito es distinto (definir el
# corpus de REEVALUACIONES, no elegir el dictamen vigente de una
# sustancia) -- no unificar esa diferencia sin volver a verificar contra
# casos como este.

# Tipos de documento que SÍ cuentan como dictamen formal para el heurístico
# de vigencia. Los 'EFSA statement' se excluyen del MAX(fecha) porque pueden
# postdatar una reevaluación sin sustituirla (caso verificado: statement de
# aspartamo en 2011 es posterior al opinion de 2009 pero no lo reemplaza).
VALID_OPINION_TYPES = {"EFSA opinion"}


def _is_mistagged_food_additive_reevaluation(df: pd.DataFrame) -> pd.Series:
    """Filas de DOSSIER cuyo Domain.FoodDomain NO es FOOD_DOMAIN_VALUE pero
    el título deja claro que sí son una reevaluación de aditivo alimentario
    real (mal etiquetadas con otro dominio). Compartida por
    reevaluation_dossiers() y current_reference_value_opinion -- ver el
    comentario largo junto a FOOD_ADDITIVE_TITLE_PHRASE arriba para el
    razonamiento completo y las verificaciones hechas antes de usarla.

    Exige AMBAS frases a la vez (ni FOOD_ADDITIVE_TITLE_PHRASE ni
    REEVAL_TITLE_MARKER solas son seguras, verificado).
    """
    title_lower = df["LiteratureReference.EFSAOutputTitle"].fillna("").str.lower()
    return title_lower.str.contains(FOOD_ADDITIVE_TITLE_PHRASE) & title_lower.str.contains(
        REEVAL_TITLE_MARKER
    )


# Columnas de FLEX_SUM.ToxRefValues para el valor de ADI y su justificación.
# ADVERTENCIA: nombres confirmados de memoria de una sesión anterior por el
# usuario (no releídos carácter a carácter contra el xlsx real en esta
# sesión -- no había export en data/raw/). Verificar en cuanto el xlsx esté
# disponible: test_flex_sum_toxref_has_expected_adi_columns en
# tests/test_openfoodtox_joins.py falla con un mensaje claro si alguno de
# estos tres nombres no existe en la hoja real.
# No existe un campo estructural "CriticalEndpoint" separado confirmado --
# JustificationAndComments es texto libre y es el candidato más cercano
# disponible; no inventar un campo más específico sin verificarlo primero.
ADI_LOWER_VALUE_COLUMN = "HumanHealthHazardCharacteristics.AcceptableDailyIntake.Adi.lowerValue"
ADI_UNIT_COLUMN = "HumanHealthHazardCharacteristics.AcceptableDailyIntake.Adi.Unit"
ADI_JUSTIFICATION_COLUMN = (
    "HumanHealthHazardCharacteristics.AcceptableDailyIntake.JustificationAndComments"
)

# Discusión narrativa de END_SUM, ligada al dossier vía el mismo patrón que
# ADI (Document UUID -> DOSSIER_DOCS -> DOSSIER UUID), pero con
# DOCUMENT TYPE == 'ENDPOINT_SUMMARY' en vez de 'FLEXIBLE_SUMMARY'.
DISCUSSION_COLUMN = "Discussion.Discussion"
ENDPOINT_SUMMARY_DOCUMENT_TYPE = "ENDPOINT_SUMMARY"

# Heurístico de boilerplate validado sin excepciones encontradas en sesión
# (ver CLAUDE.md, "Hallazgos verificados"): por debajo de este umbral, el
# texto es siempre la frase de apertura del mandato sin contenido
# sustantivo. Por encima, NO hay garantía de que sea razonamiento real
# (zona gris sin señal limpia, ej. caso polisorbatos) -- el umbral solo
# atrapa los falsos negativos más claros, no certifica calidad.
DISCUSSION_BOILERPLATE_LENGTH_THRESHOLD = 280


def _parse_iso_date(value: object) -> date | None:
    """LiteratureReference.DateOfEvaluation llega de pandas como str
    'YYYY-MM-DD' (dtype str en las 11.610 filas no nulas verificadas, no
    datetime -- la celda de Excel está formateada como texto, no como
    fecha), no como datetime/Timestamp. Se parsea aquí para cumplir el
    tipo `date | None` de OpinionReference; el ordenamiento por
    MAX(fecha) en current_reference_value_opinion sigue haciéndose sobre
    el string original, que ordena igual lexicográficamente por ser ISO.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


@dataclass(frozen=True)
class OpinionReference:
    dossier_uuid: str
    date_of_evaluation: date | None
    title: str | None
    doc_type: str | None
    doi: str | None
    # Ligados al MISMO registro de FLEX_SUM.ToxRefValues que originó este
    # dossier concreto (no solo "algún" ADI de la sustancia) -- ver
    # current_reference_value_opinion. adi_justification es texto libre
    # (JustificationAndComments), no un campo estructurado de efecto
    # crítico; puede no mencionar explícitamente NOAEL/especie/estudio.
    adi_value: float | None = None
    adi_unit: str | None = None
    adi_justification: str | None = None
    # END_SUM.Discussion.Discussion ligado al mismo dossier vigente, no a
    # cualquier discusión de la sustancia. discussion_is_boilerplate=True
    # significa "detectado como sin contenido sustantivo" (ver
    # DISCUSSION_BOILERPLATE_LENGTH_THRESHOLD); False significa "no
    # detectado como boilerplate", NO "confirmado como razonamiento
    # científico real" -- hay una zona gris sin señal limpia, ver
    # CLAUDE.md.
    discussion_text: str | None = None
    discussion_is_boilerplate: bool = False


class OpenFoodToxStore:
    """Carga perezosa de las hojas relevantes del export xlsx y expone
    consultas deterministas (sin LLM) sobre ADI/TDI y vigencia de dictámenes.
    """

    def __init__(self, xlsx_path: str | Path):
        self.xlsx_path = Path(xlsx_path)
        if not self.xlsx_path.exists():
            raise FileNotFoundError(
                f"No se encuentra el export de OpenFoodTox en {self.xlsx_path}. "
                "Descárgalo desde el registro Zenodo de EFSA (record del dataset "
                "'OpenFoodTox 3.0') y colócalo en data/raw/."
            )

    # ------------------------------------------------------------------ #
    # Carga de hojas (cacheada por instancia)
    # ------------------------------------------------------------------ #

    @functools.cached_property
    def dossier(self) -> pd.DataFrame:
        return pd.read_excel(self.xlsx_path, sheet_name="DOSSIER", header=0)

    @functools.cached_property
    def dossier_docs(self) -> pd.DataFrame:
        return pd.read_excel(self.xlsx_path, sheet_name="DOSSIER_DOCS", header=0)

    @functools.cached_property
    def sub(self) -> pd.DataFrame:
        return pd.read_excel(self.xlsx_path, sheet_name="SUB", header=0)

    @functools.cached_property
    def flex_sum_toxref(self) -> pd.DataFrame:
        return pd.read_excel(self.xlsx_path, sheet_name="FLEX_SUM.ToxRefValues", header=0)

    @functools.cached_property
    def end_sum(self) -> pd.DataFrame:
        return pd.read_excel(self.xlsx_path, sheet_name="END_SUM", header=0)

    # ------------------------------------------------------------------ #
    # Filtro de corpus (aditivos en reevaluación bajo el Reglamento 257/2010)
    # ------------------------------------------------------------------ #

    def reevaluation_dossiers(self) -> pd.DataFrame:
        """Devuelve las filas de DOSSIER que corresponden a dictámenes de
        reevaluación de aditivos alimentarios.

        Domain.FoodDomain == FOOD_DOMAIN_VALUE + título con
        REEVAL_TITLE_MARKER, MÁS el rescate compartido
        _is_mistagged_food_additive_reevaluation() para dictámenes reales
        etiquetados con otro Domain.FoodDomain (verificado en sesión
        16-ago-2026: 18 dictámenes reales -- acesulfamo K E950, sacarina
        E954, eritritol E968, neotamo E961, plata E174, entre otros --
        quedaban excluidos sin este rescate; corpus pasa de 118 a 136).

        LIMITACIÓN CONOCIDA (documentada en docs/, no oculta): el filtro
        sigue siendo por patrón de texto en el título, no por un campo
        estructural fiable al 100% -- MISMA CLASE DE RIESGO que el
        rescate de dominio, no una garantía nueva. Contrastar contra las
        calls for data activas de EFSA antes de dar el corpus por
        cerrado.
        """
        df = self.dossier
        is_food_domain = df["Domain.FoodDomain"] == FOOD_DOMAIN_VALUE
        has_reeval_title = (
            df["LiteratureReference.EFSAOutputTitle"]
            .fillna("")
            .str.lower()
            .str.contains(REEVAL_TITLE_MARKER)
        )
        mask = (is_food_domain & has_reeval_title) | _is_mistagged_food_additive_reevaluation(df)
        return df[mask]

    def unique_reevaluation_opinions(self) -> pd.DataFrame:
        """Deduplica por título/DOI: una fila por dictamen, no por sustancia
        cubierta (un dictamen de grupo genera varias filas en DOSSIER,
        una por E-number). Verificado: 136 dictámenes únicos sobre food
        additives con 're-evaluation' en el título (o rescatados por
        _is_mistagged_food_additive_reevaluation, ver
        reevaluation_dossiers), a fecha del export usado en el diseño
        (Dec-2025 cutoff de OpenFoodTox 3.0). Cifra corregida en sesión
        16-ago-2026 -- era 118 antes de añadir el rescate de dominio mal
        etiquetado (ver CLAUDE.md, "Hallazgos verificados").
        """
        df = self.reevaluation_dossiers()
        return df.drop_duplicates(subset=["LiteratureReference.EFSAOutputTitle"])

    # ------------------------------------------------------------------ #
    # Nodo 3 — verificación de vigencia (determinista)
    # ------------------------------------------------------------------ #

    def substance_uuid_by_name(self, chemical_name: str) -> str | None:
        matches = self.sub[
            self.sub["ChemicalName"].str.lower() == chemical_name.lower()
        ]
        if matches.empty:
            return None
        return matches.iloc[0]["Document UUID"]

    @functools.cached_property
    def _discussion_links(self) -> pd.DataFrame:
        """Filas de END_SUM con Discussion.Discussion no nula, unidas a su
        DOSSIER UUID vía DOSSIER_DOCS (DOCUMENT TYPE == 'ENDPOINT_SUMMARY').
        Base para _discussion_boilerplate_texts y para
        current_reference_value_opinion.
        """
        links = self.dossier_docs[
            self.dossier_docs["DOCUMENT TYPE"] == ENDPOINT_SUMMARY_DOCUMENT_TYPE
        ]
        merged = links.merge(
            self.end_sum, left_on="DOCUMENT UUID", right_on="Document UUID"
        )
        return merged[merged[DISCUSSION_COLUMN].notna()]

    @functools.cached_property
    def _discussion_boilerplate_texts(self) -> frozenset[str]:
        """Textos de Discussion.Discussion idénticos en >=2 DOSSIER UUID
        distintos -- una discusión específica de una sustancia no debería
        salir palabra por palabra igual en el dictamen de otra sustancia
        distinta. Verificado en sesión: un único párrafo administrativo
        sobre el Reglamento 257/2010 comparte esta característica, en 9
        dossiers, con 518-703 caracteres -- más largo que
        DISCUSSION_BOILERPLATE_LENGTH_THRESHOLD, por eso hace falta esta
        detección aparte del umbral de longitud.
        """
        counts = self._discussion_links.groupby(DISCUSSION_COLUMN)["DOSSIER UUID"].nunique()
        return frozenset(counts[counts > 1].index)

    def _is_discussion_boilerplate(self, text: str) -> bool:
        return (
            len(text) < DISCUSSION_BOILERPLATE_LENGTH_THRESHOLD
            or text in self._discussion_boilerplate_texts
        )

    def _discussion_for_dossier(self, dossier_uuid: str) -> tuple[str | None, bool]:
        """Discussion.Discussion más larga entre las filas de END_SUM
        ligadas a este dossier concreto (un dossier puede enlazar a varias,
        p.ej. Carcinogenicity_EU_PPP + GeneticToxicity) -- más largo como
        proxy simple de "más informativo", no una garantía. Devuelve
        (texto, is_boilerplate); (None, False) si no hay ninguna.
        """
        rows = self._discussion_links[self._discussion_links["DOSSIER UUID"] == dossier_uuid]
        if rows.empty:
            return None, False
        texts = rows[DISCUSSION_COLUMN].astype(str)
        best_text = texts.loc[texts.map(len).idxmax()]
        return best_text, self._is_discussion_boilerplate(best_text)

    def _adi_row_for_toxref_uuids(self, toxref_uuids: set[str]) -> pd.Series | None:
        """De entre los registros de FLEX_SUM.ToxRefValues que enlazan al
        dossier ganador, elige el que tiene el valor de ADI relleno.

        Un dossier puede originar varios registros en esta hoja (p.ej. ADI
        y TDI como filas separadas, o valores para distintas poblaciones) --
        se prioriza el que tiene ADI_LOWER_VALUE_COLUMN no nulo en vez de
        asumir que siempre hay exactamente uno.
        """
        rows = self.flex_sum_toxref[
            self.flex_sum_toxref["Document UUID"].isin(toxref_uuids)
        ]
        if rows.empty:
            return None
        with_adi = rows[rows[ADI_LOWER_VALUE_COLUMN].notna()]
        return with_adi.iloc[0] if not with_adi.empty else rows.iloc[0]

    def current_reference_value_opinion(
        self, substance_uuid: str
    ) -> OpinionReference | None:
        """Heurístico estructural verificado con aspartamo (E 951).

        1. Toma todos los registros de ADI/TDI (FLEX_SUM.ToxRefValues) cuyo
           Parent UUID es la sustancia dada.
        2. Traza cada uno, vía DOSSIER_DOCS, al DOSSIER (dictamen) que lo
           originó.
        3. Filtra por Type == 'EFSA opinion' (excluye statements) y por
           dominio (Domain.FoodDomain == 'food additives' O título
           reconocible como reevaluación de aditivo mal etiquetada, ver
           FOOD_ADDITIVE_TITLE_PHRASE) -- descarta candidatos de otro
           programa regulatorio (pienso animal, aromas...) que compitan
           por MAX(fecha) con el dictamen real de aditivo alimentario.
        4. Devuelve el de fecha de evaluación más reciente, con el valor de
           ADI (lowerValue + Unit), la justificación y la discusión
           narrativa (END_SUM.Discussion.Discussion, con heurístico de
           boilerplate) ligados a ESE registro/dossier concreto -- no a
           cualquier ADI o discusión de la sustancia, sino a los que
           corresponden específicamente al dossier devuelto.

        Si el resultado es ambiguo (varias 'EFSA opinion' de fecha muy
        próxima sin que el título aclare cuál sustituye a cuál), este método
        devuelve la más reciente igualmente pero el nodo LangGraph que lo
        envuelve debe marcarlo para revisión narrativa (fallback a LLM sobre
        el texto del PDF) en vez de confiar ciegamente en el dato.
        """
        toxref_rows = self.flex_sum_toxref[
            self.flex_sum_toxref["Parent UUID"] == substance_uuid
        ]
        if toxref_rows.empty:
            return None

        toxref_uuids = set(toxref_rows["Document UUID"])

        linked = self.dossier_docs[
            self.dossier_docs["DOCUMENT UUID"].isin(toxref_uuids)
        ]
        dossier_uuids = set(linked["DOSSIER UUID"])

        candidates = self.dossier[self.dossier["Document UUID"].isin(dossier_uuids)]
        candidates = candidates[
            candidates["LiteratureReference.Type"].isin(VALID_OPINION_TYPES)
        ]

        # Descarta candidatos de OTRO programa regulatorio (pienso animal
        # FEEDAP, aromas/flavourings, contaminantes de procesado...) que
        # compitan por MAX(fecha) con el dictamen real de aditivo
        # alimentario para esta misma sustancia -- ver el comentario largo
        # junto a FOOD_ADDITIVE_TITLE_PHRASE arriba. Verificado con
        # aspartamo, propil galato (E 310) y plata (E 174), ver tests de
        # regresión. A propósito NO exige REEVAL_TITLE_MARKER en la rama
        # de dominio correcto (a diferencia de reevaluation_dossiers) --
        # verificado con dióxido de titanio (E 171) que el dictamen
        # realmente vigente puede no usar esa palabra.
        is_food_domain = candidates["Domain.FoodDomain"] == FOOD_DOMAIN_VALUE
        candidates = candidates[
            is_food_domain | _is_mistagged_food_additive_reevaluation(candidates)
        ]

        if candidates.empty:
            return None

        candidates = candidates.sort_values(
            "LiteratureReference.DateOfEvaluation", ascending=False
        )
        best = candidates.iloc[0]
        best_dossier_uuid = best["Document UUID"]

        # Registros de FLEX_SUM.ToxRefValues que enlazan específicamente al
        # dossier ganador (no a cualquier dossier de la sustancia).
        toxref_uuids_for_best = set(
            linked[linked["DOSSIER UUID"] == best_dossier_uuid]["DOCUMENT UUID"]
        )
        adi_row = (
            self._adi_row_for_toxref_uuids(toxref_uuids_for_best)
            if toxref_uuids_for_best
            else None
        )

        adi_value = None
        adi_unit = None
        adi_justification = None
        if adi_row is not None:
            if pd.notna(adi_row[ADI_LOWER_VALUE_COLUMN]):
                adi_value = float(adi_row[ADI_LOWER_VALUE_COLUMN])
            if pd.notna(adi_row[ADI_UNIT_COLUMN]):
                adi_unit = adi_row[ADI_UNIT_COLUMN]
            if pd.notna(adi_row[ADI_JUSTIFICATION_COLUMN]):
                adi_justification = adi_row[ADI_JUSTIFICATION_COLUMN]

        discussion_text, discussion_is_boilerplate = self._discussion_for_dossier(
            best_dossier_uuid
        )

        return OpinionReference(
            dossier_uuid=best["Document UUID"],
            date_of_evaluation=_parse_iso_date(best["LiteratureReference.DateOfEvaluation"]),
            title=best["LiteratureReference.EFSAOutputTitle"],
            doc_type=best["LiteratureReference.Type"],
            doi=best["LiteratureReference.LinkToPersistentIdentifier"],
            adi_value=adi_value,
            adi_unit=adi_unit,
            adi_justification=adi_justification,
            discussion_text=discussion_text,
            discussion_is_boilerplate=discussion_is_boilerplate,
        )
