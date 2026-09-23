# SPDX-License-Identifier: MIT
# AcademicCore Error Code Registry (D2 implementation, F15)

Format `AC-<AREA>-<NNN>`. Codes are unique and stable across releases;
message text may change. Codes are the consumer API, messages are prose.

Areas: `VAL` validation, `DOM` domain, `CFG` configuration, `UNS`
unsupported, `SER` serialization, `VER` version, `SEC` security, `APP`
application, `ADP` adapter, `INF` infrastructure, `INT` integration,
`OK` success milestones; F4.1: `ACD` academic management, `MIG` legacy
data migration, `ICS` calendar interchange.

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
| AC-ACD-001 | academic management operation refused | ERROR | RECOVER | yes | F4.1 |
| AC-ACD-002 | unknown academic entity (subject, term, task, space...) | WARNING | RECOVER | yes | F4.1 |
| AC-ACD-003 | academic integrity guard (duplicate / still referenced) | WARNING | RECOVER | yes | F4.1 |
| AC-ACD-004 | invalid academic value (state, category, weight, URL...) | WARNING | RECOVER | yes | F4.1 |
| AC-MIG-001 | migration failed; target left unchanged (rolled back) | ERROR | RETRY | yes | F4.1 |
| AC-MIG-002 | legacy source is not a valid/consistent SQLite database | ERROR | CONFIG_CHANGE | yes | F4.1 |
| AC-MIG-003 | legacy schema revision not supported | ERROR | CONFIG_CHANGE | yes | F4.1 |
| AC-MIG-004 | snapshot of the target required before applying | ERROR | CONFIG_CHANGE | yes | F4.1 |
| AC-MIG-005 | migration cancelled; target left unchanged | INFO | RETRY | yes | F4.1 |
| AC-MIG-006 | post-migration validation failed | ERROR | NONE | yes | F4.1 |
| AC-SEC-002 | path escapes the allowed root (refused) | ERROR | NONE | generic only | F4.1 |
| AC-SEC-003 | archive rejected (zip slip / bomb / limits / hash) | ERROR | NONE | generic only | F4.1 |
| AC-ICS-001 | calendar file rejected (format or limits) | WARNING | CONFIG_CHANGE | yes | F4.1 |

Engine status enums map to sub-codes: `AC-DOM-…` + `status.value`
(e.g. `ControlStatus.DIVERGED`, `ACStatus.SINGULAR`, replay
`EQUIVALENT / RESULT_DIFFERS / VERSION_MISMATCH / SCHEMA_MISMATCH /
INVALID_SERIALIZATION`). Solver math outcomes stay typed statuses in
result objects, never bare raises (D2 §7–§8).

Wire form: schema `d2-error/1` (closed keys `error_code, category,
message, severity, recoverability, context, cause_code?, schema_version`;
no tracebacks, exception objects, class paths, or private-code internals).
