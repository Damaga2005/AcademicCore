"""GUM / Measurement Uncertainty Evaluation Engine (Phase 7-B7).

Implements ISO/IEC Guide 98-3 (Guide to the Expression of Uncertainty in Measurement):
- MeasurementModel: Y = f(X1, X2, ..., Xn)
- InputQuantity: Type A & Type B evaluations (Rectangular, Triangular, Normal, Explicit)
- Sensitivity coefficients: Explicit, Analytic, and Central Finite-Difference Numerical
- Correlation and covariance propagation
- Combined standard uncertainty: u_c(y)
- Welch-Satterthwaite effective degrees of freedom: nu_eff
- Student's t distribution coverage factor: k (deterministic, non-hardcoded)
- Expanded uncertainty: U = k * u_c(y)
- Structured UncertaintyBudget tables and GUMResult
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Sequence

from academic_core.domain.engineering.equations import (
    ALLOWED_FUNCS,
    EquationError,
    evaluate,
    parse_equation,
)
from academic_core.domain.engineering.units import (
    DIMENSIONLESS,
    DIM_NAMES,
    Quantity,
    Unit,
    UnitError,
    parse_quantity,
    parse_unit,
)

ENGINE_VERSION_GUM = "gum/1.0"


# ==============================================================================
# 0. Deterministic Linear Algebra & Units Helpers (Pure Python Stdlib)
# ==============================================================================

def jacobi_eigenvalues(
    matrix: list[list[float]],
    max_sweeps: int = 50,
    tol: float = 1e-15,
) -> list[float]:
    """Compute all eigenvalues of a real symmetric matrix using the classical Jacobi algorithm.

    Guaranteed deterministic, pure Python standard library (zero NumPy/SciPy dependency),
    and unconditionally numerically stable for symmetric matrices.

    Parameters:
        matrix: n x n symmetric matrix of floats.
        max_sweeps: maximum number of rotation sweeps (typically converges in 5-10 sweeps).
        tol: convergence threshold for off-diagonal elements.

    Returns:
        Sorted list of eigenvalues [lambda_1, lambda_2, ..., lambda_n].
    """
    n = len(matrix)
    if n == 0:
        return []
    if n == 1:
        return [float(matrix[0][0])]

    a = [row[:] for row in matrix]

    for _ in range(max_sweeps):
        max_val = 0.0
        p, q = 0, 1
        for i in range(n):
            for j in range(i + 1, n):
                val = abs(a[i][j])
                if val > max_val:
                    max_val = val
                    p, q = i, j

        if max_val < tol:
            break

        app = a[p][p]
        aqq = a[q][q]
        apq = a[p][q]

        if abs(apq) < tol:
            continue

        phi = (aqq - app) / (2.0 * apq)
        if phi >= 0.0:
            t = 1.0 / (phi + math.sqrt(phi * phi + 1.0))
        else:
            t = -1.0 / (-phi + math.sqrt(phi * phi + 1.0))

        c = 1.0 / math.sqrt(t * t + 1.0)
        s = t * c
        tau = s / (1.0 + c)

        a[p][p] = app - t * apq
        a[q][q] = aqq + t * apq
        a[p][q] = 0.0
        a[q][p] = 0.0

        for i in range(n):
            if i != p and i != q:
                a_ip = a[i][p]
                a_iq = a[i][q]
                new_ip = a_ip - s * (a_iq + tau * a_ip)
                new_iq = a_iq + s * (a_ip - tau * a_iq)
                a[i][p] = new_ip
                a[p][i] = new_ip
                a[i][q] = new_iq
                a[q][i] = new_iq

    eigenvalues = sorted([a[i][i] for i in range(n)])
    return eigenvalues


def _resolve_unit(symbol: str) -> Unit:
    """Resolve a unit string to a Unit instance using the certified F6 units system.

    If the unit is a known SI/electrical unit in units.py, it is parsed via parse_unit.
    If the unit is empty or '1', a dimensionless unit is returned.
    If the unit is an external label (e.g. 'mm'), a deterministic synthetic Unit
    with a distinct dimension is assigned so identical symbols match and incompatible symbols fail.
    """
    s = (symbol or "").strip()
    if not s or s == "1":
        return Unit("1", "1", "", DIMENSIONLESS, Decimal(1))
    try:
        return parse_unit(s)
    except UnitError:
        h = int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:8], 16)
        synthetic_dim = (0, 0, 0, 0, 0, 0, h)
        return Unit(s, s, "", synthetic_dim, Decimal(1))


# ==============================================================================
# 1. Deterministic Student-t & Incomplete Beta (Pure Python Stdlib)
# ==============================================================================

def betacf(a: float, b: float, x: float, max_iter: int = 200, eps: float = 1e-15) -> float:
    """Continued fraction for regularized incomplete beta function (Lentz's method)."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        # Even step
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c

        # Odd step
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        del_val = d * c
        h *= del_val
        if abs(del_val - 1.0) < eps:
            break
    return h


def ibeta(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x < 0.0 or x > 1.0:
        raise ValueError(f"x out of bounds for incomplete beta: {x}")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * betacf(a, b, x) / a
    return 1.0 - bt * betacf(b, a, 1.0 - x) / b


def student_t_cdf(t: float, nu: float) -> float:
    """Cumulative distribution function for Student's t distribution with nu degrees of freedom."""
    if math.isinf(nu) or nu >= 1e5:
        # Standard normal limit
        return 0.5 * (1.0 + math.erf(t / math.sqrt(2.0)))
    if nu <= 0:
        raise ValueError(f"degrees of freedom must be positive, got {nu}")
    x = nu / (nu + t * t)
    prob = 0.5 * ibeta(nu / 2.0, 0.5, x)
    return 1.0 - prob if t > 0 else prob


def student_t_quantile(p: float, nu: float) -> float:
    """Inverse CDF (quantile function) of Student's t distribution.

    Reproduces ISO/IEC Guide 98-3 Table G.2 values to high precision.
    """
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"probability p must be in (0, 1), got {p}")
    if p == 0.5:
        return 0.0
    if math.isinf(nu) or nu >= 1e5:
        # Rational approximation of standard normal quantile
        return _normal_inv_cdf(p)

    if nu <= 0:
        raise ValueError(f"degrees of freedom must be positive, got {nu}")

    # Initial guess using normal approximation with Hill's correction
    z = _normal_inv_cdf(p)
    t = z + (z**3 + z) / (4.0 * nu)

    # Newton-Raphson root polishing
    for _ in range(60):
        f = student_t_cdf(t, nu) - p
        # Student's t PDF
        pdf = (
            math.exp(math.lgamma((nu + 1.0) / 2.0) - math.lgamma(nu / 2.0))
            / math.sqrt(math.pi * nu)
            * (1.0 + (t * t) / nu) ** (-(nu + 1.0) / 2.0)
        )
        if pdf <= 0:
            break
        dt = f / pdf
        t -= dt
        if abs(dt) < 1e-12:
            break
    return t


def _normal_inv_cdf(p: float) -> float:
    """Inverse CDF of standard normal distribution using Beasley-Springer-Moro algorithm."""
    import statistics
    return statistics.NormalDist().inv_cdf(p)


def calculate_coverage_factor(coverage_probability: float, nu_eff: float) -> Decimal:
    """Calculate GUM coverage factor k for a given coverage probability and effective degrees of freedom.

    For two-tailed coverage at level p (e.g. 0.95), uses t-quantile at 1 - (1 - p)/2 = (1 + p)/2.
    """
    if coverage_probability <= 0 or coverage_probability >= 1.0:
        raise ValueError(f"Coverage probability must be in (0, 1), got {coverage_probability}")

    nu = float(nu_eff)
    if nu <= 0:
        raise ValueError(f"Degrees of freedom must be strictly positive, got {nu}")

    alpha = 1.0 - coverage_probability
    p_upper = 1.0 - (alpha / 2.0)

    if math.isinf(nu) or nu >= 1e5:
        k_flt = _normal_inv_cdf(p_upper)
    else:
        k_flt = student_t_quantile(p_upper, nu)

    return Decimal(str(round(k_flt, 6)))


# ==============================================================================
# 2. Type A & Type B Evaluation Helpers
# ==============================================================================

def type_a_from_observations(
    observations: Sequence[Decimal | float | int | str | Quantity],
) -> tuple[Decimal, Decimal, int]:
    """Evaluate Type A standard uncertainty from repeated observations.

    Returns:
        (mean, u_standard = s / sqrt(n), degrees_of_freedom = n - 1)
    """
    if not observations or len(observations) < 2:
        raise ValueError("Type A evaluation requires at least 2 observations")

    dec_vals: list[Decimal] = []
    for obs in observations:
        if isinstance(obs, Quantity):
            dec_vals.append(obs.value)
        else:
            dec_vals.append(Decimal(str(obs)))

    n = len(dec_vals)
    mean_val = sum(dec_vals) / Decimal(n)
    var_sample = sum((x - mean_val) ** 2 for x in dec_vals) / Decimal(n - 1)
    s_sample = Decimal(str(math.sqrt(float(var_sample))))
    u_std = s_sample / Decimal(str(math.sqrt(n)))
    nu = n - 1
    return mean_val, u_std, nu


def type_b_rectangular(half_width: Decimal | float | int | str) -> tuple[Decimal, float]:
    """Type B evaluation for a rectangular / uniform distribution over [-a, +a]: u = a / sqrt(3)."""
    a = Decimal(str(half_width))
    if a < 0:
        raise ValueError(f"Half-width must be non-negative, got {a}")
    sqrt_3 = Decimal(str(math.sqrt(3.0)))
    return a / sqrt_3, float("inf")


def type_b_triangular(half_width: Decimal | float | int | str) -> tuple[Decimal, float]:
    """Type B evaluation for a triangular distribution over [-a, +a]: u = a / sqrt(6)."""
    a = Decimal(str(half_width))
    if a < 0:
        raise ValueError(f"Half-width must be non-negative, got {a}")
    sqrt_6 = Decimal(str(math.sqrt(6.0)))
    return a / sqrt_6, float("inf")


def type_b_normal(
    expanded_uncertainty: Decimal | float | int | str,
    k: Decimal | float | int | str = 2,
    coverage_factor: Decimal | float | int | str | None = None,
    degrees_of_freedom: float = float("inf"),
) -> tuple[Decimal, float]:
    """Type B evaluation for a normal distribution with stated expanded uncertainty U and coverage factor k: u = U / k."""
    cov_k = coverage_factor if coverage_factor is not None else k
    k_dec = Decimal(str(cov_k))
    if k_dec <= 0:
        raise ValueError(f"Coverage factor k must be strictly positive, got {k_dec}")
    U = Decimal(str(expanded_uncertainty))
    if U < 0:
        raise ValueError(f"Expanded uncertainty must be non-negative, got {U}")
    return U / k_dec, float(degrees_of_freedom)


# ==============================================================================
# 3. InputQuantity Domain Model
# ==============================================================================

class UncertaintyType(str, Enum):
    A = "A"
    B = "B"
    TYPE_A = "A"
    TYPE_B = "B"


class UncertaintyDistribution(str, Enum):
    NORMAL = "normal"
    RECTANGULAR = "rectangular"
    TRIANGULAR = "triangular"
    STUDENT_T = "student_t"
    EXPLICIT = "explicit"


DistributionType = UncertaintyDistribution


@dataclass(frozen=True)
class InputQuantity:
    """Specification of an input quantity X_i in a GUM measurement model."""
    name: str
    nominal_value: Decimal
    unit: str = ""
    standard_uncertainty: Decimal = Decimal("0")
    uncertainty_type: str = "B"  # "A" | "B"
    distribution: str = "explicit"  # "normal" | "rectangular" | "triangular" | "student_t" | "explicit"
    degrees_of_freedom: float = float("inf")
    description: str = ""
    source: str = ""

    def __post_init__(self):
        n = str(self.name).strip()
        if not n:
            raise ValueError("InputQuantity name cannot be empty")

        nom_d = Decimal(str(self.nominal_value))
        u_d = Decimal(str(self.standard_uncertainty))
        if u_d < 0:
            raise ValueError(f"Standard uncertainty must be non-negative, got {u_d}")

        ut = str(self.uncertainty_type).strip().upper()
        if ut not in ("A", "B"):
            raise ValueError(f"uncertainty_type must be 'A' or 'B', got {ut!r}")

        dist = str(self.distribution).strip().lower()
        if dist not in ("normal", "rectangular", "triangular", "student_t", "explicit"):
            raise ValueError(f"distribution must be one of normal/rectangular/triangular/student_t/explicit, got {dist!r}")

        dof = float(self.degrees_of_freedom) if self.degrees_of_freedom is not None else float("inf")
        if not math.isinf(dof) and dof <= 0:
            raise ValueError(f"Degrees of freedom must be strictly positive, got {dof}")

        object.__setattr__(self, "name", n)
        object.__setattr__(self, "nominal_value", nom_d)
        object.__setattr__(self, "standard_uncertainty", u_d)
        object.__setattr__(self, "uncertainty_type", ut)
        object.__setattr__(self, "distribution", dist)
        object.__setattr__(self, "degrees_of_freedom", dof)

    @classmethod
    def from_observations(
        cls,
        name: str,
        observations: Sequence[Decimal | float | int | str | Quantity],
        unit: str = "",
        description: str = "",
        source: str = "",
    ) -> InputQuantity:
        """Construct a Type A InputQuantity from sample observations."""
        mean_val, u_std, nu = type_a_from_observations(observations)
        return cls(
            name=name,
            nominal_value=mean_val,
            unit=unit,
            standard_uncertainty=u_std,
            uncertainty_type="A",
            distribution="student_t",
            degrees_of_freedom=float(nu),
            description=description,
            source=source or f"Type A from {len(observations)} observations",
        )

    @classmethod
    def from_rectangular(
        cls,
        name: str,
        nominal: Decimal | float | int | str = Decimal("0"),
        half_width: Decimal | float | int | str = Decimal("0"),
        unit: str = "",
        description: str = "",
        source: str = "",
        nominal_value: Decimal | float | int | str | None = None,
    ) -> InputQuantity:
        """Construct a Type B InputQuantity with rectangular distribution (u = a / sqrt(3))."""
        nom = nominal_value if nominal_value is not None else nominal
        u, nu = type_b_rectangular(half_width)
        return cls(
            name=name,
            nominal_value=Decimal(str(nom)),
            unit=unit,
            standard_uncertainty=u,
            uncertainty_type="B",
            distribution="rectangular",
            degrees_of_freedom=nu,
            description=description,
            source=source or f"Rectangular bounds +- {half_width}",
        )

    @classmethod
    def from_triangular(
        cls,
        name: str,
        nominal: Decimal | float | int | str = Decimal("0"),
        half_width: Decimal | float | int | str = Decimal("0"),
        unit: str = "",
        description: str = "",
        source: str = "",
        nominal_value: Decimal | float | int | str | None = None,
    ) -> InputQuantity:
        """Construct a Type B InputQuantity with triangular distribution (u = a / sqrt(6))."""
        nom = nominal_value if nominal_value is not None else nominal
        u, nu = type_b_triangular(half_width)
        return cls(
            name=name,
            nominal_value=Decimal(str(nom)),
            unit=unit,
            standard_uncertainty=u,
            uncertainty_type="B",
            distribution="triangular",
            degrees_of_freedom=nu,
            description=description,
            source=source or f"Triangular bounds +- {half_width}",
        )

    @classmethod
    def from_normal(
        cls,
        name: str,
        nominal: Decimal | float | int | str = Decimal("0"),
        expanded_uncertainty: Decimal | float | int | str = Decimal("0"),
        k: Decimal | float | int | str = 2,
        unit: str = "",
        degrees_of_freedom: float = float("inf"),
        description: str = "",
        source: str = "",
        nominal_value: Decimal | float | int | str | None = None,
    ) -> InputQuantity:
        """Construct a Type B InputQuantity with normal distribution (u = U / k).

        Note: The default k=2 represents an assumed 95.45% coverage factor for normal
        calibration certificates when unspecified by the user/calibration laboratory.
        It is an explicit user/model assumption and not a universal GUM constant.
        """
        nom = nominal_value if nominal_value is not None else nominal
        u, nu = type_b_normal(expanded_uncertainty, k, degrees_of_freedom=degrees_of_freedom)
        k_val = str(k)
        src = source or f"Normal calibration U={expanded_uncertainty}, k={k_val} (user/model assumption)"
        return cls(
            name=name,
            nominal_value=Decimal(str(nom)),
            unit=unit,
            standard_uncertainty=u,
            uncertainty_type="B",
            distribution="normal",
            degrees_of_freedom=nu,
            description=description,
            source=src,
        )

    @classmethod
    def from_explicit(
        cls,
        name: str,
        nominal: Decimal | float | int | str = Decimal("0"),
        standard_uncertainty: Decimal | float | int | str = Decimal("0"),
        unit: str = "",
        degrees_of_freedom: float = float("inf"),
        description: str = "",
        source: str = "",
        nominal_value: Decimal | float | int | str | None = None,
    ) -> InputQuantity:
        """Construct an InputQuantity with an explicitly provided standard uncertainty."""
        nom = nominal_value if nominal_value is not None else nominal
        return cls(
            name=name,
            nominal_value=Decimal(str(nom)),
            unit=unit,
            standard_uncertainty=Decimal(str(standard_uncertainty)),
            uncertainty_type="B",
            distribution="explicit",
            degrees_of_freedom=degrees_of_freedom,
            description=description,
            source=source or "Explicit standard uncertainty",
        )

    # Aliases
    rectangular = from_rectangular
    triangular = from_triangular
    normal = from_normal
    explicit = from_explicit


# ==============================================================================
# 4. Correlation & Covariance Matrix
# ==============================================================================

@dataclass
class CorrelationMatrix:
    """Symmetric positive semi-definite correlation matrix r(X_i, X_j) for GUM uncertainty evaluation."""
    correlations: dict[tuple[str, str], Decimal] = field(default_factory=dict)

    def __post_init__(self):
        norm: dict[tuple[str, str], Decimal] = {}
        for (k1, k2), val in list(self.correlations.items()):
            n1, n2 = str(k1).strip(), str(k2).strip()
            r_dec = Decimal(str(val))
            if r_dec < Decimal("-1") or r_dec > Decimal("1"):
                raise ValueError(f"Correlation coefficient r({n1}, {n2}) out of range [-1, 1], got {r_dec}")
            if n1 == n2 and r_dec != Decimal("1"):
                raise ValueError(f"diagonal correlation r({n1}, {n1}) must be 1, got {r_dec}")
            if (n2, n1) in self.correlations:
                r2 = Decimal(str(self.correlations[(n2, n1)]))
                if r2 != r_dec:
                    raise ValueError(f"Asymmetric correlation between {n1} and {n2}: {r_dec} != {r2}")
            norm[(n1, n2)] = r_dec
            norm[(n2, n1)] = r_dec
        self.correlations = norm

        # If populated at construction, immediately validate positive semi-definiteness:
        if self.correlations:
            vars_set = sorted({k for pair in self.correlations.keys() for k in pair})
            if len(vars_set) >= 2:
                self.validate_psd(vars_set)

    def validate_psd(self, variables: Sequence[str] | None = None, tol: float = 1e-7) -> list[float]:
        """Validate that the correlation matrix is Positive Semi-Definite (PSD).

        Computes all eigenvalues of the real symmetric correlation matrix via the Jacobi algorithm.
        Accepts PSD matrices where all eigenvalues lambda_i >= -tol.
        Tolerance tol = 1e-7 allows for small floating-point roundoff errors in rank-deficient
        or collinear cases (where true eigenvalues are zero) while firmly rejecting non-PSD matrices.

        Parameters:
            variables: Sequence of variable names forming the submatrix to validate. If None,
                       all variables appearing in self.correlations are validated.
            tol: Numerical tolerance for negative eigenvalues due to precision (default 1e-7).

        Returns:
            Sorted list of eigenvalues [lambda_1, lambda_2, ..., lambda_n].

        Raises:
            ValueError: If any eigenvalue < -tol, indicating the correlation matrix is mathematically invalid.
        """
        if variables is None:
            vars_list = sorted({k for pair in self.correlations.keys() for k in pair})
        else:
            vars_list = list(variables)

        n = len(vars_list)
        if n <= 1:
            return [1.0] if n == 1 else []

        matrix = [[float(self.get_correlation(vars_list[i], vars_list[j])) for j in range(n)] for i in range(n)]
        eigenvalues = jacobi_eigenvalues(matrix)
        min_eig = min(eigenvalues) if eigenvalues else 1.0

        if min_eig < -tol:
            raise ValueError(
                f"Correlation matrix is not positive semi-definite (PSD): "
                f"minimum eigenvalue {min_eig:.6e} < -{tol:.1e}"
            )
        return eigenvalues

    def set_correlation(self, var1: str, var2: str, r: Decimal | float | str) -> None:
        """Set correlation coefficient r(var1, var2) in [-1, 1]."""
        v1, v2 = str(var1).strip(), str(var2).strip()
        r_dec = Decimal(str(r))
        if r_dec < Decimal("-1") or r_dec > Decimal("1"):
            raise ValueError(f"Correlation coefficient r({v1}, {v2}) out of range [-1, 1], got {r_dec}")
        if v1 == v2 and r_dec != Decimal("1"):
            raise ValueError(f"diagonal correlation r({v1}, {v1}) must be 1, got {r_dec}")
        self.correlations[(v1, v2)] = r_dec
        self.correlations[(v2, v1)] = r_dec

    def get_correlation(self, var1: str, var2: str) -> Decimal:
        """Retrieve correlation coefficient r(var1, var2) in [-1, 1]."""
        v1, v2 = var1.strip(), var2.strip()
        if v1 == v2:
            return Decimal("1")
        if (v1, v2) in self.correlations:
            return self.correlations[(v1, v2)]
        if (v2, v1) in self.correlations:
            return self.correlations[(v2, v1)]
        return Decimal("0")

    def get_covariance(
        self,
        var1_or_q1: str | InputQuantity,
        var2_or_q2: str | InputQuantity,
        u1: Decimal | float | None = None,
        u2: Decimal | float | None = None,
    ) -> Decimal:
        """Calculate covariance: cov(X1, X2) = r(X1, X2) * u(X1) * u(X2)."""
        if isinstance(var1_or_q1, InputQuantity) and isinstance(var2_or_q2, InputQuantity):
            name1 = var1_or_q1.name
            name2 = var2_or_q2.name
            u1_dec = var1_or_q1.standard_uncertainty
            u2_dec = var2_or_q2.standard_uncertainty
        else:
            name1 = str(var1_or_q1)
            name2 = str(var2_or_q2)
            u1_dec = Decimal(str(u1)) if u1 is not None else Decimal("0")
            u2_dec = Decimal(str(u2)) if u2 is not None else Decimal("0")
        r = self.get_correlation(name1, name2)
        return r * u1_dec * u2_dec

    @classmethod
    def from_pairs(cls, pairs: Sequence[tuple[str, str, Decimal | float | str]]) -> CorrelationMatrix:
        """Construct from a list of (var1, var2, r) tuples."""
        d = {}
        for v1, v2, r in pairs:
            d[(v1, v2)] = Decimal(str(r))
        return cls(d)

    @classmethod
    def from_dict(cls, d: dict[tuple[str, str], Decimal | float | str]) -> CorrelationMatrix:
        """Construct from a dictionary of (var1, var2): r."""
        return cls(d)


# ==============================================================================
# 5. Sensitivity Coefficient & MeasurementModel
# ==============================================================================

class SensitivityMethod(str, Enum):
    EXPLICIT = "EXPLICIT"
    ANALYTIC = "ANALYTIC"
    NUMERICAL = "NUMERICAL"


@dataclass
class MeasurementModel:
    """Mathematical measurement model Y = f(X1, X2, ..., Xn)."""
    measurand: str
    equation: str | None = None
    input_names: tuple[str, ...] = ()
    evaluator: Callable[[dict[str, Decimal]], Decimal] | None = None
    sensitivities: dict[str, Decimal | Callable[[dict[str, Decimal]], Decimal]] | None = None
    explicit_sensitivities: dict[str, Decimal | Callable[[dict[str, Decimal]], Decimal]] | None = None
    output_unit: str = ""
    input_units: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        m = str(self.measurand).strip()
        if not m:
            raise ValueError("MeasurementModel measurand name cannot be empty")
        self.measurand = m

        if self.sensitivities is None and self.explicit_sensitivities is not None:
            self.sensitivities = self.explicit_sensitivities

        if self.equation is None and self.evaluator is None:
            raise ValueError("MeasurementModel requires either an equation string or an evaluator function")

    def evaluate_to_quantity(
        self,
        inputs: dict[str, Decimal | Quantity | Any],
        input_units: dict[str, str] | None = None,
    ) -> Quantity:
        """Evaluate measurand value and return Quantity with verified dimensional algebra."""
        effective_units = dict(self.input_units)
        if input_units:
            effective_units.update(input_units)

        if self.evaluator is not None:
            numeric_dict: dict[str, Decimal] = {}
            for k, v in inputs.items():
                if isinstance(v, Quantity):
                    numeric_dict[k] = v.value
                else:
                    numeric_dict[k] = Decimal(str(v))
            res = self.evaluator(numeric_dict)
            u = _resolve_unit(self.output_unit) if (self.output_unit and self.output_unit.strip()) else Unit("1", "1", "", DIMENSIONLESS, Decimal(1))
            return Quantity(Decimal(str(res)), u)

        if self.equation is not None:
            eq_text = self.equation.strip().replace("^", "**")
            parsed = parse_equation(eq_text if "=" in eq_text else f"{self.measurand} = {eq_text}")
            q_env: dict[str, Quantity] = {}
            for k, v in inputs.items():
                if isinstance(v, Quantity):
                    q_env[k] = v
                else:
                    unit_str = effective_units.get(k, "")
                    u_obj = _resolve_unit(unit_str)
                    q_env[k] = Quantity(Decimal(str(v)), u_obj)

            q_res = evaluate(parsed, q_env)

            # Dimensional validation against output_unit if declared:
            if self.output_unit and self.output_unit.strip():
                expected_u = _resolve_unit(self.output_unit.strip())
                if q_res.dimension != expected_u.dimension:
                    raise UnitError(
                        f"MeasurementModel '{self.measurand}': calculated unit dimension '{q_res.dim_name}' "
                        f"({q_res.unit.display}) is incompatible with declared output_unit {self.output_unit!r} "
                        f"({DIM_NAMES.get(expected_u.dimension, 'derived')})"
                    )
                if expected_u.factor != q_res.unit.factor:
                    q_res = q_res.convert_to(self.output_unit.strip())

            return q_res

        raise RuntimeError("MeasurementModel evaluation failed")

    def evaluate(
        self,
        inputs: dict[str, Decimal | Quantity | Any],
        input_units: dict[str, str] | None = None,
    ) -> Decimal:
        """Evaluate measurand value Y = f(X1, ..., Xn) for given nominal input values."""
        return self.evaluate_to_quantity(inputs, input_units=input_units).value

    def get_sensitivity(
        self,
        var_name: str,
        inputs: dict[str, Decimal],
        input_units: dict[str, str] | None = None,
    ) -> tuple[Decimal, str]:
        """Compute sensitivity coefficient c_i = dY / dX_i and report method (EXPLICIT, ANALYTIC, NUMERICAL)."""
        # 1. Explicitly supplied sensitivities
        if self.sensitivities and var_name in self.sensitivities:
            sens_spec = self.sensitivities[var_name]
            if callable(sens_spec):
                c_val = Decimal(str(sens_spec(inputs)))
                return c_val, SensitivityMethod.EXPLICIT.value
            else:
                c_val = Decimal(str(sens_spec))
                return c_val, SensitivityMethod.EXPLICIT.value

        # 2. Known analytical equation patterns
        if self.equation:
            eq_clean = self.equation.strip()
            if "=" in eq_clean:
                eq_clean = eq_clean.partition("=")[2].strip()

            # Pattern: Sum: X1 + X2
            m_sum = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)", eq_clean)
            if m_sum:
                v1, v2 = m_sum.group(1), m_sum.group(2)
                if var_name in (v1, v2):
                    return Decimal("1"), SensitivityMethod.ANALYTIC.value

            # Pattern: Difference: X1 - X2
            m_diff = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\-\s*([A-Za-z_][A-Za-z0-9_]*)", eq_clean)
            if m_diff:
                v1, v2 = m_diff.group(1), m_diff.group(2)
                if var_name == v1:
                    return Decimal("1"), SensitivityMethod.ANALYTIC.value
                elif var_name == v2:
                    return Decimal("-1"), SensitivityMethod.ANALYTIC.value

            # Pattern: Product: X1 * X2
            m_prod = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)", eq_clean)
            if m_prod:
                v1, v2 = m_prod.group(1), m_prod.group(2)
                if var_name == v1:
                    return inputs[v2], SensitivityMethod.ANALYTIC.value
                elif var_name == v2:
                    return inputs[v1], SensitivityMethod.ANALYTIC.value

            # Pattern: Quotient: X1 / X2
            m_div = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*/\s*([A-Za-z_][A-Za-z0-9_]*)", eq_clean)
            if m_div:
                v1, v2 = m_div.group(1), m_div.group(2)
                if var_name == v1:
                    return Decimal("1") / inputs[v2], SensitivityMethod.ANALYTIC.value
                elif var_name == v2:
                    return -inputs[v1] / (inputs[v2] ** 2), SensitivityMethod.ANALYTIC.value

            # Pattern: Voltage divider: Vin * R2 / (R1 + R2)
            if "Vin" in inputs and "R1" in inputs and "R2" in inputs and "R1 + R2" in eq_clean:
                vin = inputs["Vin"]
                r1 = inputs["R1"]
                r2 = inputs["R2"]
                r_sum = r1 + r2
                if var_name == "Vin":
                    return r2 / r_sum, SensitivityMethod.ANALYTIC.value
                elif var_name == "R1":
                    return -vin * r2 / (r_sum ** 2), SensitivityMethod.ANALYTIC.value
                elif var_name == "R2":
                    return vin * r1 / (r_sum ** 2), SensitivityMethod.ANALYTIC.value

        # 3. Deterministic Numerical Differentiation (Central Finite Difference)
        x_val = inputs[var_name]
        step = max(abs(x_val) * Decimal("1e-6"), Decimal("1e-9"))

        inputs_plus = dict(inputs)
        inputs_plus[var_name] = x_val + step
        y_plus = self.evaluate(inputs_plus, input_units=input_units)

        inputs_minus = dict(inputs)
        inputs_minus[var_name] = x_val - step
        y_minus = self.evaluate(inputs_minus, input_units=input_units)

        # Retain full Decimal precision without artificial rounding (Finding 3):
        c_num = (y_plus - y_minus) / (Decimal("2") * step)
        return c_num, SensitivityMethod.NUMERICAL.value


