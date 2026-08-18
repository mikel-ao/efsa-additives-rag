"""
Genera embeddings y puebla Chroma a partir de data/processed/chunks.jsonl
(pendiente #5 de CLAUDE.md, paso final -- desbloquea el Nodo 2).

Modelo: sentence-transformers/all-MiniLM-L6-v2 (384 dims, local, rápido),
backend ONNX + pesos int8 cuantizados (ver
ingestion/embedding_model.py -- decisión de memoria para el deploy,
sesión 18-ago-2026, corpus reindexado con este mismo backend para que
no haya desajuste con las queries en producción). Esquema de
metadatos: ingestion/chroma_index.py (sin `e_number`, ver ese módulo y
CLAUDE.md para el motivo).

Regla de CLAUDE.md sobre scripts en lote: este SÍ hace falta con
--dry-run/límite explícito -- 67.827 chunks es un procesado real de
CPU/GPU (embeddings) + escritura en disco (Chroma), no algo para
lanzar sin medir antes cuánto tarda.

Uso:
    python scripts/build_chroma_index.py --test-batch
        Lote de prueba (aspartamo E951 + tartratos, ~200-300 chunks):
        genera embeddings, mide el tiempo, escribe en una colección
        Chroma EFÍMERA (en memoria, no toca data/chroma/ ni ningún
        archivo), y proyecta el tiempo estimado para los 67.827
        completos. NO procesa el corpus completo.

    python scripts/build_chroma_index.py --all
        Indexa los 67.827 chunks completos en la colección Chroma
        PERSISTENTE en data/chroma/ (Opción A de despliegue ya
        decidida en CLAUDE.md). Borra la colección si ya existía antes
        de reindexar, para no dejar entradas duplicadas de una corrida
        anterior. Imprime el tiempo REAL (no proyectado) de cada fase.

    python scripts/build_chroma_index.py --verify
        Conecta a la colección PERSISTENTE ya indexada (no reindexa
        nada) y corre unas consultas semánticas de verificación --
        pensado para confirmar que el índice quedó bien poblado y es
        consultable después de --all, o en cualquier momento posterior.

    (sin argumentos) -- igual que --test-batch.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from efsa_rag.ingestion.chroma_index import rows_to_chroma_entries  # noqa: E402
from efsa_rag.ingestion.embedding_model import EMBEDDING_DIMS, EMBEDDING_MODEL_REPO_ID, load_embedding_model  # noqa: E402

CHUNKS_JSONL_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "chunks.jsonl"
CHROMA_PERSIST_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"
COLLECTION_NAME = "efsa_reevaluation_chunks"

# Lote de prueba: aspartamo (tier 1, sustancia única, dossier largo) +
# tartratos (tier 1, 7 sustancias, dossier de grupo) -- ya procesados y
# validados en sesiones anteriores, cubren tanto el caso simple como el
# caso multi-sustancia (N copias por chunk) del esquema de metadatos.
TEST_BATCH_PDF_FILENAMES = (
    "E951_10.2903_j.efsa.2013.3496.pdf",
    "E334-E335-E336-E337-E354_10.2903_j.efsa.2020.6030.pdf",
)
TEST_BATCH_MAX_ROWS = 300

TOTAL_CORPUS_ROWS = 67_827  # ver PROGRESS.md, sesión 18-ago-2026 -- data/processed/chunks.jsonl


def _load_rows(pdf_filenames: tuple[str, ...], max_rows: int) -> list[dict]:
    """Tope POR PDF (max_rows // len(pdf_filenames)), no un tope global
    sobre el total -- con un tope global, el primer PDF que aparece en
    el jsonl (orden de `--all`, no alfabético ni por tamaño) puede
    llenar todo el lote y dejar 0 filas de los demás, como pasó en la
    primera versión de este script (300/300 filas de tartratos, 0 de
    aspartamo -- el lote dejó de ser representativo del caso
    "sustancia única" que se quería probar)."""
    if not CHUNKS_JSONL_PATH.exists():
        raise FileNotFoundError(
            f"No se encuentra {CHUNKS_JSONL_PATH} -- genera primero el corpus de chunks con "
            "scripts/build_chunk_index.py --all --save-jsonl data/processed/chunks.jsonl"
        )
    per_pdf_cap = max_rows // len(pdf_filenames)
    counts = {pdf: 0 for pdf in pdf_filenames}
    rows = []
    with CHUNKS_JSONL_PATH.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            pdf = row["pdf_filename"]
            if pdf in counts and counts[pdf] < per_pdf_cap:
                rows.append(row)
                counts[pdf] += 1
            if all(c >= per_pdf_cap for c in counts.values()):
                break
    return rows


def run_test_batch() -> None:
    print(f"Cargando lote de prueba desde {CHUNKS_JSONL_PATH} ...")
    rows = _load_rows(TEST_BATCH_PDF_FILENAMES, TEST_BATCH_MAX_ROWS)
    if not rows:
        print("Lote de prueba vacío -- revisa TEST_BATCH_PDF_FILENAMES contra el jsonl real.")
        return
    by_pdf: dict[str, int] = {}
    for r in rows:
        by_pdf[r["pdf_filename"]] = by_pdf.get(r["pdf_filename"], 0) + 1
    print(f"Filas cargadas: {len(rows)}")
    for pdf, n in by_pdf.items():
        print(f"  {pdf}: {n} filas")

    entries = rows_to_chroma_entries(rows)
    texts = [e.text for e in entries]

    print(f"\nCargando modelo de embeddings: {EMBEDDING_MODEL_REPO_ID} (backend onnx, int8) ...")
    t0 = time.time()
    model = load_embedding_model()
    load_time = time.time() - t0
    print(f"Modelo cargado en {load_time:.1f} s (device: {model.device})")

    print(f"\nGenerando embeddings de {len(texts)} chunks ...")
    t0 = time.time()
    embeddings = model.encode(texts, show_progress_bar=False)
    encode_time = time.time() - t0
    rate = len(texts) / encode_time if encode_time > 0 else float("inf")
    print(f"Embeddings generados en {encode_time:.2f} s -- {rate:.1f} chunks/s")
    print(f"Dimensión del embedding: {embeddings.shape[1]} (esperado {EMBEDDING_DIMS})")
    assert embeddings.shape[1] == EMBEDDING_DIMS, "Dimensión inesperada -- revisar el modelo"

    print("\nEscribiendo en una colección Chroma EFÍMERA (en memoria, no toca disco) ...")
    import chromadb

    client = chromadb.EphemeralClient()
    collection = client.create_collection("test_batch")
    t0 = time.time()
    collection.add(
        ids=[e.id for e in entries],
        embeddings=embeddings.tolist(),
        documents=texts,
        metadatas=[e.metadata for e in entries],
    )
    write_time = time.time() - t0
    print(f"Escritura en Chroma: {write_time:.2f} s para {len(entries)} entradas")

    count = collection.count()
    print(f"Verificación: collection.count() = {count} (esperado {len(entries)})")

    # Consulta de humo: ¿el filtro por substance_uuid + metadatos funciona?
    sample_substance = entries[0].metadata["substance_uuid"]
    result = collection.get(where={"substance_uuid": sample_substance}, limit=3)
    print(
        f"Consulta de humo (where substance_uuid={sample_substance[:8]}...): "
        f"{len(result['ids'])} resultados, metadatos de ejemplo: {result['metadatas'][0]}"
    )

    # Consulta semántica de humo con una pregunta real en lenguaje
    # natural (no un embedding ya en la colección -- ese caso trivial
    # solo confirma que un texto idéntico da distancia 0, no que la
    # búsqueda semántica funcione de verdad). Genotoxicidad aparece en
    # ambos dossiers de prueba (tartratos y aspartamo), así que un buen
    # resultado debería mezclar chunks de los dos, no solo de uno.
    query_text = "genotoxicity studies and safety assessment"
    query_embedding = model.encode([query_text])[0]
    query_result = collection.query(query_embeddings=[query_embedding.tolist()], n_results=5)
    result_pdfs = [m["pdf_filename"] for m in query_result["metadatas"][0]]
    print(f"\nConsulta semántica de humo -- pregunta: {query_text!r}")
    print(f"  distancias: {[round(d, 4) for d in query_result['distances'][0]]}")
    print(f"  PDF de origen de cada resultado: {result_pdfs}")
    for text, meta in zip(query_result["documents"][0][:2], query_result["metadatas"][0][:2]):
        print(f"    [{meta['section_heading']!r}] {text[:150]!r}...")

    print(f"\n{'=' * 88}")
    print("=== PROYECCIÓN PARA EL CORPUS COMPLETO ===")
    print(f"Tasa medida: {rate:.1f} chunks/s (embeddings) sobre {len(texts)} chunks reales")
    projected_encode_s = TOTAL_CORPUS_ROWS / rate if rate > 0 else float("inf")
    write_rate = len(entries) / write_time if write_time > 0 else float("inf")
    projected_write_s = TOTAL_CORPUS_ROWS / write_rate if write_rate > 0 else float("inf")
    total_projected = projected_encode_s + projected_write_s + load_time
    print(f"Total de filas a procesar en el corpus completo: {TOTAL_CORPUS_ROWS}")
    print(f"Tiempo estimado de embeddings: {projected_encode_s / 60:.1f} min")
    print(f"Tiempo estimado de escritura en Chroma: {projected_write_s / 60:.1f} min")
    print(f"Tiempo total estimado (+ carga del modelo, una vez): {total_projected / 60:.1f} min")
    print(
        "\nNota: proyección lineal a partir de un lote de 300 -- no tiene en cuenta "
        "posible I/O adicional al escribir en un cliente persistente (data/chroma/) en vez "
        "de en memoria, ni el efecto de un lote mucho mayor sobre el uso de GPU/memoria."
    )


# Consultas de verificación -- una ya usada en el lote de prueba
# (genotoxicidad, cubre ambos PDF de esa prueba) más un caso conocido y
# específico (TiO2, ver CLAUDE.md: dictamen de 2021 que concluyó que ya
# no es seguro como aditivo por preocupaciones de genotoxicidad, sin
# ADI establecido -- caso Tier 2 ya usado como ejemplo en otros tests
# de este proyecto) y un tercero sobre un tema distinto (exposición
# dietética) para no probar solo variaciones de genotoxicidad.
VERIFY_QUERIES = (
    "genotoxicity studies and safety assessment",
    "why was titanium dioxide withdrawn as a food additive",
    "dietary exposure assessment uncertainties",
)


def _print_query_result(collection, model, query_text: str, n_results: int = 5) -> None:
    query_embedding = model.encode([query_text])[0]
    result = collection.query(query_embeddings=[query_embedding.tolist()], n_results=n_results)
    pdfs = [m["pdf_filename"] for m in result["metadatas"][0]]
    print(f"\nConsulta: {query_text!r}")
    print(f"  distancias: {[round(d, 4) for d in result['distances'][0]]}")
    print(f"  PDF de origen: {pdfs}")
    for text, meta in zip(result["documents"][0][:2], result["metadatas"][0][:2]):
        preview = text.replace(chr(10), " ")[:180]
        print(f"    [{meta['chemical_name']} | {meta['section_heading']!r}] {preview!r}...")


def run_full_index() -> None:
    """Indexa los 67.827 chunks completos en la colección Chroma
    PERSISTENTE en data/chroma/. Mide tiempo REAL (no proyección) de
    cada fase -- para comparar contra la proyección de --test-batch."""
    t_total_start = time.time()

    print(f"Cargando corpus completo desde {CHUNKS_JSONL_PATH} ...")
    rows = []
    with CHUNKS_JSONL_PATH.open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    print(f"Filas cargadas: {len(rows)}")

    entries = rows_to_chroma_entries(rows)
    texts = [e.text for e in entries]

    print(f"\nCargando modelo de embeddings: {EMBEDDING_MODEL_REPO_ID} (backend onnx, int8) ...")
    t0 = time.time()
    model = load_embedding_model()
    load_time = time.time() - t0
    print(f"Modelo cargado en {load_time:.1f} s (device: {model.device})")

    print(f"\nGenerando embeddings de {len(texts)} chunks (puede tardar varios minutos) ...")
    t0 = time.time()
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=256)
    encode_time = time.time() - t0
    rate = len(texts) / encode_time if encode_time > 0 else float("inf")
    print(f"Embeddings generados en {encode_time / 60:.2f} min -- {rate:.1f} chunks/s")

    print(f"\nEscribiendo en colección Chroma PERSISTENTE en {CHROMA_PERSIST_DIR} ...")
    import chromadb

    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    existing = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing:
        print(f"Colección '{COLLECTION_NAME}' ya existía -- borrándola antes de reindexar (evita duplicados).")
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(COLLECTION_NAME)

    max_batch = client.get_max_batch_size()
    write_batch_size = min(max_batch, 5000)
    ids_all = [e.id for e in entries]
    metas_all = [e.metadata for e in entries]
    embs_all = embeddings.tolist()

    t0 = time.time()
    for i in range(0, len(entries), write_batch_size):
        j = min(i + write_batch_size, len(entries))
        collection.add(ids=ids_all[i:j], embeddings=embs_all[i:j], documents=texts[i:j], metadatas=metas_all[i:j])
        print(f"  escritas {j}/{len(entries)}")
    write_time = time.time() - t0

    total_time = time.time() - t_total_start
    count = collection.count()

    print(f"\n{'=' * 88}")
    print("=== RESUMEN FINAL -- INDEXADO COMPLETO EN data/chroma/ ===")
    print(f"Verificación: collection.count() = {count} (esperado {len(entries)})")
    if count != len(entries):
        print("  AVISO: el recuento no coincide -- revisar antes de dar el índice por bueno.")
    print(f"Tiempo REAL -- carga del modelo: {load_time:.1f} s")
    print(f"Tiempo REAL -- embeddings ({rate:.1f} chunks/s): {encode_time / 60:.2f} min")
    print(f"Tiempo REAL -- escritura en Chroma: {write_time / 60:.2f} min")
    print(f"Tiempo REAL -- TOTAL: {total_time / 60:.2f} min")
    print(f"(Proyección previa del lote de prueba: ~4.1 min -- ver PROGRESS.md, sesión 18-ago-2026)")

    print(f"\n{'=' * 88}")
    print("=== CONSULTAS DE VERIFICACIÓN (sobre el índice completo) ===")
    for q in VERIFY_QUERIES:
        _print_query_result(collection, model, q)


def run_verify() -> None:
    """Conecta a la colección PERSISTENTE ya indexada (sin reindexar) y
    corre las consultas de verificación -- para comprobar el índice en
    cualquier momento posterior a --all."""
    if not CHROMA_PERSIST_DIR.exists():
        print(f"No existe {CHROMA_PERSIST_DIR} -- corre primero --all.")
        return
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as e:
        print(f"No se pudo abrir la colección '{COLLECTION_NAME}': {e}")
        return

    count = collection.count()
    print(f"Colección '{COLLECTION_NAME}' en {CHROMA_PERSIST_DIR}: {count} entradas.")

    print(f"Cargando modelo de embeddings: {EMBEDDING_MODEL_REPO_ID} (backend onnx, int8) ...")
    model = load_embedding_model()

    for q in VERIFY_QUERIES:
        _print_query_result(collection, model, q)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--test-batch",
        action="store_true",
        help="Lote de prueba (aspartamo + tartratos, ~200-300 chunks). No toca data/chroma/.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Indexa los 67.827 chunks completos en la colección persistente data/chroma/.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Conecta a la colección persistente ya indexada y corre consultas de verificación.",
    )
    args = parser.parse_args()

    if args.all:
        run_full_index()
        return
    if args.verify:
        run_verify()
        return

    if not args.test_batch:
        print("Sin --test-batch/--all/--verify: se ejecuta el lote de prueba por defecto (no toca data/chroma/).")
    run_test_batch()


if __name__ == "__main__":
    main()
