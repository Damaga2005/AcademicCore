# Changelog

## Unreleased — Fase D7: Ingesta estructurada → Knowledge Core (CERTIFICADA)
- Plan puro `domain/ingestion.py` + servicio `application/bank_ingest.py` (plan/dry-run/ingest, 1 tx `unit_of_work`, verify post-commit, `now_ms` inyectable). Políticas: reuse/create/rechazo determinista, ambigüedad concepto+formula → error, idempotencia por digest, versiones create/unchanged/update/conflict/stale, reuse sin overwrite, fórmula modificada = conflicto.
- Migración 016 aditiva (`qbank_banks`, `qbank_questions`, `formulas` para `academic.Formula`) + `QBankRepository` con `cx`; conceptos en `study_concepts` (reuso, creación solo con catálogo + subject existente + bump `id_counters.concept`); refs section/document/topic carried opacos. Errores `AC-ACD-002/003/004` + `AC-INT-001` (sin códigos nuevos).
- Nuevos: `test_d7_ingestion.py` (18 contractuales: mínimo, mapping, digest, create, idempotencia cero-writes, update+delete, reuse, unresolved `AC-ACD-002`, ambigüedad `AC-ACD-003`, provenance E2E, no-overwrite, conflicto de fórmula, rollback inyectado, dry-run, determinismo ×2 DBs, inválidos/versiones, subject desconocido, seguridad AST + latex inerte).
- Docs: `D7-INGESTION.md` + `GATE-D7-CERTIFICATION.md` (criterios §23: todo verde salvo CI real y roadmap, explícitamente pendientes). Tocado certificado: solo pins `15→16` en `test_migration.py`/`test_persistence.py` (la 016 los exige).
- Evidencia local: 18/18 D7 + regresión amplia verde (1 pin actualizado, re-verde) + 48 passed × 3 hash-seeds. Commit impl. `18d3815`. Run `36239628773` (`03579c0`): intento 1 con 1 flake `test_perf_academic_scale` (21.47s/20s, win-3.13, clase §8); intento 2 tras `rerun --failed` verde 4/4 + package. Roadmap: D7 CERTIFICADA, F9 SIGUIENTE.

## Unreleased — Fase D6: Esquema neutro de banco de preguntas (CERTIFICADA)
- Dominio puro `domain/question_bank.py`: `Bank`/`Question`, 7 `qtype`, `answer_spec` por tipo (claves cerradas), IDs `bank:<slug>` / `question:<slug>:q:NNNNN`, `schema d6-question-bank/1` + `content_version`, canonicalización `sort_keys` + digest `sha256(tag+0x00+canonical)`, envelope con `integrity`, validación estricta + extensiones `x-`, provenance forma F2, errores D2 existentes (sin códigos nuevos), cero floats, sin persistencia (formato + validador).
- Nuevos: `test_d6_question_bank.py` (16 contractuales: mínimos, tipos, IDs, schema/rechazo `AC-VER-001`, canonicalización, digest semántico, round-trip, provenance, knowledge_refs, answer_spec, unidades + `parse_unit`, extensiones, tamper/inválidos, determinismo, seguridad AST).
- Docs: `D6-QUESTION-BANK.md` + `GATE-D6-CERTIFICATION.md` (criterios §21: todo verde salvo CI real y roadmap, explícitamente pendientes). Cero código certificado tocado.
- Evidencia local: 16/16 D6 + regresión 189 passed / 1 skip ambiental + 36 passed × 3 hash-seeds. Commit impl. `07b3136`. Run `36236406471` (`86f105d`) verde 4/4 + package. Roadmap: D6 CERTIFICADA, D7 SIGUIENTE.

## Unreleased — Fase D5: Suite global de tests (CERTIFICADA)
- Baseline pre-D5: 4598 tests / 138 ficheros → 4583 passed, 2 failed (preexistentes), 13 skipped, ~60 min local.
- Fix §12 (bug real): `SyncService._apply_winners` llamaba `add_favourite(kind, ref, title)` sobre el repositorio → `TypeError` al aplicar favoritos remotos; ahora construye `PL.SavedSearch` (preserva `created`). Regresión incluida.
- Fix §12 (test con fecha caducada): `test_activity_from_documents_and_reading` dependía del reloj real (verde CI 09-25, rojo desde 09-26); `added_at` backdateado, fechas 100% fijas. Cero producto tocado.
- Fix §9: `test_generality_sweep_both_modes` (105s > 90s en runner lento, CI verde) marcado `perf`; umbral intacto.
- Nuevos: `test_f13ext_service.py` (13: identidad, adaptadores, 2 BDs, idempotencia, `AC-SYN-001`, límites) + `test_d5_contracts.py` (7: AST F13-ext/D4, pureza dominio, markers, perf).
- Markers `arch`/`repro`/`perf` (+registro `perf`); CI ejecuta lo mismo. Docs: `TEST-SUITE.md` canónico (+matriz 16 áreas), `STRATEGY.md` como puntero. Cero eliminaciones (auditoría: sin duplicados reales).
- Evidencia: 20 nuevos verdes + regresión 134 passed × 3 hash-seeds. Run `36232344763` (`c14c317`) verde 4/4 + package. Roadmap: D5 CERTIFICADA, D6 SIGUIENTE.

