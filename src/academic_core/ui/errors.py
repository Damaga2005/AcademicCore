# SPDX-License-Identifier: MIT
"""F15 UI error presentation (D2 §14).

Exactly ONE place converts exceptions to user-visible dialogs. Every
widget calls :func:`show_ui_error`, which converts via
``errors.to_ui_error`` and presents ONLY the safe fields. No widget
invents its own mapping; raw ``str(exc)`` never reaches the user.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from academic_core.errors import UiError, to_ui_error


def show_ui_error(parent: QWidget | None, exc: BaseException,
                  title: str = "Error") -> UiError:
    """Present ``exc`` as a UI-safe dialog; return the ``UiError`` value."""
    ui = to_ui_error(exc)
    show_value(parent, ui, title)
    return ui


def show_value(parent: QWidget | None, ui: UiError,
               title: str = "Error") -> None:
    """Present an already-built ``UiError`` value (no exception needed)."""
    body = ui.safe_message
    if ui.user_action:
        body += f"\n\n{ui.user_action}"
    if ui.severity == "WARNING":
        QMessageBox.warning(parent, title, body)
    elif ui.severity == "INFO":
        QMessageBox.information(parent, title, body)
    else:
        QMessageBox.critical(parent, title, body)
