"""F8-P3 transmission-line core (NEW): RLGC/lossless line, Z0/gamma,
Zin (sin/cos primary form), reflection, VSWR/RL.

Thin complex hyperbolic helpers (``_complex_sinh``/``_complex_cosh``/
``_complex_tanh``) are built ONLY on the certified ``decimal_sin``/
``decimal_cos``/``decimal_exp`` kernels (P2 ``_decimal_tan``
collocation pattern, gate §8) -- no second trig reducer, no second
exp engine. For a lossless line (``gamma = j*beta``) these reduce
exactly to the trigonometric form of gate §6/§8 without a second
implementation: with ``a = 0``, ``sinh(a) = 0`` and ``cosh(a) = 1``
collapse the general complex form onto ``sin(beta*l)``/``cos(beta*l)``
bit-for-bit (same Decimal path, no branch).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.response import decimal_exp
from academic_core.domain.engineering.math import DecimalComplex, decimal_cos, decimal_sin, make_context
from academic_core.domain.engineering.rf.primitives import angular_frequency

ENGINE_VERSION = "f8p3-rf/1"


def _require_decimal(value, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, f"{name} must be a Decimal")
    if not value.is_finite():
        raise ControlError(ControlStatus.INVALID, f"{name} must be finite")
    return value


def _require_complex(value, name: str) -> DecimalComplex:
    if not isinstance(value, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, f"{name} must be DecimalComplex")
    if not value.re.is_finite() or not value.im.is_finite():
        raise ControlError(ControlStatus.INVALID, f"{name} must be finite")
    return value


def _complex_sinh_cosh(z: DecimalComplex, ctx) -> tuple[DecimalComplex, DecimalComplex]:
    """sinh(a+jb) = sinh(a)cos(b) + j*cosh(a)sin(b);
    cosh(a+jb) = cosh(a)cos(b) + j*sinh(a)sin(b), via real exp/sin/cos."""
    a, b = z.re, z.im
    ea = decimal_exp(a, ctx)
    ea_inv = ctx.divide(Decimal(1), ea)
    sinh_a = ctx.divide(ctx.subtract(ea, ea_inv), Decimal(2))
    cosh_a = ctx.divide(ctx.add(ea, ea_inv), Decimal(2))
    cos_b = decimal_cos(b, ctx)
    sin_b = decimal_sin(b, ctx)
    sinh_z = DecimalComplex(ctx.multiply(sinh_a, cos_b), ctx.multiply(cosh_a, sin_b))
    cosh_z = DecimalComplex(ctx.multiply(cosh_a, cos_b), ctx.multiply(sinh_a, sin_b))
    return sinh_z, cosh_z


def _complex_tanh(z: DecimalComplex, ctx) -> DecimalComplex:
    sinh_z, cosh_z = _complex_sinh_cosh(z, ctx)
    if cosh_z.is_zero_exact():
        raise ControlError(ControlStatus.SINGULAR, "tanh singular (cosh == 0)")
    return sinh_z / cosh_z


@dataclass(frozen=True)
class PropagationConstant:
    """gamma = alpha + j*beta. alpha: Np/m label, beta: rad/m label --
    both share the 1/m dimension (documentary, not Quantity targets,
    gate §7)."""

    alpha: Decimal
    beta: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.alpha, "alpha")
        _require_decimal(self.beta, "beta")
        if self.alpha < 0:
            raise ControlError(ControlStatus.INVALID, "alpha must be >= 0")

    def as_complex(self) -> DecimalComplex:
        return DecimalComplex(self.alpha, self.beta)


@dataclass(frozen=True)
class Load:
    """Tagged load model: open/short are KINDS (never huge numbers)."""

    kind: str  # "impedance" | "open" | "short" | "matched"
    impedance: DecimalComplex | None = None
    reference: DecimalComplex | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("impedance", "open", "short", "matched"):
            raise ControlError(ControlStatus.INVALID, f"unknown load kind {self.kind!r}")
        if self.kind == "impedance":
            if self.impedance is None:
                raise ControlError(ControlStatus.INVALID, "impedance load needs a value")
            _require_complex(self.impedance, "load impedance")
        elif self.impedance is not None:
            raise ControlError(ControlStatus.INVALID, f"{self.kind} load must not carry impedance")
        if self.kind == "matched":
            if self.reference is None:
                raise ControlError(ControlStatus.INVALID, "matched load needs a reference Z0")
            _require_complex(self.reference, "matched reference")
        elif self.reference is not None:
            raise ControlError(ControlStatus.INVALID, f"{self.kind} load must not carry reference")


def load_impedance(z: DecimalComplex) -> Load:
    return Load("impedance", impedance=z)


def load_open() -> Load:
    return Load("open")


def load_short() -> Load:
    return Load("short")


def load_matched(z0: DecimalComplex) -> Load:
    return Load("matched", reference=z0)


@dataclass(frozen=True)
class LineRLGC:
    """Telegrapher line, per-unit-length R,L,G,C (finite Decimals >= 0),
    length l (m, >=0), frequency f (Hz, >0). Z0 is always DERIVED."""

    r: Decimal
    l_per_m: Decimal
    g: Decimal
    c: Decimal
    length: Decimal
    frequency: Decimal

    def __post_init__(self) -> None:
        for name, val in (("R", self.r), ("L", self.l_per_m), ("G", self.g), ("C", self.c)):
            _require_decimal(val, name)
            if val < 0:
                raise ControlError(ControlStatus.INVALID, f"{name} must be >= 0")
        _require_decimal(self.length, "length")
        if self.length < 0:
            raise ControlError(ControlStatus.INVALID, "length must be >= 0")
        _require_decimal(self.frequency, "frequency")
        if self.frequency <= 0:
            raise ControlError(ControlStatus.INVALID, "frequency must be > 0")

    def omega(self, ctx=None) -> Decimal:
        return angular_frequency(self.frequency)

    def series_impedance(self, ctx=None) -> DecimalComplex:
        """Z' = R + j*omega*L per unit length."""
        c = ctx or make_context()
        w = self.omega(c)
        return DecimalComplex(self.r, c.multiply(w, self.l_per_m))

    def shunt_admittance(self, ctx=None) -> DecimalComplex:
        """Y' = G + j*omega*C per unit length."""
        c = ctx or make_context()
        w = self.omega(c)
        return DecimalComplex(self.g, c.multiply(w, self.c))

    def characteristic_impedance(self, ctx=None) -> DecimalComplex:
        """Z0 = sqrt(Z'/Y'), principal branch (REUSEd DecimalComplex.sqrt)."""
        c = ctx or make_context()
        zp = self.series_impedance(c)
        yp = self.shunt_admittance(c)
        if yp.is_zero_exact():
            raise ControlError(ControlStatus.SINGULAR, "Z0 singular: Y' == 0")
        z0 = (zp / yp).sqrt()
        if z0.is_zero_exact():
            raise ControlError(ControlStatus.SINGULAR, "Z0 == 0 (degenerate line)")
        return z0

    def propagation_constant(self, ctx=None) -> PropagationConstant:
        """gamma = sqrt(Z'*Y'). Lossless limit (R=G=0) is exact: alpha=0."""
        c = ctx or make_context()
        if self.r == 0 and self.g == 0:
            w = self.omega(c)
            beta = c.sqrt(c.multiply(self.l_per_m, self.c))
            beta = c.multiply(w, beta)
            return PropagationConstant(Decimal(0), beta)
        zp = self.series_impedance(c)
        yp = self.shunt_admittance(c)
        gamma = (zp * yp).sqrt()
        return PropagationConstant(gamma.re, gamma.im)

    def electrical_length(self, ctx=None) -> Decimal:
        """theta = beta*l, rad label."""
        c = ctx or make_context()
        gamma = self.propagation_constant(c)
        return c.multiply(gamma.beta, self.length)

    def attenuation_factor(self, ctx=None) -> Decimal:
        """e^{-alpha*l} via REUSEd decimal_exp."""
        c = ctx or make_context()
        gamma = self.propagation_constant(c)
        return decimal_exp(c.minus(c.multiply(gamma.alpha, self.length)), c)

    def phase_delay(self, ctx=None) -> Decimal:
        """beta*l/omega, seconds."""
        c = ctx or make_context()
        theta = self.electrical_length(c)
        w = self.omega(c)
        if w == 0:
            raise ControlError(ControlStatus.SINGULAR, "phase delay singular: omega == 0")
        return c.divide(theta, w)


