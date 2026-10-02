# Changelog

## Unreleased — MathLab: motor trigonométrico exacto (T-02 a T-14, T-20, T-21, T-24)
- **Punto de partida: la suite estaba en rojo.** El motor entregado en `20e031f` dejaba `tests/test_mathlab_trig.py` con 4 fallos por tres causas distintas: `sec`, `csc` y `cot` no eran evaluables numéricamente; la paridad solo se aplicaba a `Neg(Call)` y por tanto `sin(-x)` no se reducía nunca; y tres expectativas comparaban contra `pretty()` —la forma española Unicode para pantalla (§5.1)— lo que el motor produce en `text()`, que es la forma canónica ASCII.
- **Motor.** `mathlab/trig.py` reescrito como motor de reglas por objetivo (T-20, §5.5b): cada transformación pertenece a un objetivo y solo acepta reescrituras estrictamente más baratas o estrictamente más caras, medidas por `(nodos, longitud del texto canónico)`. Esa medida es un orden bien fundado, así que cada objetivo termina y su resultado es punto fijo por construcción. Mezclar las dos direcciones en un mismo bucle no puede terminar: `sin(2x)` se desarrolla a `2·sin(x)·cos(x)` y vuelve a colapsarse.
- **Ocho objetivos**: `simplificar` (reducir), `expandir` (T-04, T-05), `producto_a_suma` (T-08), `suma_a_producto` (T-09), `potencias` (T-10), `sustitucion_universal` (T-07), `hiperbolicas` (T-14) y `exponencial` (T-14). Cada familia lleva escrito su «por qué este método», y `simplify_ex` devuelve las que han actuado para que la calculadora las escriba en la traza (§5.2, T-22).
- **Cobertura**: T-02 completo (las seis formas de cada relación), T-03 completo (paridad, periodicidad, opuestos, suplementarios y complementarios en una tabla por cuadrante en lugar de una regla por signo), T-04 y T-05 en ambos sentidos, con las tres formas de `cos(2x)` **ofrecidas** y no elegidas, T-08, T-09, T-10, y la parte de T-21 que el motor necesita (0°–180° con las seis funciones exactas y `None` donde la función no existe).
- **Inventario honesto.** `identities()` se deriva ahora de los registros de reglas. Antes anunciaba `angulo_doble_coseno`, `angulo_doble_tangente` y `medio_angulo` sin que existiera regla para ninguna de las tres; hay una prueba que falla si eso vuelve a pasar.
- **`sec`, `csc` y `cot` evaluables.** El motor los produce y la verificación no podía evaluarlos: una comprobación que no puede evaluar lo que el motor emite no comprueba nada. Ahora son `1/cos`, `1/sin`, `1/tan`. El polo el camino numérico **no lo ve** (a `pi/2`, `cos` vale 6·10⁻¹⁷ y no cero): la negativa la da la tabla simbólica y el numérico solo puede dar la magnitud.
- **Límite de profundidad.** `RecursionError` a 500 niveles escapaba del motor; ahora `MAX_REWRITE_DEPTH = 200` y se declara `EXPRESSION_LIMIT` en castellano. Nada que se pueda escribir llega ahí: el parser limita el anidamiento a `MAX_DEPTH = 64`.
- **Pruebas**: en `test_mathlab_trig.py`, en tres capas — doradas por familia, **sonoridad** (cada identidad recomprobada por camino numérico independiente con puntos sembrados, 50 casos paramétricos) y **propiedades del motor** (idempotencia, que `simplify` nunca agranda, que el inventario no promete familias sin regla). Hay un **control negativo** (`cos(x)` frente a `sin(x)` tiene que ser rechazado) porque si no la comprobación pasaría igual sin comparar nada, y un fuzz de 60 semillas que cubre los cinco objetivos.
- **Hallazgo honesto sobre la verificación**: `tan(((x³)⁴)² + x)` y `sin(x) + sin(cot(y))` son identidades verdaderas, pero con `x^24` o `cot(y)≈10⁴` dentro las dos caras difieren entre 10⁻⁵ y 10⁻², porque `sin` de un argumento enorme ya no tiene dígitos fiables. Es condicionamiento de punto flotante, no un error de las reglas; queda documentado y acotado en las pruebas en vez de esconderse.
- **T-11 (inversas y ramas).** `mathlab/ramas.py` distingue las dos direcciones, que no son simétricas: `sen(arcsen(u)) = u` vale donde está definida y el motor la reduce; `arcsen(sen x) = x` **no**, y el motor se niega a reescribirla. `ramas.ramas()` da cada rama con su intervalo de validez y `ramas.evidencia_global()` un contraejemplo calculado —en `2·pi`, `arcsen(sen(2·pi))` vale 0 y no `2·pi`—. Los dominios se marcan como abierto o cerrado según el caso: `[-1,1]` para `arcsen` y `arccos`, `(-1,1)` para `arctanh` porque en los extremos no existe.
- **T-12 (ecuaciones).** `mathlab/ecuaciones.py` resuelve `sen/cos/tan = c`, `a·sen+b·cos = c` por desplazamiento de fase, y polinomios en `sen`, `cos` o `tan` con raíces exactas. Cada familia se comprueba **sustituyendo miembros en la ecuación original**, que es lo único que caza una solución espuria. Un valor irracional como `√2/2` da una solución exacta —y además notable: `arcsen(√2/2)` sale como `pi/4`, no como un `arcsen` sin evaluar—. Cuando ningún caso encaja la respuesta es «no lo resuelve todavía», **nunca** «no hay soluciones».
- **T-13 (inecuaciones).** `mathlab/inequaciones.py` convierte `f(x) > 0` en una carta de signos sobre **un** periodo, y la carta solo vale si sus puntos críticos están todos. Dos requisitos que no son opcionales: los **polos** —`tg(x) < 1` son dos intervalos, y solo el polo de `pi/2` parte el primero en dos; los polos de `tg` y `cotg` no tienen denominador en la expresión, así que se sacan de los ceros de `cos` y `sen`— y el **origen del periodo**, que se lee en la función en lugar de asumirlo abierto, porque dejarlo abierto pierde una solución real (`cos(x)² > 1/2` se cumple en 0). El signo dentro de cada hueco se decide numéricamente, lo cual es una prueba y no una aproximación: una función continua sin ceros ni polos en un hueco no puede cambiar de signo en él. Si alguna vez cambiara, el motor se niega en vez de elegir un lado. `=` da los ceros como puntos y no como intervalos, porque una ecuación no tiene interior.
- **Dos bugs que cazó la verificación de T-13 y que son de la misma familia.** `f^n = 0` está exactamente donde `f = 0` para todo entero positivo, y el código trataba la potencia par como un caso aparte: `sen(x)²` se quedaba **sin ceros**, que es decir respondía «no hay soluciones» sobre una expresión llena de ellas. Y `dominio.periodo` daba `2·pi` para `sen(x)²`, cuyo periodo real es `pi`: no es un error en el conjunto —los puntos son los mismos— pero duplica cada intervalo y tapa la simetría que lo explica. Ahora `dominio.periodo_minimo` reduce mientras siga cumpliéndose.
- **T-14 (hiperbólica).** Identidades, suma y diferencia, ángulos dobles, inversas y la conexión exponencial. Fuera: derivadas e integrales, que son de T-17 y T-18.
- **La verificación de T-13 mira en las dos direcciones**: cada punto muestreado tiene que estar dentro exactamente cuando la desigualdad se cumple, y fuera exactamente cuando falla. Un conjunto que fuese solo un subconjunto de la verdad pasaría una dirección y fallaría la otra, y por eso es una comprobación y no una prueba de humo. Los puntos son racionales exactos, no flotantes, así que los que caen en un extremo prueban las banderas abierto/cerrado en lugar de esquivarlas.
- **T-20, T-21 y T-24 cerrados.** Tres cosas que faltaban y que no eran adornos. **La estrategia de resolución**: `N/D = 0` tiene los ceros de `N`, nunca los de `D`, porque donde el denominador se anula hay un polo y un polo no es solución de nada. Con ese paso, `sec(x) = 1`, `cosec(x) = 1` y `cotg(x) = 1` se resuelven, que antes se rechazaban. **El fallback numérico con error declarado**: `verify.aproximacion()` mide la sensibilidad de la expresión perturbando la entrada y declara el error a partir de ahí. `sen(x)` en `x = 1` sale con error 4·45·10⁻¹⁵; en `x = 10⁶` sale con **2·08·10⁻⁴**, porque la entrada y la salida son exactas y las dos se calculan en dobles. **La integración en la calculadora**: `resolver`, `resolver_inequidad`, `ramas` y `aproximar` tienen operación propia y cada resultado lleva un sello trazado por un camino que no consulta el cálculo que produjo la respuesta.
- **Agujero encontrado al sellar T-24: la comprobación de espurias no se ejecutaba nunca.** Hacía `if not mx.variables(miembro): continue`, y el miembro de una familia resuelta es justamente una constante, así que el `continue` se saltaba el caso que hay que mirar. La función devolvía una lista vacía para **toda** familia, incluidas las que no satisfacen la ecuación — y esa lista es la única evidencia de que T-12 no arrastra soluciones espurias. Una comprobación que no puede fallar no es una comprobación. Ahora una familia con el paso equivocado se marca como espuria con su residuo.
- **Dos bugs en `poly.to_expr`, escritos y cazados en la misma tanda.** El primero: el bucle de factores **asignaba** en vez de multiplicar, así que se quedaba con el último factor — `2·sen(x)·cos(x)` se reconstruía como `2·sen(x)`. El segundo: un coeficiente negativo escondido dentro de un producto es invisible para quien lee términos por signo, así que `cos(x) - sen(x)` volvió como `1·cos(x) + (-1)·sen(x)` y el caso con fase no lo reconocía. Los dos los cazó el test de ida y vuelta, que es exactamente para lo que está.
- **Pruebas**: 1006 sobre estas familias — 395 en `test_mathlab_trig.py`, 191 en `test_mathlab_ml1.py`, 135 en `test_mathlab_ml0.py`, 104 en `test_mathlab_inequaciones.py`, 99 en `test_mathlab_ecuaciones.py`, 40 en `test_mathlab_ramas.py`, 30 en `test_mathlab_t24.py` y 12 en `test_mathlab_arch.py`—. Los 30 de T-24 no se limitan a que el sello ponga «verificado»: comprueban que la comprobación **puede fallar**, porque un verificador que solo sabe decir «verificado» dejaría este fichero en verde pase lo que pase.
## Unreleased — UX 2026 redesign (CERTIFICADO CON LIMITACIONES)
- Rediseño de la interfaz en 13 prompts (15 commits sobre `d5650c5`). Solo `ui/` cambia de forma sustancial; `domain/`, `engines/` e `infrastructure/` sin diff. Tres cambios declarados en `application/`: cableado F9–F12 en la fachada, `practice.py` nuevo (orquesta, no calcula) y un arreglo de 2 líneas en `mastery.py` para respuestas `needs_review` (F10 lanzaba `DomainError` contra su propio comentario).
- Producto: carril de navegación + barra superior + secciones sobre rutas `area/seccion` (14 páginas ocultas en un `QTabWidget`); Home editorial con datos reales; espacios de trabajo de Ingeniería y laboratorio sobre un kit común (`Panel`, `Metric`, `KeyValueList`); página **Practice** (sesiones, plan, dominio, tutor con el modelo apagado por defecto); páginas de Learn, Documents, Library y Settings reconstruidas.
- Diálogos y errores: un único `DialogFrame`/`show_message`; sin `QMessageBox` fuera de `ui/dialogs.py`; sin texto crudo de excepción (D2).
- Movimiento (100–180 ms, un disparo, respeta "reducir animaciones") y estados (`RUNNING` bloquea el doble lanzamiento).
- Windows: ventana que cede ante pantallas pequeñas, carril que se pliega bajo 1100 px, instancia única, icono como recurso, `AppUserModelID`, F11. DPI medido con el factor de escala de Qt (100/125/150/200 %).
- Auditoría visual final: 19 hallazgos, corregidos salvo el idioma de la interfaz (decisión de producto) — `docs/ux/UX-REVIEW-2026-FINAL.md`.
- Tests: suite completa 4962 recogidos + 8 del recorrido de certificación; 136 tests nuevos de UX. Sin fallos de código; 5 fallos ambientales por `pypdf` ausente (resueltos instalando el lock) y 2 omitidos por `reportlab`. Gate: `docs/gates/GATE-UX-2026-CERTIFICATION.md`.
- NOT VERIFIED: instalador/EXE ejecutados, monitor físico a 125/150/200 %, lector de pantalla.
- Sin cambios de comportamiento en F0–F16; `main` como única rama.

