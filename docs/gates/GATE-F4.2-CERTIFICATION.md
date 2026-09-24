# GATE-F4.2-CERTIFICATION — F4.2 implementation (assistance layer)

Branch: `f4.1-closure` · Baseline: `4dbcd8f` (F4.2 DESIGN READY) + F4.1 `ac2581f` intact.
Design authority: `docs/gates/GATE-F4.2-DESIGN.md` (§1 evidence matrix).

## 1. Commits, branch, baseline, files

| | |
|---|---|
| branch | `f4.1-closure` (main untouched) |
| baseline | `4dbcd8f` |
| migration | `014_f42_search_history.sql` registered in `database.py:_MIGRATIONS` |
| production files | `domain/planning.py` (+`SEARCH_KINDS`, `SavedSearch`, `RecentSearch`), `infrastructure/academic_store.py` (+`SearchHistoryRepository`), `infrastructure/__init__.py` (export), `infrastructure/database.py` (014), `application/search_history.py`, `application/notify.py` (+`NotificationView`), `application/personal.py` (+`f42.*`, canonical JSON, `normalize_legacy`), `application/f42_legacy.py` (resolution + consume), `application/facade.py` (wiring), `application/academic_mgmt.py` (+`progress_of` passthrough) |
| test files | `tests/test_f42_search_history.py`, `test_f42_migration.py`, `test_f42_notify.py`, `test_f42_preferences.py`, `test_f42_security.py` |
| legitimately updated | `tests/test_persistence.py` ([1..13]→[1..14]), `tests/test_migration.py` (13→14 migrations) |

## 2. Migration 014

Additive `saved_searches`/`recent_searches` (+`UNIQUE(kind,ref)`, recents index). No F4.1 table touched. Old DBs migrate forward; migrated DBs are no-ops (loader re-check under lock). `down` = DROP both tables + `DELETE FROM schema_version WHERE version=14` (payloads intact → re-derivable; tested).

## 3. Tests and results

| File | Result |
|---|---|
| `test_f42_search_history.py` | 9 passed (add/dup/is/remove/ordering/validation; upsert/trim-15/order/determinism) |
| `test_f42_migration.py` | 3 passed (fixture fav+reciente, unmapped/rerun/payload, source untouched) |
| `test_f42_notify.py` | 11 passed (4 rules, 12 boundary cases, purity hash, determinism, multiseed 0/11/2024/random) |
| `test_f42_preferences.py` | 5 passed (values/limits/None/JSON/legacy/determinism) |
| `test_f42_security.py` | 5 passed (AST gates) |

## 4. Requirement → test → evidence

| Requirement (design §5) | Test | Evidence |
|---|---|---|
| favourites idempotent | dup add → False, title kept | `test_f42_search_history.py` |
| recents ≤15, upsert, deterministic order | 17 inserts → 15, `task:16` first | id. |
| 014 + payload consume | fixture fav `asignatura#2`→`subject:dd`, rec `documento#1`→`resource:*` | `test_f42_migration.py` |
| mapping valid/invalid/ambiguous/rerun/payload kept/Gestion untouched | `resolve_legacy_reference` matrix + `legacy.keep` row + source sha | id. |
| 4 rules + boundaries (0/threshold±1/3/2/no-data/gaps/past) | 12 boundary tests | `test_f42_notify.py` |
| compute() pure | DB hash before/after + `pending_notifications()==[]` | id. |
| prefs validation/None/JSON/legacy | limits, clears, canonical `'["b","a"]'`, skipped list | `test_f42_preferences.py` |
| security AST | no eval/exec/pickle/subprocess/network, SQL parameterized | `test_f42_security.py` |
| multiseed | subprocess seeds, identical JSON | `test_compute_stable_across_hash_seeds` |

## 5. No-regression, purity, idempotence, security, F4.1 integrity

- Full suite `pytest -q` post-change: see §7 (only pre-existing/environmental items; F4.1 migration tests green).
- `compute()` purity: target-DB hash identical + `pending_notifications()` empty (test).
- Idempotence: favourites no-op, recents change-detecting upsert, consume rerun = 0 changes, migration rerun safe.
- Security: AST bans verified on all 6 new/modified Python files; URLs stored-never-fetched; no secrets; no new deps.
- F4.1 integrity: `gestion-migration/3` untouched (only additive reads via `legacy_map`/`payloads`); Gestion real untouched (consume reads target DB only; test asserts source sha + row count); `test_f4_*` suites green.

## 6. Discrepancies found (prompt §9: stop and document)

None blocking. Three minor deviations, all documented here (not silent):
1. `record_recent` returns change-bool (spec said upsert; bool makes rerun-0 observable).
2. Favourite title fallback `"{kind} #{legacy_id}"` when no title resolver is wired (deterministic, legacy-qualified, never invented content).
3. Past exams are omitted (not "informed"): informing would be a 5th rule absent from the gate; omission + no-mutation is tested.

## 7. Full-suite result

`pytest -q` (3 tercios en paralelo + 16 ficheros F4/F4.2, flags idénticos):
**4563 passed** · 12 failed · 12 skipped · 2 errors.

| Clase | Tests |
|---|---|
| PREEXISTENTE (evidencia en baseline `f42base`/F4.1) | 11 CRLF (`test_e0_g01`, `test_q4_g01`×6, `test_q5_g01`×4) |
| AMBIENTAL (trazas en este informe) | `test_document_symlink_escape_refused` (WinError 1314 en `os.symlink` del test); 2 errores teardown `pytest-qt` (límite 32767 chars de Windows); `test_html_corpus[html_cp1252]` pasó en este entorno |
| REGRESIÓN atribuible a F4.2 | **ninguna** |
| NUEVO | 35 tests F4.2, todos verdes; `test_persistence`/`test_migration` actualizados 13→14 por la nueva 014 (legítimo) |
