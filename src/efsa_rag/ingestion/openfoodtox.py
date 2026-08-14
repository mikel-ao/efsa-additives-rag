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

# Tipos de documento que SÍ cuentan como dictamen formal para el heurístico
# de vigencia. Los 'EFSA statement' se excluyen del MAX(fecha) porque pueden
# postdatar una reevaluación sin sustituirla (caso verificado: statement de
# aspartamo en 2011 es posterior al opinion de 2009 pero no lo reemplaza).
VALID_OPINION_TYPES = {"EFSA opinion"}


@dataclass(frozen=True)
class OpinionReference:
    dossier_uuid: str
    date_of_evaluation: date | None
    title: str | None
    doc_type: str | None
    doi: str | None


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
        return pd.read_excel(self.xlsx_path, sheet_name="DOSSIER", header=1)

    @functools.cached_property
    def dossier_docs(self) -> pd.DataFrame:
        return pd.read_excel(self.xlsx_path, sheet_name="DOSSIER_DOCS", header=1)

    @functools.cached_property
    def sub(self) -> pd.DataFrame:
        return pd.read_excel(self.xlsx_path, sheet_name="SUB", header=1)

    @functools.cached_property
    def flex_sum_toxref(self) -> pd.DataFrame:
        return pd.read_excel(self.xlsx_path, sheet_name="FLEX_SUM.ToxRefValues", header=1)

    # ------------------------------------------------------------------ #
    # Filtro de corpus (aditivos en reevaluación bajo el Reglamento 257/2010)
    # ------------------------------------------------------------------ #

    def reevaluation_dossiers(self) -> pd.DataFrame:
        """Devuelve las filas de DOSSIER que corresponden a dictámenes de
        reevaluación de aditivos alimentarios.

        LIMITACIÓN CONOCIDA (documentada en docs/, no oculta): el filtro es
        por dominio + patrón de texto en el título, no por un campo
        estructural fiable al 100%. Contrastar contra las calls for data
        activas de EFSA antes de dar el corpus por cerrado.
        """
        df = self.dossier
        mask = (df["Domain.FoodDomain"] == FOOD_DOMAIN_VALUE) & (
            df["LiteratureReference.EFSAOutputTitle"]
            .fillna("")
            .str.lower()
            .str.contains(REEVAL_TITLE_MARKER)
        )
        return df[mask]

    def unique_reevaluation_opinions(self) -> pd.DataFrame:
        """Deduplica por título/DOI: una fila por dictamen, no por sustancia
        cubierta (un dictamen de grupo genera varias filas en DOSSIER,
        una por E-number). Verificado: 118 dictámenes únicos sobre food
        additives con 'ITre-evaluation' en el título, a fecha del export
        usado en el diseño (Dec-2025 cutoff de OpenFoodTox 3.0).
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

    def current_reference_value_opinion(
        self, substance_uuid: str
    ) -> OpinionReference | None:
        """Heurístico estructural verificado con aspartamo (E 951).

        1. Toma todos los registros de ADI/TDI (FLEX_SUM.ToxRefValues) cuyo
           Parent UUID es la sustancia dada.
        2. Traza cada uno, vía DOSSIER_DOCS, al DOSSIER (dictamen) que lo
           originó.
        3. Filtra por Type == 'EFSA opinion' (excluye statements).
        4. Devuelve el de fecha de evaluación más reciente.

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
        if candidates.empty:
            return None

        candidates = candidates.sort_values(
            "LiteratureReference.DateOfEvaluation", ascending=False
        )
        best = candidates.iloc[0]
        return OpinionReference(
            dossier_uuid=best["Document UUID"],
            date_of_evaluation=best["LiteratureReference.DateOfEvaluation"],
            title=best["LiteratureReference.EFSAOutputTitle"],
            doc_type=best["LiteratureReference.Type"],
            doi=best["LiteratureReference.LinkToPersistentIdentifier"],
        )
