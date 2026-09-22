# SPDX-License-Identifier: MIT
"""F8-Q.6 Logic Analyzer view (F15 tab; design §§22-26, 35).

A surface over ``DigitalAnalysisService`` (``app.digital``). It works like
this:

- **Inputs:** the widgets collect plain values into an ``AnalyzerRequest``.
- **Capture:** the service runs it on a ``ServiceWorker`` (F15 QThreadPool
  pattern), and the frozen ``CaptureView`` comes back through Qt signals.
- **Display:** ``WaveformWidget`` draws the view; the transition table
  lists every transition with its exact time.
- **Trace files:** save, load and replay go through the service's
  ``digital-trace/1`` text methods. This file only handles the file
  dialogs.
- **Errors:** everything goes through ``show_ui_error`` (the single D2 UI
  converter).

It contains no gate evaluation, no edge detection, no windowing, no
serialization and no domain imports. Unsupported features (pattern
triggers, sampling, X/Z) have no controls.
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from academic_core.application.digital_service import EDGES, MAX_TRACE_FILE_BYTES, AnalyzerRequest
from academic_core.ui.errors import show_ui_error, show_value
from academic_core.ui.state import UiState
from academic_core.ui.waveform import WaveformWidget
from academic_core.ui.workers import ServiceWorker

NO_TRIGGER = "(none — capture the window)"
COLUMNS = ("#", "time (s)", "channel", "net", "previous", "new", "same-time")
STATUS_TEXT = {
    "TRIGGERED": "TRIGGERED — trigger edge found; window captured around it",
    "NOT_TRIGGERED": "NOT_TRIGGERED — no qualifying edge in the arming window; nothing captured",
    "CAPTURED": "CAPTURED — window captured (no trigger configured)",
    "LOADED": "LOADED — trace opened from file (no circuit was run)",
}


class LogicAnalyzerPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.digital = app.digital
        self.view = None
        self.state = UiState.IDLE
        self.pool = QThreadPool(self)
        layout = QVBoxLayout(self)

        # -- circuit + channels -----------------------------------------------
        top = QHBoxLayout()
        top.addWidget(QLabel("Circuit"))
        self.demo = QComboBox()
        self.demo.setAccessibleName("Circuit")
        self.demo.setToolTip("Digital demo circuit (built fresh by the application service)")
        for info in self.digital.demos():
            self.demo.addItem(info.title, info.key)
            self.demo.setItemData(self.demo.count() - 1, info.description, Qt.ItemDataRole.ToolTipRole)
        top.addWidget(self.demo, 1)
        layout.addLayout(top)

        self.channel_list = QListWidget()
        self.channel_list.setAccessibleName("Channels")
        self.channel_list.setToolTip("Tick the channels (probes) to capture")
        self.channel_list.setMaximumHeight(120)
        layout.addWidget(QLabel("Channels (probe → net, state at start)"))
        layout.addWidget(self.channel_list)

        # -- capture + trigger ------------------------------------------------
        form = QFormLayout()
        self.start = QLineEdit("0")
        self.end = QLineEdit("4")
        self.trigger_channel = QComboBox()
        self.edge = QComboBox()
        self.edge.addItems(EDGES)
        self.pre = QLineEdit("0.5")
        self.post = QLineEdit("1")
        for widget, label, tip in (
                (self.start, "Start / arm from (s)", "Capture window start, or trigger arming start"),
                (self.end, "End / arm until (s)", "Capture window end, or trigger arming end"),
                (self.trigger_channel, "Trigger channel", "Channel whose edge starts the capture"),
                (self.edge, "Trigger edge", "RISING = LOW→HIGH, FALLING = HIGH→LOW, BOTH = either"),
                (self.pre, "Pre-trigger (s)", "Time kept before the trigger"),
                (self.post, "Post-trigger (s)", "Time kept after the trigger")):
            widget.setToolTip(tip)
            widget.setAccessibleName(label)
            form.addRow(label, widget)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.btn_run = QPushButton("&Capture")
        self.btn_run.setToolTip("Run the circuit and capture (real engine)")
        self.btn_verify = QPushButton("&Verify replay")
        self.btn_verify.setToolTip("Capture again, replay through digital-trace/1 and compare")
        self.btn_save = QPushButton("&Save trace…")
        self.btn_save.setToolTip("Save the captured trace as digital-trace/1 JSON")
        self.btn_load = QPushButton("&Load trace…")
        self.btn_load.setToolTip("Open a digital-trace/1 file (no circuit is run)")
        self.btn_replay = QPushButton("&Replay trace")
        self.btn_replay.setToolTip("Replay the shown trace and compare digests")
        for b in (self.btn_run, self.btn_verify, self.btn_save, self.btn_load, self.btn_replay):
            buttons.addWidget(b)
        layout.addLayout(buttons)

        self.status = QLabel("IDLE")
        self.status.setAccessibleName("Capture status")
        self.status.setWordWrap(True)
        self.trigger_info = QLabel("")
        self.trigger_info.setAccessibleName("Trigger details")
        self.trigger_info.setWordWrap(True)
        self.trigger_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        layout.addWidget(self.trigger_info)

        self.waveform = WaveformWidget()
        layout.addWidget(self.waveform, 2)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAccessibleName("Transitions")
        self.table.setToolTip("Every transition with its exact time; same-time transitions are listed "
                              "individually in engine order")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)

        self.demo.currentIndexChanged.connect(self._refresh_channels)
        self.btn_run.clicked.connect(self.start_capture)
        self.btn_verify.clicked.connect(self.verify)
        self.btn_save.clicked.connect(self._save)
        self.btn_load.clicked.connect(self._load)
        self.btn_replay.clicked.connect(self.replay)
        self._refresh_channels()

    # -- channels ---------------------------------------------------------------
    def _refresh_channels(self) -> None:
        self.channel_list.clear()
        self.trigger_channel.clear()
        self.trigger_channel.addItem(NO_TRIGGER, "")
        try:
            infos = self.digital.channels(self.demo.currentData())
        except Exception as exc:
            show_ui_error(self, exc, "Channels")
            return
        for info in infos:
            item = QListWidgetItem(f"{info.channel_id} → net {info.net_id} (start: {info.initial})")
            item.setData(Qt.ItemDataRole.UserRole, info.channel_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.channel_list.addItem(item)
            self.trigger_channel.addItem(info.channel_id, info.channel_id)

    def selected_channels(self) -> tuple[str, ...]:
        out = []
        for k in range(self.channel_list.count()):
            item = self.channel_list.item(k)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return tuple(out)

    def set_channels(self, channels) -> None:
        wanted = set(channels)
        for k in range(self.channel_list.count()):
            item = self.channel_list.item(k)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in wanted
                               else Qt.CheckState.Unchecked)

    # -- capture ----------------------------------------------------------------
    def request(self) -> AnalyzerRequest:
        trigger = self.trigger_channel.currentData() or ""
        return AnalyzerRequest(
            demo=self.demo.currentData(),
            channels=self.selected_channels(),
            start=self.start.text(),
            end=self.end.text(),
            trigger_channel=trigger,
            edge=self.edge.currentText() if trigger else "",
            pre_trigger=self.pre.text() if trigger else "",
            post_trigger=self.post.text() if trigger else "",
        )

    def start_capture(self) -> None:
        try:
            request = self.request()
            self.digital.build_config(request)  # fail fast on the UI thread with a D2 error
        except Exception as exc:
            self._on_error(exc)
            return
        self._set_state(UiState.RUNNING, "RUNNING — capturing…")
        self.btn_run.setEnabled(False)
        worker = ServiceWorker(self.digital.capture, request)
        worker.signals.finished.connect(self.show_view)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def show_view(self, view) -> None:
        """Render a ``CaptureView`` (runs on the UI thread)."""
        self.view = view
        self.btn_run.setEnabled(True)
        self.waveform.set_view(view)
        self._fill_table(view)
        self.status.setText(f"Status: {STATUS_TEXT.get(view.status, view.status)}")
        self.trigger_info.setText(self._trigger_text(view))
        self._set_state(UiState.WARNING if view.status == "NOT_TRIGGERED" else UiState.SUCCESS, None)

    @staticmethod
    def _trigger_text(view) -> str:
        parts = []
        if view.trigger_channel:
            parts.append(f"Trigger: channel {view.trigger_channel}, edge {view.trigger_edge}, "
                         f"pre {view.pre_trigger} s, post {view.post_trigger} s")
        if view.status == "TRIGGERED":
            parts.append(f"Fired: {view.fired_edge} at t = {view.trigger_time} s "
                         f"(transition #{view.trigger_index} of {view.trigger_channel})")
        if view.window is not None:
            parts.append(f"Window: [{view.window[0]}, {view.window[1]}] s")
        if view.requested_window is not None and view.requested_window != view.window:
            parts.append(f"requested [{view.requested_window[0]}, {view.requested_window[1]}] s "
                         "(clipped to the simulated range)")
        if view.digest:
            parts.append(f"digest {view.digest[:16]}…")
        return " · ".join(parts)

    def _fill_table(self, view) -> None:
        rows = view.transitions
        self.table.setRowCount(len(rows))
        for r, t in enumerate(rows):
            same = f"{t.same_time_rank + 1}/{t.same_time_count}" if t.same_time_count > 1 else ""
            values = (str(t.index), t.time, t.channel_id, t.net_id, t.previous, t.new, same)
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def inspect(self, row: int) -> dict:
        """Exact data of one table row (time, channel, net, previous, new)."""
        t = self.view.transitions[row]
        return {"time": t.time, "channel": t.channel_id, "net": t.net_id,
                "previous": t.previous, "new": t.new, "index": t.index,
                "same_time": (t.same_time_rank, t.same_time_count)}

    # -- verification / trace files ------------------------------------------------
    def verify(self) -> None:
        try:
            result = self.digital.verify(self.request())
        except Exception as exc:
            self._on_error(exc)
            return
        from academic_core.errors import ui_error_for_code
        show_value(self, ui_error_for_code(
            result.status, severity="INFO" if result.status == "EQUIVALENT" else "WARNING",
            action="Replay re-runs digital-trace/1 through the engine and compares exactly."), "Verify")
        self.status.setText(f"Verify: {result.status}")

    def trace_text(self) -> str | None:
        return None if self.view is None else self.view.trace_json

    def load_text(self, text: str) -> None:
        try:
            view = self.digital.load_trace(text)
        except Exception as exc:
            self._on_error(exc)
            return
        self.show_view(view)

    def replay(self) -> None:
        text = self.trace_text()
        if not text:
            show_ui_error(self, ValueError("nothing to replay yet"), "Replay")
            return
        try:
            result = self.digital.replay_trace(text)
        except Exception as exc:
            self._on_error(exc)
            return
        self.status.setText(f"Replay: {result.status} (digest {result.digest[:16]}…)")

    def _save(self) -> None:
        text = self.trace_text()
        if not text:
            show_ui_error(self, ValueError("nothing captured to save"), "Save")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save digital trace", "", "Digital trace (*.json)")
        if not path:
            return
        from pathlib import Path
        Path(path).write_text(text + "\n", encoding="utf-8")
        self.status.setText(f"Saved {len(text)} bytes (digital-trace/1)")

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load digital trace", "", "Digital trace (*.json)")
        if not path:
            return
        from pathlib import Path
        try:
            if Path(path).stat().st_size > MAX_TRACE_FILE_BYTES:
                raise ValueError(f"TRACE_LIMIT: file exceeds {MAX_TRACE_FILE_BYTES} bytes")
            data = Path(path).read_bytes()
        except (OSError, ValueError) as exc:
            self._on_error(exc)
            return
        self.load_text(data)

    # -- helpers --------------------------------------------------------------------
    def _on_error(self, exc) -> None:
        self.btn_run.setEnabled(True)
        ui = show_ui_error(self, exc, "Logic Analyzer")
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}: {ui.safe_message}")

    def _set_state(self, state: UiState, text: str | None) -> None:
        self.state = state
        if text is not None:
            self.status.setText(text)
