"""F8-P4 deterministic simulation (NEW).

Counter-based uniform streams u_i = SHA256(seed || 0x00 || i)/2^256 and
Box-Muller gaussian streams over certified sin/cos/log/sqrt. Seeds are
int >= 0 (INVALID_SEED discipline, F8-M precedent). Monte Carlo is a
secondary oracle: analytic predictions carry the verdict, simulation
reports a documented statistical bound. No random/os/urandom/secrets.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.comms.constellation import (
    Constellation,
    bpsk_constellation,
)
from academic_core.domain.engineering.comms.metrics import (
    SIMULATION,
    MetricResult,
    ber_bpsk,
    from_db10,
)
from academic_core.domain.engineering.comms.modulation import (
    bpsk_demodulate,
    modulate,
)
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.response import decimal_exp
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    decimal_sqrt,
    make_context,
)
from academic_core.domain.engineering.math.logarithm import decimal_ln10, decimal_log10

MAX_MC_BITS = 1000000
MAX_UNIFORMS = 2000000
_TWO_POW_256 = 1 << 256


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


def validate_seed(seed: object) -> int:
    """Seed contract: int >= 0 (bool rejected); else INVALID_SEED."""
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise _fail(ControlStatus.INVALID, "INVALID_SEED: Monte Carlo needs an int seed >= 0")
    return seed


def _check_count(count: object, limit: int, label: str) -> int:
    if isinstance(count, bool) or not isinstance(count, int):
        raise _fail(ControlStatus.INVALID, label + " must be int")
    if count < 1:
        raise _fail(ControlStatus.INVALID, label + " >= 1 required")
    if count > limit:
        raise _fail(ControlStatus.INVALID, label + " budget exceeded")
    return count


def uniform_stream(seed: int, count: int, offset: int = 0) -> tuple:
    """Deterministic uniforms in [0, 1): SHA256(seed||0x00||i)/2^256.

    Index i runs over [offset, offset+count): the gate formula is intact;
    offset only selects a disjoint window (documented domain separation).
    """
    tag = validate_seed(seed)
    total = _check_count(count, MAX_UNIFORMS, "uniform count")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise _fail(ControlStatus.INVALID, "stream offset must be int >= 0")
    if offset + total > MAX_UNIFORMS:
        raise _fail(ControlStatus.INVALID, "stream window budget exceeded")
    ctx = make_context()
    denom = Decimal(_TWO_POW_256)
    out: list = []
    prefix = str(tag).encode("utf-8") + b"\x00"
    for i in range(offset, offset + total):
        digest = hashlib.sha256(prefix + i.to_bytes(8, "big")).digest()
        value = ctx.divide(Decimal(int.from_bytes(digest, "big")), denom)
        out.append(value)
    return tuple(out)


def gaussian_stream(seed: int, count: int, offset: int = 0) -> tuple:
    """Deterministic N(0,1) via Box-Muller over certified kernels.

    Consumes the uniform window [offset, offset+2*pairs) so callers can
    separate bit and noise domains without sharing indices.
    """
    tag = validate_seed(seed)
    total = _check_count(count, MAX_UNIFORMS, "gaussian count")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise _fail(ControlStatus.INVALID, "stream offset must be int >= 0")
    pairs = (total + 1) // 2
    if offset + pairs * 2 > MAX_UNIFORMS:
        raise _fail(ControlStatus.INVALID, "stream window budget exceeded")
    uniforms = uniform_stream(tag, pairs * 2, offset)
    ctx = make_context()
    two = Decimal(2)
    tiny = ctx.divide(Decimal(1), Decimal(_TWO_POW_256))
    out: list = []
    for p in range(pairs):
        u1 = uniforms[2 * p]
        u2 = uniforms[2 * p + 1]
        if u1 == 0:
            u1 = tiny
        radius = decimal_sqrt(ctx.multiply(ctx.minus(two),
                                           _ln_cert(u1, ctx)), ctx)
        angle = ctx.multiply(ctx.multiply(two, decimal_pi(ctx)), u2)
        out.append(ctx.multiply(radius, decimal_cos(angle, ctx)))
        if len(out) < total:
            out.append(ctx.multiply(radius, decimal_sin(angle, ctx)))
    return tuple(out)


def _ln_cert(value: Decimal, ctx) -> Decimal:
    """ln via certified log10 (ln x = log10(x)/log10(e))."""
    e_val = decimal_exp(Decimal(1), ctx)
    return ctx.divide(decimal_log10(value, ctx), decimal_log10(e_val, ctx))


def _check_db(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise _fail(ControlStatus.INVALID, "Eb/N0 dB must be Decimal")
    if not value.is_finite():
        raise _fail(ControlStatus.INVALID, "Eb/N0 dB must be finite")
    return value


@dataclass(frozen=True)
class SimReport:
    """Deterministic Monte Carlo report (validation-only post-init)."""

    scheme: str
    eb_n0_db: Decimal
    bits: int
    seed: int
    errors: int
    ber_sim: Decimal
    ber_analytic: Decimal
    bound_5sigma: Decimal
    within_bound: bool

    def __post_init__(self) -> None:
        if self.bits < 1 or self.bits > MAX_MC_BITS:
            raise _fail(ControlStatus.INVALID, "MC bits out of budget")
        if self.errors < 0 or self.errors > self.bits:
            raise _fail(ControlStatus.INVALID, "MC error count inconsistent")


def simulate_bpsk(eb_n0_db: Decimal, nbits: int, seed: int, observer=None) -> SimReport:
    """Seeded BPSK-over-AWGN run (Es = Eb = 1, real noise N0/2 per dim).

    Bits come from uniform_stream threshold 1/2 (seeded); noise from
    gaussian_stream under the same seed. Analytic BER is the verdict
    oracle; the 5-sigma bound is the documented comparison criterion.

    E0.4: an optional ``observer`` receives ``bpsk_setup(eb_n0_lin, n0,
    sigma, seed)`` and ``bpsk_bit(index, uniform, bit, symbol, noise,
    sample, decided)`` for every simulated bit (immutable snapshots).
    ``None`` keeps the simulation byte-identical.
    """
    snr_db = _check_db(eb_n0_db)
    total = _check_count(nbits, MAX_MC_BITS, "MC bits")
    tag = validate_seed(seed)
    ctx = make_context()
    eb_n0_lin = from_db10(snr_db)
    if eb_n0_lin <= 0:
        raise _fail(ControlStatus.INVALID, "Eb/N0 must be positive")
    n0 = ctx.divide(Decimal(1), eb_n0_lin)
    sigma = decimal_sqrt(ctx.divide(n0, Decimal(2)), ctx)
    uniforms = uniform_stream(tag, total, 0)
    noise = gaussian_stream(tag, total, total)
    constellation: Constellation = bpsk_constellation()
    if observer is not None:
        observer.bpsk_setup(eb_n0_lin, n0, sigma, tag)
    errors = 0
    for i in range(total):
        bit = 0 if uniforms[i] < Decimal("0.5") else 1
        symbol = constellation.coordinate_of(bit)
        sample = DecimalComplex(ctx.add(symbol.re, ctx.multiply(sigma, noise[i])),
                                symbol.im)
        decided = bpsk_demodulate((sample,))[0]
        if observer is not None:
            observer.bpsk_bit(i, uniforms[i], bit, symbol, noise[i], sample, decided)
        if decided != bit:
            errors += 1
    ber_sim = ctx.divide(Decimal(errors), Decimal(total))
    analytic = ber_bpsk(eb_n0_lin).value
    one = Decimal(1)
    var = ctx.divide(ctx.multiply(analytic, ctx.subtract(one, analytic)),
                     Decimal(total))
    bound = ctx.multiply(Decimal(5), decimal_sqrt(var, ctx))
    floor = ctx.divide(one, Decimal(total))
    if bound < floor:
        bound = floor
    diff = ctx.subtract(ber_sim, analytic).copy_abs()
    return SimReport(scheme="bpsk", eb_n0_db=snr_db, bits=total, seed=tag,
                     errors=errors, ber_sim=ber_sim, ber_analytic=analytic,
                     bound_5sigma=bound, within_bound=diff <= bound)


def simulation_metric(report: SimReport) -> MetricResult:
    """Wrap a simulation BER as a SIMULATION-kind metric (never EXACT)."""
    if not isinstance(report, SimReport):
        raise _fail(ControlStatus.INVALID, "simulation_metric needs a SimReport")
    return MetricResult(value=report.ber_sim, kind=SIMULATION)


def ln10_value() -> Decimal:
    """Certified ln10 accessor (used by channel-adjacent conversions)."""
    return decimal_ln10(make_context())
