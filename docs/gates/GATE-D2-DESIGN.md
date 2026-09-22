# D2 Design Gate — Estándar de logging, errores, excepciones y estados

Documentation only: no code under `src/` was created or modified, no
tests were written, no engine was altered, D1 was not touched, no UI
was built, no repository was fused. The only output of this phase is
this file plus one local commit (no push).

## 1. Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Baseline at audit time: **`2e8017f`** (`docs(architecture): approve D1
  module and plugin design`), `origin/main == c79961b`, working tree clean.
- D1: `FINAL VERDICT: D1 DESIGN READY` (`docs/gates/GATE-D1-DESIGN.md`,
  intact — verified via `git diff HEAD --stat`, empty).
- Roadmap authority (§5.1 rows :213–:216): D1 [12º] DONE → **D2 [13º]
  THIS GATE** → D3 [14º] → F15 [15º]. Strict order, no parallelism.

## 2. Roadmap authority

| Row | Content | Status |
|:---|:---|:---|
| :213 D1 | module/plugin architecture; static registry, manifest `d1-manifest/1` | DONE (frozen input) |
| :214 D2 | logging/errors standard; replaces conversor `except Exception: pass` | THIS GATE |
| :215 D3 | single license; conversor already MIT | boundary only (§D3) |
| :216 F15 | final app; consumes D2 via UI-safe errors + runtime logs | prerequisites only (§F15) |
| D1 §27 | D2 boundary pre-fixed: domain errors = typed values; application = typed errors + reports; adapter = degrade-with-provenance; UI = presentation | adopted verbatim (§7) |

## 3. Current error/logging audit (evidence)

Verified by inspection at baseline (paths under `src/academic_core/`).
`rg`-equivalent search via AST-aware grep; `__pycache__` excluded.

### 3.1 Existing error taxonomy (REUSE — do not duplicate)

| Class | Location | Base | Shape |
|:---|:---|:---|:---|
| `DomainError` | `domain/entities.py:43` | `ValueError` | plain message |
| `AuthoringError` | `domain/authoring.py:27` | `ValueError` | plain message |
| `AstError` | `documents/ast.py:25` | `ValueError` | plain message |
| `UnitError` / `CircuitError` / `EquationError` / `GeneralityError` | `domain/engineering/*` | `ValueError` | plain message |
| `ACFrequencyError` / `ACPhaseError` / `ACModeError`, `BodeError`, `ImpedanceError`, `TwoPortError`, `PowerAnalysisError`, `ResonanceError`, `InvalidPortError`, `UnsupportedCircuitError` | `domain/engineering/ac/*`, `thevenin/*` | `ValueError` | plain message |
| `ControlError(status, msg)` / `ControlStatus` | `domain/engineering/control/errors.py:11-26` | `ValueError` | **typed status**: `INVALID/UNSUPPORTED/SINGULAR/DIVERGED/MAX_ITERATIONS/INCONSISTENT/COMPLETED` |
| `MetrologyError` / `MetrologyStatus` | `domain/engineering/metrology/errors.py:15-30` | `ValueError` | typed status (`INCONSISTENT` = digest/chain/tamper) |
| `LabConfigError`, `RunStatus`, `MeasurementStatus`, `InstrumentStatus`, `ReplayStatus`, `LoadStatus` | `domain/engineering/lab/model.py:103-218` | `ValueError` / `str,Enum` | replay constants below |
| `ApplicationError` | `application/services.py:21` | `ValueError` | plain message |
| `SecurityError` | `application/ingest.py:29` | `ValueError` | plain message |
| `PDFError` / `StirlingError` | `pdf/engine.py:17`, `pdf/stirling.py:47` | `ValueError` | adapter errors |
| `TooLarge` / `BlobNotFound` | `infrastructure/cas.py` | (typed) | infrastructure errors |
| Chaining precedent | `control/statespace.py:51`, `poly.py:63`, `margins.py:38` | — | `raise ControlError(STATUS, msg) from exc` |

Replay/serialization constants (certified, shared idiom across
`control/report.py`, `dsp/report.py`, `comms/report.py`,
`metrology/report.py`, `satcom/report.py`, `lab/model.py`,
`lab/replay.py`):
`EQUIVALENT` (alias `VALID`), `RESULT_DIFFERS` (alias
`RESULT_DIFFERENT`), `VERSION_MISMATCH`, `SCHEMA_MISMATCH`,
`INVALID_SERIALIZATION`. Solver math states: `ACStatus`
(`SOLVED/SINGULAR/INCONSISTENT/NUMERICALLY_UNCERTAIN/INVALID/UNSUPPORTED/DIVERGED`),
`EquivalentStatus`, `LinearSolveStatus`/`SolveStatus`.

### 3.2 `except` inventory and classification

| Site | Pattern | Classification |
|:---|:---|:---|
| `documents/conversor_math.py:255,261` | `except Exception: pass` in MathML→LaTeX fallback chain (primary → `mathml2latex` → plaintext) | **legítimo en forma, deuda en señal**: fallback correct, but failure is silent (no warning recorded) → D2 requires warning propagation (§33) |
| `documents/encoding.py:25,33` | `except Exception: pass` in BOM → meta → utf-8 → cp1252 → replace chain | **legítimo**: exhaustive codec ladder, final `replace` fallback cannot fail; keep shape, add debug log at adapter level |
| `application/ingest.py:122,164` | `except Exception as e` → `ExtractedContent(status="failed", warnings=(...))` / `IngestReport(... warnings + index deferred)` | **exemplary — D2's model**: canonical state protected, failure recorded with provenance, no rollback of truth |
| `resources/adapters.py:140,182` | `except Exception as e` → degraded `ExtractedContent` with warnings | **correct**: degrade-with-provenance per D1 §13 |
| `application/ingest.py:199` (`reindex`) | bare `except Exception:` → `bodies[sid] = (kind, title, "")` | **deuda menor**: swallows per-item failure without flagging; D2 requires warning entry (batch partial-result rule §35) |
| `infrastructure/ngspice.py:205-206` | `except Exception: pass` in candidate discovery | **deuda**: silent discovery degradation; D2 requires reason in `RuntimeInfo.details` (§32) |
| `ui/*.py` (~20 sites) | `except Exception as e` → `QMessageBox.warning(self, T, f"{type(e).__name__}: {e}")` | **correct boundary, unsafe payload**: catching at UI is right; rendering raw `str(e)` leaks internals (SQL, paths) → D2 requires UI-safe conversion (§28) |
| `infrastructure/resources.py:36`, `cas.py:94`, `database.py:135` | `except BaseException: <cleanup>; raise` | **legítimo (grandfathered compliant)**: transactional rollback-and-reraise, never swallows; `KeyboardInterrupt/SystemExit` propagate |
| `pdf/stirling.py`, `pdf/engine.py:63`, `application/*` (`academic_io:84,114`, `assessment:332`, `authoring:261`) | `except Exception as e` with collect-and-continue or translate | **correct** provided translation keeps cause chain; audited, no silent `pass` found in-repo outside the rows above |

No `except:` (bare) found in `src/`. No `raise Exception(...)` /
`raise RuntimeError(...)` in domain paths (the two `RuntimeError`s live
in `engines/providers.py:44`, `engines/pdf.py:42` as disabled-provider
guards — adapter-level, compliant after re-parenting, §8).

### 3.3 Logging / print / traceback audit

- `import logging`, `getLogger`, `logger.`, `print(`, `traceback`,
  `exc_info`, `stack_info`: **zero hits in `src/`**. Logging is
  greenfield; there is no legacy framework to migrate and no
  `print`-debugging to remove.
- UI feedback today is `QMessageBox` (modal, human strings) — the only
  "observability" surface. No structured runtime telemetry exists.
- Timestamps in results: `ingest.py` writes `imported_at=_utcnow()` into
  provenance and `ngspice.py` stamps `RuntimeInfo` with `_now()` — both
  are **metadata, excluded from digests** (verified precedent for §21).

### 3.4 Conversor case (priority item, :214)

- External repo (`Documents/HTML TO MD/conversor_html_notebooklm.py`):
  **46× `except Exception`**. Same fallback idiom as the in-repo engine
  (MathML chain :410-424, image extraction ~:660 `except Exception:
  pass` dropping the failed image silently). Stdout-reconfigure guards
  (:24, :29) are legitimate. Core defect class: **silent per-item loss**
  (one image/formula fails → output claims completeness).
- In-repo engine (`documents/conversor_*.py`): fallback chains only;
  no top-level swallowing. The D1 claim "`except Exception: pass`
  belongs to the EXTERNAL conversor repo" is confirmed with the
  two in-repo exceptions listed in §3.2 rows 1–2 (both fallback chains,
  not top-level loss).
- D2 contract for the future fix (§33): every fallback records a typed
  warning; conversion returns `(output, warnings)`; batch never claims
  `status="ok"` when warnings exist.

### 3.5 Subprocess error handling (ngspice / stirling)

- `ngspice.detect/batch_probe` already returns a **`RuntimeInfo` value**
  (`verified` flag + details string) instead of raising — exemplary
  adapter translation; timeouts bounded (`min(timeout, 10/15s)`),
  `shell=False`, scoped cwd. `batch_probe` catches `(OSError,
  subprocess.TimeoutExpired)` narrowly. Only defect: discovery `except
  Exception: pass` (§3.2).
- `stirling.py`: `subprocess.Popen` list-form, `TimeoutExpired`
  handled; broad catches at :84,95,112 degrade to not-enabled — require
  cause logging under D2 (§32) but shape is sound.

## 4. Problem statement

Today AcademicCore has a **mature error vocabulary but no error
standard**: ~25 exception classes share only `ValueError`; messages are
the API (consumers must string-match); severity/recoverability are
implied; logging does not exist (diagnosis = modal dialogs); the
conversor can lose content silently; one discovery path swallows
`Exception`. D2 fixes the contract without touching behavior: codes
become stable, translation boundaries become explicit, logging becomes
structured and digest-safe, and every broad catch gets a disposition.

## 5. Error taxonomy (normative)

Reuse-first: every existing class keeps its name, module, and
`ValueError` ancestry (compatibility §57). D2 adds ONE common root and
re-parents existing classes under it (MRO still contains `ValueError`,
so all current `except ValueError` handlers keep working):

```text
AcademicCoreError(ValueError)            # new single root (D2 implementation)
├── DomainError                          # EXISTS (entities) — semantic model violations
├── ValidationError                      # NEW — invalid input (vs §10 internal inconsistency)
├── ConfigurationError                   # NEW — bad settings/wiring (never domain)
├── UnsupportedError                     # NEW — out-of-scope (model/format/curve/kind)
├── SerializationError                   # NEW — INVALID_SERIALIZATION / SCHEMA_MISMATCH payloads
├── VersionMismatchError                 # NEW — VERSION_MISMATCH (schema family differs)
├── SecurityError                        # EXISTS (ingest) — rejected payloads, policy denials
├── ApplicationError                     # EXISTS (services) — orchestration failures
├── AdapterError                         # NEW — external translation failures (conversor, providers)
├── InfrastructureError                  # NEW — SQLite/CAS/FTS/subprocess/resource failures
└── IntegrationError                     # NEW — cross-module contract violations (replay RESULT_DIFFERS carriers)
```

Re-parent map (behavior-preserving, names/modules unchanged):
`AuthoringError→DomainError`; `AstError→DomainError`;
`UnitError/CircuitError/EquationError/GeneralityError/AC*Error/BodeError/ImpedanceError/TwoPortError/PowerAnalysisError/ResonanceError/InvalidPortError→DomainError`;
`ControlError/MetrologyError/LabConfigError→DomainError` (keeping their
`(status, msg)` constructor and status enums as the typed payload);
`PDFError/StirlingError→AdapterError`; `TooLarge/BlobNotFound→InfrastructureError`.
Engine `*Error` classes additionally carry their certified status enum
value (e.g. `ControlError.status: ControlStatus`) — the status IS the
machine-readable sub-code (§6).

`except BaseException` remains restricted to rollback-and-reraise (§38);
the three existing sites are declared compliant as-is.

## 6. Error code policy (normative)

Format `AC-<AREA>-<NNN>`, e.g. `AC-VAL-004`. Areas:
`VAL` validation, `DOM` domain, `CFG` configuration, `UNS`
unsupported, `SER` serialization, `VER` version, `SEC` security,
`APP` application, `ADP` adapter, `INF` infrastructure, `INT`
integration. Registry (`docs/specs/ERROR-CODES.md` in D2
implementation): namespace, code, meaning, severity, recoverability,
public/private, since-version. Rules: codes unique and stable across
releases (message text may change); new codes only appended; engine
status enums map to sub-codes (`AC-DOM-…` + `status.value`); code is
the API, message is prose (§24). Internal-only codes marked private
(never cross the UI boundary).

## 7. Result vs exception (normative)

| Situation | Mechanism | Example |
|:---|:---|:---|
| Solver math outcome incl. non-convergence | typed status in result object, NO raise | `MAX_ITERATIONS/DIVERGED/SINGULAR` in `ControlStatus`; `ACStatus.DIVERGED` |
| Caller passes invalid object/parameter | typed raise (`ValidationError` or engine `*Error(INVALID, …)`) | `frequency = -1 Hz` → `AC-VAL-…` |
| Out-of-scope request | typed raise (`UnsupportedError` / `UNSUPPORTED` status) | unknown model, non-invertible APPROX curve |
| Internal invariant violated (bug) | `IntegrationError`/`ApplicationError` + ERROR log with correlation id | digest mismatch on trusted path |
| External tool/file/format failure | `AdapterError`/`InfrastructureError`, chained | ngspice timeout, missing exe, bad output |
| Replay comparison | string-constant result (`EQUIVALENT/RESULT_DIFFERS/VERSION_MISMATCH/SCHEMA_MISMATCH`), raise only for `INVALID_SERIALIZATION` input | `lab/replay.py`, `*/report.compare` |

Rationale (matches existing code): math non-convergence is an expected
answer about the equations, not a broken call chain — the engines
already do this; D2 pins it. Validation (§10) vs inconsistency: bad
input raises `ValidationError`; a violated internal invariant raises
`IntegrationError` (fatal/internal, §29).

## 8. Solver status policy

Certified states (`ControlStatus`, `ACStatus`, `EquivalentStatus`,
`SolveStatus`, metrology/lab enums) are **preserved verbatim** (§45).
Mapping to D2: each status value carries category + recoverability in
the code registry (e.g. `DIVERGED` → user-correctable/category
`solver`; `SINGULAR` → user-correctable; `MAX_ITERATIONS` →
retryable-with-config). Presentation to application/UI goes through
the engine's report object (never raw enum + free text). No engine
gains logging, no status becomes a bare `Exception`.

## 9. Logging levels (normative)

Stdlib `logging`, no new dependency. One root `academic_core` logger;
module loggers (`academic_core.application`, `…infrastructure`,
`…adapters`, `…ui`); **no logger in `domain/` or `documents/ast.py`**.

| Level | Use | Domain | Application | Adapter/Infra | UI |
|:---|:---|:---:|:---:|:---:|:---:|
| DEBUG | diagnostic detail (off by default; explicit flag) | — (forbidden) | operation internals | protocol traces, truncated | — |
| INFO | normal operation milestones | — | start/finish + outcome | backend detected/ready | — |
| WARNING | controlled degradation (result still usable) | — (as value) | partial results | fallback used, probe failed | — |
| ERROR | operation failed, typed error raised | — | service failure + correlation id | external failure + cause type | presentation failure |
| CRITICAL | process-wide integrity risk, cannot continue safely | — | reserved (DB corrupt, CAS poison) | reserved | never |

`logger.error(...)` never substitutes `raise` (both happen: raise the
typed error, log once at the boundary that owns the context). `raise`
never substitutes logging where §18–19 require a record. No per-Newton-iteration / per-sample / per-bit logging except DEBUG-behind-flag.

## 10. Structured logging (normative)

Required record fields: `timestamp, level, event_code, component,
operation, message`. Optional: `context (closed, §11), correlation_id,
exception_type, recoverability`. `event_code` reuses the error-code
namespace (`AC-…`) or `AC-OK-…` for success milestones. Format/handler
(console/file) is deployment config, not domain. **Timestamps live only
in log records** — never in result payloads, digests, provenance, or
`compare()` inputs (§21; existing `_utcnow()/_now()` metadata stays
outside digest inputs as today).

## 11. Context (normative)

Closed key set: `component, operation, parameter, expected, received,
unit, schema, resource_kind, adapter, attempt, limit`. Limits: message
≤ 1 KiB, context ≤ 8 fields / ≤ 4 KiB total, nesting depth ≤ 3, batch
errors capped at 100 + `overflow_count` (§52). Secrets/PII forbidden
(§12).

## 12. Redaction (normative)

NEVER log: passwords, tokens, API keys, secrets, OAuth material, full
auth headers, credentials, `ACORE_*` env values, absolute home paths
(trim to `<home>/…` or relative). Evaluate-and-minimize: personal data
(ids only when needed for support, never bulk), full document contents
(metadata + digests only), binary payloads (hash + size only),
environment dumps. Engine math values are safe (no redaction needed)
but bounded by §11 size rules. Violation = security bug (test D2-012).

## 13. Exception chaining (normative)

Every translation boundary uses `raise NewError(code, msg) from exc`
(the `ControlError…from exc` precedent becomes the universal rule).
Forbidden: `raise Exception(str(exc))`, `raise New(str(e))` without
`from`, and re-raising with the original traceback erased. The inner
cause's *type name* may be logged; its message crosses layers only if
UI-safe (§28). Cause chains serialize as `cause_code` (code only, §39).

## 14. UI boundary (normative)

UI receives a frozen `UiError` value: `error_code, safe_message,
severity, recoverability, user_action`. Conversion happens in ONE
application-level function (D2 implementation), never inline per
dialog: it maps codes → safe strings + actions (e.g. `AC-VAL-…` →
"check the highlighted value"; `AC-UNS-…` → "not supported in this
version"; `AC-INF-…` → "external tool failed — details logged, ref
<correlation>"). Never shown: tracebacks, SQL, subprocess commands,
absolute paths, secrets, digests, internal codes marked private.
Current `f"{type(e).__name__}: {e}"` dialogs are grandfathered until
D2 implementation replaces them (migration row 5, §24bis).

## 15. Adapter boundary (normative)

`external failure → AdapterError/InfrastructureError (chained) →
ApplicationError/report → UiError`. Adapters catch narrow external
types first (`OSError`, `TimeoutExpired`, `sqlite3.Error`,
`UnicodeDecodeError`, parser errors), then `Exception` ONLY as the
documented last net with translation + WARNING log (never `pass`).
`sqlite3/subprocess/requests/Qt/third-party` exceptions never cross
into domain. Successful degradation keeps today's shape:
`ExtractedContent(status, warnings)` / `IngestReport(warnings)` /
`RuntimeInfo(verified=False, details)`.

## 16. Infrastructure boundary (normative)

Typed failures: `timeout` (bounded, config value in context),
`non-zero exit` (exit code, truncated stderr ≤ 1 KiB, redacted),
`missing executable` (searched paths count, not full home listing),
`invalid output` (`InfrastructureError` + parser position),
`resource failure` (`TooLarge/BlobNotFound` preserved). `unit_of_work`
keeps rollback-and-reraise. No new spawners without a gate (D1 §18
carries over).

## 17. Serialization (normative)

Error wire form, schema `d2-error/1` (closed keys, unknown rejected):
`error_code, category, message, severity, recoverability, context,
cause_code?, schema_version`. Forbidden on the wire: tracebacks,
exception objects, Python class paths, private codes' internals.
Existing engine document schemas (`f8*/1`, `f8n-lab/1`) are untouched;
`d2-error/1` is additive and only used for transport/presentation.

## 18. Replay (normative)

Existing semantics preserved verbatim: `EQUIVALENT/RESULT_DIFFERS/
VERSION_MISMATCH/SCHEMA_MISMATCH/INVALID_SERIALIZATION` keep their
strings, aliases (`VALID`, `RESULT_DIFFERENT`), and compare-function
shapes. D2 mapping: `SCHEMA_MISMATCH→SerializationError`,
`VERSION_MISMATCH→VersionMismatchError`,
`RESULT_DIFFERS→IntegrationError` (as carrier, still returned not
raised), tamper (`INCONSISTENT` digest) → `SecurityError`-auditable
event + ERROR log. No certified compare function changes signature.

## 19. Determinism (normative)

Logging NEVER alters results: no log call in domain hot paths; log
records excluded from every digest input; enabling DEBUG changes bytes
on disk (log files) but zero bytes in canonical outputs. Tests assert
`result(deterministic input)` identical with logging disabled / INFO /
DEBUG (§D2-011). Correlation ids are runtime-only (UUID allowed),
never embedded in domain values or digests (§22).

## 20. Resource limits (normative)

Per §11 caps + `log rate`: adapters token-bucket DEBUG traces (default
≤ 10/s per component, overflow counted not dropped-silently);
batch ops aggregate (cap 100 item-errors + `overflow_count`, §35);
no full-matrix/full-waveform/full-corpus dumps at any level. Hot-path
rule: logging statements in solver loops must be DEBUG-guarded
(`if logger.isEnabledFor(DEBUG)`) or absent.

## 21. Performance (contract)

No optimization now; contract only: zero logging in domain math;
lazy `%s`-args (never f-string interpolation at call site for
DEBUG); guarded blocks; sampling for high-frequency adapter traces.
Regression test asserts no logger attribute exists on domain engine
modules (static check, D2-011 companion).

## 22. Security (summary)

Security errors are a separate category (`SecurityError`) with private
messages by default (public `UiError` says "rejected input — nothing
was stored", details logged with correlation id). Tamper/digest
failures always ERROR-logged. No error path executes content (§24 D1
carries over: no `eval/exec/compile/subprocess/pickle` reachable from
manifest/JSON/parameters). Audit method: §3 greps + new AST tests
(D2-009/D2-010/D2-012).

## 23. Migration strategy (normative)

Gradual, no big bang. Order: 1) conversor engine + external adapter
slot (warnings on every fallback; `status="ok"` forbidden with
non-empty warnings); 2) external adapters (`RuntimeInfo.details` for
ngspice discovery; stirling cause logs); 3) application services
(re-parent to root, add codes); 4) infrastructure (typed spawner
errors); 5) UI (single `UiError` converter, replace inline
`str(e)`); 6) legacy residual (`reindex:199` warning flag).
Rule: existing `except` sites are grandfathered per the §3.2
dispositions; new code MUST follow D2; each migrated site references
its D2 invariant in a comment. Zero behavior change to F8 engines.

## 24. Compatibility

All existing `except ValueError` handlers keep working (MRO
preserved). Status enums, replay strings, report shapes, `RuntimeInfo`,
`IngestReport`, `ExtractedContent` unchanged. `status`-returning APIs
are never converted to raises. Generic `ValueError`s gain codes via
mapping table (D2 implementation) without changing raise sites'
semantics. Private-code redaction applies at the UI converter only.

## 24bis. D3 boundary

D2 leaves for D3: license headers/policy, NOTICE, SPDX identifiers.
D2 requires only that the future `ERROR-CODES.md` registry and any new
D2 module carry license metadata compatible with the single-license
decision (manifest `security_policy` + provenance fields per D1 §28).

## 25. F8 preservation

F8-P1…P5 untouched: `ControlStatus` (incl. `CONVERGED`-family,
`MAX_ITERATIONS`, `DIVERGED`, `SINGULAR_JACOBIAN`-equivalent
`SINGULAR`), per-engine `*Error` classes, report `dumps/loads/compare`,
and N-110 layer-direction tests all preserved. D2 only *maps* these
into codes/presentation; any future engine change needs its own gate.

## 26. F8-N preservation

F8-N `SCHEMA / LAB_VERSION = f8n-lab/1`, `ReplayStatus`, `LoadStatus`,
`SESSION_ID_RE` discipline, `serialize.py` closed-JSON rules (no
pickle/eval/marshal/YAML tags) preserved. D2 error wire form
(`d2-error/1`) is separate and never mixed into lab documents.

## 27. Error matrix

| Layer | Case | Type | Raise? | Log? | UI? |
|:---|:---|:---|:---:|:---:|:---:|
| Domain | invalid input | `ValidationError`/engine `*Error(INVALID)` + code | yes | no (caller logs) | via application |
| Domain | out-of-scope | `UnsupportedError`/`UNSUPPORTED` | yes | no | yes (action: change request) |
| Solver | non-convergence etc. | status in result | no | application INFO/WARNING | yes (report) |
| Serialization | bad payload | `SerializationError` (`INVALID_SERIALIZATION`) | yes | WARNING + corr. id | yes (reject, safe msg) |
| Serialization | schema/version drift | `VersionMismatchError` / compare constants | const / yes | WARNING | yes |
| Adapter | external failure | `AdapterError` chained | yes | WARNING/ERROR + cause type | yes (safe msg + ref) |
| Infrastructure | spawner/IO/store failure | `InfrastructureError` chained | yes | ERROR + corr. id | yes (safe msg + ref) |
| Application | orchestration failure | `ApplicationError` + report | yes | ERROR + corr. id | via `UiError` |
| Security | rejected/tamper | `SecurityError` (private msg) | yes | ERROR + corr. id | generic safe msg |
| UI | presentation failure | `UiError` (value, not exception) | no | ERROR | fallback dialog |

## 28. Logging matrix

| Level | Use | Required at | Forbidden at |
|:---|:---|:---|:---|
| DEBUG | behind-flag detail | nowhere mandatory | domain; default-on paths |
| INFO | milestones (op start/finish + outcome) | application ops; backend ready | per-item/per-iteration |
| WARNING | controlled degradation | every fallback/degrade site | as substitute for raise |
| ERROR | failed operation + typed error | every translation boundary | domain; without correlation id |
| CRITICAL | process integrity risk | DB/CAS corruption paths only | UI; routine failures |

## 29. Invariants

| ID | Property | Future test |
|:---|:---|:---|
| D2-I001 | no swallowed exceptions (every `except` translates, warns, or reraises) | D2-009/D2-010 |
| D2-I002 | error codes stable + unique (registry) | D2-002 |
| D2-I003 | domain has no logger (static check) | D2-011 |
| D2-I004 | logging never alters digests/results | D2-011 |
| D2-I005 | no secret/PII in logs (redaction) | D2-012 |
| D2-I006 | adapters translate externals (no leakage into domain) | D2-008 |
| D2-I007 | F8 statuses preserved verbatim | D2-007/D2-015 |
| D2-I008 | replay constants preserved | D2-014 |
| D2-I009 | no broad catch without translation+log at a documented boundary | D2-009 |
| D2-I010 | no error-by-log-only (every ERROR log pairs with raise or report entry) | D2-010 |
| D2-I011 | UI shows only `UiError` safe fields | D2-013 |
| D2-I012 | chaining preserves cause (`from exc`) | D2-001 |
| D2-I013 | wire errors are closed `d2-error/1` (no traceback/class-path) | D2-006 |
| D2-I014 | `except BaseException` only rollback-and-reraise | D2-009 |
| D2-I015 | codes, not message text, are the consumer API | D2-002/D2-003 |

## 30. Test plan (D2 implementation, not this phase)

D2-001 hierarchy+re-parenting (MRO/`from`-chain) · D2-002 code
registry uniqueness/stability · D2-003 validation mapping ·
D2-004 domain error mapping · D2-005 unsupported mapping ·
D2-006 serialization mapping + `d2-error/1` round-trip ·
D2-007 solver status preservation (F8 matrices green) ·
D2-008 adapter translation (fake failing externals) ·
D2-009 broad-catch AST detection (allowlist = §3.2 + migrated sites) ·
D2-010 swallowed-exception detection (no `pass`-only handlers outside
allowlist) · D2-011 logging determinism (outputs identical across log
levels; no logger in domain) · D2-012 redaction (secret fixtures) ·
D2-013 UI-safe conversion (no internals in `safe_message`) ·
D2-014 replay compatibility (golden vectors) · D2-015 F8 regression
(P1…P5 + F8-N suites green).

## 31. Risk matrix

| Risk | Prob. | Impact | Mitigation | Residual |
|:---|:---:|:---:|:---|:---|
| Silent swallowing survives migration | M | H | §3.2 per-site dispositions + D2-009/010 | low |
| Taxonomy explosion (25+ classes × codes) | M | M | reuse-first; codes appended not multiplied; registry review | low |
| Domain→logging coupling temptation | L | H | static test D2-011; values-not-logs rule | low |
| Secret/PII leakage via context/cause | M | H | closed context keys; redaction policy; D2-012 | med |
| Log amplification (MC/FFT/transient) | M | M | hot-path ban + rate caps + guarded DEBUG | low |
| Nondeterministic ids/timestamps in results | L | H | runtime-only rule; digest-input tests | low |
| UI traceback/internal leakage | M | M | single converter; D2-013; grandfather list | low |
| Adapter external leakage (sqlite3/subprocess/Qt) | L | H | translation table; D2-008 | low |
| F8/serialization compat break | L | H | map-don't-replace; golden replay vectors | low |
| Legacy `str(e)` dialogs linger | M | L | migration row 5; allowlist shrinks per release | low |
| `except BaseException` misuse spreads | L | H | allowlist = 3 sites; AST test | low |

## 32. Open questions

1. Log sink/rotation policy (file location, retention) — deployment
   detail, needs F15 runtime shape. NON-BLOCKING (defaults: console,
   no file).
2. Exact `ERROR-CODES.md` numeric assignments — D2 implementation
   bookkeeping. NON-BLOCKING.
3. External conversor's 46 handlers' per-site warning taxonomy —
   needs adapter implementation pass. NON-BLOCKING (contract fixed
   here).
4. Log verbosity UX in F15 (user-visible log viewer?) — F15 design.
   NON-BLOCKING.
5. `AC-OK-…` success milestone catalog — implementation detail.
   NON-BLOCKING.
No BLOCKING questions remain.

## 33. Acceptance criteria

Defined (§61 prompt): taxonomy ✓ (§5) · codes ✓ (§6) · result vs
exception ✓ (§7) · solver mapping ✓ (§8) · levels ✓ (§9) ·
domain boundary ✓ (§9–10) · structured context ✓ (§10–11) ·
redaction ✓ (§12) · chaining ✓ (§13) · UI boundary ✓ (§14) ·
adapter translation ✓ (§15) · serialization/replay ✓ (§17–18) ·
determinism ✓ (§19) · resource limits ✓ (§11/§20) · migration ✓
(§23) · F8 ✓ (§25) · F8-N ✓ (§26) · security ✓ (§12/§22) · test
strategy ✓ (§30) · D3 boundary ✓ (§24bis) · F15 prerequisites (§F15
below) · matrices ✓ (§27–28) · invariants ✓ (§29) · risks ✓ (§31).

## §F15. F15 prerequisites (from D2)

D2 implementation must deliver before F15: `AcademicCoreError` root +
re-parenting, `ERROR-CODES.md` registry, stdlib-logging wiring (root
`academic_core` logger + single `UiError` converter), per-site
migration of §3.2 debt rows (conversor warnings, ngspice discovery
details, `reindex` flag, UI converter), D2-001…D2-015 green. F15 then
uses: `UiError` values in every dialog, correlation ids in failure
reports, log viewer fed by structured records only.

## 34. Final verdict

All acceptance items closed on repository evidence; taxonomy reuses
(rather than replaces) certified contracts; no BLOCKING open
questions; D1 gate, F8-P1…P5, prior gates and roadmap untouched; no D2
implementation, no D3, no F15 code created.

FINAL VERDICT: D2 DESIGN READY
