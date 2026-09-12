# GATE F7-B6 — Monte Carlo y Análisis Estadístico con ngspice Real

## Result: PASS

- [x] `MonteCarloAnalysis` implementado (modelo de dominio con iteraciones, parámetros con distribuciones, output_variables, seed determinista, continue_on_error y metric_extractors)
- [x] RNG reproducible implementado (instancia explícita `random.Random(seed)` sin estado global, sub-seeding determinista por iteración y ordenación alfabética de parámetros)
- [x] Seed reproducible verificado (Config A + seed 12345 dos veces genera resultados idénticos bit a bit; seed diferente produce muestras distintas)
- [x] Distribución `Normal` implementada (nominal, std_dev o tolerance_pct con sigma_coverage configurable, y clamping min/max)
- [x] Distribución `Uniform` implementada (nominal con tolerance_pct o límites explícitos [low, high])
- [x] Muestras trazables (pre-generadas antes de ejecutar simulación y almacenadas en `MonteCarloIteration` con parámetros, netlist y sub-seed)
- [x] Sustitución de parámetros en netlist implementada (soporte para R, L, C, V, I y .param sin alterar directivas SPICE)
- [x] Estadísticas implementadas (`VariableStatistics` con count, mean, median, min, max, varianza muestral, desviación estándar muestral con corrección de Bessel N-1, y coeficiente de variación)
- [x] Percentiles implementados ($P_1, P_5, P_{25}, P_{50}, P_{75}, P_{95}, P_{99}$ mediante interpolación lineal de rango)
- [x] Casos límites $N=0$ rechazado (ValueError) y $N=1$ permitido (std_dev = 0, percentiles = valor)
- [x] Fallos parciales correctamente tratados (política configurable `continue_on_error`: captura de errores en iteración y estado `PARTIAL` o `FAILED`)
- [x] Cancelación soportada (interrupción limpia de ejecuciones ngspice y estado `CANCELLED`)
- [x] Timeout soportado (heredado y verificado en runtime backend)
- [x] CAS funciona (almacenamiento de raw payload y digest SHA-256 verificado en `FileBlobStore`)
- [x] Provenance funciona (backend_id, backend_version, executable_path, seeds, configuración, timestamps)
- [x] Caso 1 Validado científicamente: Divisor resistivo ($V_1=10\text{ V}, R_1=1\text{ k}\Omega \pm 5\%, R_2=1\text{ k}\Omega \pm 5\%$, media $4.996\text{ V} \approx 5.0\text{ V}$, min/max dentro de límites $[4.75, 5.25]\text{ V}$)
- [x] Caso 2 Validado científicamente: Filtro RC pasa-bajos ($R=1\text{ k}\Omega \pm 5\%, C=1\ \mu\text{F} \pm 5\%$, media $f_c = 163.07\text{ Hz} \approx 159.155\text{ Hz}$, dispersión física dentro de $[140, 180]\text{ Hz}$)
- [x] Caso 3 Validado científicamente: Circuito RLC resonante ($R=10\ \Omega \pm 5\%, L=1\text{ mH} \pm 5\%, C=1\ \mu\text{F} \pm 5\%$, media $f_0 = 5032.06\text{ Hz} \approx 5032.92\text{ Hz}$ y corriente máxima $0.1010\text{ A} \approx 0.1000\text{ A}$)
- [x] Ambas distribuciones (Normal y Uniform) validadas contra ngspice 47 real
- [x] Múltiples parámetros simultáneos validados ($V_1, R_1, R_2, R_3$)
- [x] Fallo controlado de iteración validado y registrado en `MonteCarloIteration.errors`
- [x] Integración end-to-end con `EngineeringService.simulate_circuit` y modelo `Circuit`
- [x] ngspice 47 real utilizado (`ngspice_con.exe`)
- [x] Tests F7-B6 pasan: 29 passed
- [x] F7-A/B1/B2/B3/B4/B5/B6 pasan: 118 passed
- [x] Regresión completa del repositorio pasa: 323 passed, 2 skipped, 0 failed
- [x] Auditoría creada (`docs/migration/ENGINEERING-F7B6-AUDIT.md`)
- [x] Gate creado (`docs/gates/GATE-F7B6.md`)
- [x] Distinción rigurosa explícita: Monte Carlo $\neq$ GUM $\neq$ tolerancia $\neq$ error $\neq$ desviación estándar $\neq$ percentil
- [x] Confirmación de que GUM / ISO 98-3 NO fue implementado
- [x] Confirmación de que paralelización / multiprocessing NO fue implementada
- [x] Confirmación de que F7-B7 NO ha sido iniciado
- [x] Working tree limpio

F7-B6 is certified PASS. F7-B7 has not started.
