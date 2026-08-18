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

from efsa_rag.graph.llm_client import LLMClient

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

# Reglas de fundamentación del Nodo 4 -- distintas de las reglas de
# comunicación de riesgo de arriba (esas son sobre CÓMO redactar el ADI;
# estas son sobre CON QUÉ datos redactar). Separadas porque estas últimas
# dependen del estado actual del proyecto (Nodo 2 sin implementar todavía,
# retrieved_chunks casi siempre vacío) y pueden dejar de aplicar cuando
# haya vector store real -- no tocar NODE_4_SAFETY_COMMUNICATION_RULES.
NODE_4_GROUNDING_RULES = """\
Eres el nodo de generación de un asistente RAG sobre dictámenes de
reevaluación de aditivos alimentarios de la EFSA.

Reglas de fundamentación (obligatorias, además de las reglas de
comunicación de riesgo de abajo):

1. Responde solo con lo que aparece en el CONTEXTO de este mensaje
   (dictamen vigente identificado + fragmentos narrativos, si los hay).
   No inventes valores numéricos (ADI, TDI, NOAEL) ni conclusiones del
   panel que no estén ahí.

2. Cita siempre el dictamen exacto -- título y, si está disponible, DOI /
   identificador persistente -- en el que se basa tu respuesta.

3. Si el CONTEXTO no incluye fragmentos narrativos (porque el corpus de
   PDFs todavía no está indexado), dilo explícitamente y limita la
   respuesta a los metadatos del dictamen vigente (cuál es, de qué fecha,
   con qué identificador) en vez de simular que conoces el contenido
   completo del documento.

4. Si no se pudo determinar un dictamen vigente para la sustancia con los
   datos estructurados disponibles, dilo explícitamente en vez de
   responder como si lo hubiera.
"""

NODE_4_SYSTEM_PROMPT = f"{NODE_4_GROUNDING_RULES}\n{NODE_4_SAFETY_COMMUNICATION_RULES}"


@dataclass(frozen=True)
class RetrievedChunk:
    """Contrato de salida del Nodo 2 (retrieval híbrido) hacia el Nodo 4 --
    fijado en sesión 17-ago-2026 (continuación 7) ANTES de escribir el
    Nodo 2 (sigue siendo `NotImplementedError` en `hybrid_retrieval_node`),
    para que no haga falta rehacer este contrato cuando se implemente. Ver
    CLAUDE.md, "Decisiones de arquitectura ya tomadas", para el
    razonamiento completo.

    Sustituye a `list[str]` (texto plano sin metadatos) en
    `GraphState.retrieved_chunks`. El Nodo 2 SIEMPRE debe producir esta
    forma, nunca strings sueltos.

    `text` y `substance_resolution_tier` son los únicos campos que el
    Nodo 4 consume hoy (ver `_format_retrieved_chunks`). El resto
    (`chemical_name`, `dossier_uuid`, `dossier_title`, `doi`,
    `section_heading`, `page_number`) se fija ahora porque es la misma
    información que ya va a estar en los metadatos de cada chunk de
    Chroma (ver el esquema de metadatos diseñado en CLAUDE.md,
    "Hallazgos verificados") -- el Nodo 2 solo tiene que copiarlos, no
    inventar de dónde sacarlos. Sin uso todavía en el Nodo 4; añadir un
    consumidor cuando aparezca una necesidad concreta.
    """

    text: str
    substance_uuid: str
    chemical_name: str
    dossier_uuid: str
    dossier_title: str
    # 1 = sustancia con ADI propio ligado a este dossier; 2 = sustancia
    # identificada vía el mismo enlace estructural pero sin ADI (patrón
    # TiO2); 3 = identidad de sustancia inferida por coincidencia de
    # nombre en el título, sin enlace estructural -- ver
    # OpenFoodToxStore.substances_per_dossier() y CLAUDE.md.
    substance_resolution_tier: int
    doi: str | None = None
    section_heading: str | None = None
    page_number: int | None = None


