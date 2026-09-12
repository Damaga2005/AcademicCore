"""Circuit: components, pins/nets, topology, deterministic netlist roundtrip."""
import pytest

from academic_core.domain.engineering.circuit import (
    Circuit, CircuitError, Component, EngineeringProject,
)
from academic_core.domain.engineering.units import parse_quantity as Q


def divider():
    c = Circuit("divisor")
    c.add(Component("V1", "V", Q("5 V"), {"+": "IN", "-": "0"}))
    c.add(Component("R1", "R", Q("10 kohm"), {"1": "IN", "2": "OUT"}))
    c.add(Component("R2", "R", Q("10 kohm"), {"1": "OUT", "2": "0"}))
    return c


def test_topology_clean_and_deterministic():
    c = divider()
    assert c.validate() == []
    assert c.to_netlist() == ("* divisor [engcircuit/6.0]\n"
                              "R1 IN OUT 10kohm\n"
                              "R2 OUT 0 10kohm\n"
                              "V1 IN 0 5V\n.end\n")


def test_topology_warnings():
    c = Circuit("lonely")
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "A", "2": "B"}))
    assert c.validate() == ["floating pin: R1.1 (net A)", "floating pin: R1.2 (net B)"]
    assert Circuit("empty").validate() == ["empty circuit"]


def test_invalid_constructions_rejected():
    c = Circuit("t")
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "A", "2": "B"}))
    with pytest.raises(CircuitError):
        c.add(Component("R1", "R", Q("2 kohm"), {"1": "A", "2": "B"}))  # dup ref
    with pytest.raises(CircuitError):
        Component("C1", "R", Q("1 kohm"), {"1": "A", "2": "B"})  # ref/type mismatch
    with pytest.raises(CircuitError):
        Component("R2", "R", Q("1 kohm"), {"1": "A"})  # missing pin
    with pytest.raises(CircuitError):
        Component("R3", "R", Q("1 kohm"), {"1": "", "2": "B"})  # empty net
    with pytest.raises(CircuitError):
        Component("X1", "X", None, {})  # unknown type


def test_netlist_roundtrip_and_malformed():
    nl = divider().to_netlist()
    assert Circuit.from_netlist(nl, name="divisor").to_netlist() == nl
    with pytest.raises(CircuitError):
        Circuit.from_netlist("R1 IN\n.end")
    with pytest.raises(CircuitError):
        Circuit.from_netlist("R1 IN OUT 10 XX\n.end")
    with pytest.raises(CircuitError):
        Circuit.from_netlist("R1 IN OUT 10kohm\nR1 OUT 0 1kohm\n.end")  # dup


def test_project_links_optional():
    p = EngineeringProject("lab1", "subject:sistemes-de-mesura")
    assert p.circuits == [] and p.subject_id.startswith("subject:")
    with pytest.raises(CircuitError):
        EngineeringProject("  ")
    with pytest.raises(CircuitError):
        EngineeringProject("x", subject_id="rowid:1")


def test_all_component_types():
    from academic_core.domain.engineering import models as M
    c = Circuit("all")
    c.add(Component("R1", "R", Q("1 kohm"), {"1": "A", "2": "B"}))
    c.add(Component("C1", "C", Q("100 nF"), {"1": "B", "2": "0"}))
    c.add(Component("L1", "L", Q("1 mH"), {"1": "B", "2": "0"}))
    c.add(Component("V1", "V", Q("5 V"), {"+": "A", "-": "0"}))
    c.add(Component("I1", "I", Q("10 mA"), {"+": "A", "-": "0"}))
    c.add(Component("D1", "D", None, {"A": "A", "K": "0"}))
    c.add(Component("Q1", "Q", None, {"C": "A", "B": "B", "E": "0"}))
    assert len(c.to_netlist().splitlines()) == 9
    assert M.resistor(Q("1 kohm")).params["R"].format() == "1 kΩ"
    with pytest.raises(CircuitError):
        M.resistor(Q("1 uF"))
    with pytest.raises(CircuitError):
        M.resistor(Q("0 ohm"))
