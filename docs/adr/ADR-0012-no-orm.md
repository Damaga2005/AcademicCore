# ADR-0012 — Persistence without ORM: stdlib sqlite3 + explicit repositories

Date: 2026-09-12 · Status: Accepted

## Context
Brief allows SQLAlchemy but requires it confined to infrastructure and absent
from Domain. Single-user desktop, modest relational model, zero new runtime
dependencies preferred.

## Decision
No ORM at all: `Database` (migrations runner) + hand-written repositories
mapping rows ↔ domain dataclasses. Migrations are small, forward-only, one
concern per file (`001_academic` … `004_study`).

## Consequence
Gate "Domain has no SQLAlchemy" holds trivially and is enforced by test.
Cost: more manual SQL; acceptable at this schema size. Revisit only if the
model outgrows hand mapping (a future ADR, not a silent drift).
