# F9-D — ASSESSMENT PERSISTENCE & HARDENING AUDIT GATE (SEALED)

**Subsystem:** F9 — Assessment / Evaluation
**Phase:** F9-D (Master Hardening & Final Seal)
**Repository:** `Damaga2005/AcademicCore` (`academic_core`)
**Status:** SEALED (AUDITED & CERTIFIED, ZERO REGRESSION, F8 UNTOUCHED)
**Date:** September 2026

---

## 1. Scope

Phase F9-D provides persistent storage, transactional integrity, process-restart recovery, and concurrency safety for the summative assessment subsystem in `academic_core`.

The subsystem manages four core entities:
1. `Assessment`: Multi-item examination specification aggregate with grading policy, timing, and deterministic shuffle settings.
2. `AssessmentSession`: Examination lifecycle state machine (NOT_STARTED -> IN_PROGRESS -> SUBMITTED / EXPIRED / CANCELLED).
3. `StudentResponse`: Immutable answers submitted for assessment items.
4. `AssessmentResult`: Immutable graded verdict, itemized Decimal scores, and pass/fail determination.

---

## 2. Schema & Storage Architecture

* **Database Engine**: Single SQLite database managed by `Database` with:
  * `PRAGMA foreign_keys = ON;`
  * `PRAGMA journal_mode = WAL;` (Write-Ahead Logging for non-blocking concurrent reads/writes)
  * `PRAGMA busy_timeout = 10000;` (10s lock wait for concurrent transactions)
* **Migration 011 (`011_assessment.sql`)**:
  * Tables: `assessments`, `assessment_sessions`, `assessment_responses`, `assessment_results`, `id_counters`.
  * Indexes: `idx_assessments_subject`, `idx_sessions_assessment`, `idx_sessions_student`.
  * Exact Decimal representation stored as `TEXT`. Zero float storage.
  * Explicit database engine triggers:
    * `trg_prevent_response_on_terminal_session`: `BEFORE INSERT ON assessment_responses` raises `ABORT` if session status is terminal (`SUBMITTED`, `EXPIRED`, `CANCELLED`).
    * `trg_response_immutable`: `BEFORE UPDATE ON assessment_responses` raises `ABORT` preventing mutation of stored responses.
    * `trg_result_immutable`: `BEFORE UPDATE ON assessment_results` raises `ABORT` preventing mutation of stored results.

---

## 3. Transaction Model & TOCTOU Elimination

* **Transaction Context Manager (`AssessmentRepository._tx`)**:
  * Connections set `cx.isolation_level = None` (manual autocommit mode).
  * Write operations execute `BEGIN IMMEDIATE`, instantly acquiring SQLite's `RESERVED` lock before reading or modifying state.
  * Complete atomic rollback on any exception: `except Exception: cx.execute("ROLLBACK"); raise`.
* **TOCTOU Elimination Pattern**:
  ```text
  Client Call
    ↓
  BEGIN IMMEDIATE (acquires RESERVED lock)
    ↓
  SELECT session.status
    ↓
  Validation (reject if terminal status)
    ↓
  INSERT / UPDATE statement (guarded by DB triggers)
    ↓
  COMMIT (releases lock)
  ```
  This serialization guarantees that no two concurrent connections can race between reading session status and writing answers or finalizing sessions.

---

## 4. Persistent ID Allocation Contract

* **Mechanism**: Persisted in SQLite `id_counters` table using atomic upsert:
  ```sql
  INSERT INTO id_counters (kind, last_n) VALUES (?, 1)
  ON CONFLICT(kind) DO UPDATE SET last_n = last_n + 1
  RETURNING last_n;
  ```
* **Identity Properties**:
  * **Atomicity**: [IMPLEMENTED + TESTED] Single SQL upsert with `RETURNING`.
  * **Uniqueness**: [IMPLEMENTED + TESTED] Monotonically incremented integer mapped via `IdAllocator`.
  * **Restart Safety**: [IMPLEMENTED + TESTED] Counters survive process death and database reconnection.
  * **Multi-Process / Multi-Thread Safety**: [IMPLEMENTED + TESTED] Tested across N=10, 50, 100 concurrent worker connections.
  * **Subject Scope**: Formatted as `<kind>:<subject>:sess:NNNNN`.
  * **Rollback & Gap Semantics**: **NOT gapless**. When an ID is allocated and subsequent domain validation fails before aggregate persistence, the allocated sequence number is consumed and skipped. Tested in `test_id_allocation_contract_unique_monotonic_not_gapless`.

