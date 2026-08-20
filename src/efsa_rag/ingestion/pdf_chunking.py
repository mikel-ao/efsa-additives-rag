"""
Pipeline de chunking de los PDFs de reevaluación (pendiente #5 de
CLAUDE.md, "Estado del código") -- extracción de texto narrativo,
detección de encabezados de sección vía la señal de fuente tipográfica,
exclusión de tablas, troceo con RecursiveCharacterTextSplitter, y
resolución de sustancia por dossier en 3 niveles (ver CLAUDE.md,
"Hallazgos verificados", "Contrato Nodo 2 -> Nodo 4").

Decisiones de diseño (ver CLAUDE.md para el razonamiento completo):
- Loader: PyMuPDF directo (no el wrapper `PyMuPDFLoader` de
  langchain_community) -- necesitamos acceso a bbox/fuente por span para
  la detección de encabezados y de tablas, que el wrapper no expone.
  Misma fidelidad de texto que ya validó la comparación
  PyPDFLoader-vs-PyMuPDFLoader (0 palabras rotas) porque usamos el mismo
  algoritmo de extracción subyacente (`page.get_text()` en modo texto
  plano/"blocks", no el modo "dict"/"rawdict" -- ver más abajo por qué).
- Tablas: Opción A (excluir del texto narrativo, no reconstruir).
- Splitter: RecursiveCharacterTextSplitter plano; `section_heading`
  extraído vía fuente tipográfica (bold vs regular), no vía regex de
  numeración sobre texto plano (demasiado ruidoso, ver CLAUDE.md).

Hallazgo no documentado previamente: para varias de las
fuentes bold incrustadas de estos PDFs (ej. "AdvTTec80583d.B"), el modo
"dict"/"rawdict" de PyMuPDF concatena el texto de una línea SIN espacios
entre palabras (el glifo de espacio no tiene avance en la fuente
incrustada) -- "Chemistry of phosphates" sale como "Chemistryofphosphates"
si se concatena texto de spans en modo "dict". El modo "blocks" (misma
extracción por líneas que el modo texto plano) NO tiene este problema
-- usa el algoritmo de layout de MuPDF, que reconstruye espacios
correctamente incluso con esta fuente. Por eso el texto de cada bloque
sale de `page.get_text("blocks", textpage=tp)`, y el modo "dict" (sobre
el MISMO textpage, para garantizar la misma segmentación en bloques --
verificado que `block_no` coincide 1:1 entre ambos modos sobre el mismo
textpage) se usa SOLO para decidir si un bloque es bold, nunca para su
texto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

from efsa_rag.graph.nodes import RetrievedChunk
from efsa_rag.ingestion.openfoodtox import DossierSubstance, OpenFoodToxStore
from efsa_rag.ingestion.pdf_naming import clean_doi, destination_filename, e_numbers_from_title

# ------------------------------------------------------------------ #
# Detección de encabezados vía fuente tipográfica
# ------------------------------------------------------------------ #

# Fuentes bold incrustadas verificadas en los PDFs de referencia:
# "TimesNewRomanPS-BoldMT" (statement
# corto) y variantes con sufijo ".B"/".B+..." (AdvTT..., Scientific
# Opinion largos) -- NINGUNA de las dos usa el bit "bold" del bitfield
# `flags` de PyMuPDF (verificado: flags=4 para ambas, bit 16 nunca
# activo en estas fuentes incrustadas/subsetadas) -- el nombre de fuente
# es la señal fiable, no `flags`.
_BOLD_FONT_RE = re.compile(r"bold|\.b(?:\+|$)", re.IGNORECASE)

# Bloques cuyo texto (normalizado, ver _normalize_for_dedup) se repite en
# >= este número de páginas distintas del MISMO PDF se tratan como
# cabecera/pie de página recurrente (título del dictamen repetido en cada
# página, numeración de página, banner de descarga de Wiley) -- no como
# encabezado de sección ni como texto narrativo. Mismo principio que
# `_discussion_boilerplate_texts` en openfoodtox.py (duplicado exacto
# entre >=2 instancias == administrativo, no contenido real), aplicado
# aquí a bloques de página en vez de a discusiones de dossier.
REPEATED_BLOCK_MIN_PAGES = 3

# Título de tabla ("Table 5a: ...", "Table 12." ...) -- verificado en
# CLAUDE.md que este patrón, combinado con find_tables(), captura tanto
# la leyenda como el cuerpo tabular. Ancla al inicio del bloque porque un
# título de tabla siempre abre su propio bloque de texto (verificado en
# los 3 PDFs de referencia).
_TABLE_CAPTION_RE = re.compile(r"^\s*table\s*\d+[a-z]?\s*[:.]", re.IGNORECASE)


# U+00AD (soft hyphen) -- hallazgo de una validación en lote sobre el
# corpus completo: los PDF EFSA/Wiley más recientes (2024-2025 en la
# muestra probada, ausente en TODOS los
# anteriores a 2024 comprobados) incrustan el carácter de guion suave
# literalmente en el texto extraído, no solo como punto de corte de
# línea invisible -- verificado sobre el PDF de acesulfame K (2025):
# 474 de 1170 bloques lo contienen, 1168 apariciones en total (esencialmente
# todos los bloques del documento). Sin limpiarlo, "Re-evaluation" sale
# como "Re-\xadevaluation" en el texto de cada chunk -- un carácter
# invisible pero real que degradaría embeddings/tokenización sin que se
# note a simple vista. Nunca es información real (es una marca de
# formato, no texto visible), seguro quitarlo siempre.
_SOFT_HYPHEN = "\xad"  # escapado a propósito -- es invisible si se pega literal


def _normalize_for_dedup(text: str) -> str:
    """Quita dígitos antes de comparar -- el pie de página
    ("EFSA Journal 2019;17(6):5674", "www.efsa.europa.eu/efsajournal\\nN\\n...")
    es idéntico entre páginas salvo el número de página; el banner de
    descarga de Wiley ("Downloaded from ... on [17/08/2026]...") resultó
    ser byte-a-byte idéntico en todas las páginas probadas, así que
    normalizar dígitos no cambia ese caso pero sí captura el del pie de
    página con número de página variable."""
    return re.sub(r"\d+", "", text).strip()


def _block_is_bold(dict_block: dict) -> bool:
    spans = [s for line in dict_block.get("lines", []) for s in line["spans"] if s["text"].strip()]
    if not spans:
        return False
    return all(_BOLD_FONT_RE.search(s["font"]) for s in spans)


@dataclass(frozen=True)
class _RawBlock:
    page_number: int  # 1-indexado, para que coincida con lo que ve un lector humano del PDF
    text: str
    is_bold: bool


@dataclass(frozen=True)
class NarrativeSection:
    """Texto narrativo agrupado bajo un mismo encabezado de sección --
    unidad de entrada al splitter. `heading` es `None` para el texto
    anterior al primer encabezado detectado (portada/cabecera del
    dictamen)."""

    heading: str | None
    page_number: int  # página del primer bloque de esta sección
    text: str


def _table_block_indices(page: "pymupdf.Page", blocks: list) -> set[int]:
    """`block_no` de los bloques de esta página que forman parte de una
    tabla -- vía page.find_tables() (bboxes estructurales de PyMuPDF,
    misma fuente de verdad ya usada para medir prevalencia de tablas en
    CLAUDE.md) MÁS cualquier bloque cuyo texto sea una leyenda "Table N"
    que find_tables() no incluya en su bbox (verificado en el PDF de
    fosfatos: la leyenda "Table 5a: Summary..." es un bloque de texto
    aparte, fuera de los 4 bbox que devuelve find_tables() para esa
    tabla).

    Solo bbox, no reconstrucción de celdas -- Opción A (CLAUDE.md,
    "Hallazgos verificados") descarta el contenido de la tabla, no
    necesita reconstruirlo."""
    try:
        table_bboxes = [t.bbox for t in page.find_tables().tables]
    except Exception:
        table_bboxes = []

    excluded: set[int] = set()
    for x0, y0, x1, y1, text, block_no, block_type in blocks:
        if block_type != 0:
            continue
        if _TABLE_CAPTION_RE.match(text):
            excluded.add(block_no)
            continue
        block_cx, block_cy = (x0 + x1) / 2, (y0 + y1) / 2
        for tx0, ty0, tx1, ty1 in table_bboxes:
            if tx0 <= block_cx <= tx1 and ty0 <= block_cy <= ty1:
                excluded.add(block_no)
                break
    return excluded


def extract_raw_blocks(pdf_path: str | Path) -> list[_RawBlock]:
    """Extrae, en orden de lectura, los bloques de texto narrativo del
    PDF -- ya sin tablas ni cabeceras/pies de página recurrentes.

    Dos pasadas: (1) recoge todos los bloques candidatos con su bbox/
    negrita/texto de tabla; (2) sobre el documento COMPLETO, cuenta
    repeticiones normalizadas para identificar cabeceras/pies de página
    recurrentes (necesita ver todas las páginas antes de decidir, no se
    puede hacer en una sola pasada por página)."""
    doc = pymupdf.open(pdf_path)
    try:
        candidates: list[tuple[int, str, bool]] = []  # (page_number, text, is_bold)

        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            tp = page.get_textpage()
            dict_data = page.get_text("dict", textpage=tp)
            blocks = page.get_text("blocks", textpage=tp)

            bold_by_block_no = {
                i: _block_is_bold(b)
                for i, b in enumerate(dict_data["blocks"])
                if b.get("type") == 0
            }
            table_block_nos = _table_block_indices(page, blocks)

            for x0, y0, x1, y1, text, block_no, block_type in blocks:
                if block_type != 0 or block_no in table_block_nos:
                    continue
                text = text.replace(_SOFT_HYPHEN, "").strip()
                if not text:
                    continue
                candidates.append((page_number, text, bold_by_block_no.get(block_no, False)))

        # Frecuencia de texto normalizado (dígitos fuera) a través de
        # páginas DISTINTAS -- ver REPEATED_BLOCK_MIN_PAGES.
        pages_by_normalized: dict[str, set[int]] = {}
        for page_number, text, _ in candidates:
            pages_by_normalized.setdefault(_normalize_for_dedup(text), set()).add(page_number)

        blocks_out: list[_RawBlock] = []
        for page_number, text, is_bold in candidates:
            normalized = _normalize_for_dedup(text)
            if len(pages_by_normalized[normalized]) >= REPEATED_BLOCK_MIN_PAGES:
                continue  # cabecera/pie de página recurrente, no contenido real
            blocks_out.append(_RawBlock(page_number=page_number, text=text, is_bold=is_bold))
        return blocks_out
    finally:
        doc.close()


def group_into_sections(blocks: list[_RawBlock]) -> list[NarrativeSection]:
    """Agrupa bloques narrativos consecutivos bajo el último encabezado
    (bloque bold) visto -- un encabezado nuevo cierra la sección anterior
    y abre una nueva, independientemente de si cruza páginas. El texto
    antes del primer encabezado (portada/metadatos de citación) se
    agrupa con heading=None."""
    sections: list[NarrativeSection] = []
    current_heading: str | None = None
    current_page: int | None = None
    current_parts: list[str] = []

    def _flush() -> None:
        if current_parts:
            sections.append(
                NarrativeSection(
                    heading=current_heading,
                    page_number=current_page if current_page is not None else 1,
                    text="\n\n".join(current_parts),
                )
            )

    for block in blocks:
        if block.is_bold:
            _flush()
            current_heading = block.text.replace("\n", " ").strip()
            current_page = block.page_number
            current_parts = []
            continue
        if current_page is None:
            current_page = block.page_number
        current_parts.append(block.text)

    _flush()
    return sections


# ------------------------------------------------------------------ #
# Troceo
# ------------------------------------------------------------------ #

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150

# Umbral mínimo de longitud de chunk -- descarta fragmentos casi vacíos
# (un encabezado seguido inmediatamente de otro encabezado, o un resto
# de sección de una sola frase corta tras el troceo). Verificado sobre
# los 2.559 chunks generados en una validación anterior (6
# PDF): 25 (1,0%) caían por debajo de 50 caracteres, ej. "1 " o
# fragmentos de una palabra sueltos entre dos secciones -- sin valor de
# retrieval real, solo ruido en el índice. 50 caracteres elegido porque
# ninguna frase con contenido narrativo mínimamente útil observada en
# esos 2.559 chunks cae por debajo de eso; no es un umbral ajustado
# contra un corpus más amplio todavía.
MIN_CHUNK_LENGTH = 50


@dataclass(frozen=True)
class TextChunk:
    text: str
    section_heading: str | None
    page_number: int


def split_sections(
    sections: list[NarrativeSection],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    min_chunk_length: int = MIN_CHUNK_LENGTH,
) -> list[TextChunk]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[TextChunk] = []
    for section in sections:
        for piece in splitter.split_text(section.text):
            if len(piece.strip()) < min_chunk_length:
                continue
            chunks.append(
                TextChunk(text=piece, section_heading=section.heading, page_number=section.page_number)
            )
    return chunks


# ------------------------------------------------------------------ #
# Resolución de sustancia por dossier -- diseño de 3 niveles, ver
# CLAUDE.md "Hallazgos verificados".
# ------------------------------------------------------------------ #

# Nombres de sustancia demasiado cortos dan falsos positivos como
# substring de título (ej. "tin", "acid" aparecen dentro de palabras no
# relacionadas) -- mínimo elegido para evitar eso sin excluir nombres
# reales cortos ("Silver" tiene 6, cubierto).
_MIN_TIER3_NAME_LENGTH = 5


def _guess_substance_by_title(store: OpenFoodToxStore, title: str) -> DossierSubstance | None:
    """Nivel 3 (peor confianza, ver CLAUDE.md): busca, entre TODOS los
    nombres de sustancia de la hoja SUB, el que aparece como palabra
    completa dentro del título -- si hay varios, el más largo (más
    específico). Verificado que resuelve los 2 casos reales conocidos
    (Sucralose, Shellac); NO probado contra los demás títulos del
    corpus todavía -- heurístico de último recurso, exactamente por eso
    es tier 3."""
    title_lower = title.lower()
    sub = store.sub[store.sub["ChemicalName"].notna()]
    best: tuple[int, str, str] | None = None  # (len, uuid, name)
    for _, row in sub.iterrows():
        name = row["ChemicalName"]
        if len(name) < _MIN_TIER3_NAME_LENGTH:
            continue
        pattern = r"\b" + re.escape(name.lower()) + r"\b"
        if re.search(pattern, title_lower):
            if best is None or len(name) > best[0]:
                best = (len(name), row["Document UUID"], name)
    if best is None:
        return None
    return DossierSubstance(substance_uuid=best[1], chemical_name=best[2])


@dataclass(frozen=True)
class ResolvedSubstance:
    substance: DossierSubstance
    tier: int


def resolve_dossier_substances(
    store: OpenFoodToxStore, dossier_uuid: str, title: str, dossier_row_df
) -> list[ResolvedSubstance]:
    """Nivel 1 (con ADI) -> Nivel 2 (mismo enlace, sin ADI) -> Nivel 3
    (nombre en el título) -- se detiene en el primer nivel no vacío, tal
    como especifica el diseño en CLAUDE.md. `dossier_row_df` es la fila
    de `current_reevaluation_corpus()` para ESTE dossier, ya acotada por
    el llamador (evita recalcular `substances_per_dossier()` sobre el
    corpus completo -- ~27 s medidos en una prueba anterior -- para
    procesar un único PDF)."""
    tier1 = store.substances_per_dossier(corpus=dossier_row_df, require_adi=True).get(
        dossier_uuid, []
    )
    if tier1:
        return [ResolvedSubstance(s, 1) for s in tier1]

    tier2 = store.substances_per_dossier(corpus=dossier_row_df, require_adi=False).get(
        dossier_uuid, []
    )
    if tier2:
        return [ResolvedSubstance(s, 2) for s in tier2]

    guess = _guess_substance_by_title(store, title)
    if guess is not None:
        return [ResolvedSubstance(guess, 3)]

    return []


# ------------------------------------------------------------------ #
# Mapeo PDF en disco -> fila del corpus
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class DossierPdf:
    dossier_uuid: str
    title: str
    doi: str | None
    pdf_path: Path


def map_corpus_to_pdfs(store: OpenFoodToxStore, pdf_dir: str | Path) -> list[DossierPdf]:
    """Empareja cada fila de `current_reevaluation_corpus()` con su PDF
    en `pdf_dir`, usando el mismo esquema de nombre de archivo que generó
    `scripts/generate_pdf_checklist.py` (ingestion.pdf_naming).

    El corpus tiene 162 filas pero 161 archivos reales -- ver CLAUDE.md,
    "Hallazgos verificados": "Re-evaluation of saccharin..." aparece dos
    veces con el MISMO DOI (variante de título con errata de espacio), y
    por tanto con el MISMO nombre de archivo esperado. Se deduplica por
    nombre de archivo (se queda con la primera fila vista, orden estable
    por `current_reevaluation_corpus()`) -- mismo comportamiento que ya
    tiene el checklist, no un caso nuevo.

    Filas cuyo archivo esperado no existe en `pdf_dir` se omiten
    silenciosamente en la lista devuelta pero se puede diagnosticar
    comparando `len(resultado)` contra `len(corpus)` -- no debería pasar
    con los 161 PDFs ya descargados, pero no se asume."""
    pdf_dir = Path(pdf_dir)
    corpus = store.current_reevaluation_corpus()

    seen_filenames: set[str] = set()
    result: list[DossierPdf] = []
    for i, row in corpus.iterrows():
        title = row["LiteratureReference.EFSAOutputTitle"]
        doi = clean_doi(row["LiteratureReference.LinkToPersistentIdentifier"])
        e_numbers = e_numbers_from_title(title)
        filename = destination_filename(doi, e_numbers, fallback_index=i)

        if filename in seen_filenames:
            continue
        pdf_path = pdf_dir / filename
        if not pdf_path.exists():
            continue
        seen_filenames.add(filename)
        result.append(
            DossierPdf(dossier_uuid=row["Document UUID"], title=title, doi=doi, pdf_path=pdf_path)
        )
    return result


# ------------------------------------------------------------------ #
# Orquestación por PDF
# ------------------------------------------------------------------ #


@dataclass
class DossierChunkingResult:
    dossier: DossierPdf
    chunks: list[TextChunk]
    resolved_substances: list[ResolvedSubstance]
    retrieved_chunks: list[RetrievedChunk]


def chunk_dossier(
    store: OpenFoodToxStore,
    dossier: DossierPdf,
    dossier_row_df,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> DossierChunkingResult:
    blocks = extract_raw_blocks(dossier.pdf_path)
    sections = group_into_sections(blocks)
    chunks = split_sections(sections, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    resolved = resolve_dossier_substances(store, dossier.dossier_uuid, dossier.title, dossier_row_df)

    # Esquema de metadatos de CLAUDE.md: un chunk que cubre N sustancias
    # se indexa N veces, una entrada por sustancia -- aquí, un
    # RetrievedChunk por combinación (chunk, sustancia resuelta). Si no
    # se resolvió ninguna sustancia (el caso 1/162 genuinamente sin
    # enlace estructural ni nombre reconocible en el título, ver
    # CLAUDE.md), no se generan RetrievedChunk para este dossier -- el
    # contrato actual de RetrievedChunk exige substance_uuid no nulo, no
    # contempla ese caso. Los chunks de texto SÍ existen (`chunks`,
    # devueltos igualmente), solo no hay forma de envolverlos en
    # RetrievedChunk todavía -- el script de indexado reporta este caso
    # en su resumen de ejecución.
    retrieved_chunks: list[RetrievedChunk] = []
    for chunk in chunks:
        for r in resolved:
            retrieved_chunks.append(
                RetrievedChunk(
                    text=chunk.text,
                    substance_uuid=r.substance.substance_uuid,
                    chemical_name=r.substance.chemical_name,
                    dossier_uuid=dossier.dossier_uuid,
                    dossier_title=dossier.title,
                    substance_resolution_tier=r.tier,
                    doi=dossier.doi,
                    section_heading=chunk.section_heading,
                    page_number=chunk.page_number,
                )
            )

    return DossierChunkingResult(
        dossier=dossier, chunks=chunks, resolved_substances=resolved, retrieved_chunks=retrieved_chunks
    )
