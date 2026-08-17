"""
Diagnóstico de solo lectura para el pipeline de descarga de PDFs (pendiente
#4 de CLAUDE.md): antes de escribir el descargador real, comprueba a qué
URL resuelve cada DOI y qué tipo de contenido devuelve (PDF directo, página
HTML de landing, error) -- SIN descargar el cuerpo de la respuesta.

Limitado a un puñado de DOIs de ejemplo (MAX_ITEMS) y con pausa de cortesía
entre peticiones -- ver CLAUDE.md, "Cómo trabajar en este repo": cualquier
script que itere sobre un lote de elementos debe tener un límite explícito
y (cuando aplica) un modo --dry-run. Este script en concreto ya es
"dry" por construcción -- no escribe ningún PDF a disco, solo inspecciona
cabeceras -- pero mantiene el flag --dry-run igualmente para que el mismo
patrón de invocación sirva de plantilla al descargador real que lo
sustituya.

Uso:
    python scripts/probe_dossier_urls.py            # imprime el plan y lo ejecuta (solo cabeceras, no descarga)
    python scripts/probe_dossier_urls.py --dry-run   # imprime el plan sin hacer ninguna petición de red
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore  # noqa: E402

XLSX_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "OFT3_0_export_repository.xlsx"

# Límite explícito -- no ampliar sin revisar también REQUEST_DELAY_SECONDS.
MAX_ITEMS = 5
REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "efsa-additives-rag/0.1 (proyecto de portfolio, exploracion de dictamenes EFSA; contacto via github)"


def _sample_dois(store: OpenFoodToxStore) -> list[tuple[str, str]]:
    """5 DOIs de ejemplo: aspartamo primero (caso de referencia del
    proyecto), + 4 más del corpus final (current_reevaluation_corpus()).
    Devuelve [(titulo, doi_limpio), ...] -- el DOI en el xlsx viene con
    prefijo "doi:" (ej. "doi:10.2903/j.efsa.2013.3496"), hay que quitarlo
    antes de construir la URL de resolución.
    """
    aspartame_uuid = store.substance_uuid_by_name("Aspartame")
    aspartame = store.current_reference_value_opinion(aspartame_uuid)
    samples = [(aspartame.title, aspartame.doi)]

    corpus = store.current_reevaluation_corpus()
    with_doi = corpus[corpus["LiteratureReference.LinkToPersistentIdentifier"].notna()]
    for _, row in with_doi.iterrows():
        if len(samples) >= MAX_ITEMS:
            break
        doi = row["LiteratureReference.LinkToPersistentIdentifier"]
        title = row["LiteratureReference.EFSAOutputTitle"]
        if doi in {d for _, d in samples}:
            continue
        samples.append((title, doi))

    return samples[:MAX_ITEMS]


def _clean_doi(raw_doi: str) -> str:
    return raw_doi.removeprefix("doi:").strip()


def _probe(doi: str) -> dict:
    """HEAD primero (más barato, no baja cuerpo); si el servidor no lo
    soporta bien (algunos landing pages de Wiley devuelven 405/403 a
    HEAD), reintenta con GET en modo streaming y cierra la conexión sin
    leer el cuerpo -- inspecciona cabeceras igual, sin descargar nada.
    """
    url = f"https://doi.org/{doi}"
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.head(
            url, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if resp.status_code in (403, 405) or "content-type" not in resp.headers:
            resp.close()
            resp = requests.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=REQUEST_TIMEOUT_SECONDS,
                stream=True,
            )
            resp.close()
        return {
            "requested_url": url,
            "final_url": resp.url,
            "status_code": resp.status_code,
            "content_type": resp.headers.get("Content-Type", "(sin cabecera)"),
            "content_length": resp.headers.get("Content-Length", "(desconocido)"),
            "error": None,
        }
    except requests.RequestException as exc:
        return {
            "requested_url": url,
            "final_url": None,
            "status_code": None,
            "content_type": None,
            "content_length": None,
            "error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo imprime el plan (qué DOIs se consultarían), sin hacer ninguna petición de red.",
    )
    args = parser.parse_args()

    store = OpenFoodToxStore(XLSX_PATH)
    samples = _sample_dois(store)

    print(f"Plan: {len(samples)} DOIs de ejemplo (límite MAX_ITEMS={MAX_ITEMS}), "
          f"pausa de {REQUEST_DELAY_SECONDS}s entre peticiones.\n")
    for i, (title, raw_doi) in enumerate(samples, start=1):
        print(f"  {i}. {_clean_doi(raw_doi)} -- {title[:80]!r}")
    print()

    if args.dry_run:
        print("--dry-run: no se hace ninguna petición de red.")
        return

    for i, (title, raw_doi) in enumerate(samples, start=1):
        doi = _clean_doi(raw_doi)
        print(f"[{i}/{len(samples)}] {doi} -- {title[:80]!r}")
        result = _probe(doi)
        if result["error"]:
            print(f"    ERROR: {result['error']}")
        else:
            print(f"    -> {result['final_url']}")
            print(f"    status={result['status_code']}  "
                  f"content-type={result['content_type']}  "
                  f"content-length={result['content_length']}")
        print()

        if i < len(samples):
            time.sleep(REQUEST_DELAY_SECONDS)


if __name__ == "__main__":
    main()
