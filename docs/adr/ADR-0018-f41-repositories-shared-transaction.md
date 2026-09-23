# ADR-0018 — F4.1 repositories with an optional shared transaction

Date: 2026-09-23 · Status: Accepted

## Context
ADR-0012 forbids an ORM; F1 repositories open one connection per call.
The Gestion migration must write thousands of rows all-or-nothing.

## Decision
F4.1 repositories (`infrastructure/academic_store.py`) accept an optional
open connection `cx`; without it each call is its own `BEGIN IMMEDIATE`
unit. `TargetWriter` binds hierarchy/people/task rows to one transaction.
Reads always use explicit `ORDER BY` on stable keys. SQL is parameterized;
the only interpolation is a `?` placeholder list (AST-tested).

## Consequence
Migrations and multi-step use cases are atomic; F1 repository behaviour is
unchanged (subject/task/professor mapping moved to named columns).
