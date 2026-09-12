# GATE F7-B7 — GUM / Measurement Uncertainty Evaluation Engine

## Result: PASS (Final Post-Audit Hardened & Certified)

A second independent audit found that `gum.py::_resolve_unit()` fabricated a synthetic,
hash-derived dimension for any unit string unrecognized by F6's `units.py`. This gate
reflects the final remediation: the synthetic fallback has been removed, F6 was extended
with a real `LENGTH` dimension and `m`/`mm`/`cm`/`km` units, and `parse_unit()` is now the
sole, exclusive authority for unit resolution throughout GUM. See
`docs/migration/ENGINEERING-F7B7-AUDIT.md` §8 for full detail.

### Final Post-Audit Hardening Checklist
- [x] No existen unidades sintéticas (`_resolve_unit` no contiene fallback; `hashlib` solo se usa para el hash de provenance CAS, no para unidades).
- [x] No existen dimensiones generadas por hash.
- [x] `parse_unit()` (`units.py`) es la única autoridad de resolución de unidades en todo `gum.py`.
- [x] `LENGTH = (0, 1, 0, 0, 0, 0, 0)` correctamente implementada e integrada; `mm`/`cm`/`km` derivan de `m` vía prefijos SI reales (`Decimal` exacto), no de casos especiales por símbolo.
- [x] `mm` y `m` comparten dimensión (`parse_unit("m").dimension == parse_unit("mm").dimension == parse_unit("cm").dimension == parse_unit("km").dimension`).
- [x] `mm` ↔ `m` convierte correctamente (`100 mm == 0.1 m`; `1 m == 1000 mm`).
- [x] Unidades desconocidas son rechazadas (`parse_unit("unknown_unit")` → `UnitError`).
- [x] `output_unit` desconocida es rechazada (`MeasurementModel(output_unit="unknown_unit")` → `UnitError` en `evaluate_gum`).
- [x] $V / \Omega = A$.
- [x] $V \cdot A = W$.
- [x] $V + A$ es rechazado.
- [x] $V + s$ es rechazado.
- [x] Cross-dimension `1 mm + 1 s` y `1 mm + 1 V` son rechazados; `1 m + 100 mm == 1.1 m` es aceptado.
- [x] PSD sigue validado (Jacobi eigenvalue solver, `tol = 1e-7`; confirmado independiente del sistema de unidades).
- [x] Sensibilidad numérica no se redondea artificialmente (precisión `Decimal` completa, sin `round()`).
- [x] `explicit_k` sigue validado ($k > 0$; rechazo de $k \le 0$, NaN, $\pm\infty$).
- [x] Provenance sigue correcto (`explicit_user` / `student_t` / `normal_limit`).
- [x] Todos los tests B7 pasan: **68/68** (`tests/test_f7b7_gum.py`, incluye 12 tests nuevos A–L de Hallazgo 7).
- [x] Todos los tests F7 pasan: **186/186** (`tests/test_f7*.py`).
- [x] Full regression pasa: **391 passed, 2 skipped** (skips preexistentes de `reportlab`, no relacionados), **0 failed**.
- [x] Working tree limpio (post-commit).

### Scope & Architectural Compliance
- [x] Cero dependencias externas (`scipy` / `numpy` estrictamente NO utilizados).
- [x] Prohibición estricta de `eval()` / `exec()` respetada rigurosamente en toda la implementación.
- [x] GUM estrictamente desacoplado de Monte Carlo.
- [x] No se ha modificado Monte Carlo.
- [x] No se ha implementado F7-B8, ni nuevas capacidades metrológicas, ni nuevas distribuciones GUM.
- [x] Arquitectura de una única fuente de verdad para unidades: `MeasurementModel` → `units.py` → `Quantity` → `equations.py` → validación dimensional.

---
F7-B7 is certified **PASS** (final post-audit remediation). F7-B8 has not started.
