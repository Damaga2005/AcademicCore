# CI / Pipeline D4

> **Pipeline canónico:** `.github/workflows/ci.yml` (único workflow; no fragmentar).

## Qué ejecuta

```text
checkout -> setup Python -> pip install -r requirements-lock.txt
  -> pip install -e . --no-deps -> python -m compileall -q src
  -> pytest -m "not external" -q
  -> (job package, solo si test está verde) pip install build
  -> python -m build -> verifica sdist+wheel -> sube dist/
```

- Matriz `test`: `windows-latest × ubuntu-latest` × Python `3.12, 3.13`.
  El rango soportado es `>=3.11,<3.15` (`pyproject.toml`, badge README
  3.11–3.14); CI muestrea 3.12/3.13 y el resto sigue siendo instalable.
  D5 podrá ampliar la matriz.
- `fail-fast: true`, `timeout-minutes: 60` (la suite incluye tests `slow`
  por diseño), `permissions: contents: read`, sin secretos.
- Única exclusión: `-m "not external"` (runtimes vivos como Stirling/Java
  nunca bloquean el gate; ver `docs/testing/STRATEGY.md`). Sin `|| true`,
  sin `continue-on-error`, sin `--deselect`, sin `exit 0`.

## Cuándo se ejecuta

`push` a `main` y `pull_request` hacia `main`. `main` es la única línea
canónica. Este repo no configura branch protection desde aquí; la
comprobación exigible antes de consolidar es el job `test` en verde.

## Reproducir localmente

```powershell
pip install -r requirements-lock.txt
pip install -e . --no-deps
python -m compileall -q src
$env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONPATH='src'
python -m pytest -m "not external" -q
python -m build  # en venv limpio con `pip install build`
```

Bucle rápido (estrategia del proyecto): `pytest -m "not migration"`.

## Qué significa un fallo

- `AssertionError` / `ImportError` / fallo de test o de build → fallo de
  código: CI rojo, corregir antes de consolidar.
- El test `test_document_symlink_escape_refused` requiere privilegio de
  symlinks del SO (`WinError 1314` sin modo desarrollador): limitación
  ambiental conocida, preexistente en local; si un runner la reproduce,
  es entorno, no regresión (ver gate D4).

## Artefactos

`dist/*.tar.gz` + `dist/*.whl` como artefacto `academic-core-dist` del job
`package`. Los tests usan `tmp_path`; no contaminan el árbol (ver
`test_no_unwanted_artifacts_in_worktree`).

## Fuera de D4 (corresponde a D5+)

Consolidación de la suite global, cobertura, ampliación de matriz,
lint/type-check dedicados, branch protection, publicación de artefactos.
