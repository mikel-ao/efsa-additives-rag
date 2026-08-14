"""
Los 4 nodos del grafo LangGraph. Ver docs/efsa-rag-proyecto.html -> ARCHITECTURE.md
para el diagrama y el razonamiento de cada decisión.

Estado del desarrollo: esqueleto con contratos de entrada/salida definidos
y el system prompt del Nodo 4 ya fijado (fue una decisión de diseño
explícita, no debe quedar a criterio del LLM en tiempo de ejecución).
La implementación real de las llamadas al LLM (Nodo 1, 3-fallback, 4)
queda pendiente de conectar con el cliente de DeepSeek.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from efsa_rag.ingestion.openfoodtox import OpenFoodToxStore, OpinionReference

# --------------------------------------------------------------------- #
# Nodo 4 -- restricción de comunicación de riesgo (decisión de diseño,
# NO tocar sin volver a discutir el razonamiento científico detrás).
# --------------------------------------------------------------------- #

NODE_4_SAFETY_COMMUNICATION_RULES = """\
Al describir el ADI/TDI de una sustancia y su relación con la salud:

1. SIEMPRE que menciones el efecto crítico (CriticalEndpoint) que
   fundamenta el valor de referencia, aclara explícitamente que el ADI
   incluye un factor de incertidumbre (normalmente x100) aplicado sobre
   el NOAEL/punto de partida -- es decir, el ADI ya está muy por debajo
   de la dosis a la que se observó el efecto en los estudios.

2. PROHIBIDO redactar frases del tipo "si se supera el ADI, se
   produce/puede producir [efecto]". El ADI no es un umbral de
   toxicidad, es un límite de exposición segura con margen incorporado.

3. Fórmula correcta: "el ADI incorpora un margen de seguridad de
   [factor] veces por debajo de la dosis a la que se observó [efecto]
   en el estudio pivotal [especie/duración]" -- describe el mecanismo
   del límite, nunca dramatiza el exceso.

4. Si el usuario pregunta directamente "¿qué pasa si supero el ADI?",
   responde explicando el propósito del margen de seguridad, no
   especulando sobre síntomas.

5. Esta herramienta es de exploración de literatura regulatoria, no de
   asesoramiento regulatorio ni médico. No emitas juicios de "seguro" /
   "no seguro" -- cita lo que dice el dictamen.
"""


class GraphState(TypedDict, total=False):
    user_query: str
    substance_name: str | None
    substance_uuid: str | None
    structured_result: OpinionReference | None
    retrieved_chunks: list[str]
    vigencia_ambigua: bool
    answer: str
    citation: str | None


@dataclass
class NodeDependencies:
    store: OpenFoodToxStore
    vectorstore: object | None = None  # Chroma, se conecta en graph/build.py
    llm_client: object | None = None  # cliente DeepSeek, se conecta en graph/build.py


# --------------------------------------------------------------------- #
# Nodo 1 -- extracción de entidad
# --------------------------------------------------------------------- #

def extract_entity_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Identifica qué aditivo/E-number pregunta el usuario.

    TODO: llamada real al LLM con prompt corto (~200 tokens de entrada,
    ver estimación de coste en docs/). Placeholder de contrato.
    """
    raise NotImplementedError


# --------------------------------------------------------------------- #
# Nodo 2 -- retrieval híbrido
# --------------------------------------------------------------------- #

def hybrid_retrieval_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Query estructurada contra OpenFoodTox + búsqueda vectorial contra
    Chroma para el contexto narrativo del dictamen.

    TODO: conectar deps.vectorstore.similarity_search(...).
    """
    raise NotImplementedError


# --------------------------------------------------------------------- #
# Nodo 3 -- verificación de vigencia
# --------------------------------------------------------------------- #

def verify_currency_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Determinista primero (ver ingestion/openfoodtox.py::
    current_reference_value_opinion, verificado con aspartamo). Solo cae
    a LLM sobre el texto del PDF si hay ambigüedad real (varias 'EFSA
    opinion' del mismo tipo, fechas muy próximas, título no concluyente).
    """
    substance_uuid = state.get("substance_uuid")
    if not substance_uuid:
        raise ValueError("Nodo 3 requiere substance_uuid ya resuelto por el Nodo 1")

    result = deps.store.current_reference_value_opinion(substance_uuid)
    new_state: GraphState = {**state, "structured_result": result}

    # Marcador de ambigüedad: placeholder -- la lógica real de detección de
    # ambigüedad (candidatos con fechas dentro de una ventana estrecha, o
    # título no concluyente) se implementa aquí, no en el prompt del LLM.
    new_state["vigencia_ambigua"] = result is None

    return new_state


# --------------------------------------------------------------------- #
# Nodo 4 -- generación con cita obligatoria
# --------------------------------------------------------------------- #

def generate_answer_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Redacta la respuesta citando el número exacto de EFSA Journal / DOI.
    Aplica NODE_4_SAFETY_COMMUNICATION_RULES como parte del system prompt.

    TODO: construir el prompt combinando structured_result +
    retrieved_chunks + NODE_4_SAFETY_COMMUNICATION_RULES, llamar a
    deps.llm_client.
    """
    raise NotImplementedError
