# SPDX-License-Identifier: MIT
"""D2 error taxonomy root + UI-safe error converter (F15 implementation).

Single root ``AcademicCoreError(ValueError)``. Existing domain/application
error classes are re-parented under it in their own modules (names, modules
and ``ValueError`` ancestry preserved, so every ``except ValueError``
handler keeps working). New categories defined here.

UI boundary: exactly ONE converter ``to_ui_error`` (exception/result ->
frozen ``UiError``). No widget invents its own mapping.
"""

from __future__ import annotations

from dataclasses import dataclass


class AcademicCoreError(ValueError):
    """Single D2 root. Carries a stable ``AC-<AREA>-<NNN>`` code."""

    code = "AC-APP-000"
    category = "application"

    def __init__(self, message: str = "", *, code: str = ""):
        super().__init__(message)
        if code:
            self.code = code
        self.message = message


class ValidationError(AcademicCoreError):
    code = "AC-VAL-001"
    category = "validation"


class ConfigurationError(AcademicCoreError):
    code = "AC-CFG-001"
    category = "configuration"


class UnsupportedError(AcademicCoreError):
    code = "AC-UNS-001"
    category = "unsupported"


class SerializationError(AcademicCoreError):
    code = "AC-SER-001"
    category = "serialization"


class VersionMismatchError(AcademicCoreError):
    code = "AC-VER-001"
    category = "version"


class AdapterError(AcademicCoreError):
    code = "AC-ADP-001"
    category = "adapter"


class InfrastructureError(AcademicCoreError):
    code = "AC-INF-001"
    category = "infrastructure"


class IntegrationError(AcademicCoreError):
    code = "AC-INT-001"
    category = "integration"


class AcademicManagementError(AcademicCoreError):
    """F4.1 academic management use-case failure (unknown entity, guard...)."""
    code = "AC-ACD-001"
    category = "academic"


class MigrationError(AcademicCoreError):
    """F4.1 legacy data migration failure (never partially applied)."""
    code = "AC-MIG-001"
    category = "migration"


# F4.1 code registry (documented in docs/specs/ERROR-CODES.md; uniqueness
# is enforced by tests/test_f4_security.py).
F41_ERROR_CODES: dict[str, str] = {
    "AC-ACD-001": "academic management operation refused",
    "AC-ACD-002": "unknown academic entity",
    "AC-ACD-003": "academic integrity guard (duplicate / still referenced)",
    "AC-ACD-004": "invalid academic value (state, category, weight...)",
    "AC-MIG-001": "migration failed; target left unchanged",
    "AC-MIG-002": "legacy source is not a valid/consistent SQLite database",
    "AC-MIG-003": "legacy schema version not supported",
    "AC-MIG-004": "snapshot of the target is required before applying",
    "AC-MIG-005": "migration cancelled; target left unchanged",
    "AC-MIG-006": "post-migration validation failed",
    "AC-SEC-002": "path escapes the allowed root (refused)",
    "AC-SEC-003": "archive rejected (zip slip / bomb / limits)",
    "AC-ICS-001": "calendar file rejected (format or limits)",
}


# ---------------------------------------------------------------------------
# UiError (D2 §14): the ONLY value widgets may present.
# ---------------------------------------------------------------------------

SEVERITIES = ("INFO", "WARNING", "ERROR", "CRITICAL")
RECOVERABILITIES = ("RETRY", "RECOVER", "CONFIG_CHANGE", "NONE")


@dataclass(frozen=True)
class UiError:
    error_code: str
    safe_message: str
    severity: str = "ERROR"
    recoverability: str = "RECOVER"
    user_action: str = ""


_FALLBACK = UiError(
    error_code="AC-APP-000",
    safe_message="The operation could not be completed.",
    severity="ERROR",
    recoverability="RECOVER",
    user_action="Check the highlighted values and try again.",
)


def _code_of(exc: BaseException) -> str:
    return str(getattr(exc, "code", "") or getattr(type(exc), "code", "") or "")


