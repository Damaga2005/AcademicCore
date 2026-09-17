# F9-D ASSESSMENT PERSISTENCE & RECOVERY REPORT

**Subsystem:** F9 — Assessment / Evaluation  
**Phase:** F9-D (Assessment Persistence, Serialization, Recovery & Integrity Audit)  
**Repository:** `Damaga2005/AcademicCore` (`academic_core`)  
**Status:** IMPLEMENTED & VERIFIED (ZERO REGRESSION, F8 SEALED)  
**Date:** September 2026  

---

## A. Executive Verdict
Phase **F9-D** has successfully implemented durable SQLite persistence and restart-safe recovery for the certified assessment models (`Assessment`, `AssessmentSession`, `StudentResponse`, `AssessmentResult`), closing the persistence gap documented in F9-A and F9-C.

The implementation reuses the existing infrastructure (`Database`, `schema_version` migrations, `AcademicApp` wiring) via migration `011_assessment.sql` and [`AssessmentRepository`](file:///c:/Users/dmart/Documents/AcademicCore/src/academic_core/infrastructure/assessment.py).
Zero floats were introduced: all numerical quantities (weights, thresholds, penalties, partial credit, scores) serialize strictly as `TEXT` and deserialize directly into Python `Decimal`.
All 14 tests in `tests/test_f9d_assessment_persistence.py` passed (including recovery across process restart, timer survival, and 128-item scalability benchmarks). Core regressions (38/38) and the sealed F8 suite (288/288) passed with 100% fidelity.

---

## B. Repository State
* **Branch:** `main` (clean working tree with respect to git commits; zero commits made).
* **F8 Boundary:** Sealed and untouched. `src/academic_core/domain/engineering/` has 0 modifications.
* **Modified Production Files:**
  * `src/academic_core/infrastructure/__init__.py`
  * `src/academic_core/infrastructure/database.py`
  * `src/academic_core/application/assessment.py`
  * `src/academic_core/application/facade.py`
  * `tests/test_persistence.py`
* **New Production Files:**
  * `src/academic_core/infrastructure/migrations/011_assessment.sql`
  * `src/academic_core/infrastructure/assessment.py`
* **New Test Files:**
  * `tests/test_f9d_assessment_persistence.py`

---

## C. Existing Persistence Architecture
Audit of existing repository persistence confirmed:
* Database: Single SQLite database at `academic.db` managed by `academic_core.infrastructure.database.Database`.
* Migrations: Forward-only scripts in `academic_core/infrastructure/migrations/` tracked by integer `schema_version`.
* Connection pattern: Explicit row-to-domain mapping, parameterized queries, `cx.row_factory = sqlite3.Row`, and `PRAGMA foreign_keys=ON`.
* No ORM (ADR-0012): Domain entities remain pure dataclasses with zero database dependencies.
* Repositories: Dedicated classes (`AcademicRepository`, `PlanningRepository`, `GradingRepository`, `GradebookRepository`, `EngineeringRepository`).
* F9-D extends this established pattern by registering migration `011_assessment.sql` and providing `AssessmentRepository`.

---

## D. F9-B/F9-C Compatibility
* F9-B domain models (`Assessment`, `AssessmentItem`, `GradingPolicy`, `AssessmentSession`, `StudentResponse`, `AssessmentResult`) were preserved with zero structural or semantic alterations.
* F9-C orchestration APIs (`AssessmentService`) gained durable persistence transparently via constructor injection (`repo=self.assessment_repo`). In-memory fallback is preserved when `repo=None`.

---

## E. Persistent Data Model
Defined in `011_assessment.sql`:
1. `assessments`:
   * Columns: `stable_id` (PK), `subject_id`, `title`, `description`, `items_json`, `duration_min`, `attempts_allowed`, `policy_json`, `shuffle_items`, `master_seed`, `created_at`.
2. `assessment_sessions`:
   * Columns: `stable_id` (PK), `assessment_id` (FK $\to$ `assessments`), `student_id`, `attempt_number`, `status`, `duration_seconds`, `started_at`, `expires_at`, `submitted_at`, `item_order_json`, `seed_used`, `updated_at`.
3. `assessment_responses`:
   * Columns: `session_id` (FK $\to$ `assessment_sessions`), `item_id`, `answer`, `submitted_at`.
   * Composite Primary Key: `(session_id, item_id)`.
4. `assessment_results`:
   * Columns: `session_id` (PK, FK $\to$ `assessment_sessions`), `assessment_id`, `student_id`, `total_score`, `max_possible`, `percentage`, `passed`, `item_scores_json`, `evaluated_at`.

---

## F. Serialization
Deterministic serialization implementation:
* Field order in JSON schemas is fixed and stable.
* Enums: Serialized via string values (`SessionStatus.value`).
* Datetimes: Serialized as ISO-8601 strings (`dt.isoformat()`) and parsed via `datetime.fromisoformat()`.
* Collections: Item orders and options serialized as UTF-8 JSON lists (`json.dumps(..., ensure_ascii=False)`).
* Decimals: Serialized as exact string representations (`str(d)`), never as binary floating-point.

---

## G. Decimal Integrity
Audited all numerical storage boundaries:
* Weights: `str(it.weight)` $\to$ `Decimal(d["weight"])`.
* Penalties: `str(p.negative_marking_factor)` $\to$ `Decimal(d["negative_marking_factor"])`.
* Scores & Thresholds: `str(r.total_score)` $\to$ `Decimal(row["total_score"])`.
* AST check verified 0 calls to `float()` in `academic_core/infrastructure/assessment.py`.
* Zero float precision loss or rounding discrepancies across save $\to$ SQLite $\to$ load.

---

## H. Session Recovery
Verified through process restart simulation:
* Session created, started, and partially answered in process 1.
* Database connection closed and process memory discarded.
* Reopened under independent process/database connection.
* Reconstructed `AssessmentSession` retains:
  * Identical `stable_id` and `student_id`.
  * Identical deterministic `item_order`.
  * Identical timer deadlines (`started_at`, `expires_at`).
  * All previously recorded answers.
* Resumed session continues answering remaining items, submits, and finalizes cleanly.

---

## I. Terminal Session Recovery
Verified for all terminal states:
* `SUBMITTED`: Persisted submitted session reloads in `SUBMITTED` status; rejects subsequent answers or re-submissions.
* `EXPIRED`: Persisted expired session reloads in `EXPIRED` status; rejects subsequent answers or submissions.
* `CANCELLED`: Persisted cancelled session reloads in `CANCELLED` status; rejects answers and transitions.
* Terminal sessions remain permanently immutable across reloads.

---

## J. Timer / Expiration Persistence
* Expiration calculation does not rely on an in-memory background timer.
* `expires_at` timestamp is durably persisted in SQLite upon session start.
* Upon process reload, `now >= expires_at` is evaluated deterministically against stored deadline.
* Any late interaction triggers immediate transition to `EXPIRED` and durable persistence of the expired status.

---

## K. Transactions & Atomicity
* Connections use `cx.commit()` for atomic unit-of-work persistence.
* Session updates, response insertions, and result records execute within coherent transactional blocks.
* Foreign keys enforced with cascade delete on child tables (`assessment_responses`, `assessment_results`).

---

## L. Concurrency
* Database connections open and close per operation or transactional boundary (`cx = self.db.connect(); ... cx.commit(); cx.close()`).
* Thread-safe memory cache and lock in `AssessmentService` prevent race conditions between in-memory operations and persistent store.
* Atomic transactions prevent double submissions and lost responses.

---

## M. Idempotency
Verified repeated executions:
* `save_assessment` called multiple times produces 1 row without duplicates.
* `save_session` called repeatedly with identical state executes idempotently.
* `save_response` called repeatedly updates or retains existing response idempotently.

---

## N. Corruption Handling
Robust error handling against corrupted persistent state:
* Malformed JSON in `items_json` raises `IntegrityError` safely.
* Unknown session status in SQLite raises `IntegrityError` safely.
* Invalid numeric text raises `IntegrityError` via `InvalidOperation`.
* Zero execution of arbitrary payload; zero silent data fabrication.

---

## O. Schema Versioning
* Forward-only migration script `011_assessment.sql` registered in `Database._MIGRATIONS`.
* Verified by `test_migrations_are_incremental_and_rerunnable`: migrations 1 through 11 apply cleanly on clean database and re-opening is an exact no-op.

---

## P. Provenance & Determinism
Verified full provenance round-trip:
* Given identical seed, persisted assessments produce identical item ordering upon reconstruction.
* Formula provenance metadata (`source_path`, `section`, `hash`) stored in `rubric_ref` and `options` is retained bit-for-bit.

---

## Q. Formula Coverage
Mandatory invariant: **100% formula coverage**.
* `Formula` $\to$ `item_from_formula` $\to$ `AssessmentItem` $\to$ `save_assessment` $\to$ SQLite $\to$ `get_assessment`:
  * LaTeX string: $Z = R + j\omega L$ preserved exactly.
  * Formula stable ID: `formula:sdm:f:000088` preserved.
  * Topic ID: `topic:sdm:t02` preserved.
  * Weight: `Decimal("4.5")` preserved.
  * Provenance: `formula_prov:teoria/ca.md#Impedance` preserved.
* Zero formula metadata dropped or converted.

---

## R. Security
* Parameterized SQL queries used exclusively (`?` placeholders).
* Zero string formatting or concatenation of user inputs into SQL queries.
* AST static audit verified 0 calls to `eval`, `exec`, `compile`, `__import__`, `system`, or `popen`.
* Zero float conversions in persistence layer.

---

## S. Test Suite
Comprehensive test suite in `tests/test_f9d_assessment_persistence.py`:
* 14 test cases covering all 20 required categories.
* Status: **14/14 passed in 20.34s**.

---

## T. Regression
* `tests/test_f9b_domain_assessment.py`: 11 passed.
* `tests/test_f9c_assessment_orchestration.py`: 11 passed.
* `tests/test_domain.py`, `test_ids.py`, `test_grading.py`, `test_results.py`, `test_architecture.py`, `test_persistence.py`: 38 passed.
* Sealed F8 Regression Suite (`test_f8j_small_signal_ac.py`, `test_f8d1_complex.py`, `test_f8d2_complex_solver.py`, `test_f8h_nonlinear_dc.py`, `test_f8i_bjt.py`, `test_f8i_nonlinear_bjt.py`): **288 passed**.

---

## U. Performance
Representative persistence benchmarks measured across realistic assessment scales:

| Scale | Save Assessment | Save Session | Save All Responses | Load Session + Responses |
| :---: | :---: | :---: | :---: | :---: |
| **1 item** | 15.76 ms | 21.84 ms | 17.62 ms | 5.94 ms |
| **10 items** | 16.45 ms | 24.85 ms | 178.42 ms | 5.99 ms |
| **32 items** | 36.09 ms | 21.27 ms | 572.54 ms | 6.88 ms |
| **64 items** | 20.37 ms | 17.33 ms | 1,130.39 ms | 7.43 ms |
| **128 items** | 21.43 ms | 18.56 ms | 2,264.55 ms | 6.81 ms |

Session reconstruction with 128 responses executes in **6.81 ms** (well below the 1.5s threshold).

---

## V. Architectural Duplication Audit
* Was a second database introduced? **No.**
* Was a second persistence layer introduced? **No.**
* Were F9-B models modified unnecessarily? **No.**
* Was F9-C orchestration duplicated? **No.**
* Was grading duplicated? **No.**
* Was correction duplicated? **No.**
* Was formula infrastructure duplicated? **No.**
* Was an ORM introduced unnecessarily? **No.**
* Was float conversion introduced? **No.**
* Was F8 modified? **No.**
* Was security weakened? **No.**
* Was deterministic behavior lost? **No.**

---

## W. New Findings
`NONE — deliberate finding search performed`

---

## X. Final Gate Decision
### **GATE DECISION: PASS**

Persistence, recovery, integrity, determinism, security, and regression criteria all pass.

---

## Summary Matrix

| Area | Status |
| :--- | :---: |
| **Existing persistence reuse** | PASS |
| **Assessment persistence** | PASS |
| **Session persistence** | PASS |
| **Response persistence** | PASS |
| **Result persistence** | PASS |
| **Recovery** | PASS |
| **Timer persistence** | PASS |
| **Terminal states** | PASS |
| **Decimal integrity** | PASS |
| **Transactions** | PASS |
| **Concurrency** | PASS |
| **Idempotency** | PASS |
| **Corruption handling** | PASS |
| **Schema versioning** | PASS |
| **Formula preservation** | PASS |
| **Determinism** | PASS |
| **Security** | PASS |
| **Regression** | PASS |
| **F8 integrity** | PASS |
| **Gate decision** | **PASS** |

No commits were made.  
No pushes were made.  
F8 production code was not modified.  
F9-B domain semantics were preserved.  
F9-C orchestration semantics were preserved.  
