# ADR-0001 — UI Technology: PySide6 / Qt

Date: 2026-09-12 · Status: Accepted (Phase 0)

## Context
Windows-native desktop, years of growth, Python-heavy legacy (Flask/Tk/stdlib),
SPICE/LaTeX/PDF/external processes, 16 GB RAM, RTX 2060 optional. Candidates:
PySide6/Qt, .NET WPF, .NET WinUI, Tauri.

## Decision
**PySide6 (Qt 6, LGPL) as UI layer**, Python for application/domain/engines.

## Rationale
- Reuses existing Python capital (audit: 132-file Sistemes app, Flask models,
  BS4/lxml/mathml2latex/genanki pipelines) without a language rewrite.
- Qt gives real Windows-native integration: filesystem, drag&drop, clipboard,
  file associations, multi-window, tabs, dockable panels, DPI/multi-monitor,
  notifications, printing, background workers (QThread/QProcess).
- Graphics path (2D schematics now, 3D later via Qt3D/QtQuick) covers CAD/Bode/
  Smith evolution; WebGL lab HTML can be hosted in QtWebEngine during transition.
- Packaging: PyInstaller + installer/updater (existing build.ps1/.spec precedent).
- .NET options would force a full Python→C# rewrite of the audited engines with
  no compensating advantage; Tauri adds a web-first inversion the brief forbids
  ("no diseñar primero una web app").

## Consequences
- UI code lives only in `src/academic_core/app.py` (+ future `ui/`); domain and
  engines MUST NOT import PySide6 (enforced by `test_architecture.py`).
- LGPL compliance: dynamic linking, document in release notes.
- GPU stays optional; Qt renders fine on CPU/iGPU.