class GraphState(TypedDict, total=False):
    user_query: str
    substance_name: str | None
    substance_uuid: str | None
    structured_result: OpinionReference | None
    retrieved_chunks: list[RetrievedChunk]
    vigencia_ambigua: bool
    answer: str
    citation: str | None


@dataclass
class NodeDependencies:
    store: OpenFoodToxStore
    vectorstore: object | None = None  # Chroma, se conecta en graph/build.py
    llm_client: LLMClient | None = None  # ver graph/llm_client.py -- intercambiable


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

    TODO: conectar deps.vectorstore.similarity_search(...). El resultado
    DEBE poblar `state["retrieved_chunks"]` como `list[RetrievedChunk]`
    (contrato fijado en sesión 17-ago-2026, continuación 7 -- ver
    CLAUDE.md, "Decisiones de arquitectura ya tomadas"), NUNCA como
    `list[str]` -- copiar `substance_resolution_tier` y el resto de
    campos directamente de los metadatos de cada chunk en Chroma (mismo
    esquema diseñado en CLAUDE.md, "Hallazgos verificados").
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

def _format_structured_result(result: OpinionReference | None) -> str:
    if result is None:
        return (
            "No se ha podido determinar un dictamen vigente para esta "
            "sustancia con los datos estructurados disponibles."
        )
    fecha = result.date_of_evaluation.isoformat() if result.date_of_evaluation else "no disponible"

    if result.adi_value is not None:
        adi_line = f"- ADI: {result.adi_value} {result.adi_unit or '(unidad no disponible)'}"
    else:
        # NO generalizar el motivo -- verificado sobre el corpus real
        # (sesión 17-ago-2026, ver CLAUDE.md "Hallazgos verificados"):
        # de las sustancias sin ADI numérico, la mayoría (gomas, ceras,
        # glicerol, plata, oro...) lo tienen por un motivo FAVORABLE (el
        # panel no consideró necesario un límite), y solo alguna (dióxido
        # de titanio) por una preocupación de seguridad concreta
        # (genotoxicidad). Instruir al LLM a mirar la justificación/
        # discusión ya incluidas más abajo en vez de asumir cuál aplica.
        adi_line = (
            "- ADI: no hay un valor numérico en los datos estructurados "
            "para esta sustancia. Esto puede deberse a motivos opuestos "
            "-- que el panel no considerara necesario fijar un límite "
            "numérico (frecuente en gomas, ceras y espesantes), o que no "
            "pudiera establecerse un ADI por una preocupación científica "
            "concreta (p. ej. genotoxicidad, como en el dióxido de "
            "titanio). NO asumas cuál de los dos aplica aquí -- básate "
            "solo en la justificación del ADI y la discusión narrativa de "
            "más abajo si mencionan el motivo; si ninguna de las dos lo "
            "aclara, dilo explícitamente en la respuesta en vez de "
            "especular."
        )

    if result.adi_justification:
        justification_line = (
            "- Justificación del ADI (CITA TEXTUAL de OpenFoodTox, campo "
            "JustificationAndComments -- transcríbela o resúmela como cita "
            "del dictamen, NO la reformules como si fuera tu propio "
            f"razonamiento): \"{result.adi_justification}\""
        )
    else:
        justification_line = "- Justificación del ADI: no disponible en los datos estructurados"

    if result.discussion_text is None:
        discussion_line = "- Discusión narrativa (END_SUM): no disponible en los datos estructurados"
    elif result.discussion_is_boilerplate:
        # Detectado como boilerplate (frase de apertura del mandato o
        # párrafo repetido en otros dictámenes, ver
        # DISCUSSION_BOILERPLATE_LENGTH_THRESHOLD en ingestion/openfoodtox.py)
        # -- se omite el texto para que el LLM no lo cite como si fuera
        # contenido sustantivo del dictamen.
        discussion_line = (
            "- Discusión narrativa (END_SUM): detectada como texto "
            "administrativo genérico (frase de apertura del mandato o "
            "párrafo repetido igual en otros dictámenes) -- omitida, no "
            "aporta contenido sustantivo sobre esta sustancia."
        )
    else:
        discussion_line = (
            "- Discusión narrativa (END_SUM.Discussion, CITA TEXTUAL -- "
            "NO está confirmada como razonamiento científico sustantivo, "
            "solo que no coincide con el patrón de boilerplate detectado; "
            "puede ser una descripción regulatoria genérica de la "
            "sustancia en vez de discusión real de incertidumbre. No le "
            f"atribuyas más peso del que el texto sostiene por sí mismo): "
            f"\"{result.discussion_text}\""
        )

    return (
        f"- Título: {result.title or '(sin título)'}\n"
        f"- Tipo de documento: {result.doc_type or 'desconocido'}\n"
        f"- Fecha de evaluación: {fecha}\n"
        f"- Identificador persistente (DOI): {result.doi or 'no disponible'}\n"
        f"{adi_line}\n"
        f"{justification_line}\n"
        f"{discussion_line}"
    )


