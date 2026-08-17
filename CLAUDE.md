# CLAUDE.md — efsa-additives-rag

Este documento existe para que no repitas trabajo de diseño ya hecho, ni
reviertas decisiones ya tomadas con datos reales. Léelo entero antes de
tocar código. Si algo aquí te parece mejorable, dilo y discútelo — no lo
cambies en silencio.

## Qué es este proyecto

RAG assistant sobre dictámenes de reevaluación de aditivos alimentarios
(EFSA, Reglamento UE 257/2010). Proyecto de portfolio del autor (química/
ciencia de alimentos, 6 años de investigación, patente, 30+ publicaciones,
en transición a Data Science/AI). La razón de ser del proyecto es la
diferenciación de dominio, no la ejecución técnica en sí — no lo conviertas
en un ejercicio genérico de "monté un RAG con LangGraph".

Documentación completa (objetivo, audiencia, stack, roadmap): `docs/efsa-rag-proyecto.html`.
Ábrelo y léelo también antes de empezar.

## Cómo trabajar en este repo

- **Verifica contra datos reales antes de implementar, no asumas el esquema.**
  Varias decisiones de este proyecto cambiaron cuando se inspeccionó el xlsx
  real de OpenFoodTox en vez de fiarse de la documentación pública (ver
  "Hallazgos verificados" abajo). Si vas a tocar `ingestion/openfoodtox.py`
  o el esquema de datos, inspecciona las hojas reales primero.
- **No metas scope creep.** Ya se descartó explícitamente: integrar PubMed
  (ver "Restricciones no negociables"), refresco en tiempo real del corpus,
  y ampliar el alcance más allá de aditivos en reevaluación bajo 257/2010.
  Si crees que algo debería añadirse, pregúntalo, no lo añadas.
- **Documenta las limitaciones, no las escondas.** El README y
  `docs/.../LIMITATIONS.md` existen para eso. Si implementas algo con una
  limitación conocida (ej. el heurístico del Nodo 3 no cubre todos los
  casos borde), anótalo ahí, no lo dejes como sorpresa.
- **Mantén actualizado `PROGRESS.md`** (en la raíz del repo) según avances.
  Ver instrucciones al final de este documento.
- **Cualquier script que llame al LLM en bucle o sobre un lote de elementos**
  (ej. iterar los 162 dictámenes, reintentos, pruebas de prompt) DEBE
  incluir un límite explícito de iteraciones y un modo `--dry-run` que
  muestre qué se va a llamar sin gastar tokens reales. La key de
  desarrollo tiene saldo prepago limitado (unos pocos euros) sin ningún
  candado automático como el que sí protege la demo desplegada
  (`ui/app.py` → `check_and_register_query`) -- un bucle mal acotado
  aquí sí puede agotar el saldo real. No lo des por sobreentendido en
  cada prompt: si vas a escribir un script así, añade el límite y el
  dry-run sin que haga falta que se te pida explícitamente.

## Restricciones no negociables

1. **Comunicación de riesgo del Nodo 4** (`graph/nodes.py` →
   `NODE_4_SAFETY_COMMUNICATION_RULES`): el ADI/TDI es un margen de
   seguridad (~×100 sobre el NOAEL), nunca un umbral de toxicidad.
   PROHIBIDO redactar "si se supera el ADI, se produce/puede producir
   [efecto]". Esta restricción va en el system prompt, no se deja a
   criterio del LLM en tiempo de ejecución. No la relajes ni la
   reformules sin discutirlo antes.

2. **No integrar PubMed ni ninguna fuente de literatura primaria** como
   contraste de las conclusiones EFSA. Se evaluó explícitamente y se
   descartó: mezclar un estudio individual con una conclusión regulatoria
   consensuada replica la estructura retórica de la desinformación
   alimentaria ("aunque el regulador dice X, hay estudios que dicen Y"),
   incluso si el LLM no falsea ningún dato. Si en el futuro se retoma,
   solo con literatura posterior a la fecha del dictamen vigente,
   etiquetada explícitamente como "no evaluada aún por el panel", nunca
   contrapuesta a la conclusión EFSA en el mismo párrafo.

3. **Esta es una herramienta de exploración de literatura regulatoria, no
   de asesoramiento regulatorio ni médico.** El sistema nunca debe emitir
   juicios de "seguro"/"no seguro" — solo citar lo que dice el dictamen.

## Hallazgos verificados (no los redescubras ni los contradigas sin motivo)

- **Filtro de corpus (cifra corregida dos veces, ver bullets de dominio
  mixto y de cierre del Grupo A más abajo):** `Domain.FoodDomain ==
  'food additives'` + `'re-evaluation'` en
  `LiteratureReference.EFSAOutputTitle` (case-insensitive) O uno de
  `ADDITIONAL_REEVAL_TITLE_PATTERNS`/`SAFETY_ASSESSMENT_FOOD_ADDITIVE_PATTERN`
  (`"extension of use"`, `"statement on"`, `"reconsideration of the
  ADI"`, `"safety assessment... as a food additive"` -- verificados uno
  por uno contra el dataset completo en sesión 17-ago-2026, ver bullet
  de cierre del Grupo A), Y NOT `Domain.Regulation` contiene
  `ANIMAL_FEED_REGULATION_MARKER` (`'1831/2003'`, pienso animal), **más
  el rescate de dictámenes reales mal etiquetados con otro dominio**
  (`_is_mistagged_food_additive_reevaluation` en
  `ingestion/openfoodtox.py`), da **162 dictámenes únicos** (tras
  deduplicar por título/DOI — una fila de `DOSSIER` por sustancia
  cubierta, no por dictamen). Progresión de la cifra, no repitas ninguna
  de las anteriores como si fuera la actual: 118 (diseño original, sin
  rescate de dominio) → 136 (sesión 16-ago-2026, con rescate de
  dominio) → **162 (sesión 17-ago-2026, con el cierre del Grupo A)**.
  Filtrar por `Domain.Regulation == '257/2010'` da solo 62 (infravalora
  el corpus real: la mayoría de reevaluaciones están etiquetadas con el
  reglamento marco 1333/2008, no con 257/2010). **No uses el campo de
  regulación como filtro principal** (sí como exclusión puntual de
  pienso animal, ver arriba).
- **Cobertura del corpus NO está validada al 100%** contra una fuente
  oficial EFSA (no existe una tabla pública descargable para ese cruce).
  El programa sigue activo en 2025-2026 (follow-ups de plata E174,
  Patent Blue V E131, almidones modificados). Trátalo como corpus de
  trabajo razonable, no como lista cerrada.
- **Cadena de joins para vigencia (Nodo 3):**
  `FLEX_SUM.ToxRefValues` (Parent UUID = sustancia) → `DOSSIER_DOCS`
  (DOCUMENT UUID = Document UUID del ToxRefValues, DOCUMENT TYPE
  'FLEXIBLE_SUMMARY'/'ToxRefValues') → `DOSSIER` (DOSSIER UUID) → fecha/
  título/DOI. Filtrar `LiteratureReference.Type == 'EFSA opinion'`
  (excluir 'EFSA statement') antes de tomar `MAX(fecha)`. Verificado con
  aspartamo (E 951): 5 candidatos (2006, 2009×2, 2011 statement, 2013),
  resultado correcto = 2013-11-28. `Parent UUID` en la hoja `DOSSIER` está
  vacío en el 100% de las 11.613 filas — no uses esa hoja/campo para
  vigencia, la cadena correcta pasa por `FLEX_SUM.ToxRefValues`.