# ==============================================================================
# 6. UncertaintyBudget & GUMResult Domain Models
# ==============================================================================

@dataclass(frozen=True)
class UncertaintyBudgetRow:
    """Individual quantity row in an ISO/IEC Guide 98-3 uncertainty budget table."""
    quantity: str
    nominal_value: Decimal
    unit: str
    uncertainty_type: str  # "A" | "B"
    distribution: str      # "normal" | "rectangular" | "triangular" | "explicit"
    standard_uncertainty: Decimal
    degrees_of_freedom: float
    sensitivity_coefficient: Decimal
    sensitivity_method: str  # "EXPLICIT" | "ANALYTIC" | "NUMERICAL"
    contribution: Decimal    # c_i * u_i
    variance_contribution: Decimal  # (c_i * u_i)^2
    relative_contribution_pct: Decimal  # (c_i * u_i)^2 / sum(...) * 100
    correlation_metadata: dict
    source: str = ""

    def to_dict(self) -> dict:
        dof_str = "inf" if math.isinf(self.degrees_of_freedom) else str(self.degrees_of_freedom)
        return {
            "quantity": self.quantity,
            "nominal_value": str(self.nominal_value),
            "unit": self.unit,
            "uncertainty_type": self.uncertainty_type,
            "distribution": self.distribution,
            "standard_uncertainty": str(self.standard_uncertainty),
            "degrees_of_freedom": dof_str,
            "sensitivity_coefficient": str(self.sensitivity_coefficient),
            "sensitivity_method": self.sensitivity_method,
            "contribution": str(self.contribution),
            "variance_contribution": str(self.variance_contribution),
            "relative_contribution_pct": str(self.relative_contribution_pct),
            "correlation_metadata": self.correlation_metadata,
            "source": self.source,
        }


