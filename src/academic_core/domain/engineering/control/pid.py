"""F8-P1 PID compensators + Ziegler-Nichols tuning (NEW).

Parallel: C(s) = Kp + Ki/s + Kd s.
Ideal: C(s) = Kp (1 + 1/(Ti s) + Td s).
Series: C(s) = Kp (1 + 1/(Ti s)) (1 + Td s) (documented exact definition).
Ziegler-Nichols ultimate table with documented constants (not magic).

Sub-design resolution D-R1: a pure-derivative PID is mathematically
improper (numerator degree 2 over denominator degree 1) and therefore
cannot inhabit the proper-only TransferFunctionTF type. Compensators
live in the exact PIDController type; loop/closed-loop formation stays
exact rational arithmetic and yields proper TFs whenever the plant
provides enough relative degree. Derivative-free (P/PI) compensators
convert to TF exactly via as_tf().
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.margins import phase_crossover_bisection
from academic_core.domain.engineering.control.tf import (
    TransferFunctionTF,
    feedback,
    series,
)
from academic_core.domain.engineering.math import decimal_pi, make_context


def _req_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ControlError(ControlStatus.INVALID, label + " rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise ControlError(ControlStatus.INVALID, label + " bad string") from exc
    else:
        raise ControlError(ControlStatus.INVALID, label + " must be Decimal/int/str")
    if not out.is_finite():
        raise ControlError(ControlStatus.INVALID, label + " must be finite")
    return out


@dataclass(frozen=True)
class PIDController:
    """Exact PID compensator (validation-only post-init).

    Parallel parametrisation (Kp, Ki, Kd) with the ideal/series source
    recorded in ``form`` plus (Ti, Td) when applicable. Pure-derivative
    forms are improper as rational functions; they convert to TF only
    through loop formation with a plant of sufficient relative degree.
    """

    kp: Decimal
    ki: Decimal
    kd: Decimal
    form: str = "parallel"
    ti: Decimal | None = None
    td: Decimal | None = None

    def __post_init__(self) -> None:
        for label, item in (("Kp", self.kp), ("Ki", self.ki), ("Kd", self.kd)):
            if isinstance(item, bool) or not isinstance(item, Decimal):
                raise ControlError(ControlStatus.INVALID, label + " must be Decimal")
            if not item.is_finite():
                raise ControlError(ControlStatus.INVALID, label + " must be finite")
        if self.form not in ("parallel", "ideal", "series", "ziegler-nichols"):
            raise ControlError(ControlStatus.INVALID, "unknown PID form")

    def is_proper_tf(self) -> bool:
        return self.kd == 0

    def as_tf(self) -> TransferFunctionTF:
        """Exact TF conversion (derivative-free P/PI only)."""
        if self.kd != 0:
            raise ControlError(
                ControlStatus.UNSUPPORTED,
                "pure-derivative PID is improper; form the loop with a plant instead",
            )
        return TransferFunctionTF.create((self.kp, self.ki), (Decimal(1), Decimal(0)))

    def loop_with(self, plant: TransferFunctionTF) -> TransferFunctionTF:
        """Exact loop L = C * P as a proper TF (plant must supply relative degree)."""
        if not isinstance(plant, TransferFunctionTF):
            raise ControlError(ControlStatus.INVALID, "loop formation needs a plant TF")
        from academic_core.domain.engineering.control.poly import make_polynomial

        if self.kd == 0:
            num_c = make_polynomial((self.kp, self.ki))
        else:
            num_c = make_polynomial((self.kd, self.kp, self.ki))
        den_c = make_polynomial((Decimal(1), Decimal(0)))
        num = num_c.multiply(plant.num)
        den = den_c.multiply(plant.den)
        # The proper-TF constructor re-validates: a plant without enough
        # relative degree yields INVALID here, never a silent improper loop.
        return TransferFunctionTF(num=num, den=den)

    def closed_with(self, plant: TransferFunctionTF) -> TransferFunctionTF:
        """Exact unity-feedback closed loop with this compensator."""
        return feedback(self.loop_with(plant))

    def to_dict(self) -> dict:
        return {
            "form": self.form,
            "kp": str(self.kp),
            "ki": str(self.ki),
            "kd": str(self.kd),
            "ti": "" if self.ti is None else str(self.ti),
            "td": "" if self.td is None else str(self.td),
        }


def pid_parallel(kp: object, ki: object, kd: object) -> PIDController:
    return PIDController(kp=_req_decimal(kp, "Kp"), ki=_req_decimal(ki, "Ki"),
                         kd=_req_decimal(kd, "Kd"), form="parallel")


def pid_ideal(kp: object, ti: object, td: object) -> PIDController:
    """Ideal form stored exactly as (Kp, Ki = Kp/Ti, Kd = Kp Td)."""
    p = _req_decimal(kp, "Kp")
    ti_d = _req_decimal(ti, "Ti")
    td_d = _req_decimal(td, "Td")
    if ti_d <= 0:
        raise ControlError(ControlStatus.INVALID, "Ti > 0 required")
    if td_d < 0:
        raise ControlError(ControlStatus.INVALID, "Td >= 0 required")
    ctx = make_context()
    return PIDController(kp=p, ki=ctx.divide(p, ti_d), kd=ctx.multiply(p, td_d),
                         form="ideal", ti=ti_d, td=td_d)


def pid_series(kp: object, ti: object, td: object) -> PIDController:
    """Series form C = Kp (1 + 1/(Ti s))(1 + Td s), exact parallel equivalent."""
    p = _req_decimal(kp, "Kp")
    ti_d = _req_decimal(ti, "Ti")
    td_d = _req_decimal(td, "Td")
    if ti_d <= 0:
        raise ControlError(ControlStatus.INVALID, "Ti > 0 required")
    if td_d < 0:
        raise ControlError(ControlStatus.INVALID, "Td >= 0 required")
    ctx = make_context()
    # Kp (Ti s + 1)(Td s + 1)/(Ti s): Ki = Kp/Ti, Kd = Kp Td, Kp' = Kp(1 + Td/Ti).
    kp_eff = ctx.multiply(p, ctx.add(Decimal(1), ctx.divide(td_d, ti_d)))
    ki_eff = ctx.divide(p, ti_d)
    kd_eff = ctx.multiply(p, td_d)
    return PIDController(kp=kp_eff, ki=ki_eff, kd=kd_eff,
                         form="series", ti=ti_d, td=td_d)


ZN_TABLE = {
    "P": {"kp": "0.5", "ti": "", "td": ""},
    "PI": {"kp": "0.45", "ti": "Tu/1.2", "td": ""},
    "PID": {"kp": "0.6", "ti": "Tu/2", "td": "Tu/8"},
}


@dataclass(frozen=True)
class ZieglerNicholsResult:
    kind: str
    kp: str
    ti: str
    td: str
    ki: str
    kd: str
    compensator: PIDController


def ziegler_nichols(ku: object, tu: object, kind: str) -> ZieglerNicholsResult:
    """Classic Z-N ultimate table (documented constants, Routh-derived Ku)."""
    if kind not in ("P", "PI", "PID"):
        raise ControlError(ControlStatus.INVALID, "Z-N kind in {P, PI, PID} required")
    ku_d = _req_decimal(ku, "Ku")
    tu_d = _req_decimal(tu, "Tu")
    if ku_d <= 0:
        raise ControlError(ControlStatus.INVALID, "Ku > 0 required")
    if tu_d <= 0:
        raise ControlError(ControlStatus.INVALID, "Tu > 0 required")
    ctx = make_context()
    if kind == "P":
        kp = ctx.multiply(Decimal("0.5"), ku_d)
        return ZieglerNicholsResult(
            kind=kind, kp=str(kp), ti="", td="",
            ki="", kd="",
            compensator=PIDController(kp=kp, ki=Decimal(0), kd=Decimal(0),
                                      form="ziegler-nichols"),
        )
    if kind == "PI":
        kp = ctx.multiply(Decimal("0.45"), ku_d)
        ti = ctx.divide(tu_d, Decimal("1.2"))
        ki = ctx.divide(kp, ti)
        return ZieglerNicholsResult(
            kind=kind, kp=str(kp), ti=str(ti), td="",
            ki=str(ki), kd="",
            compensator=PIDController(kp=kp, ki=ki, kd=Decimal(0),
                                      form="ziegler-nichols", ti=ti),
        )
    kp = ctx.multiply(Decimal("0.6"), ku_d)
    ti = ctx.divide(tu_d, Decimal(2))
    td = ctx.divide(tu_d, Decimal(8))
    ki = ctx.divide(kp, ti)
    kd = ctx.multiply(kp, td)
    return ZieglerNicholsResult(
        kind=kind, kp=str(kp), ti=str(ti), td=str(td),
        ki=str(ki), kd=str(kd),
        compensator=PIDController(kp=kp, ki=ki, kd=kd,
                                  form="ziegler-nichols", ti=ti, td=td),
    )


@dataclass(frozen=True)
class UltimatePoint:
    ku: str
    omega_u: str
    period_u: str
    detail: str = ""


def ultimate_gain(plant: TransferFunctionTF) -> UltimatePoint:
    """Ultimate gain from the loop phase crossover (Routh cross-checked by callers).

    Ku is the magnitude gain at the first -180 deg crossing of the plant
    seen as the loop, Wu its frequency, Tu = 2 pi / Wu. Plants without a
    phase crossover have no finite Ku -> UNSUPPORTED.
    """
    if not isinstance(plant, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "ultimate gain needs a plant TF")
    found = phase_crossover_bisection(plant)
    if not found:
        raise ControlError(ControlStatus.UNSUPPORTED, "no phase crossover: Ku undefined")
    ordered = sorted(found, key=lambda kv: kv[0])
    wu, ku = ordered[0]
    ctx = make_context()
    tu = ctx.divide(ctx.multiply(decimal_pi(ctx), Decimal(2)), wu)
    return UltimatePoint(ku=str(ku), omega_u=str(wu), period_u=str(tu),
                         detail="phase-crossover bisection")


def closed_loop(plant: TransferFunctionTF,
                compensator: object) -> TransferFunctionTF:
    if not isinstance(plant, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "closed loop needs a plant TF")
    if isinstance(compensator, PIDController):
        return compensator.closed_with(plant)
    if isinstance(compensator, TransferFunctionTF):
        return feedback(series(compensator, plant))
    raise ControlError(ControlStatus.INVALID, "closed loop needs a PIDController or TF compensator")