## Unreleased — Fase D4: Pipeline CI/build (CERTIFICADA)
- Workflow único `.github/workflows/ci.yml`: matriz windows/ubuntu × py3.12/3.13, install desde `requirements-lock.txt`, `compileall`, `pytest -m "not external"`, job `package` con `python -m build` y artefacto `dist/`. Sin bypasses, sin secretos, sin dependencias de producto.
- Tests `test_d4_pipeline.py` (7, stdlib, sin red): triggers, sin bypasses, lock pineado, pytest ejecuta, fallo→rc!=0, build declarado, árbol limpio.
- Docs `docs/testing/CI.md` + `GATE-D4-CERTIFICATION.md`. Evidencia local: 58 passed regresión, build real sdist+whl en venv aislado. Runs del proveedor: #1 fallo setup (Qt/ubuntu, corregido), #2 un solo fallo preexistente `html_cp1252` (divergencia manylinux-lxml, documentada) → `tests/conftest.py` con tabla §14 (xfail estricto en linux + skip por sonda symlink), sin tocar ficheros certificados → Run `36133175963` (`6bdd27b`) verde en las 4 celdas + package (ver gate). Roadmap: D4 CERTIFICADA, D5 SIGUIENTE.

## Unreleased — Fase F13-ext: Sync determinista 2 PCs (CERTIFICADA)
- Motor puro `domain/sync.py`: LWW `(ms, device)`, digest canónico, tombstones, idempotencia `sync(S',R)=S'`, protocolo `f13ext-sync/1`, sin CRDT.
- Aplicación `application/sync.py`: identidad estable `sync.device_id`, adaptadores preferences/saved_searches/quick_notes, verify interno.
- Infraestructura: migración 015 (`sync_state`+`sync_log`), `FileTransport` con límites y rechazo `AC-SYN-001`, wiring en facade.
- Tests `test_f13ext_sync.py`: 12/12 normativos. Docs: `F13EXT-SYNC.md` + `GATE-F13EXT-CERTIFICATION.md`. Roadmap: F13-ext CERTIFICADA, D4 SIGUIENTE.

## Unreleased — Fase F4.1: Gestion-Academica integrada (2026-09-23)
- Modelo académico centrado en la asignatura: estados CURSANDO/APROBADA/SUSPENDIDA/NO_CURSANDO, Home/Carrera/detalle de asignatura.
- Evaluación esquema/bloque/componente/nota mínima en Decimal (golden 400 casos vs Gestion real).
- Documentos en contexto de asignatura sobre CAS+FTS, espacios de estudio, recursos externos solo-URL, ICS, guía docente sobre F3/F3.1.
- Migración Gestion → AcademicCore: dry-run, snapshot, transacción única, idempotente, sin pérdidas, determinista.
- Cierre: profesores sin fusión por nombre, restore de backup verificado, arnés de certificación real. Gate: F4.1 NOT CERTIFIED hasta ejecutar el arnés sobre la instalación real (fallo F3 golden preexistente por libxml2). Ver `docs/gates/GATE-F4.1-CERTIFICATION.md`.

## 0.18.0 — Fase F8-I: BJT Ebers-Moll Nonlinear DC Operating Point (2026-09-16)
- Bipolar Junction Transistor (BJT) model under classic Ebers-Moll equations for NPN and PNP polarities.
- Exact coupled $3 \times 3$ analytical Jacobian without numerical approximations.
- Invariant matrix properties: $\sum_i J_{ij} = 0$ (KCL conservation), $\sum_j J_{ij} = 0$ (reference voltage shift invariance).
- Strict `Decimal` physical calculations (`prec=50`, `prec=80`) and zero `float` policy (verified via AST audit).
- Robust exponential damping and clamping ($V_{\text{clamp}} = 100 \cdot V_T$) with geometric bisection line-search.
- 15 canonical circuit topologies verified (B1–B15: fixed bias, self-bias, emitter follower, common base, PNP common emitter, saturation, reverse active, current mirror, differential pair, Darlington pair, inverter switch, BJT+diode, BJT+dependent sources, BJT+OpAmp, BJT+transformer).
- Multi-BJT scaling matrix ($N=1..64$) with constant 7 Newton iterations.
- Automated cross-validation with ngspice 47 (< $10^{-4}$ relative error).
- Gate F8-I: 143 passed (69 F8-H diode + 33 F8-I BJT physics + 41 F8-I nonlinear MNA circuits).

