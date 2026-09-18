"""F8-D1 Complex Numeric Foundation: exactness, invariants, adversarial.

Covers RationalComplex (exact Gaussian rationals), DecimalComplex
(50-digit working-precision complex), the one-way promotion rule, zero
and division semantics, algebraic invariants over seeded random sets,
high-precision checks with explicit tolerances, determinism,
immutability, serialization, and package security/architecture.

Conventions: RationalComplex assertions are exact (no tolerances,
no floats). DecimalComplex assertions always carry an explicit
absolute/relative tolerance stated at the assertion site.
"""
import ast
import json
import pathlib
import random
from decimal import Decimal, getcontext
from fractions import Fraction

import pytest
from dataclasses import FrozenInstanceError

from academic_core.domain.engineering.math import (
    WORKING_PRECISION,
    DecimalComplex,
    RationalComplex,
    complex_from_polar,
    decimal_pi_value,
    make_context,
)
from academic_core.domain.engineering.math import trig as trig_mod

SEED = 20260913


def _rationals(rng: random.Random, n: int) -> list[Fraction]:
    pool = [
        Fraction(0), Fraction(1), Fraction(-1), Fraction(1, 2),
        Fraction(-3, 4), Fraction(7, 3), Fraction(22, 7),
        Fraction(10) ** 12, Fraction(-10) ** 12,
        Fraction(1, 10**9), Fraction(-1, 10**9),
        Fraction(123456789, 987654321),
    ]
    out = list(pool)
    while len(out) < n:
        num = rng.randint(-10**6, 10**6)
        den = rng.randint(1, 10**6)
        out.append(Fraction(num, den))
    return out[:n]


def _rz_set(n: int = 300) -> list[RationalComplex]:
    rng = random.Random(SEED)
    vals = _rationals(rng, n)
    return [RationalComplex(a, b) for a, b in zip(vals[::2], vals[1::2])]


def _dz_set(n: int = 60) -> list[DecimalComplex]:
    rng = random.Random(SEED + 1)
    out = []
    for _ in range(n):
        re = Decimal(rng.randint(-10**6, 10**6)) / Decimal(rng.randint(1, 10**6))
        im = Decimal(rng.randint(-10**6, 10**6)) / Decimal(rng.randint(1, 10**6))
        out.append(DecimalComplex(re, im))
    return out


# -- 1. canonical values ---------------------------------------------------------

def test_canonical_values():
    assert RationalComplex.zero() == RationalComplex(Fraction(0), Fraction(0))
    assert RationalComplex.one() == RationalComplex(Fraction(1), Fraction(0))
    assert RationalComplex(Fraction(-1), Fraction(0)) == RationalComplex(-1, 0)
    assert RationalComplex.j() == RationalComplex(Fraction(0), Fraction(1))
    assert -RationalComplex.j() == RationalComplex(Fraction(0), Fraction(-1))
    assert RationalComplex(Fraction(1), Fraction(1)) == RationalComplex(1, 1)
    assert RationalComplex(Fraction(1, 2), Fraction(3, 4)) == RationalComplex(
        Fraction(1, 2), Fraction(3, 4))
    assert DecimalComplex.zero().is_zero_exact()
    assert DecimalComplex.one() == DecimalComplex(Decimal(1), Decimal(0))
    assert DecimalComplex.j() == DecimalComplex(Decimal(0), Decimal(1))


def test_int_constructor_coercion():
    z = RationalComplex(2, -3)
    assert z.re == Fraction(2) and z.im == Fraction(-3)
    d = DecimalComplex(2, -3)
    assert d.re == Decimal(2) and d.im == Decimal(-3)


# -- 2. exactness suite (hand-derived, no tolerances) ------------------------------

def test_exact_addition():
    z = RationalComplex(Fraction(1, 2), Fraction(1, 3)) + RationalComplex(
        Fraction(2, 3), Fraction(-1, 3))
    assert z == RationalComplex(Fraction(7, 6), Fraction(0))


def test_exact_multiplication_conjugate_pair():
    z = RationalComplex(Fraction(1), Fraction(1)) * RationalComplex(
        Fraction(1), Fraction(-1))
    assert z == RationalComplex(Fraction(2), Fraction(0))


def test_exact_division():
    z = RationalComplex(Fraction(1, 2), Fraction(1, 4)) / RationalComplex(
        Fraction(3, 2), Fraction(-1, 2))
    assert z == RationalComplex(Fraction(1, 4), Fraction(1, 4))


def test_exact_subtraction_and_negation():
    z = RationalComplex(Fraction(3, 7), Fraction(-2, 5))
    assert z - z == RationalComplex.zero()
    assert -(-z) == z
    assert z + RationalComplex.zero() == z


