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

3. Si el CONTEXTO no incluye fragmentos narrativos, dilo explícitamente
   y limita la respuesta a los metadatos del dictamen vigente (cuál es,
   de qué fecha, con qué identificador) en vez de simular que conoces
   el contenido completo del documento -- usa la explicación que te
   da el propio CONTEXTO para ese caso, no asumas ni inventes una causa
   distinta (en particular, nunca digas que el corpus de PDFs no está
   indexado -- no es cierto).

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
    # RESERVADO, SIN EFECTO TODAVÍA -- no lo trates como protección real.
    # (1) Ningún nodo ni graph/build.py lo lee -- verificado, cero
    #     consumidores (sesión 18-ago-2026). Puesto por verify_currency_node
    #     y ahí se queda.
    # (2) Ni siquiera mide lo que su nombre sugiere: hoy es literalmente
    #     `result is None` (ningún candidato 'EFSA opinion' encontrado),
    #     NO "varios candidatos con fechas próximas sin que el título
    #     aclare cuál sustituye a cuál" (la ambigüedad real que describe
    #     current_reference_value_opinion en su propio docstring, pendiente
    #     #6 de CLAUDE.md). Ese caso hoy se resuelve en silencio por
    #     MAX(fecha) sin ninguna señal hacia el llamador.
    # No lo borres sin revisar el pendiente #6 primero -- es el punto de
    # extensión ya reservado para cuando se implemente la detección real.
    vigencia_ambigua: bool
    answer: str
    citation: str | None


@dataclass
class NodeDependencies:
    store: OpenFoodToxStore
    # Chroma collection ya poblada (ver ingestion/chroma_index.py,
    # scripts/build_chroma_index.py --all) -- objeto con `.query(...)`,
    # tipado como `object` a propósito para no acoplar graph/nodes.py a
    # la API concreta de chromadb (mismo principio ya aplicado a
    # llm_client con la interfaz LLMClient).
    vectorstore: object | None = None
    # SentenceTransformer (mismo modelo usado para indexar -- ver
    # EMBEDDING_MODEL_NAME en scripts/build_chroma_index.py,
    # "all-MiniLM-L6-v2") -- necesario para embeder la pregunta del
    # usuario con el MISMO modelo que los chunks indexados, no uno
    # distinto por coincidencia. Objeto con `.encode(list[str])`.
    embedding_model: object | None = None
    llm_client: LLMClient | None = None  # ver graph/llm_client.py -- intercambiable


# --------------------------------------------------------------------- #
# Nodo 1 -- extracción de entidad
# --------------------------------------------------------------------- #

# PRIMERA VEZ que este prompt existe (sesión 18-ago-2026, continuación
# 7) -- no es una continuación de nada previo, ver CLAUDE.md/PROGRESS.md
# para la corrección de que este nodo llevaba siendo `NotImplementedError`
# desde el primer commit del repo pese a documentación previa que decía
# lo contrario.
#
# Salida en una sola línea, sin JSON/tool-calling -- LLMClient.complete()
# no expone eso (ver graph/llm_client.py), y no hace falta más
# estructura que un nombre. El nombre debe ser el CANÓNICO EN INGLÉS
# porque `OpenFoodToxStore.substance_uuid_by_name` exige coincidencia
# EXACTA contra `SUB.ChemicalName` -- limitación conocida, NO resuelta
# aquí (ver CLAUDE.md, pendiente #2): si el LLM normaliza a un nombre
# razonable pero que no coincide carácter a carácter con el de SUB
# (ej. nombres compuestos como "Tartaric acid (L(+)-)"), la resolución
# falla y `substance_uuid` queda en None -- comportamiento esperado,
# no un bug de este nodo.
NODE_1_ENTITY_EXTRACTION_PROMPT = """\
Identificas de qué aditivo alimentario habla una pregunta de usuario, \
para un sistema que después consulta una base de datos regulatoria \
(OpenFoodTox, EFSA) por el nombre químico exacto de la sustancia.

Tu única salida debe ser el NOMBRE QUÍMICO CANÓNICO EN INGLÉS de la \
sustancia, tal como aparecería en una base de datos regulatoria de \
aditivos alimentarios (ej. "Aspartame", "Titanium dioxide", "Sodium \
nitrite") -- SIN explicación, SIN puntuación adicional, SIN frases \
introductorias como "The substance is" -- solo el nombre, en una sola \
línea.

Reglas:
1. Si la pregunta menciona el nombre en español u otro idioma (ej. \
   "aspartamo"), tradúcelo a su nombre canónico en inglés.
2. Si la pregunta menciona un E-number (ej. "E 951", "E951"), \
   identifica la sustancia correspondiente y responde con su nombre \
   canónico en inglés, nunca con el E-number.
3. Si la pregunta no menciona ningún aditivo alimentario identificable, \
   responde exactamente: NONE
4. No inventes un nombre si no estás razonablemente seguro -- en ese \
   caso, responde NONE en vez de adivinar.
"""


