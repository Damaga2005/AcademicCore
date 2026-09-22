"""F8-Q.1 digital core (NEW): public surface."""

from academic_core.domain.engineering.digital.core import (
    DIGITAL_CORE_VERSION,
    ID_RE,
    MAX_EVENTS,
    MAX_NETS,
    MAX_TIME,
    DigitalCircuit,
    DigitalEvent,
    DigitalNet,
    DigitalSimulator,
    EventQueue,
    LogicState,
    check_id,
    check_sequence,
    check_state,
    check_time,
)

__all__ = [
    "DIGITAL_CORE_VERSION",
    "ID_RE",
    "MAX_EVENTS",
    "MAX_NETS",
    "MAX_TIME",
    "DigitalCircuit",
    "DigitalEvent",
    "DigitalNet",
    "DigitalSimulator",
    "EventQueue",
    "LogicState",
    "check_id",
    "check_sequence",
    "check_state",
    "check_time",
]
