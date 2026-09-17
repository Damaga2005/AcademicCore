"""Physical unit tests for F8-I Ebers-Moll BJT model (NPN and PNP).

Verifies parameter extraction, NPN/PNP injection and terminal currents,
current conservation, analytical Jacobian vs high-precision central finite
differences, global potential shift invariance, overflow protection,
absence of float, determinism, and AST security.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
import pytest

from academic_core.domain.engineering.circuit import Component
from academic_core.domain.engineering.mna.bjt import (
    BJTParams,
    bjt_companion,
    bjt_conductances,
    bjt_injection_currents,
    bjt_jacobian,
    bjt_terminal_currents,
    extract_bjt_params,
)
from academic_core.domain.engineering.mna.errors import InvalidCircuitError
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import (
    CURRENT,
    DIMENSIONLESS,
    VOLTAGE,
    Quantity,
    parse_unit,
)

_VOLT = parse_unit("V")
_AMP = parse_unit("A")
_DIM = parse_unit("1")


def _make_q(
    polarity: str = "NPN",
    is_val: str = "1E-14",
    bf_val: str = "100",
    br_val: str = "1",
    nf_val: str = "1.0",
    nr_val: str = "1.0",
    vt_val: str = "0.0258649",
    ref: str = "Q1",
    pins: dict | None = None,
    value: Quantity | None = None,
    comp_type: str = "Q",
) -> Component:
    if pins is None:
        pins = {"C": "c", "B": "b", "E": "e"}
    params = {
        "polarity": polarity,
        "Is": Quantity(Decimal(is_val), _AMP),
        "Bf": Quantity(Decimal(bf_val), _DIM),
        "Br": Quantity(Decimal(br_val), _DIM),
        "Nf": Quantity(Decimal(nf_val), _DIM),
        "Nr": Quantity(Decimal(nr_val), _DIM),
        "Vt": Quantity(Decimal(vt_val), _VOLT),
    }
    return Component(
        ref=ref,
        type=comp_type,
        value=value,
        pins=pins,
        parameters=params,
    )


# ----------------------------------------------------------------------
# 1. Parameter validation tests
# ----------------------------------------------------------------------

def test_extract_bjt_params_valid_npn():
    comp = _make_q(polarity="NPN")
    p = extract_bjt_params(comp)
    assert p.polarity == "NPN"
    assert p.Is == Decimal("1E-14")
    assert p.Bf == Decimal("100")
    assert p.Br == Decimal("1")
    assert p.Nf == Decimal("1.0")
    assert p.Nr == Decimal("1.0")
    assert p.Vt == Decimal("0.0258649")
    ctx = make_context()
    assert p.alphaF == ctx.divide(Decimal(100), Decimal(101))
    assert p.alphaR == Decimal("0.5")


def test_extract_bjt_params_valid_pnp():
    comp = _make_q(polarity="PNP")
    p = extract_bjt_params(comp)
    assert p.polarity == "PNP"


def test_extract_bjt_params_rejects_wrong_type():
    comp = _make_q(comp_type="D", ref="D1", pins={"A": "a", "K": "k"})
    with pytest.raises(InvalidCircuitError, match="requires a Q component"):
        extract_bjt_params(comp)


def test_extract_bjt_params_rejects_non_none_value():
    comp = _make_q(value=Quantity(Decimal(10), _VOLT))
    with pytest.raises(InvalidCircuitError, match="takes no value"):
        extract_bjt_params(comp)


def test_extract_bjt_params_rejects_missing_parameter():
    comp = _make_q()
    del comp.parameters["Bf"]
    with pytest.raises(InvalidCircuitError, match="BJT needs exactly parameters"):
        extract_bjt_params(comp)


def test_extract_bjt_params_rejects_invalid_polarity():
    comp = _make_q(polarity="NMOS")
    with pytest.raises(InvalidCircuitError, match="polarity must be 'NPN' or 'PNP'"):
        extract_bjt_params(comp)


def test_extract_bjt_params_rejects_non_quantity():
    comp = _make_q()
    comp.parameters["Is"] = 1e-14
    with pytest.raises(InvalidCircuitError, match="must be a Quantity"):
        extract_bjt_params(comp)


def test_extract_bjt_params_rejects_wrong_dimension():
    comp = _make_q()
    comp.parameters["Is"] = Quantity(Decimal("1E-14"), _VOLT)
    with pytest.raises(InvalidCircuitError, match="wrong dimension"):
        extract_bjt_params(comp)


def test_extract_bjt_params_rejects_non_positive():
    comp = _make_q(is_val="0")
    with pytest.raises(InvalidCircuitError, match="must be > 0"):
        extract_bjt_params(comp)

    comp_neg = _make_q(bf_val="-50")
    with pytest.raises(InvalidCircuitError, match="must be > 0"):
        extract_bjt_params(comp_neg)


def test_extract_bjt_params_rejects_non_finite():
    comp = _make_q(vt_val="Infinity")
    with pytest.raises(InvalidCircuitError, match="non-finite"):
        extract_bjt_params(comp)


# ----------------------------------------------------------------------
# 2. Physics & Operating Regions (NPN)
# ----------------------------------------------------------------------

def test_npn_forward_active():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN", bf_val="100", br_val="1"))
    # Base at 0.7V, Emitter at 0V -> VBE = 0.7V
    # Collector at 5V -> VBC = -4.3V (strongly reverse biased)
    vc, vb, ve = Decimal("5.0"), Decimal("0.7"), Decimal("0.0")
    ic, ib, ie = bjt_terminal_currents(vc, vb, ve, p, ctx)

    assert ic > 0, "Collector current must be positive (entering C)"
    assert ib > 0, "Base current must be positive (entering B)"
    assert ie < 0, "Emitter current must be negative (leaving E)"
    ratio = ctx.divide(ic, ib)
    assert abs(ratio - Decimal("100")) < Decimal("0.01")
    assert abs(ctx.add(ctx.add(ic, ib), ie)) < Decimal("1E-25")


def test_npn_cutoff():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN"))
    # VBE = 0V, VBC = -5V -> both reverse or zero
    vc, vb, ve = Decimal("5.0"), Decimal("0.0"), Decimal("0.0")
    ic, ib, ie = bjt_terminal_currents(vc, vb, ve, p, ctx)

    assert abs(ic) < Decimal("1E-12")
    assert abs(ib) < Decimal("1E-12")
    assert abs(ie) < Decimal("1E-12")
    assert abs(ctx.add(ctx.add(ic, ib), ie)) < Decimal("1E-25")


def test_npn_saturation():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN", bf_val="100", br_val="2"))
    # VBE = 0.75V, VBC = 0.65V -> both junctions forward biased
    vc, vb, ve = Decimal("0.1"), Decimal("0.75"), Decimal("0.0")
    ic, ib, ie = bjt_terminal_currents(vc, vb, ve, p, ctx)

    assert ic > 0
    assert ib > 0
    assert ie < 0
    ratio = ctx.divide(ic, ib)
    assert ratio < Decimal("60")
    assert abs(ctx.add(ctx.add(ic, ib), ie)) < Decimal("1E-25")


def test_npn_reverse_active():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN", bf_val="100", br_val="2"))
    # VBE = -2V (reverse), VBC = 0.65V (forward)
    vc, vb, ve = Decimal("0.0"), Decimal("0.65"), Decimal("2.65")
    ic, ib, ie = bjt_terminal_currents(vc, vb, ve, p, ctx)

    assert ic < 0
    assert ib > 0
    assert ie > 0
    assert abs(ctx.add(ctx.add(ic, ib), ie)) < Decimal("1E-25")


# ----------------------------------------------------------------------
# 3. Physics & Operating Regions (PNP)
# ----------------------------------------------------------------------

def test_pnp_forward_active():
    ctx = make_context()
    p = extract_bjt_params(_make_q("PNP", bf_val="80", br_val="1"))
    # Emitter at 5V, Base at 4.3V -> VEB = 0.7V
    # Collector at 0V -> VCB = -4.3V
    vc, vb, ve = Decimal("0.0"), Decimal("4.3"), Decimal("5.0")
    ic, ib, ie = bjt_terminal_currents(vc, vb, ve, p, ctx)

    assert ie > 0, "PNP emitter current must enter device"
    assert ic < 0, "PNP collector current must leave device"
    assert ib < 0, "PNP base current must leave device"
    ratio = ctx.divide(abs(ic), abs(ib))
    assert abs(ratio - Decimal("80")) < Decimal("0.01")
    assert abs(ctx.add(ctx.add(ic, ib), ie)) < Decimal("1E-25")


def test_pnp_cutoff():
    ctx = make_context()
    p = extract_bjt_params(_make_q("PNP"))
    # VEB <= 0, VCB <= 0
    vc, vb, ve = Decimal("0.0"), Decimal("5.0"), Decimal("5.0")
    ic, ib, ie = bjt_terminal_currents(vc, vb, ve, p, ctx)

    assert abs(ic) < Decimal("1E-12")
    assert abs(ib) < Decimal("1E-12")
    assert abs(ie) < Decimal("1E-12")
    assert abs(ctx.add(ctx.add(ic, ib), ie)) < Decimal("1E-25")


def test_pnp_saturation():
    ctx = make_context()
    p = extract_bjt_params(_make_q("PNP", bf_val="80", br_val="2"))
    # VEB = 0.75V, VCB = 0.65V
    ve = Decimal("5.0")
    vb = Decimal("4.25")  # VEB = 0.75
    vc = Decimal("4.9")   # VCB = 0.65
    ic, ib, ie = bjt_terminal_currents(vc, vb, ve, p, ctx)

    assert ie > 0
    assert ic < 0
    assert ib < 0
    ratio = ctx.divide(abs(ic), abs(ib))
    assert ratio < Decimal("60")
    assert abs(ctx.add(ctx.add(ic, ib), ie)) < Decimal("1E-25")


def test_pnp_reverse_active():
    ctx = make_context()
    p = extract_bjt_params(_make_q("PNP", bf_val="80", br_val="2"))
    # VEB = -2V, VCB = +0.7V
    vb = Decimal("3.0")
    ve = Decimal("1.0")   # VEB = -2V
    vc = Decimal("3.7")   # VCB = +0.7V
    ic, ib, ie = bjt_terminal_currents(vc, vb, ve, p, ctx)

    assert ic > 0
    assert ib < 0
    assert ie < 0
    assert abs(ctx.add(ctx.add(ic, ib), ie)) < Decimal("1E-25")


# ----------------------------------------------------------------------
# 4. Analytical Jacobian vs Numerical Derivatives
# ----------------------------------------------------------------------

@pytest.mark.parametrize("polarity, vc_s, vb_s, ve_s", [
    ("NPN", "5.0", "0.7", "0.0"),    # forward active
    ("NPN", "0.2", "0.75", "0.0"),   # saturation
    ("NPN", "0.0", "0.65", "2.0"),   # reverse active
    ("NPN", "5.0", "0.0", "0.0"),    # cutoff
    ("PNP", "0.0", "4.3", "5.0"),    # forward active
    ("PNP", "4.8", "4.3", "5.0"),    # saturation
    ("PNP", "5.0", "4.3", "0.0"),    # reverse active
    ("PNP", "0.0", "5.0", "5.0"),    # cutoff
])
def test_jacobian_analytical_vs_numerical_central_diff(polarity, vc_s, vb_s, ve_s):
    ctx = make_context()
    p = extract_bjt_params(_make_q(polarity, bf_val="100", br_val="2"))
    vc, vb, ve = Decimal(vc_s), Decimal(vb_s), Decimal(ve_s)

    jac = bjt_jacobian(vc, vb, ve, p, ctx)
    assert jac is not None

    # Step for central finite difference (1 uV gives optimal balance in Decimal-50)
    h = Decimal("1E-8")

    coords = [vc, vb, ve]
    for m in range(3):
        c_plus = list(coords)
        c_plus[m] = ctx.add(c_plus[m], h)
        i_plus = bjt_terminal_currents(c_plus[0], c_plus[1], c_plus[2], p, ctx)

        c_minus = list(coords)
        c_minus[m] = ctx.subtract(c_minus[m], h)
        i_minus = bjt_terminal_currents(c_minus[0], c_minus[1], c_minus[2], p, ctx)

        for k in range(3):
            dI_num = ctx.divide(ctx.subtract(i_plus[k], i_minus[k]), ctx.multiply(Decimal(2), h))
            dI_ana = jac[k][m]

            diff = abs(ctx.subtract(dI_ana, dI_num))
            scale = max(abs(dI_ana), abs(dI_num), Decimal("1E-12"))
            rel_err = ctx.divide(diff, scale)

            assert rel_err < Decimal("1E-6"), (
                f"Jacobian mismatch at polarity={polarity} node=({vc_s},{vb_s},{ve_s}) "
                f"k={k} m={m}: ana={dI_ana} num={dI_num} rel_err={rel_err}"
            )


def test_jacobian_row_and_column_sums():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN"))
    vc, vb, ve = Decimal("4.0"), Decimal("0.72"), Decimal("0.0")
    jac = bjt_jacobian(vc, vb, ve, p, ctx)
    assert jac is not None

    for row_idx, row in enumerate(jac):
        row_sum = ctx.add(ctx.add(row[0], row[1]), row[2])
        scale = max(abs(v) for v in row)
        assert abs(row_sum) <= ctx.multiply(scale, Decimal("1E-25")), f"Row {row_idx} sum nonzero"

    for col_idx in range(3):
        col_sum = ctx.add(ctx.add(jac[0][col_idx], jac[1][col_idx]), jac[2][col_idx])
        scale = max(abs(jac[row_idx][col_idx]) for row_idx in range(3))
        assert abs(col_sum) <= ctx.multiply(scale, Decimal("1E-25")), f"Col {col_idx} sum nonzero"


def test_invariance_under_global_potential_shift():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN"))
    vc, vb, ve = Decimal("5.0"), Decimal("0.7"), Decimal("0.0")
    shift = Decimal("100.0")

    i1 = bjt_terminal_currents(vc, vb, ve, p, ctx)
    i2 = bjt_terminal_currents(ctx.add(vc, shift), ctx.add(vb, shift), ctx.add(ve, shift), p, ctx)

    for a, b in zip(i1, i2):
        assert abs(ctx.subtract(a, b)) < Decimal("1E-25")

    j1 = bjt_jacobian(vc, vb, ve, p, ctx)
    j2 = bjt_jacobian(ctx.add(vc, shift), ctx.add(vb, shift), ctx.add(ve, shift), p, ctx)

    for r1, r2 in zip(j1, j2):
        for val1, val2 in zip(r1, r2):
            assert abs(ctx.subtract(val1, val2)) < Decimal("1E-25")


# ----------------------------------------------------------------------
# 5. Companion Model Equivalence
# ----------------------------------------------------------------------

def test_companion_model_taylor_expansion():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN"))
    vc, vb, ve = Decimal("5.0"), Decimal("0.7"), Decimal("0.0")
    currents, jac, ieq = bjt_companion(vc, vb, ve, p, ctx)

    assert jac is not None
    assert ieq is not None
    v_vec = (vc, vb, ve)
    for k in range(3):
        rec_i = ieq[k]
        for m in range(3):
            rec_i = ctx.add(rec_i, ctx.multiply(jac[k][m], v_vec[m]))
        assert abs(ctx.subtract(currents[k], rec_i)) < Decimal("1E-25")


# ----------------------------------------------------------------------
# 6. Overflow Protection
# ----------------------------------------------------------------------

def test_overflow_protection_extreme_voltages():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN"))
    # 1E12 V across base-emitter causes astronomical exp overflow in Decimal
    vc, vb, ve = Decimal("0.0"), Decimal("1000000000000.0"), Decimal("0.0")

    if_val, ir_val = bjt_injection_currents(vc, vb, ve, p, ctx)
    assert not if_val.is_finite()

    currents = bjt_terminal_currents(vc, vb, ve, p, ctx)
    assert not all(c.is_finite() for c in currents)

    jac = bjt_jacobian(vc, vb, ve, p, ctx)
    assert jac is None


# ----------------------------------------------------------------------
# 7. AST Security Audit
# ----------------------------------------------------------------------

def test_ast_security_audit_bjt_module():
    bjt_path = Path(__file__).parent.parent / "src" / "academic_core" / "domain" / "engineering" / "mna" / "bjt.py"
    with open(bjt_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(bjt_path))

    forbidden_names = {"eval", "exec", "compile", "globals", "locals", "__import__"}
    forbidden_modules = {"os", "sys", "subprocess", "socket", "urllib", "requests", "shutil"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in forbidden_names:
                pytest.fail(f"Forbidden call found: {node.func.id}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_modules, f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_modules, f"Forbidden from-import: {node.module}"


# ----------------------------------------------------------------------
# 8. Determinism & Zero Float
# ----------------------------------------------------------------------

def test_determinism_identical_runs():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN"))
    vc, vb, ve = Decimal("3.3"), Decimal("0.68"), Decimal("0.0")

    run1 = bjt_terminal_currents(vc, vb, ve, p, ctx)
    run2 = bjt_terminal_currents(vc, vb, ve, p, ctx)
    assert run1 == run2

    j1 = bjt_jacobian(vc, vb, ve, p, ctx)
    j2 = bjt_jacobian(vc, vb, ve, p, ctx)
    assert j1 == j2


def test_absence_of_float():
    ctx = make_context()
    p = extract_bjt_params(_make_q("NPN"))
    for val in (p.Is, p.Bf, p.Br, p.Nf, p.Nr, p.Vt, p.alphaF, p.alphaR):
        assert isinstance(val, Decimal)

    currents = bjt_terminal_currents(Decimal("3"), Decimal("0.7"), Decimal("0"), p, ctx)
    for c in currents:
        assert isinstance(c, Decimal)

    jac = bjt_jacobian(Decimal("3"), Decimal("0.7"), Decimal("0"), p, ctx)
    for row in jac:
        for val in row:
            assert isinstance(val, Decimal)
