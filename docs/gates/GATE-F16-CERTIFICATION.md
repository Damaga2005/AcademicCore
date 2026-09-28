# GATE-F16-CERTIFICATION — F16 Contenido Aeroespacial (certificación)

> **FASE:** F16 — Contenido Aeroespacial / Satélite, mecánica orbital básica.
> **MODO:** implementación + certificación completa, revisión de cierre sobre `main`.
> **BASELINE:** `main @ f539a91` (`docs(f13): certificar con run 36385930302 verde`);
> revisión sin ramas permanentes.
> **VEREDICTO: F16 CERTIFICADA. ROADMAP COMPLETADO.**

## 1. Baseline, HEAD, commits, archivos

| | |
|---|---|
| baseline | `f539a91` |
| commit F16 (implementación) | `195d3e7` (`feat(f16): mecanica orbital basica determinista`, 13 ficheros, +1302/-1) |
| commit F16 (certificación) | este commit (gate + roadmap + changelog + readme) |
| CI run | [`36394085024`](https://github.com/Damaga2005/AcademicCore/actions/runs/36394085024) sobre `195d3e7`, `completed success` |
| estado esperado | F0→F13 CERTIFICADAS, F14 ELIMINADA, F15 CERTIFICADA, F16 única pendiente (verificado en ROADMAP §5.2) |
| producción | `domain/engineering/orbital/` (constants, bodies, orbits, kepler, elements), `domain/execution/orbital.py` (traza `physics.orbital`), `domain/engineering/units.py` (+MASS/FORCE/g/N/rad, aditivo), `application/explain_service.py` (+orbital_trace/explain_orbital/rama replay, aditivo) |
| tests | `tests/test_f16_orbital.py` (16 contractuales) |
| docs | `docs/architecture/F16-AEROSPACE.md` (este gate la describe) |

Sin códigos AC nuevos (reutiliza `ControlError/ControlStatus`).
Sin migraciones (sin persistencia nueva).
Sin dependencias nuevas.

## 2. Alcance y arquitectura

Motor único `f16-orbital/1` (two-body Decimal SI). Reutiliza `math/`
(sqrt/cbrt-Newton documentado/pi/trig), dimensiones `units.py`, traza
E0, errores de control. F8-P5 intacto (link-budget con `d` de entrada;
F16 calcula el movimiento, no el enlace). F9/D7 sin cambios.

## 3. Tests específicos (16/16 verdes local)

Matemática (ISS/GEO/escape/Molniya/Kepler round-trip 1E-25), cuerpo
central + provenance, unidades extendidas, dominio (r/μ/e/a/finitos/
marcos), determinismo (hash-seeds), traza `physics.orbital` + replay
equivalente.

TDD: test creado primero, RED verificado (ModuleNotFoundError), luego
GREEN mínimo; 2 fallos reales intermedios corregidos con contrato
explícito (cbrt con presupuesto propio, tolerancia relativa energía).

## 4. Regresión (verde local + CI completo verde)

- Local (cierre): `test_f16_orbital` 16/16; `test_quantities +
  test_eng_equations + test_eng_security + test_f7b7_gum +
  test_architecture + test_f8p5_satcom + test_e01r_hardening +
  test_application` verdes; E01/E02/E03/E04 verdes (219 tests);
  1 preexistente CRLF (`test_e0_g01_golden_voltage_divider`, falla en
  `main` limpio — clase documentada en el gate F12, ajeno a F16).
- CI completo `pytest -m "not external"` (run 36394085024): 4/4 celdas
  `success` (windows-2025 py 3.12, windows-2025 py 3.13, ubuntu-24.04 py
  3.12, ubuntu-24.04 py 3.13) + job `package` `success`; run `completed
  success`. Sin bypasses.

## 5. Seguridad

Sin `eval/exec/compile/subprocess/os.system/shell=True/pickle` en
ficheros F16 (test AST en `test_f16_orbital.py`, verde).
Parámetros físicos validados antes de calcular; sin deserialización
insegura (digests solo SHA-256 sobre JSON canónico).

## 6. E2E real

No aplica TLE/efemérides (fuera de alcance declarado). Casos conocidos
ISS/GEO/escape verifican la física contra referencias documentadas.

## 7. CI real

Run [`36394085024`](https://github.com/Damaga2005/AcademicCore/actions/runs/36394085024)
(`push` de `195d3e7` en `main`): 4/4 jobs `test` `completed success` +
job `package` `completed success`; run `completed success`. Workflow
canónico `.github/workflows/ci.yml` sin bypasses. E02/E03/E04 y el resto
de la suite completa corrieron dentro de este run.

## 8. Criterios de aceptación (§31 del prompt)

- [x] baseline certificado inspeccionado (subagentes: unidades, P5, traza)
- [x] capacidades existentes reutilizadas (math/units/traza/errores/P5 intacto)
- [x] motor único (`f16-orbital/1`, fórmulas en un solo lugar)
- [x] modelo gravitacional determinista + provenance
- [x] órbita circular / periodo / velocidad / vis-viva / energía / escape
- [x] elipses ligadas + Kepler + elementos con marcos documentados
- [x] unidades verificadas (MASS/FORCE, conversiones explícitas)
- [x] dominios validados, precisión definida (50 dígitos, tols explícitas)
- [x] errores explícitos (INVALID/MAX_ITERATIONS, sin clamps)
- [x] ExecutionTrace integrado (`physics.orbital` + replay + ExplainService)
- [x] serialización determinista (`f16-elements/1` + digest)
- [x] sin duplicación Assessment/Knowledge (sin cambios F9/D7)
- [x] tests F16 verdes (16/16 local)
- [x] regresión relevante verde (salvo preexistente CRLF documentado)
- [x] seguridad verificada (test AST verde)
- [x] documentación (F16-AEROSPACE + ERROR-CODES sin cambios + este gate)
- [x] CI real verde (run 36394085024, 4/4 celdas + package)
- [x] roadmap actualizado (F16 CERTIFICADA, ROADMAP COMPLETADO)
- [x] F16 CERTIFICADA

## 9. Veredicto

**Veredicto: F16 CERTIFICADA. ROADMAP COMPLETADO.** F16 cierra
AcademicCore: F0→F13 CERTIFICADAS, F14 ELIMINADA, F15 CERTIFICADA,
F16 CERTIFICADA. Límites reales en §6 de `F16-AEROSPACE.md` (two-body
puro, sin TLE, marcos etiquetados sin transformar).
