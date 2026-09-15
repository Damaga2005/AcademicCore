"""Port representation and validation for F8-C Thevenin & Norton analysis.

A port represents an electrical two-terminal interface on a canonical
`Circuit`. It does NOT duplicate the circuit or invent nodes; it references
two existing distinct nets.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.domain.engineering.circuit import Circuit
from academic_core.domain.engineering.thevenin.errors import InvalidPortError, UnsupportedCircuitError

SUPPORTED_TYPES = frozenset({"R", "V", "I", "E", "G", "H", "F", "O"})


@dataclass(frozen=True)
class TheveninPort:
    """An electrical two-terminal interface defined by two distinct nets."""

    positive_terminal: str
    negative_terminal: str

    def __post_init__(self) -> None:
        pos = str(self.positive_terminal or "").strip()
        neg = str(self.negative_terminal or "").strip()
        if not pos or not neg:
            raise InvalidPortError("both port terminals must be non-empty strings")
        if pos == neg:
            raise InvalidPortError(
                f"degenerate port: positive and negative terminals coincide ({pos!r} == {neg!r})"
            )

    @property
    def name(self) -> str:
        return f"{self.positive_terminal}->{self.negative_terminal}"

    def validate_against(self, circuit: Circuit) -> None:
        """Validate this port against a canonical `Circuit`.

        Ensures:
        1. Both terminals exist as nets in `circuit.nets`.
        2. Reference node ('0' or 'GND') exists in `circuit.nets`.
        3. All components belong to the F8-B linear DC domain
           (R, V, I, dependent E, G, H, F, and ideal op-amp O).
        """
        if self.positive_terminal not in circuit.nets:
            raise InvalidPortError(
                f"port positive terminal {self.positive_terminal!r} does not exist in circuit {circuit.name!r}"
            )
        if self.negative_terminal not in circuit.nets:
            raise InvalidPortError(
                f"port negative terminal {self.negative_terminal!r} does not exist in circuit {circuit.name!r}"
            )

        ref_candidates = {net for net in circuit.nets if net.strip().upper() in ("0", "GND")}
        if not ref_candidates:
            raise InvalidPortError(
                f"circuit {circuit.name!r} has no reference node ('0' or 'GND')"
            )

        for c in circuit.components:
            if c.type.upper() not in SUPPORTED_TYPES:
                raise UnsupportedCircuitError(
                    f"{c.ref}: component type {c.type!r} is unsupported in F8-C linear DC domain "
                    f"(R, V, I, dependent E, G, H, F, ideal op-amp O)"
                )
