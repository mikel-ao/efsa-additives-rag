# Decisiones verificadas — efsa-additives-rag

Este documento es el detalle evidencial completo de la sección "Hallazgos
verificados" de `CLAUDE.md`: cifras exactas, tablas, verificación contra
las hojas reales de OpenFoodTox, y los bloques `[CORRECCIÓN...]` que
enmiendan hallazgos anteriores de este mismo documento. Nada de esto está
resumido — es el texto íntegro tal como se escribió sesión a sesión.

`CLAUDE.md` mantiene un resumen de 1-2 frases por hallazgo, en el mismo
orden que aparecen aquí, con un puntero a esta sección. Carga este archivo
cuando necesites el razonamiento completo detrás de una decisión (por
qué se descartó una alternativa, qué casos concretos se verificaron, qué
cifra es la vigente frente a una anterior ya superada) — para trabajo de
sesión a sesión normal, el resumen de `CLAUDE.md` suele bastar.

**No reordenes ni resumas el contenido de este archivo al editarlo** —
es la fuente de verdad íntegra; si un hallazgo cambia, corrígelo aquí
igual que se haría en `CLAUDE.md` antes de esta reestructuración, y
actualiza el resumen correspondiente en `CLAUDE.md` si el resumen deja
de reflejarlo.

---

