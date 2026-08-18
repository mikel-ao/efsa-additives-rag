"""
Indexado en Chroma a partir de data/processed/chunks.jsonl (una línea
por combinación chunk x sustancia resuelta, ver ingestion/pdf_chunking.py
y scripts/build_chunk_index.py).

Esquema de metadatos y decisión de excluir `e_number` documentados en
CLAUDE.md, "Hallazgos verificados" -- ESQUEMA FINAL. No lo reabras sin
una fuente fiable de E-number a nivel de sustancia (SUB no la tiene,
confirmado).
"""

from __future__ import annotations

from dataclasses import dataclass

# Campos que SIEMPRE están presentes en las filas reales de
# chunks.jsonl (verificado: 0 valores None en los 67.827 para doi y
# page_number) -- se escriben sin guardado especial, pero el código no
# asume que vayan a seguir siéndolo si el JSONL se regenera con datos
# distintos.
_ALWAYS_STR_FIELDS = ("substance_uuid", "chemical_name", "dossier_uuid", "dossier_title", "chunk_group_id")


def chroma_id(row: dict) -> str:
    """Id único por entrada de Chroma -- una fila de chunks.jsonl es ya
    (chunk, sustancia), pero `chunk_group_id` por sí solo se repite N
    veces (una por sustancia del chunk) así que hace falta combinarlo
    con `substance_uuid` para unicidad."""
    return f"{row['chunk_group_id']}::{row['substance_uuid']}"


def to_chroma_metadata(row: dict, is_group_dossier: bool) -> dict:
    """Convierte una fila de chunks.jsonl al dict de metadatos que
    Chroma acepta -- solo str/int/float/bool, sin `None` (Chroma lanza
    TypeError con None, verificado directamente en sesión 18-ago-2026,
    no asumido). Campos con valor None se OMITEN de la clave, no se
    escriben como None ni como sentinela -- confirmado que Chroma
    admite metadatos con distintas claves entre documentos de la misma
    colección.

    Deliberadamente NO incluye `e_number` -- ver CLAUDE.md, "Hallazgos
    verificados", ESQUEMA FINAL, para el motivo (SUB no tiene ese
    campo; el título del dossier no mapea 1:1 a cada substance_uuid en
    casos multi-sustancia)."""
    metadata: dict[str, str | int | bool] = {}
    for field in _ALWAYS_STR_FIELDS:
        value = row[field]
        if value is not None:
            metadata[field] = value

    metadata["substance_resolution_tier"] = int(row["substance_resolution_tier"])
    metadata["is_group_dossier"] = bool(is_group_dossier)

    if row["doi"] is not None:
        metadata["doi"] = row["doi"]
    if row["section_heading"] is not None:
        metadata["section_heading"] = row["section_heading"]
    if row["page_number"] is not None:
        metadata["page_number"] = int(row["page_number"])
    if row["pdf_filename"] is not None:
        metadata["pdf_filename"] = row["pdf_filename"]

    return metadata


def compute_is_group_dossier(rows: list[dict]) -> dict[str, bool]:
    """dossier_uuid -> True si el dossier tiene más de una sustancia
    resuelta DISTINTA entre las filas dadas (nota: si `rows` es un
    subconjunto del corpus completo, ej. un lote de prueba, este mapa
    solo refleja lo que se ve en ese subconjunto -- pasar el corpus
    completo de chunks.jsonl si se quiere el valor real por dossier)."""
    substances_by_dossier: dict[str, set[str]] = {}
    for row in rows:
        substances_by_dossier.setdefault(row["dossier_uuid"], set()).add(row["substance_uuid"])
    return {uuid: len(subs) > 1 for uuid, subs in substances_by_dossier.items()}


@dataclass(frozen=True)
class ChromaEntry:
    id: str
    text: str
    metadata: dict


def rows_to_chroma_entries(rows: list[dict]) -> list[ChromaEntry]:
    is_group = compute_is_group_dossier(rows)
    return [
        ChromaEntry(
            id=chroma_id(row),
            text=row["text"],
            metadata=to_chroma_metadata(row, is_group_dossier=is_group[row["dossier_uuid"]]),
        )
        for row in rows
    ]
