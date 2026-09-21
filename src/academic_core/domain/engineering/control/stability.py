"""F8-P1 Routh-Hurwitz exact stability (NEW).

Exact Fraction table, no iteration. Zero-row -> auxiliary polynomial
plus derivative row (honest, tagged). First-column zero -> small
positive EPS substitution (explicitly tagged). No silent division.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.poly import (
    Polynomial,
    durand_kerner_roots,
    validate_roots,
)
from academic_core.domain.engineering.control.tf import TransferFunctionTF

EPS_SUBSTITUTE = Fraction(1, 1000000)


def _decimal_to_fraction(value: Decimal) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ControlError(ControlStatus.INVALID, "Routh needs Decimal coefficients")
    if not value.is_finite():
        raise ControlError(ControlStatus.INVALID, "Routh needs finite coefficients")
    return Fraction(value)


@dataclass(frozen=True)
class RouthResult:
    table: tuple
    first_column: tuple
    sign_changes: int
    rhp_count: int
    verdict: str
    used_epsilon: bool
    used_auxiliary: bool
    aux_degree: int
    detail: str = ""


def _build_table(fracs: list) -> tuple:
    n = len(fracs) - 1
    ncols = (n + 2) // 2
    rows: list = []
    r0 = [Fraction(0)] * ncols
    r1 = [Fraction(0)] * ncols
    for j in range(ncols):
        i0 = 2 * j
        i1 = 2 * j + 1
        r0[j] = fracs[i0] if i0 < len(fracs) else Fraction(0)
        r1[j] = fracs[i1] if i1 < len(fracs) else Fraction(0)
    rows.append(r0)
    if n >= 1:
        rows.append(r1)
    used_eps = False
    used_aux = False
    aux_deg = 0
    for i in range(2, n + 1):
        prev = rows[i - 1]
        prev2 = rows[i - 2]
        if all(v == 0 for v in prev):
            # Zero row: auxiliary polynomial from prev2, differentiate it.
            used_aux = True
            order = n - (i - 2)
            aux_deg = order
            # Coefficients of aux poly in descending powers stepping by 2.
            # Derivative row: multiply each entry by its power.
            new_row = [Fraction(0)] * ncols
            for j in range(ncols):
                power = order - 2 * j
                if power > 0 and j < len(prev2):
                    new_row[j] = prev2[j] * power
            rows.append(new_row)
            prev = new_row
            prev2 = rows[i - 2]
        pivot = prev[0]
        if pivot == 0:
            used_eps = True
            pivot = EPS_SUBSTITUTE
            fixed = list(prev)
            fixed[0] = EPS_SUBSTITUTE
            rows[i - 1] = fixed
            prev = fixed
        new_row = [Fraction(0)] * ncols
        for j in range(ncols - 1):
            a = prev[0]
            b = prev2[j + 1] if j + 1 < len(prev2) else Fraction(0)
            c = prev2[0]
            d = prev[j + 1] if j + 1 < len(prev) else Fraction(0)
            new_row[j] = (a * b - c * d) / a if a != 0 else Fraction(0)
        new_row[ncols - 1] = Fraction(0)
        rows.append(new_row)
    return tuple(tuple(r) for r in rows), used_eps, used_aux, aux_deg


def _sign_changes(first_col: list) -> int:
    signs: list = []
    for v in first_col:
        if v > 0:
            signs.append(1)
        elif v < 0:
            signs.append(-1)
        else:
            signs.append(0)
    # Epsilon rows never leave literal zeros (replaced above); a residual
    # zero here means a structurally zero first column -> count conservatively.
    compact = [s for s in signs if s != 0]
    changes = 0
    for a, b in zip(compact, compact[1:]):
        if a != b:
            changes += 1
    return changes


def routh_of_poly(poly: Polynomial) -> RouthResult:
    if not isinstance(poly, Polynomial):
        raise ControlError(ControlStatus.INVALID, "Routh needs a Polynomial")
    if len(poly.coeffs) == 1 and poly.coeffs[0] == 0:
        raise ControlError(ControlStatus.INVALID, "Routh needs a nonzero polynomial")
    fracs = [_decimal_to_fraction(c) for c in poly.coeffs]
    table, used_eps, used_aux, aux_deg = _build_table(fracs)
    first_col = [row[0] for row in table]
    changes = _sign_changes(first_col)
    if changes > 0:
        verdict = "UNSTABLE"
    elif used_aux:
        verdict = "MARGINAL"
    else:
        verdict = "STABLE"
    table_str = tuple(tuple(str(v) for v in row) for row in table)
    first_str = tuple(str(v) for v in first_col)
    detail = "ok"
    if used_eps:
        detail = "epsilon-substitution applied to zero first-column entry"
    if used_aux:
        detail = "auxiliary-polynomial row applied to zero row"
    return RouthResult(
        table=table_str,
        first_column=first_str,
        sign_changes=changes,
        rhp_count=changes,
        verdict=verdict,
        used_epsilon=used_eps,
        used_auxiliary=used_aux,
        aux_degree=aux_deg,
        detail=detail,
    )


def routh_of_tf(h: TransferFunctionTF) -> RouthResult:
    if not isinstance(h, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "Routh needs a TF")
    return routh_of_poly(h.den)


@dataclass(frozen=True)
class PoleInventory:
    poles: tuple
    routh: RouthResult
    rhp_dk: int
    agreement: bool
    status: ControlStatus
    detail: str = ""


def _count_rhp(roots: tuple, tol: Decimal = Decimal("1e-24")) -> int:
    total = 0
    for z in roots:
        if z.re > tol:
            total += 1
    return total


def pole_inventory(h: TransferFunctionTF) -> PoleInventory:
    if not isinstance(h, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "inventory needs a TF")
    res = durand_kerner_roots(h.den)
    if res.status != ControlStatus.COMPLETED:
        rh = routh_of_tf(h)
        return PoleInventory(
            poles=res.roots, routh=rh, rhp_dk=-1, agreement=False,
            status=res.status, detail="root core non-converged",
        )
    validation = validate_roots(h.den, res)
    if not validation.count_ok or not validation.residuals_ok:
        rh = routh_of_tf(h)
        return PoleInventory(
            poles=res.roots, routh=rh, rhp_dk=-1, agreement=False,
            status=ControlStatus.NUMERIC_ERROR, detail="root validation failed",
        )
    rh = routh_of_tf(h)
    rhp = _count_rhp(res.roots)
    agree = rhp == rh.rhp_count
    status = ControlStatus.COMPLETED if agree else ControlStatus.INCONSISTENT
    detail = "DK/Routh agree" if agree else "DK/Routh disagree"
    return PoleInventory(
        poles=res.roots, routh=rh, rhp_dk=rhp, agreement=agree,
        status=status, detail=detail,
    )
