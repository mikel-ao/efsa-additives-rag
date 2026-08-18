"""
UI Streamlit de demo. La lógica de refresco del corpus está bloqueada por
un candado server-side de 24h (decisión de diseño: ver docs/, Opción A --
índice de Chroma horneado en el despliegue, este botón NO reindexa en
caliente en producción, solo comprueba novedades y te avisa a ti para
reindexar en local y redesplegar).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

LOCK_FILE = Path(__file__).parent.parent.parent.parent / "data" / "last_update_check.txt"
MIN_INTERVAL = timedelta(hours=24)

# --------------------------------------------------------------------- #
# Límites de consulta -- protección de presupuesto de la API del LLM.
#
# Dos capas con roles distintos, no intercambiables:
#   - Límite GLOBAL diario: la protección real del gasto. Vive en el
#     servidor, nadie lo puede saltar. Si esto falla, el presupuesto
#     mensual (6-7 EUR) sigue acotado porque el límite es en EUR
#     estimados, no solo en número de consultas.
#   - Límite por IP: mejora de UX (reparte el uso, evita que una sola
#     persona agote el global sin querer). NO es una protección de
#     seguridad real: usa una API interna no estable de Streamlit
#     (get_script_run_ctx), y las IPs se comparten (redes corporativas)
#     o se cambian (VPN) con facilidad. Trátalo como cortesía, no como
#     candado.
# --------------------------------------------------------------------- #

USAGE_LOG = Path(__file__).parent.parent.parent.parent / "data" / "usage_log.json"
DAILY_QUERY_LIMIT_PER_IP = 10
DAILY_GLOBAL_QUERY_LIMIT = 200
# Estimación conservadora (hora punta, nuevo precio DeepSeek V4-Flash
# desde 16-ago-2026): ~$0.002/consulta. Ajustar si cambia el proveedor
# o el precio -- ver docs/efsa-rag-proyecto.html -> STACK.json.
ESTIMATED_COST_PER_QUERY_USD = 0.002
DAILY_HARD_COST_CEILING_USD = 0.35  # ~7 EUR/mes repartidos en ~30 dias, con margen


def _load_usage() -> dict:
    if not USAGE_LOG.exists():
        return {"date": str(date.today()), "global_count": 0, "estimated_cost_usd": 0.0, "by_ip": {}}
    data = json.loads(USAGE_LOG.read_text())
    if data.get("date") != str(date.today()):
        return {"date": str(date.today()), "global_count": 0, "estimated_cost_usd": 0.0, "by_ip": {}}
    return data


def _save_usage(data: dict) -> None:
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    USAGE_LOG.write_text(json.dumps(data))


def _get_client_ip() -> str:
    """Best-effort. API interna no estable -- si falla, cambia entre
    versiones de Streamlit, o devuelve algo que no es un string usable
    (ej. bajo streamlit.testing.v1.AppTest, `session_info.request` no es
    una request HTTP real -- encontrado midiendo memoria con AppTest en
    sesión 18-ago-2026, `remote_ip` no era un `str`), degrada a
    'unknown' -- el sistema sigue protegido por el límite global, que no
    depende de esto."""
    try:
        from streamlit import runtime
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is None:
            return "unknown"
        session_info = runtime.get_instance().get_client(ctx.session_id)
        ip = session_info.request.remote_ip if session_info else None
        return ip if isinstance(ip, str) and ip else "unknown"
    except Exception:
        return "unknown"


def check_and_register_query() -> tuple[bool, str]:
    """Llamar ANTES de invocar al grafo LangGraph / LLM.
    Devuelve (permitido, mensaje_si_no_permitido).
    """
    data = _load_usage()

    if data["estimated_cost_usd"] >= DAILY_HARD_COST_CEILING_USD:
        return False, "Límite diario de presupuesto alcanzado. Vuelve mañana."

    if data["global_count"] >= DAILY_GLOBAL_QUERY_LIMIT:
        return False, "Límite diario de consultas alcanzado. Vuelve mañana."

    ip = _get_client_ip()
    ip_count = data["by_ip"].get(ip, 0)
    if ip != "unknown" and ip_count >= DAILY_QUERY_LIMIT_PER_IP:
        return False, (
            f"Has alcanzado el límite de {DAILY_QUERY_LIMIT_PER_IP} "
            "consultas hoy. Vuelve mañana."
        )

    data["global_count"] += 1
    data["estimated_cost_usd"] += ESTIMATED_COST_PER_QUERY_USD
    data["by_ip"][ip] = ip_count + 1
    _save_usage(data)
    return True, ""


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


def _render_answer(query: str) -> None:
    """Import perezoso -- `efsa_rag.graph.build` carga Chroma, el modelo
    de embeddings y el cliente LLM (cacheados a nivel de módulo por
    `answer_question`, ver graph/build.py). No se paga ese coste hasta
    que se envía la primera consulta, no al arrancar la app.

    Antes de tocar `graph.build` (que es lo primero que intenta abrir
    `data/chroma/` y leer el xlsx de OpenFoodTox), se asegura que esos
    dos artefactos existen en disco -- en el deploy real no van en el
    repo de git (ver `efsa_rag.deploy_assets`, y CLAUDE.md/PROGRESS.md
    sesión 18-ago-2026 continuación 21 para el motivo de licencia), así
    que la primera consulta real del contenedor los descarga desde
    MEGA S4. En desarrollo local, si ya están en disco, esta llamada no
    toca la red en absoluto."""
    from efsa_rag.deploy_assets import ensure_deploy_assets_downloaded
    from efsa_rag.graph.build import answer_question

    try:
        with st.spinner("Preparando datos (primera consulta tras un reinicio)..."):
            ensure_deploy_assets_downloaded()
    except Exception:
        logger.exception("Fallo al descargar los assets de deploy desde MEGA S4")
        st.error(
            "No se pudieron descargar los datos necesarios para responder -- "
            "es un fallo de configuración del servicio, no de tu pregunta. "
            "Inténtalo de nuevo más tarde."
        )
        return

    with st.spinner("Consultando el dictamen EFSA vigente..."):
        try:
            result = answer_question(query)
        except Exception:
            logger.exception("Fallo al generar la respuesta (grafo/LLM)")
            st.error(
                "No se pudo generar una respuesta -- inténtalo de nuevo en unos "
                "segundos. Si el problema persiste, es un fallo del servicio, no "
                "de tu pregunta."
            )
            return

    st.write(result.answer)
    if result.structured_result and (result.structured_result.doi or result.structured_result.title):
        cita = result.structured_result.doi or result.structured_result.title
        st.caption(f"Fuente: {cita}")


def main() -> None:
    st.set_page_config(page_title="EFSA Additives RAG", page_icon="🧪")
    st.title("Reevaluación de aditivos alimentarios (EFSA)")
    render_disclaimer()

    query = st.text_input("Pregunta sobre un aditivo (nombre o E-number)")
    if query:
        permitido, mensaje = check_and_register_query()
        if not permitido:
            st.error(mensaje)
        else:
            _render_answer(query)

    st.divider()
    render_update_section()


if __name__ == "__main__":
    main()
