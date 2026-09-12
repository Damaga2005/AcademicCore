# ADR-0002 — Modular Monolith (not microservices, not big ball of mud)

Date: 2026-09-12 · Status: Accepted

## Decision
Single deployable **modular monolith** with hard boundaries:
`ui → application → domain ← engines (academic/engineering/simulation/document/ai/data)`,
`data → storage`, `integrations` behind provider adapters.

## Rationale
Audit shows the failure mode to avoid: 6.051-line single-file Tk app (Conversor)
vs 132-file stdlib app (Sistemes). Both work solo; neither scales to multi-subject.
Microservices would add network/ops cost for zero benefit on a single-user desktop
with 16 GB RAM. Modular monolith lets modules graduate to separate processes
(QProcess for SPICE/LaTeX/Stirling/Ollama) without a rewrite.

## Consequences
- Boundary test `test_architecture.py` blocks Qt/app imports in core.
- Cross-module calls go through typed interfaces (`engines/*`, `providers`).
- Future split points documented in `docs/architecture/MODULES.md`.
