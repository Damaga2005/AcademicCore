"""F8-A hardening: generality tests (section 40/41).

Demonstrates that series/parallel/current-divider/voltage-divider are NOT
hardcoded to two resistors (R1/R2) -- they hold for N in {1, 2, 3, 4, 8, 16}
-- and that the SPECIAL_CASE / GENERAL split (section 5), the GeneralLaw
registry, and the Thevenin/Norton honesty fix (section 6/36) are real.
"""

from __future__ import annotations

import ast
import re
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.units import Quantity, parse_quantity
from academic_core.domain.electronics import calc
from academic_core.domain.electronics.analyses import ANALYSES
from academic_core.domain.electronics.concepts import CONCEPTS
from academic_core.domain.electronics.equations import EQUATIONS, GENERAL_LAWS
from academic_core.domain.electronics.procedures import PROCEDURES
from academic_core.domain.electronics.registry import validate_registries
from academic_core.domain.electronics.types import Generality, ImplementationStatus

SIZES = (1, 2, 3, 4, 8, 16)


def _resistors(n: int, start_kohm: int = 1) -> list[Quantity]:
    return [parse_quantity(f"{start_kohm + i} kohm") for i in range(n)]


# ==============================================================================
# 1. Series / parallel: no artificial N==2 limit (section 10/26/41)
# ==============================================================================
@pytest.mark.parametrize("n", SIZES)
def test_series_equivalent_general_n(n):
    rs = _resistors(n)
    req = calc.series_equivalent(rs)
    expected = sum((r.to_base() for r in rs), Decimal(0))
    assert req.to_base() == expected
    # invariant (section 30): Req >= max(Ri) for positive resistances
    assert req.to_base() >= max(r.to_base() for r in rs)


@pytest.mark.parametrize("n", SIZES)
def test_parallel_equivalent_general_n(n):
    rs = _resistors(n)
    req = calc.parallel_equivalent(rs)
    expected = Decimal(1) / sum((Decimal(1) / r.to_base() for r in rs), Decimal(0))
    assert abs(req.to_base() - expected) / expected < Decimal("1e-20")
    # invariant (section 30): Req <= min(Ri) for positive resistances
    assert req.to_base() <= min(r.to_base() for r in rs)


def test_series_order_independence():
    rs = _resistors(5)
    assert calc.series_equivalent(rs).to_base() == calc.series_equivalent(list(reversed(rs))).to_base()


def test_parallel_order_independence():
    rs = _resistors(5)
    assert calc.parallel_equivalent(rs).to_base() == calc.parallel_equivalent(list(reversed(rs))).to_base()


# ==============================================================================
# 2. Current divider: N >= 2 branches, currents conserve Itot (section 12/30)
# ==============================================================================
@pytest.mark.parametrize("n", [n for n in SIZES if n >= 2])
def test_current_divider_general_n_conserves_current(n):
    rs = _resistors(n)
    itot = parse_quantity("10 mA")
    currents = calc.current_divider(itot, rs)
    assert len(currents) == n
    total = currents[0]
    for c in currents[1:]:
        total = total + c
    assert abs(total.to_base() - itot.to_base()) < Decimal("1e-20")
    # larger R -> smaller branch current (monotonic, general property)
    paired = sorted(zip(rs, currents), key=lambda t: t[0].to_base())
    for (r_lo, i_lo), (r_hi, i_hi) in zip(paired, paired[1:]):
        assert i_lo.to_base() >= i_hi.to_base()


def test_current_divider_rejects_single_branch():
    with pytest.raises(calc.GeneralityError):
        calc.current_divider(parse_quantity("1 mA"), _resistors(1))


def test_current_divider_rejects_empty():
    with pytest.raises(calc.GeneralityError):
        calc.current_divider(parse_quantity("1 mA"), [])


# ==============================================================================
# 3. Voltage divider chain: any N, any explicit tap, 0 <= Vout <= Vin (section 11/30)
# ==============================================================================
@pytest.mark.parametrize("n", SIZES)
def test_voltage_divider_chain_general_n_bounded(n):
    rs = _resistors(n)
    vin = parse_quantity("12 V")
    for tap in range(n):
        vout = calc.voltage_divider_chain(vin, rs, tap)
        assert Decimal(0) <= vout.to_base() <= vin.to_base()


def test_voltage_divider_chain_last_tap_is_zero():
    rs = _resistors(4)
    vin = parse_quantity("12 V")
    vout = calc.voltage_divider_chain(vin, rs, len(rs) - 1)
    assert vout.to_base() == 0


def test_voltage_divider_chain_rejects_bad_tap():
    rs = _resistors(3)
    with pytest.raises(calc.GeneralityError):
        calc.voltage_divider_chain(parse_quantity("1 V"), rs, 3)
    with pytest.raises(calc.GeneralityError):
        calc.voltage_divider_chain(parse_quantity("1 V"), rs, -1)


