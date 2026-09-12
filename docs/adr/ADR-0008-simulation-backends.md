# ADR-0008 — External simulation engines (SPICE/KiCad/LaTeX as backends)

Date: 2026-09-12 · Status: Accepted

## Decision
One canonical `Circuit` model → `to_netlist()` → pluggable backends
(ngspice/LTspice/KiCad) → `Result → Analysis`. Same for LaTeX/CircuitTikZ export.
Engines run as **external processes** (QProcess) with timeouts, temp-dir jails,
no shell interpolation.

## Rationale
Conversor audit: circuit physics is triple-implemented (Tk filters, Tk RLC, JS
MNA) with zero tests — must be unified, not copied. External backends give
certifiable results (`BENCHMARKED`) instead of home-grown solver claims.

## Consequences
- Never claim "equivalent to LTspice/KiCad" without benchmarks (status labels).
- MNA from lab JS is REWRITE in Python/TS with tests, not transliteration.
