# GATE F7-B7 — GUM / Measurement Uncertainty Evaluation Engine

## Result: PASS (Post-Audit Hardened & Certified)

### Post-Audit Hardening Verification Checklist
- [x] PSD validation implementada (algoritmo Jacobi puro en Python stdlib, sin scipy/numpy, tolerancia $\text{tol} = 10^{-7}$).
- [x] PSD tests pasan (casos A a I: identidad 3x3, matriz válida, correlación perfecta $+1$ y $-1$, matrices no PSD rechazadas, $r > 1$ y $r < -1$ rechazados, diagonal $\neq 1$ rechazada, autovalor nulo aceptado dentro de tolerancia, y validación integrada en `evaluate_gum`).
- [x] dimensional evaluation real implementada (integración con el sistema de unidades certificado en F6 `units.py`, `equations.py`, cada `InputQuantity` entra con su unidad real).
- [x] dimensional tests pasan (casos 1 a 8: $V / \Omega = A$, $V \cdot A = W$, $V / A = \Omega$, rechazo dimensional de $V + s$, $V + A$, $A + \Omega$, rechazo de `output_unit` incompatible, aceptación de `output_unit` compatible, y preservación de ecuaciones existentes).
- [x] sensitivity precision corregida (eliminado el redondeo arbitrario a 9 decimales; preservada la precisión `Decimal` completa).
- [x] explicit_k validation implementada (validación estricta $k > 0$, rechazo de $k \le 0$, NaN, $\pm\infty$, y distinción de provenance `explicit_user` vs `student_t` vs `normal_limit`).
- [x] Type A/B existentes siguen pasando (repetibilidad muestral con corrección de Bessel, rectangular, triangular, normal, explícita).
- [x] Welch-Satterthwaite sigue pasando (grados de libertad efectivos finitos e infinitos).
- [x] Student-t sigue pasando (benchmark contra Tabla G.2 de ISO/IEC Guide 98-3 a 95% y 99%).
- [x] correlation propagation sigue pasando (propagación analítica de términos de covarianza).
- [x] provenance sigue completo (hashes CAS SHA-256, metadatos, timestamp UTC, inputs, presupuesto completo).
- [x] F7 regression PASS (174 tests pasando en F7-A y F7-B1..B7).
- [x] full repository regression PASS (379 tests pasando, 2 skipped explicables, 0 failed).
- [x] working tree limpio.

### Scope & Architectural Compliance
- [x] Cero dependencias externas (`scipy` / `numpy` estrictamente NO utilizados).
- [x] Prohibición estricta de `eval()` / `exec()` respetada rigurosamente en toda la implementación.
- [x] GUM estrictamente desacoplado de Monte Carlo.
- [x] F7-B8 NO ha sido iniciado.

---
F7-B7 is certified PASS. F7-B8 has not started.

