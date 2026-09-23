# ADR-0017 — Subject-centred academic model and status classification (F4.1)

Date: 2026-09-23 · Status: Accepted

## Context
Gestion-Academica keeps five subject states (`cursando/superada/no_superada/
pendiente/no_elegida`); F4.1 requires four product statuses
(CURSANDO/APROBADA/SUSPENDIDA/NO_CURSANDO) for Home and Carrera, one entity
per subject, and no data loss.

## Decision
- `Subject.state` keeps the fine five-value vocabulary (persisted as is).
- `domain/career.py::classify` maps it to `AcademicStatus`; `pendiente`
  and `no_elegida` both classify NO_CURSANDO but stay distinguishable.
- Views are partitions of the SAME entities: Home = CURSANDO subjects of
  the terms flagged `actual` (several may be current); Carrera = current /
  in progress elsewhere / approved / failed / not taken / not chosen.
- Status change updates the same stable id in place (idempotent).
- Gestion parity fields on Subject are additive with defaults (final grade
  override, catalogue origin, scheme rule, notes, classroom URL, `extra`
  JSON for lossless legacy metadata).

## Consequence
No duplicated subjects; a subject that passes simply leaves the "current"
view. New F4.1 stable-id kinds (scheme/block/component/link/docgroup/series/
space, milestone/note) follow the ADR-0010 grammar.
