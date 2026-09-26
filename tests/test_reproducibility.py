"""Reproducibility: netlist generation + CAS hashing are deterministic."""
import pytest

from academic_core.engines.engineering import Circuit, Component
from academic_core.storage import Store

pytestmark = pytest.mark.repro


def test_netlist_deterministic():
    c = Circuit("lab:sistemes-de-mesura:lab:00006",
                [Component("R1", "R", "10k", ("n1", "n2"))])
    assert c.to_netlist() == c.to_netlist()
    assert ".end" in c.to_netlist()


def test_cas_deterministic(tmp_path):
    st = Store(tmp_path / "m.db", tmp_path / "cas")
    assert st.put_bytes(b"abc") == st.put_bytes(b"abc")