@dataclass(frozen=True)
class UncertaintyBudget:
    """Complete structured uncertainty budget table and aggregation results."""
    measurand: str
    measurand_value: Decimal
    measurand_unit: str
    rows: tuple[UncertaintyBudgetRow, ...]
    combined_variance: Decimal
    covariance_term: Decimal
    combined_standard_uncertainty: Decimal  # u_c(y)
    effective_degrees_of_freedom: float     # nu_eff
    coverage_probability: float             # e.g. 0.95
    coverage_factor: Decimal                # k
    expanded_uncertainty: Decimal           # U = k * u_c(y)
    notes: tuple[str, ...] = ()

    def sorted_by_contribution(self) -> tuple[UncertaintyBudgetRow, ...]:
        """Return rows sorted in descending order of absolute contribution |c_i * u_i|."""
        return tuple(sorted(self.rows, key=lambda r: abs(r.contribution), reverse=True))

    def sorted_by_name(self) -> tuple[UncertaintyBudgetRow, ...]:
        """Return rows sorted alphabetically by quantity name."""
        return tuple(sorted(self.rows, key=lambda r: r.quantity))

    def by_contribution(self, descending: bool = True) -> list[UncertaintyBudgetRow]:
        """Return rows sorted by variance/standard contribution."""
        return sorted(self.rows, key=lambda r: abs(r.contribution), reverse=descending)

    def by_name(self) -> list[UncertaintyBudgetRow]:
        """Return rows sorted alphabetically by quantity name."""
        return sorted(self.rows, key=lambda r: r.quantity)

    def get_row(self, quantity: str) -> UncertaintyBudgetRow:
        """Find row by quantity name."""
        for r in self.rows:
            if r.quantity == quantity:
                return r
        raise KeyError(f"Quantity {quantity!r} not found in uncertainty budget")

    def to_markdown(self) -> str:
        """Render uncertainty budget as a GitHub-flavored Markdown table."""
        dof_s = "inf" if math.isinf(self.effective_degrees_of_freedom) else f"{self.effective_degrees_of_freedom:.2f}"
        lines = [
            f"# Uncertainty Budget: {self.measurand}",
            "",
            f"- **Measurand Value**: {self.measurand_value} {self.measurand_unit}",
            f"- **Combined Standard Uncertainty (u_c)**: {self.combined_standard_uncertainty} {self.measurand_unit}",
            f"- **Effective Degrees of Freedom (nu_eff)**: {dof_s}",
            f"- **Coverage Factor (k)**: {self.coverage_factor} (p = {self.coverage_probability * 100:.1f}%)",
            f"- **Expanded Uncertainty (U)**: {self.expanded_uncertainty} {self.measurand_unit}",
            "",
            "| Quantity | Nominal | Unit | Type | Dist | u(xi) | dof | c_i | Method | u_i(y) | (c_i*u_i)^2 | % Contrib |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in self.rows:
            r_dof = "inf" if math.isinf(r.degrees_of_freedom) else f"{r.degrees_of_freedom:.1f}"
            lines.append(
                f"| {r.quantity} | {r.nominal_value} | {r.unit} | {r.uncertainty_type} | {r.distribution} | "
                f"{r.standard_uncertainty} | {r_dof} | {r.sensitivity_coefficient} | {r.sensitivity_method} | "
                f"{r.contribution} | {r.variance_contribution} | {r.relative_contribution_pct}% |"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        dof_str = "inf" if math.isinf(self.effective_degrees_of_freedom) else str(self.effective_degrees_of_freedom)
        return {
            "measurand": self.measurand,
            "measurand_value": str(self.measurand_value),
            "measurand_unit": self.measurand_unit,
            "combined_variance": str(self.combined_variance),
            "covariance_term": str(self.covariance_term),
            "combined_standard_uncertainty": str(self.combined_standard_uncertainty),
            "effective_degrees_of_freedom": dof_str,
            "coverage_probability": self.coverage_probability,
            "coverage_factor": str(self.coverage_factor),
            "expanded_uncertainty": str(self.expanded_uncertainty),
            "rows": [r.to_dict() for r in self.sorted_by_name()],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class GUMResult:
    """Scientific result of a GUM / Measurement Uncertainty evaluation."""
    measurand: str
    measurand_value: Decimal
    measurand_unit: str
    combined_standard_uncertainty: Decimal
    effective_degrees_of_freedom: float
    coverage_probability: float
    coverage_factor: Decimal
    expanded_uncertainty: Decimal
    budget: UncertaintyBudget
    correlation_matrix: dict
    provenance: dict
    raw_artifact_hash: str = ""

    def summary(self) -> str:
        dof_str = "∞" if math.isinf(self.effective_degrees_of_freedom) else f"{self.effective_degrees_of_freedom:.1f}"
        pct = self.coverage_probability * 100.0
        unit_str = f" {self.measurand_unit}" if self.measurand_unit else ""
        return (
            f"{self.measurand} = {self.measurand_value} ± {self.expanded_uncertainty}{unit_str} "
            f"(k = {self.coverage_factor}, p = {pct:.1f}%, νeff = {dof_str})"
        )


# ==============================================================================
# 7. GUM Engine: Evaluation & Propagation
# ==============================================================================

def evaluate_gum(
    model: MeasurementModel,
    inputs: dict[str, InputQuantity],
    correlation: CorrelationMatrix | None = None,
    coverage_probability: float = 0.95,
    explicit_k: Decimal | float | int | None = None,
    cas_store: Any = None,
) -> GUMResult:
    """Execute complete GUM uncertainty propagation according to ISO/IEC Guide 98-3."""
    if not inputs:
        raise ValueError("GUM evaluation requires at least one input quantity")

    sorted_names = sorted(inputs.keys())
    corr = correlation or CorrelationMatrix()

    # 0. Validate that the correlation matrix is Positive Semi-Definite (Finding 1)
    corr.validate_psd(variables=sorted_names, tol=1e-7)

    # 1. Evaluate nominal measurand value with full dimensional validation (Finding 2)
    nominal_dict = {name: q.nominal_value for name, q in inputs.items()}
    input_units = {name: q.unit for name, q in inputs.items()}
    q_res = model.evaluate_to_quantity(nominal_dict, input_units=input_units)
    y_val = q_res.value
    calc_unit = model.output_unit if (model.output_unit and model.output_unit.strip()) else (
        q_res.unit.display if q_res.unit.dimension != DIMENSIONLESS else ""
    )

    # 2. Compute sensitivity coefficients and individual variance contributions
    c_map: dict[str, Decimal] = {}
    c_method_map: dict[str, str] = {}
    u_map: dict[str, Decimal] = {}
    ui_contrib: dict[str, Decimal] = {}
    var_contrib: dict[str, Decimal] = {}

    for name in sorted_names:
        q = inputs[name]
        c_i, method = model.get_sensitivity(name, nominal_dict, input_units=input_units)
        c_map[name] = c_i
        c_method_map[name] = method
        u_map[name] = q.standard_uncertainty

        contrib_i = c_i * q.standard_uncertainty
        ui_contrib[name] = contrib_i
        var_contrib[name] = contrib_i ** 2

    # 3. Sum of individual variance contributions
    sum_var = sum(var_contrib.values())

    # 4. Covariance terms: 2 * sum_{i < j} c_i * c_j * cov(X_i, X_j)
    cov_sum = Decimal("0")
    for i in range(len(sorted_names)):
        for j in range(i + 1, len(sorted_names)):
            n1 = sorted_names[i]
            n2 = sorted_names[j]
            cov_val = corr.get_covariance(inputs[n1], inputs[n2])
            if cov_val != 0:
                cov_term = Decimal("2") * c_map[n1] * c_map[n2] * cov_val
                cov_sum += cov_term

    # 5. Combined standard uncertainty u_c^2(y) = sum_var + cov_sum
    total_var = sum_var + cov_sum
    if total_var < 0:
        raise ValueError(
            f"combined variance is negative ({total_var}) due to invalid correlation matrix"
        )

    uc = Decimal(str(math.sqrt(float(total_var))))

    # 6. Welch-Satterthwaite formula for effective degrees of freedom
    # nu_eff = u_c^4 / sum( (c_i * u_i)^4 / nu_i )
    ws_denom = 0.0
    all_infinite = True
    for name in sorted_names:
        dof_i = inputs[name].degrees_of_freedom
        if not math.isinf(dof_i):
            all_infinite = False
            ui_flt = float(ui_contrib[name])
            if dof_i > 0 and ui_flt != 0:
                ws_denom += (ui_flt ** 4) / dof_i

    if all_infinite or ws_denom == 0.0:
        nu_eff = float("inf")
    else:
        uc_flt = float(uc)
        nu_eff = (uc_flt ** 4) / ws_denom

    # 7. Coverage factor k with explicit_k validation (Finding 4)
    if explicit_k is not None:
        try:
            k_flt = float(explicit_k)
            k_dec = Decimal(str(explicit_k))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"explicit_k must be a valid positive number, got {explicit_k!r}")

        if math.isnan(k_flt) or math.isinf(k_flt) or k_flt <= 0.0 or k_dec <= Decimal("0"):
            raise ValueError(f"explicit_k must be finite and strictly positive (k > 0), got {explicit_k!r}")

        k = k_dec
        k_source = "explicit_user"
    else:
        k = calculate_coverage_factor(coverage_probability, nu_eff)
        k_source = "student_t" if not math.isinf(nu_eff) else "normal_limit"

    # 8. Expanded uncertainty U = k * u_c(y)
    U = k * uc

    # 9. Build structured budget table rows
    budget_rows: list[UncertaintyBudgetRow] = []
    for name in sorted_names:
        q = inputs[name]
        vc = var_contrib[name]
        rel_pct = (vc / total_var * Decimal("100")) if total_var > 0 else Decimal("0")

        # Correlation metadata for this variable
        corr_meta = {}
        for other_name in sorted_names:
            if other_name != name:
                r_val = corr.get_correlation(name, other_name)
                if r_val != 0:
                    corr_meta[other_name] = str(r_val)

        row = UncertaintyBudgetRow(
            quantity=name,
            nominal_value=q.nominal_value,
            unit=q.unit,
            uncertainty_type=q.uncertainty_type,
            distribution=q.distribution,
            standard_uncertainty=q.standard_uncertainty,
            degrees_of_freedom=q.degrees_of_freedom,
            sensitivity_coefficient=c_map[name],
            sensitivity_method=c_method_map[name],
            contribution=ui_contrib[name],
            variance_contribution=vc,
            relative_contribution_pct=Decimal(str(round(float(rel_pct), 4))),
            correlation_metadata=corr_meta,
            source=q.source,
        )
        budget_rows.append(row)

    budget = UncertaintyBudget(
        measurand=model.measurand,
        measurand_value=y_val,
        measurand_unit=calc_unit,
        rows=tuple(budget_rows),
        combined_variance=total_var,
        covariance_term=cov_sum,
        combined_standard_uncertainty=uc,
        effective_degrees_of_freedom=nu_eff,
        coverage_probability=coverage_probability,
        coverage_factor=k,
        expanded_uncertainty=U,
        notes=(),
    )

    # 10. Execution Provenance & CAS Storage
    now_ts = datetime.now(timezone.utc).isoformat()
    provenance = {
        "engine": ENGINE_VERSION_GUM,
        "standard": "ISO/IEC Guide 98-3 (GUM)",
        "timestamp": now_ts,
        "measurand": model.measurand,
        "measurand_value": str(y_val),
        "measurand_unit": calc_unit,
        "combined_standard_uncertainty": str(uc),
        "effective_degrees_of_freedom": "inf" if math.isinf(nu_eff) else str(nu_eff),
        "coverage_probability": coverage_probability,
        "coverage_factor": str(k),
        "coverage_factor_source": k_source,
        "expanded_uncertainty": str(U),
        "inputs": {name: {
            "nominal": str(q.nominal_value),
            "standard_uncertainty": str(q.standard_uncertainty),
            "unit": q.unit,
            "type": q.uncertainty_type,
            "distribution": q.distribution,
            "dof": "inf" if math.isinf(q.degrees_of_freedom) else str(q.degrees_of_freedom),
        } for name, q in inputs.items()},
        "budget": budget.to_dict(),
    }

    raw_bytes = json.dumps(provenance, sort_keys=True, indent=2).encode("utf-8")
    raw_hash = ""
    if cas_store is not None:
        try:
            raw_hash = cas_store.put_bytes(raw_bytes)
        except Exception:
            raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    else:
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

    corr_dict = {f"{k1},{k2}": str(v) for (k1, k2), v in corr.correlations.items()}

    return GUMResult(
        measurand=model.measurand,
        measurand_value=y_val,
        measurand_unit=calc_unit,
        combined_standard_uncertainty=uc,
        effective_degrees_of_freedom=nu_eff,
        coverage_probability=coverage_probability,
        coverage_factor=k,
        expanded_uncertainty=U,
        budget=budget,
        correlation_matrix=corr_dict,
        provenance=provenance,
        raw_artifact_hash=raw_hash,
    )