def test_voltage_divider_chain_rejects_empty():
    with pytest.raises(calc.GeneralityError):
        calc.voltage_divider_chain(parse_quantity("1 V"), [], 0)


# ==============================================================================
# 4. Generality contract: GENERAL vs SPECIAL_CASE is a checkable field, not prose
# ==============================================================================
def test_special_case_concepts_declare_parent():
    two_r = CONCEPTS["concept:two-resistor-divider"]
    assert two_r.generality == Generality.SPECIAL_CASE
    assert two_r.parent == "concept:voltage-divider"
    assert CONCEPTS[two_r.parent].generality == Generality.GENERAL

    balanced = CONCEPTS["concept:wheatstone-bridge-balanced"]
    assert balanced.generality == Generality.SPECIAL_CASE
    assert balanced.parent == "concept:resistive-bridge"
    assert CONCEPTS[balanced.parent].generality == Generality.GENERAL


def test_pairwise_equations_are_special_cases_of_a_general_law():
    for eq_id, law_id in (
        ("equation:series-resistors-pair", "law:series-resistors"),
        ("equation:parallel-resistors-pair", "law:parallel-resistors"),
        ("equation:current-divider-pair", "law:current-divider"),
        ("equation:voltage-divider-pair", "law:voltage-divider"),
    ):
        eq = EQUATIONS[eq_id]
        assert eq.generality == Generality.SPECIAL_CASE
        assert eq.parent == law_id
        law = GENERAL_LAWS[law_id]
        assert law.special_case_equation == eq_id


def test_general_laws_declare_covered_and_not_covered_domain():
    for law in GENERAL_LAWS.values():
        assert law.domain, f"{law.stable_id}: missing domain"
        assert law.not_covered, f"{law.stable_id}: missing not_covered"
        assert law.conditions, f"{law.stable_id}: missing conditions"


def test_general_concepts_declare_covered_and_not_covered_domain():
    for concept in CONCEPTS.values():
        if concept.generality == Generality.GENERAL and concept.stable_id in (
            "concept:series-resistors", "concept:parallel-resistors",
            "concept:voltage-divider", "concept:current-divider",
            "concept:resistive-bridge", "concept:thevenin", "concept:norton",
        ):
            assert concept.domain_covered, f"{concept.stable_id}: missing domain_covered"
            assert concept.domain_not_covered, f"{concept.stable_id}: missing domain_not_covered"


# ==============================================================================
# 5. Thevenin/Norton: no 2-resistor solver disguised as a general one (section 6)
# ==============================================================================
def test_thevenin_norton_are_not_silently_universal():
    thevenin = ANALYSES["analysis:thevenin"]
    norton = ANALYSES["analysis:norton"]
    assert thevenin.implementation_status == ImplementationStatus.PARTIAL
    assert norton.implementation_status == ImplementationStatus.PARTIAL
    # must not claim the 2-resistor pairwise equations solve Vth/Rth directly
    assert "equation:voltage-divider-pair" not in thevenin.equations
    assert "equation:parallel-resistors-pair" not in thevenin.equations
    assert "law:series-resistors" in thevenin.laws
    assert "law:parallel-resistors" in thevenin.laws


def test_thevenin_procedure_uses_general_laws_not_pair_equations():
    proc = PROCEDURES["procedure:thevenin"]
    for step in proc.steps:
        assert step.equation not in ("equation:voltage-divider-pair", "equation:parallel-resistors-pair")
    used_laws = {s.law for s in proc.steps if s.law}
    assert "law:series-resistors" in used_laws
    assert "law:voltage-divider" in used_laws


# ==============================================================================
# 6. Registry stays consistent after the hardening pass
# ==============================================================================
def test_registries_still_have_no_invariant_violations():
    assert validate_registries() == []


# ==============================================================================
# 7. No hidden N==2 cap in production code (section 41)
# ==============================================================================
def test_no_hardcoded_two_component_limit_in_electronics_domain():
    root = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "electronics"
    suspect = re.compile(r"len\([A-Za-z_.]+\)\s*==\s*2")
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in suspect.finditer(text):
            hits.append(f"{path.name}:{text.count(chr(10), 0, m.start()) + 1}: {m.group()}")
    # The only legitimate len(...) == 2 checks left are the SPECIAL_CASE
    # concept:two-resistor-divider recognizer branch, which exists precisely
    # to detect the N==2 special case (not to cap the general concept).
    unexpected = [h for h in hits if "recognition.py" not in h]
    assert not unexpected, f"unexpected hardcoded 2-component checks: {unexpected}"


def test_no_eval_exec_subprocess_in_new_calc_module():
    path = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "electronics" / "calc.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    banned = {"eval", "exec", "subprocess", "compile", "os", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in banned:
            pytest.fail(f"forbidden name {node.id!r} used in calc.py")
