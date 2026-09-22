"""F8-P5 thermal noise + G/T (NEW).

N0 = k*T (W/Hz), N = k*T*B (W) with exact SI k. Tsys as single-value
input or Friis cascade Te = T1 + T2/G1 + ... over <= 8 stages
(reference plane: LNA input). Tant is a LIMITED explicit input (no sky
model). G/T = Grx - 10*log10(Tsys) in dB/K. P4's sample-level AWGN is
NOT duplicated: this module delivers link N0/C/N0 only.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.comms.metrics import to_db10
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import make_context
from academic_core.domain.engineering.satcom.constants import boltzmann_k, check_magnitude

MAX_FRIIS_STAGES = 8


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def _temperature(value: object) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, "temperature rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, "bad temperature string") from exc
    else:
        raise _fail(ControlStatus.INVALID, "temperature must be Decimal/int/str (K label)")
    if not out.is_finite() or out <= 0 or out > Decimal("1E+30"):
        raise _fail(ControlStatus.INVALID, "temperature must be finite K in (0, 1e30]")
    return out


def _bandwidth(value: object) -> Decimal:
    if isinstance(value, bool):
        raise _fail(ControlStatus.INVALID, "bandwidth rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise _fail(ControlStatus.INVALID, "bad bandwidth string") from exc
    else:
        raise _fail(ControlStatus.INVALID, "bandwidth must be Decimal/int/str (Hz)")
    return check_magnitude(out, "bandwidth")


def noise_psd_w_hz(temperature_k: object) -> Decimal:
    """N0 = k*T (W/Hz), T > 0 K."""
    temp = _temperature(temperature_k)
    return make_context().multiply(boltzmann_k(), temp)


def noise_power_w(temperature_k: object, bandwidth_hz: object) -> Decimal:
    """N = k*T*B (W), T > 0 K, B > 0 Hz."""
    temp = _temperature(temperature_k)
    band = _bandwidth(bandwidth_hz)
    ctx = make_context()
    return ctx.multiply(ctx.multiply(boltzmann_k(), temp), band)


def friis_temperature(stages: object) -> Decimal:
    """Friis cascade Te = T1 + T2/G1 + T3/(G1*G2) + ... (K), 1..8 stages.

    Each stage is (gain_linear > 0, temp_K > 0). Reference plane: LNA
    (first-stage) input. Gains are linear power ratios (dimensionless).
    """
    if not isinstance(stages, (tuple, list)) or len(stages) == 0:
        raise _fail(ControlStatus.INVALID, "Friis cascade needs 1..8 stages")
    if len(stages) > MAX_FRIIS_STAGES:
        raise _fail(ControlStatus.INVALID, "Friis budget exceeded (8 stages max)")
    ctx = make_context()
    total = Decimal(0)
    gain_product = Decimal(1)
    for stage in stages:
        if (not isinstance(stage, (tuple, list)) or len(stage) != 2):
            raise _fail(ControlStatus.INVALID, "Friis stage must be (gain, temp)")
        gain_raw, temp_raw = stage
        if isinstance(gain_raw, bool) or not isinstance(gain_raw, Decimal):
            raise _fail(ControlStatus.INVALID, "Friis gain must be Decimal linear")
        if not gain_raw.is_finite() or gain_raw <= 0:
            raise _fail(ControlStatus.INVALID, "Friis gain must be finite > 0")
        temp = _temperature(temp_raw)
        total = ctx.add(total, ctx.divide(temp, gain_product))
        gain_product = ctx.multiply(gain_product, gain_raw)
    return total


def g_over_t_dbk(gain_dbi: Decimal, system_temp_k: object) -> Decimal:
    """G/T = Grx(dBi) - 10*log10(Tsys) (dB/K)."""
    if isinstance(gain_dbi, bool) or not isinstance(gain_dbi, Decimal):
        raise _fail(ControlStatus.INVALID, "receive gain must be Decimal dBi")
    if not gain_dbi.is_finite():
        raise _fail(ControlStatus.INVALID, "receive gain must be finite")
    temp = _temperature(system_temp_k)
    ctx = make_context()
    return ctx.subtract(gain_dbi, to_db10(temp))
