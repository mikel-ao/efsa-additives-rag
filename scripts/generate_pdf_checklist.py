"""
Genera el checklist de descarga MANUAL de los PDFs del corpus final
(current_reevaluation_corpus(), 162 dictámenes) -- ver CLAUDE.md,
"Hallazgos verificados": ninguna de las 3 fuentes probadas (Wiley
directo, efsa.europa.eu, PubMed Central) permite descarga automatizada
fiable, así que la descarga es manual vía navegador normal (el bloqueo
detectado es específico de peticiones automatizadas).

No hace peticiones de red -- solo lee el xlsx local y escribe el
checklist. Por eso no lleva --dry-run ni límite de iteraciones (la
regla de CLAUDE.md sobre eso es para scripts que llaman al LLM o hacen
peticiones de red en bucle, no aplica aquí).

Columnas: sustancia(s), E-number(s), DOI, título, nombre de archivo de
destino esperado, descargado (vacía, para que el usuario la rellene a
mano).

Salida: data/pdf_download_checklist.csv y data/pdf_download_checklist.md
(misma información, dos formatos -- CSV para llevar el seguimiento en
una hoja de cálculo, Markdown para verla legible en el propio repo).

Uso:
    python scripts/generate_pdf_checklist.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore  # noqa: E402

XLSX_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "OFT3_0_export_repository.xlsx"
CSV_OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "pdf_download_checklist.csv"
MD_OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "pdf_download_checklist.md"

E_NUMBER_PATTERN = re.compile(r"\bE\s?\d{3,4}[a-z]{0,2}(?:\([iv]+\))?\b", re.IGNORECASE)

# LiteratureReference.LinkToPersistentIdentifier no es consistente en el
# xlsx real -- verificado sobre el corpus de 162: 147 filas con prefijo
# "doi:", 15 con "doi. org/" (con espacio y "org/" en vez de dos puntos).
# Un DOI siempre empieza por "10." (especificación DOI) -- se usa eso
# como ancla en vez de una lista de prefijos conocidos, para no
# depender de que no aparezca una tercera variante de prefijo mañana.
DOI_PATTERN = re.compile(r"10\.\d{4,}/.+")


def _clean_doi(raw_doi: str | None) -> str | None:
    """Normaliza el prefijo del DOI -- ver DOI_PATTERN arriba, el xlsx
    real mezcla "doi:10.2903/..." y "doi. org/10.2903/...". Ancla en el
    propio DOI ("10." en adelante) en vez de en el prefijo, para cubrir
    ambas variantes con la misma lógica."""
    if raw_doi is None:
        return None
    match = DOI_PATTERN.search(raw_doi)
    return match.group(0).strip() if match else raw_doi.strip()


def _e_numbers_from_title(title: str) -> list[str]:
    """E-numbers citados en el título, en orden de aparición, sin
    duplicados -- heurístico de texto, no un campo estructural (mismo
    tipo de limitación que otros heurísticos de título de este
    proyecto, ver CLAUDE.md). Normaliza "E951"/"E 951" a "E951"."""
    seen: list[str] = []
    for match in E_NUMBER_PATTERN.finditer(title):
        normalized = match.group(0).upper().replace(" ", "")
        if normalized not in seen:
            seen.append(normalized)
    return seen


def _substances_for_dossier(
    store: OpenFoodToxStore, title: str, sub_df, dossier_docs, toxref, all_dossier_rows
) -> list[str]:
    """Sustancias ligadas a este dictamen vía FLEX_SUM.ToxRefValues -- el
    mismo enlace usado en current_reference_value_opinion.

    OJO: se busca por TÍTULO contra `all_dossier_rows` (sin deduplicar),
    no por el `Document UUID` único que devuelve
    `current_reevaluation_corpus()`/`unique_reevaluation_opinions()` --
    un dictamen de grupo genera varias filas DOSSIER con el mismo
    título y distinto UUID (una por sustancia cubierta), y el enlace
    real hacia FLEX_SUM.ToxRefValues puede estar en una fila HERMANA
    distinta de la que el dedup por título conservó. Mismo bug ya
    encontrado y corregido una vez en current_reevaluation_corpus()
    (ver CLAUDE.md) -- confirmado aquí de nuevo con el caso de
    aspartamo antes de fijar esta versión: buscar por el único UUID del
    corpus daba 0 sustancias, buscar por título entre TODAS las filas
    encuentra la correcta.

    Algunos dictámenes no tienen ningún registro ADI/TDI ligado en
    absoluto (no solo por este problema de UUID -- genuinamente sin
    enlace, ver CLAUDE.md "Hallazgos verificados", el desglose de los
    32 documentos del híbrido: saccharin, shellac, statements sin ADI
    propio); para esos, la lista queda vacía y el checklist se apoya en
    el título.
    """
    dossier_uuids_for_title = set(
        all_dossier_rows[all_dossier_rows["LiteratureReference.EFSAOutputTitle"] == title][
            "Document UUID"
        ]
    )
    linked = dossier_docs[
        (dossier_docs["DOSSIER UUID"].isin(dossier_uuids_for_title))
        & (dossier_docs["DOCUMENT TYPE"].isin(["FLEXIBLE_SUMMARY", "ToxRefValues"]))
    ]
    toxref_doc_uuids = set(linked["DOCUMENT UUID"])
    toxref_rows = toxref[toxref["Document UUID"].isin(toxref_doc_uuids)]
    substance_uuids = sorted(set(toxref_rows["Parent UUID"].dropna()))

    names = []
    for suid in substance_uuids:
        if suid not in sub_df.index:
            continue
        name = sub_df.loc[suid, "ChemicalName"]
        if hasattr(name, "iloc"):  # por si hay más de una fila para el mismo UUID
            name = name.iloc[0]
        if name not in names:
            names.append(name)
    return names


def _destination_filename(doi: str | None, e_numbers: list[str], fallback_index: int) -> str:
    """Nombre de archivo determinista: prefijo de E-numbers (para
    reconocer la sustancia a simple vista) + sufijo del DOI. El DOI
    normalmente garantiza unicidad, con UNA excepción real encontrada
    en sesión (ver `main()`, deduplicación por DOI antes de escribir):
    "Re-evaluation of saccharin..." aparece dos veces en el xlsx con el
    MISMO DOI porque el título tiene una variante con una errata de
    espacio ("and calcium" / "andcalcium") -- dos filas de corpus para
    el mismo documento real. Si no hay DOI (no debería pasar en el
    corpus final, pero no asumirlo sin comprobar), cae a un índice
    secuencial para seguir siendo único."""
    e_prefix = "-".join(e_numbers) if e_numbers else "sinE"
    if doi:
        doi_suffix = doi.replace("/", "_").replace(":", "_")
        return f"{e_prefix}_{doi_suffix}.pdf"
    return f"{e_prefix}_sinDOI_{fallback_index:03d}.pdf"


def main() -> None:
    store = OpenFoodToxStore(XLSX_PATH)
    corpus = store.current_reevaluation_corpus()
    corpus = corpus.sort_values("LiteratureReference.EFSAOutputTitle").reset_index(drop=True)

    sub_df = store.sub.set_index("Document UUID")
    dossier_docs = store.dossier_docs
    toxref = store.flex_sum_toxref
    all_dossier_rows = store.dossier

    rows = []
    for i, row in corpus.iterrows():
        title = row["LiteratureReference.EFSAOutputTitle"]
        doi = _clean_doi(row["LiteratureReference.LinkToPersistentIdentifier"])

        substances = _substances_for_dossier(
            store, title, sub_df, dossier_docs, toxref, all_dossier_rows
        )
        e_numbers = _e_numbers_from_title(title)
        filename = _destination_filename(doi, e_numbers, fallback_index=i)

        rows.append(
            {
                "sustancia": "; ".join(substances) if substances else "(ver título)",
                "e_number": "; ".join(e_numbers) if e_numbers else "",
                "doi": doi or "",
                "titulo": title,
                "archivo_destino": filename,
                "descargado": "",
            }
        )

    # Deduplicar por DOI -- encontrado en sesión 17-ago-2026: "Re-evaluation
    # of saccharin..." aparece dos veces en el xlsx con el mismo DOI
    # (10.2903/j.efsa.2024.9044), por una variante de título con una
    # errata de espacio ("and calcium salts" / "andcalcium salts"). Es
    # el mismo documento real -- sin deduplicar, el checklist pediría
    # descargarlo dos veces con el mismo nombre de archivo destino
    # (sobrescribiendo la primera descarga sin avisar). Dentro de cada
    # grupo con el mismo DOI, se prefiere la fila con sustancia
    # resuelta (no "(ver título)") -- verificado que, en el caso real,
    # las dos filas no son intercambiables: la del título con la errata
    # SÍ tenía el enlace a FLEX_SUM.ToxRefValues, la del título correcto
    # no: quedarse con la "primera" a secas habría perdido la sustancia
    # resuelta.
    groups: dict[str, list[dict]] = {}
    no_doi_rows = []
    for r in rows:
        if not r["doi"]:
            no_doi_rows.append(r)
            continue
        groups.setdefault(r["doi"], []).append(r)

    deduped_rows = []
    duplicate_titles: list[str] = []
    for doi, group in groups.items():
        if len(group) == 1:
            deduped_rows.append(group[0])
            continue
        with_substance = [g for g in group if g["sustancia"] != "(ver título)"]
        kept = with_substance[0] if with_substance else group[0]
        deduped_rows.append(kept)
        duplicate_titles.extend(g["titulo"] for g in group if g is not kept)
    rows = deduped_rows + no_doi_rows
    rows.sort(key=lambda r: r["titulo"])

    if duplicate_titles:
        print(f"Filas quitadas por DOI duplicado ({len(duplicate_titles)}):")
        for t in duplicate_titles:
            print(f"  - {t!r}")

    fieldnames = ["sustancia", "e_number", "doi", "titulo", "archivo_destino", "descargado"]

    with CSV_OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with MD_OUT_PATH.open("w", encoding="utf-8") as f:
        f.write(
            f"# Checklist de descarga manual de PDFs -- corpus de reevaluación "
            f"({len(rows)} dictámenes)\n\n"
        )
        f.write(
            "Descarga manual vía navegador normal -- ver CLAUDE.md, \"Hallazgos verificados\": "
            "ninguna de las 3 fuentes probadas (Wiley directo, efsa.europa.eu, PubMed Central) "
            "permite descarga automatizada fiable. El bloqueo detectado es específico de "
            "peticiones automatizadas; un navegador con sesión humana normal no debería "
            "toparse con el mismo challenge.\n\n"
        )
        f.write(
            "Para cada fila: busca el DOI o el título en Google/Wiley/EFSA, descarga el PDF, "
            "guárdalo como `archivo_destino` en `data/raw/pdfs/` (o la carpeta que corresponda), "
            "y marca la columna `descargado`.\n\n"
        )
        f.write(
            f"Nota: el corpus final (`current_reevaluation_corpus()`) tiene 162 filas, pero "
            f"este checklist tiene {len(rows)} -- una fila menos por un duplicado real "
            "encontrado en el xlsx (\"Re-evaluation of saccharin...\" aparece dos veces con "
            "el mismo DOI, por una variante de título con una errata de espacio). Ver "
            "CLAUDE.md, \"Hallazgos verificados\", para el detalle.\n\n"
        )
        f.write("| Sustancia | E-number | DOI | Título | Archivo destino | Descargado |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in rows:
            titulo_escaped = r["titulo"].replace("|", "\\|")
            f.write(
                f"| {r['sustancia']} | {r['e_number']} | {r['doi']} | {titulo_escaped} | "
                f"`{r['archivo_destino']}` | [ ] |\n"
            )

    print(f"Escrito: {CSV_OUT_PATH} ({len(rows)} filas)")
    print(f"Escrito: {MD_OUT_PATH} ({len(rows)} filas)")

    without_substance = sum(1 for r in rows if r["sustancia"] == "(ver título)")
    without_e_number = sum(1 for r in rows if not r["e_number"])
    print(f"Filas sin sustancia ligada vía toxref (se apoyan solo en el título): {without_substance}")
    print(f"Filas sin E-number detectado en el título: {without_e_number}")


if __name__ == "__main__":
    main()
