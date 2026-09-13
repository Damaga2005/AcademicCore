"""General Thevenin & Norton Analysis (Phase F8-C).

Provides general two-terminal DC linear one-port reduction (Thevenin and
Norton equivalents) over the linear DC domain of F8-B, reusing the certified
MNA solver without introducing a second linear-algebra engine.
"""

from __future__ import annotations

from academic_core.domain.engineering.thevenin.analysis import (
    SOLVER_ENGINE,
    SOLVER_VERSION,
    analyze_norton,
    analyze_one_port,
    analyze_thevenin,
)
from academic_core.domain.engineering.thevenin.errors import InvalidPortError, UnsupportedCircuitError
from academic_core.domain.engineering.thevenin.port import TheveninPort
from academic_core.domain.engineering.thevenin.result import (
    EquivalentStatus,
    LoadVerificationResult,
    NortonResult,
    OnePortEquivalent,
    ResistanceKind,
    TheveninResult,
)
from academic_core.domain.engineering.thevenin.verification import verify_equivalent_with_loads

__all__ = [
    "TheveninPort",
    "TheveninResult",
    "NortonResult",
    "OnePortEquivalent",
    "LoadVerificationResult",
    "EquivalentStatus",
    "ResistanceKind",
    "analyze_thevenin",
    "analyze_norton",
    "analyze_one_port",
    "verify_equivalent_with_loads",
    "InvalidPortError",
    "UnsupportedCircuitError",
    "SOLVER_ENGINE",
    "SOLVER_VERSION",
]
