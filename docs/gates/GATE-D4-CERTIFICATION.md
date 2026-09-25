# GATE-D4-CERTIFICATION — D4 Pipeline CI/build

> **FASE:** D4 — Pipeline CI/build. **BASELINE:** `main @ abf49ed`
> (`feat(f13ext)... CERTIFIED`); sin workflows previos (verificado:
> no existía `.github/workflows`). **Rama:** `main`, sin líneas paralelas.

## 1. Implementación

| | |
|---|---|
| workflow | `.github/workflows/ci.yml` (único; jobs `test` + `package`) |
| triggers | `push` a `main`, `pull_request` hacia `main` |
| matriz `test` | `windows-latest × ubuntu-latest` × Python `3.12, 3.13` (`fail-fast`, timeout 60 min) |
| install | `pip install -r requirements-lock.txt` (pineado `==`) + `pip install -e . --no-deps` |
| checks | `python -m compileall -q src` → `pytest -m "not external" -q` (sin bypasses) |
| package | solo si `test` verde (`needs`): `pip install build` → `python -m build` → verifica sdist+wheel → artefacto `academic-core-dist` |
| tests D4 | `tests/test_d4_pipeline.py` (7 tests, solo stdlib, sin red) |
| docs | `docs/testing/CI.md` |

Sin dependencias de producto nuevas (`build` solo vive en el runner).
Sin `eval/exec/subprocess/shell` en el workflow (todo `run:` es un comando
fijo del repo). Sin secretos (`permissions: contents: read`).

## 2. Evidencia fresca (local, 2026-09-25)

```text
HEAD: abf49ed | Python 3.14.6 (rango soportado >=3.11,<3.15) | OS: Windows 10/11 local
BASELINE previo (sin cambios D4): test_f13ext_sync+architecture+persistence+migration → 39 passed
```

| Comando | Resultado |
|---|---|
| `pytest tests/test_d4_pipeline.py` | 7 passed (triggers, sin bypasses, lock pineado, pytest ejecuta, fallo→rc!=0, compileall+build declarado, sin artefactos) |
| regresión `d4+f13ext+arch+persist+migration+f42sec+f4mgmt` | 58 passed |
| build real aislado (`venv` en TEMP + `pip install build` + `python -m build`) | `academic_core-0.1.0.tar.gz` (1 399 720 B) + `.whl` (1 007 374 B) |
| `git status` tras build | limpio salvo `.github/` + test nuevo (sin egg-info/dist en el árbol) |

## 3. No regresión

Solo ficheros nuevos (`.github/`, `test_d4_pipeline.py`, `CI.md`, este gate)
más CHANGELOG. Cero toques a F13-ext/F15/F4.2/motores/persistencia/gates.
`test_document_symlink_escape_refused` (`WinError 1314`) es ambiental y
preexistente en baseline (falla con y sin D4); documentado en `CI.md`.

## 4. Criterios de aceptación (§19)

- [x] CI implementado en el repo (único `ci.yml`)
- [x] triggers push/PR sobre `main`
- [x] instalación reproducible (lock `==`, verificado por test)
- [x] suite válida ejecutada realmente (local; comando idéntico al de CI)
- [x] fallos hacen fallar (fail-detection probado, `fail-fast`, sin bypasses)
- [x] F13-ext verde (12/12) y regresiones críticas verdes (58)
- [x] build verificado de verdad (sdist+wheel en venv aislado)
- [x] sin dependencias innecesarias ni contratos tocados
- [x] documentación reproducible (`docs/testing/CI.md`)
- [x] este gate
- [ ] **evidencia de ejecución real en el proveedor CI** — imposible desde
  esta máquina (sin `gh`, sin credenciales de push; §15 prohíbe afirmar lo
  no ejecutado). Al hacer push, GitHub Actions ejecutará el workflow; con
  el run en verde se marca el criterio y el roadmap.

## 5. Veredicto

**D4 IMPLEMENTADA, PENDIENTE DE RUN REAL EN CI.** No certificada todavía
por criterio explícito del prompt (§15/§19). Roadmap queda en
`D4 SIGUIENTE` → pasará a `CERTIFICADA` (y `D5 SIGUIENTE`) cuando el primer
run del proveedor esté verde. Para cerrar: push a `origin/main` →
Actions → run verde → actualizar §4 y roadmap en commit aparte.
