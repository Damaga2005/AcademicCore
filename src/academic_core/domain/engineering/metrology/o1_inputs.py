"""F8-O O1/O7/O8 inputs (WRAP + ADAPT, no new statistics).

Every estimator delegates to the certified F7-B7 ``gum.py`` helpers
(``type_a_from_observations``, ``type_b_*``, ``InputQuantity``); this module
adds only deterministic ingress validation and the lab-``Waveform`` adapter.
The Type A equations implemented by the wrapped helper are::

    xbar = (1/n) sum x_j
    s^2  = sum (x_j - xbar)^2 / (n - 1)
    u_A  = s / sqrt(n)
    nu   = n - 1

Reuse: WRAP ``gum.InputQuantity`` / ``gum.type_a_from_observations`` /
``gum.type_b_rectangular|triangular|normal``; ADAPT lab ``Waveform`` samples.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from academic_core.domain.engineering.gum import (
    InputQuantity,
    type_a_from_observations,
    type_b_normal as _gum_type_b_normal,
    type_b_rectangular as _gum_type_b_rectangular,
    type_b_triangular as _gum_type_b_triangular,
)

from academic_core.domain.engineering.metrology.errors import (
    MetrologyError,
    MetrologyStatus,
)

MAX_METROLOGY_INPUTS = 64


def _to_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool):
        raise MetrologyError(MetrologyStatus.INVALID, "bool is not a valid numeric ingress")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except Exception as exc:
            raise MetrologyError(MetrologyStatus.INVALID, f"unparseable decimal {value!r}") from exc
    else:
        raise MetrologyError(
            MetrologyStatus.INVALID, f"unsupported numeric type {type(value).__name__}"
        )
    if not result.is_finite():
        raise MetrologyError(MetrologyStatus.INVALID, "non-finite decimal ingress rejected")
    return result


def _require_name(name: str) -> str:
    cleaned = name.strip() if isinstance(name, str) else ""
    if not cleaned:
        raise MetrologyError(MetrologyStatus.INVALID, "input name cannot be empty")
    return cleaned


def type_a(
    name: str,
    observations: Sequence[Decimal | int | str],
    unit: str = "",
    description: str = "",
    source: str = "",
) -> InputQuantity:
    """Type A input from repeated observations (WRAP ``gum.type_a_from_observations``).

    Raises ``MetrologyError(INVALID)`` for ``n < 2``, empty names,
    non-finite or non-numeric ingress. Order-invariance of (mean, u) is a
    tested property; the stored nominal keeps full Decimal precision.
    """
    cleaned = _require_name(name)
    if observations is None or len(tuple(observations)) < 2:
        raise MetrologyError(
            MetrologyStatus.INVALID, "Type A evaluation requires at least 2 observations"
        )
    decimals = tuple(_to_decimal(v) for v in observations)
    try:
        mean_val, u_std, nu = type_a_from_observations(decimals)
    except ValueError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc
    return InputQuantity(
        name=cleaned,
        nominal_value=mean_val,
        unit=unit,
        standard_uncertainty=u_std,
        uncertainty_type="A",
        distribution="student_t",
        degrees_of_freedom=float(nu),
        description=description,
        source=source or f"Type A from {len(decimals)} observations",
    )


def waveform_to_observations(waveform: object) -> tuple[Decimal, ...]:
    """ADAPT lab ``Waveform`` samples to Type A observations (values only).

    Structural adapter (no import edge: certified test N-110 forbids any
    non-lab module importing ``lab/``). Time base is intentionally
    discarded: Type A over waveform samples treats the committed samples
    as repeated observations of one quantity. Raises
    ``MetrologyError(INVALID)`` for empty waveforms or non-finite samples.
    """
    try:
        raw_values = waveform.values  # type: ignore[union-attr]
    except AttributeError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, "waveform_to_observations needs values") from exc
    if len(raw_values) == 0:
        raise MetrologyError(MetrologyStatus.INVALID, "empty waveform carries no observations")
    out: list[Decimal] = []
    for v in raw_values:
        if isinstance(v, bool) or not isinstance(v, Decimal) or not v.is_finite():
            raise MetrologyError(MetrologyStatus.INVALID, "waveform sample must be finite Decimal")
        out.append(v)
    return tuple(out)


def type_a_from_waveform(
    name: str, waveform: object, unit: str = "", description: str = "", source: str = ""
) -> InputQuantity:
    """Type A input from lab ``Waveform`` samples (ADAPT + WRAP)."""
    try:
        unit_label = waveform.unit_label  # type: ignore[union-attr]
        origin = waveform.source  # type: ignore[union-attr]
    except AttributeError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, "type_a_from_waveform needs a Waveform") from exc
    return type_a(
        name,
        waveform_to_observations(waveform),
        unit=unit or (unit_label if isinstance(unit_label, str) else ""),
        description=description,
        source=source or f"Type A from waveform {origin}",
    )


def _non_negative_half_width(half_width: Decimal | int | str) -> Decimal:
    a = _to_decimal(half_width)
    if a < 0:
        raise MetrologyError(MetrologyStatus.INVALID, f"half-width must be non-negative, got {a}")
    return a


def type_b_rectangular(
    name: str,
    nominal: Decimal | int | str = Decimal("0"),
    half_width: Decimal | int | str = Decimal("0"),
    unit: str = "",
    description: str = "",
    source: str = "",
) -> InputQuantity:
    """Type B rectangular ``u = a / sqrt(3)`` (WRAP ``gum``)."""
    cleaned = _require_name(name)
    a = _non_negative_half_width(half_width)
    nom = _to_decimal(nominal)
    try:
        u, nu = _gum_type_b_rectangular(a)
    except ValueError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc
    return InputQuantity(
        name=cleaned,
        nominal_value=nom,
        unit=unit,
        standard_uncertainty=u,
        uncertainty_type="B",
        distribution="rectangular",
        degrees_of_freedom=nu,
        description=description,
        source=source or f"Rectangular bounds +- {a}",
    )


def type_b_triangular(
    name: str,
    nominal: Decimal | int | str = Decimal("0"),
    half_width: Decimal | int | str = Decimal("0"),
    unit: str = "",
    description: str = "",
    source: str = "",
) -> InputQuantity:
    """Type B triangular ``u = a / sqrt(6)`` (WRAP ``gum``)."""
    cleaned = _require_name(name)
    a = _non_negative_half_width(half_width)
    nom = _to_decimal(nominal)
    try:
        u, nu = _gum_type_b_triangular(a)
    except ValueError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc
    return InputQuantity(
        name=cleaned,
        nominal_value=nom,
        unit=unit,
        standard_uncertainty=u,
        uncertainty_type="B",
        distribution="triangular",
        degrees_of_freedom=nu,
        description=description,
        source=source or f"Triangular bounds +- {a}",
    )


def type_b_normal(
    name: str,
    nominal: Decimal | int | str = Decimal("0"),
    expanded_uncertainty: Decimal | int | str = Decimal("0"),
    k: Decimal | int | str = 2,
    unit: str = "",
    degrees_of_freedom: float = float("inf"),
    description: str = "",
    source: str = "",
) -> InputQuantity:
    """Type B normal ``u = U / k`` (WRAP ``gum``).

    ``k`` must be finite and ``> 0``; ``U`` must be ``>= 0``; both are
    validated here (INVALID) before delegating.
    """
    cleaned = _require_name(name)
    nom = _to_decimal(nominal)
    u_in = _to_decimal(expanded_uncertainty)
    k_in = _to_decimal(k)
    if u_in < 0:
        raise MetrologyError(MetrologyStatus.INVALID, "expanded uncertainty must be non-negative")
    if k_in <= 0:
        raise MetrologyError(MetrologyStatus.INVALID, "coverage factor k must be strictly positive")
    try:
        u, nu = _gum_type_b_normal(u_in, k_in, degrees_of_freedom=degrees_of_freedom)
    except ValueError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc
    return InputQuantity(
        name=cleaned,
        nominal_value=nom,
        unit=unit,
        standard_uncertainty=u,
        uncertainty_type="B",
        distribution="normal",
        degrees_of_freedom=nu,
        description=description,
        source=source or f"Normal calibration U={u_in}, k={k_in}",
    )


def type_b_explicit(
    name: str,
    nominal: Decimal | int | str = Decimal("0"),
    standard_uncertainty: Decimal | int | str = Decimal("0"),
    unit: str = "",
    degrees_of_freedom: float = float("inf"),
    description: str = "",
    source: str = "",
) -> InputQuantity:
    """Type B explicit standard uncertainty (WRAP ``gum.InputQuantity``)."""
    cleaned = _require_name(name)
    nom = _to_decimal(nominal)
    u = _to_decimal(standard_uncertainty)
    if u < 0:
        raise MetrologyError(
            MetrologyStatus.INVALID, "standard uncertainty must be non-negative"
        )
    try:
        return InputQuantity(
            name=cleaned,
            nominal_value=nom,
            unit=unit,
            standard_uncertainty=u,
            uncertainty_type="B",
            distribution="explicit",
            degrees_of_freedom=degrees_of_freedom,
            description=description,
            source=source or "Explicit standard uncertainty",
        )
    except ValueError as exc:
        raise MetrologyError(MetrologyStatus.INVALID, str(exc)) from exc
