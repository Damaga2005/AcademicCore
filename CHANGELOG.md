# Changelog

## 0.1.0 — Fase 0 foundation (2026-09-12)
- Audits: Conversor (monolito 6.051 lín + lab 16 módulos), Gestion (Flask,
  28 tablas, 152 rutas, 672 docs), Sistemes (91 fuentes, 2896 fórmulas,
  1092 tests) — full detail in `docs/migration/`.
- Architecture: modular monolith, 10 ADRs, domain v0, stable IDs, storage
  SQLite+CAS, engines interfaces (resource/document/pdf/ai/providers/
  engineering), Qt skeleton executable, config system, 6 test files.
- Gates: fast suite + migration contract + reproducibility + boundary test.
