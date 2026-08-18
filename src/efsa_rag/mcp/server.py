"""
Servidor MCP -- dos herramientas, ambas wrappers finos sobre el grafo
LangGraph ya compilado (`graph/build.py`). No reimplementa ninguna
lógica de negocio: `search_efsa_opinion` llama a `answer_question`
(camino completo, Nodo 1->2->3->4) y `get_reevaluation_status` llama a
`resolve_current_opinion` (camino parcial, Nodo 1->3, sin retrieval
narrativo ni generación LLM) -- ambas funciones ya existentes en
`graph/build.py`.

Diseño original: `docs/efsa-rag-proyecto.html`, paso 6 del roadmap --
"search_efsa_opinion y get_reevaluation_status como wrapper del grafo
compilado". Los nombres y el parámetro único `substance` vienen de ese
diseño. El esquema completo (tipos, descripciones, forma de la salida,
y el porqué de los dos caminos de ejecución) se revisó explícitamente
con el usuario antes de escribir este archivo -- ver CLAUDE.md,
"Decisiones de arquitectura ya tomadas", sección "Dos caminos de
ejecución del grafo", para las garantías de seguridad de cada uno
(en particular, por qué saltarse el Nodo 4 en el camino parcial no
compromete la restricción no negociable #1 sobre comunicación de
riesgo del ADI/TDI).

Uso: `python -m efsa_rag.mcp.server` (transporte stdio, el estándar
para clientes MCP locales).
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from efsa_rag.graph.build import answer_question, resolve_current_opinion

# Constante fija, NO generada por ningún LLM -- capa extra de defensa en
# profundidad específica del servidor MCP (no una regla nueva del Nodo
# 4, que ya cubre esto en sus respuestas narrativas vía
# NODE_4_SAFETY_COMMUNICATION_RULES). get_reevaluation_status devuelve
# números crudos (adi_value/adi_unit) sin pasar por el Nodo 4 -- un
# cliente MCP externo que consuma ese JSON y componga su propia prosa a
# partir de esos números no tiene, por defecto, el contexto que el Nodo
# 4 sí incorpora. Ver CLAUDE.md para el razonamiento completo.
SAFETY_NOTE = (
    "El ADI/TDI es un margen de seguridad (~100x el NOAEL), no un umbral "
    "de toxicidad. Superarlo no implica que se produzca un efecto adverso."
)

SubstanceParam = Annotated[
    str,
    Field(
        description=(
            "Nombre del aditivo alimentario en lenguaje natural (inglés o "
            'español) o su E-number -- p.ej. "aspartame", "aspartamo", '
            '"E 951", "titanium dioxide". Se resuelve con el mismo Nodo 1 '
            "de extracción de entidad que usa el resto del sistema; no "
            "exige coincidencia exacta -- si no se identifica ninguna "
            "sustancia, la herramienta lo indica explícitamente en vez de "
            "fallar o inventar una."
        )
    ),
]

server = MCPServer(
    name="efsa-additives-rag",
    description=(
        "Consulta dictámenes de reevaluación EFSA de aditivos alimentarios "
        "(Reglamento UE 257/2010). Herramienta de exploración de "
        "literatura regulatoria -- nunca emite juicios de 'seguro'/'no "
        "seguro', solo cita lo que dice el dictamen vigente."
    ),
)


@server.tool()
def search_efsa_opinion(substance: SubstanceParam) -> dict[str, Any]:
    """Busca y resume lo que dice el dictamen de reevaluación EFSA
    vigente sobre un aditivo alimentario. Ejecuta el grafo completo
    (identificación de sustancia + retrieval narrativo del PDF +
    generación con las reglas de comunicación de riesgo del proyecto --
    nunca un veredicto de "seguro"/"no seguro", el ADI se presenta
    siempre como margen de seguridad, nunca como umbral de toxicidad).
    Devuelve una respuesta en lenguaje natural, fundamentada y citada
    (DOI/título del dictamen)."""
    result = answer_question(substance)
    structured = result.structured_result

    return {
        "substance_identified": result.substance_name,
        "answer": result.answer,
        "dossier_title": structured.title if structured else None,
        "doi": structured.doi if structured else None,
        "retrieved_chunks_count": len(result.retrieved_chunks),
    }


@server.tool()
def get_reevaluation_status(substance: SubstanceParam) -> dict[str, Any]:
    """Devuelve el estado estructurado (no narrativo) de la reevaluación
    EFSA vigente para un aditivo alimentario: fecha, DOI/título de
    referencia, y ADI/TDI si existe -- citado tal cual de OpenFoodTox,
    sin pasar por generación LLM (más rápido y más barato que
    search_efsa_opinion, pensado para consumo programático). Si el
    sistema no pudo determinar un dictamen vigente, o no identificó
    ninguna sustancia, lo indica explícitamente en vez de inventar un
    valor."""
    status = resolve_current_opinion(substance)
    structured = status.structured_result

    return {
        "substance_identified": status.substance_name,
        "dossier_found": structured is not None,
        "dossier_title": structured.title if structured else None,
        "doi": structured.doi if structured else None,
        "date_of_evaluation": (
            structured.date_of_evaluation.isoformat()
            if structured and structured.date_of_evaluation
            else None
        ),
        "adi_value": structured.adi_value if structured else None,
        "adi_unit": structured.adi_unit if structured else None,
        "adi_justification": structured.adi_justification if structured else None,
        "discussion_available": bool(
            structured and structured.discussion_text and not structured.discussion_is_boilerplate
        ),
        "safety_note": SAFETY_NOTE,
    }


if __name__ == "__main__":
    server.run()