def to_ui_error(exc: BaseException) -> UiError:
    """Convert any exception/result into a UI-safe ``UiError``.

    Never leaks: tracebacks, SQL, subprocess commands, absolute home
    paths, secrets, digests, or private internals. Cause chains cross
    layers as ``cause_code`` only (callers log the correlation id).
    """
    name = type(exc).__name__
    code = _code_of(exc) or "AC-APP-000"

    if isinstance(exc, AcademicCoreError) or name in (
        "DomainError", "AuthoringError", "AstError", "UnitError",
        "CircuitError", "EquationError", "GeneralityError", "ControlError",
        "MetrologyError", "LabConfigError",
    ):
        if "VERSION_MISMATCH" in str(exc) or "VersionMismatch" in name:
            return UiError(code if code != "AC-APP-000" else "AC-VER-001",
                           "This file was created by a different version and cannot be opened.",
                           "ERROR", "CONFIG_CHANGE",
                           "Re-export from the current version or pick a compatible file.")
        if "SCHEMA_MISMATCH" in str(exc) or "SCHEMA" in str(exc):
            return UiError(code if code != "AC-APP-000" else "AC-SER-002",
                           "This file has an unrecognized format and was rejected.",
                           "ERROR", "CONFIG_CHANGE",
                           "Select a file exported by this application.")
        if any(k in str(exc) for k in ("INVALID_SERIALIZATION", "tamper", "INCONSISTENT")):
            return UiError(code if code != "AC-APP-000" else "AC-SER-001",
                           "The file is invalid or damaged and was rejected. Nothing was changed.",
                           "ERROR", "NONE",
                           "Pick a valid exported file.")
        if "UNSUPPORTED" in str(exc) or isinstance(exc, UnsupportedError):
            return UiError(code if code != "AC-APP-000" else "AC-UNS-001",
                           "This request is not supported in the current version.",
                           "WARNING", "CONFIG_CHANGE",
                           "Change the request to a supported configuration.")
        return UiError(code, "The value is invalid. Check the highlighted field and try again.",
                       "WARNING", "RECOVER", "Correct the highlighted value and retry.")
    if name in ("SecurityError",) or "Security" in name:
        return UiError("AC-SEC-001", "The input was rejected. Nothing was stored.",
                       "ERROR", "NONE", "Use a different file or value.")
    if name in ("ApplicationError",):
        return UiError(code if code != "AC-APP-000" else "AC-APP-001",
                       "The operation could not be completed.",
                       "ERROR", "RECOVER", "Check the inputs and try again.")
    if name in ("AdapterError", "PDFError", "StirlingError"):
        return UiError("AC-ADP-001", "An external tool failed. Details were logged.",
                       "ERROR", "RETRY", "Try again; if it persists, check the external tool.")
    if name in ("InfrastructureError", "TooLarge", "BlobNotFound") or "sqlite3" in name.lower():
        return UiError("AC-INF-001", "Storage failed. Details were logged.",
                       "ERROR", "RETRY", "Free disk space and try again.")
    if isinstance(exc, (ValueError,)):
        return UiError(code, "The value is invalid. Check the highlighted field and try again.",
                       "WARNING", "RECOVER", "Correct the highlighted value and retry.")
    return _FALLBACK


def ui_error_for_code(code: str, *, severity: str = "ERROR",
                      action: str = "Check the inputs and try again.") -> UiError:
    """Build a ``UiError`` for replay/status constants without exceptions."""
    messages = {
        "RESULT_DIFFERS": "Replay finished: the result differs from the saved one.",
        "VERSION_MISMATCH": "Replay refused: the saved file targets different engine versions.",
        "SCHEMA_MISMATCH": "Replay refused: unrecognized file format.",
        "INVALID_SERIALIZATION": "Replay refused: the file is invalid.",
        "EQUIVALENT": "Replay finished: identical result.",
    }
    return UiError(code, messages.get(code, "The operation could not be completed."),
                   severity, "RECOVER", action)
