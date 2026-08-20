"""
Servidor MCP -- dos herramientas, ambas wrappers finos sobre el grafo
LangGraph ya compilado (`graph/build.py`). No reimplementa ninguna
lógica de negocio: `search_efsa_opinion` llama a `answer_question`
(camino completo, Nodo 1->2->3->4) y `get_reevaluation_status` llama a
`resolve_current_opinion` (camino parcial, Nodo 1->3, sin retrieval
narrativo ni generación LLM) -- ambas funciones ya existentes en
`graph/build.py`.

Los nombres y el parámetro único `substance` de ambas herramientas
siguen el diseño "wrapper fino del grafo compilado" -- ver CLAUDE.md,
"Decisiones de arquitectura", sección "Dos caminos de ejecución del
grafo", para las garantías de seguridad de cada uno (en particular, por
qué saltarse el Nodo 4 en el camino parcial no compromete la
restricción no negociable #1 sobre comunicación de riesgo del ADI/TDI).

**Salida en ARRAY SIEMPRE** -- `{"candidates_found", "candidates_shown",
"results": [...]}`, con 1 elemento en `results` en el caso común, nunca
un objeto plano de un único candidato. Alternativas descartadas (ver
CLAUDE.md para el detalle completo, con sus trade-offs): (B) objeto
único + campo `candidates` opcional solo si hay ambigüedad, (C) las dos
herramientas intactas + una tercera herramienta nueva de
desambiguación. Se eligió A -- no solo porque no hay ningún cliente MCP
real hoy que proteger (`output_schema` de ambas herramientas es
`{"additionalProperties": true}`, sin ningún campo declarado
formalmente, así que no hay contrato de esquema que romper), sino
porque B y C dejan la honestidad ante la ambigüedad como OPCIONAL para
el consumidor: un cliente que no sepa mirar el campo `candidates`, o
que nunca llame a la tercera herramienta, vuelve a elegir un candidato
en silencio, reintroduciendo el mismo problema que el resto del sistema
elimina estructuralmente. Con A, la honestidad es ESTRUCTURAL: no hay
ninguna forma de leer la respuesta sin toparse con el array `results` y
su longitud real.

Uso: `python -m efsa_rag.mcp.server` (transporte stdio, el estándar
para clientes MCP locales).
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from efsa_rag.graph.build import AnswerResult, ReevaluationStatus, answer_question, resolve_current_opinion
from efsa_rag.ingestion.openfoodtox import SubstanceCandidate

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


def _chunk_counts_by_substance(chunks) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.substance_uuid] = counts.get(chunk.substance_uuid, 0) + 1
    return counts


def _search_result_item(
    candidate: SubstanceCandidate,
    structured_results: dict,
    chunk_counts: dict[str, int],
) -> dict[str, Any]:
    structured = structured_results.get(candidate.substance_uuid)
    return {
        "chemical_name": candidate.chemical_name,
        "match_type": candidate.match_type,
        "match_score": candidate.match_score,
        "dossier_title": structured.title if structured else None,
        "doi": structured.doi if structured else None,
        "retrieved_chunks_count": chunk_counts.get(candidate.substance_uuid, 0),
    }


def _status_result_item(candidate: SubstanceCandidate, structured_results: dict) -> dict[str, Any]:
    structured = structured_results.get(candidate.substance_uuid)
    return {
        "chemical_name": candidate.chemical_name,
        "match_type": candidate.match_type,
        "match_score": candidate.match_score,
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
    }


@server.tool()
def search_efsa_opinion(substance: SubstanceParam) -> dict[str, Any]:
    """Busca y resume lo que dice el dictamen de reevaluación EFSA
    vigente sobre un aditivo alimentario. Ejecuta el grafo completo
    (identificación de sustancia + retrieval narrativo del PDF +
    generación con las reglas de comunicación de riesgo del proyecto --
    nunca un veredicto de "seguro"/"no seguro", el ADI se presenta
    siempre como margen de seguridad, nunca como umbral de toxicidad).

    Si el nombre resuelve a VARIAS sustancias plausibles (typo, o nombre
    genérico que cubre varias variantes reales -- ver
    OpenFoodToxStore.resolve_substance_candidates), NINGUNA se elige en
    silencio: `results` trae una entrada por candidato, con sus propios
    metadatos de citación. `answer` es un ÚNICO texto narrativo que ya
    trata cada candidato por separado internamente (mismo diseño que el
    resto del sistema, ver graph/nodes.py::_build_user_prompt) -- no se
    genera una respuesta distinta por candidato, sería una llamada al
    LLM por cada uno, coste innecesario para lo que ya resuelve una sola
    generación bien diseñada."""
    result: AnswerResult = answer_question(substance)
    chunk_counts = _chunk_counts_by_substance(result.retrieved_chunks)
    results = [
        _search_result_item(candidate, result.structured_results, chunk_counts)
        for candidate in result.substance_candidates
    ]

    return {
        "candidates_found": result.candidates_total_found,
        "candidates_shown": len(results),
        "substance_identified": result.substance_name,
        "answer": result.answer,
        "results": results,
    }


@server.tool()
def get_reevaluation_status(substance: SubstanceParam) -> dict[str, Any]:
    """Devuelve el estado estructurado (no narrativo) de la reevaluación
    EFSA vigente para un aditivo alimentario: fecha, DOI/título de
    referencia, y ADI/TDI si existe -- citado tal cual de OpenFoodTox,
    sin pasar por generación LLM (más rápido y más barato que
    search_efsa_opinion, pensado para consumo programático). Si el
    sistema no identificó ninguna sustancia, `results` viene vacío.

    Si el nombre resuelve a VARIAS sustancias plausibles, NINGUNA se
    elige en silencio: `results` trae una entrada estructurada completa
    por candidato (mismo principio que search_efsa_opinion), no solo el
    de mayor similitud."""
    status: ReevaluationStatus = resolve_current_opinion(substance)
    results = [
        _status_result_item(candidate, status.structured_results)
        for candidate in status.substance_candidates
    ]

    return {
        "candidates_found": status.candidates_total_found,
        "candidates_shown": len(results),
        "substance_identified": status.substance_name,
        "safety_note": SAFETY_NOTE,
        "results": results,
    }


if __name__ == "__main__":
    server.run()