def test_exact_squared_modulus_stays_rational():
    z = RationalComplex(Fraction(1, 3), Fraction(1, 4))
    sq = z.squared_modulus()
    assert isinstance(sq, Fraction)
    assert sq == Fraction(1, 9) + Fraction(1, 16) == Fraction(25, 144)
    # z * conj(z) == |z|^2 verified exactly through Fraction
    prod = z * z.conjugate()
    assert prod == RationalComplex(sq, Fraction(0))


def test_exact_modulus_345():
    m = RationalComplex(Fraction(3), Fraction(4)).modulus()
    assert isinstance(m, Decimal)  # explicitly approximate, never Fraction
    assert m == Decimal(5)


# -- 3. algebraic invariants over seeded sets -----------------------------------------

def test_identity_laws_rational():
    for z in _rz_set():
        assert z + RationalComplex.zero() == z
        assert z * RationalComplex.one() == z
        assert z * RationalComplex.zero() == RationalComplex.zero()
        assert z - z == RationalComplex.zero()
        assert z / RationalComplex.one() == z


def test_conjugation_laws_rational():
    for z in _rz_set():
        assert z.conjugate().conjugate() == z
    zs = _rz_set()
    for z, w in zip(zs[::2], zs[1::2]):
        assert (z + w).conjugate() == z.conjugate() + w.conjugate()
        assert (z * w).conjugate() == z.conjugate() * w.conjugate()


def test_modulus_identity_rational():
    for z in _rz_set():
        prod = z * z.conjugate()
        assert prod.im == Fraction(0)
        assert prod.re == z.squared_modulus()


def test_distributivity_rational():
    zs = _rz_set(150)
    for z, w, x in zip(zs[::3], zs[1::3], zs[2::3]):
        assert z * (w + x) == z * w + z * x


def test_associativity_rational():
    zs = _rz_set(150)
    for z, w, x in zip(zs[::3], zs[1::3], zs[2::3]):
        assert (z + w) + x == z + (w + x)
        assert (z * w) * x == z * (w * x)


def test_commutativity_rational():
    zs = _rz_set()
    for z, w in zip(zs[::2], zs[1::2]):
        assert z + w == w + z
        assert z * w == w * z