## 0.17.0 — Fase F8-H: Shockley Diode Nonlinear DC Operating Point (2026-09-16)
- Nonlinear DC MNA solver with damped Newton-Raphson and geometric backtracking.
- Shockley diode companion model and analytical conductance $g_d = \frac{I_S}{n V_T} \exp(V_d / n V_T)$.
- Physical block convergence criteria: KCL residual $\le 10^{-12}\text{ A}$, aux residual $\le 10^{-9}\text{ V}$.
- Full conservation checks: KCL, KVL, Tellegen power balance.
- Automated cross-validation with ngspice 47.
- Gate F8-H: 69 passed.

## 0.16.0 — Fase F8-G: Ideal Transformers & Two-Port Network Parameters (2026-09-16)
- Ideal transformer model with turns ratio $n$ ($V_1 = n V_2, I_2 = -n I_1$).
- Auxiliary variables for primary and secondary winding currents in MNA.
- Linear two-port matrix parameter extraction ($Z, Y, H, ABCD$) via test-source excitation.
- Gate F8-G: CERTIFIED (`GATE-F8G.md`).

## 0.15.0 — Fase F8-F: Ideal Operational Amplifiers / Nullors (2026-09-15)
- Ideal op-amp model (nullor: $V_+ = V_-$, $i_+ = i_- = 0$) for DC and AC steady-state MNA.
- Auxiliary output current unknown $i_o$ leaving op-amp output pin into ground.
- Strict singularity and degenerate topology classification via `math.linsolve` rank analysis.
- Gate F8-F: CERTIFIED (`GATE-F8F.md`).

## 0.14.0 — Fase F8-E: Linear Dependent Sources (2026-09-14)
- All four linear controlled sources: VCVS ($E$), VCCS ($G$), CCVS ($H$), CCCS ($F$).
- Current control graph cycle detection (`check_control_cycles`) and `CircularControlError`.
- Deterministic control current resolution and DC/AC stamping.
- Gate F8-E: CERTIFIED (`GATE-F8E.md`).

## 0.13.0 — Fase F8-D: AC Small-Signal Phasor Simulation Suite (2026-09-14)
- F8-D1: Exact and arbitrary-precision complex arithmetic (`DecimalComplex`, `FractionComplex`).
- F8-D2: Complex linear system solver with Rouché-Capelli rank analysis.
- F8-D3: General AC MNA in steady-state with peak phasors ($e^{+j\omega t}$) for $R, L, C, V, I$.
- F8-D4: Complex power $S = P + jQ$, apparent power, power factor, Tellegen balance in AC.
- F8-D5: AC driving-point impedance/admittance and transfer functions.
- F8-D6: Frequency sweep engine and Bode plots (dB magnitude, phase unwrap, $-3\text{ dB}$ cutoff brackets).
- F8-D7: Complex AC Thévenin and Norton equivalents ($Z_{th}, V_{th}, I_{no}$).
- F8-D8: Resonance detection by bracket search and reactive/dissipated energy quality factor ($Q$).
- Gates F8-D1 through F8-D8: CERTIFIED.

## 0.12.0 — Fase F8-C: DC Thévenin & Norton Reductions (2026-09-13)
- General active one-port network reduction via test-source injection and open-circuit voltage calculation.
- Certified equivalence validation across arbitrary linear resistive networks.
- Gate F8-C: CERTIFIED (`GATE-F8C.md`).

## 0.11.0 — Fase F8-B: General Linear DC MNA Solver (2026-09-13)
- Exact rational MNA solver over `fractions.Fraction` for $R, V, I, E, G, H, F, O$.
- Machine-zero KCL/KVL residuals and exact power balance.
- Gate F8-B: CERTIFIED (`GATE-F8B.md`).

## 0.10.0 — Fase F8-A: Electronics Knowledge Core (2026-09-13)
- Canonical circuit model extensions, models registry, validation contracts.
- Gate F8-A: CERTIFIED (`GATE-F8A.md`).

## 0.9.0 — Fase F7-B: Simulation Suite Hardening (2026-09-13)
- Hardened external ngspice 47 subprocess execution, timeout management, stdout/stderr isolation.
- Report F7-B8: CERTIFIED (`F7-B8-HARDENING-REPORT.md`).