## Hallazgos verificados (detalle completo)


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
  - **DIFERIDO EXPLÍCITAMENTE (sesión 18-ago-2026), con evidencia de
    prevalencia, no por omisión -- ver pendiente #6 de "Estado del
    código" para la decisión completa y el razonamiento de por qué se
    difiere.** Escaneadas las 247 sustancias con enlace estructural
    resoluble del corpus (94 tier 1 + 153 tier 2/3): **0 casos
    ambiguos** con un umbral de 90 días (y también 0 con 30 días) --
    el hueco de código es real, pero no se ha materializado en ningún
    dato real del corpus actual. Detalle completo en el pendiente #6.
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
    **[CORRECCIÓN, sesión 18-ago-2026 (auditoría general de
    CLAUDE.md/PROGRESS.md): la cifra 146/161 (91%) NO se ha podido
    reproducir.** Re-escaneados los 161 PDFs con el mismo patrón
    (`Table N:`) sobre texto plano y sobre texto en modo "blocks" (dos
    métodos de extracción, mismo resultado en ambos): **138/161 (86%)**.
    Probada también una variante más laxa del patrón (sin exigir los
    dos puntos, "Table N" a secas): 155/161 (96%) -- ninguna de las dos
    reproduce 146 exactamente, y 146 cae entre ambos límites sin que se
    haya identificado qué variante de método la produjo (no quedó
    guardado el script original de esa sesión). **No se borra la cifra
    original -- se deja marcada como NO VERIFICADA, cifra vigente para
    cualquier razonamiento posterior: 138/161 (86%)**, re-confirmada
    contra el xlsx real en la sesión de auditoría. La CONCLUSIÓN que
    esta evidencia sostenía (las tablas son la norma, no el caso raro,
    y cualquier decisión de tratamiento de tablas afecta a la inmensa
    mayoría del corpus) sigue siendo válida con cualquiera de las tres
    cifras -- 86-96% es "inmensa mayoría" en cualquier lectura -- así
    que la discrepancia no cambia la decisión tomada (Opción A), solo
    corrige el número citado. Mediana de tablas/documento y máximo en
    aspartamo (23) no re-verificados en esta auditoría -- solo la
    cifra de prevalencia (con/sin tabla) fue el objeto de la duda.]**
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
    - **ESQUEMA FINAL, IMPLEMENTADO (sesión 18-ago-2026) -- SIN
      `e_number`, decisión explícita del usuario.** Al escribir de
      verdad el indexado en Chroma se encontró que `e_number` (arriba)
      no tiene una fuente fiable a NIVEL DE SUSTANCIA: `SUB` no tiene
      ningún campo de E-number (ver pendiente #2 de "Estado del
      código", cerrado en esta misma sesión), y la única fuente
      disponible (patrón de texto en el título del dossier) es POR
      DOSSIER, no por sustancia -- en un dossier de grupo (ej.
      tartratos: 5 E-numbers en el título, 7 sustancias resueltas) no
      hay un mapeo 1:1 fiable entre cada E-number y cada
      `substance_uuid` sin inventar una relación de identidad que el
      dato no respalda -- MISMA disciplina que ya rige los 3 niveles de
      resolución de sustancia (preferir omitir a inventar). **Decisión:
      `e_number` NO forma parte del esquema de metadatos de Chroma.**
      `chemical_name` + `substance_uuid` siguen siendo el identificador
      fiable de sustancia por chunk. La resolución de E-numbers en
      preguntas de usuario (Nodo 1, ej. "E 951") queda para una tabla
      auxiliar futura E-number -> `substance_uuid` derivada aparte
      (con su propia verificación de los casos multi-sustancia), NO
      como metadato por chunk -- ver el pendiente #2 actualizado.
      **Esquema final de metadatos por entrada de Chroma** (uno por
      combinación chunk×sustancia resuelta, implementado en
      `ingestion/chroma_index.py`): `substance_uuid`, `chemical_name`,
      `dossier_uuid`, `dossier_title`, `substance_resolution_tier`
      (int), `doi`, `pdf_filename`, `chunk_group_id`, `is_group_dossier`
      (bool, `True` si el dossier tiene >1 sustancia resuelta) --
      siempre presentes en los 67.827 chunks del corpus persistido
      (`data/processed/chunks.jsonl`), 0 valores `None` para estos
      campos, verificado. `section_heading` (str) y `page_number` (int)
      también, pero con un guardado explícito: **Chroma rechaza `None`
      en metadatos con `TypeError` (verificado directamente, no
      asumido)** -- `section_heading` es `None` en 116/67.827 filas
      (0,17%, los chunks de portada antes del primer encabezado
      detectado), así que la clave se OMITE del diccionario de
      metadato en vez de escribir `None` -- confirmado que Chroma
      admite metadatos con claves distintas entre documentos de la
      MISMA colección sin problema (no exige un esquema uniforme).
      `page_number`/`doi` no necesitaron este guardado en la práctica
      (0 `None` en los 67.827), pero el código los trata igual por
      seguridad, no por necesidad medida.
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
- **Consumo de memoria de la app completa medido con datos reales
  (sesión 18-ago-2026), NO estimado -- bloquea el deploy en el tier
  gratuito de Streamlit Community Cloud tal como está el sistema hoy.**
  Pedido explícitamente antes de intentar el deploy (pendiente #8):
  medir RSS del proceso con Chroma (67.827 chunks) + modelo de
  embeddings + Streamlit corriendo + una consulta real ya resuelta.
  - **Primer intento -- `streamlit.testing.v1.AppTest` -- COLGADO, no
    completado.** Metodología elegida porque ejecuta el mismo
    `ui/app.py` a través del mismo `ScriptRunner` que usaría
    `streamlit run`, sin necesitar un navegador real (no había
    `playwright`/`selenium` instalados, y no se pidió instalarlos solo
    para esta medición). Cargó Streamlit (44,6 MB), renderizó la app
    (54,1 MB) y cargó el modelo de embeddings (`Loading weights: 100%`
    visible en el log) -- y ahí se quedó colgado más allá de 180s de
    timeout. **Diagnóstico realizado antes de abandonar el método, no
    descartado a ciegas:** una llamada de red aislada a la API de
    DeepSeek tardó 2,4s (no es un problema de red/sandbox); una llamada
    directa y completa a `answer_question()` FUERA de `AppTest` tardó
    39s de principio a fin y funcionó sin problemas. La diferencia
    apunta a que `AppTest` ejecuta el script en un hilo dedicado (no el
    hilo principal), y algo en la pila `torch`/`sentence-transformers`/
    `chromadb` se comporta de forma distinta (más lento hasta el punto
    de parecer colgado, o genuinamente en deadlock) fuera del hilo
    principal -- no investigado hasta la causa raíz exacta, porque
    había una alternativa más simple disponible (ver debajo) y el
    objetivo era medir memoria, no depurar `AppTest`. **Anotado aquí
    como aviso para el futuro:** si se retoma la idea de tests
    automatizados de `ui/app.py` con `AppTest` y alguna vez involucran
    el camino real de embeddings/Chroma (no solo mocks), probar primero
    con un timeout muy alto para descartar que sea solo lentitud y no
    un deadlock real antes de asumir que el método funciona.
  - **Bug real encontrado y arreglado durante el primer intento, antes
    de llegar al cuelgue de `AppTest`:** `_get_client_ip()`
    (`ui/app.py`) devolvía un valor no-`str` bajo el harness de test de
    Streamlit (probablemente porque `session_info.request` no es una
    request HTTP real ahí), que rompía `check_and_register_query()` al
    usarse como clave de un `dict` antes de `json.dumps` (`TypeError:
    keys must be str, int, float, bool or None, not MagicMock`). El
    docstring de la función ya prometía degradar a `"unknown"` ante
    cualquier fallo -- el `try/except` capturaba excepciones, pero no
    validaba que el valor devuelto por la ruta feliz fuera
    efectivamente un `str`. Arreglado con una comprobación de tipo
    explícita (`ip if isinstance(ip, str) and ip else "unknown"`) antes
    de devolver -- mismo contrato ya documentado, ahora cumplido de
    verdad en todos los casos, no solo en el camino de excepción.
  - **Método final -- descomposición en dos medidas reales, sin
    `AppTest`, con total transparencia sobre qué mide cada una:**
    1. `streamlit run src/efsa_rag/ui/app.py --server.headless true`
       lanzado como subproceso REAL (el comando literal que se pidió),
       con la app cargada y respondiendo (`curl` a `http://localhost`
       devuelve `200`) pero SIN ninguna consulta enviada todavía (nadie
       ha escrito en el `text_input`, así que el import perezoso de
       `graph.build` en `_render_answer` nunca se dispara) --
       **63,2 MB de RSS** (`/proc/<pid>/status`, `VmRSS`). Esto es el
       coste base real de "Streamlit corriendo con la app cargada",
       antes de tocar Chroma/embeddings/LLM.
    2. Un proceso Python normal que también importa `streamlit` (para
       no perder ese componente de la cifra) y luego ejecuta EXACTAMENTE
       el mismo camino que `_render_answer` -- `build_default_deps()`
       (carga xlsx + Chroma + modelo de embeddings + cliente LLM) +
       `build_graph(deps)` + una consulta real de extremo a extremo
       (`"What is the ADI of aspartame and what study is it based
       on?"`, la misma pregunta de referencia ya usada en el resto del
       proyecto) -- midiendo RSS en cada etapa:
       | Etapa | RSS |
       |---|---|
       | Intérprete arrancado | 9,3 MB |
       | tras `import streamlit` | 44,6 MB |
       | tras `import graph.build` (chromadb/sentence-transformers/langgraph/openai) | 157,7 MB |
       | tras `build_default_deps()` (xlsx + Chroma 67.827 chunks + modelo de embeddings + cliente LLM cargados, 10,2s) | **1.023,0 MB** |
       | tras compilar el grafo | 1.023,0 MB |
       | **tras UNA consulta real de extremo a extremo (29,6s)** | **1.870,4 MB** |
    - **`AppTest` (paso [2], "app cargada sin consulta") dio 54,1 MB --
      consistente con la medida del `streamlit run` real (63,2 MB,
      diferencia explicable por el servidor Tornado/websocket de un
      proceso real vs. el harness de test)** -- confirma que, hasta
      donde `AppTest` llegó a funcionar, sus números eran fiables; el
      problema era solo el cuelgue posterior, no que el método diera
      cifras falsas.
  - **Desglose fino de dónde sale el salto grande (medido aparte, SIN
    LLM, sin gastar tokens -- solo import + carga + una consulta de
    embeddings + `collection.query()`, dos veces, una con filtro
    `where` inexistente para confirmar que el filtrado en sí es
    barato):**
    | Paso | RSS acumulado | Delta |
    |---|---|---|
    | Intérprete | 9,3 MB | -- |
    | `import streamlit` | 44,6 MB | +35,3 MB |
    | `import torch` (dependencia de sentence-transformers) | 500,3 MB | **+455,7 MB** |
    | `import chromadb` | 532,7 MB | +32,4 MB |
    | `import sentence_transformers` (solo el import, sin cargar modelo) | 836,6 MB | **+303,9 MB** |
    | `SentenceTransformer("all-MiniLM-L6-v2")` cargado | 960,9 MB | +124,3 MB |
    | `chromadb.PersistentClient(...)` abierto | 975,0 MB | +14,1 MB |
    | `get_collection()` (67.827 chunks, solo el handle + metadata) | 1.129,7 MB | +154,7 MB |
    | `model.encode()` de UNA query corta (0,34s) | 1.539,7 MB | **+410,0 MB** |
    | `collection.query(n_results=5)`, sin filtro | 1.540,1 MB | +0,4 MB |
    | `collection.query(...)` CON filtro `where` (sustancia inexistente) | 1.542,1 MB | +2,0 MB |
    - **La consulta a Chroma en sí (con o sin filtro `where`) es
      barata (~2 MB) una vez todo está cargado y "caliente" -- el
      coste real está en la carga de las librerías y, sobre todo, en
      el "warm-up" de PyTorch en su primera inferencia real (+410 MB,
      de lejos el salto más grande de toda la tabla, y no depende del
      tamaño del corpus ni de cuántos resultados se pidan -- es un
      coste fijo de PyTorch la primera vez que corre una inferencia,
      conocido en la comunidad de PyTorch, no un bug de este
      proyecto).**
    - **`import torch` (+455,7 MB) y `import sentence_transformers`
      (+303,9 MB) juntos ya suman ~760 MB solo en IMPORTS, antes de
      cargar ningún modelo ni tocar ningún dato** -- el mayor
      contribuyente estructural al total, no algo que dependa de las
      decisiones de este proyecto en particular (viene de la pila
      `transformers`/`tokenizers`/`huggingface_hub` que arrastra
      `sentence-transformers`).
  - **Aparte, aislado sin LLM ni tokens: coste de `OpenFoodToxStore`
    (relevante porque explica gran parte del salto de +847 MB durante
    la consulta real de extremo a extremo, del que la tabla de arriba
    de Chroma/embeddings solo explica ~410 MB):**
    | Paso | RSS | Delta |
    |---|---|---|
    | Intérprete | 10,9 MB | -- |
    | `import openfoodtox` (pandas/openpyxl incluidos) | 98,3 MB | +87,4 MB |
    | `OpenFoodToxStore(xlsx)` construido | 98,3 MB | +0,0 MB |
    | `substance_uuid_by_name("Aspartame")` (primera llamada real) | 174,1 MB | +75,8 MB |
    | `current_reference_value_opinion(uuid)` (primera llamada real) | 366,8 MB | **+192,7 MB** |
    - **Confirma que `OpenFoodToxStore` carga las hojas del xlsx de
      forma PEREZOSA, no al construirse** -- construir el store no
      cuesta nada extra, pero la PRIMERA llamada real a cada método
      (`substance_uuid_by_name`, `current_reference_value_opinion`)
      dispara la carga de las hojas que necesita (`SUB`, `DOSSIER`,
      `DOSSIER_DOCS`, `FLEX_SUM.ToxRefValues`, etc.) -- ~269 MB en
      total una vez "caliente" (98,3→366,8), sin contar el import base
      de pandas/openpyxl (87,4 MB). En el pipeline completo esto se
      dispara dentro del Nodo 3 (`verify_currency_node`), durante la
      consulta real, explicando gran parte del salto de +847 MB medido
      ahí (el resto, unos ~170-200 MB, no se ha aislado con la misma
      precisión -- probablemente el cliente `openai`/DeepSeek y
      LangGraph, no investigado más a fondo porque el desglose ya era
      suficiente para entender el origen del problema).
  - **Verificado con fuentes externas actuales, no asumido de memoria:**
    el tier gratuito de Streamlit Community Cloud tiene un límite de
    **1 GB de RAM por app** (confirmado con `WebSearch` contra varias
    fuentes independientes -- foro oficial de Streamlit, artículos de
    terceros -- sesión 18-ago-2026, límite consistente desde al menos
    2021 según una de las fuentes). **1.870 MB medidos es ~87% por
    encima de ese límite -- el deploy tal como está el sistema hoy
    fallaría por OOM en el tier gratuito, no es un margen ajustado, es
    un bloqueo real.**
  - **NO investigado ni implementado en esta sesión (queda para cuando
    se retome el pendiente #8, deploy):** ninguna mitigación concreta
    -- ni cambiar a un modelo de embeddings más ligero, ni evitar cargar
    `torch` completo (ej. `onnxruntime` en vez de la pila
    `sentence-transformers`/`torch`, si existe una ruta de inferencia
    equivalente), ni cargar las hojas de OpenFoodTox de forma más
    selectiva (Nodo 3 no necesita TODAS las hojas que
    `OpenFoodToxStore` parece cargar de golpe en la primera llamada),
    ni subir de tier de hosting (Streamlit Community Cloud tiene tiers
    de pago con más RAM, no explorado el coste). Ninguna decisión
    tomada sobre cuál de estas vías seguir -- señalado al usuario
    explícitamente para que decida antes de que se intente el deploy,
    tal como se pidió.
  - **Limpieza tras la sesión de medición:** el proceso `streamlit run`
    lanzado para la medición se mató (`kill`) al terminar; el archivo
    `data/usage_log.json` quedó con un registro de prueba
    (`global_count: 1`) por una ejecución de `AppTest` que sí llegó a
    pasar por `check_and_register_query()` antes de colgarse más
    adelante -- reseteado (borrado; `_load_usage()` lo regenera limpio
    solo con uso real) para no contaminar el candado de presupuesto
    diario con una consulta que nunca llegó a costar dinero de verdad.

---

Detalle evidencial íntegro de la sección "Decisiones de arquitectura" de
`CLAUDE.md` -- mismo principio que la sección de Hallazgos de arriba:
`CLAUDE.md` mantiene un resumen de una frase por decisión, en el mismo
orden que aquí, con puntero a esta sección. Nada de esto está resumido --
es el texto íntegro tal como se escribió sesión a sesión.

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
  - **Mecanismo concreto para Streamlit Community Cloud -- datos
    pesados del deploy vía MEGA S4, NUNCA en git (ni siquiera Git LFS
    en un repo privado), sesión 18-ago-2026 continuación 21.** A
    diferencia de un deploy Docker con imagen propia, Streamlit
    Community Cloud despliega DIRECTAMENTE desde un repo de git -- no
    hay un paso de "artefacto" separado del repo. La única forma de
    cumplir el matiz de arriba ("SÍ en el artefacto, NO en el repo
    público") sin meter los datos en ningún repo de GitHub es que la
    propia app los descargue en tiempo de arranque desde
    almacenamiento externo. Decisión del usuario: MEGA S4
    (almacenamiento de objetos S3-compatible, incluido en su plan MEGA
    Pro Lite) -- **NO Git LFS** (evaluado y descartado explícitamente
    por el usuario: aunque Git LFS "funciona" con Streamlit Community
    Cloud sin cambios de código, seguiría metiendo el texto con
    licencia restrictiva en el historial de git, que es justo lo que
    esta decisión prohíbe, repo privado o no).
    - `src/efsa_rag/deploy_assets.py::ensure_deploy_assets_downloaded()`
      -- descarga el xlsx y un tarball de `data/chroma/` vía boto3 SOLO
      si no están ya en disco (no toca la red en desarrollo local con
      los datos ya presentes, verificado). Credenciales/endpoint/bucket
      SIEMPRE por variable de entorno (`MEGA_S4_*`, ver
      `.env.example`), nunca hardcodeadas. Llamada desde
      `ui/app.py::_render_answer`, justo antes de tocar `graph.build`.
    - `scripts/upload_deploy_assets.py` -- script manual, un solo uso
      por sesión de reindexado, que el usuario ejecuta EN LOCAL con sus
      propias credenciales para poblar el bucket. No lo ejecuta Claude
      (no tiene ni debe pedir las credenciales reales).
    - Ver `README.md`, sección "Deploy en Streamlit Community Cloud",
      para los pasos completos, y `PROGRESS.md` continuación 21 para el
      detalle de la implementación y verificación.
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
- **`data/usage_log.json` NO va en git, igual que `data/last_update_check.txt`
  -- inconsistencia real corregida (sesión 19-ago-2026), no una
  hipótesis.** Ambos son el mismo tipo de archivo: contador de estado
  runtime, escrito por `ui/app.py`, que se autorreinicia según la fecha
  (`_load_usage()` descarta el contenido si `data.get("date") !=
  str(date.today())`). `last_update_check.txt` ya estaba en
  `.gitignore` desde el principio por este motivo; `usage_log.json` se
  había quedado trackeado con un valor fijo (`git ls-files` lo
  confirmaba), verificado ANTES de tocar nada -- no asumido por
  analogía. Comitear un snapshot de este archivo es activamente
  engañoso, no solo redundante: en producción (Streamlit Community
  Cloud, disco efímero -- ver "Opción A, índice horneado" más arriba)
  el valor comiteado se descarta en la primera consulta real del día de
  todos modos (el chequeo de fecha lo resetea), así que el número fijo
  en git nunca refleja el estado real de ningún entorno, ni local ni de
  producción -- solo genera diffs espurios cada vez que alguien corre
  la app en local (confirmado: dos verificaciones puntuales de UI en la
  misma sesión bastaron para ensuciar el archivo, sin tocar código).
  Sacado de git con `git rm --cached` (el archivo sigue en disco local,
  solo deja de trackearse) + añadido a `.gitignore` junto a
  `last_update_check.txt`.
- **Precio LLM de referencia (ajustar si cambia):** DeepSeek V4-Flash,
  **~$0.0008-0.0020 por consulta según franja horaria -- RECALCULADO
  Y CERRADO (sesión 18-ago-2026, continuación 15)** con la tarifa
  oficial vigente verificada directamente en
  `https://api-docs.deepseek.com/quick_start/pricing` (no una cifra
  heredada de una sesión anterior sin fuente citable, ver el motivo
  del recálculo más abajo): modelo `deepseek-v4-flash`, input cache-hit
  $0,007 (valle) / $0,014 (punta) por millón de tokens, input cache-miss
  $0,22 (valle) / $0,44 (punta), output $0,66 (valle) / $1,32 (punta) --
  "punta" = 01:00-04:00 y 06:00-10:00 UTC, "valle" el resto (tarifa
  valle = mitad de la de punta, confirmado en la propia página de
  pricing). Cálculo: input ~1.250-2.000 tokens (system prompt 575
  tokens medido + `retrieved_chunks`, k=3-5 chunks ~150-180
  tokens/chunk, mismo presupuesto ya medido en sesión anterior, sin
  cambios) + output **845 tokens (medido de verdad, no estimado --
  caso real Shellac, `finish_reason == 'stop'`, ver más abajo)**,
  asumiendo cache-miss en el input (cota conservadora; si el caché
  automático de DeepSeek para el system prompt repetido sí aplica en
  producción, el coste real baja un poco más, pero el efecto es
  pequeño porque el output domina el coste total -- ver el cálculo
  completo en `PROGRESS.md`, sesión 18-ago-2026 continuación 15).
  Rango resultante: ~$0,0008/consulta en valle, ~$0,0020/consulta en
  punta.
  - **Sustituye a la cifra anterior de $0,0005-0,0014/consulta**
    (basada en ~365 tokens de salida, de antes de subir
    `NODE_4_MAX_TOKENS` de 800 a 2000 -- ver el hallazgo de
    truncamiento del Nodo 4 resumido arriba) -- la nueva cifra es
    ~1,4-1,6x mayor, consistente con que el output real más que se
    dobló (365→845) pero el input no cambió y domina menos que el
    output en el total.
  - **El hardcoded `ESTIMATED_COST_PER_QUERY_USD = 0.002` en
    `ui/app.py` (candado de presupuesto real) SIGUE SIENDO VÁLIDO,
    verificado contra esta cifra, no solo asumido** -- cae justo en el
    extremo superior (punta) del rango recalculado, así que el candado
    de presupuesto real (`DAILY_HARD_COST_CEILING_USD = 0.35`) sigue
    protegiendo con el margen esperado en el caso normal. **Caveat
    real, no bloqueante:** ese hardcoded es un valor FIJO por consulta,
    y no distingue una consulta normal (~845 tokens de salida) de una
    que dispara el reintento por truncamiento (`NODE_4_RETRY_MAX_TOKENS
    = 3500`) -- el caso peor de reintento paga DOS llamadas completas
    (la truncada + el reintento), hasta ~5.500 tokens de salida en
    total entre ambas, ~$0,004-0,009/consulta -- 2-4,5x el hardcoded.
    Como el reintento solo se paga en el caso raro (la primera pasada
    ya se truncó), el promedio real debería seguir cerca del hardcoded
    salvo que las respuestas truncadas se vuelvan frecuentes -- no
    detectado como un problema real hoy, solo documentado para no
    asumir que el candado cubre ese caso con el mismo margen que el
    caso normal.
  - Presupuesto de referencia sin cambios en la conclusión: 6-7€/mes
    (`DAILY_HARD_COST_CEILING_USD = 0.35`/día × ~30 días) sigue
    cubriendo miles de consultas -- entre ~5.250/mes (todo en franja
    punta, cota inferior) y ~13.000/mes (todo en franja valle, cota
    superior) al nuevo coste por consulta, muy por encima de lo que un
    proyecto de portfolio necesita.
  - Se evaluó Kimi K2.6/K3 como alternativa: K2.6 es más caro que
    DeepSeek y con peor puntuación en benchmarks generales; K3 iguala
    casi a modelos de frontera pero a 15-20x el coste. Se mantiene
    DeepSeek por defecto. **Antes de cambiar de proveedor por
    benchmarks genéricos**, construir un set de 10-15 casos de prueba
    del Nodo 4 (con las reglas de comunicación de riesgo) y medir tasa
    de cumplimiento real, no decidir por índices de inteligencia
    genéricos que no miden eso.
  - **Esta estimación de coste asume "thinking" desactivado** (ver
    bullet de arriba). Medido en sesión con el mismo prompt del Nodo 4:
    799 tokens de salida con "thinking" activo (esfuerzo "high", casi
    todo `reasoning_content`) frente a 365 con "thinking" desactivado
    -- un desplegado con el default de DeepSeek sin darse cuenta habría
    corrido con un coste real notablemente mayor al estimado aquí, no
    por un cambio de precio del proveedor sino por un parámetro de la
    llamada.
- **Modelo de embeddings: `sentence-transformers/all-MiniLM-L6-v2`
  (384 dims, local) -- decidido y probado con datos reales (sesión
  18-ago-2026), no solo elegido por defecto teórico.**
  **ACTUALIZADO EN LA MISMA FECHA (sesión 18-ago-2026, más tarde): el
  backend de carga cambió de `torch` (por defecto) a ONNX + pesos int8
  cuantizados** -- decisión de memoria para el deploy, ver el bullet
  "Backend de embeddings: ONNX int8, no torch" más abajo para el
  razonamiento y las cifras. **Las cifras de esta entrada (597 MB en
  disco, 2,97 min de indexado, GPU) describen la corrida ORIGINAL con
  `torch` -- ya SUPERADA, el índice actual se reconstruyó con ONNX int8
  (718 MB en disco, ~22,4 min, CPU, ver el bullet de ONNX) -- no las
  repitas como si fueran las vigentes, se dejan aquí solo como
  registro de lo que se midió entonces.** Se descarga y
  carga sin problemas en el venv del proyecto (`sentence-transformers`
  ya en `requirements.txt`) -- 3,4-7,7 s de carga según si el modelo ya
  está en caché local.
  - **Entorno de esta sesión con GPU disponible** (`model.device` ->
    `cuda:0`). **ADVERTENCIA EXPLÍCITA PARA EL DESPLIEGUE, no lo des
    por descontado:** si se reconstruye el índice en un entorno sin GPU
    (ej. HF Spaces/Streamlit Cloud gratuito, ver la decisión de
    despliegue "Opción A" -- el índice de Chroma se construye en local
    y se empaqueta, no se reindexa en caliente en producción, pero
    "en local" puede seguir siendo un entorno sin GPU si el reindexado
    se hace desde otra máquina o CI) las cifras de abajo NO son
    representativas -- solo-CPU sería significativamente más lento, no
    medido en esta sesión. Volver a medir en el entorno real donde se
    reconstruya el índice antes de asumir minutos de reconstrucción
    similares a los de aquí. Esto importa en concreto para el flujo de
    "refresco" descrito en la decisión de despliegue: cada vez que se
    añadan dictámenes nuevos al corpus y haga falta reindexar antes de
    redeploy, el tiempo real dependerá de si esa reconstrucción corre
    con GPU o no.
  - **Lote de prueba (300 chunks, 150 aspartamo + 150 tartratos):
    435,5 chunks/s**, proyección lineal ~4,1 min para el corpus
    completo.
  - **CORPUS COMPLETO INDEXADO DE VERDAD (sesión 18-ago-2026,
    continuación 4) -- tiempo REAL, no proyección:** 67.827 chunks,
    **2,97 min en total** (3,4 s carga del modelo + 1,27 min embeddings
    a 887,3 chunks/s + 1,51 min escritura en Chroma) -- más rápido que
    la proyección de 4,1 min, principalmente porque `model.encode()`
    con `batch_size=256` explícito rinde casi el doble que el batch
    interno por defecto (32) usado implícitamente en la prueba de 300.
    Verificado `collection.count() == 67827` tras escribir. Persistido
    en `data/chroma/` (colección `efsa_reevaluation_chunks`, cliente
    `chromadb.PersistentClient`) -- **597 MB en disco**
    (`chroma.sqlite3`). Reindexar por completo BORRA la colección
    anterior primero (`scripts/build_chroma_index.py --all`, evita
    duplicados de una corrida previa) -- no es incremental, es un
    rebuild completo cada vez.
  - **Consultas de verificación sobre el índice completo (no el lote
    de prueba) -- 3 preguntas, temas distintos, todas con resultados
    temáticamente correctos:**
    1. *"genotoxicity studies and safety assessment"* -- top 5 incluye
       la sección `4.3. Genotoxicity` del TiO2 vigente (E171, 2021) y
       contenido de genotoxicidad de sílice/eritritol.
    2. *"why was titanium dioxide withdrawn as a food additive"* --
       **los 5 resultados son de los 2 dossiers de TiO2 (2016 y
       2021)**, incluida su sección `1. Introduction` y `Summary`
       explicando la re-evaluación -- caso conocido usado como prueba
       específica, resultado correcto.
    3. *"dietary exposure assessment uncertainties"* -- top 5 mezcla
       secciones "Uncertainty analysis" de 5 aditivos DISTINTOS
       (verificado contra `chemical_name`, no adivinado: poliglicerol
       poliricinoleato E476, octyl gallate E311, cochinilla/ácido
       carmínico E120, dimetil dicarbonato E242, dodecyl gallate E312)
       -- confirma que no es un acierto aislado del tema de
       genotoxicidad, generaliza a otro tema.
  - Verificado además, no asumido: Chroma lanza `TypeError` con valores
    `None` en metadatos (ver el ESQUEMA FINAL más abajo en "Hallazgos
    verificados") y SÍ admite claves de metadato distintas entre
    documentos de la misma colección.
- **Backend de embeddings: ONNX int8, no `torch` -- decisión de
  memoria para el deploy (sesión 18-ago-2026), con el índice de Chroma
  YA reconstruido con este backend, no solo decidido en teoría.** Motivo
  completo, cifras de cada alternativa probada, y el pivote de plan de
  deploy que lo motivó (Streamlit Community Cloud → HF Spaces → HF
  Spaces con Docker de pago descubierto → esta optimización de memoria
  como palanca adicional): `PROGRESS.md`, sesión 18-ago-2026,
  continuación 19 -- no repetido aquí para no duplicar el detalle.
  **Puntos que SÍ hace falta recordar al tocar este código:**
  - `torch` SIGUE siendo dependencia dura de `sentence-transformers`
    pase lo que pase -- verificado desinstalándolo, rompe el import
    incluso con `backend="onnx"`. El ahorro de ONNX no viene de evitar
    `torch`, viene de evitar el "calentamiento" de la primera
    inferencia de PyTorch (~400 MB) porque la inferencia real la hace
    ONNX Runtime.
  - **Único punto de la base de código que debe instanciar
    `SentenceTransformer`: `ingestion/embedding_model.py::load_embedding_model()`.**
    Indexado (`scripts/build_chroma_index.py`) y retrieval
    (`graph/build.py::build_default_deps`) lo llaman a los DOS -- si
    alguna vez se cambia el modelo/backend, cambiar solo ahí, nunca
    instanciar `SentenceTransformer` directamente en otro sitio (ya
    pasó una vez que index y query usaban backends distintos por
    accidente -- fp32/torch en el índice, int8/onnx en la consulta --
    antes de unificarlo con este módulo, ver PROGRESS.md).
  - `requirements.txt`: `sentence-transformers[onnx]`, no
    `sentence-transformers` a secas (añade `optimum` + `onnxruntime`).
  - Reindexado completo con este backend: ~22,4 min en CPU (sin GPU),
    frente a los ~3 min con GPU+torch de la corrida original -- más
    lento, aceptado porque es un paso offline que no cuenta contra el
    presupuesto de memoria del deploy.
  - `data/chroma/` pasó de 597 MB a 718 MB en disco tras reconstruir
    -- sin investigar la causa exacta (no es por las embeddings en sí,
    siguen siendo float32/384 dims igual que antes), no bloqueante.
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
- **Resolución multi-candidato del Nodo 1 (sesión 19-ago-2026) --
  `GraphState.substance_uuid: str | None` sustituido por
  `substance_candidates: list[SubstanceCandidate]`, mismo tipo de cambio
  de contrato que la entrada de `retrieved_chunks` de arriba, no la
  reabras sin motivo nuevo.** Decisión de producto explícita del
  usuario: cuando `OpenFoodToxStore.resolve_substance_candidates` (nuevo
  método, exacto -> exacto normalizado por guion/espacio -> fuzzy
  restringido a las 246 sustancias resolubles del corpus) encuentra
  varios nombres razonablemente parecidos, el sistema nunca elige uno en
  silencio -- resuelve y presenta TODOS por separado. Detalle completo
  (calibración del umbral fuzzy, por qué se descartó la hipótesis del
  símbolo griego para tocoferol, presupuesto de `retrieved_chunks` con
  2+ candidatos, por qué MCP queda deliberadamente fuera) en "Hallazgos
  verificados", pendiente #2 de más abajo (ahora marcado RESUELTO).
- **Dos caminos de ejecución del grafo -- completo y parcial -- decisión
  tomada al implementar el servidor MCP (sesión 18-ago-2026):**
  `graph/build.py` expone dos puntos de entrada, no uno:
  - **Completo -- `answer_question(query) -> AnswerResult`:** Nodo 1 →
    2 → 3 → 4, el grafo compilado tal cual (`build_graph`). Usado por la
    herramienta MCP `search_efsa_opinion`. Produce prosa (el texto de
    `answer`), así que está sujeto a `NODE_4_SAFETY_COMMUNICATION_RULES`
    en tiempo de generación -- el único punto del sistema donde se
    compone lenguaje nuevo sobre el ADI, y por tanto el único que
    necesita esa restricción activa.
  - **Parcial -- `resolve_current_opinion(query) -> ReevaluationStatus`:**
    Nodo 1 + Nodo 3 únicamente, llamando a `extract_entity_node`/
    `verify_currency_node` directamente (NO al grafo compilado, que
    siempre enruta al Nodo 4) -- sin Nodo 2 (no hace falta
    `retrieved_chunks` para esto) ni Nodo 4 (no hace falta prosa
    generada, solo campos ya calculados por OpenFoodTox). Usado por la
    herramienta MCP `get_reevaluation_status`. Comparte el mismo
    `_default_deps` cacheado que `answer_question` -- llamar a una u
    otra función no recarga embeddings/Chroma/xlsx por separado.
  - **Por qué saltarse el Nodo 4 en el camino parcial NO compromete la
    restricción no negociable #1, verificado campo a campo antes de
    implementarlo, no asumido:** la restricción prohíbe que el LLM
    **redacte** una frase que enmarque el ADI como umbral ("si se
    supera el ADI, se produce/puede producir [efecto]") -- vive en el
    system prompt del Nodo 4 precisamente porque ahí es donde se
    compone prosa nueva. `ReevaluationStatus`/`OpinionReference` no
    pasan por ningún LLM para el ADI: `adi_value`/`adi_unit` son
    lectura directa de `FLEX_SUM.ToxRefValues` (números crudos, sin
    interpretar), `adi_justification` es
    `adi_row[ADI_JUSTIFICATION_COLUMN]` -- texto de EFSA citado tal
    cual, sin reformular (`ingestion/openfoodtox.py`) -- el MISMO campo
    que el Nodo 4 ya cita literalmente dentro de sus respuestas
    generadas hoy (`test_format_structured_result_tier1_cites_adi_normally`).
    Sin generación no hay redacción que pudiera violar la regla.
  - **Capa extra en el servidor MCP, no en `graph/build.py`:** el JSON
    que devuelve la herramienta `get_reevaluation_status` incluye un
    campo `safety_note` -- una constante de texto fija (NO generada por
    ningún LLM), recordando que el ADI es un margen de seguridad, no un
    umbral. No lo exige la restricción #1 (que solo rige redacción
    dentro del sistema), pero un cliente MCP externo que reciba estos
    números crudos podría componer la frase prohibida por su cuenta sin
    ese contexto -- defensa en profundidad, no una regla nueva del
    Nodo 4.

---

## Estado del código (detalle completo, histórico)

Detalle evidencial íntegro, sesión a sesión, del estado de implementación
de cada componente -- incluye los bloques `[CORRECCIÓN...]`, la
verificación con llamadas reales a la API, y el análisis completo de cada
punto pendiente tal como se escribió en el momento. `CLAUDE.md` mantiene
solo una lista compacta del estado actual (implementado / pendiente), sin
esta narrativa, con puntero aquí para el histórico completo. Nada de esto
está resumido -- es el texto íntegro tal como se escribió sesión a sesión.

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
- `graph/nodes.py` — Nodo 2 (retrieval híbrido), Nodo 3 (determinista) y
  Nodo 4 (generación) implementados.
  **Nodo 1 (`extract_entity_node`) -- PRIMERA IMPLEMENTACIÓN REAL
  (sesión 18-ago-2026, continuación 7), NO una continuación de nada
  previo.** Hasta esta sesión era literalmente `raise NotImplementedError`
  desde el primer commit del repo, pese a documentación previa que
  decía lo contrario -- ver la corrección completa en PROGRESS.md
  (continuación 6) antes de esta entrada. Diseño e implementación:
  - `NODE_1_ENTITY_EXTRACTION_PROMPT` (nuevo, primera vez que existe):
    pide al LLM el nombre químico CANÓNICO EN INGLÉS de la sustancia
    mencionada en la pregunta -- una sola línea, sin explicación, o
    literalmente `NONE` si no identifica ningún aditivo. Necesario en
    inglés porque `OpenFoodToxStore.substance_uuid_by_name` exige
    coincidencia EXACTA contra `SUB.ChemicalName` (limitación conocida,
    pendiente #2 más abajo, NO resuelta por este nodo -- si el LLM
    normaliza a un nombre razonable que no coincide carácter a
    carácter con `SUB` (ej. nombres compuestos), la resolución falla y
    `substance_uuid` queda en `None`, comportamiento esperado).
  - `max_tokens=30` -- un nombre químico, no una frase.
  - **Probado con llamada REAL a la API de DeepSeek, no asumido ni
    mockeado** (`tests/test_nodes.py::test_extract_entity_node_resolves_aspartame_from_real_english_query`,
    pregunta en inglés sobre aspartamo -- el caso de referencia ya
    usado en el resto del proyecto -- verifica `substance_uuid` contra
    `store.substance_uuid_by_name("Aspartame")` directamente, no da el
    resultado por bueno solo porque el prompt parezca razonable) +
    `test_extract_entity_node_unrelated_query_resolves_to_none`
    (pregunta sin ningún aditivo -- confirma que no inventa una
    sustancia). Ambos tests hacen una llamada real y FACTURADA a la
    API en cada ejecución (a diferencia del resto de tests de este
    archivo, que son gratis una vez el recurso local existe) -- se
    saltan si `DEEPSEEK_API_KEY` no está configurada.
  - **Verificado además, a mano, con 4 preguntas reales antes de dar
    la implementación por buena** (no solo las 2 del test automatizado):
    inglés+aspartamo -> `Aspartame` (UUID correcto); español, "Por
    qué se retiró el dióxido de titanio como aditivo?" -> `Titanium
    dioxide` (UUID correcto); E-number "Is E 951 safe for children?"
    -> `Aspartame` (UUID correcto); pregunta sin relación ("What time
    is it in Tokyo") -> `None`/`None`, sin inventar.
    **La limitación de idioma español/E-numbers de
    `substance_uuid_by_name` (pendiente #2 más abajo) sigue SIN
    RESOLVER a nivel estructural -- NO la des por cerrada.** La función
    en sí sigue exigiendo coincidencia EXACTA contra `SUB.ChemicalName`
    en inglés, sin cambios. Lo único que cambió es que el LLM normaliza
    ANTES de llegar a esa función, y en los 4 casos puntuales probados
    (1 en español, 1 con E-number) acertó la traducción/normalización.
    Eso es **una mitigación parcial, verificada en un puñado de casos
    concretos, NO una batería de pruebas sistemática** -- no hay
    ninguna garantía de que el LLM acierte con nombres compuestos,
    E-numbers menos conocidos, o variantes de redacción no probadas
    todavía. Tratar como "probablemente ayuda en la mayoría de casos
    comunes", no como "el problema está resuelto" -- si en el futuro se
    quiere una garantía real, hace falta una batería de pruebas más
    amplia (o una solución estructural, ej. una tabla de sinónimos/
    traducciones curada) antes de confiar en esto para producción.
  - Si `substance_uuid` resuelve a `None` (LLM respondió `NONE`, o el
    nombre no coincide exacto en `SUB`), el resto del grafo ya lo
    maneja: Nodo 2 deja `retrieved_chunks` vacío sin llamar a Chroma;
    Nodo 3 espera `substance_uuid` no nulo y lanza `ValueError` si se
    le llama sin él -- decidir si llamarlo en ese caso es
    responsabilidad de la orquestación del grafo -- ver `graph/build.py`
    más abajo, implementado en la misma sesión que cierra este punto.
  Nodo 4 conecta `deps.llm_client.complete(...)` con system prompt =
  `NODE_4_GROUNDING_RULES` + `NODE_4_SAFETY_COMMUNICATION_RULES`;
  probado con llamada real a la API (caso aspartamo) cumpliendo las
  reglas de comunicación de riesgo -- este es el nodo que se probó
  contra la API real ya en sesión 2 (16-ago-2026), probablemente el
  origen de la confusión que atribuyó lo mismo al Nodo 1 sin serlo
  (ver la entrada de corrección en PROGRESS.md) -- ahora el Nodo 1
  TAMBIÉN está probado contra la API real por derecho propio, no por
  la misma prueba de otro nodo.
  **[CORRECCIÓN, sesión 18-ago-2026 (auditoría general): esta prueba
  real es cierta pero está DESACTUALIZADA -- no cubre el prompt tal
  como es hoy.** La llamada real de sesión 2 se hizo contra una
  versión de `_format_structured_result` anterior a que existieran
  `discussion_text`/`discussion_is_boilerplate` (añadidos en sesión 3,
  16-ago-2026) y anterior al texto de "motivos opuestos" para ADI sin
  valor numérico (tier 1/2, añadido en sesión 17-ago-2026 continuación
  7) -- ambos confirmados presentes en el código actual, ambos
  ausentes en el momento de esa prueba. `_format_retrieved_chunks` (el
  aviso de tier 3) tampoco existía todavía. **Ninguna de estas tres
  adiciones ha pasado nunca por una llamada real a la API.** Más
  importante: como el Nodo 2 no existía hasta la sesión de hoy,
  **todas las llamadas reales hechas a este nodo hasta ahora se
  hicieron con `retrieved_chunks=[]`** -- el caso de fragmentos
  narrativos reales poblando el prompt (el motivo de ser del Nodo 2)
  nunca se ha probado end-to-end con una llamada real. Y, verificado
  con `grep` en esta misma auditoría: **no existe ningún test
  automatizado de `generate_answer_node`** en `tests/` -- a diferencia
  del Nodo 1 y el Nodo 2, esta verificación nunca se codificó como
  reproducible, solo quedó como una sesión manual puntual de hace
  varios días. No tratar "Nodo 4 probado contra la API real" como una
  garantía vigente del comportamiento actual -- antes de confiar en
  ello para producción, hace falta repetir la prueba real con el
  prompt de hoy (incluido `retrieved_chunks` no vacío) y, si se quiere
  que sea reproducible, añadir un test automatizado como los de los
  Nodos 1 y 2.]**
  **Nodo 2 (`hybrid_retrieval_node`) IMPLEMENTADO (sesión 18-ago-2026,
  continuación 5) y probado con una consulta real contra el índice
  completo de Chroma (67.827 chunks, caso aspartamo).** Diseño:
  - Si `state["substance_uuid"]` es `None` (Nodo 1 no resolvió nada),
    NO se llama a Chroma en absoluto -- `retrieved_chunks` queda vacío
    directamente. Verificado con un vectorstore de prueba que lanza
    excepción si se le llama, para confirmar que de verdad no se
    invoca, no solo que el resultado da vacío por casualidad.
  - Si hay `substance_uuid`, se embede `user_query` con
    `deps.embedding_model` (el MISMO modelo usado para indexar,
    `all-MiniLM-L6-v2` -- pasado como dependencia, no cargado de nuevo
    en cada llamada) y se consulta `deps.vectorstore.query(...)`
    filtrando por `where={"substance_uuid": ...}` -- el único campo
    del esquema de metadatos con filtro exacto fiable (no hay
    `e_number`, y `substance_name` es texto libre del usuario, no una
    clave de índice).
  - `k = DEFAULT_RETRIEVAL_K = 5` -- el extremo superior del rango
    k=3-5 ya asumido en el cálculo de presupuesto de contexto del Nodo
    4 (ver PROGRESS.md sesión 18-ago-2026), elegido porque el
    presupuesto seguía siendo razonable ahí y da más contexto real.
  - `substance_resolution_tier` y el resto de campos de
    `RetrievedChunk` se copian TAL CUAL de los metadatos ya escritos
    al indexar -- no se re-derivan en el Nodo 2.
  - `NodeDependencies` ganó un campo nuevo, `embedding_model` (además
    de `vectorstore`, ya existente) -- ambos tipados como `object` a
    propósito, mismo principio que `LLMClient`: no acoplar
    `graph/nodes.py` a la API concreta de chromadb/sentence-transformers.
  - Probado con `tests/test_nodes.py::test_hybrid_retrieval_node_aspartame_real_query`
    (consulta real sobre genotoxicidad/carcinogenicidad de aspartamo,
    no un mock -- verifica que todos los chunks devueltos tienen el
    `substance_uuid` correcto, `chemical_name == "Aspartame"`,
    `section_heading` no vacío, y `substance_resolution_tier == 1`) y
    `test_hybrid_retrieval_node_no_uuid_skips_chroma_entirely`. Se
    saltan si `data/chroma/` no existe (mismo patrón que los tests que
    dependen del xlsx real).
  - **DIAGNÓSTICO (sesión 18-ago-2026, continuación 12, SOLO
    investigación, nada implementado): la calidad del retrieval es
    sensible al fraseo de la pregunta -- confirmado con TiO2, no
    asumido.** La consulta "Why was titanium dioxide withdrawn as a
    food additive?" NO recuperó ningún fragmento de la sección
    "4.3. Genotoxicity" (página 45) -- la sección que de hecho contiene
    la preocupación de seguridad central del dictamen de 2021 -- y en
    su lugar trajo Introduction/Background/Summary, contenido más
    regulatorio que sustantivo. Probada una reformulación más directa,
    "titanium dioxide genotoxicity concern conclusion": **el resultado
    #1 es exactamente esa sección (4.3. Genotoxicity)** -- confirma que
    el contenido SÍ está bien chunked e indexado, el problema es de
    fraseo de la pregunta original ("withdrawn" no es un marco que el
    propio dictamen use -- es una reevaluación, no un anuncio de
    retirada, así que la similitud de embeddings favoreció contenido
    superficial sobre la sección sustantiva). **Hallazgo secundario, no
    buscado:** incluso con la reformulación mejor, 3 de los 5
    resultados fueron fragmentos de la sección "References" (entradas
    bibliográficas que mencionan "genotoxicity" en el título del
    estudio citado, no razonamiento del panel) -- mismo tipo de ruido
    de baja calidad que ya motivó excluir tablas del índice narrativo
    (ver la decisión de Opción A). **No implementado nada de esto** --
    ni reformulación de query en el Nodo 1/2, ni exclusión de
    "References" del chunking -- queda como candidato a mejora futura
    del Nodo 2/chunker, no urgente pero real.
  El Nodo 4 sigue diseñado para degradar con gracia con
  `retrieved_chunks` vacío, y desde sesión 18-ago-2026 (continuación
  10-11) también se ha probado de extremo a extremo con
  `retrieved_chunks` reales poblados por el Nodo 2 en la misma
  ejecución (`answer_question`, ver `graph/build.py` más abajo).
  - **BUG REAL ENCONTRADO Y ARREGLADO (sesión 18-ago-2026, continuación
    12): truncamiento silencioso de la respuesta, sin ningún aviso al
    usuario.** Una respuesta real sobre Shellac (caso tier 3, con aviso
    de fiabilidad + desglose largo) se cortó a mitad de frase. Antes de
    tocar nada, se confirmó la causa exacta vía
    `response.choices[0].finish_reason` (expuesto ahora como
    `LLMResponse.finish_reason`, campo nuevo en `graph/llm_client.py`,
    antes no existía en la interfaz): **`finish_reason == 'length'`,
    `output_tokens == 800` (el tope exacto de entonces)** -- truncamiento
    real por `max_tokens`, no otra causa (no filtro de contenido, no
    secuencia de parada). El texto se devolvía al usuario tal cual,
    cortado, sin ninguna señal de que faltaba contenido.
  - **Fix, dos partes:** (1) `NODE_4_MAX_TOKENS` subido de 800 a 2000
    (`graph/nodes.py`) -- con "thinking" ya desactivado (ver más abajo),
    esto es presupuesto de texto de salida real, no overhead oculto de
    razonamiento, así que subirlo es coste directo -- ver el bullet de
    precio de referencia más arriba para la actualización pendiente de
    ese cálculo. (2) `generate_answer_node` ahora comprueba
    `response.finish_reason == "length"` explícitamente: si trunca,
    reintenta UNA vez con `NODE_4_RETRY_MAX_TOKENS = 3500`, y si sigue
    truncada incluso así, añade `"\n\n[respuesta incompleta por límite
    de longitud]"` al final -- nunca se devuelve una respuesta cortada
    sin avisar, pase lo que pase.
  - **Verificado tras el fix, misma consulta de Shellac:** con
    `max_tokens=2000`, la respuesta terminó sola
    (`finish_reason == 'stop'`) en **845 tokens de salida** -- ni
    siquiera hizo falta el reintento, y la respuesta ahora cierra con
    un párrafo de "Conclusión" completo, no cortado a mitad de frase.
    Suite de tests completa: 23/23 siguen pasando.
- **`graph/build.py` (nuevo, sesión 18-ago-2026, continuación 9) --
  ensamblado del grafo LangGraph completo, COMPILADO Y VERIFICADO
  ESTRUCTURALMENTE, NO ejecutado todavía con datos reales.** Distingue
  a propósito de otros bullets de esta lista: aquí "verificado" es
  "el grafo compila y su diagrama Mermaid tiene la forma esperada", no
  "se ha invocado con una pregunta real" -- eso queda explícitamente
  para la próxima sesión, no se hizo en esta a petición del usuario
  ("no llames a la API todavía").
  - `build_graph(deps: NodeDependencies) -> CompiledStateGraph`: los 4
    nodos registrados como closures que capturan `deps` (las funciones
    de nodo toman `(state, deps)`, `StateGraph.add_node` espera solo
    `state`). `extract_entity -> hybrid_retrieval ->` arista
    condicional `-> {verify_currency -> generate_answer} | {generate_answer}`.
  - **Decisión de diseño explícita -- qué pasa si el Nodo 1 no resuelve
    `substance_uuid`: el grafo SIGUE hasta el Nodo 4, no corta antes.**
    Pero salta el Nodo 3 (que lanzaría `ValueError` si se le llamara
    sin `substance_uuid`, sin cambios en su código) -- una única arista
    condicional justo después del Nodo 2 decide entre el camino normal
    (Nodo 3 -> Nodo 4) y el camino corto (directo a Nodo 4). Motivo de
    seguir hasta el Nodo 4 en vez de cortar: el Nodo 4 ya estaba
    diseñado para degradar con gracia en ambos huecos --
    `structured_result` no puesto en el estado se lee como `None`
    igual que si el Nodo 3 lo hubiera puesto explícitamente
    (`GraphState` es `TypedDict(total=False)`), y `retrieved_chunks`
    ya queda vacío por diseño del propio Nodo 2 sin `substance_uuid` --
    así que el Nodo 4 puede producir una respuesta útil ("no he podido
    identificar de qué aditivo hablas") sin código nuevo. Cortar antes
    dejaría al usuario sin respuesta y no ahorra nada (el Nodo 1, la
    única llamada cara del camino corto, ya se pagó). `vigencia_ambigua`
    (solo la pone el Nodo 3) queda sin definir en el camino corto --
    verificado que ningún otro nodo la lee, sin efecto secundario.
  - `build_default_deps()`: instancia real de `NodeDependencies` --
    `OpenFoodToxStore` sobre el xlsx, colección Chroma persistente
    (`data/chroma/`, `chromadb.PersistentClient`), `SentenceTransformer`
    (`all-MiniLM-L6-v2`, el mismo modelo del indexado) y
    `build_default_client()` (ya existente en `graph/llm_client.py`,
    reutilizado sin duplicar -- lee `EFSA_RAG_LLM_BACKEND` del entorno).
  - `answer_question(query: str) -> AnswerResult`: punto de entrada
    simple pedido explícitamente. `deps`/grafo cacheados a nivel de
    módulo (variables globales `_default_deps`/`_default_graph`,
    inicializadas en la primera llamada) -- decisión propia, no pedida
    literalmente así, para no recargar el modelo de embeddings ni
    reabrir Chroma en cada pregunta; documentado en el propio código
    por qué.
    - **CAMBIO DE CONTRATO (sesión 18-ago-2026, continuación 11):
      devuelve `AnswerResult` (dataclass: `answer: str`,
      `retrieved_chunks: list[RetrievedChunk]`,
      `structured_result: OpinionReference | None`), NO un `str` como
      en la versión original.** Motivo -- existe específicamente para
      poder AUDITAR FUNDAMENTACIÓN sin tener que reproducir el
      retrieval a mano: en una sesión de verificación real (misma
      sesión, antes de este cambio) se pidió confirmar si una mención
      concreta de la respuesta ("Soffritti et al. 2006") aparecía de
      verdad en algún `retrieved_chunk`, y como `answer_question` solo
      devolvía el string, hubo que reconstruir la llamada a
      `hybrid_retrieval_node` por separado con el mismo `substance_uuid`
      y query para poder inspeccionarlo -- funcionó (sí aparecía,
      chunk de la sección "2.7.1. Existing authorisations and
      evaluations of aspartame"), pero no debería hacer falta
      reproducir nada para verificar esto la próxima vez.
      `retrieved_chunks`/`structured_result` en `AnswerResult` son los
      MISMOS objetos que vio el Nodo 4 al construir el prompt (leídos
      del estado final tras `.invoke(...)`), no una reconstrucción
      aparte. `answer` sigue siendo el texto final -- esto no lo
      sustituye, lo acompaña. **Verificado sin callers reales que
      rompiera** (`grep` antes del cambio: ningún caller en
      `ui/app.py`, tests o scripts esperaba el `str` de antes -- solo
      invocaciones manuales sueltas de sesiones de verificación, nada
      persistido). Re-verificado con una llamada real tras el cambio:
      reproduce exactamente los mismos 5 `retrieved_chunks` que la
      reconstrucción manual anterior, mismo orden -- confirma que el
      retrieval es determinista para esta consulta.
  - **Verificado en esta sesión (sin tocar la API):** `python -m
    efsa_rag.graph.build` compila el grafo con un `NodeDependencies`
    de relleno (todos los campos `None` -- seguro porque `deps` solo
    se usa DENTRO de las funciones de nodo cuando el grafo se invoca de
    verdad, nunca durante `.compile()`/`.get_graph()`) y dibuja el
    Mermaid: `extract_entity -> hybrid_retrieval`, dos aristas
    punteadas (condicionales) desde `hybrid_retrieval` hacia
    `verify_currency` y hacia `generate_answer` directamente,
    `verify_currency -> generate_answer -> __end__` -- coincide
    exactamente con el diseño de arriba. Suite de tests completa
    (23/23) sigue en verde con el módulo nuevo importado.
  - **YA INVOCADO DE VERDAD (sesión 18-ago-2026, continuación 10):**
    `answer_question("What is the ADI of aspartame and what study is
    it based on?")` -- primera ejecución real de extremo a extremo
    (Nodo 1 -> 2 -> 3 -> 4 en una sola llamada), no solo por nodos
    separados. Respuesta completa, ADI/DOI/fecha correctos, cita
    textual de `adi_justification`, margen de seguridad explicado
    correctamente (sin la frase prohibida de "si se supera el ADI").
    Fundamentación de una mención concreta de la respuesta
    ("Soffritti et al. 2006") verificada contra `retrieved_chunks`
    real -- aparece literalmente en el chunk de la sección "2.7.1.
    Existing authorisations and evaluations of aspartame", confirmando
    que el Nodo 4 no mezcló esa mención con conocimiento propio del
    entrenamiento sin decirlo. Motivó el cambio de contrato de
    `answer_question` (ver el bullet de arriba, `AnswerResult`) para
    no tener que reproducir el retrieval a mano la próxima vez.
- `ui/app.py` — candado de refresco + límites de consulta, funcional.
  **Conectada al grafo (sesión 18-ago-2026):** `_render_answer` llama a
  `answer_question` (import perezoso -- no se paga el coste de
  Chroma/embeddings hasta la primera consulta real, no al arrancar la
  app), SIEMPRE después de `check_and_register_query()` -- si el límite
  está agotado, el grafo NUNCA se invoca (verificado leyendo `main()`,
  no solo asumido). **Bug real encontrado y arreglado en la misma
  sesión, al medir memoria con `AppTest`:** `_get_client_ip()` podía
  devolver un valor no-`str` (ej. bajo el harness de test de
  Streamlit) que rompía `check_and_register_query()` al usarse como
  clave de un dict antes de serializar a JSON -- el docstring ya
  prometía degradar a `"unknown"` en cualquier fallo, solo le faltaba
  validar el TIPO del resultado, no solo capturar excepciones.
- `tests/test_openfoodtox_joins.py` — test de regresión del caso
  aspartamo + test de columnas de ADI, **pasan los 3 contra el xlsx
  real** (antes se saltaban por no haber xlsx en `data/raw/`).
- **`mcp/server.py` (sesión 18-ago-2026) -- dos herramientas,
  `search_efsa_opinion` y `get_reevaluation_status`, wrappers finos
  sobre `answer_question`/`resolve_current_opinion` de `graph/build.py`
  (ver "Decisiones de arquitectura ya tomadas", "Dos caminos de
  ejecución del grafo", para el diseño completo y las garantías de
  seguridad).** Implementado con `mcp.server.mcpserver.MCPServer`
  (mcp>=2.0, API distinta de `mcp.server.fastmcp.FastMCP` de la 1.x --
  `requirements.txt` corregido de `mcp>=1.0` a `mcp>=2.0` tras verificar
  la versión real instalada, ver más abajo si aparece un
  `ModuleNotFoundError` al reinstalar con una 1.x vieja). Esquema de
  cada herramienta (un único parámetro `substance: str`, descripción vía
  `Annotated[str, Field(description=...)]`) revisado y aprobado por el
  usuario ANTES de escribir el servidor -- no improvisado durante la
  implementación. Ambas devuelven `dict[str, Any]` con salida
  ESTRUCTURADA (verificado que el tipo de retorno concreto es necesario
  para que el SDK genere `outputSchema` -- un `dict` a secas sin
  parámetros de tipo no lo genera, probado directamente).
  **`tests/test_mcp_server.py` (sesión 18-ago-2026, mismo día) -- 6
  tests, mismo patrón de stubs que `tests/test_nodes.py` para el
  truncamiento del Nodo 4 (sin xlsx/Chroma/API real, sin gastar
  tokens):** esquema de `list_tools()` (nombres, `inputSchema` con
  `substance` como único parámetro requerido, `outputSchema` presente
  en ambas); `get_reevaluation_status` con sustancia conocida tier 1
  (ADI real) y tier 2 (sin ADI, patrón TiO2 -- confirma que no se
  inventa un valor); `search_efsa_opinion` con sustancia conocida;
  degradación con gracia de ambas con sustancia no identificada. **Cada
  test que stubea una función deja la OTRA como `_exploding` (lanza si
  se le llama)** -- confirma en positivo que `get_reevaluation_status`
  nunca invoca `answer_question` (no paga el Nodo 4) y viceversa, no
  solo que el resultado sea el esperado por casualidad. Sin
  `pytest-asyncio` en el proyecto -- `list_tools()`/`call_tool()`
  (async) se invocan con `asyncio.run(...)` dentro de tests síncronos,
  para no añadir una dependencia nueva solo para esto. Suite completa:
  **30 passed, 2 skipped**, sin regresiones tras los cambios en
  `graph/build.py`.

Pendiente, en orden de menor a mayor incertidumbre:
1. QA del corpus de 162 dictámenes contra las calls for data activas
   conocidas (ribonucleótidos E626-635, ácido glucónico E574-579,
   aditivos en forma gaseosa).
2. Resolver la limitación conocida del Nodo 1: `substance_uuid_by_name`
   exige coincidencia exacta del nombre químico canónico en inglés — no
   maneja español ("aspartamo") ni E-numbers ("E 951") todavía.
   **VERIFICADO Y CERRADO (sesión 18-ago-2026, al diseñar el esquema de
   metadatos de Chroma): `SUB` NO tiene ningún campo de E-number
   consultable.** Columnas reales de la hoja: `Document UUID`,
   `Definition`, `Parent UUID`, `ChemicalName`, `OwnerLegalEntity`,
   `ReferenceSubstance.ReferenceSubstance`,
   `TypeOfSubstance.Composition[.Other]`,
   `TypeOfSubstance.Origin[.Other]` -- ninguna es un E-number,
   confirmado inspeccionando la fila de aspartamo. **Implicación para
   el fallback de E-numbers en el Nodo 1: no puede resolverse con un
   lookup directo contra `SUB`** -- la única fuente de E-numbers en
   todo el dataset es texto libre en `LiteratureReference.EFSAOutputTitle`
   (vía el mismo patrón `E_NUMBER_PATTERN`/`e_numbers_from_title` ya
   usado en `ingestion/pdf_naming.py` para el checklist de PDFs), y esa
   extracción es POR DOSSIER, no por sustancia -- un dossier de grupo
   (ej. tartratos, 5 E-numbers en el título, 7 sustancias resueltas
   vía `substances_per_dossier`, ver "Hallazgos verificados") no tiene
   un mapeo 1:1 fiable entre cada E-number citado y cada
   `substance_uuid`. **Diseño futuro propuesto, NO implementado:** una
   tabla auxiliar E-number -> `substance_uuid` derivada por separado
   (con su propia verificación de los casos multi-sustancia, mismo
   nivel de cuidado que el resto de heurísticos de título de este
   proyecto), consultada por el Nodo 1 -- NO como metadato de Chroma
   por chunk (decisión tomada explícitamente al diseñar el esquema de
   metadatos, ver "Hallazgos verificados": el índice de retrieval usa
   `chemical_name`/`substance_uuid`, no `e_number`, precisamente porque
   esta limitación existe y no hay que mezclar un dato no verificado a
   nivel de sustancia con los campos que sí lo son).
   **Esta limitación SIGUE ABIERTA a nivel estructural, no la trates
   como cerrada por el Nodo 1** (sesión 18-ago-2026, continuación 7,
   ver `graph/nodes.py` en "Estado del código" más arriba): el Nodo 1
   ya implementado pide al LLM que normalice español/E-numbers a
   inglés ANTES de llamar a `substance_uuid_by_name`, y acertó en los
   4 casos puntuales probados a mano (1 en español, 1 con E-number) --
   pero es una mitigación parcial dependiente de que el LLM acierte la
   normalización cada vez, verificada en un puñado de casos, NO una
   solución sistemática ni una batería de pruebas amplia. La función
   subyacente sigue sin poder resolver español/E-numbers por sí sola.
   La tabla auxiliar E-number -> `substance_uuid` propuesta arriba
   seguiría siendo la solución estructural si se necesita una garantía
   real, no solo "probablemente funciona para casos comunes".
   - **Variante MÁS ESPECÍFICA de esta misma limitación, diagnosticada
     con datos reales (sesión 19-ago-2026, caso tocoferol) -- distinta
     del problema de español/E-numbers de arriba, no la confundas con
     él:** el LLM del Nodo 1 puede producir un nombre canónico en
     inglés RAZONABLE y bien normalizado, y aun así no resolver, porque
     `SUB.ChemicalName` tiene varias filas casi-duplicadas para lo que
     un humano llamaría "la misma sustancia" -- con prefijos/sufijos
     que el LLM no tiene forma de adivinar. Caso real verificado con
     una llamada real a la API (3 preguntas, español e inglés, todas
     sobre tocoferol): el LLM devuelve consistentemente `"Tocopherol"`
     (genérico, sin prefijo) -- `substance_uuid_by_name("Tocopherol")`
     devuelve `None`, porque esa cadena exacta no existe en `SUB`. Pero
     la sustancia SÍ está en el programa, con contenido real e
     indexado: de las 7 variantes de nombre que sí existen en `SUB`
     para tocoferoles, **4 resuelven perfectamente** (`structured_result`
     completo + 5 `retrieved_chunks` cada una) -- `DL-alpha-tocopherol`,
     `Tocopherol-rich extract`, `Gamma-tocopherol`, `Delta-tocopherol`,
     todas apuntando correctamente al dictamen de grupo de 2015 (DOI
     `10.2903/j.efsa.2015.4247`) -- y 3 no resuelven nada (`beta-tocopherol`,
     `tocopherols, total`, `Alpha-tocopherol` con mayúscula, sin
     dictamen vinculado ni chunks). Confirma que NO es un bug de
     retrieval del Nodo 2 independiente de un fallo del Nodo 3 --
     ambos fallan a la vez porque comparten la misma causa raíz en el
     Nodo 1 (`graph/build.py` salta el Nodo 3 y deja `retrieved_chunks`
     vacío cuando `substance_uuid` no resuelve, ver "Dos caminos de
     ejecución del grafo" más abajo).
   - **Fix de mensaje YA APLICADO (mismo día, `graph/nodes.py`,
     `_format_retrieved_chunks`):** el texto que se mostraba con
     `retrieved_chunks` vacío afirmaba **"el corpus de PDFs todavía no
     está indexado"** -- FALSO (67.827 chunks reales, verificado
     repetidamente en sesiones anteriores) y engañoso sobre la causa
     real. Corregido a dos mensajes distintos según si
     `structured_result` también es `None`: si SÍ lo es, "no se ha
     podido resolver de forma exacta la sustancia mencionada en la
     pregunta" (el caso de tocoferol, diagnosticado arriba); si
     `structured_result` NO es `None` (el dictamen vigente sí se
     resolvió por OpenFoodTox pero esta sustancia concreta no tiene
     chunks indexados -- causa distinta, no diagnosticada a fondo
     todavía, ver pendiente más abajo), "no se han encontrado
     fragmentos narrativos indexados para esta sustancia concreta,
     aunque sí se resolvió el dictamen vigente". La regla 3 de
     `NODE_4_GROUNDING_RULES` (el system prompt del Nodo 4) tenía la
     MISMA causa falsa incrustada -- corregida también, para que el
     LLM no le siga repitiendo esa explicación inventada al usuario
     final aunque el dato ya venga bien formateado.
   - **Segundo caso real confirmado, mismo patrón, distinto matiz --
     Caramel colours / E150a (sesión 19-ago-2026, reportado por el
     usuario tras ver el mensaje viejo en el deploy real).**
     Verificado con `grep` en TODO el código fuente (no solo
     `nodes.py`): **no existe ningún segundo punto que genere el texto
     "todavía no está indexado"** -- el fix de arriba es el único
     lugar del código que lo producía, y ya no lo produce (confirmado
     además con una llamada real de extremo a extremo,
     `answer_question("Is E150a (Caramel colour) safe as a food
     additive?")`, que devuelve correctamente "no se ha podido
     resolver de forma exacta la sustancia..." con el código tal como
     está en este commit). El Nodo 1 normaliza consultas reales sobre
     E150a a `"Caramel colour"` o `"Caramel colour (plain)"` (probado
     con 3 preguntas reales, español e inglés) -- ninguna de las dos
     coincide con `SUB.ChemicalName`, que solo tiene `"Caramel
     colours"` (plural), `"Plain caramel"`, `"Ammonia caramel"`,
     `"Caustic sulphite caramel"`, `"Sulphite ammonia caramel"`.
     **Matiz importante frente a tocoferol: aquí las 5 variantes SÍ
     resuelven perfectamente** (mismo dictamen de grupo, "re-evaluation
     of caramel colours (E 150 a,b,c,d)", `structured_result` completo
     + 5 chunks cada una) -- a diferencia de tocoferol, donde solo 4 de
     7 variantes resolvían. Confirma que el fallo es 100% del Nodo 1
     (ninguna variante nombrada por el LLM coincide), no una mezcla de
     dato incompleto + resolución -- y refuerza el riesgo de falsos
     positivos ya anotado abajo para el fallback de substring: aquí
     TODAS las filas candidatas son "correctas" (mismo dictamen), así
     que un fallback ingenuo habría funcionado por casualidad en este
     caso concreto pero no en el de tocoferol -- no hay forma de saber
     de antemano cuál de los dos patrones aplica sin la batería de
     pruebas todavía no construida. **Si el usuario sigue viendo el
     texto viejo en el deploy real después de este commit, la causa
     más probable no es un bug de código -- es que la prueba se hizo
     antes de que el contenedor de Streamlit Cloud terminara de
     reiniciarse con el commit nuevo** (confirmar reproduciendo tras
     un "Reboot app" manual, no solo un nuevo push).
   - **Diseño futuro propuesto para la resolución en sí, NO
     implementado -- fallback de coincidencia por substring/prefijo
     cuando la exacta falla** (ej. si `"Tocopherol"` no resuelve,
     probar `SUB.ChemicalName` que contenga `"tocopherol"` como
     substring, case-insensitive): **riesgo real de falsos positivos
     que hay que resolver con cuidado antes de tocarlo, no es un
     cambio trivial.** Un substring genérico puede casar con MÁS de
     una fila (como ya pasa aquí: 7 filas contienen "tocopherol", con
     resultados MUY distintos -- 4 resuelven bien, 3 no resuelven
     nada, y no hay ninguna señal en el propio nombre para elegir
     automáticamente cuál de las 7 es "la correcta" para una pregunta
     genérica del usuario). Un fallback ingenuo (ej. "coge la primera
     coincidencia") podría resolver a una fila SIN dictamen vinculado
     igual de fácil que a una con él, sustituyendo un fallo visible
     (`None`, mensaje honesto) por un resultado incorrecto silencioso
     -- peor que el problema actual. Cualquier implementación futura
     necesita, como mínimo: (a) desambiguar entre múltiples matches de
     substring en vez de coger el primero a ciegas, (b) preferir filas
     que SÍ tengan un dictamen vinculado sobre las que no, y (c) una
     batería de pruebas sobre varios casos multi-variante reales --
     ahora hay 2 casos documentados (tocoferol: 4/7 variantes
     resuelven; Caramel colours/E150a: 5/5 resuelven), y los dos
     apuntan en direcciones opuestas sobre si "cualquier match" sería
     seguro, lo que confirma que hace falta una muestra bastante más
     amplia antes de confiar en ello -- ninguno de los tres puntos
     está diseñado todavía, esto es solo el problema y la idea de
     dirección, no una propuesta lista para implementar.
   - **RESUELTO (sesión 19-ago-2026, continuación posterior a lo de
     arriba) -- implementada la resolución multi-candidato, NO el
     fallback de substring "coge cualquier match" descartado arriba por
     riesgo de falso positivo silencioso.** Decisión de producto
     explícita del usuario, distinta de "elegir el mejor candidato":
     cuando hay varios nombres razonablemente parecidos, el sistema
     **nunca elige uno en silencio** -- resuelve y presenta TODOS los
     candidatos plausibles por separado (cada uno con su propio dictamen
     vigente y sus propios `retrieved_chunks`), dejando que el usuario
     identifique cuál buscaba. Esto es justo el (a)/(b) que el párrafo
     de arriba pedía como mínimo para cualquier implementación futura,
     resuelto de raíz: no hace falta desambiguar "cuál de las N es la
     correcta" ni preferir filas con dictamen vinculado sobre las que no
     -- se muestran todas, con su propio dato (o su propia ausencia de
     dato) cada una.
   - **Hipótesis del símbolo griego (α/β/γ vs. palabra latina) probada y
     DESCARTADA con datos reales, antes de implementar nada** -- el
     usuario sospechaba que el problema de tocoferol era de símbolo
     griego vs. palabra escrita; verificado que `SUB.ChemicalName` NO
     tiene NINGUNA fila de tocoferol con símbolo griego Unicode (las 7
     variantes reales usan palabra latina: `alpha`, `beta`, `Gamma`,
     `Delta`; solo 14/7.871 filas de TODO el dataset usan símbolos
     griegos, ninguna relevante aquí). **Causa real, verificada con 7
     llamadas reales al Nodo 1:** el LLM hyphena de forma inconsistente
     según si la pregunta del usuario ya trae guion -- `"alpha
     tocopherol"` (sin guion) -> `"Alpha tocopherol"` (sin guion, NO
     resuelve, `SUB` tiene `"Alpha-tocopherol"` con guion) vs.
     `"α-tocopherol"`/`"alfa-tocoferol"` (con guion o símbolo) ->
     siempre `"Alpha-tocopherol"` (con guion, SÍ resuelve). Inconsistente
     incluso entre casos similares (`"gamma tocopherol"` sin guion en la
     pregunta dio `"Gamma-tocopherol"` CON guion en la respuesta) -- no
     es un patrón fiable por sí solo, pero el fix de normalización
     espacio<->guion de abajo lo cubre sin necesidad de entenderlo del
     todo.
   - **Diseño final, implementado (`OpenFoodToxStore.resolve_substance_candidates`,
     `ingestion/openfoodtox.py`):** tres escalones, el primero que
     produzca resultado(s) gana:
     1. Exacto (case-insensitive) contra `SUB.ChemicalName` completo --
        tier `"exact"`, score 100. Corregido de paso un bug latente real
        encontrado en esta sesión: `SUB.ChemicalName` tiene 9 nombres
        duplicados con distinto UUID (ej. `"Sodium saccharin"` x2, SÍ
        dentro del universo de 246 resolubles) -- `substance_uuid_by_name`
        (sin cambios, sigue usándose como atajo de test) solo devolvía
        `matches.iloc[0]`, descartando el segundo en silencio;
        `resolve_substance_candidates` devuelve TODOS.
     2. Igual, probando `name.replace(" ", "-")` y
        `name.replace("-", " ")` como coincidencia exacta adicional --
        tier `"exact_normalized"`, score 100, el fix de tocoferol de
        arriba. Sigue siendo coincidencia EXACTA, cero riesgo de
        ambigüedad nuevo. Recupera 2 de los 3 variantes de tocoferol que
        antes no resolvían (`Alpha-tocopherol`, `beta-tocopherol`) --
        solo `"tocopherols, total"` sigue sin recuperarse por esta vía
        (no es un problema de guion/espacio).
     3. Fuzzy (`rapidfuzz.fuzz.ratio`, NO `WRatio` -- `WRatio` probado y
        descartado, da falsos positivos graves por coincidencia de
        substring, ej. `"Xylene"` -> `"Perfluorobutylethylene"` al
        81,82%) contra un universo RESTRINGIDO a las 246 sustancias con
        dictamen de reevaluación resoluble (`substances_per_dossier(require_adi=False)`
        sobre `current_reevaluation_corpus()`), NO el `SUB.ChemicalName`
        completo (7.871 filas, todos los dominios regulatorios de
        OpenFoodTox -- pesticidas, veterinaria, contaminantes). **Esto es
        una decisión de ALCANCE, no solo una optimización de ruido** --
        mismo tipo de contaminación cruzada de dominio que causó el bug
        real de Sunset Yellow FCF (Grupo B, ver "Hallazgos verificados"
        arriba): verificado que contra el universo completo, consultas
        sin relación real llegan a ~48% de similitud con sustancias de
        otros programas regulatorios. `FUZZY_MATCH_LOW_THRESHOLD = 60`,
        calibrado con datos reales (no a ciegas):
        - `"Tocopherol"` (salida REAL del Nodo 1 para preguntas
          genéricas de tocoferol): 69,23 Delta-tocopherol, 69,23
          Gamma-tocopherol, 62,07 DL-alpha-tocopherol, 60,61
          Tocopherol-rich extract -- los 4 caen sobre el umbral; 55,56
          Glycerol (sustancia real no relacionada) queda excluido.
        - `"plai caramel"` (typo real): 88,00 Plain caramel, 66,67
          Ammonia caramel, 61,11 Sulphite ammonia caramel -- los 3 caen
          sobre el umbral. **Trade-off conocido y aceptado, no oculto:**
          para un typo claro de una sola sustancia, este umbral también
          incluye sustancias reales de la misma familia -- no es un
          falso positivo inventado, pero sí más candidatos de los
          estrictamente necesarios. No se persigue un umbral "perfecto"
          sin más señal que un ratio de caracteres.
        - Consultas sin relación real (`"quantum flux capacitor"`,
          `"banana smoothie recipe"`, `"Xylene"`): máximo 46-57 sobre el
          universo restringido -- ninguna cruza el umbral. Cero falsos
          positivos verificados.
     El resultado final se ordena SIEMPRE con `_candidate_sort_key`
     (`(-match_score, chemical_name.lower())` -- score descendente,
     nombre alfabético ascendente como desempate) antes de devolverse,
     para que `candidates[0]` ("el candidato top", el usado por el
     contrato MCP de un único resultado y por `structured_result`
     singular de `AnswerResult`) sea determinista incluso con empate
     exacto de score -- verificado real con `"Tocopherol"`:
     Delta-tocopherol y Gamma-tocopherol empatan a 69,23, y el orden
     ("d" < "g") da siempre Delta-tocopherol primero.
   - **`GraphState` cambia de contrato (mismo nivel de decisión que la
     entrada "Contrato Nodo 2 -> Nodo 4" de arriba, no la reabras sin
     motivo nuevo):** `substance_uuid: str | None` ->
     `substance_candidates: list[SubstanceCandidate]` (+
     `candidates_truncated: bool`); `structured_result: OpinionReference
     | None` -> `structured_results: dict[str, OpinionReference | None]`
     (clave = `substance_uuid`); `vigencia_ambigua: bool` (global, ya
     documentado como reservado/sin consumidor) -> `currency_verification_incomplete:
     dict[str, bool]` (mismo cálculo, por candidato); campo `citation`
     ELIMINADO (verificado con `grep` que no tenía ningún consumidor
     real, estado muerto desde que se escribió). Los 4 nodos y
     `graph/build.py::_route_after_retrieval` tocados.
   - **Presupuesto de `retrieved_chunks` con 2+ candidatos, decisión
     explícita del usuario -- dos topes, nunca un reparto sin fondo**
     (`graph/nodes.py`): `TOTAL_CHUNK_BUDGET = 15`, `MIN_K_PER_CANDIDATE
     = 3` (nunca se diluye un candidato por debajo), `MAX_CANDIDATES_SHOWN
     = 5` (`ingestion/openfoodtox.py` -- si hay más candidatos, se
     muestran los 5 de mayor similitud y se anuncia explícitamente en el
     propio prompt de usuario del Nodo 4, nunca en silencio).
     `k_por_candidato = min(5, max(3, 15 // N_mostrados))` -- con 1
     candidato da k=5 (idéntico al comportamiento de antes de esta
     sesión, sin regresión).
   - **`_build_user_prompt` (Nodo 4) con 0 o 1 candidato produce
     EXACTAMENTE el mismo formato de prompt que antes de esta sesión**
     -- sin envoltorio de "candidato 1 de 1", para no regresar el
     comportamiento ya probado (caso aspartamo, Shellac). Con 2+, cada
     candidato se presenta en su propio bloque `=== Candidato N:
     {nombre} ===`, con una instrucción incrustada en el propio prompt
     de usuario (mismo patrón que el aviso de tier 3 ya existente, NO
     una regla nueva de `NODE_4_GROUNDING_RULES`/
     `NODE_4_SAFETY_COMMUNICATION_RULES`) pidiendo al LLM que no las
     fusione ni asuma cuál buscaba el usuario. Verificado con llamada
     real a la API (`answer_question("Is tocopherol safe as a food
     additive?")`): los 4 candidatos se presentan por separado, en el
     orden determinista esperado (Delta primero), cada uno con su propio
     bloque de ADI/justificación/discusión/fragmentos, y el texto final
     dice explícitamente "cuatro sustancias... no se ha asumido cuál de
     ellas buscaba el usuario" -- sin violar la restricción no
     negociable #1 (ningún candidato sin ADI numérico se describe como
     "no seguro").
   - **MCP (`mcp/server.py`) queda FUERA de este cambio, explícitamente
     -- pendiente aparte, no una omisión.** Sigue devolviendo un único
     resultado con el contrato JSON de siempre: `resolve_current_opinion`/
     `answer_question` (`graph/build.py`) toman `candidates[0]` (el
     candidato top, orden determinista) para rellenar `structured_result`
     singular -- verificado con una llamada MCP real
     (`get_reevaluation_status("aspartame")`) que el JSON de salida no
     cambió de forma. `AnswerResult` gana 2 campos ADITIVOS con default
     (`substance_candidates`, `structured_results`) para quien SÍ quiera
     ver todos los candidatos -- MCP no los usa. Diseño de un esquema
     multi-resultado dedicado para MCP queda como trabajo futuro, no
     decidido ni empezado. **Los 6 tests de `tests/test_mcp_server.py`
     pasan SIN haberse modificado ni una línea** (verificado con `git
     diff --stat` tras la implementación) -- si algún cambio futuro de
     `graph/build.py` los rompe, es señal de acoplamiento no detectado a
     investigar, no un efecto colateral a parchear sobre la marcha.
   - **RESUELTO (misma sesión, continuación posterior) -- el "trabajo
     futuro, no decidido ni empezado" de arriba SÍ se decidió e
     implementó.** `search_efsa_opinion`/`get_reevaluation_status`
     devuelven ahora SIEMPRE `{"candidates_found": N, "candidates_shown":
     M, "results": [...]}` -- 1 elemento en `results` en el caso común,
     N en el ambiguo, NUNCA un objeto plano con un único resultado
     elegido en silencio. Tres alternativas evaluadas antes de decidir
     (mismo nivel de detalle que otras decisiones de este documento):
     - **(A, elegida) array siempre.** **(B, descartada)** objeto único +
       campo `candidates` opcional solo si hay ambigüedad. **(C,
       descartada)** las dos herramientas intactas + una tercera
       herramienta nueva de desambiguación.
     - **Por qué A, no solo "no hay cliente real que proteger" --**
       verificado antes de decidir, no como excusa a posteriori:
       `server.list_tools()` real muestra que `output_schema` de ambas
       herramientas es `{"additionalProperties": true}`, SIN ningún
       campo declarado formalmente -- no hay contrato de esquema MCP
       que romper con ningún cambio de forma, la "ruptura de
       compatibilidad" es puramente sobre código de cliente hipotético,
       no sobre el protocolo en sí. **Pero el motivo de fondo para
       preferir A sobre B/C es otro, y es el que pesó más: B y C dejan
       la honestidad ante la ambigüedad como OPCIONAL para el
       consumidor** -- un cliente que no sepa mirar el campo
       `candidates` (B), o que nunca llame a la tercera herramienta de
       desambiguación (C), vuelve a elegir un candidato en silencio sin
       enterarse de que había otros -- exactamente el problema que el
       resto del sistema (Nodo 1-4) pasó esta sesión entera eliminando.
       **Con A, la honestidad es ESTRUCTURAL:** no existe ninguna forma
       de leer la respuesta sin toparse con el array `results` y su
       longitud real, sin que el cliente tenga que saber buscar un
       campo opcional o una herramienta aparte.
     - **Plumbing nuevo necesario, no solo cambiar `mcp/server.py`:**
       `GraphState.candidates_total_found: int` (`graph/nodes.py`,
       poblado en `extract_entity_node` -- el total ANTES del recorte a
       `MAX_CANDIDATES_SHOWN`, distinto de `candidates_truncated: bool`,
       que solo dice SI hubo recorte, no CUÁNTOS había). `AnswerResult`
       gana `candidates_total_found: int = 0` (aditivo). `ReevaluationStatus`
       (hasta ahora con la forma singular de siempre, `substance_uuid`/
       `structured_result`) gana los mismos 3 campos plurales que
       `AnswerResult` ya tenía (`substance_candidates`,
       `structured_results`, `candidates_total_found`) -- necesarios
       porque ahora es `get_reevaluation_status` quien los consume
       directamente, no solo un caller hipotético futuro.
     - **Forma final de `results[i]`:** `search_efsa_opinion` -- por
       candidato: `chemical_name`, `match_type`, `match_score`,
       `dossier_title`, `doi`, `retrieved_chunks_count` (contado por
       `substance_uuid` sobre `retrieved_chunks`, NO dividido a partes
       iguales -- cada candidato cuenta solo SUS propios chunks).
       `answer` se queda FUERA del array, a nivel superior -- sigue
       siendo un ÚNICO texto narrativo (el Nodo 4 ya trata cada
       candidato por separado dentro de esa misma prosa, ver
       `_build_user_prompt`) -- partirlo en N respuestas exigiría N
       llamadas al LLM, coste innecesario para lo que una sola
       generación bien diseñada ya resuelve. `get_reevaluation_status`
       -- por candidato: los mismos campos que antes tenía el objeto
       plano (`dossier_found`, `dossier_title`, `doi`,
       `date_of_evaluation`, `adi_value`, `adi_unit`,
       `adi_justification`, `discussion_available`) más
       `chemical_name`/`match_type`/`match_score` para identificar cada
       fila. `safety_note` se queda fuera del array en ambas (constante
       fija, no varía por candidato).
     - **Verificado con llamada MCP real, no solo con los tests --
       tocoferol, no solo aspartamo** (`get_reevaluation_status("tocopherol")`,
       vía `asyncio.run(server.call_tool(...))`, sin mock):
       `candidates_found: 4, candidates_shown: 4`, con las 4 variantes
       reales (Delta/Gamma/DL-alpha/Tocopherol-rich extract) en
       `results`, mismo orden determinista que el resto del sistema.
       `search_efsa_opinion("aspartame")` confirma la regresión: sigue
       dando `candidates_found: 1, candidates_shown: 1`, sin cambio de
       comportamiento para el caso común.
     - **`tests/test_mcp_server.py` reescrito por completo para la nueva
       forma** (los 6 tests existentes, más 2 nuevos para el caso de
       2+ candidatos, uno por herramienta) -- a diferencia de la sesión
       anterior, aquí SÍ se tocó el archivo a propósito, porque ahora sí
       es la forma del propio MCP la que cambió, no un efecto colateral
       de otro cambio.
   - Detalle completo de la implementación, calibración y verificación:
     `PROGRESS.md`, sesión 19-ago-2026.
   - **Hallazgo real tras implementar, SIN resolver -- pendiente aparte
     explícito, verificado con llamada real, no una suposición: el caso
     ORIGINAL que motivó todo este diseño ('plai caramel') NO llega a
     usar `resolve_substance_candidates` en el pipeline completo
     (`answer_question`).** `resolve_substance_candidates("plai
     caramel")` funciona exactamente como se calibró (`Plain caramel`
     88.0 como candidato top, verificado directamente contra el store)
     -- pero probado con 4 formulaciones distintas de pregunta en
     lenguaje natural ("What is plai caramel used for...", "Is plai
     caramel safe...", "Tell me about plai caramel", "What does the
     EFSA opinion say about plai caramel?"), el Nodo 1
     (`extract_entity_node`) devuelve `NONE` en las 4 -- nunca propone
     ningún `substance_name`, así que `resolve_substance_candidates`
     nunca se llama (`extract_entity_node` solo la invoca `if
     substance_name else []`). Causa probable: la regla 4 del prompt del
     Nodo 1 (`NODE_1_ENTITY_EXTRACTION_PROMPT`, `graph/nodes.py`) --
     "No inventes un nombre si no estás razonablemente seguro -- en ese
     caso, responde NONE en vez de adivinar" -- filtra typos agresivos
     (una palabra que no reconoce como ningún nombre químico plausible)
     ANTES de que puedan llegar a la capa de fuzzy matching de esta
     sesión, que está diseñada precisamente para tolerar typos.
     **Contraste real con los typos que SÍ funcionan de extremo a
     extremo** (ver PROGRESS.md, sesión 19-ago-2026): "asprtame"/
     "Aspartam" sí resuelven porque el Nodo 1 SÍ propone un nombre (algo
     como "Aspartame", con la ortografía ya corregida por el propio
     LLM) -- el fuzzy matching downstream nunca hace falta invocarlo
     para esos casos, así que no son una prueba real de que la capa de
     esta sesión sea alcanzable desde una pregunta de usuario con un
     typo que el LLM no sepa corregir por su cuenta. "plai caramel" es
     el caso contrario: un typo lo bastante agresivo (o una sustancia lo
     bastante poco conocida por el LLM) para que el Nodo 1 no se atreva
     a proponer nada.
     **NO arreglado en esta sesión -- a propósito, decisión del
     usuario.** La solución PROBABLE a futuro (NO diseñada ni
     implementada, solo la dirección): relajar la regla 4 del Nodo 1
     para que proponga un nombre con menor confianza cuando la pregunta
     suena claramente a nombre de aditivo (aunque no lo reconozca con
     certeza), confiando en que el fuzzy matching downstream ya
     implementado filtre lo irrelevante (ver el umbral
     `FUZZY_MATCH_LOW_THRESHOLD` y el universo restringido a 246
     sustancias, ambos ya diseñados para absorber ruido). **Esto es un
     cambio de PROMPT del Nodo 1, con su propio riesgo de calibración
     (relajar la regla 4 puede aumentar falsos positivos de sustancias
     inventadas para preguntas que de verdad no mencionan ningún
     aditivo -- el motivo original de que la regla exista) -- no es una
     extensión trivial de lo de hoy, necesita su propia batería de
     pruebas antes de tocarse.** Si se retoma, verificar primero cuántas
     preguntas reales caen en este hueco (typo agresivo + Nodo 1
     rechaza) antes de relajar la regla a ciegas.
   - **Investigación de continuación (misma sesión, 19-ago-2026) --
     prompt relajado probado con llamadas reales, NO puesto en
     producción por decisión explícita del usuario ("no toques
     NODE_1_ENTITY_EXTRACTION_PROMPT en producción con esta muestra tan
     pequeña"). Marcado de PRIORIDAD BAJA, no bloqueante -- caso más
     idiosincrático que sistémico, ver por qué abajo.** Resultados
     completos de las dos baterías de prueba (5 typos + 6 preguntas sin
     sustancia, cada una con el prompt actual y una versión relajada de
     la regla 4) en el historial de la sesión, no repetidos aquí en
     detalle -- resumen de lo que importa para decisiones futuras:
     - **El fallo de "plai caramel" es sensible al FRASEO, no solo a la
       regla 4 -- mismo patrón ya diagnosticado (y tampoco resuelto
       todavía) para el Nodo 2 con TiO2/genotoxicidad más arriba (ver
       "DIAGNÓSTICO... la calidad del retrieval es sensible al fraseo
       de la pregunta").** Con el prompt ACTUAL sin cambios, la frase
       pelada `"plai caramel"` SÍ resuelve a `"Plain caramel"`; la MISMA
       cadena embebida en una pregunta completa ("What is plai caramel
       used for as a food additive?") da `NONE`, reproducido 2/2 veces
       de forma determinista (`temperature=0.0`). No es que la regla 4
       sea intrínsecamente incapaz de tolerar este typo -- es que el
       contexto de la frase completa cambia la respuesta.
     - **"plai caramel" NO es representativo de una clase amplia de
       typos rotos -- de 5 typos probados en forma de pregunta completa
       (`asprtame`, `titanum doxide`, `sorbik acid`, `xanthum gumm`,
       `plai caramel`), 4 YA resolvían bien con el prompt ACTUAL sin
       ningún cambio.** Solo "plai caramel" falla -- hipótesis no
       verificada más allá de la observación: "caramel" es una palabra
       común en inglés (a diferencia de "aspartame"/"titanium dioxide",
       más claramente nombres químicos), lo que puede hacer que el LLM
       dude más de si la pregunta se refiere a un aditivo concreto
       cuando está embebida en una frase completa.
     - **El prompt relajado SÍ elimina el `NONE`, pero no da el nombre
       esperado -- generaliza al nombre de GRUPO, no a la sal
       específica.** Para "plai caramel" en pregunta completa, propone
       `"Caramel colour"` (no `"Plain caramel"`), que
       `resolve_substance_candidates` resuelve a un único candidato
       confiado (`"Caramel colours"`, fuzzy 96,55) -- verificado que
       `"Caramel colours"` y `"Plain caramel"` apuntan al MISMO
       dictamen (mismo título, "re-evaluation of caramel colours (E 150
       a,b,c,d)", filas hermanas del mismo dossier de grupo con
       `Document UUID` distinto). Funcionalmente el usuario llegaría al
       contenido correcto, aunque no a la sal E150a concreta que
       nombró.
     - **Sin regresión detectada en los 6 casos de "sin sustancia"
       probados** (español e inglés, incluida "aditivos en general"
       sin nombrar ninguno -- el caso más parecido a un falso positivo
       posible): el prompt relajado sigue devolviendo `NONE` en los 6,
       igual que el actual. Dentro de esta muestra pequeña, el riesgo
       que motivó no tocar la regla a la ligera (inventar sustancias
       para preguntas sin ninguna) no se materializó -- pero la muestra
       (6 casos) es demasiado pequeña para tratarlo como garantía.
     - **Diseño futuro PREFERIBLE, según el usuario, sobre relajar la
       regla 4 globalmente -- NO diseñado en detalle, solo la
       dirección:** en vez de cambiar el umbral de confianza del Nodo 1
       para TODAS las preguntas (con el riesgo de calibración ya
       anotado arriba), una SEGUNDA PASADA aislada del Nodo 1 -- solo
       cuando la primera pasada da `NONE` pero la pregunta contiene
       palabras que podrían ser un nombre de sustancia mal escrito --
       que reformule/aísle esa entidad concreta antes de decidir. Mismo
       principio de intervención dirigida (no un cambio global) que se
       consideró para el caso de TiO2 en el Nodo 2 -- **ojo, ese caso
       tampoco tiene la reformulación implementada todavía, sigue
       siendo "diagnosticado, no resuelto" según su propia entrada más
       arriba** -- no lo trates como un precedente ya funcionando, es
       la misma clase de solución propuesta y sin construir en los dos
       sitios. Ninguna parte de esta segunda pasada (cuándo disparar,
       cómo aislar la entidad, qué prompt usar) está diseñada todavía.
   - **IMPLEMENTADO (misma sesión, 19-ago-2026, continuación posterior):
     mensaje honesto de "sustancia no identificada" cuando
     `substance_candidates` está vacío -- no bloqueado por la
     investigación de arriba (que sigue sin resolver), es un fix
     independiente del texto que se muestra en ese caso, no de la
     resolución en sí.**
     - **Decisión: enlace FIJO a la página de aditivos de EFSA, NO un
       buscador con parámetro.** Se investigó primero
       `https://www.efsa.europa.eu/en/search?query={término}` -- el
       parámetro `query=` es real (reaparece en los enlaces internos
       del propio sitio, y `curl` confirma que solo `/en/search`
       específicamente da 403 de CloudFront, no el resto del dominio) --
       pero **el usuario lo verificó en un navegador real y confirmó que
       NO filtra de verdad**: muestra el mismo listado genérico
       ("Results 1-10 of 18734", títulos sin relación con la sustancia)
       tanto para "aspartame" como para una cadena sin sentido -- SPA
       cuyo filtrado real (si existe) depende de JavaScript del lado
       del cliente que ni la verificación automatizada de esta sesión
       ni, según el usuario, el navegador real, mostraron funcionando.
       **Descartado.** En su lugar: `EFSA_FOOD_ADDITIVES_URL =
       "https://www.efsa.europa.eu/en/topics/topic/food-additives"`
       (`graph/nodes.py`) -- la página general de aditivos alimentarios
       de EFSA, verificada con `curl` (HTTP 200, sin bloqueo) y con
       `WebFetch` (landing page real, cita la cifra de 315 sustancias
       pre-2009 en reevaluación -- misma cifra ya verificada y citada
       en el README de este proyecto -- con enlaces a OpenEFSA y a
       dictámenes del EFSA Journal).
     - **Texto del mensaje, deliberadamente SIN la afirmación "esta
       sustancia no tiene reevaluaciones recientes"** -- esa frase no es
       verificable por el sistema y podría ser FALSA: el caso real
       "plai caramel" de esta misma sesión demostró que la sustancia SÍ
       existía y SÍ tenía un dictamen vigente indexado (Plain caramel,
       parte del grupo E150a-d) -- el fallo fue de RESOLUCIÓN DE NOMBRE
       (ver el punto de arriba, sensibilidad al fraseo del Nodo 1), no
       de ausencia real de reevaluación. Mensaje nuevo, honesto sobre la
       incertidumbre: "No se ha podido identificar esta sustancia
       dentro del corpus indexado (aditivos en reevaluación bajo el
       Reglamento UE 257/2010); puede que esté fuera de ese alcance, o
       que el nombre no se haya reconocido correctamente. Para buscar
       directamente en las fuentes de EFSA: [enlace fijo], usando el
       término "[query del usuario tal cual]"."
     - **El término incluido es `user_query` (la pregunta completa tal
       como la escribió el usuario), NO `substance_name`** (la
       propuesta normalizada/traducida del LLM del Nodo 1) -- decisión
       deliberada: en el caso donde este mensaje aplica,
       `substance_name` por definición no resolvió nada (o ni siquiera
       existe, si el Nodo 1 respondió `NONE`), así que mostrarlo en vez
       del texto original arriesgaría presentar al usuario un nombre
       que ni él escribió ni el sistema pudo verificar, como si fuera
       fiable. Verificado con llamada real
       (`answer_question("What is plai caramel used for as a food
       additive?")`): la respuesta final incluye el enlace fijo y cita
       la pregunta completa del usuario tal cual, sin reformularla.
     - **Implementación acotada a propósito, sin tocar el caso de 1
       candidato:** nueva función `_format_unresolved_substance_message`
       (`graph/nodes.py`), usada SOLO cuando `substance_candidates` está
       vacío (`_build_user_prompt`, ahora con 3 ramas explícitas: 0
       candidatos / 1 candidato / 2+ candidatos, en vez de agrupar 0 y 1
       juntos como antes). El mensaje genérico interno YA EXISTENTE de
       `_format_retrieved_chunks` (para "chunks vacíos +
       structured_result None") se mantiene SIN CAMBIOS -- sigue
       usándose para el caso distinto de un candidato SÍ identificado
       (1 o dentro de 2+) cuyo dictamen concreto no resuelve, donde el
       mensaje de "no se ha podido identificar la sustancia" no
       aplicaría con propiedad (la sustancia SÍ se identificó). Ese otro
       mensaje tiene una inconsistencia latente preexistente
       (potencialmente engañoso en ese caso concreto, ya presente antes
       de esta sesión) que NO se tocó aquí -- fuera de alcance de lo
       pedido, no una omisión.
   - **RESUELTO (misma sesión, continuación posterior) -- la
     inconsistencia latente de arriba SÍ se arregló, con un caso real
     verificado, no en abstracto.** Caso real usado:
     `"Olive leaf dry extract from O. europaea L."` -- ya documentado
     como caso de regresión en `test_openfoodtox_joins.py` desde la
     sesión 17-ago-2026 (`test_olive_leaf_extract_has_no_real_food_additive_opinion`):
     resuelve por nombre EXACTO en `SUB` (`substance_candidates` con 1
     elemento, tier `"exact"`), pero su única fila en `DOSSIER` es un
     dossier de PIENSO ANIMAL -- tras excluirlo por dominio,
     `current_reference_value_opinion` da `None`, sin ningún dictamen
     alimentario real. Probado con el pipeline real completo
     (`hybrid_retrieval_node` + `verify_currency_node` +
     `_build_user_prompt`, sin mock, contra el store y Chroma reales)
     ANTES de escribir el fix, para confirmar el bug en vivo, no solo en
     teoría: el prompt resultante se contradecía a sí mismo -- la línea
     `"Sustancia identificada: Olive leaf dry extract..."` aparecía
     justo encima de un mensaje que afirmaba `"no se ha podido resolver
     de forma exacta la sustancia mencionada en la pregunta"`.
     - **Distinción entre los DOS tipos de bug de mensaje cazados esta
       semana en este mismo archivo de nodos (`graph/nodes.py`) --
       relacionados pero de naturaleza distinta, no confundirlos:**
       1. **Incondicionalmente falso** (el bug de "el corpus de PDFs
          todavía no está indexado", sesión 19-ago-2026 anterior, caso
          tocoferol/E150a): el mensaje afirma algo que NUNCA es cierto
          en ningún contexto de la aplicación (el corpus SIEMPRE tiene
          67.827 chunks indexados) -- el fix fue cambiar el texto en sí,
          sin tocar la lógica de cuándo se dispara.
       2. **Condicionalmente falso por reutilización sin contexto**
          (este bug, "Olive leaf dry extract"): el mensaje ERA cierto en
          el contexto para el que se escribió originalmente (0
          candidatos -- "no se ha podido resolver... la sustancia"), y
          SIGUE siendo cierto ahí, pero la misma función
          (`_format_retrieved_chunks`) se reutilizaba sin distinguir ese
          caso del de "sí hay candidato, pero sin dictamen concreto" --
          donde la MISMA frase pasa a ser falsa. El fix real no fue solo
          cambiar el texto, fue separar los DOS CONTEXTOS que antes
          compartían una función: `_build_user_prompt` con 0 candidatos
          ahora usa `_format_unresolved_substance_message` (nunca
          `_format_retrieved_chunks`); `_format_retrieved_chunks` en sí
          se documentó con la precondición explícita de que solo se
          llama hoy cuando YA hay un candidato identificado, y su propio
          mensaje se corrigió para dejar de asumir lo contrario.
     - **Lección para el patrón general, más allá de este caso
       concreto:** un mensaje de error/degradación escrito para UN
       contexto específico (aquí, "0 candidatos") puede volverse
       engañoso si la misma función que lo produce se reutiliza después
       para un contexto distinto (aquí, "candidato identificado, sin
       dictamen") sin que la función sepa distinguirlos. No basta con
       revisar si un mensaje es cierto en abstracto -- hay que revisar
       en qué contextos REALES se dispara hoy (grep de callers, no
       suposición) antes de darlo por seguro.
     - Verificado también con una llamada real de extremo a extremo,
       incluida la generación del Nodo 4 (`generate_answer_node` con
       `llm_client` real, sin mock): la respuesta final nombra la
       sustancia correctamente y dice honestamente que no se encontró
       ningún dictamen vigente para ella en el corpus, sin ninguna
       contradicción con el nombre ya identificado.
     - Test de regresión con este caso exacto:
       `tests/test_nodes.py::test_build_user_prompt_olive_leaf_extract_real_case_does_not_self_contradict`
       (usa el `store` real, mismo patrón que los demás tests de casos
       reales conocidos de este proyecto -- no un mock).
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
   `--save-jsonl` para eso).
   **Embeddings/Chroma -- COMPLETADO (sesión 18-ago-2026): corpus
   completo indexado y verificado en `data/chroma/`.**
   `ingestion/chroma_index.py` convierte filas de `chunks.jsonl` a
   entradas de Chroma (`to_chroma_metadata`, `chroma_id`,
   `compute_is_group_dossier`) -- esquema SIN `e_number`, ver el
   bullet de "Hallazgos verificados" "ESQUEMA FINAL, IMPLEMENTADO"
   para el porqué. `scripts/build_chroma_index.py` tiene 3 modos:
   `--test-batch` (300 chunks, colección efímera en memoria, para
   validar el diseño sin comprometerse al corpus completo),
   `--all` (indexa los 67.827 en la colección PERSISTENTE, borrando
   cualquier colección previa del mismo nombre antes -- no es
   incremental), `--verify` (conecta a la colección persistente ya
   creada y corre las consultas de verificación, sin reindexar --
   útil para comprobar el índice en cualquier momento posterior).
   **Corpus completo indexado de verdad, no solo proyectado:** 67.827
   chunks, 2,97 min reales, `collection.count() == 67827` verificado,
   597 MB en disco (`data/chroma/chroma.sqlite3`, colección
   `efsa_reevaluation_chunks`). 3 consultas de verificación con temas
   distintos (genotoxicidad, un caso específico conocido -- por qué se
   retiró TiO2 como aditivo, generaliza a incertidumbre de exposición
   dietética) -- las 3 con resultados temáticamente correctos, ver el
   detalle completo en el bullet de modelo de embeddings en
   "Decisiones de arquitectura ya tomadas" (incluida la advertencia
   GPU-vs-CPU para el tiempo de reconstrucción en despliegue).
   **RECONSTRUIDO con otro backend (sesión 18-ago-2026, misma fecha,
   más tarde) -- las cifras del párrafo anterior (597 MB, 2,97 min,
   GPU) quedan SUPERADAS, no las repitas como vigentes.** Nuevo módulo
   `ingestion/embedding_model.py::load_embedding_model()` -- backend
   ONNX + pesos int8, único punto de la base de código que instancia
   `SentenceTransformer` (ver el bullet "Backend de embeddings: ONNX
   int8, no torch" en "Decisiones de arquitectura ya tomadas" para el
   razonamiento completo, y `PROGRESS.md` continuación 19 para el
   detalle). Índice reconstruido de verdad: 67.827/67.827 chunks,
   ~22,4 min (CPU, sin GPU), 718 MB en disco. Verificado con las
   mismas 3 consultas de verificación (mismo patrón de calidad) y con
   una consulta real de extremo a extremo sobre aspartamo vía
   `answer_question` (ADI=40, DOI correcto, 5 chunks tier 1) -- para
   confirmar que indexado y retrieval usan ahora el MISMO backend, sin
   el desajuste fp32/int8 que existía antes de este cambio.
   **Nodo 2 (`hybrid_retrieval_node`) CONECTADO A CHROMA (sesión
   18-ago-2026, continuación 5)** -- ver `graph/nodes.py` en la lista
   de arriba para el detalle de diseño e implementación. Este punto
   (pendiente #5 de esta lista) queda completo de extremo a extremo:
   chunking -> embeddings -> índice Chroma -> Nodo 2 consultándolo.
6. **Detección de ambigüedad en el Nodo 3 -- DIFERIDO explícitamente
   (sesión 18-ago-2026), con evidencia de prevalencia, no implementado
   todavía y sin fecha de retomarlo salvo que cambie la evidencia.**
   Contexto completo: antes de la primera ejecución real del grafo
   ensamblado (`graph/build.py`), se auditó qué pasa hoy si
   `verify_currency_node` encuentra un caso ambiguo (varias
   `'EFSA opinion'` con fechas próximas, título no concluyente) --
   respuesta: **ni excepción ni manejo real, se elige `MAX(fecha)` en
   silencio, sin ninguna señal hacia el llamador** (`vigencia_ambigua`
   NO cubre este caso pese al nombre -- ver el comentario en
   `GraphState`/`verify_currency_node`, corregido en esta misma sesión
   para que no parezca protección real). Antes de decidir si
   implementarlo ahora o después, se pidió un diagnóstico de
   prevalencia sobre el corpus real completo.
   - **Metodología:** replicado el filtrado EXACTO de candidatos de
     `current_reference_value_opinion` (mismos pasos: `VALID_OPINION_TYPES`,
     rescate de dominio mal-etiquetado, exclusión de pienso animal),
     pero sin el pick final de `MAX(fecha)` -- en su lugar, para cada
     sustancia con 2+ candidatos supervivientes, se mide la distancia
     en días entre el candidato ganador (el que `MAX(fecha)` elegiría)
     y el más cercano de los demás. **Umbral de "ambiguo": 90 días**
     (probado también a 30 días, mismo resultado en ambos) -- elegido
     porque los dictámenes EFSA son eventos de adopción puntuales y
     fechados; una separación de 3+ meses es muy improbable que sea un
     artefacto del mismo evento (corrigendum, enmienda) y mucho más
     probable que sea un paso regulatorio genuinamente distinto.
     Metodología verificada contra el caso conocido de aspartamo antes
     de confiar en ella: reproduce exactamente los 4 candidatos
     esperados (2006, 2009×2, 2013 -- excluye correctamente el
     statement de 2011).
   - **Universo escaneado: 247 sustancias con enlace estructural
     resoluble en el corpus de reevaluación -- prácticamente todo el
     espacio de preguntas que el Nodo 3 puede responder hoy con el
     corpus actual, no una muestra.**
     - **Tier 1 (94 sustancias, con ADI resuelto):** 74 con un único
       candidato superviviente (ambigüedad estructuralmente imposible),
       0 sin ningún candidato, 20 con 2+ candidatos. **0 de esas 20
       caen dentro de 90 días** (ni de 30). El gap más pequeño de las
       94: **106 días** (Propane-1,2-diol, 2 candidatos) -- el segundo
       más pequeño, 182 días (Steviol glycosides, 7 candidatos). El
       resto, 280+ días, la mayoría 900+ días (2,5+ años -- ej. las 6
       sales de glutamato, todas a 924 días).
     - **Tier 2/3 (153 sustancias adicionales, sin ADI numérico --
       `require_adi=False` menos las 94 de tier 1, más Shellac vía
       tier 3):** 125 con un único candidato o una sola fecha
       parseable, 3 sin ningún candidato tras los filtros (caso ya
       manejado -- `current_reference_value_opinion` devuelve `None`,
       Node 4 ya lo comunica explícitamente, no es el caso de
       ambigüedad), 25 con 2+ candidatos. **0 de esas 25 caen dentro
       de 90 días** (ni de 30). El gap más pequeño: **160 días**
       (Beetroot Red/betanin, 2 candidatos) -- el resto, 246+ días.
     - **Total combinado: 0/247 sustancias ambiguas a 90 días, 0/247 a
       30 días.** El gap real más pequeño de TODO el corpus es 106
       días -- ningún caso cerca del umbral que hiciera dudar de la
       elección de 90 días sobre, digamos, 60 o 120.
   - **CAVEAT EXPLÍCITO, no ocultar: esto es una foto del corpus tal
     como está hoy (162 dictámenes, export de OpenFoodTox usado en
     este proyecto), no una garantía permanente.** El programa de
     reevaluación sigue activo (ver "Hallazgos verificados" más
     arriba, sección de cobertura del corpus -- follow-ups de plata
     E174, Patent Blue V E131, almidones modificados, entre otros
     conocidos en curso). Un futuro follow-up publicado cerca en el
     tiempo de un dictamen ya existente para la misma sustancia SÍ
     podría producir el caso ambiguo que hoy no existe -- este
     diagnóstico no lo descarta para siempre, solo confirma que no ha
     pasado todavía con los datos disponibles.
   - **Por qué se difiere, no por qué no importa:** impacto
     verificado = cero incidentes reales hasta hoy, frente a trabajo
     con impacto YA conocido y pendiente en esta misma lista (Nodo 4
     sin re-probar contra la API con el prompt actual -- pendiente #9;
     servidor MCP sin empezar -- pendiente #7; deploy -- pendiente #8).
     Implementar detección de ambigüedad ahora sería trabajo especulativo
     sobre un caso con prevalencia empírica de 0/247 en vez de sobre
     huecos con impacto ya confirmado. Si el corpus cambia
     (nuevos follow-ups) o aparece un caso real, re-ejecutar este mismo
     diagnóstico (no hay script permanente guardado -- fue una
     investigación puntual, replicable con el mismo método descrito
     arriba) antes de decidir si sigue siendo seguro diferirlo.
7. ~~Servidor MCP (`mcp/`, carpeta vacía todavía).~~ **HECHO (sesión
   18-ago-2026)** -- ver "Implementado" arriba (`mcp/server.py` +
   `tests/test_mcp_server.py`, 6 tests con stubs, 30/30 en verde). Sigue
   sin probarse con un cliente MCP real (Claude Desktop u otro) -- solo
   `server.list_tools()`/`server.call_tool()` invocados directamente en
   Python, tanto en la sesión de implementación como en los tests.
8. Deploy siguiendo la Opción A descrita arriba, en **Streamlit
   Community Cloud -- este ha sido el plan activo en TODO momento, no
   ha cambiado nunca.** **CORRECCIÓN (sesión 18-ago-2026, continuación
   21):** una versión anterior de esta entrada afirmó que el plan
   "cambió"/"pivotó" a HF Spaces -- eso era incorrecto, un error de
   redacción de Claude que el usuario corrigió directamente. HF Spaces
   solo se INVESTIGÓ como alternativa posible (motivado por el bloqueo
   de memoria medido en continuación 18), nunca se adoptó. Ver
   PROGRESS.md, continuaciones 19-21, para el detalle completo
   (incluida la corrección explícita in situ en la propia continuación
   19). **EN CURSO, NO CERRADO -- memoria parcialmente optimizada,
   repo preparado para un primer intento de deploy real, ese intento
   todavía no se ha hecho:**
   - Backend de embeddings cambiado a ONNX int8 (ver el bullet
     correspondiente en "Decisiones de arquitectura ya tomadas") --
     reduce el consumo medido de 1.870 MB a ~1.214 MB (combinado con
     `torch` CPU-only).
   - **`usecols` añadido a las 5 hojas de `OpenFoodToxStore` (sesión
     18-ago-2026, continuación 20) -- palanca de memoria adicional,
     medida sobre el pipeline completo, no solo sobre la carga del
     xlsx aislada.** Reduce el consumo medido de ~1.214 MB a
     **~1.150-1.170 MB** (2 corridas, mismo método de medición que las
     cifras anteriores) -- ahorro real de ~44-64 MB. **SIGUE ~126-145
     MB (12-14%) por encima del límite de ~1 GB de Streamlit Community
     Cloud** -- riesgo real y sin cerrar de cara al primer deploy.
     Investigada una palanca adicional (reescribir el pipeline de
     embeddings sobre ONNX Runtime directo, sin la capa de
     `sentence-transformers`) -- **el usuario decidió explícitamente NO
     implementarla todavía**, prefiriendo intentar el deploy real
     primero y observar el comportamiento empírico. Detalle completo
     de la auditoría de columnas (verificada contra cada caller real,
     no adivinada) y de la medición en `PROGRESS.md`, continuación 20.
   - **`requirements.txt` fija `torch==2.13.0+cpu` explícitamente**
     (vía `--extra-index-url https://download.pytorch.org/whl/cpu`,
     sesión 18-ago-2026, continuación 20) -- para que un `pip install
     -r requirements.txt` limpio en el host de deploy instale la
     versión ligera por defecto, sin depender de que alguien lo
     recuerde a mano. **El venv de desarrollo local SIGUE con el build
     CUDA** (`2.13.0+cu130`, instalado a mano, útil para reindexados
     rápidos) -- este pin de `requirements.txt` no lo cambia
     automáticamente; solo un entorno nuevo instalado desde cero (como
     el deploy) se lleva el build CPU-only. Con esto, el punto
     pendiente de "cómo gestionar la diferencia dev(GPU)/prod(CPU)" de
     la entrada anterior queda resuelto: `requirements.txt` es la
     única fuente, prod la sigue al pie de la letra, dev se desvía a
     propósito y a mano.
   - **Repo preparado para el primer intento de deploy real (sesión
     18-ago-2026, continuación 21) -- ver la nueva decisión de
     arquitectura "Datos pesados del deploy vía MEGA S4, nunca en git"
     más abajo, y `README.md` sección "Deploy en Streamlit Community
     Cloud" para los pasos exactos.** `src/efsa_rag/deploy_assets.py`
     (descarga xlsx + índice de Chroma desde MEGA S4 en el arranque,
     solo si no están ya en disco) +
     `scripts/upload_deploy_assets.py` (sube ambos, manual, un uso, con
     las credenciales del usuario) + `ui/app.py` conectado a esa
     descarga antes de tocar `graph.build`. La subida real a MEGA S4 y
     el primer deploy en share.streamlit.io quedan pendientes de que
     el usuario los haga desde su propia cuenta -- fuera del alcance de
     lo que Claude puede ejecutar (credenciales/cuenta del usuario).
     **El riesgo de memoria de arriba (~126-145 MB sobre el límite)
     sigue sin resolver** -- el primer deploy real puede fallar por OOM
     en la primera consulta; eso es un resultado esperado a día de
     hoy, no una sorpresa si ocurre.
9. **Re-probar el Nodo 4 con llamada real a la API usando el prompt
   actual -- PARCIALMENTE HECHO (sesión 18-ago-2026, continuación 10),
   no cerrar del todo.** `answer_question(...)` de extremo a extremo
   con aspartamo SÍ ejercitó `retrieved_chunks` NO vacío (5 fragmentos
   reales) y el campo `discussion_text` (con
   `discussion_is_boilerplate=True` para este caso concreto,
   correctamente omitido del texto citado). **NO ejercitó** el mensaje
   de "motivos opuestos" para ADI sin valor (aspartamo SÍ tiene ADI,
   camino tier 1 -- haría falta una consulta sobre una sustancia tier 2,
   ej. TiO2, para probar esa rama) ni el aviso de tier 3 en
   `_format_retrieved_chunks` (los 5 fragmentos de aspartamo son todos
   tier 1 -- haría falta una consulta sobre Shellac o el statement de
   sucralosa para ejercitar esa rama). Sigue sin existir ningún test
   automatizado de `generate_answer_node`/`answer_question` en
   `tests/test_nodes.py` (mismo patrón que los Nodos 1 y 2) -- solo
   verificación manual puntual hasta ahora, en las dos sesiones donde
   se ha probado (16-ago-2026 y 18-ago-2026).

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
