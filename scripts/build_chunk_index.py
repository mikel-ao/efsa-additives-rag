"""
Pipeline de chunking de los PDFs de reevaluación (pendiente #5 de
CLAUDE.md) -- extrae texto narrativo, detecta encabezados de sección,
excluye tablas, trocea y resuelve sustancia(s) por dossier en 3 niveles.
Ver src/efsa_rag/ingestion/pdf_chunking.py para la implementación.

NO toca embeddings ni Chroma -- solo extracción y chunking. Ese paso
llega después, por separado.

Incluye límite explícito + --dry-run por lote: esto no llama al LLM,
pero procesa hasta 161 PDFs con parsing de PDF (coste de CPU/tiempo
real, no de presupuesto de API), así que evita lanzar por error un
procesado completo sin querer.

Uso:
    python scripts/build_chunk_index.py --dry-run
        Procesa solo los 3 PDF de referencia usados para diagnóstico de
        estructura (corto/statement, largo/fosfatos, mediano/cloruros).
        No escribe nada en data/.

    python scripts/build_chunk_index.py --limit N
        Procesa los primeros N dossiers (orden estable de
        current_reevaluation_corpus()) emparejados con su PDF real.

    python scripts/build_chunk_index.py --pdf E338
        Procesa solo los dossiers cuyo nombre de archivo contiene ese
        substring. Admite varios separados por coma.

    python scripts/build_chunk_index.py --all
        Procesa los 161 PDF, EN LOTES (BATCH_SIZE, ver más abajo), con
        una línea corta por PDF (no el detalle completo de --dry-run/
        --pdf/--limit -- sería inmanejable para 161) y un marcador de
        progreso al cierre de cada lote. Si un PDF concreto lanza una
        excepción no esperada, el script PARA inmediatamente (no la
        traga ni sigue con el siguiente) y la reporta completa -- ver
        `_run_all`. Al final, resumen agregado: total de chunks,
        distribución de sustancias por tier, PDF con 0 chunks o sin
        ninguna sustancia resuelta.

    (sin argumentos) -- igual que --dry-run, con un aviso de cómo
    escalar. Nunca procesa los 161 por defecto sin --all explícito.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore  # noqa: E402
from efsa_rag.ingestion.pdf_chunking import (  # noqa: E402
    DossierChunkingResult,
    DossierPdf,
    chunk_dossier,
    map_corpus_to_pdfs,
)

BATCH_SIZE = 20

XLSX_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "OFT3_0_export_repository.xlsx"
PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "pdfs"

# Los 3 PDF de referencia para diagnóstico de estructura: corto/statement
# (que además resultó ser el único caso sin sustancia resoluble por
# título ni enlace, ver CLAUDE.md), largo/fosfatos (jerarquía numerada
# de 4 niveles + Tabla 5a, el caso que motivó la Opción A de tablas),
# mediano/cloruros (discussion_is_boilerplate=True en el xlsx pero con
# discusión sustantiva propia en el PDF).
REFERENCE_PDF_SUBSTRINGS = ("2011.1996", "j.efsa.2019.5674", "j.efsa.2019.5751")

MAX_EXAMPLE_CHUNKS = 3
EXAMPLE_TEXT_PREVIEW_CHARS = 260


def _select_dossiers(
    all_dossiers: list[DossierPdf], dry_run: bool, limit: int | None, pdf_substring: str | None
) -> list[DossierPdf]:
    if pdf_substring:
        # Admite varios substrings separados por coma para seleccionar un
        # lote elegido a mano (ej. "--pdf E951,E171,sinE_2011.1996") sin
        # tener que lanzar el script una vez por PDF.
        substrings = [s.strip() for s in pdf_substring.split(",") if s.strip()]
        return [d for d in all_dossiers if any(s in d.pdf_path.name for s in substrings)]
    if dry_run or (limit is None and pdf_substring is None):
        return [
            d
            for d in all_dossiers
            if any(sub in d.pdf_path.name for sub in REFERENCE_PDF_SUBSTRINGS)
        ]
    return all_dossiers[:limit]


def _print_result(result: DossierChunkingResult) -> None:
    dossier = result.dossier
    print(f"\n{'=' * 88}")
    print(f"PDF: {dossier.pdf_path.name}")
    print(f"Título: {dossier.title}")
    print(f"DOI: {dossier.doi}")
    print(f"Chunks generados: {len(result.chunks)}")

    tiers = sorted({r.tier for r in result.resolved_substances})
    if result.resolved_substances:
        names = ", ".join(f"{r.substance.chemical_name} (tier {r.tier})" for r in result.resolved_substances)
        print(f"Sustancias resueltas ({len(result.resolved_substances)}): {names}")
    else:
        print(
            "Sustancias resueltas: NINGUNA -- ningún nivel (1/2/3) encontró un enlace "
            "estructural ni una coincidencia de nombre en el título. Caso conocido en "
            "CLAUDE.md (1/162 dossiers, ej. statements genéricos sin E-number en el "
            "título). Chunks de texto SÍ se generaron, pero no hay RetrievedChunk para "
            "ellos -- el contrato actual exige substance_uuid no nulo."
        )
    print(f"RetrievedChunk generados: {len(result.retrieved_chunks)}")

    headings = [c.section_heading for c in result.chunks]
    distinct_headings = list(dict.fromkeys(h for h in headings if h))
    print(f"Encabezados de sección distintos detectados: {len(distinct_headings)}")
    for h in distinct_headings[:12]:
        print(f"  - {h}")
    if len(distinct_headings) > 12:
        print(f"  ... y {len(distinct_headings) - 12} más")

    print(f"\nEjemplos de chunk (hasta {MAX_EXAMPLE_CHUNKS}):")
    for chunk in result.chunks[:MAX_EXAMPLE_CHUNKS]:
        preview = chunk.text.replace("\n", " ")[:EXAMPLE_TEXT_PREVIEW_CHARS]
        print(f"  [pág. {chunk.page_number}] sección: {chunk.section_heading!r}")
        print(f"    {preview}...")

    _report_table_leak_check(result)


def _report_table_leak_check(result: DossierChunkingResult) -> None:
    """Comprobación de humo (no exhaustiva, con falsos positivos
    conocidos): ¿algún chunk EMPIEZA con una leyenda de tabla
    ("Table N: ..."), tal como haría si un bloque de leyenda no
    excluido hubiera sido el primer texto de su sección? Ancla al
    inicio del chunk (no de cualquier línea interna) porque anclar solo
    al inicio de línea da falsos positivos reales: frases narrativas
    normales envuelven su línea justo antes de mencionar una tabla por
    número ("...summarised in\\nTable 1."), lo que no es una leyenda
    que se haya colado, solo un salto de línea coincidente. Para el
    caso conocido de la Tabla 5a del PDF de fosfatos, se confirmó
    aparte (ver PROGRESS.md) que ni la leyenda ('Table 5a: Summary of
    dietary exposure...') ni una fila numérica real de esa tabla
    aparecen en ningún chunk."""
    import re

    caption_start_re = re.compile(r"^\s*table\s*\d+[a-z]?\s*[:.]", re.IGNORECASE)
    leaked = [c for c in result.chunks if caption_start_re.match(c.text)]
    if leaked:
        print(
            f"\n  AVISO: {len(leaked)} chunk(s) EMPIEZAN con una leyenda "
            "'Table N:' -- revisar la exclusión de tablas."
        )
    else:
        print(
            "\n  Confirmado: ningún chunk empieza con una leyenda de tabla sin excluir "
            "('Table N:')."
        )


def _write_jsonl_for_dossier(f, dossier: DossierPdf, result: DossierChunkingResult) -> None:
    """Una línea JSON por (chunk, sustancia resuelta) -- el mismo
    esquema "N copias por chunk" ya diseñado en CLAUDE.md para Chroma.
    `chunk_group_id` (NO es un campo de `RetrievedChunk`, se añade solo
    aquí en la persistencia) identifica las N copias del MISMO chunk de
    texto que sirven a distintas sustancias, para poder deduplicar en la
    capa de aplicación -- reproduce el mismo orden "por chunk, por
    sustancia resuelta" que ya usa `pdf_chunking.py::chunk_dossier` al
    construir `retrieved_chunks`."""
    resolved = result.resolved_substances
    for chunk_idx, chunk in enumerate(result.chunks):
        group_id = f"{dossier.dossier_uuid}#{chunk_idx}"
        for r in resolved:
            row = {
                "chunk_group_id": group_id,
                "text": chunk.text,
                "substance_uuid": r.substance.substance_uuid,
                "chemical_name": r.substance.chemical_name,
                "dossier_uuid": dossier.dossier_uuid,
                "dossier_title": dossier.title,
                "substance_resolution_tier": r.tier,
                "doi": dossier.doi,
                "section_heading": chunk.section_heading,
                "page_number": chunk.page_number,
                "pdf_filename": dossier.pdf_path.name,
            }
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
    f.flush()


def _run_all(
    store: OpenFoodToxStore,
    all_dossiers: list[DossierPdf],
    batch_size: int = BATCH_SIZE,
    save_jsonl: Path | None = None,
) -> None:
    """Procesa TODOS los dossiers emparejados, en lotes, con una línea
    corta por PDF -- el detalle completo de `_print_result` (encabezados,
    ejemplos de chunk) sería inmanejable impreso 161 veces. Para
    inmediatamente (sys.exit, no un `continue` silencioso) si un PDF
    concreto lanza una excepción no esperada -- distinto de "0 chunks" o
    "0 sustancias resueltas", que son resultados válidos ya conocidos
    (el 1/162 sin sustancia por diseño) y se acumulan en el resumen en
    vez de detener el proceso.

    `save_jsonl`, si se pasa, escribe una línea por (chunk, sustancia
    resuelta) -- persistido y con `flush()` DESPUÉS de cada dossier, no
    al final del proceso completo -- para que un fallo a mitad de la
    corrida (o del siguiente paso, embeddings) no obligue a reprocesar
    los PDF ya hechos desde cero."""
    corpus = store.current_reevaluation_corpus()

    total_chunks = 0
    total_retrieved = 0
    tier_counts = {1: 0, 2: 0, 3: 0}
    zero_chunk_pdfs: list[str] = []
    zero_substance_pdfs: list[str] = []
    processed = 0

    jsonl_file = None
    if save_jsonl is not None:
        save_jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl_file = save_jsonl.open("w", encoding="utf-8")
        print(f"Persistiendo RetrievedChunk en: {save_jsonl} (una línea JSON por chunk x sustancia)\n")

    try:
        num_batches = (len(all_dossiers) + batch_size - 1) // batch_size
        for batch_idx in range(num_batches):
            batch = all_dossiers[batch_idx * batch_size : (batch_idx + 1) * batch_size]
            for dossier in batch:
                row_df = corpus[corpus["Document UUID"] == dossier.dossier_uuid]
                try:
                    result = chunk_dossier(store, dossier, row_df)
                except Exception:
                    print(f"\n{'!' * 88}")
                    print(f"ERROR NUEVO procesando {dossier.pdf_path.name} -- DETENIENDO EL LOTE.")
                    print(f"{'!' * 88}")
                    traceback.print_exc()
                    print(
                        f"\nProcesados con éxito antes del error: {processed} dossiers, "
                        f"{total_chunks} chunks. No se sigue con el siguiente PDF -- corrige "
                        "el error y relanza (--pdf <substring> para aislar este dossier)."
                    )
                    if jsonl_file is not None:
                        print(
                            f"Lo ya escrito en {save_jsonl} hasta este punto ({processed} "
                            "dossiers) queda intacto -- no hace falta reprocesarlos."
                        )
                    sys.exit(1)

                processed += 1
                total_chunks += len(result.chunks)
                total_retrieved += len(result.retrieved_chunks)
                for r in result.resolved_substances:
                    tier_counts[r.tier] = tier_counts.get(r.tier, 0) + 1
                if not result.chunks:
                    zero_chunk_pdfs.append(dossier.pdf_path.name)
                if not result.resolved_substances:
                    zero_substance_pdfs.append(dossier.pdf_path.name)

                if jsonl_file is not None:
                    _write_jsonl_for_dossier(jsonl_file, dossier, result)

                tiers_here = sorted({r.tier for r in result.resolved_substances})
                flag = ""
                if not result.chunks:
                    flag = "  <<< 0 CHUNKS"
                elif not result.resolved_substances:
                    flag = "  <<< 0 sustancias resueltas"
                print(
                    f"  [{processed}/{len(all_dossiers)}] {dossier.pdf_path.name}: "
                    f"{len(result.chunks)} chunks, {len(result.resolved_substances)} sustancias "
                    f"(tiers {tiers_here or '-'}){flag}"
                )

            print(
                f"=== LOTE {batch_idx + 1}/{num_batches} completo -- "
                f"{processed}/{len(all_dossiers)} dossiers, {total_chunks} chunks acumulados ==="
            )
    finally:
        if jsonl_file is not None:
            jsonl_file.close()

    print(f"\n{'=' * 88}")
    print("=== RESUMEN FINAL ===")
    print(f"Dossiers procesados: {processed}/{len(all_dossiers)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Total RetrievedChunk: {total_retrieved}")
    print(
        f"Distribución de sustancias resueltas por tier -- tier 1: {tier_counts[1]}, "
        f"tier 2: {tier_counts[2]}, tier 3: {tier_counts[3]}"
    )
    print(f"PDF con 0 chunks ({len(zero_chunk_pdfs)}): {zero_chunk_pdfs or 'ninguno'}")
    print(
        f"PDF sin ninguna sustancia resuelta ({len(zero_substance_pdfs)}): "
        f"{zero_substance_pdfs} -- esperado: 1 solo caso conocido "
        "(sinE_10.2903_j.efsa.2011.1996.pdf, ver CLAUDE.md)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Procesa solo los 3 PDF de referencia.")
    parser.add_argument("--all", action="store_true", help="Procesa los 161 PDF en lotes -- ver docstring.")
    parser.add_argument("--limit", type=int, default=None, help="Procesa como mucho N dossiers.")
    parser.add_argument(
        "--pdf",
        type=str,
        default=None,
        help="Filtra por substring(s) del nombre de archivo, separados por coma.",
    )
    parser.add_argument(
        "--save-preview",
        type=str,
        default=None,
        help="Ruta opcional para volcar los RetrievedChunk generados como JSON (solo inspección).",
    )
    parser.add_argument(
        "--save-jsonl",
        type=str,
        default=None,
        help="Ruta para persistir una línea JSON por (chunk, sustancia resuelta) -- pensado para --all.",
    )
    args = parser.parse_args()

    store = OpenFoodToxStore(XLSX_PATH)
    all_dossiers = map_corpus_to_pdfs(store, PDF_DIR)
    print(f"Dossiers del corpus emparejados con un PDF real en disco: {len(all_dossiers)}")

    if args.all:
        print(f"Procesando los {len(all_dossiers)} dossiers en lotes de {BATCH_SIZE}...\n")
        save_jsonl = Path(args.save_jsonl) if args.save_jsonl else None
        _run_all(store, all_dossiers, save_jsonl=save_jsonl)
        return

    selected = _select_dossiers(all_dossiers, args.dry_run, args.limit, args.pdf)
    if not selected:
        print("Ningún dossier seleccionado -- revisa --pdf/--limit.")
        return

    if not (args.dry_run or args.limit or args.pdf):
        print(
            "Sin --dry-run/--limit/--pdf: procesando solo los 3 PDF de referencia "
            f"(mismo comportamiento que --dry-run). Para procesar más, usa --limit N "
            f"(hay {len(all_dossiers)} en total) o --pdf <substring>."
        )
    print(f"Procesando {len(selected)} dossier(es)...\n")

    corpus = store.current_reevaluation_corpus()
    all_results: list[DossierChunkingResult] = []
    for dossier in selected:
        row_df = corpus[corpus["Document UUID"] == dossier.dossier_uuid]
        result = chunk_dossier(store, dossier, row_df)
        all_results.append(result)
        _print_result(result)

    total_chunks = sum(len(r.chunks) for r in all_results)
    total_retrieved = sum(len(r.retrieved_chunks) for r in all_results)
    unresolved = [r.dossier.pdf_path.name for r in all_results if not r.resolved_substances]
    print(f"\n{'=' * 88}")
    print(f"Total: {len(all_results)} dossiers, {total_chunks} chunks, {total_retrieved} RetrievedChunk.")
    if unresolved:
        print(f"Dossiers sin sustancia resuelta ({len(unresolved)}): {', '.join(unresolved)}")

    if args.save_preview:
        preview = [
            {
                "pdf": r.dossier.pdf_path.name,
                "title": r.dossier.title,
                "doi": r.dossier.doi,
                "num_chunks": len(r.chunks),
                "resolved_substances": [
                    {"chemical_name": rs.substance.chemical_name, "tier": rs.tier}
                    for rs in r.resolved_substances
                ],
                "sample_chunks": [
                    {
                        "text": c.text,
                        "section_heading": c.section_heading,
                        "page_number": c.page_number,
                    }
                    for c in r.chunks
                ],
            }
            for r in all_results
        ]
        out_path = Path(args.save_preview)
        out_path.write_text(json.dumps(preview, ensure_ascii=False, indent=2))
        print(f"\nVolcado de inspección escrito en: {out_path}")


if __name__ == "__main__":
    main()
