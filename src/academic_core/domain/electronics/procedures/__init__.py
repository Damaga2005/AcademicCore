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
    equation: str | None = None  # equation stable_id (fixed-arity, F6-parseable)
    law: str | None = None  # GeneralLaw stable_id (general N-ary computation)
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
        order_set = set(orders)
        for s in self.steps:
            if any(d >= s.order for d in s.dependencies):
                raise ValueError(f"{self.stable_id}: step {s.order} depends on a later/self step")
            missing = [d for d in s.dependencies if d not in order_set]
            if missing:
                raise ValueError(f"{self.stable_id}: step {s.order} depends on missing step(s) {missing}")


def _step(order, description, required_inputs=(), equation=None, law=None, expected_output=None,
          dependencies=(), validation=None, mandatory=True) -> AnalysisStep:
    return AnalysisStep(order, description, required_inputs, equation, law,
                         expected_output, dependencies, validation, mandatory)


def _procedure(stable_id, concept, analysis, steps) -> AnalysisProcedure:
    return AnalysisProcedure(stable_id, concept, analysis, steps, provenance(stable_id))


PROCEDURES: dict[str, AnalysisProcedure] = {
    p.stable_id: p for p in (
        _procedure("procedure:voltage-divider-dc", "concept:voltage-divider", "analysis:dc", (
            _step(1, "Identify ground/reference node."),
            _step(2, "Identify the source voltage Vin.", ("Vin",)),
            _step(3, "Identify the series resistor chain R1..Rn (N >= 1).", ("R1..Rn",)),
            _step(4, "Identify the explicit output node (tap) Vout.",
                  validation="tap node must be explicit, never inferred"),
            _step(5, "Calculate equivalent series resistance for the whole chain.", ("R1..Rn",),
                  law="law:series-resistors", expected_output="Req",
                  dependencies=(3,)),
            _step(6, "Calculate branch current I = Vin / Req.", ("Vin", "Req"),
                  equation="equation:ohm-i", expected_output="I", dependencies=(2, 5)),
            _step(7, "Calculate output voltage Vout = Vin * (R below tap) / Req.", ("Vin", "R1..Rn"),
                  law="law:voltage-divider", expected_output="Vout",
                  dependencies=(2, 3, 4)),
            _step(8, "Calculate resistor power dissipation per resistor.", ("I", "R1..Rn"),
                  equation="equation:power-i2r", expected_output="P", dependencies=(6,)),
            _step(9, "Verify KCL at the tap node.", validation="branch current in == out",
                  law="law:kcl", dependencies=(6,)),
            _step(10, "Verify conservation of power (supplied == dissipated).",
                  dependencies=(8,)),
            _step(11, "Optionally verify with a SPICE .op simulation.", mandatory=False,
                  dependencies=(7,)),
        )),
        _procedure("procedure:current-divider-dc", "concept:current-divider", "analysis:dc", (
            _step(1, "Identify the total injected current Itot.", ("Itot",)),
            _step(2, "Identify the parallel resistor branches R1..Rn (N >= 2).", ("R1..Rn",)),
            _step(3, "Calculate equivalent parallel resistance for all branches.", ("R1..Rn",),
                  law="law:parallel-resistors", expected_output="Req", dependencies=(2,)),
            _step(4, "Calculate each branch current Ik via conductance ratio.", ("Itot", "R1..Rn"),
                  law="law:current-divider", expected_output="I1..In", dependencies=(1, 2)),
            _step(5, "Verify KCL: sum of branch currents equals Itot.", law="law:kcl", dependencies=(4,)),
            _step(6, "Optionally verify with a SPICE .op simulation.", mandatory=False, dependencies=(4,)),
        )),
        _procedure("procedure:series-resistors-dc", "concept:series-resistors", "analysis:dc", (
            _step(1, "Confirm each intermediate node has exactly two incident branches."),
            _step(2, "Calculate equivalent series resistance for all N resistors.", ("R1..Rn",),
                  law="law:series-resistors", expected_output="Req", dependencies=(1,)),
            _step(3, "Calculate the common branch current via Ohm's law.",
                  equation="equation:ohm-i", dependencies=(2,)),
        )),
        _procedure("procedure:parallel-resistors-dc", "concept:parallel-resistors", "analysis:dc", (
            _step(1, "Confirm each resistor shares both terminal nodes."),
            _step(2, "Calculate equivalent parallel resistance for all N resistors.", ("R1..Rn",),
                  law="law:parallel-resistors", expected_output="Req", dependencies=(1,)),
            _step(3, "Calculate branch currents via Ohm's law and verify KCL.",
                  equation="equation:ohm-i", law="law:kcl", dependencies=(2,)),
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
        # NOTE (section 6/36): Vth/Rth are NOT computed by plugging the port
        # into the two-resistor divider/parallel *equations* -- that would be
        # exactly the "2-resistor case presented as universal solver"
        # anti-pattern this hardening pass removes. The general, honest
        # procedure is: reduce the port sub-network via repeated series/
        # parallel combination (law:series-resistors / law:parallel-resistors,
        # both N-ary) with sources zeroed for Rth. That covers any port whose
        # sub-network is series-parallel reducible, for any N of resistors --
        # not just two. A port that is NOT series-parallel reducible (e.g. an
        # unbalanced bridge as one arm of the port) needs a general linear
        # network solve (nodal/mesh analysis), which is explicitly
        # NOT_IMPLEMENTED in F8-A (see analysis:thevenin.limitations) rather
        # than silently faked.
        _procedure("procedure:thevenin", "concept:thevenin", "analysis:thevenin", (
            _step(1, "Identify the target terminal pair (the port).",
                  validation="terminals must be explicit and distinct"),
            _step(2, "Calculate Vth as the open-circuit voltage at the port.",
                  law="law:voltage-divider", expected_output="Vth", dependencies=(1,),
                  validation="requires the port sub-network to be series-parallel reducible; "
                             "otherwise Vth is NOT_IMPLEMENTED in F8-A"),
            _step(3, "Zero all independent sources (short V, open I).", dependencies=(1,)),
            _step(4, "Reduce the port sub-network via repeated series/parallel combination "
                     "(any depth, any N of resistors) to obtain Rth.",
                  law="law:series-resistors", expected_output="Rth", dependencies=(3,),
                  validation="requires series-parallel reducibility; otherwise Rth is "
                             "NOT_IMPLEMENTED in F8-A (needs a general linear-network solver)"),
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
