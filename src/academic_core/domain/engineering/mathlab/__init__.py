# SPDX-License-Identifier: MIT
"""MATH_LAB — the mathematics laboratory, phase ML-0 (Cimientos).

Scope of this package
---------------------

ML-0 is the first phase of ``MATH_LAB.md`` §10: the foundations every later
phase stands on.

- ``mvexpr``   multivariate exact expressions, text input with a live preview,
               and the bridge to the E0.1 single-variable engine;
- ``poly``     exact multivariate normal form and rational functions — the
               engine behind the equivalence-based corrector;
- ``trace``    the step trace of §5.2, versioned and serialisable, with the
               mandatory «por qué este método» of §5.5b;
- ``verify``   the independent second paths of §5.3 and the three seals;
- ``derive_mv``partial and total differentiation, verified against a central
               difference;
- ``contract`` the stable interface of §5.9 that the other laboratories use;
- ``calculators`` the first calculators, registered against that contract.

What is deliberately *not* here yet
----------------------------------

ML-1 through ML-22 are separate phases (§10): arithmetic and elementary
algebra, one-variable calculus, linear algebra, series, several variables,
multiple integration, ODEs and transforms, probability, and the v2 blocks. The
foundation is built so they can be added without touching what exists: every
calculation already goes through :func:`contract.calcular` and returns a
:class:`contract.Resultado` with a trace, a seal and a graph described as data.

Two rules this package never breaks
-----------------------------------

**Nothing is shown as correct without an independent second path** (§5.3,
§11.2 criterion 2). A result whose second path fails gets the ``✘ Discrepa``
seal, and :func:`contract.calcular` will not let a caller ignore it.

**The domain is pure** — no Qt, no backends, no filesystem, no network, and no
third-party library. A library such as SymPy may later be registered as a
verification plug-in from *outside* this package (§5.8), but the steps are
always produced here.

The E0.1 engine (``domain/engineering/symbolic``) is **reused, not rewritten**
(§12): ``mvexpr.to_symbolic`` hands a single-variable expression to it and
``derive_mv`` copies its step log into the ML-0 format, so the certified rules
and their explanations remain the source of the steps.
"""

from __future__ import annotations

from academic_core.domain.engineering.mathlab import calculators  # registers the operations
from academic_core.domain.engineering.mathlab import calculadoras_ml9  # noqa: F401  ML-9
from academic_core.domain.engineering.mathlab import calculadoras_ml14  # noqa: F401  ML-14
from academic_core.domain.engineering.mathlab import calculadoras_ml15  # noqa: F401  ML-15
from academic_core.domain.engineering.mathlab import calculadoras_ml16  # noqa: F401  ML-16
from academic_core.domain.engineering.mathlab import calculadoras_ml22  # noqa: F401  ML-22
from academic_core.domain.engineering.mathlab import calculadoras_dem  # noqa: F401  demostraciones
from academic_core.domain.engineering.mathlab import calculadoras_ml17  # noqa: F401  ML-17
from academic_core.domain.engineering.mathlab import calculadoras_ml18  # noqa: F401  ML-18
from academic_core.domain.engineering.mathlab import calculadoras_ml19  # noqa: F401  ML-19
from academic_core.domain.engineering.mathlab import calculadoras_ml20  # noqa: F401  ML-20
from academic_core.domain.engineering.mathlab import calculadoras_ml21  # noqa: F401  ML-21
from academic_core.domain.engineering.mathlab import calculadoras_ml10  # noqa: F401  ML-10
from academic_core.domain.engineering.mathlab import calculadoras_ml11  # noqa: F401  ML-11
from academic_core.domain.engineering.mathlab import derive_mv
from academic_core.domain.engineering.mathlab import mvexpr
from academic_core.domain.engineering.mathlab import poly
from academic_core.domain.engineering.mathlab import trace
from academic_core.domain.engineering.mathlab import verify
from academic_core.domain.engineering.mathlab.contract import (
    CONTRACT_VERSION,
    ConvencionConjunto,
    Graph,
    Limites,
    Peticion,
    Resultado,
    Serie,
    calcular,
    comprobar_version,
    operaciones,
    registrar,
    registrar_verificador,
    verificadores,
    withdraw_verificador,
)
from academic_core.domain.engineering.mathlab.mvexpr import Expr, parse, parse_calculus, preview
from academic_core.domain.engineering.mathlab.trace import DETALLADO, PASO, RESUMEN, Trace
from academic_core.domain.engineering.mathlab.verify import Seal

#: phase implemented, per §10
FASE = "ML-0"
FASE_NOMBRE = "Cimientos"

#: the version of the §5.9 contract this package speaks
CONTRACT_VERSION = CONTRACT_VERSION

__all__ = [
    "CONTRACT_VERSION", "DETALLADO", "Expr", "FASE", "FASE_NOMBRE", "Graph",
    "Limites", "PASO", "Peticion", "RESUMEN", "Resultado", "Seal", "Serie", "Trace",
    "calcular", "comprobar_version", "derive_mv", "mvexpr", "operaciones", "parse",
    "parse_calculus", "poly", "preview", "registrar", "registrar_verificador", "trace",
    "verificadores", "verify", "withdraw_verificador",
]
