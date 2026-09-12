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

## Surgical Closure: `MeasurementModel.evaluator` Dimensional Bypass

A third independent audit found that the `evaluator=` callable path bypassed all of the
above: `evaluate_to_quantity()` reduced every input to bare `Decimal` before calling the
evaluator, then labeled whatever it returned with `output_unit` unchecked — allowing e.g.
`10 mm + 2 s` to silently return `12 mm`. See `docs/migration/ENGINEERING-F7B7-AUDIT.md`
§9 for full detail.

### Evaluator Bypass Closure Checklist
- [x] `evaluator` dimensional recibe `dict[str, Quantity]` (cuando el modelo declara alguna unidad de entrada o `output_unit`).
- [x] `evaluator` dimensional debe devolver `Quantity`; un `Decimal` es rechazado con `UnitError: ... must return Quantity` — nunca etiquetado silenciosamente con `output_unit`.
- [x] Las operaciones dimensionales dentro del evaluator las ejecuta `Quantity` (p. ej. `x["V"] / x["R"]`), no aritmética manual.
- [x] `mm + s` dentro de un evaluator falla con `UnitError`.
- [x] `mm + V` dentro de un evaluator falla con `UnitError`.
- [x] `V / Ω = A` vía evaluator funciona (`0.01 A` exacto).
- [x] `output_unit` incompatible con el resultado del evaluator falla (`UnitError`).
- [x] `output_unit` compatible con distinta escala convierte correctamente (`100 mm → 0.1 m`, `Decimal` exacto).
- [x] Unidades de entrada u `output_unit` desconocidas siguen fallando (`UnitError`, sin unidad fabricada).
- [x] Un `Quantity` pasado directamente como input llega intacto al evaluator (verificado por identidad `is`).
- [x] Modelo legacy totalmente adimensional (sin ninguna unidad declarada) conserva el contrato `Decimal → Decimal` preexistente (`test_custom_evaluator`).
- [x] No existe fallback sintético ni segundo sistema de unidades: `_build_quantity_env` y `_validate_output` (nuevos, compartidos por `evaluator=` y `equation=`) delegan exclusivamente en `_resolve_unit` → `units.py::parse_unit()`.
- [x] Test de regresión del caso auditado exacto (`evaluator=lambda x: x["X"]+x["T"]`, `input_units={"X":"mm","T":"s"}`, `output_unit="mm"`) falla con `UnitError`, nunca devuelve `12`.
- [x] Todos los tests B7 pasan: **79/79** (`tests/test_f7b7_gum.py`, +11 tests nuevos de cierre del bypass).
- [x] Todos los tests F7 pasan: **197/197** (`tests/test_f7*.py`).
- [x] Full regression pasa: **402 passed, 2 skipped** (mismos skips preexistentes de `reportlab`), **0 failed**.
- [x] PSD, Student-t, sensibilidad, `explicit_k`, provenance, Monte Carlo, y la arquitectura F6 `units.py` NO fueron modificados (solo se añadieron `_build_quantity_env`/`_validate_output`/`_is_dimensional` internos a `gum.py`, refactorizando lógica ya existente).
- [x] Working tree limpio (post-commit).

---
F7-B7 is certified **PASS** (final post-audit remediation + evaluator dimensional bypass closed). F7-B8 has not started.
