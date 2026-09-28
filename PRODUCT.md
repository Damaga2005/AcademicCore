# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop
<!-- NOTE: init schema v1 allows only web/ios/android/adaptive; confirmed truth is PySide6 Qt desktop on Windows, offline-first. Recorded truthfully here so future work does not assume web. -->

## Users

Primary: electrical-engineering students doing coursework — building circuits, running DC/AC/nonlinear/small-signal simulations, resolving exercises, and taking timed assessments.

Secondary (repo-confirmed): instructors and auditors authoring question banks, grading deterministically, and reviewing mastery/adaptive plans and evidence.

## Product Purpose

AcademicCore is a high-precision, deterministic academic engineering, physics simulation, and verification platform. It bridges exact circuit physics, semiconductor modeling, curriculum governance, and high-integrity assessment without requiring an LLM for mathematical or physical answers.

Success means: exact reproducible solves, machine-zero residuals, KCL/KVL/Tellegen conservation, ngspice-cross-validated accuracy, crash-safe assessment sessions, and auditable mastery/adaptive progression.

## Positioning

Deterministic precision over convenience: exact rationals (`Fraction`) and 50–80 digit `Decimal` throughout the physical core and grading; zero-float invariant enforced by AST tripwires; every solved circuit auto-checks KCL/KVL/Tellegen down to 1e-24 W; continuous regression against ngspice 47 (<1e-4 relative, <0.05° phase); AI strictly pedagogical/explanatory, never physical or grading authority.

A neighboring simulator, LMS, or generic SPICE wrapper cannot truthfully copy this combination of exact arithmetic, conservation proofs, oracle verification, and deterministic assessment-to-mastery chain.

## Operating Context

Offline-first PySide6 Qt desktop on Windows, launched via `python -m academic_core` (`academic-core`). Entry: `src/academic_core/app.py` wiring Settings → AcademicApp facade → `AcademicMainWindow`.

Core workflows: circuit construction and MNA solves (linear DC, AC phasor, damped Newton-Raphson nonlinear DC, small-signal linearized AC); Thévenin/Norton reductions; Bode/resonance sweeps; 7-tier curriculum tree (University → Degree → Year → Term → Subject → Topic → Section) with prerequisite DAG and weighted gradebook; D6 neutral question banks → D7 ingestion → F9 sessions/correction → F10 mastery → F11 adaptive plans; document AST authoring with LaTeX, Markdown/HTML roundtrip, native PDF, CAS SHA-256, undo/redo.

Storage: SQLite (`academic.db`, FTS5, forward-only migrations 001–021) plus CAS; ngspice 47 via sandboxed subprocess oracle; deterministic seed permutations for exam variants.

## Capabilities and Constraints

Confirmed: unified MNA solver; R/L/C/V/I/E/G/H/F/O/T/D/Q components; Shockley diode and Ebers-Moll NPN/PNP with 3×3 analytical Jacobians and KCL/reference-shift invariants; AC power, posters claim `S = P + jQ`, power factor, resonance Q; session state machine NOT_STARTED → IN_PROGRESS → SUBMITTED/EXPIRED/CANCELLED with ISO-8601 expiry recovery; strict `Decimal` scoring (partial credit, penalties, clamping, thresholds); `f9-correct/1` over 7 D6 types with frozen snapshots and immutable evidence; `f10-beta/1` Beta-Binomial mastery; `f11-adaptive/1` deterministic planner (60/20/15/5, stable tie-break, caps, prerequisites, idempotent); F12 tutor with verified/unverified/rejected chain and LLM=OFF via NullProvider; F13/F13-ext sync (LWW, local-folder transport); F16 orbital mechanics; zero `eval`/`exec`/`compile`; Python 3.11–3.14; 4700+ tests.

Constraints: offline core solve/grade must not require cloud or LLM; float banned from physical/grading paths; no persistence parallel to app for D6; one-transaction applies with post-commit verification.

Explicitly undecided: none for core scope; web/mobile port out of scope per 2026-09-28 confirmation (offline desktop only).

## Brand Commitments

Name: AcademicCore. MIT license (`LICENSE`, `THIRD_PARTY_NOTICES.md`). Deterministic Sovereignty Principle and Zero-Float Invariant from `README.md`. Manifesto: build small verify completely; keep deterministic; eliminate drift; Tellegen/KCL/KVL inviolable; AI for pedagogy never authority; provable provenance and reproducibility. No binding visual assets, fonts, or palette confirmed.

## Evidence on Hand

Real: `README.md` recipes (BJT OP, Bode, F9+F10 session, F11 plan); `src/academic_core/` domain/application/infrastructure; `docs/gates/GATE-*.md`, `docs/phase-reports/`, `docs/architecture/`, `docs/adr/`; `F7-B8-HARDENING-REPORT.md`; `tests/` battery.

Absences future work must not fabricate: no testimonials, customers, benchmarks beyond gated reports, pricing, or deployment claims.

## Product Principles

1. Determinism first: same inputs reproduce same outputs, digests, and plans.
2. Exactness is non-negotiable: no float drift in physics or scores.
3. Verify completely: conservation laws and oracle checks ship with every solve.
4. Pedagogy without authority drift: AI explains, deterministic engines decide.
5. Provenance always: digests, frozen snapshots, idempotent applies, auditable history.
