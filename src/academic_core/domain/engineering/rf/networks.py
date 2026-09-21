"""F8-P3 two-port networks (NEW): Z/Y/ABCD matrices, certified
conversions, ABCD cascade.

Sign convention frozen from F8-G (``ac/twoport.py``, gate §13/§30,
verbatim, never reinterpreted): ``V1 = A*V2 - B*I2``,
``I1 = C*V2 - D*I2`` (I1, I2 both entering). ``rf`` never imports
``ac/twoport.py`` (it is a live-circuit MNA extraction layer, not a
closed-form engine, and importing it would create a forbidden
``rf -> ac`` DAG edge); this module derives its own closed-form Z/Y/
ABCD matrices independently, reusing only the frozen sign convention
and the ``_UNITS``-shaped table (z: Ohm, y: S, abcd: 1/Ohm/S/1).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import DecimalComplex, make_context
from academic_core.domain.engineering.rf.lines import LineLike, _complex_sinh_cosh, gamma_length

ENGINE_VERSION = "f8p3-rf/1"

MAX_CASCADE_BLOCKS = 64

_UNITS = {
    "z": (("ohm", "ohm"), ("ohm", "ohm")),
    "y": (("S", "S"), ("S", "S")),
    "abcd": (("1", "ohm"), ("S", "1")),
}


def _check_finite(z: DecimalComplex, name: str) -> DecimalComplex:
    if not isinstance(z, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, f"{name} must be DecimalComplex")
    if not z.re.is_finite() or not z.im.is_finite():
        raise ControlError(ControlStatus.INVALID, f"{name} must be finite")
    return z


@dataclass(frozen=True)
class TwoPort:
    """A closed-form 2x2 two-port in one of the representations
    ("z" | "y" | "abcd"). Entries are always named a11..a22 with the
    kind carrying their physical meaning (Z11/Y11/A, etc.)."""

    kind: str
    a11: DecimalComplex
    a12: DecimalComplex
    a21: DecimalComplex
    a22: DecimalComplex

    def __post_init__(self) -> None:
        if self.kind not in ("z", "y", "abcd"):
            raise ControlError(ControlStatus.INVALID, f"unknown two-port kind {self.kind!r}")
        for name, val in (("a11", self.a11), ("a12", self.a12), ("a21", self.a21), ("a22", self.a22)):
            _check_finite(val, f"{self.kind}.{name}")

    def determinant(self, ctx=None) -> DecimalComplex:
        c = ctx or make_context()
        return self.a11 * self.a22 - self.a12 * self.a21

    def units(self) -> tuple:
        return _UNITS[self.kind]


def make_z(z11: DecimalComplex, z12: DecimalComplex, z21: DecimalComplex, z22: DecimalComplex) -> TwoPort:
    return TwoPort("z", z11, z12, z21, z22)


def make_y(y11: DecimalComplex, y12: DecimalComplex, y21: DecimalComplex, y22: DecimalComplex) -> TwoPort:
    return TwoPort("y", y11, y12, y21, y22)


def make_abcd(a: DecimalComplex, b: DecimalComplex, c_: DecimalComplex, d: DecimalComplex) -> TwoPort:
    return TwoPort("abcd", a, b, c_, d)


def z_to_y(z: TwoPort, ctx=None) -> TwoPort:
    """Y = Z^-1 (exact matrix inverse); singular -> SINGULAR."""
    if z.kind != "z":
        raise ControlError(ControlStatus.INVALID, "z_to_y needs a z two-port")
    det = z.determinant(ctx)
    if det.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "Z -> Y singular (det Z == 0)")
    return TwoPort("y", z.a22 / det, -z.a12 / det, -z.a21 / det, z.a11 / det)


def y_to_z(y: TwoPort, ctx=None) -> TwoPort:
    """Z = Y^-1 (exact matrix inverse); singular -> SINGULAR."""
    if y.kind != "y":
        raise ControlError(ControlStatus.INVALID, "y_to_z needs a y two-port")
    det = y.determinant(ctx)
    if det.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "Y -> Z singular (det Y == 0)")
    return TwoPort("z", y.a22 / det, -y.a12 / det, -y.a21 / det, y.a11 / det)


def z_to_abcd(z: TwoPort, ctx=None) -> TwoPort:
    """A=Z11/Z21, B=det(Z)/Z21, C=1/Z21, D=Z22/Z21 (derived from
    V1=A*V2-B*I2, I1=C*V2-D*I2 under the F8-G frozen sign convention);
    Z21 == 0 -> SINGULAR."""
    if z.kind != "z":
        raise ControlError(ControlStatus.INVALID, "z_to_abcd needs a z two-port")
    if z.a21.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "Z -> ABCD singular (Z21 == 0)")
    det = z.determinant(ctx)
    return TwoPort("abcd", z.a11 / z.a21, det / z.a21, DecimalComplex.one() / z.a21, z.a22 / z.a21)


def abcd_to_z(m: TwoPort, ctx=None) -> TwoPort:
    """Z11=A/C, Z12=det(ABCD)/C, Z21=1/C, Z22=D/C; C == 0 -> SINGULAR."""
    if m.kind != "abcd":
        raise ControlError(ControlStatus.INVALID, "abcd_to_z needs an abcd two-port")
    if m.a21.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "ABCD -> Z singular (C == 0)")
    det = m.determinant(ctx)
    return TwoPort("z", m.a11 / m.a21, det / m.a21, DecimalComplex.one() / m.a21, m.a22 / m.a21)


def y_to_abcd(y: TwoPort, ctx=None) -> TwoPort:
    c = ctx or make_context()
    return z_to_abcd(y_to_z(y, c), c)


def abcd_to_y(m: TwoPort, ctx=None) -> TwoPort:
    c = ctx or make_context()
    return z_to_y(abcd_to_z(m, c), c)


def reciprocal(t: TwoPort) -> bool:
    """Reciprocity: Z12==Z21 / Y12==Y21 (exact); for ABCD, det==1
    (AD-BC=1)."""
    if t.kind in ("z", "y"):
        return t.a12 == t.a21
    return t.determinant() == DecimalComplex.one()


def symmetric(t: TwoPort) -> bool:
    """Symmetry: Z11==Z22 / Y11==Y22; for ABCD, A==D."""
    if t.kind in ("z", "y"):
        return t.a11 == t.a22
    return t.a11 == t.a22


def line_abcd(line: LineLike, ctx=None) -> TwoPort:
    """ABCD_line = [[cosh(gl), Z0*sinh(gl)], [sinh(gl)/Z0, cosh(gl)]]
    (gate §15). Lossless collapses exactly to the cos/sin form via the
    shared ``_complex_sinh_cosh`` helper (no second implementation)."""
    c = ctx or make_context()
    z0 = line.characteristic_impedance(c)
    gl = gamma_length(line, c)
    sinh_gl, cosh_gl = _complex_sinh_cosh(gl, c)
    return TwoPort("abcd", cosh_gl, z0 * sinh_gl, sinh_gl / z0, cosh_gl)


def cascade_abcd(blocks: tuple, ctx=None) -> TwoPort:
    """ABCD_total = A . B . C ... (exact DecimalComplex matmul,
    deterministic left-to-right order). Only ABCD multiplies (gate
    §16 hard-stop: S never multiplies directly). Limit 64 blocks."""
    if not isinstance(blocks, tuple) or len(blocks) == 0:
        raise ControlError(ControlStatus.INVALID, "cascade needs a non-empty tuple of blocks")
    if len(blocks) > MAX_CASCADE_BLOCKS:
        raise ControlError(ControlStatus.INVALID, f"cascade exceeds MAX_CASCADE_BLOCKS={MAX_CASCADE_BLOCKS}")
    for b in blocks:
        if not isinstance(b, TwoPort) or b.kind != "abcd":
            raise ControlError(ControlStatus.INVALID, "cascade blocks must all be abcd two-ports")
    total = blocks[0]
    for b in blocks[1:]:
        total = TwoPort(
            "abcd",
            total.a11 * b.a11 + total.a12 * b.a21,
            total.a11 * b.a12 + total.a12 * b.a22,
            total.a21 * b.a11 + total.a22 * b.a21,
            total.a21 * b.a12 + total.a22 * b.a22,
        )
    return total
