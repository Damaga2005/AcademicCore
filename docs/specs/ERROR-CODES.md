# SPDX-License-Identifier: MIT
# AcademicCore Error Code Registry (D2 implementation, F15)

Format `AC-<AREA>-<NNN>`. Codes are unique and stable across releases;
message text may change. Codes are the consumer API, messages are prose.

Areas: `VAL` validation, `DOM` domain, `CFG` configuration, `UNS`
unsupported, `SER` serialization, `VER` version, `SEC` security, `APP`
application, `ADP` adapter, `INF` infrastructure, `INT` integration,
`OK` success milestones.

| Code | Meaning | Severity | Recoverability | Public | Since |
|:---|:---|:---:|:---:|:---:|:---:|
| AC-VAL-001 | invalid input value | WARNING | RECOVER | yes | F15 |
| AC-DOM-001 | domain invariant violation | ERROR | RECOVER | yes | F15 |
| AC-CFG-001 | bad settings / wiring | ERROR | CONFIG_CHANGE | yes | F15 |
| AC-UNS-001 | out-of-scope request | WARNING | CONFIG_CHANGE | yes | F15 |
| AC-SER-001 | invalid serialization payload | ERROR | NONE | yes | F15 |
| AC-SER-002 | schema mismatch (unrecognized format) | ERROR | CONFIG_CHANGE | yes | F15 |
| AC-VER-001 | version mismatch (different engine version) | ERROR | CONFIG_CHANGE | yes | F15 |
| AC-SEC-001 | rejected payload / policy denial (private detail) | ERROR | NONE | generic only | F15 |
| AC-APP-000 | generic application failure (fallback) | ERROR | RECOVER | yes | F15 |
| AC-APP-001 | orchestration failure | ERROR | RECOVER | yes | F15 |
| AC-ADP-001 | external tool / adapter failure | ERROR | RETRY | yes | F15 |
| AC-INF-001 | storage / spawner / IO failure | ERROR | RETRY | yes | F15 |
| AC-INT-001 | internal invariant violated (bug) | ERROR | NONE | yes | F15 |
| AC-OK-001 | operation completed | INFO | NONE | yes | F15 |

Engine status enums map to sub-codes: `AC-DOM-…` + `status.value`
(e.g. `ControlStatus.DIVERGED`, `ACStatus.SINGULAR`, replay
`EQUIVALENT / RESULT_DIFFERS / VERSION_MISMATCH / SCHEMA_MISMATCH /
INVALID_SERIALIZATION`). Solver math outcomes stay typed statuses in
result objects, never bare raises (D2 §7–§8).

Wire form: schema `d2-error/1` (closed keys `error_code, category,
message, severity, recoverability, context, cause_code?, schema_version`;
no tracebacks, exception objects, class paths, or private-code internals).
