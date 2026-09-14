"""General AC resonance & quality-factor analysis over D5/D6 results (F8-D8).

Thin post-processing over certified infrastructure — no new solver, no
new MNA, no new circuit model, no new complex type, no new port model,
no new sweep engine:

* observable series come from one D5 ``frequency_response`` sweep
  (``SweepResult``); transfer bands/extrema come from D6 (``analyze_bode``
  for transfers, ``observed_extrema`` for magnitudes, D6 canonical
  frequency keys throughout);
* energy-Q is evaluated LAZILY: candidate frequencies are identified
  first, then each is solved through D3 (``solve_ac``) and analyzed
  through D4 (``analyze_power``) — never for the whole sweep;
* a D7-equivalent sweep (``ACOnePortEquivalent`` series) is supported
  as a port-as-seen-by-load view, without Q (Q needs live-circuit D4).

Resonance verdict ladder (per observable, never a bare frequency):

* ``ZERO_CONFIRMED`` — EXACT mode only: SOLVED, FINITE, imaginary part
  exactly zero via ``is_zero_exact`` (includes physical ``Z = 0`` of a
  lossless LC series resonance). HP near-zero is NEVER promoted.
* ``BRACKET_CANDIDATE`` — strict native sign change between two
  adjacent SOLVED+FINITE samples. Always carries the pole diagnostic:
  a sign change across a singularity satisfies the same evidence.
  Never promoted, never interpolated, never root-found.
* ``EXTREMUM_OBSERVED`` — a D6 extremum (strict/flat/endpoint),
  corroboration only. A transfer strict-maximum is a transfer-peak
  candidate, never a resonance verdict.
* ``NO_RESONANCE_OBSERVED`` — summary finding when no zero/bracket
  evidence exists (nonreactive nets always land here).

Reactivity gate: networks without L/C produce no resonance findings
(a purely resistive network has ``Im(Z) = 0`` everywhere — that is not
resonance). Energy-Q (``Qe = sum|Q_L,C| / (2*sum P_R)`` from D4 branch
powers, F6 type-filtered, peak-phasor convention) is DEFINED only for
SOLVED evidence with ``sum P_R > 0`` and ``sum|Q| > 0``; lossless and
nonreactive yield UNDEFINED (never Infinity). Bandwidth-Q exists only
as a conditional interval for transfer observables with one D6-defined
band and one isolated strict peak — never scalar ``f0/BW``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from fractions import Fraction

from academic_core.domain.engineering.ac.bode import (
    BodeResult,
    analyze_bode,
    canonical_frequency_key,
    observed_extrema,
)
from academic_core.domain.engineering.ac.impedance import (
    ImpedanceCategory,
    ImpedanceValue,
    PortDefinition,
)
from academic_core.domain.engineering.ac.phasors import (
    fmt_cartesian,
    magnitude,
)
from academic_core.domain.engineering.ac.response import (
    ResponseDefinition,
    TransferFunction,
    frequency_response,
)
from academic_core.domain.engineering.ac.solution import ACStatus
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve.problem import NumericMode
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.math.trig import make_context

ENGINE_VERSION = "f8d-ac-resonance/1.0"

#: Observable labels carried on findings (observable is semantic identity).
OBS_PORT_IMPEDANCE = "port-impedance"
OBS_PORT_ADMITTANCE = "port-admittance"
OBS_BRANCH_IMPEDANCE = "branch-impedance"
OBS_BRANCH_ADMITTANCE = "branch-admittance"
OBS_TRANSFER = "transfer"

#: Resonance criteria.
CRIT_SERIES_REACTANCE_ZERO = "series-reactance-zero"
CRIT_PARALLEL_SUSCEPTANCE_ZERO = "parallel-susceptance-zero"
CRIT_TRANSFER_PEAK = "transfer-peak"
CRIT_MAGNITUDE_EXTREMUM = "magnitude-extremum"

#: Q bases.
BASIS_ENERGY = "energy"
BASIS_BANDWIDTH = "bandwidth"

#: Policy stamp: what D8 refuses to do (part of provenance + digest).
THRESHOLD_POLICY = (
    "bracket-only v1: no interpolation, no root finding, no adaptive "
    "refinement; HP near-zero never promoted to zero; brackets never "
    "promoted to confirmed"
)

_POLE_NOTE = (
    "a sign change across a pole/singularity satisfies the same "
    "evidence; refine the grid (D5) to discriminate: interior magnitude "
    "fall is zero-consistent, interior magnitude rise is pole-consistent "
    "(consistency check, not proof); this bracket claims no frequency"
)


class ResonanceError(ValueError):
    """Misuse of the D8 resonance layer (bad grid, wrong input types).

    Physical/solver states travel as data on the result types, never as
    exceptions.
    """


class FindingKind(Enum):
    ZERO_CONFIRMED = "zero_confirmed"
    BRACKET_CANDIDATE = "bracket_candidate"
    EXTREMUM_OBSERVED = "extremum_observed"
    NO_RESONANCE_OBSERVED = "no_resonance_observed"


class QState(Enum):
    DEFINED = "defined"
    UNDEFINED = "undefined"


@dataclass(frozen=True)
class ResonanceFinding:
    """One resonance observation (never an invented frequency)."""

    observable: str
    criterion: str
    kind: FindingKind
    frequency: str | None  # canonical key for single-sample evidence
    frequency_lo: str | None  # bracket lower key
    frequency_hi: str | None  # bracket upper key
    evidence: tuple[str, ...]  # deterministic evidence strings
    status: ACStatus  # parent AC status
    diagnostic: str

    def to_dict(self) -> dict:
        return {
            "observable": self.observable,
            "criterion": self.criterion,
            "kind": self.kind.value,
            "frequency": self.frequency,
            "frequency_lo": self.frequency_lo,
            "frequency_hi": self.frequency_hi,
            "evidence": list(self.evidence),
            "status": self.status.value,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class QualityFactor:
    """Quality factor: scalar energy-Q or conditional bandwidth interval."""

    state: QState
    basis: str  # energy | bandwidth
    value: Fraction | Decimal | None  # scalar (energy basis)
    interval: tuple[str, str] | None  # [lo, hi] strings (bandwidth basis)
    frequency: str  # canonical key of the evaluation (peak sample)
    diagnostic: str

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "basis": self.basis,
            "value": None if self.value is None else str(self.value),
            "interval": None if self.interval is None else list(self.interval),
            "frequency": self.frequency,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class ResonanceReport:
    """Immutable collection of resonance findings (0..n)."""

    observable: str
    criterion: str
    findings: tuple[ResonanceFinding, ...]
    quality: tuple[QualityFactor, ...]
    bands: tuple  # D6 PassBand passthrough (transfer role), else ()
    numeric_mode: str | None
    provenance: dict
    diagnostics: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict:
        return {
            "observable": self.observable,
            "criterion": self.criterion,
            "findings": [f.to_dict() for f in self.findings],
            "quality": [q.to_dict() for q in self.quality],
            "bands": [b.to_dict() for b in self.bands],
            "numeric_mode": self.numeric_mode,
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
            "digest": self.digest,
        }


# -- grid + circuit helpers ----------------------------------------------------


def _normalize_grid(frequencies) -> list:
    """Validate the caller grid: non-empty, Hz, f > 0, strictly increasing.

    Returns the Quantity list in order. Anything else is caller misuse
    (``ResonanceError``) — D8 never sorts, pads, or repairs grids.
    """
    from academic_core.domain.engineering.units import (
        FREQUENCY,
        Quantity,
        parse_quantity,
    )

    if isinstance(frequencies, (str, Quantity)):
        raise ResonanceError("frequencies must be a non-empty sequence, not one value")
    try:
        items = list(frequencies)
    except TypeError:
        raise ResonanceError(
            f"frequencies must be a sequence, got {type(frequencies).__name__}"
        )
    if not items:
        raise ResonanceError("frequency grid must not be empty")
    out = []
    for f in items:
        q = parse_quantity(f) if isinstance(f, str) else f
        if not isinstance(q, Quantity) or q.dimension != FREQUENCY:
            raise ResonanceError(f"sweep frequency must be Hz, got {f!r}")
        if q.to_base() <= 0:
            raise ResonanceError(f"sweep frequency must be f > 0, got {f!r}")
        out.append(q)
    bases = [q.to_base() for q in out]
    for a, b in zip(bases, bases[1:]):
        if not b > a:
            raise ResonanceError(
                "frequency grid must be strictly increasing "
                f"(got {a} Hz followed by {b} Hz)"
            )
    return out


def _reactive_present(circuit) -> bool:
    """Reactivity gate: any L/C branch (F6 ``type`` strings, read-only)."""
    return any(
        str(c.type).upper() in ("L", "C") for c in circuit.components
    )


def _circuit_refs(circuit) -> list[str]:
    return sorted(c.ref.upper() for c in circuit.components)


def _native_sign(value) -> int:
    """Sign of a native Fraction|Decimal: -1, 0, +1 (exact, no epsilon)."""
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


# -- sample extraction ----------------------------------------------------------


def _extract_phasor(point):
    """Valid solved phasor or None (non-SOLVED / non-FINITE / undefined)."""
    if point.status != ACStatus.SOLVED or point.value is None:
        return None
    v = point.value
    if isinstance(v, ImpedanceValue):
        if v.category != ImpedanceCategory.FINITE or v.value is None:
            return None
        return v.value
    if isinstance(v, TransferFunction):
        if not v.defined or v.value is None:
            return None
        return v.value
    return None


def _is_exact(phasor) -> bool:
    return isinstance(phasor, RationalComplex)


# -- zero / bracket scan (native arithmetic, exactness-preserving) --------------


def _scan_zero_brackets(keys, phasors, valid, exact_flags, observable,
                        criterion):
    """Native zero/bracket scan over imaginary-part samples.

    ``    phasors`` holds solved phasors (None for invalid samples); only
    the native ``im`` attribute is ever read, with native ``==``/``>``
    ``<`` comparisons (exactness-preserving for Fraction and Decimal —
    this is why D6's Decimal-coercing ``crossing_brackets`` is not
    reused here: coercion would round exact zeros). EXACT zero samples
    confirm: in EXACT mode the native ``im == 0`` comparison IS the
    exact-zero verdict (``is_zero_exact`` at phasor level would
    additionally demand ``re == 0``, which resonance must not require:
    ``X = 0`` with ``R != 0`` is the normal resonant case). Strict
    native sign changes bracket. HP exact-zero samples are inert: a
    computed zero is neither confirmation nor bracket evidence.
    Returns ``(findings, zero_indices, bracket_endpoint_indices)``.
    """
    findings: list[ResonanceFinding] = []
    zero_idx: list[int] = []
    endpoint_idx: list[int] = []
    hp_inert = 0
    im_of = [ph.im if (ok and ph is not None) else None
             for ph, ok in zip(phasors, valid)]
    for i, (key, im, ok, is_ex) in enumerate(
            zip(keys, im_of, valid, exact_flags)):
        if not ok or im is None:
            continue
        if _native_sign(im) != 0:
            continue
        if is_ex and im == 0:
            zero_idx.append(i)
            findings.append(ResonanceFinding(
                observable=observable, criterion=criterion,
                kind=FindingKind.ZERO_CONFIRMED, frequency=key,
                frequency_lo=None, frequency_hi=None,
                evidence=(f"im == 0 exactly at sample {i} ({key})",),
                status=ACStatus.SOLVED,
                diagnostic=("exact zero of the stated imaginary part in "
                            "EXACT mode (includes physical Z = 0)"),
            ))
        else:
            hp_inert += 1
    for i in range(len(keys) - 1):
        if not (valid[i] and valid[i + 1]):
            continue
        a, b = im_of[i], im_of[i + 1]
        if a is None or b is None:
            continue
        sa, sb = _native_sign(a), _native_sign(b)
        if sa == 0 or sb == 0:
            continue  # exact hits handled above; flat runs never cross
        if sa != sb:
            endpoint_idx.extend([i, i + 1])
            findings.append(ResonanceFinding(
                observable=observable, criterion=criterion,
                kind=FindingKind.BRACKET_CANDIDATE, frequency=None,
                frequency_lo=keys[i], frequency_hi=keys[i + 1],
                evidence=(f"strict sign change {sa:+d} -> {sb:+d} "
                          f"between samples {i} and {i + 1}",),
                status=ACStatus.SOLVED,
                diagnostic=_POLE_NOTE,
            ))
    endpoint_idx = sorted(set(endpoint_idx))
    return findings, zero_idx, endpoint_idx, hp_inert


# -- energy-Q (lazy, D4 authority) -----------------------------------------------


def _energy_q_at(circuit, quantity, frequency_key: str) -> QualityFactor:
    """Energy-Q of the live circuit at one frequency via D3 + D4.

    ``Qe = sum|Q_L,C| / (2 * sum P_R)`` over D4 branch powers, F6
    type-filtered. Never Infinity: lossless/nonreactive/non-SOLVED yield
    UNDEFINED with reasons. Native arithmetic (exactness-preserving).
    """
    from academic_core.domain.engineering.ac.power import analyze_power
    from academic_core.domain.engineering.ac.solver import solve_ac

    try:
        sol = solve_ac(circuit, quantity, NumericMode.AUTO)
    except Exception as exc:  # defensive: solve surface stays local
        return QualityFactor(
            QState.UNDEFINED, BASIS_ENERGY, None, None, frequency_key,
            f"no Q: D3 solve raised {type(exc).__name__}: {exc}")
    if sol.status != ACStatus.SOLVED:
        return QualityFactor(
            QState.UNDEFINED, BASIS_ENERGY, None, None, frequency_key,
            f"no Q: parent status {sol.status.value} (never laundered)")
    try:
        power = analyze_power(sol)
    except Exception as exc:
        return QualityFactor(
            QState.UNDEFINED, BASIS_ENERGY, None, None, frequency_key,
            f"no Q: D4 analysis raised {type(exc).__name__}: {exc}")
    type_of = {c.ref.upper(): str(c.type).upper()
               for c in circuit.components}
    p_sum = None
    q_sum = None
    for e in power.elements:
        t = type_of.get(e.ref.upper())
        if t == "R":
            p_sum = e.active if p_sum is None else p_sum + e.active
        elif t in ("L", "C"):
            aq = -e.reactive if e.reactive < 0 else e.reactive
            q_sum = aq if q_sum is None else q_sum + aq
        # V/I/D/Q/unknown: not storage/dissipation — excluded by design.
    if q_sum is None or q_sum == 0:
        return QualityFactor(
            QState.UNDEFINED, BASIS_ENERGY, None, None, frequency_key,
            "no Q: nonreactive (no stored reactive energy)")
    if p_sum is None or p_sum == 0:
        return QualityFactor(
            QState.UNDEFINED, BASIS_ENERGY, None, None, frequency_key,
            "no Q: lossless (no dissipation; Q would be infinite, "
            "never reported)")
    if not p_sum > 0:
        return QualityFactor(
            QState.UNDEFINED, BASIS_ENERGY, None, None, frequency_key,
            "no Q: non-positive dissipation (outside passive domain)")
    if isinstance(q_sum, Decimal) or isinstance(p_sum, Decimal):
        ctx = make_context()
        value = ctx.divide(_as_decimal(q_sum),
                           ctx.multiply(Decimal(2), _as_decimal(p_sum)))
    else:
        value = q_sum / (2 * p_sum)
    return QualityFactor(
        QState.DEFINED, BASIS_ENERGY, value, None, frequency_key,
        f"energy-Q sum|Q_L,C|/(2*sum P_R) via D4 at {frequency_key}")


def _as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    ctx = make_context()
    return ctx.divide(Decimal(value.numerator), Decimal(value.denominator))


# -- report assembly --------------------------------------------------------------


def _aggregate_status(points) -> ACStatus:
    for p in points:
        if p.status != ACStatus.SOLVED:
            return p.status
    return ACStatus.SOLVED


def _digest_report(payload: dict) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, default=str).encode()).hexdigest()


_ROLE_FOR_KIND = {
    "port-impedance": (OBS_PORT_IMPEDANCE, "immittance",
                       CRIT_SERIES_REACTANCE_ZERO),
    "port-admittance": (OBS_PORT_ADMITTANCE, "immittance",
                        CRIT_PARALLEL_SUSCEPTANCE_ZERO),
    "branch-impedance": (OBS_BRANCH_IMPEDANCE, "immittance",
                         CRIT_SERIES_REACTANCE_ZERO),
    "branch-admittance": (OBS_BRANCH_ADMITTANCE, "immittance",
                          CRIT_PARALLEL_SUSCEPTANCE_ZERO),
    "transfer": (OBS_TRANSFER, "transfer", CRIT_TRANSFER_PEAK),
}


def scan_resonance(circuit, definition: ResponseDefinition, frequencies,
                   *, compute_q: bool = True) -> ResonanceReport:
    """Resonance scan of one D5 sweep definition over a caller grid.

    Runs one D5 ``frequency_response`` sweep (AUTO per D5 authority),
    applies the verdict ladder, and lazily evaluates energy-Q at
    candidate frequencies only. Transfer observables additionally carry
    D6 bands. Pure post-processing otherwise: no solves beyond the D5
    sweep and the documented lazy D3/D4 Q evaluations.
    """
    if not isinstance(definition, ResponseDefinition):
        raise ResonanceError(
            f"definition must be a ResponseDefinition, got "
            f"{type(definition).__name__}")
    if definition.kind not in _ROLE_FOR_KIND:
        raise ResonanceError(
            f"unsupported sweep kind {definition.kind!r}")
    observable, role, criterion = _ROLE_FOR_KIND[definition.kind]
    grid = _normalize_grid(frequencies)
    keys = [canonical_frequency_key(q) for q in grid]
    sweep = frequency_response(circuit, definition, grid)
    points = list(sweep.points)

    phasors = [_extract_phasor(p) for p in points]
    valid = [ph is not None for ph in phasors]
    exact_flags = [_is_exact(ph) if ph is not None else False
                   for ph in phasors]
    reactive = _reactive_present(circuit)

    findings: list[ResonanceFinding] = []
    candidate_positions: list[int] = []
    hp_inert = 0
    if role == "immittance":
        if reactive:
            zf, zero_idx, endpoint_idx, hp_inert = _scan_zero_brackets(
                keys, phasors, valid, exact_flags, observable, criterion)
            findings.extend(zf)
            candidate_positions.extend(zero_idx)
            candidate_positions.extend(endpoint_idx)
        else:
            findings.append(ResonanceFinding(
                observable=observable, criterion=criterion,
                kind=FindingKind.NO_RESONANCE_OBSERVED, frequency=None,
                frequency_lo=None, frequency_hi=None,
                evidence=("nonreactive network: no L/C branches",),
                status=_aggregate_status(points),
                diagnostic=("resonance requires energy storage; a "
                            "nonreactive net cannot resonate"),
            ))
            return _assemble(
                circuit, definition, observable, criterion, sweep, grid,
                keys, findings, (), (), reactive, hp_inert,
                "nonreactive network: zero-conditions not evaluated")

    # Extrema (D6 authority, all roles).
    mag_series: list = []
    for ph, ok in zip(phasors, valid):
        mag_series.append(magnitude(ph) if (ok and ph is not None) else None)
    extrema = observed_extrema(keys, mag_series)
    for e in extrema:
        if role == "transfer" and e.kind == "strict-maximum":
            crit = CRIT_TRANSFER_PEAK
            diag = ("transfer-peak candidate at the observed sample; "
                    "peak position is discrete evidence, never a "
                    "resonance verdict")
            candidate_positions.append(e.index)
        else:
            crit = CRIT_MAGNITUDE_EXTREMUM
            diag = (f"D6 {e.kind} observation; corroboration only, "
                    f"never a resonance verdict")
        findings.append(ResonanceFinding(
            observable=observable, criterion=crit,
            kind=FindingKind.EXTREMUM_OBSERVED, frequency=e.frequency,
            frequency_lo=None, frequency_hi=None,
            evidence=(f"D6 extremum {e.kind} at sample {e.index} "
                      f"(span {e.index}..{e.end_index}) value {e.value}",),
            status=(points[e.index].status
                    if points[e.index].status == ACStatus.SOLVED
                    else points[e.index].status),
            diagnostic=diag,
        ))

    has_positive = any(f.kind in (FindingKind.ZERO_CONFIRMED,
                                  FindingKind.BRACKET_CANDIDATE)
                       for f in findings)
    if not has_positive:
        reasons = []
        if not reactive:
            reasons.append("nonreactive network")
        if not any(valid):
            reasons.append("no valid SOLVED+FINITE samples")
        if not reasons:
            reasons.append("no zero/bracket evidence on this grid")
        findings.append(ResonanceFinding(
            observable=observable, criterion=criterion,
            kind=FindingKind.NO_RESONANCE_OBSERVED, frequency=None,
            frequency_lo=None, frequency_hi=None,
            evidence=tuple(reasons),
            status=_aggregate_status(points),
            diagnostic="; ".join(reasons),
        ))

    # Lazy energy-Q at candidate frequencies only.
    quality: tuple[QualityFactor, ...] = ()
    if compute_q and reactive:
        order = sorted(set(candidate_positions))
        qs: list[QualityFactor] = []
        for i in order:
            qs.append(_energy_q_at(circuit, grid[i], keys[i]))
        quality = tuple(qs)

    bands: tuple = ()
    band_note = "bands apply to transfer observables only"
    if role == "transfer":
        bode = analyze_bode(sweep)
        bands = tuple(bode.bands)
        band_note = (f"D6 transfer bands reused: {len(bands)} band(s)")

    return _assemble(
        circuit, definition, observable, criterion, sweep, grid, keys,
        findings, quality, bands, reactive, hp_inert, band_note)


def _assemble(circuit, definition, observable, criterion, sweep, grid,
              keys, findings, quality, bands, reactive, hp_inert,
              extra_note):
    n_valid = sum(1 for p in sweep.points
                  if p.status == ACStatus.SOLVED and p.value is not None)
    diagnostics = [
        f"resonance: {len(findings)} finding(s), {len(quality)} Q "
        f"evaluation(s), {n_valid}/{len(grid)} valid samples",
        f"reactive network: {reactive}",
        f"HP exact-zero inert samples: {hp_inert} "
        f"(computed zeros are never confirmations)",
        extra_note,
    ]
    numeric_mode = None
    for p in sweep.points:
        v = p.value
        ph = None
        if isinstance(v, ImpedanceValue) and v.value is not None:
            ph = v.value
        elif isinstance(v, TransferFunction) and v.value is not None:
            ph = v.value
        if ph is not None:
            numeric_mode = ("exact" if isinstance(ph, RationalComplex)
                            else "high_precision")
            break
    provenance = {
        "engine": ENGINE_VERSION,
        "version": "1.0",
        "circuit_refs": _circuit_refs(circuit),
        "observable": observable,
        "criterion": criterion,
        "definition": definition.to_dict(),
        "frequencies": keys,
        "threshold_policy": THRESHOLD_POLICY,
        "q_criterion": ("energy-Q sum|Q_L,C|/(2*sum P_R) via D4, lazy, "
                        "F6 type-filtered"),
        "bandwidth_criterion": ("D6 PassBand reuse (transfer only); no "
                                "resonance bandwidth computed"),
        "numeric_mode": numeric_mode,
        "sweep_engine": "f8d-ac-response/1.0",
        "sweep_digest": sweep.digest,
        "sweep_status": sweep.status,
        "per_point_status": [p.status.value for p in sweep.points],
        "q_digests": [q.to_dict() for q in quality],
        "temporal_convention": "e^(+jwt)",
        "amplitude_convention": "peak",
    }
    digest = _digest_report({
        # NOTE (D6 precedent): the D5 sweep digest embeds input spelling
        # ("1 kHz" vs "1000 Hz"), so covering it would make physically
        # identical scans hash differently. The sweep stays exactly
        # linked via provenance["sweep_digest"], outside hash coverage.
        # Everything hashed here is canonical (keys, refs).
        "engine": ENGINE_VERSION,
        "observable": observable,
        "criterion": criterion,
        "definition": definition.to_dict(),
        "circuit": _circuit_refs(circuit),
        "frequencies": keys,
        "policy": THRESHOLD_POLICY,
        "findings": [f.to_dict() for f in findings],
        "quality": [q.to_dict() for q in quality],
        "bands": [b.to_dict() for b in bands],
        "statuses": [p.status.value for p in sweep.points],
    })
    return ResonanceReport(
        observable=observable, criterion=criterion,
        findings=tuple(findings), quality=quality, bands=bands,
        numeric_mode=numeric_mode, provenance=provenance,
        diagnostics=tuple(diagnostics), digest=digest)


# -- D7-equivalent sweep mode ------------------------------------------------------


def scan_port_equivalents(circuit, port: PortDefinition,
                          equivalents) -> ResonanceReport:
    """Port resonance over a D7-equivalent series (port-as-seen-by-load).

    Consumes precomputed :class:`ACOnePortEquivalent` results (one per
    frequency, strictly increasing). Zero/bracket machinery runs on the
    ``Zth`` FINITE series with the series-reactance criterion. No Q is
    produced (Q needs live-circuit D4 branch powers, unavailable from
    deactivated-network equivalents). A D7 resonance is the port view
    only — never the whole circuit's resonance.
    """
    try:
        items = list(equivalents)
    except TypeError:
        raise ResonanceError("equivalents must be a non-empty sequence")
    if not items:
        raise ResonanceError("equivalents must not be empty")
    if not isinstance(port, PortDefinition):
        raise ResonanceError(
            f"port must be a PortDefinition, got {type(port).__name__}")
    freqs: list = []
    for e in items:
        op = getattr(e, "operating_point", None)
        fq = getattr(op, "frequency", None) if op is not None else None
        if fq is None:
            raise ResonanceError("every equivalent needs an operating point frequency")
        freqs.append(fq)
    grid = _normalize_grid(freqs)
    keys = [canonical_frequency_key(q) for q in grid]
    for e in items:
        if e.port != port:
            raise ResonanceError(
                f"equivalent port {e.port.to_dict()} mismatches {port.to_dict()}")
    observable, _, criterion = _ROLE_FOR_KIND["port-impedance"]
    reactive = _reactive_present(circuit)
    zth_series: list = []
    valid: list[bool] = []
    exact_flags: list[bool] = []
    statuses: list = []
    for e in items:
        statuses.append(e.status)
        z = getattr(e, "zth", None)
        if (e.status == ACStatus.SOLVED and isinstance(z, ImpedanceValue)
                and z.category == ImpedanceCategory.FINITE
                and z.value is not None):
            valid.append(True)
            zth_series.append(z.value)
            exact_flags.append(isinstance(z.value, RationalComplex))
        else:
            valid.append(False)
            zth_series.append(None)
            exact_flags.append(False)
    findings: list[ResonanceFinding] = []
    hp_inert = 0
    if reactive:
        zf, _, _, hp_inert = _scan_zero_brackets(
            keys, zth_series, valid, exact_flags, observable, criterion)
        findings.extend(zf)
    else:
        findings.append(ResonanceFinding(
            observable=observable, criterion=criterion,
            kind=FindingKind.NO_RESONANCE_OBSERVED, frequency=None,
            frequency_lo=None, frequency_hi=None,
            evidence=("nonreactive network: no L/C branches",),
            status=statuses[0] if statuses else ACStatus.INVALID,
            diagnostic="resonance requires energy storage",
        ))
        return _assemble_equivalents(
            circuit, port, observable, criterion, items, keys, findings,
            reactive, hp_inert, "nonreactive network")
    # |Zth| extrema (D6 authority).
    mag_series = []
    for e, ok in zip(items, valid):
        if ok and e.zth.value is not None:
            mag_series.append(magnitude(e.zth.value))
        else:
            mag_series.append(None)
    for x in observed_extrema(keys, mag_series):
        findings.append(ResonanceFinding(
            observable=observable, criterion=CRIT_MAGNITUDE_EXTREMUM,
            kind=FindingKind.EXTREMUM_OBSERVED, frequency=x.frequency,
            frequency_lo=None, frequency_hi=None,
            evidence=(f"D6 extremum {x.kind} of |Zth| at sample {x.index}",),
            status=statuses[x.index],
            diagnostic="corroboration only, never a resonance verdict",
        ))
    if not any(f.kind in (FindingKind.ZERO_CONFIRMED,
                          FindingKind.BRACKET_CANDIDATE) for f in findings):
        agg = ACStatus.SOLVED
        for s in statuses:
            if s != ACStatus.SOLVED:
                agg = s
                break
        findings.append(ResonanceFinding(
            observable=observable, criterion=criterion,
            kind=FindingKind.NO_RESONANCE_OBSERVED, frequency=None,
            frequency_lo=None, frequency_hi=None,
            evidence=("no zero/bracket evidence on this equivalent series",),
            status=agg,
            diagnostic="no zero/bracket evidence on this equivalent series",
        ))
    return _assemble_equivalents(
        circuit, port, observable, criterion, items, keys, findings,
        reactive, hp_inert,
        "D7-mode: port-as-seen-by-load; no Q from equivalents")


def _assemble_equivalents(circuit, port, observable, criterion, items,
                          keys, findings, reactive, hp_inert, extra_note):
    diagnostics = (
        f"D7-mode resonance: {len(findings)} finding(s)",
        f"reactive network: {reactive}",
        f"HP exact-zero inert samples: {hp_inert}",
        extra_note,
    )
    provenance = {
        "engine": ENGINE_VERSION,
        "version": "1.0",
        "mode": "d7-equivalents",
        "circuit_refs": _circuit_refs(circuit),
        "port": port.to_dict(),
        "observable": observable,
        "criterion": criterion,
        "frequencies": keys,
        "threshold_policy": THRESHOLD_POLICY,
        "q_criterion": "none: Q unavailable from deactivated equivalents",
        "bandwidth_criterion": "none in D7-mode",
        "equivalent_digests": [e.digest for e in items],
        "per_point_status": [e.status.value for e in items],
        "temporal_convention": "e^(+jwt)",
        "amplitude_convention": "peak",
    }
    digest = _digest_report({
        "engine": ENGINE_VERSION,
        "mode": "d7-equivalents",
        "observable": observable,
        "criterion": criterion,
        "circuit": _circuit_refs(circuit),
        "port": port.to_dict(),
        "frequencies": keys,
        "policy": THRESHOLD_POLICY,
        "findings": [f.to_dict() for f in findings],
        "equivalents": [e.digest for e in items],
    })
    return ResonanceReport(
        observable=observable, criterion=criterion,
        findings=tuple(findings), quality=(), bands=(),
        numeric_mode=None, provenance=provenance,
        diagnostics=diagnostics, digest=digest)


# -- conditional bandwidth-Q --------------------------------------------------------


def quality_from_bandwidth(bode_result) -> QualityFactor:
    """Conditional bandwidth-Q interval from a D6 transfer Bode result.

    DEFINED only when: transfer kind, exactly one D6-defined band,
    exactly one strict-maximum extremum inside that band, positive
    interval bandwidth. The peak frequency is the observed sample (no
    invented ``f0``); the Q INTERVAL ``[f_peak/BW_hi, f_peak/BW_lo]``
    propagates the bracket uncertainty instead of hiding it. Anything
    else yields UNDEFINED with its reason — never scalar ``f0/BW``.
    A non-BodeResult input is caller misuse (``ResonanceError``).
    """
    definition = getattr(bode_result, "definition", None)
    if (not isinstance(bode_result, BodeResult)
            or not isinstance(definition, dict)):
        raise ResonanceError(
            f"quality_from_bandwidth needs a D6 BodeResult, got "
            f"{type(bode_result).__name__}")
    bands = list(bode_result.bands)
    extrema = list(bode_result.extrema)
    points = list(bode_result.points)
    if definition.get("kind") != "transfer":
        return QualityFactor(
            QState.UNDEFINED, BASIS_BANDWIDTH, None, None, "",
            "no bandwidth-Q: not a transfer Bode result "
            "(bandwidth is a transfer concept)")
    defined_bands = [b for b in bands if b.defined]
    if len(defined_bands) != 1:
        return QualityFactor(
            QState.UNDEFINED, BASIS_BANDWIDTH, None, None, "",
            f"no bandwidth-Q: need exactly one defined band, found "
            f"{len(defined_bands)}")
    band = defined_bands[0]
    peaks = [x for x in extrema
             if x.kind == "strict-maximum"
             and band.start_index <= x.index <= band.end_index]
    if len(peaks) != 1:
        return QualityFactor(
            QState.UNDEFINED, BASIS_BANDWIDTH, None, None, "",
            f"no bandwidth-Q: need exactly one isolated strict peak in "
            f"band, found {len(peaks)}")
    peak = peaks[0]
    blo = band.bandwidth_lo
    bhi = band.bandwidth_hi
    if blo is None or bhi is None or not blo > 0 or not bhi > 0:
        return QualityFactor(
            QState.UNDEFINED, BASIS_BANDWIDTH, None, None, "",
            "no bandwidth-Q: non-positive bandwidth interval")
    if peak.index >= len(points):
        return QualityFactor(
            QState.UNDEFINED, BASIS_BANDWIDTH, None, None, "",
            "no bandwidth-Q: peak index outside Bode points")
    peak_freq = points[peak.index].frequency
    f_peak = peak_freq.to_base()
    if not f_peak > 0:
        return QualityFactor(
            QState.UNDEFINED, BASIS_BANDWIDTH, None, None, "",
            "no bandwidth-Q: non-positive peak frequency")
    ctx = make_context()
    q_lo = ctx.divide(f_peak, bhi)
    q_hi = ctx.divide(f_peak, blo)
    key = canonical_frequency_key(peak_freq)
    return QualityFactor(
        QState.DEFINED, BASIS_BANDWIDTH, None, (str(q_lo), str(q_hi)),
        key,
        f"bandwidth-Q interval [f_peak/BW_hi, f_peak/BW_lo] at observed "
        f"peak {key} (f0 not invented)")


__all__ = [
    "ENGINE_VERSION",
    "THRESHOLD_POLICY",
    "OBS_PORT_IMPEDANCE",
    "OBS_PORT_ADMITTANCE",
    "OBS_BRANCH_IMPEDANCE",
    "OBS_BRANCH_ADMITTANCE",
    "OBS_TRANSFER",
    "CRIT_SERIES_REACTANCE_ZERO",
    "CRIT_PARALLEL_SUSCEPTANCE_ZERO",
    "CRIT_TRANSFER_PEAK",
    "CRIT_MAGNITUDE_EXTREMUM",
    "BASIS_ENERGY",
    "BASIS_BANDWIDTH",
    "ResonanceError",
    "FindingKind",
    "QState",
    "ResonanceFinding",
    "QualityFactor",
    "ResonanceReport",
    "scan_resonance",
    "scan_port_equivalents",
    "quality_from_bandwidth",
]