## Unreleased — Windows Product 1.0 (productización)
- Producto/UX post-roadmap (sin fase nueva): menú Go agrupado sobre los 13 tabs intactos; índice de módulos reales; Virtual Lab/Simulation en secciones Experiment/Inputs/Execution/Results sin renombrar widgets; vista orbital F16 con números reales; dashboard editorial con recents reales; motion 150 ms sin bounce.
- Validación: exe/installer reconstruidos del árbol final, smoke verde, regresión verde; Start Menu/uninstall-ejecutado/clean-machine/DPI sistemático NOT VERIFIED (sin admin ni 2ª máquina).
- `AcademicCore.exe` (PyInstaller onedir) + `AcademicCore-1.0.0-Setup.exe` (NSIS 3, Start Menu, desinstalación registrada). Versión única `1.0.0` (`__init__` → pyproject → version_info → installer, pineado por tests).
- Runtime: `%LOCALAPPDATA%/AcademicCore` solo en bundle (`runtime.py`); dev intacto en `~/.academic-core`. Icono propio generado por render Qt (sin assets de terceros).
- UX: splash con versión, first-run de una pantalla (sin cuentas ni red), búsqueda global Ctrl+K sobre `UnifiedSearchService` (sin segundo motor), Settings con Appearance/Data/About reales, icono de ventana.
- CI: job `release` (build exe + installer + smoke offscreen con DB verificada + artifact). Sin updater automático (limitación documentada en `packaging/windows/README.md`).
- Núcleo académico intacto (F9–F13, F15, F16 sin cambios de comportamiento).