def _format_retrieved_chunks(chunks: list[RetrievedChunk] | None) -> str:
    if not chunks:
        return (
            "(vacío -- el corpus de PDFs todavía no está indexado; no hay "
            "fragmentos narrativos disponibles para esta consulta)"
        )
    parts = []
    for i, chunk in enumerate(chunks):
        caveat = ""
        if chunk.substance_resolution_tier == 3:
            # Mismo patrón que discussion_line en _format_structured_result:
            # instrucción incrustada en el propio dato del prompt de
            # usuario, no una regla nueva en el system prompt -- ver
            # CLAUDE.md, "Decisiones de arquitectura ya tomadas".
            caveat = (
                " [La identificación de qué sustancia cubre este fragmento "
                "se hizo por coincidencia de nombre en el título del "
                "dictamen, no por un enlace estructural confirmado -- menos "
                "fiable que el resto del contexto. Si te apoyas en él, "
                "comunica esa incertidumbre en vez de darle la misma "
                "confianza que a los demás fragmentos.]"
            )
        parts.append(f"[fragmento {i + 1}]{caveat}\n{chunk.text}")
    return "\n\n".join(parts)


def _build_user_prompt(state: GraphState) -> str:
    query = state.get("user_query", "")
    substance = state.get("substance_name") or "(no identificada explícitamente)"
    structured = _format_structured_result(state.get("structured_result"))
    chunks = _format_retrieved_chunks(state.get("retrieved_chunks"))

    return f"""\
Pregunta del usuario: {query}

Sustancia identificada: {substance}

CONTEXTO -- dictamen vigente (fuente: OpenFoodTox, consulta determinista):
{structured}

CONTEXTO -- fragmentos narrativos recuperados del dictamen (fuente: PDFs indexados):
{chunks}

Responde a la pregunta del usuario usando solo el CONTEXTO anterior, \
siguiendo las reglas de fundamentación y de comunicación de riesgo del \
system prompt."""


def generate_answer_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Redacta la respuesta citando el número exacto de EFSA Journal / DOI.

    El system prompt es NODE_4_SYSTEM_PROMPT (reglas de fundamentación +
    NODE_4_SAFETY_COMMUNICATION_RULES, esta última fijada por diseño, ver
    CLAUDE.md). El prompt de usuario combina structured_result (Nodo 3,
    siempre disponible si hay dictamen vigente) y retrieved_chunks (Nodo 2,
    puede venir vacío mientras no exista vector store -- el prompt está
    diseñado para degradar con gracia a solo metadatos en ese caso, no
    para fallar ni para que el LLM rellene el hueco inventando contenido).
    """
    if deps.llm_client is None:
        raise ValueError("Nodo 4 requiere un llm_client configurado en NodeDependencies")

    user_prompt = _build_user_prompt(state)
    response = deps.llm_client.complete(
        system_prompt=NODE_4_SYSTEM_PROMPT,
        user_message=user_prompt,
    )

    structured = state.get("structured_result")
    citation = (structured.doi or structured.title) if structured else None

    return {**state, "answer": response.text, "citation": citation}