def extract_entity_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Identifica qué aditivo pregunta el usuario -- llamada real al LLM
    (`NODE_1_ENTITY_EXTRACTION_PROMPT`) para normalizar la pregunta a un
    nombre químico canónico en inglés, más resolución determinista
    contra OpenFoodTox (`OpenFoodToxStore.substance_uuid_by_name`, la
    MISMA función ya probada en otros nodos -- coincidencia exacta, no
    fuzzy, limitación conocida sin resolver aquí).

    Si el LLM responde "NONE", o el nombre no resuelve a un UUID exacto
    en `SUB`, `substance_uuid` queda en `None` -- el resto del grafo ya
    maneja ese caso (Nodo 2: `retrieved_chunks` vacío sin llamar a
    Chroma; Nodo 3: espera un `substance_uuid` no nulo y lanza
    `ValueError` si se le llama sin él -- decidir SI llamarlo en ese
    caso es responsabilidad de la orquestación del grafo, no de este
    nodo).
    """
    if deps.llm_client is None:
        raise ValueError("Nodo 1 requiere un llm_client configurado en NodeDependencies")

    user_query = state.get("user_query", "")
    response = deps.llm_client.complete(
        system_prompt=NODE_1_ENTITY_EXTRACTION_PROMPT,
        user_message=user_query,
        max_tokens=30,  # un nombre químico, no una frase -- ver el prompt
    )

    raw_name = response.text.strip().strip('"').strip("'").rstrip(".")
    substance_name = raw_name if raw_name and raw_name.upper() != "NONE" else None

    substance_uuid = deps.store.substance_uuid_by_name(substance_name) if substance_name else None

    return {**state, "substance_name": substance_name, "substance_uuid": substance_uuid}


# --------------------------------------------------------------------- #
# Nodo 2 -- retrieval híbrido
# --------------------------------------------------------------------- #

DEFAULT_RETRIEVAL_K = 5
# Extremo superior del rango k=3-5 asumido en el cálculo de presupuesto
# de contexto del Nodo 4 (ver PROGRESS.md, sesión 18-ago-2026: ~150-180
# tokens/chunk medidos sobre el corpus real, k=3-5 -> ~1.250-2.000
# tokens de entrada, coste recalculado ~$0.0005-0.0014/consulta,
# confirmado del mismo orden de magnitud que la estimación previa sin
# retrieval -- ver CLAUDE.md, "Decisiones de arquitectura ya tomadas").
# Se fija en 5 (no 3) porque el presupuesto seguía siendo razonable
# incluso en el extremo superior, y más contexto real reduce el riesgo
# de que el Nodo 4 tenga que degradar a solo metadatos por falta de
# fragmentos relevantes.


def hybrid_retrieval_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Búsqueda semántica en Chroma, filtrada por `substance_uuid`, con
    la pregunta del usuario como query.

    Solo usa `substance_uuid` (ya resuelto por el Nodo 1) como filtro --
    es el único campo por el que el esquema de metadatos de Chroma
    permite un filtro exacto y fiable (ver CLAUDE.md, "Hallazgos
    verificados", ESQUEMA FINAL: no hay `e_number` en los metadatos, y
    `substance_name` es texto libre del usuario, no una clave de
    filtrado). Si el Nodo 1 no resolvió un UUID (`state["substance_uuid"]`
    es `None` -- puede que sí haya `substance_name`, ej. el nombre tal
    como lo escribió el usuario, pero sin UUID no hay filtro fiable
    posible), NO se llama a Chroma en absoluto -- una búsqueda sin
    filtro de sustancia devolvería fragmentos de CUALQUIER dictamen del
    corpus, mezclando contexto no relacionado con la pregunta. Se deja
    `retrieved_chunks` vacío y el Nodo 4 ya degrada con gracia a ese
    caso (`_format_retrieved_chunks`).

    `substance_resolution_tier` (y el resto de campos de
    `RetrievedChunk`) se copian TAL CUAL de los metadatos ya escritos
    en el chunk al indexar (ver `ingestion/chroma_index.py`) -- no se
    re-derivan aquí. La resolución de tier ocurrió una sola vez, al
    construir el índice.
    """
    substance_uuid = state.get("substance_uuid")
    if not substance_uuid:
        return {**state, "retrieved_chunks": []}

    if deps.vectorstore is None or deps.embedding_model is None:
        raise ValueError("Nodo 2 requiere vectorstore y embedding_model configurados en NodeDependencies")

    query_text = state.get("user_query", "")
    query_embedding = deps.embedding_model.encode([query_text])[0]
    query_embedding_list = (
        query_embedding.tolist() if hasattr(query_embedding, "tolist") else list(query_embedding)
    )

    result = deps.vectorstore.query(
        query_embeddings=[query_embedding_list],
        where={"substance_uuid": substance_uuid},
        n_results=DEFAULT_RETRIEVAL_K,
    )

    documents = result.get("documents") or [[]]
    metadatas = result.get("metadatas") or [[]]

    retrieved_chunks = [
        RetrievedChunk(
            text=text,
            substance_uuid=meta["substance_uuid"],
            chemical_name=meta["chemical_name"],
            dossier_uuid=meta["dossier_uuid"],
            dossier_title=meta["dossier_title"],
            substance_resolution_tier=meta["substance_resolution_tier"],
            doi=meta.get("doi"),
            section_heading=meta.get("section_heading"),
            page_number=meta.get("page_number"),
        )
        for text, meta in zip(documents[0], metadatas[0])
    ]

    return {**state, "retrieved_chunks": retrieved_chunks}


