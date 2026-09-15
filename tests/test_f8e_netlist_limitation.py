"""AUDIT-002 contract: netlist limitation for dependent sources.

El netlist F6 existente soporta la representación estructural básica,
pero la serialización/persistencia de los parámetros específicos de
E/G/H/F queda fuera de alcance de F8-E. Los circuitos con fuentes
dependientes no deben considerarse roundtrip-complete mediante el
formato netlist actual.

These tests express the LIMITATION (they must keep failing-to-roundtrip
if anyone claims completeness); they do not resolve it.
"""
import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna.errors import InvalidCircuitError
from academic_core.domain.engineering.mna.problem import build_mna_problem
from academic_core.domain.engineering.units import parse_quantity


def Q(text):
    return parse_quantity(text)


def test_dependent_parameters_not_preserved_by_netlist():
    c = Circuit("dep")
    c.add(Component("E1", "E", Q("2"), {"+": "a", "-": "0"},
                    {"cp": "in", "cn": "0"}))
    nl = c.to_netlist()
    assert "E1" in nl  # structural line exists
    back = Circuit.from_netlist(nl, name="dep")
    e1 = next(x for x in back.components if x.ref == "E1")
    assert dict(e1.parameters) == {}, dict(e1.parameters)


@pytest.mark.parametrize("typ", ["G", "H", "F"])
def test_all_dependent_kinds_lose_parameters(typ):
    pins = {"+": "a", "-": "0"}
    params = {"cp": "in", "cn": "0"} if typ == "G" else {"control_ref": "R1"}
    c = Circuit(f"dep-{typ}")
    c.add(Component("R1", "R", Q("1 kOhm"), {"1": "in", "2": "0"}, {}))
    c.add(Component(f"{typ}1", typ, Q("2") if typ in ("E", "F") else
                    Q("2 mS") if typ == "G" else Q("2 ohm"),
                    pins, params))
    back = Circuit.from_netlist(c.to_netlist(), name=f"dep-{typ}")
    d1 = next(x for x in back.components if x.ref == f"{typ}1")
    assert dict(d1.parameters) == {}


def test_parameterless_dependent_rejected_honestly():
    # No silent acceptance, no invented parameters: build fails honestly.
    back = Circuit.from_netlist("* dep\nE1 a 0 2\nR1 a 0 1kohm\n.end\n",
                                name="dep")
    with pytest.raises(InvalidCircuitError):
        build_mna_problem(back)


def test_rvi_structural_roundtrip_still_complete():
    c = Circuit("div")
    c.add(Component("R1", "R", Q("1 kOhm"), {"1": "in", "2": "0"}, {}))
    c.add(Component("V1", "V", Q("5 V"), {"+": "in", "-": "0"}, {}))
    nl = c.to_netlist()
    assert Circuit.from_netlist(nl, name="div").to_netlist() == nl
