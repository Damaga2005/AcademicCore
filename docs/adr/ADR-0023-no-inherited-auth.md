# ADR-0023 — Gestion authentication is not inherited (F4.1)

Date: 2026-09-23 · Status: Accepted

## Decision
Gestion's lock-key/CSRF/cookie gate protected a Flask server on the LAN.
AcademicCore is a local PySide6 app with no HTTP surface; that code and its
secrets (`GREELEC_LOCK_KEY`, `FLASK_SECRET_KEY`) are neither ported nor
migrated. The existing `application/security.py::AppLock` remains the local
lock. Multi-user or network access would need a new ADR.