- **`current_reference_value_opinion` necesita filtrar también por dominio,
  no solo por `Type == 'EFSA opinion'`** (bug encontrado y corregido en
  sesión 16-ago-2026, `ingestion/openfoodtox.py`). Sin este filtro,
  `MAX(fecha)` puede elegir un dictamen de OTRO programa regulatorio
  (pienso animal FEEDAP, aromas/flavourings, contaminantes de procesado)
  para la misma sustancia química -- verificado con propil galato (E
  310): compite un dictamen de aditivo alimentario (2014-04-01,
  `Domain.FoodDomain == 'food additives'`) contra uno de seguridad como
  aditivo de pienso animal (2020-03-17, `Domain.FoodDomain ==
  'technological additives'`), y sin filtro gana el segundo. **No es un
  caso aislado: 29 de 102 sustancias del corpus de reevaluación (28,4%)
  tienen candidatos de dominio mixto.**
  - Filtro correcto: `Domain.FoodDomain == FOOD_DOMAIN_VALUE` **O**
    (título contiene `FOOD_ADDITIVE_TITLE_PHRASE` ("food additive") Y
    `REEVAL_TITLE_MARKER` ("re-evaluation")) -- MISMA CLASE DE RIESGO que
    el filtro de corpus de arriba, aproximación verificada contra los
    casos conocidos, no garantía estructural.
  - **El filtro de dominio a secas (sin la rama de título) NO basta**:
    de las 29 sustancias afectadas, 24 son genuinamente de otro programa
    y el filtro de dominio solo ya las excluye correctamente -- pero 5
    (plata E 174, sílice E 551, goma garrofín E 410, goma xantana E 415,
    ésteres cítricos de mono/diglicéridos E 472c) son dictámenes de
    aditivo alimentario reales y vigentes, mal etiquetados
    `Domain.FoodDomain == 'other:'` en vez de `'food additives'` --
    filtrar solo por dominio los descartaría y volvería a un dictamen
    antiguo ya superado (regresión, no fix). El caso de plata (E 174,
    follow-up 2025-03-06) ya estaba mencionado arriba como programa
    activo -- este es el mecanismo concreto por el que se perdería si no
    se maneja con cuidado.
  - **Tampoco basta con exigir solo la frase "food additive" en el
    título, sin exigir también "re-evaluation"**: 1.360 dictámenes de
    Flavouring Group Evaluation (dominio `flavourings`) también
    contienen "food additive" en el título, porque el panel que los
    evalúa se llama literalmente "Panel on Food Additives, Flavourings,
    Processing Aids and Materials in Contact with Food (AFC)" -- la
    frase aparece por el nombre del comité, no porque el dictamen sea
    una reevaluación de aditivo. Verificado que exigir ambas frases a la
    vez no captura ninguno de esos falsos positivos.
  - Tests de regresión en `tests/test_openfoodtox_joins.py`: propil
    galato (bloquea que vuelva a colarse un candidato de dominio ajeno)
    y plata (bloquea que el fix se vuelva demasiado estricto y excluya
    un follow-up real mal etiquetado).
  - **Resuelto en la misma sesión (16-ago-2026):** el mismo problema de
    fondo (dictámenes reales etiquetados `Domain.FoodDomain == 'other:'`)
    afectaba también a `reevaluation_dossiers()`/`unique_reevaluation_opinions()`
    -- el filtro del CORPUS, no solo la elección de "vigente" por
    sustancia. Se extrajo la lógica de rescate a una función compartida
    (`_is_mistagged_food_additive_reevaluation`, usada por ambas
    funciones) para no repetir la divergencia que ya se había dado una
    vez. **18 dictámenes de reevaluación de aditivos alimentarios
    reales** (acesulfamo K E950, sacarina E954, eritritol E968, neotamo
    E961, plata E174 y 13 más) estaban excluidos del corpus por este
    motivo -- **corpus corregido: 118 → 136**, validado contra el xlsx
    completo sin falsos positivos de otros dominios (verificado
    especialmente contra los 1.360 dictámenes de `flavourings` que ya
    habían dado problemas antes). Cifra actualizada en todo el
    documento, en `PROGRESS.md`, `docs/efsa-rag-proyecto.html` y el
    umbral del test de regresión del corpus.
  - **IMPORTANTE -- unificar NO significa exigir el mismo predicado
    completo en los dos sitios.** Se probó exigir también
    `REEVAL_TITLE_MARKER` en la rama de dominio correcto de
    `current_reference_value_opinion` (para unificarla del todo con
    `reevaluation_dossiers()`) y se descartó: rompía el caso del dióxido
    de titanio (E 171) -- el dictamen que de hecho concluyó que ya no es
    seguro como aditivo (2021-03-25, "Safety assessment of titanium
    dioxide (E171) as a food additive", dominio correcto) no contiene la
    palabra "re-evaluation", así que exigirla habría hecho perder ese
    dictamen a favor de uno de 2016 ya superado. Lo compartido entre las
    dos funciones es solo el rescate de mal-etiquetado, no el predicado
    completo -- ver el comentario largo en `ingestion/openfoodtox.py`
    antes de intentar unificar más.
- **Alcance de la divergencia TiO2 (investigado sesión 17-ago-2026):**
  el caso E171 (dictamen vigente sin `REEVAL_TITLE_MARKER` en el
  título, por tanto excluido de `reevaluation_dossiers()`) no es
  aislado. De las 233 sustancias del corpus con al menos un registro de
  ADI/TDI ligado a un dossier de `reevaluation_dossiers()`, **7 (3,0%)
  tienen esta misma divergencia** entre lo que devuelve
  `current_reference_value_opinion()` y el conjunto capturado por
  `reevaluation_dossiers()`. Se dividen en dos grupos de naturaleza muy
  distinta -- no tratarlos como el mismo problema:
  - **Grupo A -- solo cobertura del corpus, el dato de ADI/vigencia
    sigue siendo correcto (6 sustancias):** titanio E171 (ya conocido),
    propionato sódico E281, rojo remolacha E162, beta-caroteno E160a,
    beta-apo-8'-carotenal E160e, Allura Red AC E129. En los 6, la fila
    ganadora tiene `Domain.FoodDomain == 'food additives'` con
    regulación alimentaria real (178/2002, 1331/2008, 1333/2008,
    257/2010) -- el dato que devuelve `current_reference_value_opinion`
    es correcto, solo faltaba el patrón de título esperado
    (`REEVAL_TITLE_MARKER`) para que `reevaluation_dossiers()` lo
    capturase como parte del corpus. Patrones de título vistos:
    3× "Safety of the [proposed] extension of use of...", 1×
    "Statement on...", 1× "Scientific Opinion on the reconsideration of
    the ADI...", 1× "Safety assessment of... as a food additive" (E171).
    **"Follow-up" no aparece en ningún caso real** -- no construir una
    regla para ese patrón sin evidencia nueva.
    - **FIX IMPLEMENTADO -- Grupo A cerrado (sesión 17-ago-2026):**
      cada uno de los 4 patrones se probó individualmente contra las
      11.613 filas completas de `DOSSIER` (cualquier dominio) antes de
      aceptarlo, no solo dentro de `food additives`:
      - `"extension of use"`: 42 coincidencias en todo el dataset (25
        en `food additives`, 15 en `other:`, 1 `nutritional additives`,
        1 `zootechnical additives`). Sin acotar, se cuela en dominios
        ajenos -- de las 17 coincidencias fuera de `food additives`, 11
        son claramente ajenas al programa de reevaluación: 9 son
        extensiones de uso de **novel foods** bajo el Reglamento (UE)
        2015/2283 (2'-fucosil-lactosa, semillas de chía, ésteres de
        fitosterol...) y 2 son solicitudes de **pienso animal**
        (lechones, salmónidos); las 2 restantes ("Re-evaluation of
        pullulan..."/"Re-evaluation of shellac...") sí son
        reevaluaciones reales de aditivo alimentario, solo que
        etiquetadas con otro dominio -- ya cubiertas por el rescate de
        mal-etiquetado existente (`_is_mistagged_food_additive_reevaluation`,
        contienen ambas frases "food additive" y "re-evaluation"), no
        una fuga nueva de este patrón. Acotado con `Domain.FoodDomain
        == 'food additives'` (ya prerrequisito de la rama) Y NOT
        `Domain.Regulation` contiene `'1831/2003'`: 25 supervivientes,
        11 no capturados ya por `'re-evaluation'` -- sodio propionato,
        rojo remolacha, beta-caroteno, acesulfamo K, sucralosa,
        taumatina, eritritol, esteviol glucósidos, etil lauroil
        arginato, extracto de romero, ésteres de sacarosa. Todos con
        E-number citado excepto el de ésteres de sacarosa
        ("...extension of use of sucrose esters of fatty acids in
        flavourings") -- caso límite, mencionado explícitamente porque
        su frase final ("in flavourings") sugiere una aplicación de
        aromatizante, no de aditivo puro; se acepta porque
        `Domain.FoodDomain`/`Domain.Regulation` (178/2002, no de
        pienso) siguen siendo correctos, mismo criterio de seguridad
        que el resto -- pero es la excepción a vigilar si en el futuro
        aparece un falso positivo real de esta rama.
      - `"statement on"`: 62-75 coincidencias en todo el dataset según
        se ancle al inicio del título o no (mismo resultado dentro de
        `food additives` en ambos casos) -- de largo el patrón más
        amplio, con fugas reales a pesticidas (15-18), contaminantes de
        procesado, melamina, materiales en contacto con alimentos y
        `flavourings` si no se acota. Acotado igual que arriba: 20
        supervivientes, todos sobre aditivos alimentarios concretos ya
        dentro del programa (eritritol, licopeno, TBHQ E319, luteína,
        beta-caroteno, lignosulfonato cálcico, ésteres de yodo,
        sucralosa, edulcorantes artificiales, nitritos, Allura Red AC)
        -- cero fuera de tema tras la exclusión.
      - `"reconsideration of the ADI"`: 1 coincidencia en TODO el
        dataset (beta-apo-8'-carotenal) -- el patrón más estrecho
        posible, sin ningún riesgo de falso positivo.
      - `"safety assessment...as a food additive"` (regex con comodín
        entre las dos frases): 3 filas en todo el dataset (2 títulos
        únicos), ambas en `food additives` -- TiO2 (ya conocido) y
        "Safety assessment of medium viscosity white mineral oils...
        as a food additive" (nuevo, mismo patrón exacto).
      - Los 4 patrones combinados con `Domain.FoodDomain ==
        FOOD_DOMAIN_VALUE` Y NOT `Domain.Regulation` contiene
        `ANIMAL_FEED_REGULATION_MARKER` -- verificado sin overlap con
        las filas ya capturadas por `REEVAL_TITLE_MARKER`/el rescate de
        dominio (0 de esas filas tenía regulación de pienso animal), la
        exclusión no cambia ningún resultado previo, solo cierra la
        misma clase de fuga que el fix del Grupo B.
      - Implementado en `ingestion/openfoodtox.py`:
        `ADDITIONAL_REEVAL_TITLE_PATTERNS` (los 3 patrones de texto
        literal) + `SAFETY_ASSESSMENT_FOOD_ADDITIVE_PATTERN` (el único
        que necesita regex, por el comodín), usados en
        `reevaluation_dossiers()`.
      - **Corpus recalculado: 136 → 162 dictámenes únicos**
        (`unique_reevaluation_opinions()`). Verificado que los 6
        dictámenes vigentes del Grupo A quedan ahora dentro del corpus
        (test `test_group_a_substances_current_opinion_is_in_reevaluation_corpus`
        en `tests/test_openfoodtox_joins.py`, 9/9 tests en verde). Cifra
        actualizada en `PROGRESS.md`, `docs/efsa-rag-proyecto.html` y el
        umbral del test de tamaño del corpus (subido de 130 a 150).
      - Estadísticas de cobertura de `END_SUM.Discussion.Discussion`
        recalculadas sobre el corpus de 162 en sesión posterior el mismo
        día -- ver "Estado del código" más abajo: 25,3% (41/162), bajó
        desde 29,4%/136 porque 25 de los 26 dictámenes nuevos del cierre
        del Grupo A aportan solo boilerplate.
    - **Verificación del caso límite "sucrose esters...in
      flavourings" (segunda mitad de la sesión 17-ago-2026, a petición
      del usuario antes de dar el Grupo A por cerrado):** VERDADERO
      POSITIVO, no una fuga del dominio `flavourings`. Confirmado:
      `Domain.FoodDomain == 'food additives'` (fila única, sin
      duplicado en `flavourings`), `Domain.ExpertGroup == 'EFSA ANS'`
      (el panel de aditivos, no CEF/flavourings), regulación real
      (178/2002), sustancia confirmada "Sucrose esters of fatty acids"
      (E473) vía `FLEX_SUM.ToxRefValues.Parent UUID` → `SUB`. La
      palabra "flavourings" describe el USO propuesto (extender el uso
      a preparados aromatizantes), no el panel evaluador ni el
      dominio. No se excluye.
    - **Límite estructural del enfoque de patrones de título,
      confirmado empíricamente (mismo verificación):** al trazar E473
      se encontró que sus 4 dictámenes reales (2004/2010/2012/2017) no
      contienen "re-evaluation" en ningún título, y el vigente real
      (2017, "Refined exposure assessment...") no coincide con ningún
      patrón aceptado ("refined", no "safety", assessment).
      Generalizando la comprobación a todas las sustancias del corpus,
      **6 sustancias tienen algún dossier en el corpus de 162 pero su
      dictamen REALMENTE vigente (`current_reference_value_opinion`)
      no está capturado**: Sucrose esters of fatty acids E473 (2017,
      "refined" no "safety" assessment), **Sunset Yellow FCF E110**
      (2014, "Reconsideration of the **temporary** ADI..." -- la
      palabra "temporary" insertada rompe el substring
      `"reconsideration of the adi"`, regresión parcial sobre el
      mismo caso arreglado por el fix del Grupo B de esta sesión),
      Rosemary extract liquid E392 (2018, mismo problema que E473),
      Steviol glycosides E960 (2020, "amendment of the
      specifications...", frase distinta), Calcium lignosulphonate
      40-65 (2010, "carrier for vitamins and carotenoids", frase
      distinta), Lycopene (2008, "food colour", frase distinta). **No
      se ha ampliado ningún patrón más para cubrir estos 6** -- decisión
      explícita del usuario, ver el diagnóstico del híbrido justo
      abajo.
    - **Diagnóstico del enfoque híbrido (sustancia-primero, sin patrón
      de título) -- probado, NO adoptado, ningún cambio de código:**
      se probó redefinir el corpus como "un documento por sustancia,
      el vigente según `current_reference_value_opinion` (dominio
      `food additives` + NOT regulación pienso animal, sin exigir
      patrón de título)" en vez de filtrar `DOSSIER` por título.
      Resultado sobre las 4.476 sustancias con algún registro ADI/TDI
      en todo el dataset: 317 resuelven un vigente (186 documentos
      únicos por título) -- muy por encima de las 162 reales del
      programa. Comparado con el corpus de 162 por título: 130 en
      común, 56 SOLO en el híbrido, 32 SOLO en el corpus de 162 (el
      híbrido los pierde). De las 56 nuevas, solo 6 son los casos
      genuinos de arriba -- las ~50 restantes son dictámenes de
      PRIMERA autorización o cambio de especificación que NUNCA
      formaron parte del programa de reevaluación (Advantame, Monk
      fruit extract, buffered vinegar, green tea catechins, Ephedra,
      decenas de "Opinion... on a request from the Commission related
      to..." del panel AFC antiguo -- primeras autorizaciones bajo
      directivas pre-1333/2008). De las 32 que el híbrido pierde, la
      mayoría son reevaluaciones reales y centrales del programa --
      goma acacia E414, lecitinas E322, goma garrofín E410, PGPR E476,
      propano-1,2-diol E1520, sacarina E954, goma laca E904, sílice
      E551, **el "Re-evaluation of titanium dioxide (E171)" de 2016
      original**, goma xantana E415, Allura Red AC E129, Indigo
      Carmine E132, **el "re-evaluation" de 2009 original de Sunset
      Yellow FCF**, rojo remolacha E162, beta-apo-8'-carotenal E160e,
      luteína E161b, plata E174 -- el híbrido, al quedarse con un solo
      documento por sustancia (el más reciente), pierde
      estructuralmente los documentos de reevaluación históricos en
      cuanto existe un documento más reciente sin "re-evaluation" para
      esa misma sustancia. **Conclusión: el híbrido tal como está
      especificado NO es un sustituto viable del filtro por patrón de
      título** -- cambia un hueco pequeño y bien caracterizado (6
      sustancias) por una regresión mayor (pierde 32 documentos
      centrales, gana ~50 fuera de alcance).
    - **Desglose de los 32 documentos que el híbrido puro pierde
      (investigado antes de decidir, misma sesión):** para cada uno se
      comprobó si la sustancia ligada reaparece en el híbrido con OTRO
      documento (reemplazo correcto) o desaparece del todo (pérdida
      real). **26 son reemplazos correctos** (la sustancia SÍ aparece
      en el híbrido, con un documento distinto y más reciente -- p.ej.
      TiO2 2016→2021). **1 mixto**: "Statement on nitrites in meat
      products" cubre 2 sustancias -- Nitrites se reemplaza bien (→
      re-evaluation 2017 de E249/E250), Nitrate no resuelve nada porque
      su único candidato en dominio `food additives` es un `EFSA
      statement`, excluido por diseño de `VALID_OPINION_TYPES`. **1
      pérdida real**: "Iodized ethyl esters of poppy seed oil" -- la
      sustancia solo tiene un `EFSA statement`, nunca un `EFSA opinion`
      formal, así que `current_reference_value_opinion` no puede
      producir un vigente (comportamiento correcto, no un defecto del
      híbrido). **4 sin sustancia ligada vía toxref** (saccharin,
      shellac, statement de sucralosa/Ramazzini, statement de
      "artificial sweeteners") -- no clasificables por este método, sin
      registro ADI/TDI que los enlace. Ninguno de estos 2+4 casos
      revela un defecto del híbrido en sí -- son diferencias de diseño
      ya existentes entre `reevaluation_dossiers()` (no filtra por
      `Type`) y `current_reference_value_opinion` (sí exige `Type ==
      'EFSA opinion'`, por diseño, ver más abajo).
    - **Híbrido ESTRECHO (restringido a sustancias ya confirmadas en el
      corpus de 162, no a las 4.476 del dataset completo) -- probado y
      SÍ adoptado:** en vez de enumerar sustancias por dominio+regulación
      sobre todo el dataset, se enumeran solo las que ya están ligadas
      (vía `FLEX_SUM.ToxRefValues`) a algún dossier ya capturado por
      `reevaluation_dossiers()` -- 246 sustancias. Resolviendo su
      vigente para cada una: **136 documentos únicos, 130 en común con
      el corpus de 162, exactamente 6 nuevos genuinos (los mismos 6 de
      la tabla de arriba) y CERO sustancias fuera de alcance** -- por
      construcción, el universo de entrada ya viene acotado por el
      corpus existente, es estructuralmente imposible que aparezca una
      sustancia nueva.
    - **Corrección importante sobre cómo combinar el híbrido estrecho
      con el corpus (encontrada tras un primer intento equivocado, ver
      `PROGRESS.md`): NO es una unión de conjuntos.** De las 6
      sustancias del híbrido estrecho, TODAS ya tenían un documento
      distinto en el corpus de 162 para esa misma sustancia (Sunset
      Yellow FCF: 2009 "re-evaluation..."; sucrose esters E473: 2010
      "...in flavourings"; rosemary extract: "...in fat-based
      spreads"; steviol glycosides: "...extension of use..."; calcium
      lignosulphonate: "Statement on the safety..."; lycopene:
      "Statement on the divergence..."). Unir sin más habría dado 168
      (6 de más, contando dos veces la misma sustancia). La cifra
      correcta es **162 -- 6 documentos sustituidos, mismo total**
      (verificado que cada sustitución es 1:1, ningún dossier viejo
      compartido con otra sustancia, así que quitarlo no pierde
      cobertura colateral).
    - **FIX IMPLEMENTADO -- `OpenFoodToxStore.current_reevaluation_corpus()`
      en `ingestion/openfoodtox.py`:** nuevo método, corpus final
      recomendado para la descarga de PDFs (pendiente #4 en "Estado del
      código"). Sustituye, no une: para cada sustancia cuyo vigente real
      NO está ya capturado por NINGÚN patrón de título (ni siquiera vía
      otra fila hermana del mismo documento de grupo), quita el/los
      dossier(s) viejo(s) de esa sustancia del corpus y añade el
      vigente -- con comprobación de seguridad de que ningún OTRO
      dossier sigue siendo vigente para otra sustancia antes de
      quitarlo (dossier de grupo compartido).
      - **Dos bugs de implementación encontrados y corregidos en el
        mismo diagnóstico, antes de fijar la versión final** (ninguno
        llegó a commitearse por separado):
        1. Una primera versión sustituía CUALQUIER dossier que no fuera
           el vigente de NINGUNA de sus sustancias ligadas -- demasiado
           agresivo: sobre-podaba el corpus a 143, quitando historial
           legítimo ya cubierto por OTRO patrón de título (ej.
           "Re-evaluation of titanium dioxide (E171)" de 2016, aunque
           el vigente 2021 ya estuviera en el corpus vía
           `SAFETY_ASSESSMENT_FOOD_ADDITIVE_PATTERN`). Corregido:
           sustituir SOLO cuando el vigente de la sustancia no está
           capturado en absoluto, no cuando ya coexiste con otro
           documento por otro patrón.
        2. Con esa corrección, seguían sustituyéndose de más
           (Allura Red AC, ácido sórbico, luteína, estearoil-2-lactilato)
           -- causa: `unique_reevaluation_opinions()` deduplica por
           TÍTULO, no por `Document UUID`; un dictamen de grupo genera
           varias filas DOSSIER con el MISMO título y distinto UUID
           (una por sustancia cubierta), y `drop_duplicates` descarta
           todas menos una. Comparar `current.dossier_uuid` contra ese
           conjunto YA deduplicado daba un falso "no está en el corpus"
           para cualquier sustancia cuyo enlace resolviera a una de las
           UUIDs descartadas por el dedup, aunque el título sí
           estuviera representado. Corregido: la comprobación de "¿ya
           está capturado?" usa el conjunto COMPLETO sin deduplicar
           (`reevaluation_dossiers()`, no `unique_reevaluation_opinions()`).
      - **Verificado tras el fix: 162 → 162, exactamente las 6
        sustituciones esperadas, nada más tocado** (confirmado que
        titanio, Allura Red AC, etc. conservan AMBOS documentos, viejo
        y nuevo). 3 tests de regresión nuevos en
        `tests/test_openfoodtox_joins.py`:
        `test_current_reevaluation_corpus_is_same_size_as_title_corpus`,
        `test_current_reevaluation_corpus_substitutes_narrow_hybrid_cases`,
        `test_current_reevaluation_corpus_keeps_substances_already_well_represented`
        (este último bloquea específicamente la regresión del bug 1) --
        **12/12 tests en verde.**
      - `unique_reevaluation_opinions()` NO se modifica ni se
        deprecia -- sigue siendo el corpus "crudo" por patrón de
        título. `current_reevaluation_corpus()` es la función a usar
        para la descarga de PDFs (pendiente #4), no aquella.
  - **Grupo B -- bug real de Nodo 3, dato incorrecto, caso único hasta
    ahora (1 sustancia): Sunset Yellow FCF (E110).**
    `current_reference_value_opinion` devuelve como "vigente" un
    dictamen de 2022 ("Safety and efficacy of a **feed** additive
    consisting of Sunset Yellow FCF for cats and dogs, ornamental fish,
    grain-eating ornamental birds and small rodents") con
    `Domain.FoodDomain == 'food additives'` **pero
    `Domain.Regulation == 'Regulation (EC) No 1831/2003'`** (regulación
    de aditivos para PIENSO ANIMAL, no alimentario) -- mal-etiquetado
    genuino de dominio, no detectable por el filtro actual porque solo
    mira `Domain.FoodDomain`. Desplaza al dictamen que sí sería vigente
    (candidatos reales: 2009 "re-evaluation of Sunset Yellow FCF (E 110)
    as a food additive", o 2014 "Reconsideration of the temporary ADI
    and refined exposure assessment for Sunset Yellow FCF"). A
    diferencia del Grupo A, aquí el ADI/dictamen devuelto al usuario
    sería sobre la sustancia equivocada de contexto regulatorio (pienso
    animal, no alimentación humana) -- un falso positivo real del Nodo
    3, no solo una laguna de cobertura.
  - **Alcance del bug de Grupo B investigado y cerrado (sesión
    17-ago-2026):** sobre las 507 filas de `DOSSIER` con
    `Domain.FoodDomain == 'food additives'` (todo el dataset, no solo
    las 233 sustancias del corpus de reevaluación), solo **2 filas
    (0,4%)** tienen `Domain.Regulation` apuntando a pienso animal
    (`1831/2003`) -- las mismas 2 coinciden exactamente con lenguaje de
    especies animales en el título (`for cats and dogs`, `for all
    animal species`), así que ambas señales no añaden casos nuevas por
    separado. **Las dos materializan el bug de verdad** (el dossier
    mal-etiquetado gana `MAX(fecha)` en `current_reference_value_opinion`
    para su sustancia):
    1. Sunset Yellow FCF (E110) -- ya descrito arriba, sustancia real
       del corpus de reevaluación con dictamen alimentario genuino
       (2009/2014) desplazado.
    2. **Nuevo, no visto en el análisis anterior porque esa sustancia
       no está ligada a ningún dossier de `reevaluation_dossiers()`:
       "Olive leaf dry extract from O. europaea L."** -- su ÚNICA fila
       en `DOSSIER` es precisamente este dossier de pienso animal
       (`"...used as a sensory additive in feed for all animal
       species"`, 2020-01-28). No existe ningún dictamen alimentario
       real para esta sustancia en el dataset -- no es un caso de
       "dictamen real desplazado" como Sunset Yellow FCF, sino de una
       sustancia que NO es un aditivo alimentario en absoluto
       presentándose como si lo fuera si alguien la consulta por
       nombre exacto (`substance_uuid_by_name` no distingue esto).
    - Verificado con un escaneo adicional más amplio (`título contiene
      la palabra suelta "feed"`, sin exigir regulación): confirma que
      no hay más filas -- las otras 5 coincidencias son las 5 filas del
      Statement de Allura Red AC (Grupo A, regulación 178/2002
      correcta, dominio correcto, solo le falta el marcador de título).
    - **Conclusión: el patrón inverso (dominio `'food additives'` en
      dossiers que en realidad son de pienso animal) es real pero raro
      -- 2 de 507 filas (0,4%), no sistémico como el mistag en la otra
      dirección (18 de ~120 dossiers, ver más arriba).**
  - **FIX IMPLEMENTADO (sesión 17-ago-2026):** `current_reference_value_opinion`
    ahora excluye de los candidatos cualquier dossier cuyo
    `Domain.Regulation` contenga `"1831/2003"` (regulación de aditivos
    para pienso animal, FEEDAP) -- constante
    `ANIMAL_FEED_REGULATION_MARKER` en `ingestion/openfoodtox.py` --
    **independientemente de lo que diga `Domain.FoodDomain`**. Señal
    estructural, no de texto de título -- más fiable para este caso
    concreto que el patrón usado para el rescate de mal-etiquetado en
    la otra dirección (que sí depende de texto porque no hay campo
    estructural que distinga "aditivo alimentario real mal etiquetado
    `'other:'`" de "no es aditivo alimentario en absoluto"). Verificado
    con los dos casos reales:
    - Sunset Yellow FCF (E110): tras excluir el dossier de pienso, el
      resultado pasa a ser el de **2014-06-26** ("Reconsideration of
      the temporary ADI and refined exposure assessment for Sunset
      Yellow FCF (E110)") -- no el de 2009 ("re-evaluation..."), porque
      2014 es el 'EFSA opinion' de dominio alimentario más reciente
      tras la exclusión (mismo heurístico MAX-fecha que en el resto del
      sistema; el de 2014 reconsidera/refina el de 2009, no es un
      programa distinto).
    - "Olive leaf dry extract from O. europaea L.": tras excluir su
      única fila (el dossier de pienso animal), el resultado pasa a ser
      **`None`** -- correcto, porque no existe ningún dictamen de
      aditivo alimentario real para esta sustancia en el dataset. Ya
      estaba bien manejado aguas abajo sin necesidad de reforzarlo:
      `verify_currency_node` marca `vigencia_ambigua=True` con
      `result is None`, y `_format_structured_result(None)` en el Nodo
      4 devuelve un mensaje explícito de "no se ha podido determinar un
      dictamen vigente" (regla 4 de `NODE_4_GROUNDING_RULES` ya cubre
      este caso) en vez de inventar relevancia alimentaria con el
      dossier de pienso.
    - Tests de regresión nuevos en `tests/test_openfoodtox_joins.py`:
      `test_sunset_yellow_current_opinion_excludes_feed_regulation_dossier`
      y `test_olive_leaf_extract_has_no_real_food_additive_opinion`. Los
      6 tests previos (aspartamo, propil galato, plata, columnas ADI/
      discusión, tamaño de corpus) siguen en verde tras el fix -- 8/8.
    - **Grupo A también cerrado, en sesión separada el mismo día** -- ver
      el bullet "FIX IMPLEMENTADO -- Grupo A cerrado" más arriba, dentro
      de la descripción del Grupo A. No lo confundas con este fix: son
      dos cambios de código independientes (`current_reference_value_opinion`
      para el Grupo B, `reevaluation_dossiers()` para el Grupo A), cada
      uno con sus propios tests de regresión.
- **No hay campo estructural de "vigente/superseded"** en ningún sitio del
  esquema. El heurístico de fecha+tipo es una aproximación razonable, no
  una garantía — puede fallar si hay dos 'EFSA opinion' del mismo tipo con
  fechas muy próximas sin que el título aclare cuál sustituye a cuál. La
  detección de esa ambigüedad (para decidir cuándo caer a un fallback de
  LLM sobre el texto del PDF) está marcada como TODO en
  `verify_currency_node`, no implementada todavía.
- **Existe un servidor MCP público** (`mcp-openfoodtox`) que ya expone
  OpenFoodTox por MCP, sobre un dataset desactualizado (2023). La
  diferenciación de este proyecto NO puede ser "expongo OpenFoodTox por
  MCP" — tiene que ser el razonamiento LangGraph orquestado (en particular
  el Nodo 3), que ese servidor no hace.
- **`HumanHealthHazardCharacteristics.OtherReferenceValues.ReferenceToEFSAOpinion`
  (FLEX_SUM.ToxRefValues) NO es un enlace fiable al dossier de origen,
  pese a lo que sugiere el nombre.** Apunta en teoría al UUID del
  dossier que originó el valor de referencia -- un atajo directo que
  ahorraría el join `DOCUMENT UUID → DOSSIER_DOCS → DOSSIER UUID` que
  usa `current_reference_value_opinion`. Vacío en los 5 registros de ADI
  de aspartamo verificados en el diseño original. Comprobado en sesión
  (16-ago-2026) que no fue mala suerte con aspartamo: **solo 8,3% de las
  filas de `FLEX_SUM.ToxRefValues` con `adi_value` no nulo lo tienen
  poblado (84/1007)** -- genuinamente disperso, no una excepción del
  caso de prueba. **No lo uses como enlace principal ni como fallback
  primario.** El enlace fiable sigue siendo el que ya usa
  `current_reference_value_opinion`: `Document UUID` (del registro de
  ADI) → `DOSSIER_DOCS` → `DOSSIER UUID` → `DOSSIER`.
- **`HumanHealthHazardCharacteristics.AcceptableDailyIntake.CriticalEndpoint`
  (FLEX_SUM.ToxRefValues) NO contiene el efecto crítico, pese al nombre.**
  Mismo patrón de fondo que con `ReferenceToEFSAOpinion` arriba: un campo
  bien poblado no garantiza que contenga lo que su nombre sugiere —
  verifica el contenido real antes de usarlo, no solo la tasa de
  relleno.
  Investigado y descartado como fuente de `adi_justification` (sesión
  16-ago-2026):
  - Es un `Reference field` / `Link to document (single)` a
    `ENDPOINT_STUDY_RECORD` (confirmado en la hoja `DATA_DICTIONARY`),
    no texto ni categoría — un UUID que apunta a otro registro en
    `END_STUDY_REC.HumanHealth`.
  - Poblado en el 86,9% de las filas de `FLEX_SUM.ToxRefValues` con
    `adi_value` no nulo (875/1007) — mejor tasa que
    `JustificationAndComments` (50%, 504/1007) — pero vacío en las 5
    filas del caso aspartamo.
  - El UUID resuelve al 100% contra `END_STUDY_REC.HumanHealth`, pero
    los subcampos que sí describirían el efecto real
    (`TargetSystemOrganToxicity.Organ`,
    `TargetSystemOrganToxicity.CriticalEffectsObserved`) están vacíos en
    >97% de esos registros resueltos (2,5% y 1,0% de relleno
    respectivamente). Lo único consistentemente poblado es
    `AdministrativeData.Endpoint` (100%, una categoría genérica de tipo
    de estudio, ej. "chronic toxicity: other route") y la especie
    (97,9%) — no el efecto crítico en sí.
  - `Document UUID` no es clave única en `END_STUDY_REC.HumanHealth`:
    los 875 UUIDs de `CriticalEndpoint` resuelven a 1.862 filas (~2,1
    filas por UUID), así que integrarlo exigiría además resolver esa
    ambigüedad de clave.
  - **Conclusión: `JustificationAndComments` sigue siendo el mejor
    candidato disponible para `adi_justification`** pese a su menor
    tasa de relleno (50%) — porque cuando está poblado es texto
    descriptivo real (ver caso aspartamo en `ingestion/openfoodtox.py`),
    no una categoría genérica. No reabrir esto sin nueva evidencia.
- **`END_SUM.Discussion.Discussion` -- enlace, tasa de relleno real y
  heurístico de boilerplate (investigado sesión 16-ago-2026, ver
  también "Estado del código" para las cifras corregidas de
  cobertura):**
  - Enlace: mismo patrón que `current_reference_value_opinion` --
    `END_SUM.Document UUID` → `DOSSIER_DOCS` (con `DOCUMENT TYPE ==
    'ENDPOINT_SUMMARY'`, no `'FLEXIBLE_SUMMARY'`) → `DOSSIER UUID` →
    `DOSSIER`. Resuelve al 100%. Cada dictamen de reevaluación enlaza
    típicamente a ~2 filas de `END_SUM`
    (`Carcinogenicity_EU_PPP` + `GeneticToxicity`, a veces también
    `Toxicokinetics`).
  - Longitud: siempre un párrafo corto cuando existe (media 321
    caracteres / ~51 palabras, máximo 954 caracteres / ~157 palabras --
    recalculado sobre el corpus corregido de 136 dictámenes, cifra
    anterior de 336/54 sobre los 118 pre-fix ligeramente desactualizada,
    el máximo no cambia) -- cabe entero en el prompt del Nodo 4, no hace
    falta chunking para este campo concreto.
  - **Heurístico de boilerplate validado sin excepciones encontradas:**
    `len(texto) < 280` caracteres **O** el texto es un duplicado exacto
    del mismo `Discussion.Discussion` en ≥2 `DOSSIER UUID` distintos
    (calculado dinámicamente sobre los datos, no una lista hardcodeada
    de strings). Un prefijo textual (p.ej. "Following a request from
    the European Commission") NO sirve como heurístico -- ese prefijo
    aparece tanto en boilerplate puro (209 car.) como en discusión
    sustantiva (932-954 car.). Tampoco basta un umbral de longitud
    simple más alto: existe un párrafo administrativo sobre el
    Reglamento 257/2010 que se repite literalmente en 9 dossiers
    distintos con 518-703 caracteres -- más largo que cualquier umbral
    razonable, y aun así puro boilerplate; solo la detección de
    duplicado cross-dossier lo captura.
  - **Zona gris sin señal limpia (280-650+ caracteres, no cubierta por
    el heurístico):** ni la longitud ni un listado de palabras clave
    (`concluded`/`considered`/`noted`/`agreed`, probado y descartado
    por dar falsos positivos) separan de forma fiable la discusión de
    incertidumbre real de la descripción regulatoria genérica dentro
    de este rango. Ejemplo: el texto de polisorbatos (E 432-E436, 621
    car.) no es boilerplate según el heurístico, pero tampoco contiene
    razonamiento del panel -- solo enumera qué sustancias cubre el
    dictamen. Frente a esto, ejemplos reales SÍ sustantivos en ese
    mismo rango de longitud: octyl gallate (E 311, 595 car.) y ácido
    ascórbico (E 300-302, 636 car.) sí incluyen razonamiento real del
    panel ("was not provided with a newly submitted dossier... noted
    that not all original studies... were available").

- **Wiley (`onlinelibrary.wiley.com`) descartado como ruta directa de
  descarga de PDFs -- bloqueo Cloudflare, no un fallo de script
  (verificado sesión 17-ago-2026, `scripts/probe_dossier_urls.py`).**
  Los DOIs de `current_reevaluation_corpus()` resuelven correctamente
  vía `doi.org` a `https://onlinelibrary.wiley.com/doi/<doi>`
  (`LiteratureReference.LinkToPersistentIdentifier`, con prefijo
  `doi:` a quitar antes de construir la URL). Probado con 5 DOIs de
  ejemplo (aspartamo E 951 + 4 más): **las 5 devuelven `403` con
  cabecera `cf-mitigated: challenge`** -- un desafío JS activo de
  Cloudflare, no un bloqueo por `User-Agent` (probado también con UA de
  navegador real vía `curl`, mismo resultado) ni por `robots.txt`
  (comprobado: el path `/doi/` no está en `Disallow` de
  `onlinelibrary.wiley.com/robots.txt`). Ninguna petición HTTP simple
  (`requests`, `curl`) puede resolver un challenge de Cloudflare --
  haría falta un navegador con ejecución de JS (Playwright/Selenium),
  con la fragilidad y zona gris de ToS que eso conlleva. **No usar
  Wiley como fuente de descarga sin resolver antes esto.**
- **`efsa.europa.eu` descartado -- es un alias que redirige a Wiley, no
  una fuente independiente (verificado sesión 17-ago-2026,
  `scripts/probe_alternate_sources.py`).** La "referencia" de la URL
  `efsa.europa.eu/en/efsajournal/pub/<referencia>` **es literalmente el
  último segmento numérico del DOI** (ej. DOI
  `10.2903/j.efsa.2013.3496` → referencia `3496` -- confirmado contra
  el caso real de aspartamo por búsqueda web antes de asumirlo, no es
  una transformación inventada). Pero la URL resultante hace `301
  redirect` a `https://efsa.onlinelibrary.wiley.com/doi/<doi>` -- un
  subdominio de Wiley DISTINTO al de la ruta por DOI
  (`efsa.onlinelibrary.wiley.com` vs `onlinelibrary.wiley.com`), pero
  detrás del MISMO bloqueo: `403` + `cf-mitigated: challenge`.
  `efsa.europa.eu` no aloja los PDFs de EFSA Journal en absoluto para
  este propósito, solo redirige.
- **PubMed Central (PMC) -- fuente parcialmente viable, pero NO fiable
  sin verificación, y con un tipo de bloqueo distinto al de Wiley
  (investigado sesión 17-ago-2026, mismo script).** Tres hallazgos
  independientes, cada uno importante por separado:
  1. **La búsqueda de PMCID por DOI (`ESearch`, `db=pmc`,
     `term=<doi>[DOI]`) da falsos positivos -- verificado con los 5
     DOIs de prueba, no es un caso aislado.** De los 5 PMCIDs
     encontrados, solo 2 correspondían realmente al DOI solicitado al
     verificar `citation_doi`/`citation_title` en la página devuelta
     (ácido algínico E 400-404, nitrito potásico/sódico E 249/250). Los
     otros 3 fallan de formas distintas: el de aspartamo (el caso de
     referencia del proyecto) apunta a un artículo de *Scientific
     Reports* de 2025 sobre cálculos renales que solo menciona
     "aspartame" en el texto -- **la reevaluación EFSA de aspartamo de
     2013 no parece estar indexada en PMC bajo ese DOI en absoluto**;
     el de Quillaia extract apunta a un documento real pero
     EQUIVOCADO (el follow-up de 2024, no el dictamen de 2019
     solicitado); el de ácido tartárico fue bloqueado por un reCAPTCHA
     (punto 3) antes de poder verificarlo. **Cualquier uso de PMC como
     fuente debe verificar `citation_doi` contra el DOI solicitado
     antes de confiar en el PMCID encontrado -- nunca asumir que el
     primer resultado de ESearch es el correcto.** Buscar por texto del
     título en vez de por DOI es peor, no mejor: una prueba con
     `"re-evaluation of aspartame" AND "E 951"` devolvió 69 resultados
     (probablemente artículos que CITAN el dictamen, no el dictamen
     mismo) -- no es una alternativa fiable.
  2. **Cuando el PMCID SÍ es correcto, la página es accesible -- pero
     solo con `curl`, NO con `requests` de Python, para la MISMA URL y
     el MISMO `User-Agent`.** Verificado repetidamente:
     `requests.get()`/`requests.head()` devuelven `403` con un cuerpo
     genérico de 134 bytes ("403 Forbidden", sin cabeceras de
     Cloudflare ni de ningún WAF identificable por nombre) de forma
     consistente, mientras que `curl` con las mismas cabeceras obtiene
     `200` con el HTML completo del artículo. Descartado que sea por
     HTTP/1.1 vs HTTP/2 (probado forzando `--http1.1` en `curl`, sigue
     en `200`) -- la explicación más probable es fingerprinting
     TLS/HTTP a nivel de librería (`requests`/`urllib3` vs la pila TLS
     de `curl`), no un problema de cabeceras que se pueda arreglar
     cambiando el `User-Agent`. Implicación práctica: un descargador
     real necesitaría usar `curl` (subproceso) o una librería que
     imite su fingerprint (ej. `curl_cffi`), no `requests` a secas.
  3. **Incluso con acceso que funciona, no es 100% estable: 1 de los 5
     PMCIDs devolvió una página de reCAPTCHA ("Checking your
     browser") en vez del artículo**, con `curl` y las mismas
     cabeceras que en los casos que sí funcionaron -- no se ha
     determinado si es por ráfaga de peticiones, aleatorio, o
     específico de ese artículo; no investigado más a fondo en esta
     sesión.
  - **Conclusión: PMC no es un "sí" limpio ni un "no" limpio.** Es una
    fuente real y parcialmente accesible (a diferencia de Wiley, que
    está bloqueado sin excepción), pero con cobertura incompleta
    (aspartamo, el caso de referencia del proyecto, no está verificado
    en absoluto), riesgo de falsos positivos en la búsqueda que
    exigen verificación por DOI antes de confiar en el resultado, la
    necesidad de un cliente HTTP con fingerprint tipo `curl` en vez de
    `requests`, y bloqueos intermitentes tipo reCAPTCHA incluso cuando
    el resto funciona.
- **DECISIÓN TOMADA (sesión 17-ago-2026): descarga MANUAL vía
  navegador normal, no automatizada.** De las 3 fuentes probadas
  (Wiley directo, `efsa.europa.eu`, PMC), ninguna permite descarga
  automatizada fiable -- Wiley bloquea con un *challenge* de
  Cloudflare que ningún cliente HTTP simple puede resolver,
  `efsa.europa.eu` solo redirige a la misma Wiley, y PMC tiene falsos
  positivos de búsqueda por DOI, exige `curl` en vez de `requests`, y
  aun así da captcha intermitente. **El bloqueo detectado es
  específico de peticiones automatizadas (fingerprint TLS/HTTP,
  desafíos JS) -- un navegador con sesión humana normal no debería
  toparse con el mismo challenge.** Se descarta explícitamente un
  navegador headless (Playwright/Selenium) para resolver esto de forma
  automática -- más frágil, zona gris de ToS, y el volumen (162
  documentos, una vez cada uno) no justifica esa complejidad frente a
  una descarga manual asistida por checklist.
  - **Checklist generado:** `scripts/generate_pdf_checklist.py`
    produce `data/pdf_download_checklist.csv` y
    `data/pdf_download_checklist.md` (mismas columnas: sustancia(s),
    E-number(s), DOI, título, nombre de archivo de destino esperado,
    columna `descargado` vacía para marcar progreso a mano). Sin
    peticiones de red -- solo lee el xlsx local.
  - **Nombre de archivo destino:** `<E-numbers>_<DOI saneado>.pdf` (ej.
    `E951_10.2903_j.efsa.2013.3496.pdf`) -- el DOI garantiza unicidad
    salvo la excepción de abajo; el prefijo de E-numbers es solo para
    legibilidad humana.
  - **Hallazgo de calidad de datos encontrado al generar el checklist,
    no visto antes en esta sesión:** `LiteratureReference.LinkToPersistentIdentifier`
    no es consistente en el xlsx -- 147 filas del corpus con prefijo
    `"doi:"`, 15 con `"doi. org/"` (con espacio, sin dos puntos).
    Normalizado ancla en el propio DOI (`10\.\d+/...`) en vez de en el
    prefijo, para no depender de que no aparezca una tercera variante
    mañana.
  - **Segundo hallazgo: el corpus de 162 tiene un duplicado real, no
    162 documentos únicos -- son 161.** "Re-evaluation of saccharin
    and its sodium, potassium and calcium salts (E 954)..." aparece
    DOS VECES en el xlsx con el MISMO DOI
    (`10.2903/j.efsa.2024.9044`), por una variante de título con una
    errata de espacio ("and calcium salts" / "andcalcium salts") --
    como `reevaluation_dossiers()`/`unique_reevaluation_opinions()`
    deduplican por texto EXACTO de título, la errata cuela como una
    fila de corpus adicional para el mismo documento real. El
    checklist deduplica por DOI (prefiriendo la fila con sustancia
    resuelta vía toxref, que resultó ser la de la errata, no la del
    título "correcto") antes de escribir -- **161 filas en el
    checklist, no 162.** No corregido en
    `current_reevaluation_corpus()`/`unique_reevaluation_opinions()`
    en esta sesión (el checklist ya lo maneja; arreglarlo en el
    corpus en sí -- deduplicar por DOI en vez de por título -- queda
    como mejora pendiente, no bloqueante).

## Decisiones de arquitectura ya tomadas (no las reabras sin motivo nuevo)

- **Separación estructurado/narrativo:** OpenFoodTox (xlsx) para todo lo
  cuantificable (ADI/TDI/NOAEL, fechas, DOIs) vía queries deterministas,
  sin LLM. PDFs + RAG solo para el contenido narrativo (discusión de
  incertidumbre, razonamiento del panel) que no está en campos
  estructurados.
- **Cliente LLM intercambiable** (`graph/llm_client.py`): interfaz
  `LLMClient` con `DeepSeekClient` (producción, modelo
  `deepseek-v4-flash`) y `OllamaClient` (alternativa local opcional,
  coste cero, calidad menor — no es el backend por defecto). Selección
  vía `EFSA_RAG_LLM_BACKEND` en el entorno. No acoples los nodos del
  grafo a un proveedor concreto.
- **Modo "thinking" de DeepSeek V4 desactivado explícitamente**
  (`DeepSeekClient.complete()`, `extra_body={"thinking": {"type":
  "disabled"}}`): DeepSeek V4 lo activa por defecto con esfuerzo "high".
  Verificado en sesión (16-ago-2026, caso aspartamo/Nodo 4): con
  "thinking" activo, `reasoning_content` consume presupuesto del mismo
  `max_tokens` que el texto final -- en una prueba real se gastaron 799
  de 800 tokens en razonamiento, dejando la respuesta truncada/vacía. Y
  con "thinking" activo, `temperature` se ignora silenciosamente (no
  hace nada, ni siquiera con `temperature=0.0`). Desactivarlo restaura
  el comportamiento determinista esperado y evita el riesgo de
  truncamiento con el `max_tokens=800` por defecto. **No lo reactives
  sin volver a medir coste y truncamiento** -- si en el futuro se
  necesita razonamiento explícito para algún nodo, hazlo opt-in por
  nodo, no como default global del cliente.
- **Despliegue — Opción A, índice horneado:** el índice de Chroma se
  construye en local y se empaqueta como parte del repo/imagen de
  despliegue (read-only en producción), no se reindexa en caliente desde
  la demo pública. El botón de refresco en la UI comprueba novedades y
  avisa, no reindexa en producción. Redeploy manual tras reindexar en
  local. Motivo: el hosting gratuito (HF Spaces / Streamlit Community
  Cloud) tiene almacenamiento efímero — un índice construido en caliente
  se puede perder en un reinicio de contenedor.
- **Candado de refresco de 24h** (`ui/app.py`, `LOCK_FILE`): protege
  cómputo del hosting, NO presupuesto de API (el botón no llama al LLM).
  Es un archivo server-side, no session_state — compartido por todos los
  usuarios del día, no por sesión de navegador.
- **Límites de consulta** (`ui/app.py`, `check_and_register_query`): dos
  capas independientes — límite GLOBAL diario en USD estimados (la
  protección real de presupuesto, infalible porque es server-side) y
  límite por IP (mejora de UX, NO es protección real: usa una API interna
  no estable de Streamlit y las IPs se comparten/cambian con facilidad).
  No confundas una capa con la otra al documentar o modificar esto.
- **Precio LLM de referencia (ajustar si cambia):** DeepSeek V4-Flash,
  ~$0.001-0.002 por consulta según franja horaria (precios actualizados
  16-ago-2026 con tarifas punta/valle). Presupuesto de referencia:
  6-7€/mes cubre miles de consultas incluso en el peor caso. Se evaluó
  Kimi K2.6/K3 como alternativa: K2.6 es más caro que DeepSeek y con peor
  puntuación en benchmarks generales; K3 iguala casi a modelos de
  frontera pero a 15-20x el coste. Se mantiene DeepSeek por defecto.
  **Antes de cambiar de proveedor por benchmarks genéricos**, construir
  un set de 10-15 casos de prueba del Nodo 4 (con las reglas de
  comunicación de riesgo) y medir tasa de cumplimiento real, no decidir
  por índices de inteligencia genéricos que no miden eso.
  **Esta estimación de coste asume "thinking" desactivado** (ver bullet
  de arriba). Medido en sesión con el mismo prompt del Nodo 4: 799
  tokens de salida con "thinking" activo (esfuerzo "high", casi todo
  `reasoning_content`) frente a 365 con "thinking" desactivado -- un
  desplegado con el default de DeepSeek sin darse cuenta habría corrido
  con un coste real ~2-3x el estimado aquí, no por un cambio de precio
  del proveedor sino por un parámetro de la llamada.

## Estado del código (a fecha de este documento)

Implementado y con lógica real (no placeholder):
- `ingestion/openfoodtox.py` — cadena de joins completa, incluyendo ADI
  (`adi_value` + `adi_unit`) y justificación (`adi_justification`)
  ligados al registro de `FLEX_SUM.ToxRefValues` del dossier vigente
  concreto, no a cualquier ADI de la sustancia. **Validado contra el
  xlsx real** (`data/raw/OFT3_0_export_repository.xlsx`, sesión
  16-ago-2026): caso aspartamo da ADI = 40 mg/kg bw/day, fecha
  2013-11-28, tipo 'EFSA opinion' — coincide con el valor conocido.
  - **Bug corregido en esta sesión, no antes:** las cuatro cargas de
    hoja (`dossier`, `dossier_docs`, `sub`, `flex_sum_toxref`) usaban
    `pd.read_excel(..., header=1)`. La cabecera real está en la
    primera fila de cada hoja (verificado con `openpyxl`,
    `min_row=1`), no en la segunda — con `header=1`, pandas se saltaba
    la cabecera real y usaba la primera fila de datos (UUIDs, números)
    como nombres de columna, lo que rompía cualquier acceso por
    nombre. Corregido a `header=0` en las cuatro hojas.
  - Hallazgo relacionado, también de esta sesión:
    `LiteratureReference.DateOfEvaluation` llega de pandas como `str`
    `'YYYY-MM-DD'` (celda de Excel formateada como texto), no como
    `date`/`Timestamp` — `current_reference_value_opinion` ahora lo
    parsea con `_parse_iso_date()` antes de construir
    `OpinionReference` para cumplir su tipo `date | None`.
- `graph/llm_client.py` — interfaz `LLMClient` + `DeepSeekClient`
  (con "thinking" explícitamente desactivado, ver "Decisiones de
  arquitectura ya tomadas") + `OllamaClient`.
- `graph/nodes.py` — Nodo 1 (extracción con LLM), Nodo 3 (determinista)
  y Nodo 4 (generación) implementados. Nodo 4 conecta
  `deps.llm_client.complete(...)` con system prompt =
  `NODE_4_GROUNDING_RULES` + `NODE_4_SAFETY_COMMUNICATION_RULES`;
  probado con llamada real a la API (caso aspartamo) cumpliendo las
  reglas de comunicación de riesgo. Nodo 2 (retrieval híbrido) sigue
  siendo un contrato con `NotImplementedError` — bloqueado por no
  existir todavía el vector store (ver pendiente 4-5 abajo). El Nodo 4
  está diseñado para degradar con gracia con `retrieved_chunks` vacío
  mientras tanto, pero no se ha probado con fragmentos narrativos
  reales.
- `ui/app.py` — candado de refresco + límites de consulta, funcional.
- `tests/test_openfoodtox_joins.py` — test de regresión del caso
  aspartamo + test de columnas de ADI, **pasan los 3 contra el xlsx
  real** (antes se saltaban por no haber xlsx en `data/raw/`).

Pendiente, en orden de menor a mayor incertidumbre:
1. QA del corpus de 162 dictámenes contra las calls for data activas
   conocidas (ribonucleótidos E626-635, ácido glucónico E574-579,
   aditivos en forma gaseosa).
2. Resolver la limitación conocida del Nodo 1: `substance_uuid_by_name`
   exige coincidencia exacta del nombre químico canónico en inglés — no
   maneja español ("aspartamo") ni E-numbers ("E 951") todavía. Falta
   verificar si `SUB` tiene un campo de E-number consultable antes de
   implementar un fallback.
3. **Integrar `END_SUM.Discussion.Discussion` en `OpinionReference`**,
   con el heurístico de detección de boilerplate ya validado en datos
   (ver "Hallazgos verificados": `len < 280` caracteres O duplicado
   exacto entre ≥2 dossiers distintos → boilerplate). **Prioridad
   movida por delante de la descarga de PDFs y el pipeline de
   chunking/embeddings/Chroma** (antes puntos 3-4, ver nota más abajo).
4. **Descarga MANUAL asistida por checklist de los PDFs (161
   dictámenes únicos -- ver "Hallazgos verificados", el corpus de 162
   tiene un duplicado real por errata de título)** -- ya NO es "escribir
   un script de descarga": las 3 fuentes probadas (Wiley directo,
   `efsa.europa.eu`, PubMed Central) bloquean peticiones automatizadas
   (ver "Hallazgos verificados"), así que la descarga es manual vía
   navegador normal. Checklist ya generado:
   `data/pdf_download_checklist.csv` /
   `data/pdf_download_checklist.md` (script:
   `scripts/generate_pdf_checklist.py`, re-ejecutar si el corpus
   cambia). Queda: descargar los 161 PDFs a mano y marcar la columna
   `descargado` según se avance -- trabajo del usuario, no de Claude en
   sesión.
5. Pipeline de chunking + embeddings locales (`sentence-transformers`) +
   Chroma — esto desbloquea el Nodo 2 (retrieval híbrido).
   **A tener en cuenta en el diseño del mapeo sustancia→archivo (no
   implementado todavía, anotado sesión 17-ago-2026 antes de que se
   olvide): 29 de los 161 PDFs del checklist cubren MÁS DE UN E-number
   en el mismo archivo** (dictámenes de grupo -- ej.
   `E200-E202-E203_...pdf` para "Re-evaluation of sorbic acid (E 200),
   potassium sorbate (E 202) and calcium sorbate (E 203)", o
   `E220-E221-E222-E223-E224-E226-E227-E228_...pdf` para el grupo de
   sulfitos, hasta 9 E-numbers en un solo PDF). **No asumir un archivo
   por E-number 1:1 al indexar** -- el chunking/vector store necesita
   poder resolver "¿en qué PDF(s) está la sustancia X?" como una
   relación muchos-a-uno (una sustancia -> un archivo, pero un archivo
   -> potencialmente varias sustancias), no una tabla 1:1 archivo↔E-number.
   Lista completa de los 29 casos disponible en
   `data/pdf_download_checklist.csv` (filas con `;` en la columna
   `e_number`).
6. Detección de ambigüedad en el Nodo 3 (ver "Hallazgos verificados").
7. Servidor MCP (`mcp/`, carpeta vacía todavía).
8. Deploy siguiendo la Opción A descrita arriba.

**Por qué el punto 3 pasa por delante de PDFs/chunking/Chroma:**
`Discussion.Discussion` (hoja `END_SUM`, enlace verificado con el mismo
patrón `Document UUID → DOSSIER_DOCS → DOSSIER` que ya usa
`current_reference_value_opinion`) es un párrafo corto (máx. ~157
palabras) que cabe entero en `OpinionReference`/el prompt del Nodo 4 sin
chunking ni vector store, y no depende de nada del pipeline de PDFs.
**Corrección (16-ago-2026): la cifra de cobertura real es 29,4%, no el
81% estimado en una medición anterior de esta misma sesión** -- ese 81%
usaba un detector de boilerplate demasiado estrecho (solo el prefijo
literal "Following a request from..." + `len < 320`), que no capturaba
variantes de la misma frase de mandato con otra redacción ni el párrafo
administrativo sobre el Reglamento 257/2010 que se repite igual en 9
dossiers distintos. Recalculada tres veces al cambiar el corpus: 118
(pre-fix de dominio) dio 32,2% (38/118); 136 (tras el rescate de
dominio, sesión 16-ago-2026) dio 29,4% (40/136) -- los 18 dossiers
rescatados por ese fix aportan sobre todo boilerplate (14 de 18 caen en
"toda la discusión es boilerplate"), así que el porcentaje bajó un poco
al ampliar el corpus, aunque el número absoluto de dossiers con
contenido no-boilerplate subió (38→40); **recalculada de nuevo tras el
cierre del Grupo A (sesión 17-ago-2026, corpus 136→162) da 25,3%
(41/162)** -- de los 26 dictámenes nuevos que entraron con el cierre
del Grupo A ("extension of use", "statement on", "reconsideration of
the ADI", "safety assessment... as a food additive"), 25 aportan solo
boilerplate y únicamente 1 aporta contenido no-boilerplate nuevo, así
que el porcentaje vuelve a bajar por el mismo mecanismo que la vez
anterior (documentos más cortos/específicos, no reevaluaciones
completas) aunque el número absoluto sube otra vez (40→41). Cifra
vigente, sobre los 162 dictámenes de reevaluación:

| Categoría | Dossiers (sobre 162) |
|---|---|
| Sin ninguna fila de `Discussion` en `END_SUM` | 9 (5,6%) |
| Con discusión, pero TODAS las filas son boilerplate | 112 (69,1%) |
| Con al menos una fila NO marcada como boilerplate | **41 (25,3%)** |

**Ese 25,3% es "no probado como boilerplate", no "confirmado como
razonamiento científico sustantivo"** -- no lo trates como si lo fuera.
Ni la longitud ni un listado de palabras clave (`concluded`,
`considered`, `noted`, etc. -- probado y descartado, da falsos
positivos) separan de forma fiable, dentro de esa franja, la discusión
de incertidumbre real de la descripción regulatoria genérica. Ejemplo
de zona gris: el texto de polisorbatos (E 432-E436, 621 caracteres) no
es boilerplate según el heurístico (no es corto, no está duplicado
cross-dossier), pero tampoco contiene razonamiento del panel -- solo
lista qué sustancias cubre el dictamen y que "Polysorbates (E 432-E 436)
are authorised as food additives in the European Union (EU)". Esta
imprecisión residual es una limitación conocida del campo, no un bug a
resolver antes de integrarlo -- documentar en LIMITATIONS.md cuando se
implemente, no ocultarla.

Con esa salvedad, el 25,3% (o el subconjunto de ese 25,3% que resulte
genuinamente sustantivo) sigue siendo contenido narrativo real -- no
solo metadatos de citación -- sin depender de nada del pipeline de
PDFs. Esto permite un Nodo 4 con algo de contenido narrativo genuino
(no solo ADI + cita) mucho antes de tener PDFs descargados o Chroma
montado, aunque a menor escala de lo que se pensó inicialmente. El
pipeline de PDFs + RAG completo (puntos 4-5) sigue siendo necesario
para preguntas que requieran más profundidad de la que cabe en ese
párrafo -- y ahora también para el 74,7% de dossiers donde
`Discussion.Discussion` no aporta nada -- pero no es bloqueante para
tener una demo funcional con algo de contenido narrativo real.

(Investigado y descartado: `CriticalEndpoint` como fuente de efecto
crítico estructurado — ver "Hallazgos verificados". No es una tarea
pendiente, es una decisión ya tomada.)

## Mantenimiento de PROGRESS.md

Mantén un archivo `PROGRESS.md` en la raíz del repo, editándolo (no
recreándolo) a medida que avances. Formato: una entrada por sesión de
trabajo, con fecha, qué se implementó/decidió, y qué quedó pendiente o
sin resolver. Sé tan honesto ahí como este documento lo es contigo:
si algo quedó a medias, dilo explícitamente, no lo des por hecho.
