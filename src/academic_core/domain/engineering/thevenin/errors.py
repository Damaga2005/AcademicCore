"""Structured error hierarchy for F8-C Thevenin & Norton analysis.

Follows the repo-wide convention (flat ValueError subclasses, one per
distinct failure mode).
"""

from __future__ import annotations


class InvalidPortError(ValueError):
    """Raised when a specified port is structurally invalid: non-existent nets,
    terminals that coincide (A == B), empty terminal strings, or undefined port."""


class UnsupportedCircuitError(ValueError):
    """Raised when the target circuit contains elements outside the linear DC
    domain (only R, V, I supported), or is missing reference / floating."""
