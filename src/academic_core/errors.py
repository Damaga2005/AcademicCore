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


class TutorError(AcademicCoreError):
    """F12 Socratic tutor pipeline failure (schema/claim/provider)."""
    code = "AC-TUT-001"
    category = "tutor"


# F12 code registry (documented in docs/specs/ERROR-CODES.md).
F12_ERROR_CODES: dict[str, str] = {
    "AC-TUT-001": "invalid LLM output (not parseable JSON)",
    "AC-TUT-002": "schema validation failed",
    "AC-TUT-003": "claim unverified or rejected by the solver",
    "AC-TUT-004": "policy rejected (socratic reveal too early)",
    "AC-TUT-005": "LLM unavailable (LLM=OFF or no provider)",
    "AC-TUT-006": "provider error or timeout",
}


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
    safe_message="No se pudo completar la operación.",
    severity="ERROR",
    recoverability="RECOVER",
    user_action="Revisa los valores resaltados e inténtalo de nuevo.",
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
                           "Este archivo se creó con otra versión y no se puede abrir.",
                           "ERROR", "CONFIG_CHANGE",
                           "Expórtalo de nuevo desde la versión actual o elige un archivo compatible.")
        if "SCHEMA_MISMATCH" in str(exc) or "SCHEMA" in str(exc):
            return UiError(code if code != "AC-APP-000" else "AC-SER-002",
                           "Este archivo tiene un formato desconocido y se rechazó.",
                           "ERROR", "CONFIG_CHANGE",
                           "Elige un archivo exportado por esta aplicación.")
        if any(k in str(exc) for k in ("INVALID_SERIALIZATION", "tamper", "INCONSISTENT")):
            return UiError(code if code != "AC-APP-000" else "AC-SER-001",
                           "El archivo no es válido o está dañado y se rechazó. No se cambió nada.",
                           "ERROR", "NONE",
                           "Elige un archivo exportado válido.")
        if "UNSUPPORTED" in str(exc) or isinstance(exc, UnsupportedError):
            return UiError(code if code != "AC-APP-000" else "AC-UNS-001",
                           "Esta petición no se admite en la versión actual.",
                           "WARNING", "CONFIG_CHANGE",
                           "Cambia la petición a una configuración admitida.")
        return UiError(code, "El valor no es válido. Revisa el campo resaltado e inténtalo de nuevo.",
                       "WARNING", "RECOVER", "Corrige el valor resaltado y vuelve a intentarlo.")
    if name in ("SecurityError",) or "Security" in name:
        return UiError("AC-SEC-001", "Se rechazó la entrada. No se guardó nada.",
                       "ERROR", "NONE", "Usa otro archivo u otro valor.")
    if name in ("ApplicationError",):
        return UiError(code if code != "AC-APP-000" else "AC-APP-001",
                       "No se pudo completar la operación.",
                       "ERROR", "RECOVER", "Revisa los datos e inténtalo de nuevo.")
    if name in ("AdapterError", "PDFError", "StirlingError"):
        return UiError("AC-ADP-001", "Falló una herramienta externa. Los detalles quedaron registrados.",
                       "ERROR", "RETRY", "Inténtalo de nuevo; si persiste, revisa la herramienta externa.")
    if name in ("InfrastructureError", "TooLarge", "BlobNotFound") or "sqlite3" in name.lower():
        return UiError("AC-INF-001", "Falló el almacenamiento. Los detalles quedaron registrados.",
                       "ERROR", "RETRY", "Libera espacio en disco e inténtalo de nuevo.")
    if isinstance(exc, (ValueError,)):
        return UiError(code, "El valor no es válido. Revisa el campo resaltado e inténtalo de nuevo.",
                       "WARNING", "RECOVER", "Corrige el valor resaltado y vuelve a intentarlo.")
    return _FALLBACK


def ui_error_for_code(code: str, *, severity: str = "ERROR",
                      action: str = "Revisa los datos e inténtalo de nuevo.") -> UiError:
    """Build a ``UiError`` for replay/status constants without exceptions."""
    messages = {
        "RESULT_DIFFERS": "Repetición terminada: el resultado difiere del guardado.",
        "VERSION_MISMATCH": "Repetición rechazada: el archivo guardado es de otras versiones del motor.",
        "SCHEMA_MISMATCH": "Repetición rechazada: formato de archivo desconocido.",
        "INVALID_SERIALIZATION": "Repetición rechazada: el archivo no es válido.",
        "EQUIVALENT": "Repetición terminada: resultado idéntico.",
    }
    return UiError(code, messages.get(code, "No se pudo completar la operación."),
                   severity, "RECOVER", action)
