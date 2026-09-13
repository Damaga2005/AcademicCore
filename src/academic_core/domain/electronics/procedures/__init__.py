"""AnalysisProcedure / AnalysisStep registry (Phase 8-A, section 11).

Represents how a student would solve a problem, step by step, so that a
future Exam Engine can later compare an attempt against these steps. Not an
executable workflow engine yet (section 12) — just the structured model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.electronics.types import provenance


@dataclass(frozen=True)
class AnalysisStep:
    order: int
    description: str
    required_inputs: tuple[str, ...] = ()
    equation: str | None = None  # equation stable_id
    expected_output: str | None = None
    dependencies: tuple[int, ...] = ()  # prior step `order`s this step needs
    validation: str | None = None
    mandatory: bool = True


@dataclass(frozen=True)
class AnalysisProcedure:
    stable_id: str  # "procedure:<name>"
    concept: str  # concept stable_id
    analysis: str  # analysis stable_id
    steps: tuple[AnalysisStep, ...]
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        orders = [s.order for s in self.steps]
        if orders != sorted(orders) or len(set(orders)) != len(orders):
            raise ValueError(f"{self.stable_id}: step order must be strictly increasing")
        for s in self.steps:
            if any(d >= s.order for d in s.dependencies):
                raise ValueError(f"{self.stable_id}: step {s.order} depends on a later/self step")


def _step(order, description, required_inputs=(), equation=None, expected_output=None,
          dependencies=(), validation=None, mandatory=True) -> AnalysisStep:
    return AnalysisStep(order, description, required_inputs, equation,
                         expected_output, dependencies, validation, mandatory)


def _procedure(stable_id, concept, analysis, steps) -> AnalysisProcedure:
    return AnalysisProcedure(stable_id, concept, analysis, steps, provenance(stable_id))


PROCEDURES: dict[str, AnalysisProcedure] = {
    p.stable_id: p for p in (
        _procedure("procedure:voltage-divider-dc", "concept:voltage-divider", "analysis:dc", (
            _step(1, "Identify ground/reference node."),
            _step(2, "Identify the source voltage Vin.", ("Vin",)),
            _step(3, "Identify the series resistor chain R1..Rn.", ("R1", "R2")),
            _step(4, "Identify the explicit output node (tap) Vout.",
                  validation="tap node must be explicit, never inferred"),
            _step(5, "Calculate equivalent series resistance.", ("R1", "R2"),
                  equation="equation:series-resistors", expected_output="Req",
                  dependencies=(3,)),
            _step(6, "Calculate branch current I = Vin / Req.", ("Vin", "Req"),
                  equation="equation:ohm-i", expected_output="I", dependencies=(2, 5)),
            _step(7, "Calculate output voltage Vout.", ("Vin", "R1", "R2"),
                  equation="equation:voltage-divider", expected_output="Vout",
                  dependencies=(2, 3, 4)),
            _step(8, "Calculate resistor power dissipation.", ("I", "R1", "R2"),
                  equation="equation:power-i2r", expected_output="P", dependencies=(6,)),
            _step(9, "Verify KCL at the tap node.", validation="branch current in == out",
                  dependencies=(6,)),
            _step(10, "Verify conservation of power (supplied == dissipated).",
                  dependencies=(8,)),
            _step(11, "Optionally verify with a SPICE .op simulation.", mandatory=False,
                  dependencies=(7,)),
        )),
        _procedure("procedure:current-divider-dc", "concept:current-divider", "analysis:dc", (
            _step(1, "Identify the total injected current Itot.", ("Itot",)),
            _step(2, "Identify the parallel resistor branches R1..Rn.", ("R1", "R2")),
            _step(3, "Calculate equivalent parallel resistance.", ("R1", "R2"),
                  equation="equation:parallel-resistors", expected_output="Req", dependencies=(2,)),
            _step(4, "Calculate each branch current Ik.", ("Itot", "R1", "R2"),
                  equation="equation:current-divider", expected_output="I1", dependencies=(1, 2)),
            _step(5, "Verify KCL: sum of branch currents equals Itot.", dependencies=(4,)),
            _step(6, "Optionally verify with a SPICE .op simulation.", mandatory=False, dependencies=(4,)),
        )),
        _procedure("procedure:series-resistors-dc", "concept:series-resistors", "analysis:dc", (
            _step(1, "Confirm each intermediate node has exactly two incident branches."),
            _step(2, "Calculate equivalent series resistance.", ("R1", "R2"),
                  equation="equation:series-resistors", expected_output="Req", dependencies=(1,)),
            _step(3, "Calculate the common branch current via Ohm's law.",
                  equation="equation:ohm-i", dependencies=(2,)),
        )),
        _procedure("procedure:parallel-resistors-dc", "concept:parallel-resistors", "analysis:dc", (
            _step(1, "Confirm each resistor shares both terminal nodes."),
            _step(2, "Calculate equivalent parallel resistance.", ("R1", "R2"),
                  equation="equation:parallel-resistors", expected_output="Req", dependencies=(1,)),
            _step(3, "Calculate branch currents via Ohm's law and verify KCL.",
                  equation="equation:ohm-i", dependencies=(2,)),
        )),
        _procedure("procedure:dc-resistive-network", "concept:dc-resistive-network", "analysis:dc", (
            _step(1, "Identify the reference (ground) node."),
            _step(2, "Formulate KCL at each non-reference node."),
            _step(3, "Formulate KVL for each fundamental loop.", dependencies=(1,)),
            _step(4, "Solve the resulting linear system for node voltages / branch currents.",
                  dependencies=(2, 3)),
            _step(5, "Calculate power delivered/dissipated and verify conservation of power.",
                  equation="equation:power-vi", dependencies=(4,)),
            _step(6, "Optionally verify with a SPICE .op simulation.", mandatory=False, dependencies=(4,)),
        )),
        _procedure("procedure:thevenin", "concept:thevenin", "analysis:thevenin", (
            _step(1, "Identify the target terminal pair (the port).",
                  validation="terminals must be explicit and distinct"),
            _step(2, "Calculate Vth as the open-circuit voltage at the port.",
                  equation="equation:voltage-divider", expected_output="Vth", dependencies=(1,)),
            _step(3, "Zero all independent sources (short V, open I).", dependencies=(1,)),
            _step(4, "Calculate Rth as the resistance seen from the port with sources zeroed.",
                  equation="equation:parallel-resistors", expected_output="Rth", dependencies=(3,)),
            _step(5, "Optionally verify with a SPICE .op simulation of the equivalent.",
                  mandatory=False, dependencies=(2, 4)),
        )),
        _procedure("procedure:norton", "concept:norton", "analysis:norton", (
            _step(1, "Obtain Vth and Rth via the Thevenin procedure.",
                  dependencies=(), validation="reuse procedure:thevenin, do not recompute"),
            _step(2, "Calculate In = Vth / Rth.", equation="equation:ohm-i",
                  expected_output="In", dependencies=(1,)),
            _step(3, "Set Rn = Rth.", expected_output="Rn", dependencies=(1,)),
        )),
        _procedure("procedure:resistive-bridge", "concept:resistive-bridge", "analysis:kvl", (
            _step(1, "Identify the four bridge arms R1, R2, R3, R4 and the galvanometer branch."),
            _step(2, "Calculate the balance ratio (R1*R4)/(R2*R3).",
                  equation="equation:bridge-balance", expected_output="balance_ratio",
                  dependencies=(1,)),
            _step(3, "If balance_ratio == 1, the bridge is balanced (no galvanometer current).",
                  validation="ratio must equal exactly 1 for balance", dependencies=(2,)),
            _step(4, "If unbalanced, solve via KCL/KVL for the galvanometer branch current.",
                  mandatory=False, dependencies=(2,)),
        )),
    )
}


def get(stable_id: str) -> AnalysisProcedure:
    return PROCEDURES[stable_id]


__all__ = ["AnalysisStep", "AnalysisProcedure", "PROCEDURES", "get"]
