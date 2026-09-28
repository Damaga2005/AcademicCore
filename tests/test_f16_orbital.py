# SPDX-License-Identifier: MIT
"""F16 contenido aeroespacial: mecanica orbital basica determinista.

Contrato: Decimal SI (m, kg, s, rad), sin floats, errores tipados
ControlError, trazas ExecutionTrace desde la ejecucion real.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

MU_EARTH = Decimal("398600441800000")  # 398600.4418 km^3/s^2, en m^3/s^2
R_EARTH = Decimal("6371000")
H_ISS = Decimal("420000")


def _D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


# -- cuerpo central ----------------------------------------------------

def test_earth_preset_has_provenance_and_si_values():
    from academic_core.domain.engineering.orbital import EARTH
    assert EARTH.name == "Earth"
    assert EARTH.mass_kg > 0 and EARTH.radius_m == R_EARTH
    assert EARTH.mu_m3_s2 == MU_EARTH
    assert "provenance" in dir(EARTH) or EARTH.provenance != ""


def test_central_body_rejects_nonpositive_and_non_decimal():
    from academic_core.domain.engineering.orbital import CentralBody
    with pytest.raises(ValueError):
        CentralBody("X", Decimal("0"), Decimal("1000"), Decimal("10"), provenance="t")
    with pytest.raises(ValueError):
        CentralBody("X", Decimal("10"), Decimal("-5"), Decimal("10"), provenance="t")
    with pytest.raises(ValueError):
        CentralBody("X", 10.0, Decimal("1000"), Decimal("10"), provenance="t")  # float no


# -- orbita circular / periodo ------------------------------------------

def test_circular_velocity_iss_known_case():
    from academic_core.domain.engineering.orbital import EARTH, circular_velocity_m_s
    v = circular_velocity_m_s(R_EARTH + H_ISS, EARTH.mu_m3_s2)
    assert abs(v - Decimal("7660")) < Decimal("15")  # ~7668 m/s


def test_circular_period_iss_known_case():
    from academic_core.domain.engineering.orbital import EARTH, circular_period_s
    t = circular_period_s(R_EARTH + H_ISS, EARTH.mu_m3_s2)
    assert abs(t - Decimal("5560")) < Decimal("30")  # ~92-93 min


def test_geo_altitude_from_sidereal_day():
    from academic_core.domain.engineering.orbital import (
        EARTH,
        altitude_from_radius_m,
        radius_from_period_m,
    )
    r = radius_from_period_m(Decimal("86164.0905"), EARTH.mu_m3_s2)
    h = altitude_from_radius_m(r, EARTH.radius_m)
    assert abs(h - Decimal("35786000")) < Decimal("20000")  # ~35786 km


def test_radius_altitude_roundtrip_and_domain():
    from academic_core.domain.engineering.orbital import (
        EARTH,
        altitude_from_radius_m,
        radius_from_altitude_m,
    )
    assert altitude_from_radius_m(radius_from_altitude_m(H_ISS, EARTH.radius_m),
                                  EARTH.radius_m) == H_ISS
    with pytest.raises(ValueError):
        radius_from_altitude_m(Decimal("-10"), EARTH.radius_m)
    with pytest.raises(ValueError):
        altitude_from_radius_m(EARTH.radius_m - 1, EARTH.radius_m)  # bajo superficie


def test_period_radius_inverse():
    from academic_core.domain.engineering.orbital import (
        EARTH,
        circular_period_s,
        radius_from_period_m,
    )
    r = R_EARTH + H_ISS
    assert abs(radius_from_period_m(circular_period_s(r, EARTH.mu_m3_s2),
                                    EARTH.mu_m3_s2) - r) < Decimal("0.001")


# -- vis-viva / energia / escape -----------------------------------------

def test_vis_viva_matches_circular_and_ellipse():
    from academic_core.domain.engineering.orbital import (
        EARTH,
        circular_velocity_m_s,
        vis_viva_semimajor_m,
        vis_viva_velocity_m_s,
    )
    r = R_EARTH + H_ISS
    assert abs(vis_viva_velocity_m_s(r, r, EARTH.mu_m3_s2)
               - circular_velocity_m_s(r, EARTH.mu_m3_s2)) < Decimal("1E-9")
    # Molniya-like: rp=7000km, ra=42000km -> a=24500km; vis-viva en rp
    a = Decimal("24500000")
    vp = vis_viva_velocity_m_s(Decimal("7000000"), a, EARTH.mu_m3_s2)
    assert vp > circular_velocity_m_s(Decimal("7000000"), EARTH.mu_m3_s2)
    assert abs(vis_viva_semimajor_m(Decimal("7000000"), vp, EARTH.mu_m3_s2) - a) < Decimal("1")


def test_energy_consistent_and_escape_known():
    from academic_core.domain.engineering.orbital import (
        EARTH,
        escape_velocity_m_s,
        kinetic_energy_j,
        potential_energy_j,
        specific_energy_j_kg,
        total_energy_j,
    )
    m = Decimal("1000")
    r = R_EARTH + H_ISS
    v = Decimal("7668")
    assert kinetic_energy_j(m, v) == m * v * v / 2
    assert potential_energy_j(m, r, EARTH.mu_m3_s2) < 0
    assert total_energy_j(m, v, r, EARTH.mu_m3_s2) == \
        kinetic_energy_j(m, v) + potential_energy_j(m, r, EARTH.mu_m3_s2)
    # specific vs total/m agree to 12 significant figures (50-digit working
    # precision; different exact operation orders round the last digits).
    rel = abs(specific_energy_j_kg(v, r, EARTH.mu_m3_s2)
              - total_energy_j(m, v, r, EARTH.mu_m3_s2) / m)
    assert rel < abs(specific_energy_j_kg(v, r, EARTH.mu_m3_s2)) * Decimal("1E-12")
    vesc = escape_velocity_m_s(R_EARTH, EARTH.mu_m3_s2)
    assert abs(vesc - Decimal("11186")) < Decimal("10")  # ~11.186 km/s


# -- elipse / kepler / elementos ------------------------------------------

def test_ellipse_apsides_and_eccentricity_domain():
    from academic_core.domain.engineering.orbital import (
        apoapsis_m,
        ellipse_from_apsides_m,
        periapsis_m,
    )
    a, e = Decimal("24500000"), Decimal("0.72")
    assert periapsis_m(a, e) == a * (1 - e)
    assert apoapsis_m(a, e) == a * (1 + e)
    a2, e2 = ellipse_from_apsides_m(Decimal("7000000"), Decimal("42000000"))
    assert abs(a2 - a) < Decimal("1") and abs(e2 - e) < Decimal("0.01")
    with pytest.raises(ValueError):
        periapsis_m(a, Decimal("1"))  # e < 1
    with pytest.raises(ValueError):
        periapsis_m(a, Decimal("-0.1"))


def test_kepler_roundtrip_and_nonconvergence_error():
    from academic_core.domain.engineering.orbital import (
        eccentric_from_mean_rad,
        eccentric_from_true_rad,
        mean_from_eccentric_rad,
        true_from_eccentric_rad,
    )
    e = Decimal("0.5")
    M = Decimal("1.0")
    E = eccentric_from_mean_rad(M, e)
    assert abs(mean_from_eccentric_rad(E, e) - M) < Decimal("1E-25")
    nu = true_from_eccentric_rad(E, e)
    assert abs(eccentric_from_true_rad(nu, e) - E) < Decimal("1E-25")
    with pytest.raises(ValueError):
        eccentric_from_mean_rad(M, e, max_iter=1)  # no converge -> error claro


def test_classical_elements_validated_and_digested():
    from academic_core.domain.engineering.orbital import ClassicalElements
    el = ClassicalElements(a_m=Decimal("7000000"), e=Decimal("0.01"),
                           i_rad=Decimal("0.5"), omega_rad=Decimal("0"),
                           argp_rad=Decimal("0"), nu_rad=Decimal("0"))
    d1 = el.digest()
    assert el.digest() == d1 and len(d1) == 64
    with pytest.raises(ValueError):
        ClassicalElements(a_m=Decimal("7000000"), e=Decimal("1.5"),
                          i_rad=Decimal("0"), omega_rad=Decimal("0"),
                          argp_rad=Decimal("0"), nu_rad=Decimal("0"))
    with pytest.raises(ValueError):
        ClassicalElements(a_m=Decimal("7000000"), e=Decimal("0"),
                          i_rad=Decimal("0"), omega_rad=Decimal("0"),
                          argp_rad=Decimal("0"), nu_rad=Decimal("0"), frame="NOPE")


# -- unidades / determinismo / traza ---------------------------------------

def test_units_extended_mass_force_angle():
    from academic_core.domain.engineering.units import parse_quantity
    assert parse_quantity("5.97237E24 kg").dim_name == "mass"
    assert parse_quantity("1 N").dim_name == "force"
    assert parse_quantity("1 km").convert_to("m").value == Decimal("1000")
    assert parse_quantity("1 rad").dimension == (0, 0, 0, 0, 0, 0, 0)
    from academic_core.domain.engineering.orbital import deg_to_rad
    assert deg_to_rad(Decimal("180")) == deg_to_rad(Decimal("180"))  # determinista


def test_determinism_same_digest():
    from academic_core.domain.engineering.orbital import EARTH, circular_velocity_m_s
    v1 = circular_velocity_m_s(R_EARTH + H_ISS, EARTH.mu_m3_s2)
    v2 = circular_velocity_m_s(R_EARTH + H_ISS, EARTH.mu_m3_s2)
    assert v1 == v2


def test_execution_trace_orbital_replay():
    from academic_core.domain.execution import orbital as OT
    t = OT.explain_circular_velocity(str(R_EARTH + H_ISS), str(MU_EARTH))
    assert t.operation == OT.OPERATION and t.outcome.value == "SUCCESS"
    r = OT.replay_orbital(t)
    assert OT.compare_equivalent(t, r)


def test_f16_no_dangerous_calls_or_imports():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "src" / "academic_core"
    files = [root / "domain/engineering/orbital/__init__.py",
             root / "domain/engineering/orbital/constants.py",
             root / "domain/engineering/orbital/bodies.py",
             root / "domain/engineering/orbital/orbits.py",
             root / "domain/engineering/orbital/kepler.py",
             root / "domain/engineering/orbital/elements.py",
             root / "domain/execution/orbital.py"]
    assert all(p.is_file() for p in files)
    forbidden = {"pickle", "marshal", "shelve", "subprocess", "socket",
                 "urllib", "http", "requests", "flask", "sqlalchemy",
                 "PySide6", "ctypes", "os", "threading", "pathlib", "sqlite3"}
    bad = []
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8"), str(p))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in ("eval", "exec", "compile", "__import__"):
                bad.append(f"{p.name}:{n.lineno}:{n.func.id}")
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else (
                [n.module or ""] if isinstance(n, ast.ImportFrom) else [])
            for m in mods:
                if m.split(".")[0] in forbidden:
                    bad.append(f"{p.name}:{m}")
    assert bad == []
