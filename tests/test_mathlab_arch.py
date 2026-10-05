"""MATH_LAB architecture gate: the mathematics laboratory is a *lower* layer.

These tests live beside ``test_architecture.py`` rather than inside
``test_mathlab_ml0.py`` because they are the same kind of gate, and because a
failure here means the layering is wrong, not that a calculation is wrong.

What is enforced, and why each rule exists:

- **MATH_LAB §1.2 principle 5** — the mathematics lives in the domain and the
  interface only draws and asks. So the package imports no Qt, ever.
- **§5.9** — the contract is offered to the other laboratories; the direction of
  the dependency is ``digital → math``, ``signals → math``, ``circuits → math``.
  Never the reverse: a math module that imported ``dsp`` or ``ac`` would make
  the shared engine depend on the labs it is supposed to serve, and every later
  phase would inherit a cycle.
- **§12** — the E0.1 engine is extended, not rewritten. The existing files stay
  untouched; if this gate ever fails because ``symbolic/`` was edited in place,
  the certified features that depend on it have silently changed.
- **§5.8 / D1** — an external library (SymPy, NumPy, SciPy) may be registered as
  a *verifier*, but only from outside the domain and only lazily. The steps are
  always produced by the engine itself.

Parsed with ``ast``: a docstring naming another laboratory is documentation,
not a dependency.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core"
ML = SRC / "domain" / "engineering" / "mathlab"

pytestmark = pytest.mark.arch

#: the labs that consume the math engine (§16) and may therefore never be
#: imported *by* it
LABS_CONSUMIDORAS = ("dsp", "rf", "comms", "satcom", "mna", "ac", "digital",
                     "lab", "orbital", "structural", "thevenin")

#: layers above the domain (§1.2, ADR-0002)
CAPAS_SUPERIORES = ("ui", "application", "infrastructure", "storage", "engines",
                    "documents", "pdf", "resources", "config")


def _modulos_importados(f: pathlib.Path) -> list[str]:
    tree = ast.parse(f.read_text(encoding="utf-8"))
    out: list[str] = []
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.Import):
            out.extend(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            out.append(nodo.module or "")
    return out


def _paquete_de(modulo: str) -> list[str]:
    """The part of a module path that identifies its layer, e.g. ``engineering.dsp``."""
    partes = modulo.split(".")
    if not partes or partes[0] != "academic_core":
        return []
    if len(partes) > 1 and partes[1] == "engineering":
        return partes[2:3]
    return partes[1:2]


def test_el_paquete_existe():
    assert ML.is_dir(), f"falta el laboratorio de matemáticas: {ML}"
    assert sorted(p.name for p in ML.glob("*.py"))


def test_el_laboratorio_de_matematicas_no_importa_qt():
    """§1.2 principle 5: the interface only draws and asks."""
    for f in ML.rglob("*.py"):
        for modulo in _modulos_importados(f):
            assert not modulo.startswith("PySide6"), f"{f.name} importa {modulo}"


def test_el_laboratorio_no_depende_de_los_laboratorios_que_lo_consumen():
    """§16: the dependency is digital → math, signals → math, circuits → math."""
    for f in ML.rglob("*.py"):
        for modulo in _modulos_importados(f):
            capa = _paquete_de(modulo)
            for laboratorio in LABS_CONSUMIDORAS:
                assert laboratorio not in capa, f"{f.name} importa {modulo}"


def test_el_laboratorio_no_depende_de_las_capas_superiores():
    for f in ML.rglob("*.py"):
        for modulo in _modulos_importados(f):
            capa = _paquete_de(modulo)
            for superior in CAPAS_SUPERIORES:
                assert superior not in capa, f"{f.name} importa {modulo}"


def test_el_laboratorio_no_depende_de_la_interfaz_ni_de_la_aplicacion():
    """No screen may be reached from a calculation (§5.9)."""
    for f in ML.rglob("*.py"):
        for modulo in _modulos_importados(f):
            assert not modulo.startswith("academic_core.app"), f"{f.name} importa {modulo}"


def test_el_laboratorio_no_importa_una_biblioteca_externa():
    """§5.8 and D1: an external library may *check*, never compute or step.

    The domain is stdlib only. A verifier from SymPy or SciPy has to be
    registered from the outside, lazily, and a missing one must only lower the
    seal (§5.9) — never break the calculation.
    """
    externas = {"numpy", "sympy", "scipy", "mpmath", "matplotlib", "pandas",
                "networkx", "symengine"}
    for f in ML.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(tree):
            nombres: list[str] = []
            if isinstance(nodo, ast.Import):
                nombres = [a.name.split(".")[0] for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                nombres = [(nodo.module or "").split(".")[0]]
            for nombre in nombres:
                assert nombre not in externas, f"{f.name} importa {nombre}"


def test_el_laboratorio_no_abre_ficheros_ni_red():
    """The domain is pure: no filesystem, no network, no subprocess."""
    prohibido = {"os", "pathlib", "shutil", "tempfile", "socket", "urllib",
                 "http", "ftplib", "subprocess", "sqlite3"}
    for f in ML.rglob("*.py"):
        for modulo in _modulos_importados(f):
            assert modulo.split(".")[0] not in prohibido, f"{f.name} importa {modulo}"


def test_no_hay_generador_aleatorio_en_el_dominio():
    """§11.2 criterion 7: every result is deterministic and reproducible.

    The project convention is an explicit LCG (``verify.sample_values``), never
    the ``random`` module, so a verdict can be replayed exactly.
    """
    for f in ML.rglob("*.py"):
        for modulo in _modulos_importados(f):
            assert modulo.split(".")[0] not in {"random", "secrets"}, f"{f.name} importa {modulo}"


def test_el_motor_e01_se_amplia_pero_no_se_reescribe():
    """§12: the existing engine is reused, so its files must still be there.

    A future phase that edits ``symbolic/`` in place would change the results of
    every certified feature that depends on it (§11.2 criterion 9). The ML
    extension is a sibling package, and the bridge is ``mvexpr.to_symbolic``.
    """
    simbolico = SRC / "domain" / "engineering" / "symbolic"
    for nombre in ("__init__.py", "expr.py", "derive.py", "integrate.py",
                   "normal.py", "solve.py", "steps.py", "numeric.py"):
        assert (simbolico / nombre).is_file(), f"falta {nombre} del motor E0.1"


def test_el_puente_al_motor_e01_es_explicito():
    """``math → symbolic`` one way, and the refusals are in Spanish.

    ``to_symbolic`` returns an E0.1 expression, so it is printed with *that*
    engine's printer; the round trip back through ``from_symbolic`` is what has
    to preserve the mathematics.
    """
    from academic_core.domain.engineering.mathlab import mvexpr as mx
    from academic_core.domain.engineering.symbolic.expr import text as texto_e01
    from academic_core.errors import UnsupportedError

    ida = mx.to_symbolic(mx.parse("x^2+2x+1"))
    assert texto_e01(ida) == "x^2 + 2*x + 1"
    assert mx.text(mx.from_symbolic(ida)) == "x^2 + 2*x + 1"
    # e^x must cross the bridge as exp(x), not as exp(1)^x: the latter has no
    # rule in E0.1 and would be a dead end.
    assert texto_e01(mx.to_symbolic(mx.parse("e^x"))) == "exp(x)"
    # pi and i have no form in a one-variable engine: said, not guessed
    for source in ("pi", "i^2"):
        with pytest.raises(UnsupportedError) as exc:
            mx.to_symbolic(mx.parse(source))
        assert "«" in str(exc.value)


def test_la_calculadora_se_puede_llamar_sin_interfaz():
    """§5.9: another laboratory calls the domain function, never a screen."""
    import academic_core.domain.engineering.mathlab as ML

    resultado = ML.calcular(ML.Peticion("derivar", "x^3+2x"))
    assert resultado.exacto == "3·x² + 2"
    assert resultado.traza.steps
    assert resultado.sello.ok


def test_el_contrato_declara_su_version():
    """§5.9: the contract carries a version and a consumer declares its own."""
    import academic_core.domain.engineering.mathlab as ML
    from academic_core.domain.engineering.mathlab import trace as TR
    from academic_core.errors import ValidationError

    assert ML.CONTRACT_VERSION
    assert TR.TRACE_VERSION
    ML.comprobar_version(ML.CONTRACT_VERSION)
    with pytest.raises(ValidationError):
        ML.comprobar_version("99.0")