@dataclass(frozen=True)
class LineZGamma:
    """Alternative constructor from measured (Z0, gamma, l). Z0 complex
    allowed. Equivalent representation to LineRLGC (gate §6)."""

    z0: DecimalComplex
    gamma: PropagationConstant
    length: Decimal

    def __post_init__(self) -> None:
        _require_complex(self.z0, "Z0")
        if self.z0.is_zero_exact():
            raise ControlError(ControlStatus.SINGULAR, "Z0 == 0")
        if not isinstance(self.gamma, PropagationConstant):
            raise ControlError(ControlStatus.INVALID, "gamma must be a PropagationConstant")
        _require_decimal(self.length, "length")
        if self.length < 0:
            raise ControlError(ControlStatus.INVALID, "length must be >= 0")

    def characteristic_impedance(self, ctx=None) -> DecimalComplex:
        return self.z0

    def propagation_constant(self, ctx=None) -> PropagationConstant:
        return self.gamma

    def electrical_length(self, ctx=None) -> Decimal:
        c = ctx or make_context()
        return c.multiply(self.gamma.beta, self.length)

    def attenuation_factor(self, ctx=None) -> Decimal:
        c = ctx or make_context()
        return decimal_exp(c.minus(c.multiply(self.gamma.alpha, self.length)), c)