# --------------------------------------------------------------------- #
# Nodo 3 -- verificación de vigencia
# --------------------------------------------------------------------- #

def verify_currency_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Determinista (ver ingestion/openfoodtox.py::
    current_reference_value_opinion, verificado con aspartamo) --
    MAX(fecha) entre los candidatos 'EFSA opinion' que pasan los
    filtros de dominio/regulación, sin ningún chequeo de ambigüedad.

    NO hay todavía ningún fallback a LLM ni detección real de
    ambigüedad (varias 'EFSA opinion' con fechas muy próximas, título
    no concluyente) -- pendiente #6 de CLAUDE.md, diagnóstico de
    prevalencia en curso (sesión 18-ago-2026), sin implementar. Si
    `current_reference_value_opinion` encuentra 2+ candidatos así, hoy
    devuelve el de fecha más reciente en silencio, sin ninguna señal
    hacia el llamador -- ver `vigencia_ambigua` más abajo, que NO cubre
    este caso pese al nombre.
    """
    substance_uuid = state.get("substance_uuid")
    if not substance_uuid:
        raise ValueError("Nodo 3 requiere substance_uuid ya resuelto por el Nodo 1")

    result = deps.store.current_reference_value_opinion(substance_uuid)
    new_state: GraphState = {**state, "structured_result": result}

    # RESERVADO, SIN EFECTO -- ver el comentario largo junto al campo en
    # GraphState. Esto es "no se encontró ningún candidato", NO "había
    # varios candidatos y no estaba claro cuál elegir" -- son casos
    # distintos, y este campo solo cubre el primero. Nadie lo lee aguas
    # abajo todavía.
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


def _format_retrieved_chunks(
    chunks: list[RetrievedChunk] | None, structured_result: OpinionReference | None = None
) -> str:
    if not chunks:
        if structured_result is None:
            # Caso diagnosticado con datos reales (sesión 19-ago-2026,
            # caso tocoferol -- ver CLAUDE.md, pendiente sobre nombre
            # genérico del LLM vs. variantes con prefijo/sufijo en
            # `SUB.ChemicalName`): cuando NINGUNO de los dos nodos
            # tiene nada, la causa real casi siempre es que el Nodo 1
            # no resolvió `substance_uuid` -- NUNCA que el corpus no
            # esté indexado (67.827 chunks reales, verificado). Afirmar
            # "el corpus no está indexado" es una causa falsa y
            # engañosa -- no la repitas aunque parezca inofensiva.
            return (
                "(vacío -- no se ha podido resolver de forma exacta la "
                "sustancia mencionada en la pregunta; no hay fragmentos "
                "narrativos disponibles para esta consulta)"
            )
        # `structured_result` SÍ existe pero no hay chunks -- causa
        # distinta (el dictamen vigente se resolvió por la cadena de
        # OpenFoodTox, pero esta sustancia concreta no tiene fragmentos
        # indexados en Chroma) -- no reutilices el mensaje de arriba,
        # sería igual de engañoso en la dirección contraria.
        return (
            "(vacío -- no se han encontrado fragmentos narrativos "
            "indexados para esta sustancia concreta, aunque sí se "
            "resolvió el dictamen vigente por datos estructurados)"
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
    structured_result = state.get("structured_result")
    structured = _format_structured_result(structured_result)
    chunks = _format_retrieved_chunks(state.get("retrieved_chunks"), structured_result)

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


NODE_4_MAX_TOKENS = 2000
# Subido de 800 a 2000 (sesión 18-ago-2026) -- verificado con una
# respuesta real truncada (Shellac, tier 3): finish_reason == 'length',
# output_tokens == 800 exacto (el tope), cortada a mitad de frase. Ya no
# hay overhead de reasoning_content ("thinking" desactivado, ver
# DeepSeekClient) -- este es texto de salida real, así que subir el tope
# es coste directo, no oculto: ver CLAUDE.md, "Decisiones de arquitectura
# ya tomadas", para el recálculo de coste/consulta con este valor.
NODE_4_RETRY_MAX_TOKENS = 3500
# Presupuesto del reintento -- más margen que el default porque solo se
# gasta en el caso raro (la primera pasada ya se truncó), no en cada
# consulta.


def generate_answer_node(state: GraphState, deps: NodeDependencies) -> GraphState:
    """Redacta la respuesta citando el número exacto de EFSA Journal / DOI.

    El system prompt es NODE_4_SYSTEM_PROMPT (reglas de fundamentación +
    NODE_4_SAFETY_COMMUNICATION_RULES, esta última fijada por diseño, ver
    CLAUDE.md). El prompt de usuario combina structured_result (Nodo 3,
    siempre disponible si hay dictamen vigente) y retrieved_chunks (Nodo 2,
    puede venir vacío mientras no exista vector store -- el prompt está
    diseñado para degradar con gracia a solo metadatos en ese caso, no
    para fallar ni para que el LLM rellene el hueco inventando contenido).

    Comprobación de truncamiento (sesión 18-ago-2026, ver CLAUDE.md):
    si `finish_reason == 'length'`, la respuesta NUNCA se devuelve tal
    cual -- se reintenta UNA vez con más presupuesto
    (`NODE_4_RETRY_MAX_TOKENS`), y si sigue truncada incluso así, se le
    añade una nota visible al final en vez de dejarla cortada a mitad de
    frase sin ningún aviso (que es exactamente lo que pasaba antes de
    esta sesión, descubierto con una respuesta real sobre Shellac).
    """
    if deps.llm_client is None:
        raise ValueError("Nodo 4 requiere un llm_client configurado en NodeDependencies")

    user_prompt = _build_user_prompt(state)
    response = deps.llm_client.complete(
        system_prompt=NODE_4_SYSTEM_PROMPT,
        user_message=user_prompt,
        max_tokens=NODE_4_MAX_TOKENS,
    )

    if response.finish_reason == "length":
        response = deps.llm_client.complete(
            system_prompt=NODE_4_SYSTEM_PROMPT,
            user_message=user_prompt,
            max_tokens=NODE_4_RETRY_MAX_TOKENS,
        )

    answer_text = response.text
    if response.finish_reason == "length":
        answer_text += "\n\n[respuesta incompleta por límite de longitud]"

    structured = state.get("structured_result")
    citation = (structured.doi or structured.title) if structured else None

    return {**state, "answer": answer_text, "citation": citation}