---

## 5. Session Lifecycle & State Transitions

* **Valid Lifecycle Transitions**:
  * `NOT_STARTED` -> `IN_PROGRESS`
  * `NOT_STARTED` -> `CANCELLED`
  * `IN_PROGRESS` -> `SUBMITTED`
  * `IN_PROGRESS` -> `EXPIRED`
  * `IN_PROGRESS` -> `CANCELLED`
* **Terminal Immutability**:
  * `SUBMITTED`, `EXPIRED`, `CANCELLED` are terminal sink states.
  * Reversion to `IN_PROGRESS` is rejected with `IntegrityError`.
  * Transition between terminal states (e.g. `SUBMITTED` -> `EXPIRED`) is rejected with `IntegrityError`.
  * Late responses attempted on terminal sessions are rejected at both application layer (`IntegrityError`) and database engine level (`trg_prevent_response_on_terminal_session`).

---

## 6. Response & Result Immutability

* **Response Immutability**:
  * If item not yet answered: inserted.
  * If item answered with identical value: idempotent no-op, preserving original `submitted_at`.
  * If item answered with different value: raises `IntegrityError("Immutable response conflict...")`.
  * Database-level trigger `trg_response_immutable` blocks direct SQL updates.
* **Result Immutability**:
  * Compares all persisted attributes: `assessment_id`, `student_id`, `total_score`, `max_possible`, `percentage`, `passed`, `item_scores_json`, `evaluated_at`.
  * Identical re-save: idempotent no-op.
  * Divergent re-save: raises `IntegrityError("AssessmentResult ... is immutable")`.
  * Database-level trigger `trg_result_immutable` blocks direct SQL updates.

---

## 7. Concurrency Guarantees

All concurrency scenarios tested using independent SQLite database connections:
* **Case A — Duplicate Creation**: Two writers inserting the same assessment/session ID -> exactly one succeeds; the second receives a controlled `IntegrityError`; 0 duplicates; DB consistent.
* **Case B — Same Response**: Two connections saving the identical answer simultaneously -> exactly one persisted; no corruption.
* **Case C (CRITICAL) — Submit vs Response Race**: Concurrent `submit_session()` vs `save_response()`. Due to `BEGIN IMMEDIATE` and database triggers, a late response is rejected with `IntegrityError`; session remains `SUBMITTED` with zero late answers accepted.
* **Case D — Concurrent Results**: Concurrent `save_result(A)` vs `save_result(B)` -> winner persists; conflictive loser receives `IntegrityError`; identical loser succeeds idempotently.
* **Repeated Stress**: Scaled across N=10, 50, 100 concurrent workers without lockups or ID collisions.

---

## 8. Robust Corruption Handling

All corruption variants raise `academic_core.infrastructure.repositories.IntegrityError` without crashing or leaking unhandled internal exceptions:

| Corruption Vector | Input Condition | Exception Raised | DB State Unchanged |
| :--- | :--- | :--- | :---: |
| **Invalid Decimal** | Non-numeric weight string in `items_json` | `IntegrityError` | Yes |
| **Invalid Timestamp** | Malformed ISO string (`'not-a-date'`) in session row | `IntegrityError` | Yes |
| **Invalid JSON** | Unclosed JSON syntax in `policy_json` / `items_json` | `IntegrityError` | Yes |
| **Invalid Session Status** | Unknown enum string (`'BOGUS_STATUS'`) | `IntegrityError` | Yes |
| **Invalid ID Syntax** | Non-conforming stable_id grammar | `IntegrityError` | Yes |
| **Invalid Policy** | Inverted grading scale (low > high) | `IntegrityError` | Yes |
| **Missing Required Value** | Empty student_id / NULL in NOT NULL column | `IntegrityError` | Yes |
| **Invalid Foreign Key** | Session pointing to non-existent assessment | `IntegrityError` | Yes |
| **Inconsistent Response** | Response pointing to non-existent session | `IntegrityError` | Yes |
| **Inconsistent Result** | Result pointing to non-existent session | `IntegrityError` | Yes |
| **Schema Incompatibility** | Table missing or incomplete | `IntegrityError` / `Exception` | Yes |
| **Unsupported Schema Version** | Schema marked with future version (999) | Handled safely | Yes |
| **Malformed item_order** | Non-list JSON in `item_order_json` | `IntegrityError` | Yes |
| **Malformed item_scores** | Non-dict JSON in `item_scores_json` | `IntegrityError` | Yes |