def _close(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    # Explicit-context subtraction: even this comparison helper must not
    # depend on the ambient global precision.
    return abs(make_context().subtract(a, b)) <= tol


def test_identity_laws_decimal_explicit_tolerance():
    tol = Decimal(1).scaleb(-40)  # absolute tolerance, stated here
    for z in _dz_set():
        assert (z + DecimalComplex.zero() - z).modulus() <= tol
        assert (z * DecimalComplex.one() - z).modulus() <= tol
        assert (z * DecimalComplex.zero()).is_zero_exact()
        assert (z - z).is_zero_exact()
        assert (z / DecimalComplex.one() - z).modulus() <= tol


def test_conjugation_laws_decimal_explicit_tolerance():
    tol = Decimal(1).scaleb(-40)
    for z in _dz_set():
        assert (z.conjugate().conjugate() - z).modulus() <= tol
    zs = _dz_set()
    for z, w in zip(zs[::2], zs[1::2]):
        assert ((z + w).conjugate() - (z.conjugate() + w.conjugate())).modulus() <= tol
        assert ((z * w).conjugate() - (z.conjugate() * w.conjugate())).modulus() <= tol


def test_modulus_identity_decimal_explicit_tolerance():
    tol = Decimal(1).scaleb(-40)
    rel = Decimal("1e-40")  # relative tolerance, stated here
    for z in _dz_set():
        prod = z * z.conjugate()
        assert _close(prod.im, Decimal(0), tol)
        sq = z.squared_modulus()
        scale = max(abs(sq), Decimal(1))
        assert abs(prod.re - sq) <= rel * scale


def test_distributivity_decimal_explicit_tolerance():
    tol = Decimal(1).scaleb(-38)
    zs = _dz_set(45)
    for z, w, x in zip(zs[::3], zs[1::3], zs[2::3]):
        assert (z * (w + x) - (z * w + z * x)).modulus() <= tol


# -- 4. high-precision suite (tolerances explicit, never exact claims) -------------------

def test_sqrt_reference_values():
    tol = Decimal(1).scaleb(-40)
    assert _close(DecimalComplex(Decimal(2), Decimal(0)).sqrt().re,
                  Decimal("1.41421356237309504880168872420969807856967187537695"), tol)
    assert _close(DecimalComplex(Decimal(3), Decimal(0)).sqrt().re,
                  Decimal("1.73205080756887729352744634150587236694280525381038"), tol)
    assert DecimalComplex.zero().sqrt().is_zero_exact()
    assert (DecimalComplex.one().sqrt() - DecimalComplex.one()).modulus() <= tol
    four = DecimalComplex(Decimal(4), Decimal(0)).sqrt()
    assert (four - DecimalComplex(Decimal(2), Decimal(0))).modulus() <= tol
    # sqrt(-1) = +j (principal branch)
    assert DecimalComplex(Decimal(-1), Decimal(0)).sqrt() == DecimalComplex.j()


def test_pi_approximation():
    pi = decimal_pi_value()
    assert isinstance(pi, Decimal)
    assert pi == Decimal("3.14159265358979323846264338327950288419716939937510")


def test_trig_reference_values():
    atol = Decimal(1).scaleb(-40)
    pi = decimal_pi_value()
    ctx = make_context()
    # NOTE: quarter/pi-fractions are built under the explicit working
    # context: `pi / Decimal(4)` with plain `/` would round the *input*
    # to the ambient 28-digit global context and the test would measure
    # input rounding, not library accuracy.
    quarter = ctx.divide(pi, Decimal(4))
    third = ctx.divide(pi, Decimal(3))
    assert _close(trig_mod.decimal_sin(quarter), Decimal(
        "0.70710678118654752440084436210484903928483593768846"), atol)
    assert _close(trig_mod.decimal_cos(third), Decimal("0.5"), atol)
    assert _close(trig_mod.decimal_sin(Decimal(0)), Decimal(0), atol)
    assert _close(trig_mod.decimal_cos(Decimal(0)), Decimal(1), atol)


def test_phase_is_approximate():
    atol = Decimal(1).scaleb(-40)
    pi = decimal_pi_value()
    ctx = make_context()
    half = ctx.divide(pi, Decimal(2))
    assert _close(DecimalComplex.j().phase(), half, atol)
    assert _close(DecimalComplex.one().phase(), Decimal(0), atol)
    assert _close(DecimalComplex(Decimal(-1), Decimal(0)).phase(), pi, atol)
    assert _close((-DecimalComplex.j()).phase(), ctx.minus(half), atol)
    assert isinstance(DecimalComplex.j().phase(), Decimal)


def test_polar_construction():
    atol = Decimal(1).scaleb(-38)
    pi = decimal_pi_value()
    ctx = make_context()
    half = ctx.divide(pi, Decimal(2))
    z = complex_from_polar(Decimal(1), half)
    assert (z - DecimalComplex.j()).modulus() <= atol
    z2 = complex_from_polar(Fraction(3, 2), Decimal(0))
    assert _close(z2.re, Decimal("1.5"), atol) and _close(z2.im, Decimal(0), atol)
    z3 = complex_from_polar(2, pi)
    assert _close(z3.re, Decimal(-2), Decimal(1).scaleb(-36))
    with pytest.raises(TypeError):
        complex_from_polar(1.0, Decimal(0))  # float magnitude rejected
    with pytest.raises(TypeError):
        complex_from_polar(Decimal(1), 1.5707)  # non-Decimal angle rejected


# -- 5. promotion rules ------------------------------------------------------------------

def test_promotion_is_one_way_and_typed():
    r = RationalComplex(Fraction(1, 2), Fraction(1, 4))
    d = DecimalComplex(Decimal("0.1"), Decimal("0.2"))
    for expr in (r + d, r - d, r * d, r / d, d + r, d - r, d * r, d / r):
        assert isinstance(expr, DecimalComplex), type(expr)
    # exact + approximate is approximate: never silently exact
    assert not isinstance(r + d, RationalComplex)
    # explicit promotion entry point
    assert r.to_decimal() == DecimalComplex.from_rational(r)


def test_no_decimal_to_rational_api_exists():
    for name in ("to_rational", "to_exact", "as_rational", "as_fraction",
                 "to_fraction", "rationalize", "exact"):
        assert not hasattr(DecimalComplex, name), name
    # No Fraction(...) *construction call* may exist on the approximate
    # side: isinstance checks and docstring prose name the type without
    # calling it, so this is an AST check, not a substring check.
    tree = ast.parse((MATH_DIR / "decimal_complex.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else "")
            assert called != "Fraction", "Fraction(...) construction on approximate side"


def test_equality_never_mixes_representations():
    r = RationalComplex(Fraction(1), Fraction(0))
    d = DecimalComplex(Decimal(1), Decimal(0))
    assert (r == d) is False
    assert (d == r) is False
    assert (r != d) is True
    with pytest.raises(TypeError):
        RationalComplex(Fraction(1), Fraction(0)) + 1.5
    with pytest.raises(TypeError):
        DecimalComplex(Decimal(1), Decimal(0)) + 1.5
    with pytest.raises(TypeError):
        RationalComplex(Fraction(1), Fraction(0)) + complex(1, 0)


def test_mixed_scalar_operands():
    z = RationalComplex(Fraction(1, 2), Fraction(1, 2))
    assert z + 1 == RationalComplex(Fraction(3, 2), Fraction(1, 2))
    assert 1 + z == RationalComplex(Fraction(3, 2), Fraction(1, 2))
    assert z + Fraction(1, 2) == RationalComplex(Fraction(1), Fraction(1, 2))
    assert 2 * z == RationalComplex(Fraction(1), Fraction(1))
    assert z * Fraction(2) == RationalComplex(Fraction(1), Fraction(1))
    assert z - 1 == RationalComplex(Fraction(-1, 2), Fraction(1, 2))
    assert 1 - z == RationalComplex(Fraction(1, 2), Fraction(-1, 2))
    assert z / 2 == RationalComplex(Fraction(1, 4), Fraction(1, 4))
    d = DecimalComplex(Decimal("1.5"), Decimal("0.5"))
    assert d + 1 == DecimalComplex(Decimal("2.5"), Decimal("0.5"))
    assert 1 + d == DecimalComplex(Decimal("2.5"), Decimal("0.5"))
    assert d + Decimal("0.5") == DecimalComplex(Decimal("2.0"), Decimal("0.5"))
    assert d + Fraction(1, 2) == DecimalComplex(Decimal("2.0"), Decimal("0.5"))
    assert 2 * d == DecimalComplex(Decimal("3.0"), Decimal("1.0"))
    assert d / 2 == DecimalComplex(Decimal("0.75"), Decimal("0.25"))


def test_incompatible_operands_rejected():
    z = RationalComplex(Fraction(1), Fraction(1))
    d = DecimalComplex(Decimal(1), Decimal(1))
    for bad in ("1", None, [1], True):
        with pytest.raises(TypeError):
            z + bad
        with pytest.raises(TypeError):
            d + bad


def test_constructor_rejects_inexact_inputs():
    with pytest.raises(TypeError):
        RationalComplex(0.5, Fraction(0))
    with pytest.raises(TypeError):
        RationalComplex(Fraction(0), Decimal("0.5"))
    with pytest.raises(TypeError):
        RationalComplex("1/2", Fraction(0))
    with pytest.raises(TypeError):
        DecimalComplex(0.5, Decimal(0))
    with pytest.raises(TypeError):
        DecimalComplex(complex(1, 0), Decimal(0))
    with pytest.raises(TypeError):
        DecimalComplex("1.5", Decimal(0))
    with pytest.raises(TypeError):
        DecimalComplex(Fraction(1, 2), Decimal(0))


# -- 6. zero and division semantics ---------------------------------------------------------

def test_zero_exact_rational():
    assert RationalComplex.zero().is_zero_exact()
    assert RationalComplex(Fraction(0), Fraction(1)).is_zero_exact() is False
    assert RationalComplex(Fraction(1, 10**30), Fraction(0)).is_zero_exact() is False


def test_zero_explicit_tolerance_decimal():
    tiny = DecimalComplex(Decimal("1e-30"), Decimal(0))
    assert tiny != DecimalComplex.zero()  # representation-exact inequality
    assert tiny.is_zero(Decimal("1e-20")) is True
    assert tiny.is_zero(Decimal("1e-40")) is False
    assert DecimalComplex.zero().is_zero(Decimal(0)) is True
    with pytest.raises(TypeError):
        tiny.is_zero(1e-20)  # tolerance must be explicit Decimal, never float
    with pytest.raises(ValueError):
        tiny.is_zero(Decimal("-1"))


def test_division_by_exact_zero_rational():
    z = RationalComplex(Fraction(1), Fraction(2))
    with pytest.raises(ZeroDivisionError):
        z / RationalComplex.zero()
    with pytest.raises(ZeroDivisionError):
        RationalComplex.zero() / RationalComplex.zero()
    # no epsilon policy: a nonzero denominator, however small, divides normally
    tiny = RationalComplex(Fraction(1, 10**30), Fraction(0))
    assert (z / tiny).re == Fraction(10**30)


def test_division_decimal_exact_zero_vs_small():
    z = DecimalComplex(Decimal(1), Decimal(2))
    with pytest.raises(ZeroDivisionError):
        z / DecimalComplex.zero()
    small = DecimalComplex(Decimal("1e-40"), Decimal(0))
    q = z / small  # near-zero is NOT collapsed to singular here
    assert q.modulus() > Decimal("1e40")


# -- 7. immutability ----------------------------------------------------------------------------

def test_frozen_components():
    z = RationalComplex(Fraction(1), Fraction(2))
    with pytest.raises(FrozenInstanceError):
        z.re = Fraction(9)
    with pytest.raises(FrozenInstanceError):
        z.im = Fraction(9)
    d = DecimalComplex(Decimal(1), Decimal(2))
    with pytest.raises(FrozenInstanceError):
        d.re = Decimal(9)
    with pytest.raises(FrozenInstanceError):
        d.im = Decimal(9)


def test_operations_allocate_new_objects():
    z = RationalComplex(Fraction(1), Fraction(2))
    w = RationalComplex(Fraction(3), Fraction(4))
    for out in (z + w, z - w, z * w, z / w, -z, z.conjugate()):
        assert out is not z and out is not w
    assert z == RationalComplex(Fraction(1), Fraction(2))  # operands unmutated
    d = DecimalComplex(Decimal(1), Decimal(2))
    e = DecimalComplex(Decimal(3), Decimal(4))
    for out in (d + e, d - e, d * e, d / e, -d, d.conjugate(), d.sqrt()):
        assert out is not d and out is not e


# -- 8. determinism --------------------------------------------------------------------------------

def test_determinism_thousand_repetitions():
    a = RationalComplex(Fraction(123456789, 987654321), Fraction(-7, 13))
    b = RationalComplex(Fraction(22, 7), Fraction(5, 9))
    first = (a * b + a - b) / a
    first_dict = json.dumps(first.to_dict(), sort_keys=True)
    first_hash = hash(first)
    d = DecimalComplex(Decimal("1.23456789"), Decimal("-0.5"))
    e = DecimalComplex(Decimal("22") / Decimal(7), Decimal("0.25"))
    d_first = (d * e + d - e) / e
    d_first_dict = json.dumps(d_first.to_dict(), sort_keys=True)
    d_first_hash = hash(d_first)
    for _ in range(1000):
        rep = (a * b + a - b) / a
        assert type(rep) is type(first)
        assert rep == first
        assert hash(rep) == first_hash
        assert json.dumps(rep.to_dict(), sort_keys=True) == first_dict
        d_rep = (d * e + d - e) / e
        assert type(d_rep) is type(d_first)
        assert d_rep == d_first
        assert hash(d_rep) == d_first_hash
        assert json.dumps(d_rep.to_dict(), sort_keys=True) == d_first_dict


def _sig_digits(x: Decimal) -> int:
    # Context-free digit count: as_tuple() never rounds via any context
    # (unlike abs()/str-arithmetic, which would obey the ambient context).
    return len(x.as_tuple().digits)


def test_make_context_returns_fresh_object_each_call():
    """Regression test: make_context() must never share a singleton.

    A prior version returned the literal module-level ``_BASE_CONTEXT``
    by reference whenever ``extra == 0``, so two callers of
    ``make_context()`` held the *same* Context object and mutating one
    caller's ``.traps``/``.flags`` silently contaminated every other
    caller's context. Not exploitable today (nothing in the codebase
    mutates ``.traps``/``.flags``), but latent and cheap to remove:
    ``decimal.Context`` construction is trivial, so every call now
    builds its own instance, for ``extra == 0`` and ``extra > 0`` alike.
    """
    a = make_context()
    b = make_context()
    assert a is not b
    # decimal.Context has no value-based __eq__ (falls back to identity),
    # so compare the attributes that matter instead.
    assert (a.prec, a.rounding) == (b.prec, b.rounding)

    a2 = make_context(15)
    b2 = make_context(15)
    assert a2 is not b2
    assert (a2.prec, a2.rounding) == (b2.prec, b2.rounding)

    # Mutating one instance's context state must never leak to another
    # independently-obtained instance.
    from decimal import DivisionByZero, Overflow

    c1 = make_context()
    c2 = make_context()
    default_div_trap = c2.traps[DivisionByZero]
    c1.traps[DivisionByZero] = not default_div_trap
    assert c2.traps[DivisionByZero] == default_div_trap
    c1.flags[Overflow] = True
    assert c2.flags[Overflow] is False


def test_global_decimal_context_untouched():
    before_prec = getcontext().prec
    old = getcontext().prec
    getcontext().prec = 5
    try:
        z = RationalComplex(Fraction(1, 3), Fraction(1, 7))
        assert _sig_digits(z.modulus()) >= 20
        # Library-side Decimal inputs must also come from the explicit
        # context path: from_rational rounds under working precision even
        # while the ambient context is degraded to 5 digits.
        d = DecimalComplex.from_rational(
            RationalComplex(Fraction(1, 3), Fraction(1, 7)))
        assert _sig_digits(d.re) >= 20
        neg = -d
        # explicit-context negation keeps full digits even under prec=5;
        # (x + (-x) is exactly 0 under any precision, so this also proves
        # the negation is the true arithmetic opposite, not a coincidence)
        assert make_context().add(neg.re, d.re) == 0
        assert make_context().add(neg.im, d.im) == 0
        assert _sig_digits(neg.re) >= 20
    finally:
        getcontext().prec = old
    assert getcontext().prec == before_prec


def test_modulus_im_zero_fast_path_ignores_ambient_context():
    """Regression test for the modulus() im==0 fast-path precision bug.

    modulus() used to do ``return abs(re)`` on that fast path. Python's
    bare ``abs()`` on a Decimal implicitly rounds through
    ``decimal.getcontext()`` (the ambient/global context, default 28
    significant digits) rather than the module's explicit 50-digit
    working context, silently truncating precision whenever im is
    exactly zero. The fix uses ``re.copy_abs()``, which flips the sign
    bit only and never consults any context. This test degrades the
    ambient context to the default 28 digits, feeds in a >28-digit
    Decimal with im=0, and asserts modulus() still returns the full
    value untouched.
    """
    old = getcontext().prec
    try:
        getcontext().prec = 28  # the default/global context, explicitly
        big_re = Decimal(
            "1.2345678901234567890123456789012345678901234567890"
        )  # 50 significant digits
        assert len(big_re.as_tuple().digits) == 50
        z = DecimalComplex(big_re, Decimal(0))

        result = z.modulus()

        # Full 50-digit precision must survive: no rounding to 28 digits.
        assert result == big_re.copy_abs()
        assert len(result.as_tuple().digits) > 28

        # Sign is normalized (abs), value magnitude preserved exactly.
        # (Built from a literal, not unary ``-big_re``: that bare builtin
        # would itself round through the same degraded ambient context.)
        neg_big_re = Decimal(
            "-1.2345678901234567890123456789012345678901234567890"
        )
        neg_z = DecimalComplex(neg_big_re, Decimal(0))
        neg_result = neg_z.modulus()
        assert neg_result == big_re.copy_abs()
        assert len(neg_result.as_tuple().digits) > 28
    finally:
        getcontext().prec = old


def test_modulus_general_path_unaffected_by_fast_path_fix():
    """Sanity check: the im != 0 branch still computes sqrt(re^2+im^2).

    Guards against a regression in the non-fast-path branch while
    fixing the im==0 fast path above.
    """
    z = DecimalComplex(Decimal(3), Decimal(4))
    result = z.modulus()
    tol = Decimal("1e-45")
    assert abs(result - Decimal(5)) <= tol

    z2 = DecimalComplex(Decimal("1.5"), Decimal("-2.5"))
    expected = make_context().sqrt(
        make_context().add(
            make_context().multiply(z2.re, z2.re),
            make_context().multiply(z2.im, z2.im),
        )
    )
    assert z2.modulus() == expected


# -- 9. serialization ---------------------------------------------------------------------------------

def test_rational_serialization_roundtrip():
    for z in _rz_set(50):
        d = z.to_dict()
        assert d["type"] == "rational_complex"
        assert RationalComplex.from_dict(d) == z
        assert json.dumps(d, sort_keys=True) == json.dumps(
            RationalComplex.from_dict(json.loads(json.dumps(d))).to_dict(), sort_keys=True)
    assert RationalComplex.from_dict(
        {"type": "rational_complex", "re": "1/2", "im": "3/4"}
    ) == RationalComplex(Fraction(1, 2), Fraction(3, 4))
    with pytest.raises(ValueError):
        RationalComplex.from_dict({"type": "decimal_complex", "re": "1", "im": "0"})
    with pytest.raises(ValueError):
        RationalComplex.from_dict({"type": "rational_complex", "re": "abc", "im": "0"})


def test_decimal_serialization_roundtrip():
    for z in _dz_set(20):
        d = z.to_dict()
        assert d["type"] == "decimal_complex"
        assert d["precision"] == WORKING_PRECISION == 50
        assert DecimalComplex.from_dict(d) == z
    with pytest.raises(ValueError):
        DecimalComplex.from_dict(
            {"type": "decimal_complex", "re": "1", "im": "0", "precision": 28})
    with pytest.raises(ValueError):
        DecimalComplex.from_dict({"type": "rational_complex", "re": "1", "im": "0"})


# -- 10. adversarial ---------------------------------------------------------------------------------------

def test_adversarial_magnitudes_and_signs():
    huge = RationalComplex(Fraction(10) ** 300, Fraction(-10) ** 300)
    assert (huge + huge).re == Fraction(10) ** 300 * 2
    assert (huge * RationalComplex.zero()).is_zero_exact()
    tiny = RationalComplex(Fraction(1, 10**300), Fraction(-1, 10**300))
    assert not tiny.is_zero_exact()
    assert tiny.squared_modulus() == Fraction(2, 10**600)
    assert tiny * tiny == RationalComplex(Fraction(0), Fraction(-2, 10**600))
    neg = RationalComplex(Fraction(-5), Fraction(-7))
    assert (-neg).re == Fraction(5) and (-neg).im == Fraction(7)
    real_only = RationalComplex(Fraction(4), Fraction(0))
    imag_only = RationalComplex(Fraction(0), Fraction(-4))
    assert (real_only * imag_only) == RationalComplex(Fraction(0), Fraction(-16))
    # Decimal extremes
    dh = DecimalComplex(Decimal("1e300"), Decimal("-1e300"))
    assert (dh - dh).is_zero_exact()
    dt = DecimalComplex(Decimal("1e-300"), Decimal("1e-300"))
    assert not dt.is_zero_exact()
    assert dt.is_zero(Decimal("1e-290"))


def test_adversarial_division_edges():
    z = RationalComplex(Fraction(3, 11), Fraction(-5, 13))
    inv = RationalComplex.one() / z
    assert (z * inv - RationalComplex.one()).squared_modulus() == Fraction(0)
    pure_imag = RationalComplex(Fraction(0), Fraction(2))
    assert RationalComplex.one() / pure_imag == RationalComplex(Fraction(0), Fraction(-1, 2))
    pure_real = RationalComplex(Fraction(-4), Fraction(0))
    assert RationalComplex.one() / pure_real == RationalComplex(Fraction(-1, 4), Fraction(0))
    with pytest.raises(ZeroDivisionError):
        pure_imag / RationalComplex.zero()


def test_hash_consistency():
    assert hash(RationalComplex(Fraction(1), Fraction(0))) == hash(1)
    assert hash(RationalComplex(Fraction(1, 2), Fraction(0))) == hash(Fraction(1, 2))
    assert hash(DecimalComplex(Decimal(1), Decimal(0))) == hash(1)
    assert hash(DecimalComplex(Decimal("1.5"), Decimal(0))) == hash(Decimal("1.5"))
    assert RationalComplex(Fraction(1), Fraction(0)) == 1
    assert DecimalComplex(Decimal(1), Decimal(0)) == 1
    s = {RationalComplex(Fraction(1), Fraction(0)), RationalComplex(Fraction(1), Fraction(0))}
    assert len(s) == 1


# -- 11. security & architecture ------------------------------------------------------------------------------

MATH_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "math"

FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
FORBIDDEN_IMPORT_ROOTS = {
    "os", "sys", "pathlib", "sqlite3", "urllib", "socket", "http",
    "ftplib", "subprocess", "pickle", "marshal", "ctypes",
    "PySide6", "numpy", "scipy", "math", "cmath",
}
FORBIDDEN_QUALIFIED = {
    "academic_core.domain.engineering.circuit",
    "academic_core.domain.engineering.units",
    "academic_core.infrastructure",
    "academic_core.application",
    "academic_core.app",
}


def _module_sources():
    return sorted(MATH_DIR.glob("*.py"))


def test_package_files_present():
    names = {p.name for p in _module_sources()}
    assert {"__init__.py", "rational.py", "decimal_complex.py", "trig.py"} <= names


def test_no_dangerous_calls():
    for path in _module_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_CALLS, (path.name, node.func.id)


def test_no_forbidden_dependencies():
    # Real imports only (parsed with ast): docstring prose may discuss a
    # backend by name, which documents the boundary instead of depending
    # on it. The math package must stay circuit-agnostic: no Circuit,
    # Quantity, ngspice, Qt, SQLite, numpy, or float-based cmath/math.
    for path in _module_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    root = a.name.split(".")[0]
                    assert root not in FORBIDDEN_IMPORT_ROOTS, (path.name, a.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in FORBIDDEN_IMPORT_ROOTS, (path.name, node.module)
                for qual in FORBIDDEN_QUALIFIED:
                    assert node.module != qual and not node.module.startswith(qual + "."), (
                        path.name, node.module)


def test_no_float_or_cmath_imports():
    import academic_core.domain.engineering.math.decimal_complex as dm
    import academic_core.domain.engineering.math.rational as rm
    import academic_core.domain.engineering.math.trig as tm
    import inspect
    for mod in (dm, rm, tm):
        tree = ast.parse(inspect.getsource(mod))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported <= {"__future__", "dataclasses", "decimal", "fractions", "typing",
                            "academic_core"}, imported
    # RationalComplex module must never name the float type in executable code
    tree = ast.parse((MATH_DIR / "rational.py").read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "float" not in names and "complex" not in names


def test_domain_purity_preserved():
    import academic_core.domain.engineering.math.decimal_complex as dm
    import academic_core.domain.engineering.math.rational as rm
    import academic_core.domain.engineering.math.trig as tm
    import inspect
    for mod in (dm, rm, tm):
        assert "PySide6" not in inspect.getsource(mod)


def test_working_precision_declared():
    assert WORKING_PRECISION == 50


# -- 12. atan2 family (half-angle reduction; regression cover for the ------
# --     |t| ~= 1 Taylor-truncation defect) -----------------------------------

ATAN2_TOL = Decimal("1E-45")  # compatible with 50-digit working precision


def _pi_over(n: int) -> Decimal:
    ctx = make_context()
    return ctx.divide(decimal_pi_value(), Decimal(n))


def test_atan2_cardinal_angles():
    pi = decimal_pi_value()
    half = _pi_over(2)
    assert trig_mod.decimal_atan2(Decimal(0), Decimal(1)) == Decimal(0)
    assert _close(trig_mod.decimal_atan2(Decimal(1), Decimal(0)), half, ATAN2_TOL)
    assert _close(trig_mod.decimal_atan2(Decimal(0), Decimal(-1)), pi, ATAN2_TOL)
    assert _close(trig_mod.decimal_atan2(Decimal(-1), Decimal(0)),
                  make_context().minus(half), ATAN2_TOL)
    assert trig_mod.decimal_atan2(Decimal(0), Decimal(0)) == Decimal(0)


def test_atan2_45_degree_family():
    # Independent references: PI50-derived quarters, not solver output.
    q = _pi_over(4)
    tq = make_context()
    three_q = tq.multiply(Decimal(3), q)
    assert _close(trig_mod.decimal_atan2(Decimal(1), Decimal(1)), q, ATAN2_TOL)
    assert _close(trig_mod.decimal_atan2(Decimal(1), Decimal(-1)), three_q, ATAN2_TOL)
    assert _close(trig_mod.decimal_atan2(Decimal(-1), Decimal(1)),
                  tq.minus(q), ATAN2_TOL)
    assert _close(trig_mod.decimal_atan2(Decimal(-1), Decimal(-1)),
                  tq.minus(three_q), ATAN2_TOL)


def test_atan2_near_unity_both_sides():
    # The formerly broken neighborhood, from below and above, in all
    # four quadrants. Cross-validated against tan() (independent Taylor
    # path): sin(a)/cos(a) must recover t.
    ctx = make_context()
    near = [Decimal("0.999999999999"), Decimal("0.99"), Decimal("0.9"),
            Decimal("1.000000000001"), Decimal("1.01"), Decimal("1.1")]
    for t in near:
        for sy, sx in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            yy = ctx.multiply(Decimal(sy), t)
            x = Decimal(sx)
            a = trig_mod.decimal_atan2(yy, x)
            s = trig_mod.decimal_sin(a, ctx)
            c = trig_mod.decimal_cos(a, ctx)
            back = ctx.divide(s, c)
            assert abs(ctx.subtract(back, ctx.divide(yy, x))) <= Decimal("1E-40"), (t, sy, sx)
    # Complementary identity coherence: arctan(t) + arctan(1/t) = pi/2.
    pi = decimal_pi_value()
    half = _pi_over(2)
    for t in near:
        inv = ctx.divide(Decimal(1), t)
        s = ctx.add(trig_mod._arctan(t, make_context(15)),
                    trig_mod._arctan(inv, make_context(15)))
        assert abs(ctx.subtract(s, half)) <= Decimal("1E-40"), t


def test_atan2_range_and_signs():
    pi = decimal_pi_value()
    half = _pi_over(2)
    ctx = make_context()
    cases = [
        (Decimal(2), Decimal(3), 1), (Decimal(-2), Decimal(3), -1),
        (Decimal(2), Decimal(-3), 1), (Decimal(-2), Decimal(-3), -1),
        (Decimal("1E-30"), Decimal(1), 1), (Decimal(1), Decimal("1E30"), 1),
        (Decimal("1E30"), Decimal(1), 1), (Decimal("-1E30"), Decimal(1), -1),
    ]
    for y, x, sign in cases:
        a = trig_mod.decimal_atan2(y, x)
        assert (a > 0) if sign > 0 else (a < 0)
        assert a > ctx.minus(pi) and a <= pi
    # Axes carry exact-side conventions through DecimalComplex.phase too.
    assert DecimalComplex(Decimal(1), Decimal(0)).phase() == Decimal(0)
    assert _close(DecimalComplex(Decimal(0), Decimal(-1)).phase(),
                  ctx.minus(half), ATAN2_TOL)