## 0.8.0 — F7-A Simulation Runtime Foundation (2026-09-12)
- ngspice runtime discovery, version verification, isolated execution,
  stdout/stderr/exit capture, timeout, cancellation and cleanup.
- Windows setup/runtime documentation and separate external integration test.

## 0.7.0 — Fase 6 Engineering Foundation (2026-09-12)
- Decimal quantities, SI units/prefixes/dimensions and safe equation parser.
- Deterministic electrical calculations with provenance digests.
- Circuit topology (components/pins/nets), canonical netlists and typed models.
- SQLite migration 010, engineering repository/service, Authoring links and
  structured Engineering UI.
- Simulation boundary only: Null/Mock backends; no SPICE or subprocess.
- Gate F6: 205 passed, 2 skipped.

## 0.6.0 — Fase 5 Authoring Engine (2026-09-12)
- Command model (7 deterministic commands + undo/redo) + lifecycle +
  structured validation + 5 AST templates + in-document search.
- `document` resource kind + migration 009 (authored lifecycle, doc_links) +
  versioning/autosave/copy-paste/academic links service + Authoring UI tab.
- Round-trip battery (MD+HTML, documented equivalence) + F3 compat golden.
- Fidelity fixes shared with F3 (image targets, bare-inline items, math spans).
- Gate F5: 174 passed, 2 skipped (145 F0–F4 + 29 F5).

## 0.5.0 — Fase 4 Academic Management (2026-09-12)
- Gestion audit + reuse map (concept-only, no code copied).
- Generic gradebook (scales/weights/optional/partial, Decimal) beside F1
  engine (ADR-0016); results service; planning queries; JSON import/export;
  safe deletes + prerequisites; migration 008 (additive).
- Facade (`AcademicApp`) + `ui/` workspace (tree, 5 tabs, dialogs).
- Gate F4: 145 passed, 2 skipped (123 F0–F3 + 22 F4).

## 0.4.0 — Fase 3 Document + PDF Engine (2026-09-12)
- Conversor audit (20 comps) + selective reuse (math 1:1, tables, images,
  sanitize, metadata, encoding) with equivalence tests vs original module.
- Canonical AST (19 kinds, v1, validated, deterministic JSON) + HTML/MD
  parsers + MD/HTML renderers + doc derivations (007) + provenance chain.
- PDF engine (pypdf native: inspect/merge/split/rotate/extract/PDF→AST) +
  Stirling v2.14.3 research, runtime manager, API backend (mock-verified,
  live SIMULATED). ADR-0015. Gate F3: 123 passed, 2 skipped.

## 0.3.0 — Fase 2 Resource Engine (2026-09-12)
- Ports (`BlobStore/Extractor/Indexer/Records`) + `Resource/Version/Provenance`.
- CAS: streaming SHA-256, atomic, integrity-checked, traversal-safe.
- Adapters file/md/html/pdf (+ZIP refused); pipeline idempotente + versiones.
- FTS5 derivado con rebuild + filtros; tab Resources; `ingest.max_bytes`.
- ADR-0013/0014; gate F2: 81 passed (41 F0/F1 + 40 F2).

## 0.2.0 — Fase 1 Domain & Academic Foundation (2026-09-12)
- Domain: 20 entidades (University→Subject→Topic/Assignment/Exam/Project/Lab/
  Task/Deadline/Grade/Tag/Bookmark/Annotation/StudySpace/Session/Notification),
  Term genérico, invariantes con DomainError.
- Identity: 16 kinds, slugify NFKD, IdAllocator + counters persistidos.
- Grading Decimal HALF_UP + equivalencia (ADR-0011); schedule/conflictos puros.
- Persistence: sqlite3 stdlib, 4 migraciones, repos explícitos (ADR-0012).
- Application: Academic/Grading/Schedule services + Search/Backup/AppLock.
- UI Qt validación (selectores, subjects CRUD, 4 tabs) + gate F1: 41 passed.

## 0.1.0 — Fase 0 foundation (2026-09-12)
- Audits: Conversor (monolito 6.051 lín + lab 16 módulos), Gestion (Flask,
  28 tablas, 152 rutas, 672 docs), Sistemes (91 fuentes, 2896 fórmulas,
  1092 tests) — full detail in `docs/migration/`.
- Architecture: modular monolith, 10 ADRs, domain v0, stable IDs, storage
  SQLite+CAS, engines interfaces (resource/document/pdf/ai/providers/
  engineering), Qt skeleton executable, config system, 6 test files.
- Gates: fast suite + migration contract + reproducibility + boundary test.
