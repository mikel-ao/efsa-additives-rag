"""
Script MANUAL de un solo uso (por el usuario, en local, con sus propias
credenciales de MEGA S4) -- empaqueta data/chroma/ en un tarball y sube
ese tarball + el xlsx de OpenFoodTox al bucket de MEGA S4 desde el que
`efsa_rag.deploy_assets.ensure_deploy_assets_downloaded()` los
descargará en el arranque del deploy real (ver ese módulo y
CLAUDE.md/PROGRESS.md, sesión 18-ago-2026 continuación 21, para el
porqué de esta ruta en vez de versionar los datos en git).

Re-ejecutar cada vez que se reindexe el corpus en local y haga falta
propagar el índice nuevo al deploy -- sustituye los objetos existentes
en el bucket (mismo nombre, sobrescribe).

No llama a ningún LLM ni hace peticiones en bucle sobre una colección
de elementos (sube 2 objetos, punto) -- la regla de CLAUDE.md sobre
límite de iteraciones + --dry-run para scripts que sí hacen eso no
aplica aquí en sentido estricto, pero se incluye --dry-run de todas
formas porque sigue siendo una subida de ~600 MB por red que conviene
poder previsualizar antes de gastar tiempo/cuota de banda ancha.

Uso:
    export MEGA_S4_ENDPOINT_URL=...
    export MEGA_S4_BUCKET=...
    export MEGA_S4_ACCESS_KEY_ID=...
    export MEGA_S4_SECRET_ACCESS_KEY=...
    export MEGA_S4_REGION=...          # opcional, según tu bucket

    python scripts/upload_deploy_assets.py --dry-run   # solo muestra qué subiría
    python scripts/upload_deploy_assets.py              # sube de verdad
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from efsa_rag.deploy_assets import (  # noqa: E402
    CHROMA_ARCHIVE_OBJECT_KEY,
    CHROMA_PERSIST_DIR,
    XLSX_OBJECT_KEY,
    XLSX_PATH,
    _s3_client,
)


def _human_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué se subiría (tamaños, claves de objeto) sin tocar la red.",
    )
    args = parser.parse_args()

    if not XLSX_PATH.exists():
        raise SystemExit(f"No se encuentra el xlsx en {XLSX_PATH} -- nada que subir.")
    if not (CHROMA_PERSIST_DIR / "chroma.sqlite3").exists():
        raise SystemExit(f"No se encuentra data/chroma/chroma.sqlite3 en {CHROMA_PERSIST_DIR} -- nada que subir.")

    xlsx_size = XLSX_PATH.stat().st_size
    print(f"xlsx: {XLSX_PATH} ({_human_mb(xlsx_size)}) -> objeto {XLSX_OBJECT_KEY!r}")

    chroma_files = sorted(p for p in CHROMA_PERSIST_DIR.rglob("*") if p.is_file())
    chroma_total = sum(p.stat().st_size for p in chroma_files)
    print(
        f"chroma: {len(chroma_files)} ficheros bajo {CHROMA_PERSIST_DIR} "
        f"({_human_mb(chroma_total)} sin comprimir) -> tarball -> objeto "
        f"{CHROMA_ARCHIVE_OBJECT_KEY!r}"
    )

    if args.dry_run:
        print("\n--dry-run: no se ha tocado la red. Repite sin --dry-run para subir de verdad.")
        return

    client = _s3_client()
    bucket = os.environ["MEGA_S4_BUCKET"]

    print(f"\nSubiendo xlsx a s3://{bucket}/{XLSX_OBJECT_KEY} ...")
    client.upload_file(str(XLSX_PATH), bucket, XLSX_OBJECT_KEY)
    print("xlsx subido.")

    print("\nEmpaquetando data/chroma/ en un tarball temporal (puede tardar unos minutos)...")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with tarfile.open(tmp_path, "w:gz") as tar:
            for path in chroma_files:
                tar.add(path, arcname=str(path.relative_to(CHROMA_PERSIST_DIR)))
        archive_size = tmp_path.stat().st_size
        print(f"Tarball listo: {_human_mb(archive_size)} comprimido.")

        print(f"Subiendo a s3://{bucket}/{CHROMA_ARCHIVE_OBJECT_KEY} ...")
        client.upload_file(str(tmp_path), bucket, CHROMA_ARCHIVE_OBJECT_KEY)
        print("Índice de Chroma subido.")
    finally:
        tmp_path.unlink(missing_ok=True)

    print("\nListo. El deploy descargará estos objetos automáticamente en el "
          "primer arranque (ver efsa_rag.deploy_assets).")


if __name__ == "__main__":
    main()
