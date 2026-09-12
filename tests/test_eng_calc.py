"""Calculations: library values, provenance, reproducibility, precision."""
from academic_core.domain.engineering.calc import (
    LIBRARY, calculate,
)
from academic_core.domain.engineering.units import parse_quantity


def q(**kw):
    return {k: parse_quantity(v) for k, v in kw.items()}


def test_ohm_power_energy_charge_freq():
    assert calculate(q(V="5 V", R="1 kohm"), "I = V / R").value.format() == "0.005 A"
    assert calculate(q(V="12 V", R="100 ohm"), "P = V**2 / R").value.convert_to("W").value == \
        __import__("decimal").Decimal("1.44")
    assert calculate(q(I="2 A", R="10 ohm"), "P = I**2 * R").value.format() == "40 W"
    assert calculate(q(C="10 uF", V="5 V"), "Q = C * V").value.convert_to("uC").value == \
        __import__("decimal").Decimal("50")
    assert calculate(q(C="100 uF", V="10 V"), "E = 0.5 * C * V ** 2").value.format() == \
        "0.005 J"
    assert calculate(q(L="1 mH", I="2 A"), "E = 0.5 * L * I ** 2").value.format() == \
        "0.002 J"
    assert calculate(q(T="20 ms"), "f = 1 / T").value.format() == "50 Hz"


def test_voltage_divider_and_sensors():
    r = calculate(q(Vi="10 V", R1="10 kohm", R2="10 kohm"), "Vout = Vi * R2 / (R1 + R2)")
    assert r.value.format() == "5 V"
    pt = calculate(q(R0="100 ohm", A="3.9083e-3", B="-5.775e-7", T="100"),
                   LIBRARY["pt100-cvd"]["source"])
    assert abs(pt.value.value - __import__("decimal").Decimal("138.5055")) < \
        __import__("decimal").Decimal("0.0001")
    ntc = calculate(q(R0="10 kohm", B="3950", T="323.15", T0="298.15"),
                    LIBRARY["ntc-beta"]["source"])
    assert 3000 < ntc.value.convert_to("ohm").value < 5000
    rg = calculate(q(G="10"), LIBRARY["ad620-rg"]["source"])
    assert rg.value.convert_to("ohm").value == \
        __import__("decimal").Decimal("49.4") * 1000 / 9
    w = calculate(q(Vs="10 V", K="2.05", eps="1200e-6"), LIBRARY["wheatstone"]["source"])
    assert w.value.convert_to("mV").value == __import__("decimal").Decimal("24.6")


def test_provenance_and_reproducibility():
    a = calculate(q(V="5 V", R="1 kohm"), "I = V / R")
    b = calculate(q(R="1 kohm", V="5 V"), "I = V / R")  # order-independent
    assert a.digest == b.digest and a.engine.startswith("engcalc/")
    assert a.inputs == {"V": {"value": "5", "unit": "V"},
                        "R": {"value": "1", "unit": "kΩ"}}
    assert a.timestamp and a.equation_source == "I = V / R"
    c = calculate(q(V="6 V", R="1 kohm"), "I = V / R")
    assert c.digest != a.digest  # new inputs = different calculation


def test_library_shapes():
    assert set(LIBRARY) >= {"ohm-v", "ohm-i", "ohm-r", "power-vi", "power-i2r",
                            "power-v2r", "charge-qcv", "energy-cap", "energy-ind",
                            "freq-period", "voltage-divider", "pt100-cvd",
                            "ntc-beta", "ad620-rg", "wheatstone"}
    for key, entry in LIBRARY.items():
        assert "source" in entry and "=" in entry["source"]
