"""F8-P3: RF and transmission-line conducted-network mathematics.

Design gate: ``docs/gates/GATE-F8P3-DESIGN.md``. Conducted/network RF
math over certified engines (``control.errors``, ``control.response``,
``math.*``, ``units``, ``metrology.o5_traceability``) -- telegrapher
lines, two-port Z/Y/ABCD, power-wave S-parameters (Kurokawa), Smith
mathematics, closed-form matching and RF margins. Antennas, radiated
propagation and satcom link-budget synthesis are explicitly OUT
(reserved for F8-P5).

Security: this package contains no dynamic-execution, no dynamic
attribute access, no filesystem/process/network primitives, no
unsafe deserialization, and no third-party numeric library or the
stdlib math module -- verified by an AST-based test (gate §24). Every
value stays inside the Decimal/DecimalComplex/Fraction/RationalComplex
exactness discipline (gate §6/§8).
"""

from __future__ import annotations

ENGINE_VERSION = "f8p3-rf/1"

__all__ = ["ENGINE_VERSION"]
