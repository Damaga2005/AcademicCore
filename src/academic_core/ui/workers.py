# SPDX-License-Identifier: MIT
"""F15 Qt workers (F15 §32).

Expensive operations run as: worker (QThreadPool) -> application
service -> result/error -> UI thread. Widgets are NEVER touched from
a worker thread: results cross via Qt signals only.
"""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(object)


class ServiceWorker(QRunnable):
    """Run ``fn(*args, **kwargs)`` off the UI thread (application service)."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:  # noqa: D102 — Qt slot, runs off the UI thread
        try:
            self.signals.finished.emit(self.fn(*self.args, **self.kwargs))
        except Exception as exc:  # D2 boundary: value crosses to UI thread
            exc._f15_trace = traceback.format_exc(limit=3)  # noqa: SLF001
            self.signals.failed.emit(exc)
