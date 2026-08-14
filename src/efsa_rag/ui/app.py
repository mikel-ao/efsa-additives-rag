"""
UI Streamlit de demo. La lógica de refresco del corpus está bloqueada por
un candado server-side de 24h (decisión de diseño: ver docs/, Opción A --
índice de Chroma horneado en el despliegue, este botón NO reindexa en
caliente en producción, solo comprueba novedades y te avisa a ti para
reindexar en local y redesplegar).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

LOCK_FILE = Path(__file__).parent.parent.parent.parent / "data" / "last_update_check.txt"
MIN_INTERVAL = timedelta(hours=24)


def _get_last_update() -> datetime | None:
    if not LOCK_FILE.exists():
        return None
    return datetime.fromisoformat(LOCK_FILE.read_text().strip())


def _check_for_new_opinions() -> int:
    """TODO: comparar Document UUID del xlsx local contra la última versión
    publicada en Zenodo. Devuelve el número de dictámenes nuevos encontrados.
    NO reindexa nada -- solo informa. El reindexado real se hace en local
    (ver docs/ -> ROADMAP.md, paso 9).
    """
    raise NotImplementedError


def render_update_section() -> None:
    st.subheader("Estado del corpus")
    last_update = _get_last_update()
    ya_comprobado_hoy = (
        last_update is not None and (datetime.now() - last_update) < MIN_INTERVAL
    )

    if ya_comprobado_hoy:
        st.info(
            f"La fuente ya se ha comprobado hoy a las "
            f"{last_update.strftime('%H:%M:%S')}."
        )
        return

    if st.button("Buscar dictámenes nuevos"):
        with st.spinner("Comprobando novedades en OpenFoodTox..."):
            ahora = datetime.now()
            LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
            LOCK_FILE.write_text(ahora.isoformat())
            # nuevos = _check_for_new_opinions()  # TODO conectar
        st.success(f"Comprobación completada a las {ahora.strftime('%H:%M:%S')}.")
        st.rerun()


def render_disclaimer() -> None:
    st.warning(
        "Esta herramienta es de exploración de literatura regulatoria, "
        "no de asesoramiento regulatorio ni médico. Las respuestas citan "
        "el dictamen EFSA correspondiente; verifica siempre la fuente "
        "original antes de tomar decisiones."
    )


def main() -> None:
    st.set_page_config(page_title="EFSA Additives RAG", page_icon="🧪")
    st.title("Reevaluación de aditivos alimentarios (EFSA)")
    render_disclaimer()

    query = st.text_input("Pregunta sobre un aditivo (nombre o E-number)")
    if query:
        st.info("TODO: conectar con el grafo LangGraph (efsa_rag.graph.build)")

    st.divider()
    render_update_section()


if __name__ == "__main__":
    main()
