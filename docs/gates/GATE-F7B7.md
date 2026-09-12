# GATE F7-B7 — GUM / Measurement Uncertainty Evaluation Engine

## Result: PASS

- [x] `MeasurementModel` implementado (modelo de dominio con measurand, ecuación con parser seguro sin eval/exec, o evaluator callable, unidades dimensionales y sensibilidades)
- [x] `InputQuantity` implementado con soporte completo para:
  - Type A: constructor `from_observations` calculando media, desviación estándar muestral con corrección de Bessel ($s / \sqrt{n}$) y grados de libertad $\nu = n - 1$.
  - Type B Rectangular: $u = a / \sqrt{3}, \nu = \infty$.
  - Type B Triangular: $u = a / \sqrt{6}, \nu = \infty$.
  - Type B Normal: $u = U / k$ con grados de libertad $\nu = \infty$ o finitos especificados por calibración.
  - Type B Explícito: especificación directa de nominal, $u$ y $\nu$.
- [x] Coeficientes de sensibilidad ($c_i = \partial f / \partial X_i$) implementados:
  - Explícito: funciones o constantes directas.
  - Analítico: patrones cerrados reconocidos automáticamente.
  - Numérico: diferencias finitas centrales con control de escala ($h = \max(|x| \cdot 10^{-6}, 10^{-8})$).
- [x] Prohibición estricta de `eval()` / `exec()` respetada rigurosamente en toda la implementación.
- [x] Matriz de correlación y covarianza implementada (`CorrelationMatrix` con verificación de simetría $r_{ij} = r_{ji}$, rango $[-1, 1]$, diagonal unitaria y cálculo $\text{cov}(X_i, X_j) = r_{ij} u_i u_j$).
- [x] Incertidumbre estándar combinada $u_c(y)$ implementada según ISO/IEC Guide 98-3 ecuación (10) con suma cuadrática y términos de covarianza.
- [x] Fórmula de Welch-Satterthwaite implementada ($\nu_{\text{eff}} = \frac{u_c^4(y)}{\sum (c_i u_i)^4 / \nu_i}$), con tratamiento exacto de $\nu_i = \infty$ (términos nulos en denominador) y límite $\nu_{\text{eff}} = \infty$.
- [x] Distribución t de Student implementada en Python puro estándar (fracciones continuadas de Lentz para beta incompleta regularizada e inversión por Newton-Raphson).
- [x] Factor de cobertura $k$ derivado dinámicamente de $t_p(\nu_{\text{eff}})$ (estrictamente no hardcodeado a $k=2$).
- [x] Verificación benchmark contra Tabla G.2 de ISO/IEC Guide 98-3 para $\nu \in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 50, 100, \infty]$ a $95\%$ y $99\%$ de cobertura.
- [x] Incertidumbre expandida $U = k \cdot u_c(y)$ calculada.
- [x] Tabla estructurada de presupuesto de incertidumbre (`UncertaintyBudget` y `UncertaintyBudgetRow` con ordenación por contribución y nombre, exportación a Markdown y diccionario serializable).
- [x] Modelo de resultado `GUMResult` con hash CAS e integración con `FileBlobStore`.
- [x] Casos de validación analítica A a J verificados con 100% de éxito:
  - Caso A: Suma ($Y = X_1 + X_2$, $u_c = \sqrt{0.1^2 + 0.2^2} \approx 0.2236$).
  - Caso B: Producto ($Y = X_1 \cdot X_2$, $u_c \approx 0.7071$).
  - Caso C: Divisor de tensión ($V_{out} = V_{in} \cdot R_2 / (R_1 + R_2)$, $u_c \approx 0.0433\text{ V}$).
  - Caso D: Correlación ($r = +1 \implies u_c = 0.3$, $r = -1 \implies u_c = 0.1$).
  - Caso E: Tipo A a partir de observaciones muestrales.
  - Caso F: Tipo B rectangular ($u = a / \sqrt{3}$).
  - Caso G: Tipo B triangular ($u = a / \sqrt{6}$).
  - Caso H: Tipo B normal ($u = U / k$).
  - Caso I: Welch-Satterthwaite con grados de libertad finitos e infinitos.
  - Caso J: $\nu_{\text{eff}}$ pequeño produciendo $k \neq 2$ ($k \approx 2.78$ para $\nu=4$).
- [x] Integración en `EngineeringService.evaluate_measurement_uncertainty()`.
- [x] Cero dependencias externas (`scipy` NO utilizado).
- [x] GUM estrictamente desacoplado de Monte Carlo.
- [x] Tests F7-B7 pasan: 30 passed.
- [x] Tests de todos los módulos F7 (F7-A, F7-B1..B7) pasan: 148 passed.
- [x] Regresión completa del repositorio pasa: 353 passed, 2 skipped, 0 failed.
- [x] Auditoría creada (`docs/migration/ENGINEERING-F7B7-AUDIT.md`).
- [x] Gate creado (`docs/gates/GATE-F7B7.md`).
- [x] F7-B8 NO ha sido iniciado.

F7-B7 is certified PASS. F7-B8 has not started.
