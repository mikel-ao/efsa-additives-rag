"""
Normalización de DOI y nombre de archivo destino para los PDFs del corpus
de reevaluación -- extraído de scripts/generate_pdf_checklist.py (sesión
17-ago-2026) para que el chunker (ingestion/pdf_chunking.py) pueda mapear
cada fila de OpenFoodToxStore.current_reevaluation_corpus() al archivo
real en data/raw/pdfs/ sin reimplementar esta lógica por segunda vez.
scripts/generate_pdf_checklist.py sigue siendo la fuente que generó los
nombres de archivo ya usados en disco -- este módulo solo la hace
reutilizable en vez de vivir únicamente en el script.
"""

from __future__ import annotations

import re

# LiteratureReference.LinkToPersistentIdentifier no es consistente en el
# xlsx real -- ver CLAUDE.md, "Hallazgos verificados": 147 filas con
# prefijo "doi:", 15 con "doi. org/" (con espacio). Un DOI siempre empieza
# por "10." (especificación DOI) -- se usa eso como ancla en vez de una
# lista de prefijos conocidos.
DOI_PATTERN = re.compile(r"10\.\d{4,}/.+")

E_NUMBER_PATTERN = re.compile(r"\bE\s?\d{3,4}[a-z]{0,2}(?:\([iv]+\))?\b", re.IGNORECASE)


def clean_doi(raw_doi: str | None) -> str | None:
    """Normaliza el prefijo del DOI -- ver DOI_PATTERN arriba."""
    if raw_doi is None:
        return None
    match = DOI_PATTERN.search(raw_doi)
    return match.group(0).strip() if match else raw_doi.strip()


def e_numbers_from_title(title: str) -> list[str]:
    """E-numbers citados en el título, en orden de aparición, sin
    duplicados -- heurístico de texto, no un campo estructural."""
    seen: list[str] = []
    for match in E_NUMBER_PATTERN.finditer(title):
        normalized = match.group(0).upper().replace(" ", "")
        if normalized not in seen:
            seen.append(normalized)
    return seen


def destination_filename(doi: str | None, e_numbers: list[str], fallback_index: int = 0) -> str:
    """Nombre de archivo determinista: prefijo de E-numbers + sufijo del
    DOI -- mismo esquema ya usado para nombrar los 161 PDFs reales en
    data/raw/pdfs/ (ver scripts/generate_pdf_checklist.py)."""
    e_prefix = "-".join(e_numbers) if e_numbers else "sinE"
    if doi:
        doi_suffix = doi.replace("/", "_").replace(":", "_")
        return f"{e_prefix}_{doi_suffix}.pdf"
    return f"{e_prefix}_sinDOI_{fallback_index:03d}.pdf"
