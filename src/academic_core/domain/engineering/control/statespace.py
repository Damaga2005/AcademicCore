"""F8-P1 state-space SISO layer (NEW).

x_dot = A x + B u, y = C x + D u with real Decimal matrices.
TF <-> SS via controllable canonical form (exact). SS -> TF via the
Faddeeva recurrence in Decimal (exact for the certified small-integer
fixtures; working precision 50 otherwise). Ranks exact over Fraction.
Eigenvalues of A via the characteristic polynomial plus the pole core.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Sequence

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.poly import (
    Polynomial,
    durand_kerner_roots,
    make_polynomial,
)
from academic_core.domain.engineering.control.tf import TransferFunctionTF
from academic_core.domain.engineering.math import make_context


def _req_matrix(values: Sequence[Sequence[object]], label: str) -> tuple:
    if not isinstance(values, (tuple, list)) or len(values) == 0:
        raise ControlError(ControlStatus.INVALID, label + " needs non-empty rows")
    rows: list = []
    width: int | None = None
    for row in values:
        if not isinstance(row, (tuple, list)) or len(row) == 0:
            raise ControlError(ControlStatus.INVALID, label + " needs non-empty rows")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ControlError(ControlStatus.INVALID, label + " must be rectangular")
        dec_row: list = []
        for item in row:
            if isinstance(item, bool):
                raise ControlError(ControlStatus.INVALID, label + " rejects bool")
            if isinstance(item, Decimal):
                dec = item
            elif isinstance(item, int):
                dec = Decimal(item)
            elif isinstance(item, str):
                try:
                    dec = Decimal(item.strip())
                except Exception as exc:
                    raise ControlError(ControlStatus.INVALID, label + " bad string") from exc
            else:
                raise ControlError(ControlStatus.INVALID, label + " entries must be Decimal/int/str")
            if not dec.is_finite():
                raise ControlError(ControlStatus.INVALID, label + " entries must be finite")
            dec_row.append(dec)
        rows.append(tuple(dec_row))
    return tuple(rows)


def _mat_mul(a: tuple, b: tuple, ctx) -> tuple:
    n = len(a)
    m = len(b[0])
    k = len(b)
    out: list = []
    for i in range(n):
        row: list = []
        for j in range(m):
            acc = Decimal(0)
            for t in range(k):
                acc = ctx.add(acc, ctx.multiply(a[i][t], b[t][j]))
            row.append(acc)
        out.append(tuple(row))
    return tuple(out)


def _mat_add(a: tuple, b: tuple, ctx) -> tuple:
    return tuple(tuple(ctx.add(x, y) for x, y in zip(ra, rb)) for ra, rb in zip(a, b))


def _mat_scale(a: tuple, alpha: Decimal, ctx) -> tuple:
    return tuple(tuple(ctx.multiply(x, alpha) for x in row) for row in a)


def _identity(n: int) -> tuple:
    return tuple(tuple(Decimal(1) if i == j else Decimal(0) for j in range(n)) for i in range(n))


def _zeros(n: int) -> tuple:
    return tuple(tuple(Decimal(0) for _ in range(n)) for _ in range(n))


def _trace(a: tuple, ctx) -> Decimal:
    acc = Decimal(0)
    for i in range(len(a)):
        acc = ctx.add(acc, a[i][i])
    return acc


@dataclass(frozen=True)
class StateSpace:
    """SISO state-space model (validation-only post-init)."""

    a: tuple
    b: tuple
    c: tuple
    d: tuple

    def __post_init__(self) -> None:
        for label, mat in (("A", self.a), ("B", self.b), ("C", self.c), ("D", self.d)):
            if not isinstance(mat, tuple) or len(mat) == 0:
                raise ControlError(ControlStatus.INVALID, label + " must be a non-empty tuple")
            for row in mat:
                if not isinstance(row, tuple) or len(row) == 0:
                    raise ControlError(ControlStatus.INVALID, label + " rows must be tuples")
                for item in row:
                    if isinstance(item, bool) or not isinstance(item, Decimal):
                        raise ControlError(ControlStatus.INVALID, label + " entries must be Decimal")
                    if not item.is_finite():
                        raise ControlError(ControlStatus.INVALID, label + " entries must be finite")
        n = len(self.a)
        if any(len(row) != n for row in self.a):
            raise ControlError(ControlStatus.INVALID, "A must be square")
        if n < 1:
            raise ControlError(ControlStatus.INVALID, "state dimension >= 1 required")
        if len(self.b) != n or any(len(row) != 1 for row in self.b):
            raise ControlError(ControlStatus.INVALID, "B must be n x 1")
        if len(self.c) != 1 or len(self.c[0]) != n:
            raise ControlError(ControlStatus.INVALID, "C must be 1 x n")
        if len(self.d) != 1 or len(self.d[0]) != 1:
            raise ControlError(ControlStatus.INVALID, "D must be 1 x 1")

    @property
    def order(self) -> int:
        return len(self.a)

    @staticmethod
    def create(a: Sequence[Sequence[object]], b: Sequence[Sequence[object]],
               c: Sequence[Sequence[object]], d: Sequence[Sequence[object]]) -> "StateSpace":
        return StateSpace(a=_req_matrix(a, "A"), b=_req_matrix(b, "B"),
                          c=_req_matrix(c, "C"), d=_req_matrix(d, "D"))

    def to_dict(self) -> dict:
        return {
            "a": [[str(v) for v in row] for row in self.a],
            "b": [[str(v) for v in row] for row in self.b],
            "c": [[str(v) for v in row] for row in self.c],
            "d": [[str(v) for v in row] for row in self.d],
        }


def make_statespace(a: Sequence[Sequence[object]], b: Sequence[Sequence[object]],
                    c: Sequence[Sequence[object]], d: Sequence[Sequence[object]]) -> StateSpace:
    return StateSpace.create(a, b, c, d)


def tf_to_ss(h: TransferFunctionTF) -> StateSpace:
    """Controllable canonical realisation (exact)."""
    if not isinstance(h, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "tf_to_ss needs a TF")
    ctx = make_context()
    n = h.den.degree
    a0 = h.den.coeffs[0]
    den_monic = [ctx.divide(c, a0) for c in h.den.coeffs]
    num_padded = (Decimal(0),) * (n + 1 - len(h.num.coeffs)) + h.num.coeffs
    num_monic = [ctx.divide(c, a0) for c in num_padded]
    feed = num_monic[0]
    # Companion A.
    a_rows: list = []
    for i in range(n):
        row: list = []
        for j in range(n):
            if i < n - 1:
                row.append(Decimal(1) if j == i + 1 else Decimal(0))
            else:
                row.append(ctx.minus(den_monic[n - j]))
        a_rows.append(tuple(row))
    b_rows = tuple((Decimal(1) if i == n - 1 else Decimal(0),) for i in range(n))
    # Controller form reads the numerator ascending: C[j] = e_{n-j} - d_{n-j} D.
    c_row = tuple(
        ctx.subtract(num_monic[n - j], ctx.multiply(den_monic[n - j], feed))
        for j in range(n)
    )
    return StateSpace(
        a=tuple(a_rows), b=b_rows, c=(c_row,), d=((ctx.plus(feed),),),
    )


def _faddeeva(a: tuple) -> tuple:
    """Return (char_coeffs_desc, adj_mats M_1..M_n) for (sI - A)."""
    ctx = make_context()
    n = len(a)
    ident = _identity(n)
    m_prev = _zeros(n)
    p_prev = Decimal(1)
    mats: list = []
    coeffs_rev: list = [Decimal(1)]
    for _k in range(1, n + 1):
        m_k = _mat_add(_mat_mul(a, m_prev, ctx), _mat_scale(ident, p_prev, ctx), ctx)
        mats.append(m_k)
        tr = _trace(_mat_mul(a, m_k, ctx), ctx)
        p_k = ctx.divide(ctx.minus(tr), Decimal(_k))
        coeffs_rev.append(p_k)
        m_prev = m_k
        p_prev = p_k
    # coeffs_rev = [1, c1, ..., cn] for s^n + c1 s^{n-1} + ... + cn.
    return tuple(coeffs_rev), tuple(mats)


def ss_to_tf(ss: StateSpace) -> TransferFunctionTF:
    """H(s) = C adj(sI - A) B / det(sI - A) + D."""
    if not isinstance(ss, StateSpace):
        raise ControlError(ControlStatus.INVALID, "ss_to_tf needs a StateSpace")
    ctx = make_context()
    n = ss.order
    char_desc, adj_mats = _faddeeva(ss.a)
    den = Polynomial(coeffs=tuple(char_desc))
    # Numerator: C adj(s) B as polynomial; adj(s) = s^{n-1} M_1 + ... + M_n.
    num_coeffs = [Decimal(0)] * (n + 1)
    for power_index, mat in enumerate(adj_mats):
        # mat = M_{k}, k = power_index + 1, weighting s^{n-k}: in the
        # descending array (index i <-> s^{n-i}) that is slot k.
        degree_slot = power_index + 1
        # Scalar C mat B.
        tmp = _mat_mul(mat, _col(ss.b), ctx)
        scalar = Decimal(0)
        c_row = ss.c[0]
        for j in range(n):
            scalar = ctx.add(scalar, ctx.multiply(c_row[j], tmp[j][0]))
        num_coeffs[degree_slot] = ctx.add(num_coeffs[degree_slot], scalar)
    # Add D * den.
    d_val = ss.d[0][0]
    for i, dc in enumerate(den.coeffs):
        num_coeffs[i] = ctx.add(num_coeffs[i], ctx.multiply(d_val, dc))
    # C adj(sI - A) B has degree <= n - 1: strip leading zeros (D re-adds
    # degree n only for biproper systems).
    start = 0
    while start < len(num_coeffs) - 1 and num_coeffs[start] == 0:
        start += 1
    num = Polynomial(coeffs=tuple(num_coeffs[start:]))
    if num.degree > den.degree:
        raise ControlError(ControlStatus.INVALID, "SS->TF result improper")
    return TransferFunctionTF(num=num, den=den)


def _col(b: tuple) -> tuple:
    return tuple((row[0],) if isinstance(row, tuple) else (row,) for row in b)


def _fraction_rank(rows: tuple) -> int:
    fracs = [[Fraction(item) for item in row] for row in rows]
    n_rows = len(fracs)
    n_cols = len(fracs[0]) if fracs else 0
    rank = 0
    row = 0
    for col in range(n_cols):
        pivot = None
        for r in range(row, n_rows):
            if fracs[r][col] != 0:
                pivot = r
                break
        if pivot is None:
            continue
        fracs[row], fracs[pivot] = fracs[pivot], fracs[row]
        piv = fracs[row][col]
        fracs[row] = [v / piv for v in fracs[row]]
        for r in range(n_rows):
            if r == row:
                continue
            factor = fracs[r][col]
            if factor != 0:
                fracs[r] = [fracs[r][k] - factor * fracs[row][k] for k in range(n_cols)]
        rank += 1
        row += 1
    return rank


def ctrb_rank(ss: StateSpace) -> int:
    if not isinstance(ss, StateSpace):
        raise ControlError(ControlStatus.INVALID, "ctrb needs a StateSpace")
    ctx = make_context()
    n = ss.order
    cols: list = [tuple(row[0] for row in ss.b)]
    power = _identity(n)
    current = tuple(row[0] for row in ss.b)
    for _ in range(1, n):
        power = _mat_mul(ss.a, power, ctx)
        vec = [Decimal(0)] * n
        b_col = [row[0] for row in ss.b]
        for i in range(n):
            acc = Decimal(0)
            for j in range(n):
                acc = ctx.add(acc, ctx.multiply(power[i][j], b_col[j]))
            vec[i] = acc
        cols.append(tuple(vec))
    rows = tuple(tuple(cols[j][i] for j in range(n)) for i in range(n))
    return _fraction_rank(rows)


def obsv_rank(ss: StateSpace) -> int:
    if not isinstance(ss, StateSpace):
        raise ControlError(ControlStatus.INVALID, "obsv needs a StateSpace")
    ctx = make_context()
    n = ss.order
    c_row = ss.c[0]
    rows: list = [tuple(c_row)]
    power = _identity(n)
    for _ in range(1, n):
        power = _mat_mul(power, ss.a, ctx)
        new_row = [Decimal(0)] * n
        for j in range(n):
            acc = Decimal(0)
            for t in range(n):
                acc = ctx.add(acc, ctx.multiply(c_row[t], power[t][j]))
            new_row[j] = acc
        rows.append(tuple(new_row))
    return _fraction_rank(tuple(rows))


def ss_eigenvalues(ss: StateSpace) -> tuple:
    if not isinstance(ss, StateSpace):
        raise ControlError(ControlStatus.INVALID, "eigenvalues need a StateSpace")
    char_desc, _ = _faddeeva(ss.a)
    res = durand_kerner_roots(Polynomial(coeffs=tuple(char_desc)))
    if res.status != ControlStatus.COMPLETED:
        raise ControlError(res.status, "eigenvalue core did not converge")
    return res.roots
