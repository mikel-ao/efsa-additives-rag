"""
Descarga de los artefactos pesados del deploy (xlsx de OpenFoodTox +
índice de Chroma) desde almacenamiento externo (MEGA S4, API
compatible S3) en tiempo de arranque -- NO se versionan en git bajo
ningún esquema (ni siquiera Git LFS en un repo privado, ver
CLAUDE.md/PROGRESS.md sesión 18-ago-2026, continuación 21).

Motivo: `data/chroma/` contiene texto literal de los chunks de los
PDFs, no solo embeddings -- casi la mitad del corpus (79/161,
dictámenes 2007-2016) no tiene ninguna licencia abierta, y la otra
mitad (CC BY-ND 2016-2025) está pensada para el artículo completo sin
cambios, no fragmentos. Meter eso en CUALQUIER repo de GitHub
(público o privado) sería redistribuir contenido con licencia
restrictiva vía un proveedor (GitHub) fuera del control del proyecto
-- decisión ya tomada, ver CLAUDE.md "Decisiones de arquitectura ya
tomadas", que este módulo respeta, no reabre.

Uso: `ensure_deploy_assets_downloaded()` se llama UNA vez, con import
perezoso, justo antes de que `graph.build` construya el grafo (ver
`ui/app.py::_render_answer`) -- si los archivos YA están presentes en
disco (desarrollo local, o un contenedor de deploy que no se ha
reiniciado desde la última descarga), no toca la red en absoluto.

Credenciales SIEMPRE vía variables de entorno (en Streamlit Community
Cloud, pegadas en el campo "Secrets" del deploy -- Streamlit las
expone automáticamente como os.environ además de st.secrets, sin
código adicional). Nunca hardcodeadas aquí ni en ningún commit.
"""

from __future__ import annotations

import os
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
XLSX_PATH = REPO_ROOT / "data" / "raw" / "OFT3_0_export_repository.xlsx"
CHROMA_PERSIST_DIR = REPO_ROOT / "data" / "chroma"
CHROMA_SQLITE_FILE = CHROMA_PERSIST_DIR / "chroma.sqlite3"

# Nombres de objeto dentro del bucket -- fijos, no configurables por
# env var (a diferencia de endpoint/bucket/credenciales, que sí son
# específicos de la cuenta del usuario). Deben coincidir exactamente
# con lo que sube `scripts/upload_deploy_assets.py`.
XLSX_OBJECT_KEY = "openfoodtox/OFT3_0_export_repository.xlsx"
CHROMA_ARCHIVE_OBJECT_KEY = "chroma/chroma_index.tar.gz"

# Variables de entorno esperadas -- ver .env.example para el
# placeholder local y README.md para cómo pegarlas en Streamlit
# Community Cloud (campo "Secrets", Advanced settings).
ENV_ENDPOINT_URL = "MEGA_S4_ENDPOINT_URL"
ENV_BUCKET = "MEGA_S4_BUCKET"
ENV_ACCESS_KEY_ID = "MEGA_S4_ACCESS_KEY_ID"
ENV_SECRET_ACCESS_KEY = "MEGA_S4_SECRET_ACCESS_KEY"
ENV_REGION = "MEGA_S4_REGION"  # opcional, ver _s3_client


def _s3_client():
    """Cliente boto3 apuntando a MEGA S4 (API S3-compatible) --
    endpoint_url/bucket/credenciales SIEMPRE de variables de entorno,
    nunca hardcodeados (ver docstring del módulo). `addressing_style:
    path` explícito porque MEGA S4 soporta ambos estilos (path y
    virtual-hosted, ver github.com/meganz/s4-specs) y path evita
    depender de resolución DNS de subdominios por bucket, más simple
    de verificar con un bucket recién creado."""
    import boto3
    from botocore.config import Config

    missing = [
        name
        for name in (ENV_ENDPOINT_URL, ENV_BUCKET, ENV_ACCESS_KEY_ID, ENV_SECRET_ACCESS_KEY)
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(
            "Faltan variables de entorno para descargar los datos del deploy desde "
            f"MEGA S4: {', '.join(missing)}. En Streamlit Community Cloud, "
            "pégalas en el campo \"Secrets\" (Advanced settings) -- ver README.md, "
            "sección de deploy. En local, defínelas en .env (ver .env.example) solo "
            "si necesitas forzar una re-descarga; si data/chroma/ y el xlsx ya están "
            "en disco, esta función no llega a necesitarlas."
        )

    return boto3.client(
        "s3",
        endpoint_url=os.environ[ENV_ENDPOINT_URL],
        region_name=os.environ.get(ENV_REGION) or None,
        aws_access_key_id=os.environ[ENV_ACCESS_KEY_ID],
        aws_secret_access_key=os.environ[ENV_SECRET_ACCESS_KEY],
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _download_xlsx(client) -> None:
    XLSX_PATH.parent.mkdir(parents=True, exist_ok=True)
    bucket = os.environ[ENV_BUCKET]
    tmp_path = XLSX_PATH.with_suffix(".xlsx.part")
    client.download_file(bucket, XLSX_OBJECT_KEY, str(tmp_path))
    tmp_path.rename(XLSX_PATH)


def _download_and_extract_chroma(client) -> None:
    """Descarga el tarball completo de `data/chroma/` (chroma.sqlite3 +
    el/los directorio(s) de segmento HNSW) y lo extrae -- un único
    objeto en vez de replicar un "sync" de muchos ficheros pequeños con
    boto3 (más simple y suficiente para un artefacto que solo cambia
    cuando se reindexa por completo en local, ver
    scripts/upload_deploy_assets.py)."""
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    bucket = os.environ[ENV_BUCKET]
    tmp_archive = CHROMA_PERSIST_DIR / "_chroma_index_download.tar.gz"
    client.download_file(bucket, CHROMA_ARCHIVE_OBJECT_KEY, str(tmp_archive))
    try:
        with tarfile.open(tmp_archive, "r:gz") as tar:
            tar.extractall(CHROMA_PERSIST_DIR, filter="data")
    finally:
        tmp_archive.unlink(missing_ok=True)


def ensure_deploy_assets_downloaded() -> bool:
    """Descarga el xlsx y el índice de Chroma desde MEGA S4 SOLO si no
    están ya en disco. Devuelve True si descargó algo, False si ya
    estaba todo presente (caso normal en desarrollo local, y en un
    contenedor de deploy que no se ha reiniciado desde la última
    descarga -- el disco de un contenedor activo persiste entre
    reruns del script de Streamlit dentro de la misma sesión de
    contenedor, aunque no entre redeploys/reinicios completos).

    Llamar ANTES de importar/invocar `graph.build` (que es lo primero
    que intenta abrir `data/chroma/` y leer el xlsx) -- ver
    `ui/app.py::_render_answer`.
    """
    xlsx_missing = not XLSX_PATH.exists()
    chroma_missing = not CHROMA_SQLITE_FILE.exists()

    if not xlsx_missing and not chroma_missing:
        return False

    client = _s3_client()
    if xlsx_missing:
        _download_xlsx(client)
    if chroma_missing:
        _download_and_extract_chroma(client)
    return True
