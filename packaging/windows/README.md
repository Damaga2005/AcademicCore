# SPDX-License-Identifier: MIT
# Windows product packaging

Builds `AcademicCore.exe` (PyInstaller onedir) + `AcademicCore-1.0.0-Setup.exe`
(NSIS) from the certified codebase. No code changes required to rebuild.

## Prerrequisitos

- Python 3.12+ con `pip install -r requirements-lock.txt` + `pyinstaller`.
- NSIS 3 (`winget install --exact --id NSIS.NSIS`).

## Build local

```powershell
python -m PyInstaller --noconfirm --clean packaging/windows/academicore.spec
& "C:\Program Files (x86)\NSIS\makensis.exe" packaging/windows/installer.nsi
```

Artefactos (ignorados por git, ver `.gitignore`):

```text
dist/AcademicCore/AcademicCore.exe   # onedir, ~180 MB con Qt
dist/AcademicCore-1.0.0-Setup.exe    # instalador, ~72 MB
```

**Importante:** `tests/test_d4_pipeline.py::test_no_unwanted_artifacts_in_worktree`
exige que `dist/` y `build/` no existan en el árbol. Tras extraer los
artefactos, eliminarlos:

```powershell
Remove-Item -Recurse -Force dist, build
```

## Decisiones

- **PyInstaller onedir** (no one-file): arranque más rápido, updates por
  ficheros, precedente en ADR-0001. Nuitka descartado: compila C (CI lento,
  frágil con plugins Qt).
- **NSIS 3 + MUI2**: instalador moderno sin estética antigua; registra
  desinstalación en HKLM y entrada en Start Menu.
- **Versión única**: `src/academic_core/__init__.py::__version__`
  → `pyproject.toml` → `version_info.txt` → `installer.nsi`
  (pineado por `tests/test_windows_runtime.py` y `test_product_installer.py`).
- **Datos de usuario**: `%LOCALAPPDATA%/AcademicCore` solo en bundle
  (`academic_core/runtime.py`); en dev todo sigue en `~/.academic-core`.
- **Updater automático**: fuera de alcance (limitación documentada).
  La app muestra su versión en About/Settings; el update es descargar el
  nuevo Setup y reinstalar.

## Validación (runs CI + smoke local)

- CI `release`: build exe + installer + smoke offscreen (DB verificada) +
  artifact `AcademicCore-Setup` — verde en runs `36416322476`,
  `36443350048`, `36449517250`.
- Smoke local: `.exe` vivo 20 s, `academic.db` + migraciones 001–021 en
  `%LOCALAPPDATA%/AcademicCore` aislado.
- SHA-256 del Setup reconstruido del árbol final:
  `359084474C65928F57CFFB963198E3BF039205E8757325D79EFCC31AE474C3F1`.
- NOT VERIFIED (sin admin ni 2ª máquina): Start Menu, ejecución del
  uninstall, clean machine, DPI 125/150/200 sistemático.
