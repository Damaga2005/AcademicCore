"""Explicit two-sided diagonal equilibration (F8-D2, HIGH_PRECISION only).

Transform
---------

For ``A x = b`` with ``A`` an n x n ``DecimalComplex`` matrix, build
positive real diagonal matrices ``D_L`` and ``D_R`` (stored as plain
``Decimal`` scale vectors ``row_scale`` / ``col_scale``):

* ``row_scale[i] = 1 / max_j |A[i][j]|`` (``1`` when row ``i`` is exactly
  zero — a zero row carries no scale information and is left for the
  structural rank analysis);
* with ``A1 = D_L A``, ``col_scale[j] = 1 / max_i |A1[i][j]|``
  (``1`` for exactly-zero columns);
* ``A' = D_L A D_R``, ``b' = D_L b``; solve ``A' x' = b'``;
* recover ``x = D_R x'``.

All factors are ``Decimal`` values computed under the explicit working
context. They are approximations (like everything on the decimal side),
but that is harmless: scaling is a *numerical tool*, and any rounding
it introduces is accounted for in the backward error of the final
solution, which is evaluated on the ORIGINAL system.

Why the solution is preserved
-----------------------------

``x = D_R x'`` recovers the solution by substitution:
``A (D_R x') = D_L^{-1} (D_L A D_R) x' = D_L^{-1} b' = b``.
No physics is involved; this is pure algebra, valid for any system.

Why the rank is preserved
-------------------------

``D_L`` and ``D_R`` are diagonal with strictly positive (hence nonzero)
entries, therefore invertible. Left/right multiplication by invertible
matrices preserves rank: ``rank(A') = rank(A)`` and
``rank([A' | b']) = rank([A | b])`` as mathematical facts. (Numerically,
pivot *decisions* change — that is the purpose of scaling.)

Why units do not matter
-----------------------

Changing the unit of equation ``i`` multiplies row ``i`` by a factor
``k_i``; changing the unit of unknown ``j`` divides column ``j`` by
``u_j``. Both are absorbed into ``D_L``/``D_R`` up to the working
rounding, so the recovered ``x`` is invariant: the solver never sees
physical units, only the dimensionless equilibrated system whose
entries are O(1) unless the original data was exactly zero.

Exact mode never scales: exact arithmetic needs no equilibration, and
routing ``Decimal`` scale factors into the exact path would contaminate
it. ``equilibrate`` therefore accepts decimal matrices only.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.trig import make_context


def _row_scales(A: tuple[tuple[DecimalComplex, ...], ...]) -> tuple[Decimal, ...]:
    ctx = make_context()
    scales = []
    for row in A:
        m = Decimal(0)
        for e in row:
            mod = e.modulus()
            if mod > m:
                m = mod
        scales.append(ctx.divide(Decimal(1), m) if m != 0 else Decimal(1))
    return tuple(scales)


def _col_scales(A: tuple[tuple[DecimalComplex, ...], ...]) -> tuple[Decimal, ...]:
    ctx = make_context()
    n = len(A)
    scales = []
    for j in range(n):
        m = Decimal(0)
        for i in range(n):
            mod = A[i][j].modulus()
            if mod > m:
                m = mod
        scales.append(ctx.divide(Decimal(1), m) if m != 0 else Decimal(1))
    return tuple(scales)


def equilibrate(
    A: tuple[tuple[DecimalComplex, ...], ...],
    b: tuple[DecimalComplex, ...],
) -> tuple[tuple, tuple, tuple[Decimal, ...], tuple[Decimal, ...]]:
    """Return ``(A2, b2, row_scale, col_scale)`` with ``A2 = D_L A D_R``.

    For exact-zero rows/columns the corresponding scale factor is ``1``
    (documented above); such rows/columns are structural facts for the
    rank analysis, not scaling failures.
    """
    ctx = make_context()
    n = len(A)
    row_scale = _row_scales(A)
    a1 = tuple(
        tuple(
            DecimalComplex(ctx.multiply(row_scale[i], row[j].re),
                           ctx.multiply(row_scale[i], row[j].im))
            for j in range(n)
        )
        for i, row in enumerate(A)
    )
    col_scale = _col_scales(a1)
    a2 = tuple(
        tuple(
            DecimalComplex(ctx.multiply(a1[i][j].re, col_scale[j]),
                           ctx.multiply(a1[i][j].im, col_scale[j]))
            for j in range(n)
        )
        for i in range(n)
    )
    b2 = tuple(
        DecimalComplex(ctx.multiply(row_scale[i], b[i].re),
                       ctx.multiply(row_scale[i], b[i].im))
        for i in range(n)
    )
    return a2, b2, row_scale, col_scale


def unscale(
    x2: tuple[DecimalComplex, ...],
    col_scale: tuple[Decimal, ...],
) -> tuple[DecimalComplex, ...]:
    """Recover ``x = D_R x'`` from the scaled solution."""
    ctx = make_context()
    return tuple(
        DecimalComplex(ctx.multiply(x2[j].re, col_scale[j]),
                       ctx.multiply(x2[j].im, col_scale[j]))
        for j in range(len(x2))
    )
