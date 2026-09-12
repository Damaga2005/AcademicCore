# Roadmap (post Fase 0 — orden ajustable según evidencia)

- Phase 0 — Audit & Architecture ✅ (this release: skeleton + 10 ADRs + gates)
- Phase 1 — Domain & Identity: ORM/migrations, seed genérico (no GREELEC),
  grading (componentes/esquemas/bloques), staff/timetable/tasks portados.
- Phase 2 — Resource Engine: adapters pdf/html/md/latex/docx/pptx/image/csv/
  json/zip/dataset + batch + incremental index (FTS5 + TF-IDF + RRF).
- Phase 3 — Document & PDF Engine: AST converters, MathML→LaTeX, export
  HTML/PDF/exam-booklet; Stirling sidecar benchmark (merge/split/OCR).
- Phase 4 — Academic Management: dashboard, docs library + pdf.js, bookmarks,
  anotaciones, search Ctrl+K, external links, backup/restore, notifications.
- Phase 5 — Authoring: apuntes/informes/prácticas/memorias, plantillas,
  biblio/citas, build LaTeX→PDF, embed de formulas/circuits/sims.
- Phase 6 — Engineering Core: Circuit canónico + SPICE/KiCad/CircuitTikZ/SVG.
- Phase 7 — Simulation: DC/AC/transient/OP/sweep/Monte Carlo/noise/FFT vía
  backends externos + MNA reescrito con tests.
- Phase 8 — Laboratory & Measurement: experimentos, instrumentos virtuales
  (DSO/DMM/AFG/PSU), GUM + Monte Carlo, datasets reales vs simulados.
- Phase 9 — Assessment & Learning: bancos, examiner verificado, grading
  Decimal, correction, adaptive/mastery/spaced, flashcards Anki.
- Phase 10 — AI/Ollama: Model Manager/Detection/Benchmark, router
  evidence-gated, Qwen/Gemma/Llama bench, Gemini opt-in.
- Phase 11 — OneDrive & Integrations: provider read-only → sync seguro.
- Phase 12 — Sistemes-de-Mesura migration: gate 100% fórmulas + curation
  units/variables/conditions.
- Phase 13 — Packaging/Installer/Release: PyInstaller, installer, updater,
  firma, release notes con estados de certificación.

Gate entre fases: planificar → implementar → probar → auditar → documentar →
verificar → presentar → esperar autorización.
