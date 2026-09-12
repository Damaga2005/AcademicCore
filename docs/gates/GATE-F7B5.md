# GATE F7-B5 — Análisis de Ruido y Sensibilidad con ngspice Real

## Result: PASS

- [x] ngspice 47 real ejecuta `.noise` (modo batch headless `ngspice_con.exe -b`)
- [x] Parser noise funciona (`Integrated Noise` + `Noise Spectral Density Curves`)
- [x] Ruido térmico coincide con teoría ($e_n = \sqrt{4 k_B T R} \approx 4.071337 \times 10^{-9}\text{ V}/\sqrt{\text{Hz}}$ vs $4.071372 \times 10^{-9}\text{ V}/\sqrt{\text{Hz}}$, error $< 0.01\%$)
- [x] Circuito RC con ruido validado (plateau de baja frecuencia, caída pasa-bajos y ruido total integrado $\sqrt{k_B T / C} \approx 6.437 \times 10^{-8}\text{ V}_{\text{RMS}}$ vs $6.414 \times 10^{-8}\text{ V}_{\text{RMS}}$)
- [x] Sensibilidad implementada (soporte para `.sens` tanto en DC escalar como en AC espectral complejo con $R, L, C, V$)
- [x] Sensibilidad validada contra teoría y diferencias finitas ($\partial V / \partial R_1, \partial V / \partial R_2, \partial V / \partial V_1$, y $\partial H / \partial C, \partial H / \partial R$ con concordancia $< 0.05\%$)
- [x] Resultados tienen unidades correctas ($\text{V}/\sqrt{\text{Hz}}$, $\text{V}_{\text{RMS}}$, $\text{V}/\Omega$, $\text{V/F}$, $\text{V/H}$, adimensional)
- [x] CAS funciona (almacenamiento de raw payload y digest SHA-256)
- [x] Provenance funciona (backend_id, backend_version, executable_path, timestamps, duración)
- [x] Timeout funciona (heredado y validado en backend)
- [x] Cancelación funciona (heredado y validado en backend)
- [x] Errores son detectados y propagados limpiamente
- [x] Tests F7-B5 pasan: 18 passed
- [x] F7-A/B1/B2/B3/B4 siguen pasando: 71 passed
- [x] Regresión completa pasa: 294 passed, 2 skipped
- [x] Auditoría creada (`docs/migration/ENGINEERING-F7B5-AUDIT.md`)
- [x] Gate creado (`docs/gates/GATE-F7B5.md`)
- [x] Working tree limpio

F7-B5 is certified PASS. F7-B6 has not started.
