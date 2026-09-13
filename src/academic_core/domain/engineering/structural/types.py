"""Structural Circuit Analysis types and enums (Phase 7-B8).

Pure domain definitions: strictly typed, deterministic, no stringly-typed APIs.
"""

from __future__ import annotations

from enum import Enum


class TopologyType(str, Enum):
    """Catalog of structural circuit topologies and patterns recognized in F7-B8."""

    # General electrical categories
    RESISTIVE = "RESISTIVE"
    ENERGY_STORAGE = "ENERGY_STORAGE"
    MIXED = "MIXED"
    UNKNOWN_TOPOLOGY = "UNKNOWN_TOPOLOGY"

    # Resistive fundamental topologies
    SINGLE_RESISTOR = "SINGLE_RESISTOR"
    SERIES_RESISTORS = "SERIES_RESISTORS"
    PARALLEL_RESISTORS = "PARALLEL_RESISTORS"
    SERIES_PARALLEL_REDUCIBLE = "SERIES_PARALLEL_REDUCIBLE"
    SERIES_PARALLEL_MIXED = "SERIES_PARALLEL_MIXED"
    VOLTAGE_DIVIDER = "VOLTAGE_DIVIDER"
    CURRENT_DIVIDER = "CURRENT_DIVIDER"
    RESISTIVE_BRIDGE = "RESISTIVE_BRIDGE"
    RESISTIVE_WITH_SOURCE = "RESISTIVE_WITH_SOURCE"
    NON_REDUCIBLE_RESISTIVE = "NON_REDUCIBLE_RESISTIVE"

    # Sources
    INDEPENDENT_VOLTAGE_SOURCE = "INDEPENDENT_VOLTAGE_SOURCE"
    INDEPENDENT_CURRENT_SOURCE = "INDEPENDENT_CURRENT_SOURCE"

    # Dynamic topologies
    RC = "RC"
    RL = "RL"
    RLC = "RLC"


class AnalysisType(str, Enum):
    """Types of electrical analysis supported or classified in AcademicCore."""

    # Fundamental circuit analysis methods
    DC_OPERATING_POINT = "DC_OPERATING_POINT"
    DC_SWEEP = "DC_SWEEP"
    DC_STEADY_STATE = "DC_STEADY_STATE"
    TRANSIENT = "TRANSIENT"
    AC = "AC"
    NOISE = "NOISE"
    SENSITIVITY = "SENSITIVITY"
    MONTE_CARLO = "MONTE_CARLO"
    GUM_UNCERTAINTY = "GUM_UNCERTAINTY"

    # Structural & Network Theorems
    KCL = "KCL"
    KVL = "KVL"
    OHMS_LAW = "OHMS_LAW"
    VOLTAGE_DIVIDER = "VOLTAGE_DIVIDER"
    CURRENT_DIVIDER = "CURRENT_DIVIDER"
    POWER = "POWER"
    THEVENIN = "THEVENIN"
    NORTON = "NORTON"


class ApplicabilityStatus(str, Enum):
    """Applicability status of an analysis to a given circuit structure."""

    PRIMARY = "PRIMARY"
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    NEEDS_TARGET_TERMINALS = "NEEDS_TARGET_TERMINALS"


class ConfidenceLevel(str, Enum):
    """Confidence level of topology recognition and classification."""

    DETERMINISTIC = "DETERMINISTIC"
    HIGH = "HIGH"
    ABSTAINED = "ABSTAINED"
