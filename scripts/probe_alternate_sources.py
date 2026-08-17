"""
Diagnóstico de solo lectura (continuación de scripts/probe_dossier_urls.py,
ver CLAUDE.md "Hallazgos verificados" -- Wiley descartado por bloqueo
Cloudflare): comprueba dos rutas alternativas para los mismos 5 DOIs de
ejemplo, SIN descargar el cuerpo de ninguna respuesta.

  (1) efsa.europa.eu/en/efsajournal/pub/<referencia> -- la "referencia"
      es el último segmento numérico del DOI (ej. DOI
      10.2903/j.efsa.2013.3496 -> referencia 3496, confirmado por
      búsqueda web contra el caso real de aspartamo antes de escribir
      este script -- no es una suposición sin verificar).
  (2) PubMed Central (PMC) -- busca el PMCID correspondiente al DOI vía
      la API pública E-utilities de NCBI (esearch, db=pmc), y si lo
      encuentra, comprueba la página del artículo y el patrón de PDF de
      PMC.

Mismas reglas que el script anterior: límite explícito (MAX_ITEMS),
pausa de cortesía entre CADA petición de red (no solo por DOI), y flag
--dry-run que imprime el plan sin hacer ninguna petición.

Uso:
    python scripts/probe_alternate_sources.py            # ejecuta el sondeo (solo cabeceras)
    python scripts/probe_alternate_sources.py --dry-run   # solo imprime el plan
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore  # noqa: E402

XLSX_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "OFT3_0_export_repository.xlsx"

MAX_ITEMS = 5
REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "efsa-additives-rag/0.1 (proyecto de portfolio, exploracion de dictamenes EFSA; contacto via github)"

NCBI_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def _sample_dois(store: OpenFoodToxStore) -> list[tuple[str, str]]:
    """Mismos 5 DOIs de ejemplo que scripts/probe_dossier_urls.py --
    aspartamo primero, + 4 más de current_reevaluation_corpus()."""
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


def _efsa_reference_from_doi(doi: str) -> str | None:
    """Último segmento numérico del DOI -- ej.
    "10.2903/j.efsa.2013.3496" -> "3496". `None` si el DOI no sigue el
    patrón esperado (no asumir que todos los DOIs de EFSA lo cumplen sin
    comprobarlo caso a caso)."""
    match = re.search(r"\.(\d+)$", doi)
    return match.group(1) if match else None


def _probe_url(url: str) -> dict:
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
            "final_url": resp.url,
            "status_code": resp.status_code,
            "content_type": resp.headers.get("Content-Type", "(sin cabecera)"),
            "content_length": resp.headers.get("Content-Length", "(desconocido)"),
            "error": None,
        }
    except requests.RequestException as exc:
        return {
            "final_url": None,
            "status_code": None,
            "content_type": None,
            "content_length": None,
            "error": str(exc),
        }


def _print_probe_result(label: str, url: str, result: dict) -> None:
    print(f"  [{label}] {url}")
    if result["error"]:
        print(f"      ERROR: {result['error']}")
    else:
        print(f"      -> {result['final_url']}")
        print(
            f"      status={result['status_code']}  "
            f"content-type={result['content_type']}  "
            f"content-length={result['content_length']}"
        )


def _pmc_id_for_doi(doi: str) -> str | None:
    """Busca el PMCID correspondiente a un DOI vía la API pública
    E-utilities de NCBI (esearch, db=pmc, term=<doi>[DOI]). Devuelve el
    PMCID (con prefijo "PMC") o None si no hay coincidencia."""
    params = {
        "db": "pmc",
        "term": f"{doi}[DOI]",
        "retmode": "json",
    }
    try:
        resp = requests.get(
            NCBI_ESEARCH_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        print(f"      ERROR consultando ESearch: {exc}")
        return None

    if resp.status_code != 200:
        print(f"      ESearch devolvió status={resp.status_code}")
        return None

    try:
        id_list = resp.json()["esearchresult"]["idlist"]
    except (KeyError, ValueError) as exc:
        print(f"      ESearch: respuesta inesperada ({exc})")
        return None

    if not id_list:
        return None
    return f"PMC{id_list[0]}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo imprime el plan (qué URLs se consultarían), sin hacer ninguna petición de red.",
    )
    args = parser.parse_args()

    store = OpenFoodToxStore(XLSX_PATH)
    samples = _sample_dois(store)

    print(
        f"Plan: {len(samples)} DOIs de ejemplo (límite MAX_ITEMS={MAX_ITEMS}), "
        f"pausa de {REQUEST_DELAY_SECONDS}s entre CADA petición de red.\n"
    )
    for i, (title, raw_doi) in enumerate(samples, start=1):
        doi = _clean_doi(raw_doi)
        ref = _efsa_reference_from_doi(doi)
        print(f"  {i}. DOI={doi}  referencia_efsa={ref}  -- {title[:70]!r}")
    print()

    if args.dry_run:
        print("--dry-run: no se hace ninguna petición de red (ni a efsa.europa.eu ni a NCBI/PMC).")
        return

    for i, (title, raw_doi) in enumerate(samples, start=1):
        doi = _clean_doi(raw_doi)
        print(f"[{i}/{len(samples)}] {doi} -- {title[:70]!r}")

        # --- Ruta 1: efsa.europa.eu ---
        ref = _efsa_reference_from_doi(doi)
        if ref is None:
            print("  [efsa.europa.eu] DOI no sigue el patrón esperado, se omite.")
        else:
            efsa_url = f"https://www.efsa.europa.eu/en/efsajournal/pub/{ref}"
            result = _probe_url(efsa_url)
            _print_probe_result("efsa.europa.eu", efsa_url, result)
        time.sleep(REQUEST_DELAY_SECONDS)

        # --- Ruta 2: PubMed Central ---
        print("  [PMC] buscando PMCID vía ESearch...")
        pmcid = _pmc_id_for_doi(doi)
        time.sleep(REQUEST_DELAY_SECONDS)

        if pmcid is None:
            print("  [PMC] sin PMCID encontrado para este DOI.")
        else:
            print(f"  [PMC] encontrado: {pmcid}")
            article_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
            result = _probe_url(article_url)
            _print_probe_result("PMC articulo", article_url, result)
            time.sleep(REQUEST_DELAY_SECONDS)

            pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"
            result = _probe_url(pdf_url)
            _print_probe_result("PMC pdf", pdf_url, result)

        print()
        if i < len(samples):
            time.sleep(REQUEST_DELAY_SECONDS)


if __name__ == "__main__":
    main()