## Unreleased — Fase F16: Contenido Aeroespacial (CERTIFICADA)
- Motor `domain/engineering/orbital/` (`f16-orbital/1`): two-body Decimal SI (m, kg, s, rad) con contexto de 50 dígitos; circular/periodo+inversa, vis-viva+inversa, energías (total vs específica), escape, elipses (0 ≤ e < 1), Kepler (M↔E Newton acotado, ν↔E cerradas), elementos clásicos con marcos `ECI/ORBITAL` y digest `f16-elements/1`. Constantes con provenance (G CODATA 2018, Tierra IAU/IERS). Sin persistencia, sin dependencias, sin códigos AC nuevos.
- Reutilización: `math/` (sqrt/pi/trig), `units.py` extendido aditivamente (MASS/FORCE, g/N/rad + alias; min/h/day/deg como helpers explícitos), traza E0 (`domain/execution/orbital.py` `physics.orbital` + replay + wiring `ExplainService`, aditivo). F8-P5/F9/D7 intactos.
- Nuevos: `test_f16_orbital.py` (16 contractuales: ISS/GEO/escape, round-trips, dominio, hash-seeds, traza+replay, AST). TDD: RED verificado antes de GREEN.
- Docs: `F16-AEROSPACE.md` + `GATE-F16-CERTIFICATION.md` (veredicto: CERTIFICADA con CI real; ROADMAP COMPLETADO). Evidencia local: 16/16 F16 + regresión verde salvo 1 preexistente CRLF (documentado, ajeno a F16).
- Commit impl. `195d3e7`. Run de certificación [`36394085024`](https://github.com/Damaga2005/AcademicCore/actions/runs/36394085024) verde 4/4 celdas + package. Roadmap: **F16 CERTIFICADA, ROADMAP COMPLETADO**.

## Unreleased — Fase F13: OneDrive / Cloud Sync (CERTIFICADA)
- Coordinación `application/cloud_sync.py` (`CloudSyncService`) sobre el motor F13-ext intacto (`domain/sync.py` sin cambios): primer push, join bidireccional LWW, VERIFY reutilizado, estados `synced/pending/offline/conflict/error` en tabla aditiva (fuera de digests). Nunca: error cloud → rollback local; nada marcado synced sin escritura confirmada.
- Transportes `infrastructure/cloud_transport.py` (sin red ni dependencias nuevas, solo pathlib+json): `MemoryCloudTransport` (fake/in-memory para contrato) + `OneDriveFolderTransport` (carpeta local, escritura atómica tmp+replace, `expected_remote_digest` → `AC-SYN-004`). Validación y límites reutilizados F13-ext (`AC-SYN-001`); errores nuevos `AC-SYN-002/003/004`.
- Persistencia: migración 021 aditiva (`sync_status` + `cloud_sync_meta`) + métodos `set/get_status`, `all_statuses`, `set/get_meta`; wiring `cloud_sync` en facade (carpeta OneDrive si `providers.onedrive_folder`, si no Memory). Tocado certificado: solo pins `20→21` (la 021 los exige) + extensión aditiva de `test_d5_contracts` a F13.
- Nuevos: `test_f13_cloud_sync.py` (9 contractuales: primer push, offline-first+reintento, bidireccional, conflicto determinista+log, corrupto intacto, tombstone, sin secretos, carpeta round-trip, auth/límites). TDD: RED 9/9 verificado antes de GREEN.
- Docs: `F13-CLOUD-SYNC.md` + `GATE-F13-CERTIFICATION.md` (veredicto: CERTIFICADA con CI real; F13 CERTIFICADA, F16 SIGUIENTE). Evidencia local: 9/9 F13 + regresión 176 passed / 1 skip ambiental. Sin E2E real contra OneDrive/Graph (sin credenciales; no se finge).
- Commit impl. `f34a9d5`. Run de certificación [`36385930302`](https://github.com/Damaga2005/AcademicCore/actions/runs/36385930302) verde 4/4 celdas + package. Roadmap: **F13 CERTIFICADA, F16 SIGUIENTE**.

## Unreleased — Fase F12: Tutor Socrático (CERTIFICADA)
- Contratos `domain/tutor.py` (puro): `f12-tutor-response/1` (schema cerrado, 6 `response_type`), `Claim`/`TutorProposal`/`VerifiedResponse`, `SOCRATIC_LADDER` (6 etapas derivadas del nº de turnos previos, sin store de política aparte), `verify_claims` — delega en `domain.correction.correct_answer` (F9): ningún segundo motor matemático/simbólico/de unidades/circuitos.
- `infrastructure/llm.py`: `LLMProvider` (protocolo agnóstico de proveedor), `NullProvider` (LLM=OFF determinista), `OllamaProvider` (adapta el `OllamaBackend` existente; cero dependencia nueva, cero reintentos automáticos). `application/tutor.py`: `TutorService` orquesta sin recalcular F9/F10/F11.
- Autoridad estricta: LLM propone JSON → validador de schema/política → `correct_answer` decide → `verified`/`unverified`/`rejected`. El LLM no tiene acceso a herramientas/filesystem/red/BD; solo emite texto.
- Migración 020 aditiva (`tutor_turns`, append-only, solo respuesta verificada — sin texto crudo del LLM) + `TutorRepository`. Errores nuevos `AC-TUT-001..006`. Cambio aditivo mínimo en `engines/ai.py` (`OllamaBackend.generate(timeout=)`, default idéntico, sin ruptura).
- Nuevos: `test_f12_tutor.py` (35 contractuales: schema, claims/solver routing, autoridad, política socrática, LLM=OFF/timeout/provider-error, persistencia/provenance, seguridad).
- Docs: `F12-SOCRATIC-TUTOR.md` + `GATE-F12-CERTIFICATION.md` (criterios §28: todo verde incluyendo CI real). Tocado certificado: solo pins `19→20` (la 020 los exige).
- Evidencia local: 35/35 F12 + regresión curada 306 passed / 1 skip ambiental (mismo skip que F11). Suite completa sin filtrar: 13 fallos, 12 preexistentes verificados en `main` limpio (CRLF/LF en fixtures doradas de F8/E0, ajenos a F12; confirmado además por las celdas Windows del CI real, que no los reproducen) + 1 pin de migración ya corregido.
- Commit `35763bc8b09c9f212c1b7389e0ceb8472cb62fe4`. Run de certificación [`36336990034`](https://github.com/Damaga2005/AcademicCore/actions/runs/36336990034) verde 4/4 celdas + package, a la primera. Roadmap: **F12 CERTIFICADA, F13 SIGUIENTE**.

## Unreleased — Fase F11: Aprendizaje Adaptativo (CERTIFICADA)
- Motor `domain/adaptive.py` (`f11-adaptive/1`): `AdaptiveConfig` versionada (pesos 60/20/15/5, umbrales 0.40/0.70, max_per_concept 2, exclude_done), `AdaptiveContext`, `Candidate`/`ScoredCandidate`/`AdaptivePlan` (rationale cerrado + `NO_ELIGIBLE_EXERCISES`/`PREREQUISITE_UNMET`), `target_difficulty`/`difficulty_fit`, `score_candidate`, `rank_candidates` (score DESC, question_id ASC, version ASC), `build_route` (cap por concepto), `plan_digest` (`f11-adaptive-plan/1`).
- Servicio `application/adaptive.py`: `build_plan` (eligible→filter→score→rank→route→persist), elegibilidad contractual (subject/tipo/difficulty/concept/prerequisites subject-level/historial F10), persistencia idempotente (plan_id = plan_digest). LLM=OFF: sin imports de IA.
- Migración 019 aditiva (`adaptive_plans`) + consultas `QBankRepository.questions_of_subject` (json_each) y `MasteryRepository.save_plan/get_plan/plans_of`. Cero comportamiento certificado cambiado.
- Nuevos: `test_f11_adaptive.py` (22 contractuales: elegibilidad, prioridad mastery, ranking/tie-break, historial, route, reproducibilidad, idempotencia, prerequisitos, edge cases, LLM=OFF, seguridad AST).
- Docs: `F11-ADAPTIVE.md` + `GATE-F11-CERTIFICATION.md` (criterios §31: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: solo métodos nuevos + pins `18→19` (la 019 los exige).
- Evidencia local: 22/22 F11 + regresión 217 passed / 1 skip ambiental + 36 passed × 3 hash-seeds. Run `36260971728` (`28c6863`) verde 4/4 + package a la primera. Roadmap: F11 CERTIFICADA, F12 SIGUIENTE.

## Unreleased — Fase F10: Mastery y Modelado del Estudiante (CERTIFICADA)
- Modelo `domain/mastery.py` (`f10-beta/1`): Beta-Binomial conjugado Decimal (sin floats/NaN), `P=m/(m+n)`, varianza Beta, prior Beta(1,1) configurable, `split_weight` exacto multi-concepto, `fold_observations`/`fold_deltas`/`pool_states`, digests `f10-observation/1` + `f10-state/1`.
- Servicio `application/mastery.py`: `apply_evidence` (validate→plan→1 tx; `no_update` para omitidas/sin-concepto; `AC-ACD-002` concepto desconocido; `AC-ACD-003` tamper), queries concept/topic/subject (jerarquía D7 real vía `topic_ref` del ítem), `rebuild` (fold en orden fijo; incremental == rebuild).
- Migración 018 aditiva (`mastery_states` + `mastery_observations` PK-idempotente) + `MasteryRepository` con `cx`. Extensión aditiva F9: `ItemEvidence.topic_ref` + `build_evidence(assessment=)`. Motor F9 intacto.
- Nuevos: `test_f10_mastery.py` (14 contractuales: modelo, evidencia, split, unknown-concept, idempotencia (doble apply + doble-insert concurrente), rebuild, determinismo cross-fixture, jerarquía, rollback, round-trip + NaN, seguridad AST + no-re-corrección).
- Docs: `F10-MASTERY.md` + `GATE-F10-CERTIFICATION.md` (criterios §33: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: solo DTO aditivo + pins `17→18` (la 018 los exige).
- Evidencia local: 14/14 F10 + regresión 281 passed / 1 skip ambiental + 28 passed × 3 hash-seeds. Run `36254755243` (`9e6d66c`): intento 1 con 1 flake `test_perf_academic_scale` (21.0s/20s, win-3.12, clase §8); intento 2 tras `rerun --failed` verde 4/4 + package. Roadmap: F10 CERTIFICADA, F11 SIGUIENTE.

## Unreleased — Fase F9: Assessment y Evaluación Formal (CERTIFICADA)
- Motor `domain/correction.py` (`f9-correct/1`): mcq/tf exactos, numeric `Decimal`+unidades+tolerancia/precisión (cifras significativas), symbolic con prueba `equivalent` o acuerdo exacto etiquetado, short/structured/circuit honestos (`needs_review` donde D6 no da criterio), malformados → `AC-DOM-001`, razones cerradas, nada ejecutado.
- Servicio `application/correction.py`: cupo `attempts_allowed` (cancel no consume), `prepare` (snapshots congelados idempotentes), `submit_with_correction` (submit→correct→result+evidence en 1 tx), `build_evidence` (DTO F10 con `verified`, resiliente a tamper). Errores `AC-ACD-002/003/004` + `AC-INT-001` (sin códigos nuevos).
- Migración 017 aditiva (snapshots+evidence+triggers) + refactor `save_session→_save_session_tx` (misma semántica, F9-D verde) + métodos con `cx`. `GradingPolicy`/orquestación intactas; sin scoring inventado ni simulación como corrección.
- Nuevos: `test_f9_correction.py` (19 contractuales: lifecycle, cupo/cancel, doble submit, prepare, historia congelada, tipos, bordes numeric, symbolic, inválidos, pending, omitidas, evidence+tamper, rollback, determinismo, seguridad AST).
- Docs: `F9-ASSESSMENT.md` + `GATE-F9-CERTIFICATION.md` (criterios §23: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: refactor interno + pins `16→17` (la 017 los exige).
- Evidencia local: 19/19 F9 + regresión 267 passed / 1 skip ambiental + 33 passed × 3 hash-seeds. Commit impl. `acec7ed`. Run `36244520858` (`ef1976c`): intento 1 con 1 flake `test_perf_academic_scale` (22.9s/20s, win-3.13, clase §8); intento 2 tras `rerun --failed` verde 4/4 + package. Run de certificación `36248720654` (`1b41cd5`) verde 5/5. Roadmap: F9 CERTIFICADA, F10 SIGUIENTE.

## Unreleased — Fase D7: Ingesta estructurada → Knowledge Core (CERTIFICADA)
- Plan puro `domain/ingestion.py` + servicio `application/bank_ingest.py` (plan/dry-run/ingest, 1 tx `unit_of_work`, verify post-commit, `now_ms` inyectable). Políticas: reuse/create/rechazo determinista, ambigüedad concepto+formula → error, idempotencia por digest, versiones create/unchanged/update/conflict/stale, reuse sin overwrite, fórmula modificada = conflicto.
- Migración 016 aditiva (`qbank_banks`, `qbank_questions`, `formulas` para `academic.Formula`) + `QBankRepository` con `cx`; conceptos en `study_concepts` (reuso, creación solo con catálogo + subject existente + bump `id_counters.concept`); refs section/document/topic carried opacos. Errores `AC-ACD-002/003/004` + `AC-INT-001` (sin códigos nuevos).
- Nuevos: `test_d7_ingestion.py` (18 contractuales: mínimo, mapping, digest, create, idempotencia cero-writes, update+delete, reuse, unresolved `AC-ACD-002`, ambigüedad `AC-ACD-003`, provenance E2E, no-overwrite, conflicto de fórmula, rollback inyectado, dry-run, determinismo ×2 DBs, inválidos/versiones, subject desconocido, seguridad AST + latex inerte).
- Docs: `D7-INGESTION.md` + `GATE-D7-CERTIFICATION.md` (criterios §23: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: solo pins `15→16` en `test_migration.py`/`test_persistence.py` (la 016 los exige).
- Evidencia local: 18/18 D7 + regresión amplia verde (1 pin actualizado, re-verde) + 48 passed × 3 hash-seeds. Commit impl. `18d3815`. Run `36239628773` (`03579c0`): intento 1 con 1 flake `test_perf_academic_scale` (21.47s/20s, win-3.13, clase §8); intento 2 tras `rerun --failed` verde 4/4 + package. Roadmap: D7 CERTIFICADA, F9 SIGUIENTE.

## Unreleased — Fase D6: Esquema neutro de banco de preguntas (CERTIFICADA)
- Dominio puro `domain/question_bank.py`: `Bank`/`Question`, 7 `qtype`, `answer_spec` por tipo (claves cerradas), IDs `bank:<slug>` / `question:<slug>:q:NNNNN`, `schema d6-question-bank/1` + `content_version`, canonicalización `sort_keys` + digest `sha256(tag+0x00+canonical)`, envelope con `integrity`, validación estricta + extensiones `x-`, provenance forma F2, errores D2 existentes (sin códigos nuevos), cero floats, sin persistencia (formato + validador).
- Nuevos: `test_d6_question_bank.py` (16 contractuales: mínimos, tipos, IDs, schema/rechazo `AC-VER-001`, canonicalización, digest semántico, round-trip, provenance, knowledge_refs, answer_spec, unidades + `parse_unit`, extensiones, tamper/inválidos, determinismo, seguridad AST).
- Docs: `D6-QUESTION-BANK.md` + `GATE-D6-CERTIFICATION.md` (criterios §21: todo verde salvo CI real y roadmap, explícitamente pendientes). Cero código certificado tocado.
- Evidencia local: 16/16 D6 + regresión 189 passed / 1 skip ambiental + 36 passed × 3 hash-seeds. Commit impl. `07b3136`. Run `36236406471` (`86f105d`) verde 4/4 + package. Roadmap: D6 CERTIFICADA, D7 SIGUIENTE.

## Unreleased — Fase D5: Suite global de tests (CERTIFICADA)
- Baseline pre-D5: 4598 tests / 138 ficheros → 4583 passed, 2 failed (preexistentes), 13 skipped, ~60 min local.
- Fix §12 (bug real): `SyncService._apply_winners` llamaba `add_favourite(kind, ref, title)` sobre el repositorio → `TypeError` al aplicar favoritos remotos; ahora construye `PL.SavedSearch` (preserva `created`). Regresión incluida.
- Fix §12 (test con fecha caducada): `test_activity_from_documents_and_reading` dependía del reloj real (verde CI 09-25, rojo desde 09-26); `added_at` backdateado, fechas 100% fijas. Cero producto tocado.
- Fix §9: `test_generality_sweep_both_modes` (105s > 90s en runner lento, CI verde) marcado `perf`; umbral intacto.
- Nuevos: `test_f13ext_service.py` (13: identidad, adaptadores, 2 BDs, idempotencia, `AC-SYN-001`, límites) + `test_d5_contracts.py` (7: AST F13-ext/D4, pureza dominio, markers, perf).
- Markers `arch`/`repro`/`perf` (+registro `perf`); CI ejecuta lo mismo. Docs: `TEST-SUITE.md` canónico (+matriz 16 áreas), `STRATEGY.md` como puntero. Cero eliminaciones (auditoría: sin duplicados reales).
- Evidencia: 20 nuevos verdes + regresión 134 passed × 3 hash-seeds. Run `36232344763` (`c14c317`) verde 4/4 + package. Roadmap: D5 CERTIFICADA, D6 SIGUIENTE.

## Unreleased — Fase D4: Pipeline CI/build (CERTIFICADA)
- Workflow único `.github/workflows/ci.yml`: matriz windows/ubuntu × py3.12/3.13, install desde `requirements-lock.txt`, `compileall`, `pytest -m "not external"`, job `package` con `python -m build` y artefacto `dist/`. Sin bypasses, sin secretos, sin dependencias de producto.
- Tests `test_d4_pipeline.py` (7, stdlib, sin red): triggers, sin bypasses, lock pineado, pytest ejecuta, fallo→rc!=0, build declarado, árbol limpio.
- Docs `docs/testing/CI.md` + `GATE-D4-CERTIFICATION.md`. Evidencia local: 58 passed regresión, build real sdist+whl en venv aislado. Runs del proveedor: #1 fallo setup (Qt/ubuntu, corregido), #2 un solo fallo preexistente `html_cp1252` (divergencia manylinux-lxml, documentada) → `tests/conftest.py` con tabla §14 (xfail estricto en linux + skip por sonda symlink), sin tocar ficheros certificados → Run `36133175963` (`6bdd27b`) verde en las 4 celdas + package (ver gate). Roadmap: D4 CERTIFICADA, D5 SIGUIENTE.

## Unreleased — Fase F13-ext: Sync determinista 2 PCs (CERTIFICADA)
- Motor puro `domain/sync.py`: LWW `(ms, device)`, digest canónico, tombstones, idempotencia `sync(S',R)=S'`, protocolo `f13ext-sync/1`, sin CRDT.
- Aplicación `application/sync.py`: identidad estable `sync.device_id`, adaptadores preferences/saved_searches/quick_notes, verify interno.
- Infraestructura: migración 015 (`sync_state`+`sync_log`), `FileTransport` con límites y rechazo `AC-SYN-001`, wiring en facade.
- Tests `test_f13ext_sync.py`: 12/12 normativos. Docs: `F13EXT-SYNC.md` + `GATE-F13EXT-CERTIFICATION.md`. Roadmap: F13-ext CERTIFICADA, D4 SIGUIENTE.

## Unreleased — Fase F4.1: Gestion-Academica integrada (2026-09-23)
- Modelo académico centrado en la asignatura: estados CURSANDO/APROBADA/SUSPENDIDA/NO_CURSANDO, Home/Carrera/detalle de asignatura.
- Evaluación esquema/bloque/componente/nota mínima en Decimal (golden 400 casos vs Gestion real).
- Documentos en contexto de asignatura sobre CAS+FTS, espacios de estudio, recursos externos solo-URL, ICS, guía docente sobre F3/F3.1.
- Migración Gestion → AcademicCore: dry-run, snapshot, transacción única, idempotente, sin pérdidas, determinista.
- Cierre: profesores sin fusión por nombre, restore de backup verificado, arnés de certificación real. Gate: F4.1 NOT CERTIFIED hasta ejecutar el arnés sobre la instalación real (fallo F3 golden preexistente por libxml2). Ver `docs/gates/GATE-F4.1-CERTIFICATION.md`.

## 0.18.0 — Fase F8-I: BJT Ebers-Moll Nonlinear DC Operating Point (2026-09-16)
- Bipolar Junction Transistor (BJT) model under classic Ebers-Moll equations for NPN and PNP polarities.
- Exact coupled $3 \times 3$ analytical Jacobian without numerical approximations.
- Invariant matrix properties: $\sum_i J_{ij} = 0$ (KCL conservation), $\sum_j J_{ij} = 0$ (reference voltage shift invariance).
- Strict `Decimal` physical calculations (`prec=50`, `prec=80`) and zero `float` policy (verified via AST audit).
- Robust exponential damping and clamping ($V_{\text{clamp}} = 100 \cdot V_T$) with geometric bisection line-search.
- 15 canonical circuit topologies verified (B1–B15: fixed bias, self-bias, emitter follower, common base, PNP common emitter, saturation, reverse active, current mirror, differential pair, Darlington pair, inverter switch, BJT+diode, BJT+dependent sources, BJT+OpAmp, BJT+transformer).
- Multi-BJT scaling matrix ($N=1..64$) with constant 7 Newton iterations.
- Automated cross-validation with ngspice 47 (< $10^{-4}$ relative error).
- Gate F8-I: 143 passed (69 F8-H diode + 33 F8-I BJT physics + 41 F8-I nonlinear MNA circuits).

## 0.17.0 — Fase F8-H: Shockley Diode Nonlinear DC Operating Point (2026-09-16)
- Nonlinear DC MNA solver with damped Newton-Raphson and geometric backtracking.
- Shockley diode companion model and analytical conductance $g_d = \frac{I_S}{n V_T} \exp(V_d / n V_T)$.
- Physical block convergence criteria: KCL residual $\le 10^{-12}\text{ A}$, aux residual $\le 10^{-9}\text{ V}$.
- Full conservation checks: KCL, KVL, Tellegen power balance.
- Automated cross-validation with ngspice 47.
- Gate F8-H: 69 passed.

## 0.16.0 — Fase F8-G: Ideal Transformers & Two-Port Network Parameters (2026-09-16)
- Ideal transformer model with turns ratio $n$ ($V_1 = n V_2, I_2 = -n I_1$).
- Auxiliary variables for primary and secondary winding currents in MNA.
- Linear two-port matrix parameter extraction ($Z, Y, H, ABCD$) via test-source excitation.
- Gate F8-G: CERTIFIED (`GATE-F8G.md`).

## 0.15.0 — Fase F8-F: Ideal Operational Amplifiers / Nullors (2026-09-15)
- Ideal op-amp model (nullor: $V_+ = V_-$, $i_+ = i_- = 0$) for DC and AC steady-state MNA.
- Auxiliary output current unknown $i_o$ leaving op-amp output pin into ground.
- Strict singularity and degenerate topology classification via `math.linsolve` rank analysis.
- Gate F8-F: CERTIFIED (`GATE-F8F.md`).

## 0.14.0 — Fase F8-E: Linear Dependent Sources (2026-09-14)
- All four linear controlled sources: VCVS ($E$), VCCS ($G$), CCVS ($H$), CCCS ($F$).
- Current control graph cycle detection (`check_control_cycles`) and `CircularControlError`.
- Deterministic control current resolution and DC/AC stamping.
- Gate F8-E: CERTIFIED (`GATE-F8E.md`).

## 0.13.0 — Fase F8-D: AC Small-Signal Phasor Simulation Suite (2026-09-14)
- F8-D1: Exact and arbitrary-precision complex arithmetic (`DecimalComplex`, `FractionComplex`).
- F8-D2: Complex linear system solver with Rouché-Capelli rank analysis.
- F8-D3: General AC MNA in steady-state with peak phasors ($e^{+j\omega t}$) for $R, L, C, V, I$.
- F8-D4: Complex power $S = P + jQ$, apparent power, power factor, Tellegen balance in AC.
- F8-D5: AC driving-point impedance/admittance and transfer functions.
- F8-D6: Frequency sweep engine and Bode plots (dB magnitude, phase unwrap, $-3\text{ dB}$ cutoff brackets).
- F8-D7: Complex AC Thévenin and Norton equivalents ($Z_{th}, V_{th}, I_{no}$).
- F8-D8: Resonance detection by bracket search and reactive/dissipated energy quality factor ($Q$).
- Gates F8-D1 through F8-D8: CERTIFIED.

## 0.12.0 — Fase F8-C: DC Thévenin & Norton Reductions (2026-09-13)
- General active one-port network reduction via test-source injection and open-circuit voltage calculation.
- Certified equivalence validation across arbitrary linear resistive networks.
- Gate F8-C: CERTIFIED (`GATE-F8C.md`).

## 0.11.0 — Fase F8-B: General Linear DC MNA Solver (2026-09-13)
- Exact rational MNA solver over `fractions.Fraction` for $R, V, I, E, G, H, F, O$.
- Machine-zero KCL/KVL residuals and exact power balance.
- Gate F8-B: CERTIFIED (`GATE-F8B.md`).

## 0.10.0 — Fase F8-A: Electronics Knowledge Core (2026-09-13)
- Canonical circuit model extensions, models registry, validation contracts.
- Gate F8-A: CERTIFIED (`GATE-F8A.md`).

## 0.9.0 — Fase F7-B: Simulation Suite Hardening (2026-09-13)
- Hardened external ngspice 47 subprocess execution, timeout management, stdout/stderr isolation.
- Report F7-B8: CERTIFIED (`F7-B8-HARDENING-REPORT.md`).

## 0.8.0 — F7-A Simulation Runtime Foundation (2026-09-12)
- ngspice runtime discovery, version verification, isolated execution,
  stdout/stderr/exit capture, timeout, cancellation and cleanup.
- Windows setup/runtime documentation and separate external integration test.

## 0.7.0 — Fase 6 Engineering Foundation (2026-09-12)
- Decimal quantities, SI units/prefixes/dimensions and safe equation parser.
- Deterministic electrical calculations with provenance digests.
- Circuit topology (components/pins/nets), canonical netlists and typed models.
- SQLite migration 010, engineering repository/service, Authoring links and
  structured Engineering UI.
- Simulation boundary only: Null/Mock backends; no SPICE or subprocess.
- Gate F6: 205 passed, 2 skipped.

## 0.6.0 — Fase 5 Authoring Engine (2026-09-12)
- Command model (7 deterministic commands + undo/redo) + lifecycle +
  structured validation + 5 AST templates + in-document search.
- `document` resource kind + migration 009 (authored lifecycle, doc_links) +
  versioning/autosave/copy-paste/academic links service + Authoring UI tab.
- Round-trip battery (MD+HTML, documented equivalence) + F3 compat golden.
- Fidelity fixes shared with F3 (image targets, bare-inline items, math spans).
- Gate F5: 174 passed, 2 skipped (145 F0–F4 + 29 F5).

## 0.5.0 — Fase 4 Academic Management (2026-09-12)
- Gestion audit + reuse map (concept-only, no code copied).
- Generic gradebook (scales/weights/optional/partial, Decimal) beside F1
  engine (ADR-0016); results service; planning queries; JSON import/export;
  safe deletes + prerequisites; migration 008 (additive).
- Facade (`AcademicApp`) + `ui/` workspace (tree, 5 tabs, dialogs).
- Gate F4: 145 passed, 2 skipped (123 F0–F3 + 22 F4).

## 0.4.0 — Fase 3 Document + PDF Engine (2026-09-12)
- Conversor audit (20 comps) + selective reuse (math 1:1, tables, images,
  sanitize, metadata, encoding) with equivalence tests vs original module.
- Canonical AST (19 kinds, v1, validated, deterministic JSON) + HTML/MD
  parsers + MD/HTML renderers + doc derivations (007) + provenance chain.
- PDF engine (pypdf native: inspect/merge/split/rotate/extract/PDF→AST) +
  Stirling v2.14.3 research, runtime manager, API backend (mock-verified,
  live SIMULATED). ADR-0015. Gate F3: 123 passed, 2 skipped.

## 0.3.0 — Fase 2 Resource Engine (2026-09-12)
- Ports (`BlobStore/Extractor/Indexer/Records`) + `Resource/Version/Provenance`.
- CAS: streaming SHA-256, atomic, integrity-checked, traversal-safe.
- Adapters file/md/html/pdf (+ZIP refused); pipeline idempotente + versiones.
- FTS5 derivado con rebuild + filtros; tab Resources; `ingest.max_bytes`.
- ADR-0013/0014; gate F2: 81 passed (41 F0/F1 + 40 F2).

## 0.2.0 — Fase 1 Domain & Academic Foundation (2026-09-12)
- Domain: 20 entidades (University→Subject→Topic/Assignment/Exam/Project/Lab/
  Task/Deadline/Grade/Tag/Bookmark/Annotation/StudySpace/Session/Notification),
  Term genérico, invariantes con DomainError.
- Identity: 16 kinds, slugify NFKD, IdAllocator + counters persistidos.
- Grading Decimal HALF_UP + equivalencia (ADR-0011); schedule/conflictos puros.
- Persistence: sqlite3 stdlib, 4 migraciones, repos explícitos (ADR-0012).
- Application: Academic/Grading/Schedule services + Search/Backup/AppLock.
- UI Qt validación (selectores, subjects CRUD, 4 tabs) + gate F1: 41 passed.

## 0.1.0 — Fase 0 foundation (2026-09-12)
- Audits: Conversor (monolito 6.051 lín + lab 16 módulos), Gestion (Flask,
  28 tablas, 152 rutas, 672 docs), Sistemes (91 fuentes, 2896 fórmulas,
  1092 tests) — full detail in `docs/migration/`.
- Architecture: modular monolith, 10 ADRs, domain v0, stable IDs, storage
  SQLite+CAS, engines interfaces (resource/document/pdf/ai/providers/
  engineering), Qt skeleton executable, config system, 6 test files.
- Gates: fast suite + migration contract + reproducibility + boundary test.