LineLike = LineRLGC | LineZGamma


def gamma_length(line: LineLike, ctx=None) -> DecimalComplex:
    """gamma * l as a single DecimalComplex (used by Zin/ABCD)."""
    c = ctx or make_context()
    gamma = line.propagation_constant(c)
    length = line.length
    return DecimalComplex(c.multiply(gamma.alpha, length), c.multiply(gamma.beta, length))


@dataclass(frozen=True)
class ImpedanceResult:
    """Zin outcome. FINITE carries value; INFINITE is a behavioral open
    (value=None); SINGULAR marks a zero-denominator degeneracy."""

    status: str  # "FINITE" | "INFINITE" | "SINGULAR"
    value: DecimalComplex | None

    def require_finite(self) -> DecimalComplex:
        if self.status != "FINITE" or self.value is None:
            raise ControlError(ControlStatus.UNSUPPORTED, f"Zin not finite ({self.status})")
        return self.value


def input_impedance(line: LineLike, load: Load, ctx=None) -> ImpedanceResult:
    """Zin via the sin/cos-equivalent cosh/sinh primary form (gate §6):

        Zin = Z0*(ZL*cosh(gl) + Z0*sinh(gl)) / (Z0*cosh(gl) + ZL*sinh(gl))

    l = 0 is the exact identity Zin = ZL (tested). gamma = 0 collapses
    exactly through the same cosh/sinh path (cosh=1, sinh=0). Open/short
    loads use the derived degenerate forms (Z0/tanh, Z0*tanh) rather
    than a numeric infinity substitute.
    """
    c = ctx or make_context()
    z0 = line.characteristic_impedance(c)
    gl = gamma_length(line, c)

    if line.length == 0:
        if load.kind == "impedance":
            return ImpedanceResult("FINITE", load.impedance)
        if load.kind == "matched":
            return ImpedanceResult("FINITE", load.reference)
        if load.kind == "short":
            return ImpedanceResult("FINITE", DecimalComplex.zero())
        if load.kind == "open":
            return ImpedanceResult("INFINITE", None)
        raise AssertionError("unreachable load kind")  # pragma: no cover

    sinh_gl, cosh_gl = _complex_sinh_cosh(gl, c)

    if load.kind == "short":
        denom = cosh_gl
        if denom.is_zero_exact():
            return ImpedanceResult("INFINITE", None)
        return ImpedanceResult("FINITE", z0 * (sinh_gl / denom))

    if load.kind == "open":
        denom = sinh_gl
        if denom.is_zero_exact():
            return ImpedanceResult("SINGULAR", None)
        return ImpedanceResult("FINITE", z0 * (cosh_gl / denom))

    zl = load.impedance if load.kind == "impedance" else load.reference
    assert zl is not None
    numerator = z0 * (zl * cosh_gl + z0 * sinh_gl)
    denominator = z0 * cosh_gl + zl * sinh_gl
    if denominator.is_zero_exact():
        return ImpedanceResult("SINGULAR", None)
    return ImpedanceResult("FINITE", numerator / denominator)


@dataclass(frozen=True)
class ReflectionResult:
    status: str  # "FINITE" | "SINGULAR"
    value: DecimalComplex | None

    def require_finite(self) -> DecimalComplex:
        if self.status != "FINITE" or self.value is None:
            raise ControlError(ControlStatus.SINGULAR, "reflection coefficient singular")
        return self.value


def reflection_coefficient(load: Load, z0: DecimalComplex, ctx=None) -> ReflectionResult:
    """Gamma = (ZL - Z0)/(ZL + Z0), Z0 possibly complex. open -> +1
    exact, short -> -1 exact, matched(Z0ref==Z0) -> 0 exact. ZL+Z0==0
    (active anti-matched edge) -> SINGULAR."""
    c = ctx or make_context()
    _require_complex(z0, "Z0")
    if load.kind == "open":
        return ReflectionResult("FINITE", DecimalComplex.one())
    if load.kind == "short":
        return ReflectionResult("FINITE", -DecimalComplex.one())
    zl = load.impedance if load.kind == "impedance" else load.reference
    assert zl is not None
    denom = zl + z0
    if denom.is_zero_exact():
        return ReflectionResult("SINGULAR", None)
    return ReflectionResult("FINITE", (zl - z0) / denom)


def load_from_reflection(gamma: DecimalComplex, z0: DecimalComplex, ctx=None) -> ImpedanceResult:
    """Inverse: ZL = Z0*(1+Gamma)/(1-Gamma). Gamma=+1 -> INFINITE
    (open), never a numeric divide-by-zero fallthrough."""
    _require_complex(gamma, "Gamma")
    _require_complex(z0, "Z0")
    one = DecimalComplex.one()
    denom = one - gamma
    if denom.is_zero_exact():
        return ImpedanceResult("INFINITE", None)
    return ImpedanceResult("FINITE", z0 * ((one + gamma) / denom))
