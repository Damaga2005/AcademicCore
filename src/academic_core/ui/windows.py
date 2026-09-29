# SPDX-License-Identifier: MIT
"""Windows desktop integration (UX 2026, prompt 11): identity, sizing, one window per user.

Nothing here touches the core or the data layout. Every function degrades to a no-op off Windows.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket

APP_USER_MODEL_ID = "AcademicCore.Desktop"


def set_app_user_model_id() -> None:
    """Own taskbar identity (icon, grouping, pinning) instead of the Python host's."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def app_icon() -> QIcon:
    """The product icon, from the bundle or the source tree alike (same resource path)."""
    from academic_core import runtime
    return QIcon(str(runtime.resource_path("resources", "academicore.ico")))


def fit_to_screen(win, width: int = 1250, height: int = 780, min_w: int = 900, min_h: int = 600) -> None:
    """Size the window for the screen it opens on.

    At 200 % on a 1080p display the usable area is ~960x520 logical pixels, smaller than the
    designed minimum; a window taller than the screen has unreachable controls. Pages scroll, so
    the minimum simply yields to the screen.
    """
    screen = win.screen() or QGuiApplication.primaryScreen()
    area = screen.availableGeometry() if screen is not None else None
    if area is None:
        win.setMinimumSize(min_w, min_h)
        win.resize(width, height)
        return
    win.setMinimumSize(min(min_w, area.width()), min(min_h, area.height()))
    win.resize(min(width, area.width()), min(height, area.height()))


class SingleInstance(QObject):
    """One AcademicCore per user: a second launch wakes the first and exits.

    Two processes on one SQLite database is a data risk, and Windows users expect the existing
    window to come forward. ``claim()`` is True for the first process.
    """

    activated = Signal()

    def __init__(self, key: str = "AcademicCore-instance", parent=None):
        super().__init__(parent)
        self.key = key
        self._server: QLocalServer | None = None

    def claim(self) -> bool:
        probe = QLocalSocket()
        probe.connectToServer(self.key)
        if probe.waitForConnected(300):  # somebody is already listening
            probe.write(b"show")
            probe.flush()
            probe.waitForBytesWritten(300)
            probe.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.key)  # a crashed run leaves a stale endpoint behind
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._wake)
        return self._server.listen(self.key)

    def _wake(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        self.activated.emit()

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None


def bring_to_front(win) -> None:
    """Restore from minimized and raise; the Windows foreground rules may only flash the taskbar."""
    if win.isMinimized():
        win.showNormal()
    win.show()
    win.raise_()
    win.activateWindow()
