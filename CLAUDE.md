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
- **Licencia real de los 161 PDFs descargados -- NO es uniforme, varía
  por fecha de publicación (investigado sesión 17-ago-2026, antes de
  decidir si el índice de Chroma con texto de chunks puede publicarse
  en el repo público de GitHub).** Verificado por dos vías
  independientes que coinciden: (1) escaneo de texto (`pdftotext`) de
  los 161 PDFs completos buscando la mención explícita de "Creative
  Commons"; (2) el documento oficial `EFSA Journal Editorial Policy`
  (13-feb-2013, `efsa.europa.eu/sites/default/files/assets/Journaledpolicy.pdf`,
  sección 4.9 Copyright) + búsqueda web confirmando que el traslado de
  la publicación del EFSA Journal a Wiley como editor ocurrió en 2016.
  - **82 de 161 (2016-2025, todos con la MISMA frase exacta, sin
    variante NC ni ninguna otra):** llevan en el propio texto del PDF
    "This is an open access article under the terms of the Creative
    Commons Attribution-NoDerivs License, which permits use and
    distribution in any medium, provided the original work is properly
    cited and no modifications or adaptations are made." -- **CC
    BY-ND** (Wiley no imprime el número de versión en el PDF; su
    estándar actual es 4.0, no confirmado carácter a carácter en el
    texto). Permite uso comercial y no comercial, pero **explícitamente
    "sin modificaciones o adaptaciones", "unchanged and in whole"**
    según la descripción en lenguaje llano que da la propia EFSA/Wiley
    -- la licencia cubre redistribuir el artículo COMPLETO tal cual, no
    fragmentos.
  - **79 de 161 (2007-2016, solapan en 2016 -- 9 sin mención de CC ese
    año frente a 6 con ella, confirma que el corte real es a mitad de
    2016, no un cambio de año natural limpio):** SIN ninguna mención de
    "Creative Commons"/licencia en ningún punto del texto completo
    (`pdftotext` sin límite de páginas, no solo las primeras 3) --
    contemporáneos a la política oficial de 2013, que en su sección 4.9
    dice literalmente: *"The content of the EFSA Journal is EFSA
    copyright. Except where otherwise stated, reproduction of
    documents/information/articles for personal use (i.e. for
    research, educational purposes, private study or internal
    circulation within an organisation) or for further non-commercial
    dissemination to end users is authorised under the condition that
    appropriate acknowledgement is given to the source."* -- **NO es
    una licencia Creative Commons de ningún tipo**, es una política de
    copyright propia de EFSA, más restrictiva que CC BY-ND: no
    menciona explícitamente uso comercial (lo excluye por omisión, al
    contrario que CC BY-ND que sí lo permite), y su alcance ("personal
    use", "internal circulation within an organisation", "non-commercial
    dissemination to end users") no describe con claridad un caso como
    "publicar el texto indexado en un repositorio público de GitHub
    accesible a cualquiera".
  - **Implicación directa para Chroma (pregunta que motivó esta
    investigación):** Chroma va a persistir el TEXTO de los chunks, no
    solo los vectores -- eso es redistribución de texto, no solo de
    metadatos. Ninguno de los dos regímenes de licencia cubre con
    claridad ese caso concreto: el bloque 2007-2016 (79/161, 49%) no
    tiene licencia abierta en absoluto; el bloque 2016-2025 (82/161,
    51%) es CC BY-ND, que por su propia descripción oficial permite
    redistribuir el artículo "unchanged and in whole" -- un índice de
    fragmentos trocedados no es "in whole", y "no derivatives" es
    ambiguo respecto a si trocear cuenta como adaptación. **Ninguna
    lectura razonable de ninguno de los dos regímenes da un "sí" limpio
    a publicar el texto de los chunks en un repo público sin
    restricción.**
  - **DECISIÓN TOMADA (sesión 17-ago-2026, por el usuario, a la vista
    de este hallazgo):** `data/chroma/` se mantiene en `.gitignore` --
    NO se versiona en el repo público de GitHub. El índice de Chroma
    (con el texto literal de los chunks, no solo los embeddings) se
    construye y se usa en local/despliegue directo, pero nunca viaja
    por el repo público. Motivo explícito: no es "precaución" genérica,
    es la consecuencia directa de que casi la mitad del corpus (79/161,
    49%, dictámenes 2007-2016) no tiene ninguna licencia abierta -- solo
    la política de copyright propia de EFSA, que ni siquiera cubre uso
    comercial ni redistribución pública clara -- y la otra mitad
    (82/161, CC BY-ND 2016-2025) está pensada para redistribuir el
    artículo completo sin cambios, no fragmentos trocedados. La opción
    "Opción A, índice horneado" (más abajo) se mantiene para el
    **despliegue** (HF Spaces/Streamlit Cloud), no para el repo fuente
    de GitHub -- son empaquetados distintos, no lo confundas al leer esa
    decisión.
- **Estructura real de los PDFs, verificada abriendo 3 documentos
  completos antes de diseñar el chunking (sesión 17-ago-2026,
  continuación 2) -- diagnóstico únicamente, sin instalar ni ejecutar
  nada de embeddings.** Muestra deliberadamente heterogénea: uno corto
  (`sinE_10.2903_j.efsa.2011.1996.pdf`, 5 páginas, 41 KB, un
  "Statement"), uno largo (`E338-E343-E450_10.2903_j.efsa.2019.5674.pdf`,
  156 páginas, 16 MB, re-evaluación de grupo de fosfatos), uno mediano
  con `discussion_is_boilerplate=True` en el campo corto de `END_SUM`
  (`E507-E508-E509-E511_10.2903_j.efsa.2019.5751.pdf`, 51 páginas,
  5,4 MB, grupo de cloruros).
  - **Los "Statement" cortos (5 pp.) tienen una estructura mínima y
    estable:** Abstract, Table of Contents, Background, Terms of
    Reference, Evaluation, References -- sin tablas de datos, sin
    secciones numeradas jerárquicamente. Buen caso para chunking
    trivial (el documento entero cabe en pocos chunks).
  - **Los "Scientific Opinion" largos (51-156 pp.) tienen una jerarquía
    de encabezados numerados profunda** (hasta 4 niveles, ej. `3.5.7.
    Genotoxicity`, `3.10.2. Derivation of a chemical-speciﬁc adjustment
    factor`) -- un splitter que respete encabezados de sección (en vez
    de solo tamaño de ventana) puede apoyarse en este patrón para
    fronteras de chunk semánticamente sensatas, verificado con `grep`
    de patrones `^[0-9]+(\.[0-9]+)*\.?\s+[A-Z]` contra el texto
    extraído -- consistente en los 2 documentos largos inspeccionados.
  - **Confirmado el caso que preocupaba: tablas grandes de exposición
    dietética se rompen mal con extracción de texto plano
    (`pdftotext`).** Ejemplo real, `Table 5a` del documento de fosfatos
    (7 columnas de grupos de población × 2 escenarios × percentil mean/
    95th): `pdftotext` linealiza la tabla en texto corrido donde los
    encabezados de columna ("Infants below 16 weeks", "Toddlers",
    "Adults"...) quedan separados de sus valores numéricos por líneas
    de por medio, sin ninguna marca de qué número corresponde a qué
    columna -- un splitter de texto plano por caracteres/tokens
    trocearía esta tabla en fragmentos sin sentido tabular reconstruible
    (un `Table N` cada uno de los 12 documentos largos inspeccionados
    contra el índice de tablas -- 12 en el documento de fosfatos, 9 en
    el de cloruros). **Implicación para el diseño del chunking (no
    resuelto en esta sesión, solo señalado):** vale la pena decidir
    explícitamente si las tablas se excluyen del RAG narrativo (el dato
    cuantitativo estructurado ya viene de OpenFoodTox, no de los PDFs,
    según la separación estructurado/narrativo ya decidida más abajo) o
    si se intenta una extracción de tablas separada (ej.
    `pdfplumber`/`camelot`) -- no zanjado, pendiente de decidir al
    escribir el chunker.
  - **Hallazgo no buscado, mientras se inspeccionaba el documento de
    cloruros: el PDF tiene su PROPIA sección `4. Discussion` numerada,
    de varios párrafos** ("Hydrochloric acid (E 507), potassium
    chloride (E 508)... are authorised food additives... previously
    evaluated by the SCF in 1991... Chlorides occurred in the normal
    diet...") -- **más larga y más rica que el campo corto
    `END_SUM.Discussion.Discussion`** que alimenta
    `discussion_text`/`discussion_is_boilerplate` en
    `OpinionReference` (ver más arriba, sección sobre ese campo). Este
    dossier concreto tiene `discussion_is_boilerplate=True` en el campo
    de `END_SUM` (párrafo corto/genérico), pero el PDF sí contiene una
    sección de discusión sustantiva propia -- **confirma que el
    pipeline de PDFs+RAG (pendiente #5) no es redundante con el campo
    `discussion_text` ya integrado (pendiente #3, cerrado): son dos
    fuentes de discusión distintas, una corta y estructurada desde el
    xlsx, otra larga y solo disponible trocenado desde el PDF.** No
    asumir que `discussion_is_boilerplate=True` en el campo del xlsx
    implica que el PDF tampoco tiene discusión sustantiva -- es lo
    contrario en este caso concreto.
- **PyPDFLoader vs PyMuPDFLoader sobre el PDF de fosfatos (E338-E343-E450,
  156 páginas) -- comparación pedida explícitamente antes de escribir el
  chunker, no se había hecho hasta esta sesión (17-ago-2026, continuación
  8). `pymupdf` instalado solo en el venv local para esta prueba, NO
  añadido a `requirements.txt` todavía -- eso es parte de implementar el
  pipeline, no de esta comparación.** Ambos cargados con
  `langchain_community.document_loaders` (ya en `requirements.txt`
  -- `pypdf` sí, `pymupdf` no).
  - **Velocidad:** PyPDFLoader 4,2s para las 156 páginas; PyMuPDFLoader
    0,5s -- **~8x más rápido**. Sobre 161 PDFs (algunos de 100+ páginas,
    ver "Estructura real de los PDFs" arriba) esto es una diferencia de
    minutos de indexado, no bloqueante pero real.
  - **Fidelidad del texto -- diferencia decisiva, no marginal.**
    PyPDFLoader inserta un espacio espurio en medio de palabras que
    contienen el glifo de ligadura "ﬁ"/"ﬂ" del PDF (ej. "scientific" →
    "scienti ﬁc", "defined" → "de ﬁned", "specific" → "speci ﬁc").
    Contado sobre 17 palabras conocidas por sufrir este problema
    (`scientific`, `specific`, `defined`, `classified`, `identified`,
    `significant`, `efficacy`, `sufficient`, `confirmed`, `modified`,
    `justified`, `reflected`, `specifications`, `classification`,
    `reflects`, `justification`, `affinity` -- excluidas
    `findings`/`fibre`/`fixed` del recuento por tener la ligadura al
    inicio de la palabra, lo que hace indistinguible el glitch de un
    salto de línea normal antes de la palabra): **PyPDFLoader = 402
    palabras rotas en todo el documento; PyMuPDFLoader = 0.** (`scienti
    ﬁc` sola aparece rota 64 veces con PyPDFLoader, 0 con PyMuPDFLoader,
    68 veces intacta). Coincide con el recuento total de caracteres del
    documento completo: PyPDFLoader 655.733 caracteres vs PyMuPDFLoader
    652.233 -- las ~3.500 palabras rotas de más son exactamente los
    espacios espurios insertados.
  - **Tabla 5a específicamente (la que preocupaba desde la inspección de
    estructura de PDFs, ver arriba) -- ninguno de los dos "mantiene los
    encabezados cerca de sus valores" en el sentido de asociar
    explícitamente etiqueta:valor.** Ambos extraen los 7 encabezados de
    columna (Infants below 16 weeks / Infants 12wk-11mo / Toddlers /
    Children / Adolescents / Adults / Elderly) como un bloque, seguido
    de cada fila de datos con sus 7 valores en el MISMO ORDEN que los
    encabezados (verificado dígito a dígito: "Mean 349 198–998
    446–1554..." se corresponde 1:1 en orden con las 7 columnas en
    ambos loaders) -- pero ninguno reconstruye la tabla como
    tabla, solo preserva el orden de lectura del PDF subyacente. La
    diferencia entre los dos está en CÓMO se agrupa esa secuencia en
    líneas de texto:
    - **PyPDFLoader agrupa toda la fila en una sola línea** (ej. la fila
      "Mean" completa con sus 7 valores en una línea de texto) -- más
      resistente a que un splitter por tamaño de chunk corte la fila
      por la mitad.
    - **PyMuPDFLoader pone cada celda en su propia línea** (7 líneas
      solo para los valores de "Mean", más las 7 del header) -- más
      expuesto a que un splitter corte a mitad de fila si el límite de
      chunk cae entre dos celdas de la misma fila.
    - **Implicación, no resuelta en esta sesión:** este trade-off de
      layout de tabla es un problema de estrategia de chunking (chunks
      grandes alrededor de tablas detectadas, o excluir tablas del RAG
      narrativo como ya se apuntó en el hallazgo de estructura de PDFs
      de arriba), no algo que la elección de loader resuelva por sí
      sola -- ningún loader de texto plano "sabe" qué es una tabla.
  - **DECISIÓN: PyMuPDFLoader como loader por defecto del pipeline.**
    Con evidencia, no por preferencia teórica: gana claramente en
    fidelidad de texto (0 vs 402 palabras rotas, medido, no estimado) y
    en velocidad (~8x), que pesan más para la calidad del RAG (embeddings
    y LLM leyendo texto correcto) que la ligera desventaja de
    fragmentación de tablas en más líneas -- desventaja que de todos
    modos hay que mitigar a nivel de estrategia de chunking
    independientemente del loader elegido. **No implementado en el
    pipeline todavía** -- añadir `pymupdf` a `requirements.txt` y
    cambiar el loader es tarea de cuando se escriba el chunker, no de
    esta sesión.
- **Tratamiento de tablas en el chunking -- decisión con evidencia
  (sesión 17-ago-2026, continuación 9), tres opciones sobre la mesa
  (A: detectar y excluir del texto narrativo; B: extraer aparte con
  librería especializada tipo `pdfplumber`/`camelot`, como metadato
  distinto; C: aceptar la fragmentación y confiar en el contexto
  narrativo alrededor). Ninguna se descartó por intuición -- las tres
  se evaluaron con datos concretos antes de decidir.**
  - **Evidencia 1 -- las tablas no son un caso raro, son la norma:**
    escaneados los 161 PDFs con PyMuPDF (~23s), **146/161 (91%)** tienen
    al menos una tabla detectada (patrón `Table N:`), mediana de **7
    tablas por documento**, hasta 23 en el dossier de aspartamo. Esto
    descarta tratar el problema como marginal -- cualquier decisión
    aquí afecta a la inmensa mayoría del corpus.
  - **Evidencia 2 -- qué contienen esas tablas, y que OpenFoodTox NO las
    cubre (verificado, no asumido):** muestreadas 207 leyendas de tabla
    en 25 documentos al azar. Predominan MPLs (niveles máximos
    permitidos) por categoría de alimento, especificaciones de pureza,
    "population groups considered for exposure estimates", "summary of
    dietary exposure" y -- relevante para la diferenciación de este
    proyecto -- **"qualitative evaluation of influence of uncertainties
    on the dietary exposure estimate"**. Un caso (Red 2G, E128) tenía
    tablas de datos crudos de tumores/cálculos BMDL, la base misma de
    la derivación del ADI. `OpenFoodTox` (`FLEX_SUM.ToxRefValues`) solo
    aporta el valor escalar de ADI + `JustificationAndComments` como
    texto libre corto -- **nada del contenido de estas tablas está en
    los campos estructurados**, así que el supuesto de partida de la
    Opción A ("Nodo 4 ya tiene los datos numéricos") NO es válido por
    defecto -- había que comprobarlo, y solo es cierto para el ADI en
    sí, no para el desglose de exposición ni las especificaciones ni
    las tablas de estudios toxicológicos subyacentes.
  - **CASO A VIGILAR, no bloqueante para la decisión de hoy (anotado
    sesión 17-ago-2026, continuación 10, a petición del usuario):**
    Red 2G (E128) es cualitativamente distinto del resto de ejemplos de
    esta Evidencia 2 -- sus tablas de datos crudos de tumores/cálculos
    BMDL son la BASE PRIMARIA de la derivación del ADI, no un
    desglose secundario como las tablas de MPLs o de exposición por
    subgrupo. La Evidencia 3 (el Abstract restata la conclusión) se
    verificó para tablas de EXPOSICIÓN (fosfatos, cloruros) -- no se ha
    comprobado si un Abstract restata con el mismo detalle el
    razonamiento de una tabla de BMDL/incidencia de tumores subyacente
    al ADI; es plausible que no, porque ese tipo de detalle
    (dosis-respuesta, significación estadística por dosis) rara vez
    cabe en un resumen de una página. Perder esa tabla es más delicado
    que perder una de MPLs -- si en algún momento se hace QA manual del
    contenido narrativo que genera el Nodo 4, **priorizar revisar el
    caso de Red 2G (E128, `data/raw/pdfs/E128_10.2903_j.efsa.2007.515.pdf`)
    en concreto**, para confirmar si la Opción A deja al Nodo 4 sin
    fundamento suficiente para explicar el efecto crítico/NOAEL de esta
    sustancia en particular, no solo su valor final de ADI.
  - **Evidencia 3 -- hallazgo que sí sostiene la Opción A pese a lo
    anterior: la conclusión clave de esas tablas suele estar YA en
    prosa en el Abstract (página 1, prácticamente garantizado en
    cualquier chunking razonable).** Verificado directamente, no
    supuesto: el Abstract (página 1) del PDF de fosfatos dice
    textualmente *"Exposure to phosphates... ranged from 251 mg
    P/person per day in infants to 1,625 mg P/person per day for
    adults... exposure estimates exceeded the proposed ADI for
    infants, toddlers and other children..."* -- la conclusión
    cuantitativa Y cualitativa de la Tabla 5a (que está en la página 42,
    lejos en el documento) ya está en prosa en la página 1. Mismo
    patrón confirmado en el documento de cloruros (rango de exposición
    2-42 mg/kg bw/día por grupo de edad + comparación con el valor de
    referencia, también en el Abstract). Estructura estándar de
    abstract científico (resumir el hallazgo antes de detallarlo), no
    casualidad de estos 2 casos concretos -- pero solo verificado en 2
    documentos, no en el corpus completo.
  - **Evidencia 4 -- Opción B probada de verdad con `pdfplumber`, no
    descartada por intuición: falla de forma silenciosa, no solo
    costosa.** Instalado `pdfplumber` (solo en el venv local para la
    prueba, no en `requirements.txt`) y ejecutado
    `page.extract_tables()` sobre la página exacta de la Tabla 5a.
    Resultado: SÍ reconstruye correctamente pares fila/columna dentro
    de cada bloque (mejor que PyPDFLoader/PyMuPDFLoader en eso), pero
    **fragmenta la tabla visualmente única en 4 sub-tablas
    desconectadas** (una por bloque de escenario -- "regulatory maximum
    level", "brand-loyal", "non-brand-loyal" -- sin ninguna relación
    explícita entre ellas y el encabezado) **y pierde silenciosamente
    la columna "the elderly" -- 6 de 7 columnas extraídas, sin ningún
    error ni aviso**. Verificado dígito a dígito contra la extracción
    de texto plano de la misma tabla (ver el hallazgo de PyPDFLoader
    vs PyMuPDFLoader más arriba), que sí conserva las 7 columnas en
    orden. Con 1.137 tablas de layouts heterogéneos en todo el corpus
    (recuento de la Evidencia 1), una solución de producción con
    `pdfplumber`/`camelot` exigiría lógica de reensamblado + validación
    por documento, con riesgo demostrado (no hipotético) de perder
    datos sin que nada lo señale -- más peligroso que admitir
    explícitamente que la tabla no está, dada la regla del proyecto de
    no inventar/malrepresentar valores numéricos.
  - **DECISIÓN: Opción A -- detectar y excluir las tablas del texto
    narrativo que se trocea para el vector store.** No por ser la más
    simple, sino porque la Evidencia 3 muestra que la conclusión que
    de verdad importa para este proyecto (hallazgo cualitativo +
    rango cuantitativo agregado, comparado con el ADI) sobrevive en el
    Abstract sin necesidad de la tabla cruda, mientras que la Opción B
    tiene un coste de ingeniería real y un modo de fallo silencioso ya
    demostrado (Evidencia 4), y la Opción C asume que el contexto
    "alrededor" de la tabla compensa cuando en realidad la prosa que
    compensa (el Abstract) está lejos en el documento -- no es
    "contexto alrededor" en el sentido de proximidad de chunk, es un
    chunk distinto que de todos modos se recupera por su cuenta si el
    chunking incluye la sección de Abstract/Resumen.
  - **LIMITACIÓN ACEPTADA EXPLÍCITAMENTE, no oculta (documentar también
    en `docs/.../LIMITATIONS.md` cuando se implemente el chunker):**
    se pierde el desglose fino por subgrupo poblacional bajo cada
    escenario de exposición (ej. el valor exacto de exposición en
    "Toddlers, escenario no-brand-loyal, percentil 95" no será
    recuperable vía RAG, solo el rango agregado que sí aparece en el
    Abstract). Aceptable para una herramienta de exploración de
    literatura regulatoria (el objetivo declarado del proyecto, ver
    CLAUDE.md arriba), no para una calculadora de exposición detallada
    por subgrupo, que nunca fue el objetivo. Si una evaluación futura
    encuentra demanda real de ese nivel de detalle, revisar con Opción
    B presupuestando el coste de reensamblado/validación real medido
    aquí, no repitiendo la prueba de `extract_tables()` a secas.
  - **No implementado todavía** -- la detección/exclusión de bloques de
    tabla al trocear el texto (ej. usando el mismo patrón `Table N:` +
    heurística de dónde termina el bloque, o los bloques de layout que
    ya expone PyMuPDF) queda como tarea de cuando se escriba el
    chunker, no de esta sesión. `pdfplumber` instalado solo en el venv
    local para la prueba, no añadido a `requirements.txt`.
- **Splitter consciente de estructura vs `RecursiveCharacterTextSplitter`
  plano -- decisión con evidencia (sesión 17-ago-2026, continuación 11),
  verificado contra los mismos 3 PDFs de referencia (corto/statement,
  largo/fosfatos, mediano/cloruros) antes de recomendar, no por defecto
  teórico.**
  - **Intento fallido, probado antes de descartarlo: regex de
    encabezados numerados sobre el texto plano de PyMuPDF.** Un regex
    de una sola línea (`^\d+\.\s+[A-Z]...`) da 0 coincidencias en los 3
    documentos -- no porque no haya estructura, sino porque
    `page.get_text()` (lo que expone `PyMuPDFLoader`) separa el número
    del título en líneas DISTINTAS: `"1.\nIntroduction\nThe present
    opinion deals..."`, nunca `"1. Introduction"` en una sola línea.
    Ampliar el regex a "número solo en su propia línea" SÍ encuentra
    estructura real, pero con mucho ruido: **725 coincidencias en el
    documento largo (fosfatos), 229 en el mediano (cloruros)** --
    verificado que la mayoría son falsos positivos (números de página
    de pie de página tipo "EFSA Journal 2019;17(6):5674" precedidos de
    un número suelto, y artefactos de la tabla de contenidos con guías
    de puntos donde el número de página queda en su propia línea justo
    antes del número de sección real). Un regex sobre texto plano NO es
    una señal limpia por sí sola -- mismo tipo de riesgo/coste ya
    encontrado con `pdfplumber` para tablas (ver el hallazgo anterior):
    exigiría filtrar ruido de cabeceras/pies/TOC por documento, sin
    garantía de generalizar.
  - **Señal que SÍ funciona, verificada en los 3 documentos con la API
    rica de PyMuPDF (`page.get_text("dict")`, NO el texto plano de
    `page.get_text()`/`PyMuPDFLoader`): tamaño y familia de fuente
    distinguen encabezado de cuerpo de forma limpia y consistente.**
    | Documento | Fuente de encabezado | Fuente de cuerpo |
    |---|---|---|
    | Corto (statement) | 12pt `TimesNewRomanPS-BoldMT` | 10-11pt `TimesNewRomanPSMT` |
    | Largo (fosfatos) | 12pt `AdvTT...` con sufijo `.B` (variante bold) | 10pt `AdvTT...` sin sufijo |
    | Mediano (cloruros) | mismo patrón que el largo | mismo patrón que el largo |

    Verificado además que el tamaño en puntos NO es la señal más
    robusta en solitario (el caso "BACKGROUND" del documento corto
    aparece renderizado con versalitas -- la "B" inicial a 12pt, el
    resto "ACKGROUND" a 9.5pt, ambos en la misma fuente bold) -- **la
    familia de fuente (variante bold vs regular) es la señal más
    fiable de las dos**, el tamaño por sí solo puede variar dentro del
    mismo encabezado por trucos de renderizado tipográfico.
  - **Dos convenciones de encabezado distintas, no una -- cualquier
    lógica de detección tiene que cubrir ambas:**
    1. **Statement corto:** sin numeración, 4 secciones planas en
       mayúsculas (BACKGROUND / TERMS OF REFERENCE / EVALUATION /
       REFERENCES).
    2. **Scientific Opinion (largo y mediano):** jerarquía numerada
       hasta 4 niveles (`1.1.1.1`, `3.10.3`) -- **idéntica convención
       de estilo entre los dos documentos, no es casualidad de uno
       solo** -- es la plantilla estándar del EFSA Journal para este
       tipo de output (ver "Estructura real de los PDFs" más arriba,
       mismo hallazgo de jerarquía numerada profunda, ahora confirmado
       también en el documento de cloruros, no solo en el de
       fosfatos). Una lógica de detección basada solo en el patrón de
       numeración NO cubriría el tipo "Statement" -- la señal de
       fuente (bold vs regular) sí generaliza a los dos, verificado.
  - **DECISIÓN: `RecursiveCharacterTextSplitter` plano para los LÍMITES
    de chunk; extracción de `section_heading` como metadato aparte, vía
    `get_text("dict")`, no vía el regex de texto plano ni vía el propio
    `PyMuPDFLoader`.** No hay evidencia de que un splitter basado en el
    regex numerado (poco fiable, con el ruido medido arriba) produzca
    mejores límites de chunk que uno que ya respeta párrafos/frases por
    defecto -- así que no se justifica asumir ese riesgo para la
    partición del texto en sí. Pero la estructura de secciones SÍ es
    real y fiable vía la señal de fuente, y vale la pena capturarla
    como metadato (`section_heading`, ya reservado en el esquema de
    `RetrievedChunk`/metadatos de Chroma diseñado en sesiones
    anteriores) -- relevante en concreto para este proyecto porque el
    RAG se apoya en recuperar contenido de secciones como "Discussion"
    (la discusión de incertidumbre que es la razón de ser narrativa del
    proyecto, ver más arriba), no cualquier texto suelto.
  - **IMPORTANTE para quien escriba el chunker (pendiente #5): hace
    falta la API rica de PyMuPDF (`page.get_text("dict")`, con tamaño y
    familia de fuente por span), NO basta con el `PyMuPDFLoader` de
    `langchain_community` ya decidido como loader -- ese loader solo
    expone `page_content` como texto plano, sin metadatos de fuente.**
    Esto implica un paso de extracción ADICIONAL con PyMuPDF
    directamente (`fitz`/`pymupdf`, ya instalado para la prueba de esta
    sesión) para poblar `section_heading`, en paralelo al uso de
    `PyMuPDFLoader` (o en su lugar) para el texto que alimenta al
    splitter -- no una única pasada. La lógica de detección de
    encabezados debe cubrir **ambas convenciones** (numerada tipo
    Scientific Opinion Y plana en mayúsculas tipo Statement), no
    asumir que todos los documentos siguen el patrón numerado --
    verificado que un tercio+ del corpus son "Statement"/otros tipos
    sin esa numeración (ver la variedad de `doc_type` ya manejada en
    `current_reference_value_opinion`/`VALID_OPINION_TYPES`).
  - **No implementado todavía** -- ni el splitter, ni la extracción de
    `section_heading` vía fuente. Diseño verificado y documentado,
    pendiente de escribir con el resto del chunker.
- **Chunker implementado (`ingestion/pdf_chunking.py`, sesión
  17-ago-2026 continuación 12) y validado en lote sobre 22 PDF (sesión
  18-ago-2026) -- dos hallazgos de calidad de texto, uno arreglado y uno
  documentado como limitación de baja prioridad, no arreglado a
  propósito:**
  - **ARREGLADO -- guiones suaves (U+00AD) incrustados literalmente en
    el texto extraído, específico de la plantilla EFSA/Wiley más
    reciente.** Detectado inicialmente sobre 2 PDF de 2024-2025 (Shellac
    E904, Acesulfame K E950) frente a PDF más antiguos (aspartamo 2013,
    cloruros 2019, TiO2 2021): **474 de 1.170 bloques** del PDF de
    acesulfame K contenían el carácter (1.168 apariciones en total,
    esencialmente todo el documento) -- "Re-evaluation" salía como
    "Re-\xadevaluation" en el texto de cada chunk. **CIFRA CORREGIDA
    tras escanear los 161 PDF completos (sesión 18-ago-2026): no son 2,
    son 10** -- el lote de validación de 22 PDF solo había incluido 2 de
    los 10 casos reales por azar de la selección. Lista completa (todos
    2023-2025, ninguno anterior): E1204 (2025, 310 apariciones), E174
    (2025, 561), E472C (2025, 584), E551 (2024, 919), E904/Shellac
    (2024, 463), E943A-E943B-E944 (2025, 171), E950/Acesulfame K (2025,
    1.357), E954/sacarina (2024, 1.749), E961/neotamo (2025, 1.250),
    E968 (2023, solo 8 -- el único caso marginal, el resto de dossiers
    de esa sustancia en el corpus son de 2013 y no lo tienen). CERO en
    cualquier PDF de 2013-2023 comprobado fuera de esta lista -- cambio
    real de plantilla de Wiley a partir de 2023/2024, no un problema
    preexistente sin detectar. Es un carácter de formato invisible,
    nunca información real -- seguro quitarlo siempre. Fix (sin cambios,
    ya escrito antes de conocer el alcance real): `extract_raw_blocks`
    quita `\xad` del texto de cada bloque antes de cualquier otro
    procesado (deduplicación, detección de encabezado, troceo) -- al ser
    genérico (no específico de un PDF), **cubre los 10 sin necesidad de
    tocar código** -- verificado explícitamente sobre los 10 tras
    conocer la cifra real: 0 apariciones restantes en cada uno.
  - **"ActualText with no position. Text may be lost or mispositioned."
    -- INVESTIGADO A FONDO en los 7 PDF afectados (sesión 18-ago-2026,
    continuación 2), CERRADO: sin pérdida de texto real en ningún caso,
    aunque el patrón no es "solo aparece en portada" como sugería el
    primer spot-check.** Advertencia propia de MuPDF
    (`pymupdf.TOOLS.mupdf_warnings()`, no capturable por `sys.stderr`
    normal). Aparece en los MISMOS 7 de los 10 PDF del hallazgo de
    guiones suaves de 2023-2025 (E1204, E174-2025, E472C,
    E943A-E943B-E944, E950, E961, E968-2023) -- 9 a 33 apariciones cada
    uno, ausente en PDF de plantilla anterior.
    - **Metodología:** para cada uno de los 7, se identificaron las
      páginas exactas donde salta el aviso
      (`pymupdf.TOOLS.reset_mupdf_warnings()` por página + comprobar
      `'ActualText' in mupdf_warnings()`), se inspeccionó qué contenido
      hay en cada una (portada, tabla de contenidos, tabla de apéndice,
      o texto narrativo real), y para las páginas de texto narrativo
      real se leyó el texto COMPLETO extraído buscando truncamiento,
      repetición o incoherencia gramatical -- no solo "la densidad de
      caracteres parece normal" (el criterio, más débil, del primer
      spot-check).
    - **Resultado por documento:** E950/Acesulfame K y E1204/pullulan
      -- solo portada/CONTENTS (páginas 1-2), como ya se sabía.
      E472C y E943A-E943B-E944 -- portada, tabla de contenidos (entradas
      con líneas de puntos) y tablas de apéndice, ninguna página de
      texto narrativo real. E961/neotamo -- portada + páginas 57-62,
      TODAS dentro del Apéndice F/G (análisis BMD, tabla QSAR) --
      verificada directamete la página 57 (la de menor densidad de
      caracteres, marcada sospechosa por el heurístico de densidad):
      es literalmente una tabla de datos QSAR (columnas de compuestos,
      "NA", códigos "NC-00751"...), la baja densidad es simplemente que
      una tabla tiene menos texto corrido que prosa, no pérdida --
      y de todos modos el contenido de tabla ya se excluye del texto
      narrativo por Opción A, independientemente de este aviso.
    - **Los 2 casos genuinos de texto narrativo real marcado por el
      aviso -- verificados sin pérdida, leyendo el texto completo:**
      **E174/plata, páginas 12, 15 y 16** -- Sección "Overall conclusion
      on technical data", 3.4 "Biological and toxicological data
      submitted", 3.4.1 "Genotoxicity", y la propia **Sección 4
      "DISCUSSION"** completa -- párrafos largos, gramaticalmente
      coherentes, sin frases cortadas a mitad ni saltos de contenido,
      citas y notas al pie (15, 16, 19...) todas presentes y en su
      sitio. **E968/eritritol, página 41** -- Sección 6 "CONCLUSIONS"
      (incluye el ADI de 0,5 g/kg pc/día y la conclusión de que la
      exposición lo supera) y Sección 7 "RECOMMENDATION", ambas
      completas y coherentes.
    - **Conclusión:** el aviso de MuPDF no se traduce en pérdida de
      texto real en ninguno de los 7 PDF, ni siquiera en las 2 páginas
      donde coincide con contenido narrativo sustantivo (Discussion,
      Conclusions) -- probablemente lo dispara algún otro elemento con
      estilo especial en esa misma página (nota al pie, subíndice,
      cabecera repetida) sin afectar la extracción de la prosa
      principal. **No requiere ninguna acción -- ni exclusión de chunk
      ni revisión manual.** Cerrado, no reabrir sin evidencia nueva de
      contenido realmente perdido (ej. una frase que corte a mitad al
      leer un chunk generado).
  - **NO ARREGLADO A PROPÓSITO -- título largo partido en dos bloques
    bold distintos, dando un `section_heading` fragmentado para ese
    chunk concreto** (ej. "chloride (E 511) as food additives" en vez
    del título completo "Re-evaluation of hydrochloric acid... as food
    additives"). Confirmado sistémico, no un caso raro: presente en 8
    de los 16 PDF del lote de validación de 18-ago-2026 (tartratos,
    nitritos, sorbatos, celulosas, dimetilpolisiloxano, sulfitos,
    silicatos de aluminio, TiO2) además de los 2 casos ya vistos
    (cloruros, fosfatos) -- todos de la plantilla EFSA/Wiley anterior a
    2024. **Trade-off confirmado con el bug de guiones suaves de
    arriba: los 2 PDF de la plantilla 2024+ (Shellac, Acesulfame K) NO
    tienen este problema** -- su título largo permanece en un solo
    bloque bold pese a envolver dos líneas -- pero sí tienen el
    problema de guiones suaves. Ninguna plantilla es limpia en los dos
    frentes a la vez; el guion suave se arregló porque corrompe el
    TEXTO narrativo de cada chunk del documento entero, mientras que el
    título partido solo afecta la ETIQUETA `section_heading` de un
    puñado de chunks (los del arranque del documento) -- sin pérdida de
    datos, confirmado dos veces (sesión de implementación + lote de 16
    PDF). Prioridad baja, no se arregla sin motivo nuevo (ej. si
    `section_heading` empieza a usarse para algo más que texto
    informativo de apoyo en el Nodo 4).
  - **Misma clase de problema, sin investigar más por ahora:** el
    statement de luteína (`sinE_10.2903_j.efsa.2012.2589.pdf`) produjo
    un par de encabezados de sección extraños ("level*", "reported
    use") -- probablemente fragmentos de leyenda/subtítulo adyacentes a
    una tabla, en negrita pero fuera del bbox que `find_tables()`
    detectó para esa tabla, así que no se excluyeron como contenido
    tabular. Mismo tipo de imprecisión cosmética que el título partido
    -- una etiqueta de sección rara para un chunk puntual, sin pérdida
    de datos ni de contenido narrativo real. No investigado a fondo
    -- anotado aquí para no tener que redescubrirlo si aparece de nuevo
    al escalar al corpus completo.
- **Mapeo sustancia→archivo para los PDFs multi-E-number -- CIFRA
  CORREGIDA (sesión 17-ago-2026, continuación 2): no son 29/161, son AL
  MENOS 36/161 (22%), y ninguna de las dos columnas del checklist
  (`sustancia`, `e_number`) es de fiar por sí sola para enumerar qué
  sustancias cubre un PDF.** El pendiente #5 de "Estado del código"
  decía "29 de los 161 PDFs cubren MÁS DE UN E-number", contado por `;`
  en la columna `e_number` del checklist -- verificado ahora que ese
  recuento subestima el problema real: comparando el número de nombres
  en la columna `sustancia` contra el número de códigos en `e_number`
  para las 161 filas, **36 filas tienen recuentos DISTINTOS entre las
  dos columnas** (no solo >1 en `e_number`). Caso más claro,
  investigado a fondo antes de generalizar la conclusión: el dictamen
  de ésteres de ácidos orgánicos de mono/diglicéridos (E472a-f, DOI
  `10.2903/j.efsa.2020.6032`) tiene **6 nombres de sustancia distintos
  en la columna `sustancia`** (acético, láctico, cítrico, tartárico,
  mono-/diacetil tartárico, mixto acético-tartárico) **pero solo 1
  código en `e_number` ("E472A")** -- el archivo PDF resultante se
  llama `E472A_10.2903_j.efsa.2020.6032.pdf`, sin rastro de que cubre
  también E472b-f. Esta fila NO tenía `;` en `e_number`, así que el
  recuento anterior de "29" no la contaba -- de ahí la corrección a 36.
  - **Causa raíz, verificada con las hojas reales (no solo
    inferida):** el título "Re-evaluation of acetic acid, lactic acid,
    citric acid, tartaric acid, mono- and diacetyltartaric acid, mixed
    acetic and tartaric acid esters of mono- and diglycerides of fatty
    acids (E 472a-f)" aparece en **6 filas DISTINTAS de `DOSSIER`**,
    cada una con su propio `Document UUID` -- no una fila con 6
    E-numbers. `unique_reevaluation_opinions()`/
    `current_reevaluation_corpus()` deduplican por texto de título, así
    que solo UNA de esas 6 filas sobrevive al corpus final -- y esa
    fila concreta, seguida por su propia cadena de joins
    (`DOSSIER_DOCS` → `FLEX_SUM.ToxRefValues.Parent UUID` → `SUB`),
    enlaza a exactamente **1 sustancia** (verificado con las 6
    `Parent UUID` de las 6 filas hermanas, cada una resuelve a un
    `ChemicalName` distinto en `SUB` -- Acetic acid esters..., Citric
    acid esters..., Lactic acid esters..., Mono- and diacetyl tartaric
    acid esters..., Mixed acetic and tartaric acid esters..., Tartaric
    acid esters..., los 6 componentes de E472a-f). **La sustancia
    ligada al `Document UUID` que sobrevive el dedup es solo 1 de las
    6 reales -- ni la columna `e_number` del checklist (que hereda ese
    mismo problema) ni el join estructural desde el `Document UUID`
    deduplicado bastan por sí solos.**
  - **Técnica verificada que SÍ recupera las 6 sustancias completas:**
    agrupar las filas de `DOSSIER` por DOI (o por título) ANTES de la
    deduplicación de `unique_reevaluation_opinions()`/
    `current_reevaluation_corpus()`, y para cada fila hermana del grupo
    resolver su propio enlace `DOSSIER_DOCS` →
    `FLEX_SUM.ToxRefValues.Parent UUID` → `SUB` por separado, tomando
    la UNIÓN de sustancias resultante. Verificado con el caso E472a-f:
    las 6 filas hermanas resuelven, cada una individualmente, a 1 de
    las 6 sustancias reales -- la unión da las 6, no 1. **Esta técnica
    NO está implementada todavía** (solo verificada manualmente para
    este caso) -- es el diseño propuesto para el paso de indexación,
    ver más abajo.
  - **Diseño de esquema de metadatos por chunk propuesto (SOLO DISEÑO,
    nada implementado) para soportar la relación muchos-a-muchos
    archivo↔sustancia:**
    - Enumerar sustancias por archivo con la técnica de arriba (unión
      de sustancias vía filas hermanas pre-dedup), no con las columnas
      del checklist ni con el `Document UUID` post-dedup en solitario.
    - Chroma exige valores de metadato escalares (str/int/float/bool)
      por entrada -- no admite listas ni dicts anidados como valor de
      metadato filtrable. Para un chunk que sirve a N sustancias
      (N>1 en 36/161 documentos), **la opción recomendada es indexar
      ese chunk N veces** (mismo texto/embedding, N entradas de
      metadato distintas, una por sustancia), cada entrada con:
      - `substance_uuid` (str, singular, el campo por el que se filtra
        en Nodo 2 dado el UUID resuelto en Nodo 1) -- exact-match
        eficiente en `where`, no requiere parsear un campo delimitado.
      - `e_number` (str, singular, human-readable, ej. "E472A").
      - `chemical_name` (str, singular).
      - `chunk_group_id` (str, compartido entre las N copias del mismo
        chunk -- para deduplicar en la capa de aplicación si una
        consulta recupera el mismo texto vía más de una sustancia, ej.
        una pregunta que menciona dos sustancias del mismo dictamen de
        grupo).
      - `dossier_uuid` (str, el `Document UUID` post-dedup del corpus,
        para trazabilidad hacia `current_reference_value_opinion`).
      - `pdf_filename`, `doi`, `section_heading` (si se detecta, ver el
        patrón numerado de encabezados de arriba), `page_number`.
      - `is_group_dossier` (bool, `True` si el archivo cubre >1
        sustancia -- para que el Nodo 4 pueda avisar explícitamente
        "este fragmento viene de un dictamen de grupo que también
        cubre X, Y, Z" si es relevante).
    - **Alternativa descartada, documentada para no reabrirla sin
      motivo nuevo:** un único chunk con `substance_uuids` como string
      delimitado por `;` (una fila en vez de N) ahorra espacio de
      almacenamiento, pero Chroma no puede hacer *exact-match* eficiente
      sobre un substring dentro de un campo delimitado -- forzaría a
      sobre-recuperar por otros criterios y filtrar en Python después,
      perdiendo la ventaja de filtrar en la propia consulta a Chroma.
      A esta escala (161 PDFs, decenas de miles de chunks como mucho)
      la duplicación de embeddings N veces es barata en almacenamiento
      y simplifica el filtrado -- no hay razón de rendimiento para
      preferir la alternativa delimitada aquí.
- **Alcance completo del bug de deduplicación por título en
  `unique_reevaluation_opinions()` -- investigado sesión 17-ago-2026
  (continuación 3), antes de diseñar el chunking. CORRIGE el bullet
  anterior: la cifra correcta de sustancias realmente perdidas NO es la
  que sale de contar cualquier `Parent UUID` enlazado (eso da 134, muy
  inflado), es 46, tras filtrar por presencia real de ADI.**
  - **Metodología:** sobre `reevaluation_dossiers()` SIN deduplicar
    (338 filas, 162 títulos únicos -- 161 DOIs únicos, la única
    discrepancia título/DOI es el caso ya conocido de la errata de
    saccharin, verificado que agrupar por DOI en vez de por título no
    cambia ningún otro resultado de este análisis), se agrupó por
    título y se comparó, para cada grupo con >1 fila DOSSIER, la UNIÓN
    de sustancias enlazadas vía `DOSSIER_DOCS` →
    `FLEX_SUM.ToxRefValues.Parent UUID` de TODAS las filas hermanas
    contra las sustancias visibles solo a través de la fila que
    sobrevive el `drop_duplicates` por título.
  - **105 de los 162 títulos (65%) tienen exactamente 1 fila DOSSIER
    -- sin ambigüedad, el bug no les afecta en absoluto.** 57 títulos
    (35%) tienen >1 fila hermana.
  - **Corrección metodológica importante, encontrada al investigar el
    caso de nitritos (`Re-evaluation of potassium nitrite (E 249) and
    sodium nitrite (E 250)`, 20 filas DOSSIER hermanas):** contar
    ciegamente todos los `Parent UUID` enlazados vía
    `FLEX_SUM.ToxRefValues` da 20 "sustancias" para ese título -- pero
    verificado con las hojas reales que **17 de esas 20 son compuestos
    N-nitroso (N-nitrosodimetilamina y similares), sustancias de
    referencia toxicológica citadas dentro de la caracterización de
    peligro del dictamen, NO aditivos alimentarios que el PDF cubra
    con su propio E-number.** Señal estructural que las distingue,
    consistente con un patrón que el propio código ya usa en otro
    sitio (`_adi_row_for_toxref_uuids`, `current_reference_value_opinion`):
    las 3 sustancias reales (Sodium nitrite, Potassium nitrite,
    Nitrites) tienen `AcceptableDailyIntake.Adi.lowerValue` poblado
    para su fila de `FLEX_SUM.ToxRefValues` ligada a este dossier; las
    17 N-nitroso NO (`Adi.lowerValue` vacío, enlazadas en cambio vía
    `OtherReferenceValues.ReferenceValueDescriptor == 'other:'`, un
    valor de referencia distinto de un ADI, típico de sustancias
    genotóxicas evaluadas por margen de exposición). **Sin este
    filtro, cualquier recuento de "sustancias por dossier" basado en
    `Parent UUID` a secas sobreestima sistemáticamente en dossiers de
    contaminantes/subproductos (nitritos, y previsiblemente cualquier
    dossier que discuta formación de nitrosaminas, acrilamida u otros
    contaminantes de proceso dentro de la misma discusión).**
  - **Cifra corregida, con el filtro de ADI aplicado (mismo criterio
    `.notna()` sobre `Adi.lowerValue` que ya usa
    `_adi_row_for_toxref_uuids`):** de los 57 títulos con >1 fila
    hermana, **solo 20 (12% del corpus de 162) son genuinamente
    multi-sustancia** (unión de sustancias con ADI propio > 1); los
    otros 37 resuelven a ≤1 sustancia real con ADI (filas hermanas
    administrativas/duplicadas sin pérdida real, o cuyo único enlace
    con ADI está en una sola fila). **Entre esos 20 títulos: 62
    sustancias reales en total (unión), de las cuales solo 16 son
    visibles a través de la única fila que sobrevive el dedup --
    46 sustancias con ADI propio quedan invisibles** si solo se mira
    la fila superviviente por título. Casos con más pérdida: tartratos
    E334-E337+E354 (7 sustancias, 6 perdidas), glutamato E620-E625 (6
    sustancias, 5 perdidas), ésteres de sorbitán E491-E495 (5
    sustancias, 4 perdidas), colorantes caramelo E150a-d (5 sustancias
    de 8 filas hermanas, 4 perdidas). El caso E472a-f investigado antes
    (6 sustancias, 5 perdidas) es uno más de esta lista, no un caso
    aislado -- pero tampoco el peor.
  - **Comparación pedida por el usuario --
    ¿`current_reevaluation_corpus()` evita este bug o lo comparte?
    Respuesta con matiz, verificada empíricamente, no solo leyendo el
    código:** como DataFrame de salida (filas = documentos/PDFs),
    **`current_reevaluation_corpus()` NO evita el bug -- lo hereda
    intacto.** Confirmado ejecutándolo: para el título de nitritos
    devuelve exactamente **1 fila** (igual que
    `unique_reevaluation_opinions()`), no 3 ni 20 -- porque parte de
    `base = self.unique_reevaluation_opinions()` y su lógica de
    sustitución solo intercambia filas completas para 6 casos ya
    conocidos (Grupo A/B, ver más arriba), nunca EXPANDE un título a
    varias filas. Los 162 dossiers que devuelve siguen siendo 162
    documentos/títulos, no 162+46 sustancias.
    - **PERO, y esto es lo que sí es aprovechable:** el CÓDIGO de
      `current_reevaluation_corpus()` ya construye internamente, como
      paso intermedio, exactamente la enumeración de sustancias
      correcta -- `substance_uuids = sorted(set(toxref_rows["Parent
      UUID"].dropna()))` se calcula a partir de `linked` sobre
      `all_matched_uuids = self.reevaluation_dossiers()["Document
      UUID"]` (el conjunto SIN deduplicar, todas las filas hermanas),
      no sobre `base_uuids` (el conjunto ya deduplicado) -- así que
      SÍ ve las sustancias de todas las filas hermanas, incluidas las
      que el dedup por título descarta. Ese paso intermedio se usa
      solo para decidir 6 sustituciones puntuales y luego se descarta
      -- nunca se expone como resultado.
  - **Conclusión para el diseño del chunking, respondiendo
    directamente a la pregunta planteada:** la solución NO es arreglar
    `unique_reevaluation_opinions()` (colapsar a 1 fila por título es
    el comportamiento correcto para esa función -- cuenta documentos
    físicos/PDFs, no sustancias), NI usar
    `current_reevaluation_corpus()` como fuente directa de sustancias
    (su output tiene el mismo problema). **La solución es extraer la
    TÉCNICA que `current_reevaluation_corpus()` ya usa internamente
    (agrupar por título/DOI sobre `reevaluation_dossiers()` SIN
    deduplicar, resolver el enlace de sustancia de cada fila hermana
    por separado filtrando por `Adi.lowerValue` no nulo, tomar la
    unión) como una función nueva y reutilizable** -- ni reconstruir
    desde las columnas del checklist (ninguna de las dos es fiable por
    sí sola, ver el bullet anterior con el caso E472a-f invertido:
    `sustancia` sobre-reporta para nitritos si no se filtra por ADI,
    `e_number` sub-reporta para E472a-f) ni asumir que
    `current_reevaluation_corpus()` ya resuelve esto por tener
    "current" en el nombre.
  - **IMPLEMENTADO (sesión 17-ago-2026, continuación 5):**
    `OpenFoodToxStore.substances_per_dossier()` en
    `ingestion/openfoodtox.py` -- la técnica de arriba extraída como
    método público, devuelve `{Document UUID del corpus:
    [DossierSubstance, ...]}` (nuevo dataclass `DossierSubstance`,
    `substance_uuid` + `chemical_name`). Recibe opcionalmente el
    DataFrame de corpus a usar (por defecto
    `current_reevaluation_corpus()`); para cada dossier agrupa TODAS las
    filas hermanas de `reevaluation_dossiers()` sin deduplicar que
    comparten título (más la propia fila del corpus, necesario para los
    6 dossiers que `current_reevaluation_corpus()` sustituye -- esos NO
    están en `reevaluation_dossiers()` bajo ningún título, así que sin
    esa fila explícita se quedarían sin sustancia). **No se ha tocado
    `unique_reevaluation_opinions()` ni `current_reevaluation_corpus()`
    -- tal como se pidió, solo se añade la función nueva.**
    - Verificado contra las hojas reales (no solo contra la lógica):
      nitritos → exactamente `{Nitrites, Potassium nitrite, Sodium
      nitrite}` (los 17 compuestos N-nitroso quedan excluidos por el
      filtro de ADI); tartratos → las 7 sales del grupo E334-E337+E354;
      glutamato → las 6 sales del grupo E620-E625. Tests de regresión
      nuevos en `tests/test_openfoodtox_joins.py`
      (`test_substances_per_dossier_nitrites_excludes_toxicological_references`,
      `test_substances_per_dossier_tartrates_group_returns_all_seven`,
      `test_substances_per_dossier_glutamates_group_returns_all_six`) --
      **15/15 tests pasan** (12 previos + 3 nuevos).
    - **Cifra global de la función, corrida sobre el corpus completo de
      162 dossiers:** 99 dossiers sin ninguna sustancia con ADI propio
      ligada (incluye casos legítimos como dióxido de titanio E171,
      verificado explícitamente: su dossier vigente de 2021 tiene
      `adi_value=None` en `current_reference_value_opinion` -- EFSA no
      pudo establecer un ADI por preocupaciones de genotoxicidad, no es
      un fallo del enlace), 43 con exactamente 1, 20 con más de 1 (los
      mismos 20 títulos identificados en el diagnóstico), sumando 105
      enlaces sustancia-dossier en total (62 de ellos concentrados en
      esos 20 títulos multi-sustancia, coincide exactamente con la
      cifra del diagnóstico previo).
    - **Límite de alcance a tener en cuenta al diseñar el chunking (no
      resuelto aquí, solo señalado):** `substances_per_dossier()`
      devuelve lista vacía para un dossier sin ADI propio, incluso
      cuando la identidad de la sustancia no es ambigua en absoluto
      (caso TiO2: 1 sola sustancia, 1 sola fila DOSSIER para ese título,
      pero 0 en el resultado porque no tiene ADI). Para el chunking, la
      identidad de sustancia de estos dossiers de sustancia única sin
      ADI habrá que resolverla por otra vía (ej. `substance_uuid_by_name`
      directamente, ya que no hay ambigüedad de grupo que resolver) --
      esta función está pensada para el caso multi-sustancia, no como
      sustituto universal de "¿qué sustancia cubre este dossier?".
    - **Nota de rendimiento, no bloqueante:** cada llamada recalcula
      todo desde cero (sin cache) -- unos 27s para los 162 dossiers del
      corpus completo contra el xlsx real en esta máquina. Aceptable
      para uso puntual/scripts de indexación (se llama una vez por
      ejecución del pipeline de chunking, no en un bucle de consulta),
      pero si se acaba llamando repetidamente conviene memoizarla (ej.
      `functools.lru_cache` o guardar el resultado) antes de usarla
      dentro de un flujo interactivo.
- **Los 99 dossiers donde `substances_per_dossier()` devuelve lista
  vacía -- desglosados completos (sesión 17-ago-2026, continuación 6),
  antes de escribir el pipeline de chunking.** Corrige el marco de la
  pregunta original ("¿cuántos son TiO2-like vs. necesitan
  `substance_uuid_by_name`?"): la mayoría de los 99 NO necesitan
  `substance_uuid_by_name` en absoluto -- se resuelven con la MISMA
  técnica de `substances_per_dossier()`, solo quitando el filtro de ADI.
  Solo un puñado muy pequeño (2-3 de 162) necesita de verdad resolución
  por nombre de título.
  - **73/99: sustancia única, sin ADI (patrón TiO2)** -- el enlace
    `DOSSIER_DOCS` → `FLEX_SUM.ToxRefValues.Parent UUID` SIGUE
    existiendo y resuelve a exactamente 1 `Parent UUID`, la fila
    simplemente no tiene `Adi.lowerValue` relleno para esa sustancia en
    ese dossier -- verificado que no es una falla del enlace, es un
    dato real (ADI "no especificada"/"no establecida", común en gomas,
    ceras, colorantes minerales -- goma arábiga, goma xantana,
    dióxido de titanio, plata, oro, óxidos de hierro, ceras varias,
    entre 73 en total). Lista completa (nombre de sustancia resuelto vía
    el mismo enlace toxref, no por texto de título):
    4-Hexylresorcinol, Acesulfame K, Anthocyanins, Ascorbyl palmitate,
    Azorubine/Carmoisine, Beetroot Red (2 dossiers: extension of use +
    re-evaluation), Beta-carotene (2: extension of use + statement),
    Beta-cyclodextrin, Brown FK, Calcium carbonate, Calcium
    lignosulphonate (40-65), Candelilla wax, Carnauba wax,
    Chlorophyllins, Chlorophylls, Citric acid esters of mono- and
    diglycerides, Dimethyl dicarbonate, Disodium
    5-acetylamino-4-hydroxy-3-(phenylazo)naphthalene-2,7-disulphonate,
    Dodecyl gallate, Erythritol (3 dossiers), Erythrosine B, Gellan gum,
    Glycerol, Glycerol esters of wood rosins, Gold, Guar gum, Gum arabic
    (2), Hexamethylene tetramine, Iodized ethyl esters of poppy seed
    oil, Iron oxides and hydroxides, Isobutane, Karaya gum, Lecithins
    (2), Litholrubine BK, Locust bean gum (2), Microcrystalline wax,
    Mono-and diglycerides of fatty acids, Montan acid esters, Neotame,
    Octyl gallate, Oxidised soya bean oil interacted with mono- and
    diglycerides (E 479b), Polyethylene waxes oxidised, Polyglycerol
    esters of fatty acids, Polyglycerol polyricinoleate, Pullulan,
    Rosemary extract liquid, Silicon dioxide (2), Silver (2), Sodium
    carboxymethyl cellulose, Sodium propionate, Soybean hemicellulose,
    Starch sodium octenyl succinate, Stearyl tartrate, Sucralose
    (extension of use, distinto de la sucralosa sin enlace del bloque de
    4 sin toxref más abajo), Tara gum, Tartrazine, Thaumatin, Tin (II)
    chloride, Titanium dioxide (2), Tragacanth, Vegetable carbon Black,
    Xanthan gum (2). **No ambiguos en absoluto** -- la identidad de
    sustancia es tan fiable como en los dossiers con ADI, solo falta el
    número.
  - **22/99: MULTI-sustancia, NINGUNA con ADI** -- dossiers de grupo
    genuinos (alginatos, sulfatos de aluminio, cloruros, celulosas,
    carbonato cálcico, ácido ascórbico, sales de ácidos grasos, pectina,
    riboflavina, silicatos, sacarina [antes de la corrección de
    agrupación por DOI, ver más abajo], sulfatos, konjac, tocoferoles,
    propionatos, carotenos mixtos, glicerol/3-MCPD, polivinilpirrolidona,
    palmitato/estearato de ascorbilo, nitritos/nitrato del "Statement on
    nitrites in meat products" [distinto del dossier de nitritos con ADI
    ya cubierto en Tier 1], clorofilinas de cobre, silicato de aluminio
    sódico/potásico) -- de 2 a 10 sustancias cada uno (celulosas es el
    mayor, 10). Igual de fiables en identidad que el caso ADI-bearing,
    **necesitan el mismo tratamiento de "N copias por chunk"** que los
    20 dossiers multi-sustancia de Tier 1 -- no son un caso aparte para
    el diseño de metadatos, solo llegan por una ruta distinta (sin ADI).
  - **4/99 (3 tras la corrección de agrupación por DOI, ver siguiente
    punto): SIN ningún enlace toxref en absoluto** -- ni sustancia ni
    ADI. Coincide exactamente con el hallazgo ya documentado en el
    diagnóstico del "híbrido puro" (sesión anterior): "Statement on the
    validity of the conclusions of a mouse carcinogenicity study on
    sucralose", "Re-evaluation of shellac (E 904)...", "Re-evaluation of
    saccharin and its sodium, potassium and calcium salts (E 954)..."
    (la variante de título SIN la errata de espacio), "Statement on two
    recent scientific articles on the safety of artificial sweeteners".
  - **Corrección encontrada al investigar el caso de saccharin: agrupar
    las filas hermanas por TÍTULO (como hace `substances_per_dossier()`
    hoy) en vez de por DOI se puede evitar.** Las dos variantes de
    título de saccharin (con/sin espacio, errata ya documentada, MISMO
    DOI `10.2903/j.efsa.2024.9044`) tienen 1 y 4 filas hermanas
    respectivamente si se agrupa por título -- la variante "sin toxref"
    de la lista de arriba es la de 1 fila. **Agrupando por DOI en vez de
    por título, ambas variantes comparten las 5 filas hermanas
    completas y resuelven a las 4 sales de sacarina** (verificado con
    las hojas reales). Comprobado además que cambiar la clave de
    agrupación de título a DOI **no cambia NINGÚN otro resultado ya
    verificado** (nitritos, tartratos, glutamato, y los demás 160
    dossiers dan exactamente los mismos siblings por título que por DOI
    -- solo saccharin difiere, por la errata ya conocida). **Mejora de
    diseño propuesta, no implementada:** `substances_per_dossier()`
    debería agrupar por DOI, no por título -- estrictamente más seguro,
    cero regresiones detectadas, y cierra este caso sin necesitar
    heurística de título.
  - **Con esa mejora, quedan 3/162 dossiers genuinamente sin ningún
    enlace estructural:** sucralosa (statement sobre un estudio de
    carcinogenicidad), goma laca/shellac, y el statement genérico sobre
    "two recent scientific articles" (aspartamo + un estudio de
    refrescos). **De estos 3, `substance_uuid_by_name()` resuelve 2
    limpiamente por nombre extraído del título** (`"Sucralose"` →
    UUID válido, `"Shellac"` → UUID válido -- ambos verificados). **El
    tercero (el statement genérico) NO tiene ningún nombre de sustancia
    ni E-number en el título** -- menciona "aspartame" solo en el
    cuerpo/abstract, no en el título, y discute genéricamente "artificial
    sweeteners" sin nombrar una sustancia concreta con E-number.
    Aunque `substance_uuid_by_name("Aspartame")` resolvería un UUID
    válido, hacerlo automáticamente sería una suposición editorial (el
    documento SÍ es sobre todo sobre aspartamo, pero inferirlo solo del
    título es un salto que ningún patrón de texto de este proyecto ha
    necesitado hasta ahora) -- **no forzar esta inferencia
    automáticamente, dejarlo sin sustancia estructurada (o como
    excepción curada a mano si el usuario decide que vale la pena para
    1 solo documento).**
  - **Diseño de resolución de sustancia por dossier para el indexado,
    en 3 niveles, SOLO PROPUESTO -- nada implementado:**
    1. **Nivel 1 (mayor confianza):** `substances_per_dossier()` tal
       como existe hoy (con ADI) -- 63/162 dossiers (43 sustancia única
       + 20 multi-sustancia), 105 enlaces sustancia-dossier con ADI real
       adjunto.
    2. **Nivel 2 (misma fiabilidad de identidad, sin ADI):** la MISMA
       función/técnica con el filtro de ADI desactivado -- propuesto
       como parámetro nuevo `require_adi: bool = True` en
       `substances_per_dossier()` (no como función separada, para no
       duplicar la lógica de agrupación de hermanos). Resuelve 96/162
       adicionales (73 sustancia única + 22 multi + el caso de
       saccharin tras el cambio de agrupación por DOI) -- mismo
       mecanismo estructural que el Nivel 1, sin diferencia de
       confianza en la IDENTIDAD de la sustancia, solo ausencia del
       valor numérico de ADI.
    3. **Nivel 3 (heurística de título, MISMA CLASE DE RIESGO que otros
       heurísticos de este proyecto -- ver el resto de este documento):**
       solo para los dossiers donde Nivel 1 y 2 devuelven vacío (3/162
       tras el fix de agrupación por DOI) -- `substance_uuid_by_name()`
       contra un nombre de sustancia extraído del título. Resuelve 2 de
       esos 3 (sucralosa, shellac). El 1 restante (statement genérico de
       edulcorantes) se queda sin sustancia estructurada -- ver arriba
       por qué no forzarlo.
    - **Cobertura total con los 3 niveles: 161/162 dossiers con al menos
      1 sustancia resuelta, 1/162 sin sustancia estructurada (indexado
      igualmente por su contenido narrativo/título, solo sin filtro de
      sustancia en los metadatos del chunk).**
    - **Campo de metadato nuevo propuesto** (extiende el esquema ya
      diseñado en el bullet anterior): `substance_resolution_tier`
      (`1`/`2`/`3`, entero) en cada entrada de metadato por sustancia --
      permite al Nodo 4 distinguir "ADI real disponible" (tier 1) de
      "sustancia identificada pero sin ADI establecida" (tier 2, ej.
      TiO2 -- coincide con la comunicación de riesgo que el proyecto ya
      necesita para estos casos, no es nueva carga) de "identidad de
      sustancia inferida por heurística de título, verificar con más
      cuidado" (tier 3). Los dossiers de Tier 2/3 con `adi_value=None`
      ya se comunican hoy vía `current_reference_value_opinion`
      devolviendo `adi_value=None` -- este campo nuevo es sobre la
      CONFIANZA en la sustancia, no sobre si tiene ADI (eso ya se sabe
      por otro campo).
    - **IMPLEMENTADO (sesión 17-ago-2026, continuación 12):** los 3
      niveles están implementados en
      `ingestion/pdf_chunking.py::resolve_dossier_substances` --
      `substances_per_dossier(require_adi=True)` (Nivel 1) ->
      `substances_per_dossier(require_adi=False)` (Nivel 2, el
      parámetro `require_adi` que aquí seguía "propuesto" ya existe en
      `openfoodtox.py`) -> coincidencia de nombre de sustancia como
      palabra completa dentro del título, sobre TODA la hoja `SUB`
      (Nivel 3, `_guess_substance_by_title`). Verificado con los 5 PDF
      procesados en esta sesión (chlorides -> 4 sustancias tier 2,
      phosphates -> 1 sustancia tier 1, aspartamo E951 -> 1 sustancia
      tier 1, más 2 dossiers de `--limit 2`) -- ningún caso tier 3
      encontrado todavía en la práctica (Sucralose/Shellac, los 2 casos
      conocidos que sí deberían resolver en tier 3, no se han vuelto a
      probar explícitamente en esta sesión).
    - **DECISIÓN TOMADA sobre el 1/162 sin sustancia estructurada
      (statement/sweeteners, "Statement on two recent scientific
      articles on the safety of artificial sweeteners",
      `sinE_10.2903_j.efsa.2011.1996.pdf`, DOI
      `10.2903/j.efsa.2011.1996`) -- confirmado por el usuario tras ver
      el resultado del pipeline: se mantiene el comportamiento actual,
      NO se le asigna un `substance_uuid` vacío/sentinela para forzar
      que produzca `RetrievedChunk`. Este documento queda FUERA del
      índice de retrieval (Nodo 2) **por diseño, no por bug** -- ningún
      nivel de resolución (estructural con o sin ADI, ni coincidencia
      de nombre en el título) puede identificar de qué sustancia trata
      sin inventar una relación de identidad que el dato no respalda
      (el título no menciona ningún E-number ni nombre químico con
      suficiente especificidad -- "artificial sweeteners" en plural,
      sin concretar). Es la MISMA disciplina que ya rige los 3 niveles
      (preferir "sin sustancia resuelta" a una identidad inferida sin
      respaldo) llevada a su conclusión lógica en el único caso donde
      ni siquiera el heurístico más débil (Nivel 3) encuentra nada.
      Documentado aquí explícitamente para que quien retome el pipeline
      no lo trate como una laguna a rellenar: sus chunks de texto SÍ se
      generan (`DossierChunkingResult.chunks`), simplemente no se
      envuelven en `RetrievedChunk` ni entran en el índice vectorial
      cuando se implemente ese paso -- sigue siendo el único dossier de
      los 162 en esta situación (no se ha encontrado ningún otro caso
      nuevo al procesar los 5 PDF de esta sesión).

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
  - **Matiz añadido tras la investigación de licencia de los PDFs
    (sesión 17-ago-2026, ver "Hallazgos verificados"):** "empaquetado
    como parte del repo/imagen de despliegue" son dos destinos
    DISTINTOS, no lo mismo -- decisión tomada: el índice de Chroma
    (texto literal de los chunks, no solo embeddings) SÍ va en la
    imagen/artefacto de despliegue, pero NO en el repo público de
    GitHub (`data/chroma/` se queda en `.gitignore`). Motivo: casi la
    mitad del corpus (79/161, dictámenes 2007-2016) no tiene ninguna
    licencia abierta, solo la política de copyright propia de EFSA sin
    cobertura clara de redistribución pública; la otra mitad (CC BY-ND
    2016-2025) está pensada para el artículo completo sin cambios, no
    fragmentos. Si en el futuro se reabre esta decisión, hazlo con
    nueva evidencia de licencia, no por conveniencia de despliegue.
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
  ~$0.0005-0.0014 por consulta según franja horaria -- cifra recalculada
  y CONFIRMADA (sesión 18-ago-2026) contra la fuente de pricing actual
  (misma tarifa punta/valle actualizada 16-ago-2026) incluyendo ya el
  contexto real de `retrieved_chunks` (k=3-5 chunks recuperados, ~150-180
  tokens/chunk medidos sobre el pipeline de chunking implementado en la
  sesión anterior -- ver "Estado del código", pendiente #5). Mismo orden
  de magnitud que la estimación previa de $0.001-0.002/consulta, que se
  había medido con `retrieved_chunks` vacío (Nodo 2 sin implementar
  todavía en ese momento) -- el coste de incluir el contexto narrativo
  real no cambia la conclusión de presupuesto. Presupuesto de
  referencia: 6-7€/mes cubre miles de consultas incluso en el peor caso.
  Se evaluó Kimi K2.6/K3 como alternativa: K2.6 es más caro que DeepSeek
  y con peor puntuación en benchmarks generales; K3 iguala casi a
  modelos de frontera pero a 15-20x el coste. Se mantiene DeepSeek por
  defecto. **Antes de cambiar de proveedor por benchmarks genéricos**,
  construir un set de 10-15 casos de prueba del Nodo 4 (con las reglas
  de comunicación de riesgo) y medir tasa de cumplimiento real, no
  decidir por índices de inteligencia genéricos que no miden eso.
  **Esta estimación de coste asume "thinking" desactivado** (ver bullet
  de arriba). Medido en sesión con el mismo prompt del Nodo 4: 799
  tokens de salida con "thinking" activo (esfuerzo "high", casi todo
  `reasoning_content`) frente a 365 con "thinking" desactivado -- un
  desplegado con el default de DeepSeek sin darse cuenta habría corrido
  con un coste real ~2-3x el estimado aquí, no por un cambio de precio
  del proveedor sino por un parámetro de la llamada.
- **Contrato Nodo 2 → Nodo 4 (`retrieved_chunks`): `RetrievedChunk`, no
  `list[str]` -- fijado en sesión 17-ago-2026 (continuación 7), ANTES de
  escribir el Nodo 2, precisamente para que quien lo escriba (aunque sea
  en otra sesión) no tenga que rehacer este contrato después.**
  `GraphState.retrieved_chunks` era `list[str]` -- texto plano, sin
  metadatos -- lo cual hacía IMPOSIBLE que el Nodo 4 supiera nada sobre
  la procedencia de un fragmento (qué sustancia, qué dossier, con qué
  fiabilidad se resolvió esa sustancia). Motivado directamente por el
  diseño de comunicación de riesgo por `substance_resolution_tier`
  (ver "Hallazgos verificados", diseño de resolución en 3 niveles) --
  el tier 3 (identidad de sustancia inferida por título, no por enlace
  estructural) solo puede comunicarse al LLM si el Nodo 2 lo transporta
  hasta el Nodo 4, y con `list[str]` no había dónde ponerlo.
  - **Nuevo dataclass `RetrievedChunk` en `graph/nodes.py`:**
    ```python
    @dataclass(frozen=True)
    class RetrievedChunk:
        text: str
        substance_uuid: str
        chemical_name: str
        dossier_uuid: str
        dossier_title: str
        substance_resolution_tier: int  # 1, 2 o 3 -- ver substances_per_dossier()
        doi: str | None = None
        section_heading: str | None = None
        page_number: int | None = None
    ```
    Campos que el Nodo 4 usa HOY (tras esta sesión): `text` y
    `substance_resolution_tier` (para el aviso inline en fragmentos
    tier 3, ver `_format_retrieved_chunks`). El resto (`chemical_name`,
    `dossier_uuid`, `dossier_title`, `doi`, `section_heading`,
    `page_number`) NO se consume todavía en ningún punto del código --
    se fijan ahora porque son la misma información que ya va a estar en
    los metadatos de cada chunk de Chroma (ver el esquema de metadatos
    diseñado en "Hallazgos verificados", `substance_uuid`/`e_number`/
    `chemical_name`/`chunk_group_id`/`dossier_uuid`/`pdf_filename`/
    `doi`/`section_heading`/`page_number`/`is_group_dossier`) -- el Nodo
    2, cuando se escriba, solo tiene que copiar esos campos de metadato
    de Chroma a `RetrievedChunk`, no inventar de dónde sacarlos.
    `is_group_dossier`/`e_number`/`pdf_filename`/`chunk_group_id` del
    esquema de Chroma NO están en `RetrievedChunk` -- no se ha
    encontrado todavía un uso en el Nodo 4 para ellos; añadirlos si
    aparece una necesidad concreta, no por simetría con el esquema de
    Chroma.
  - **`GraphState.retrieved_chunks: list[RetrievedChunk]`** (antes
    `list[str]`) -- cambio de tipo ya aplicado en `graph/nodes.py` en
    esta sesión, aunque el Nodo 2 (`hybrid_retrieval_node`) siga sin
    implementar (`NotImplementedError`). **Cuando se escriba el Nodo 2,
    DEBE devolver `list[RetrievedChunk]`, nunca strings sueltos** -- este
    contrato es la razón de ser de esta entrada del documento, no lo
    reabras sin motivo nuevo.
  - **`_format_retrieved_chunks` actualizado** para leer
    `substance_resolution_tier` de cada chunk y anteponer un aviso
    inline SOLO cuando `tier == 3` -- mismo patrón que ya usa
    `discussion_line` en `_format_structured_result` (instrucción
    incrustada en el propio dato del prompt de usuario, no una regla
    nueva en `NODE_4_GROUNDING_RULES`/`NODE_4_SAFETY_COMMUNICATION_RULES`,
    que NO se han tocado).

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
   **A tener en cuenta en el diseño del mapeo sustancia→archivo -- CIFRA
   CORREGIDA DOS VECES, no repitas ninguna de las anteriores: NO son 29
   (recuento inicial por `;` en `e_number` del checklist), NI 36
   (recuento intermedio por mismatch de columnas del checklist,
   sesión 17-ago-2026 continuación 2) -- la cifra validada con las
   hojas reales y filtrando por ADI real (sesión 17-ago-2026
   continuación 3) es: **20 títulos del corpus de 162 (12%) son
   genuinamente multi-sustancia, con 46 sustancias con ADI propio
   invisibles si solo se mira la fila superviviente del dedup por
   título.** Ni las columnas del checklist ni el `Document UUID` post-
   dedup de `unique_reevaluation_opinions()`/`current_reevaluation_corpus()`
   son fuente fiable -- ver "Hallazgos verificados" para la técnica
   verificada que sí recupera la lista completa (agrupar por título/DOI
   SIN deduplicar + filtrar por `Adi.lowerValue` no nulo + unión), y
   para por qué `current_reevaluation_corpus()` NO resuelve esto pese
   al nombre (su output tiene el mismo problema; solo su código interno
   usa la técnica correcta, sin exponerla).** No asumir un archivo por
   E-number 1:1 al indexar -- el chunking/vector store necesita poder
   resolver "¿en qué PDF(s) está la sustancia X?" como una relación
   muchos-a-uno (una sustancia -> un archivo, pero un archivo ->
   potencialmente varias sustancias).
   **RESUELTO (sesión 17-ago-2026, continuación 5):** la técnica ya está
   extraída como `OpenFoodToxStore.substances_per_dossier()` en
   `ingestion/openfoodtox.py`, con 3 tests de regresión verificados
   contra el xlsx real (nitritos/tartratos/glutamato).
   **Cobertura de los 99 dossiers que esa función deja vacíos --
   diagnosticada y diseñada, TODAVÍA NO implementada (continuación 6):**
   ver "Hallazgos verificados" para el desglose completo (73 sustancia
   única sin ADI tipo TiO2, 22 multi-sustancia sin ADI, 3 sin ningún
   enlace estructural tras arreglar la agrupación por DOI en vez de por
   título) y el diseño de resolución en 3 niveles (Nivel 1 = con ADI,
   Nivel 2 = mismo enlace sin exigir ADI, Nivel 3 =
   `substance_uuid_by_name()`/coincidencia de nombre en título) que
   cubre 161 de 162 dossiers, dejando 1 sin sustancia estructurada a
   propósito -- ese 1/162 (statement/sweeteners) se queda fuera del
   índice de retrieval POR DISEÑO, decisión confirmada por el usuario,
   ver el bullet "DECISIÓN TOMADA sobre el 1/162..." más arriba.
   **IMPLEMENTADO (sesión 17-ago-2026, continuación 12) --
   `ingestion/pdf_chunking.py`:** extracción de texto vía PyMuPDF
   directo (no el wrapper `PyMuPDFLoader`, necesita bbox/fuente por span
   -- ver el módulo para el hallazgo nuevo de esta sesión sobre pérdida
   de espacios en modo "dict" para ciertas fuentes bold incrustadas),
   detección de `section_heading` vía fuente tipográfica (cubre ambas
   convenciones, numerada y plana en mayúsculas), exclusión de tablas
   (bbox de `page.find_tables()` + patrón de leyenda "Table N:"),
   troceo con `RecursiveCharacterTextSplitter` por sección, y
   resolución de sustancia en 3 niveles
   (`resolve_dossier_substances`, con `substances_per_dossier(require_adi=...)`
   ya implementado con el parámetro que aquí seguía "propuesto").
   Script de ejecución: `scripts/build_chunk_index.py` (`--dry-run`/
   `--limit`/`--pdf`, no toca embeddings ni Chroma). Validado sobre 5
   PDF (los 3 de referencia + aspartamo E951 + 2 más vía `--limit 2`) --
   ver PROGRESS.md para el detalle de la sesión.
   **CORPUS COMPLETO PROCESADO (sesión 18-ago-2026): 161/161 PDF, sin
   errores, sin ningún PDF con 0 chunks.** 35.991 chunks, 67.827
   `RetrievedChunk` (dossier-sustancia-chunk); distribución de
   sustancias resueltas por tier (a nivel dossier-sustancia, 256 pares
   en total): tier 1 (con ADI) 105, tier 2 (enlace sin ADI) 149, tier 3
   (nombre en título) 2 -- exactamente los 2 casos conocidos
   (Shellac, sucralosa statement), ningún tier 3 nuevo inesperado. Un
   solo dossier sin sustancia resuelta, el mismo 1/162 ya documentado
   como excluido por diseño (`sinE_10.2903_j.efsa.2011.1996.pdf`).
   **Persistido en `data/processed/chunks.jsonl`** (gitignored, mismo
   motivo de licencia que `data/chroma/` -- texto literal de los PDF,
   ver la decisión de licencia más arriba): 67.827 líneas JSON, una por
   (chunk, sustancia resuelta), con campos de `RetrievedChunk` +
   `pdf_filename` + `chunk_group_id` (id compartido entre las N copias
   del mismo chunk que sirven a distintas sustancias -- el mismo
   esquema "N copias por chunk" ya diseñado para Chroma, ver
   "Hallazgos verificados"). Generado con
   `python scripts/build_chunk_index.py --all --save-jsonl
   data/processed/chunks.jsonl` -- `_run_all` escribe y hace `flush()`
   tras cada dossier, así que un fallo a mitad de la corrida (o del
   siguiente paso, embeddings) no obliga a reprocesar los PDF ya
   hechos. Existe también `--save-preview` (JSON con ejemplos, para
   inspección puntual, no pensado para el corpus completo -- usar
   `--save-jsonl` para eso). **Pendiente dentro de este mismo punto,
   todavía sin implementar:** el paso de indexado en Chroma en sí
   (embeddings + `chromadb`), que es el que de verdad desbloquea el
   Nodo 2 -- `data/processed/chunks.jsonl` es el material de partida
   para ese paso, no un índice vectorial consultable todavía.
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