---

## 9. Formula Provenance Boundary (Section 2 & I15)

In accordance with Rule 0.2 and Section 2, `Formula -> AssessmentItem` is an evaluation adapter, **not** a full persistence mechanism for `Formula`.

| Formula Field | Persisted Directly | Transformed | Lost Deliberately | Recoverable After Restart | Source of Truth |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `stable_id` | Yes (as `question_id`) | No | No | Yes | `assessments.items_json` |
| `latex` | Yes (as `options[0]`) | No | No | Yes | `assessments.items_json` |
| `source_latex` | Yes (as `options[1]`) | No | No | Yes | `assessments.items_json` |
| `topic_id` | Yes | No | No | Yes | `assessments.items_json` |
| `provenance` | No | Yes (`formula_prov:<path>#<section>`) | Hash | Partial | `AssessmentItem.rubric_ref` |
| `variables` | No | No | Yes | No | Out of scope (Study doc) |
| `units` | No | No | Yes | No | Out of scope (Study doc) |
| `concept_ids` | No | No | Yes | No | Out of scope (Study doc) |
| `version` | No | No | Yes | No | Out of scope (Study doc) |

No artificial `FormulaRegistry` is invented. Formula domain aggregates belong to Phase 0/1 study notes. `AssessmentItem` cleanly references formulas by `question_id` and provenance rubric reference.

---

## 10. Decimal & Timestamp Fidelity

* **Decimal Fidelity**:
  * Exact Decimal equality verified for difficult values: `Decimal("0")`, `Decimal("1")`, `Decimal("-1")`, `Decimal("0.1")`, `Decimal("0.000000001")`, `Decimal("12345678901234567890.123456789")`, `Decimal("-12345678901234567890.123456789")`.
  * Zero `float()` calls in entire persistence path (AST verified).
* **Timestamp Semantics**:
  * Full ISO-8601 strings with timezone awareness (UTC and non-UTC offsets preserved).
  * Microsecond precision verified (123456 us round-trip preserved).

---

## 11. Determinism & Idempotency

* **Deterministic Ordering**: `Assessment.generate_item_order(seed)` guarantees identical permutation for identical inputs.
* **Stable Persistence**: Recovered `item_order` tuple is byte-for-byte identical to original session order.
* **Deterministic JSON**: `_serialize_items`, `_serialize_policy`, `item_order_json`, and `item_scores_json` use `sort_keys=True, separators=(',', ':')` for canonical byte-for-byte serialization.
* **Idempotency**: Repeated saves of identical assessments, sessions, responses, and results produce no duplicates, no timestamp alterations, and no ID shifts.

---

## 12. Test Evidence Summary

* **`tests/test_f9d_assessment_persistence.py`**: **49 passed** in 31.84s.
  * Persistence round-trips: Assessment, Session, Response, Result.
  * 18-step full restart recovery scenario.
  * Real multi-connection concurrency (Cases A, B, C, D).
  * Repeated concurrency stress tests (N=10, 50, 100).
  * Multi-step atomicity failure injection (complete rollback).
  * 14 corruption handling cases.
  * AST security audit (zero `eval`, `exec`, `compile`, or `float`).
* **All Regression Gates (666 passed)**:
  * F8-B, F8-C, F8-E, F8-F, F8-G, F8-H, F8-I: 100% PASS.
  * F8-J Small-Signal AC: **29 passed** (100% byte-for-byte match).
  * F9-B Domain Assessment: 11 passed.
  * F9-C Assessment Orchestration: 11 passed.
  * Persistence, IDs, Architecture: 16 passed.

---

## 13. Known Boundaries

1. **ID Allocation Rollback Gaps**: Sequence numbers allocated during an aborted transaction are consumed and skipped; IDs are monotonic and unique, but not gapless.
2. **Formula Variables/Units**: Not persisted inside `AssessmentItem` by architectural design (Rule 0.2); evaluation relies on rendered LaTeX options and topic references.
3. **Forward Schema Compatibility**: Opening a future schema (version > 11) connects without applying downgrade migrations; F9-D guarantees backward compatibility, not arbitrary forward compatibility.

---

## 14. Gate Certification Decision

### **GATE DECISION: SEALED**

Phase F9-D fulfills all 15 invariants (I1–I15), passes adversarial multi-connection concurrency audits, guarantees complete atomicity and corruption detection, preserves Decimal/timestamp fidelity, and leaves F8 100% byte-for-byte intact.
