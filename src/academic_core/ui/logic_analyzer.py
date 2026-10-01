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

E0.1: selecting a transition row shows its explanation: time, channel,
previous and new state, driver, why it changed, and the checks. The text
comes from ONE pedagogical capture trace per capture
(``app.explain.capture_trace(request, pedagogical=True, delta=True)``,
run on a worker and cached; E0.1-R+ delta-level causality). ``explain_service.transition_explanation`` extracts
the recorded events. A loaded trace file has no circuit, so no cause is
shown for it.
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from academic_core.application.digital_service import EDGES, MAX_TRACE_FILE_BYTES, AnalyzerRequest
from academic_core.application.explain_service import transition_explanation
from academic_core.ui.errors import show_ui_error, show_value
from academic_core.ui.state import UiState
from academic_core.ui.theme import apply_status_style
from academic_core.ui.waveform import WaveformWidget
from academic_core.ui.workers import ServiceWorker

NO_TRIGGER = "(ninguno — capturar la ventana)"
SHORT_LABEL = {"Inicio / armar desde (s)": "Desde (s)", "Fin / armar hasta (s)": "Hasta (s)",
               "Canal de disparo": "Canal", "Flanco de disparo": "Flanco",
               "Pre-disparo (s)": "Pre (s)", "Post-disparo (s)": "Post (s)"}
COLUMNS = ("#", "tiempo (s)", "canal", "nodo", "anterior", "nuevo", "simultánea")
STATUS_TEXT = {
    "TRIGGERED": "TRIGGERED — se encontró el flanco de disparo; ventana capturada a su alrededor",
    "NOT_TRIGGERED": "NOT_TRIGGERED — ningún flanco válido en la ventana de armado; no se capturó nada",
    "CAPTURED": "CAPTURED — ventana capturada (sin disparo configurado)",
    "LOADED": "LOADED — traza abierta desde archivo (no se ejecutó ningún circuito)",
}


class LogicAnalyzerPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.digital = app.digital
        self.view = None
        self.state = UiState.IDLE
        self.pool = QThreadPool(self)
        from PySide6.QtWidgets import QSplitter
        from academic_core.ui.workspace import Panel
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # -- tools: circuit + capture actions ----------------------------------------
        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(QLabel("Circuito"))
        self.demo = QComboBox()
        self.demo.setAccessibleName("Circuito")
        self.demo.setToolTip("Circuito digital de ejemplo (construido de nuevo por el servicio de aplicación)")
        self._fill_demos()
        tools.addWidget(self.demo, 1)
        self.btn_run = QPushButton("&Capturar")
        self.btn_run.setProperty("class", "primary")
        self.btn_run.setToolTip("Ejecuta el circuito y captura (motor real)")
        self.btn_verify = QPushButton("&Verificar repetición")
        self.btn_verify.setToolTip("Captura de nuevo, repite con digital-trace/1 y compara")
        self.btn_save = QPushButton("&Guardar traza…")
        self.btn_save.setToolTip("Guarda la traza capturada como JSON digital-trace/1")
        self.btn_load = QPushButton("&Cargar traza…")
        self.btn_load.setToolTip("Abre un archivo digital-trace/1 (no se ejecuta ningún circuito)")
        self.btn_replay = QPushButton("&Repetir traza")
        self.btn_replay.setToolTip("Repite la traza mostrada y compara digests")
        for b in (self.btn_run, self.btn_verify, self.btn_save, self.btn_load, self.btn_replay):
            tools.addWidget(b)
        layout.addLayout(tools)

        self.context_label = QLabel("")  # what the selected circuit is (from the service)
        self.context_label.setObjectName("CardStatus")
        self.context_label.setWordWrap(True)
        layout.addWidget(self.context_label)
        self.status = QLabel("EN ESPERA")
        self.status.setAccessibleName("Estado de la captura")
        apply_status_style(self.status, UiState.IDLE)
        self.status.setWordWrap(True)
        layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignLeft)  # a pill like the other labs, not a full-width band

        # -- setup (inputs): channels, capture window, trigger --------------------------
        setup = Panel("Configuración")
        channels_label = QLabel("Canales (sonda → nodo, estado inicial)")
        channels_label.setProperty("role", "key")
        setup.add(channels_label)
        self.channel_list = QListWidget()
        self.channel_list.setAccessibleName("Canales")
        self.channel_list.setToolTip("Marca los canales (sondas) que capturar")
        self.channel_list.setMaximumHeight(160)
        setup.add(self.channel_list)
        self.start = QLineEdit("0")
        self.end = QLineEdit("4")
        self.trigger_channel = QComboBox()
        self.edge = QComboBox()
        self.edge.addItems(EDGES)
        self.pre = QLineEdit("0.5")
        self.post = QLineEdit("1")
        window_form, trigger_form = QFormLayout(), QFormLayout()
        for f in (window_form, trigger_form):
            f.setVerticalSpacing(8)
        for form, widget, label, tip in (
                (window_form, self.start, "Inicio / armar desde (s)", "Inicio de la ventana de captura o del armado del disparo"),
                (window_form, self.end, "Fin / armar hasta (s)", "Fin de la ventana de captura o del armado del disparo"),
                (trigger_form, self.trigger_channel, "Canal de disparo", "Canal cuyo flanco inicia la captura"),
                (trigger_form, self.edge, "Flanco de disparo", "RISING = BAJO→ALTO, FALLING = ALTO→BAJO, BOTH = cualquiera"),
                (trigger_form, self.pre, "Pre-disparo (s)", "Tiempo que se conserva antes del disparo"),
                (trigger_form, self.post, "Post-disparo (s)", "Tiempo que se conserva después del disparo")):
            widget.setToolTip(tip)
            widget.setAccessibleName(label)
            form.addRow(SHORT_LABEL.get(label, label), widget)
        for title, form in (("Ventana de captura", window_form), ("Disparo", trigger_form)):
            head = QLabel(title)
            head.setObjectName("PanelTitle")
            setup.add(head)
            setup.body.addLayout(form)
        setup.body.addStretch(1)

        # -- visualization + instruments: waveform and trigger readout ------------------
        wave = Panel("Forma de onda")
        self.trigger_info = QLabel("")
        self.trigger_info.setAccessibleName("Detalles del disparo")
        self.trigger_info.setWordWrap(True)
        self.trigger_info.setObjectName("CardStatus")
        self.trigger_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        wave.add(self.trigger_info)
        self.waveform = WaveformWidget()
        wave.add(self.waveform, 1)

        # -- results: transitions and their explanation --------------------------------
        transitions = Panel("Transiciones")
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAccessibleName("Transiciones")
        self.table.setToolTip("Cada transición con su tiempo exacto; las simultáneas se listan "
                              "una a una en el orden del motor")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        transitions.add(self.table, 1)
        why = Panel("Por qué cambió")
        self.explanation = QTextEdit(readOnly=True)
        self.explanation.setAccessibleName("Explicación de la transición")
        self.explanation.setToolTip("Por qué cambió la transición seleccionada (de la traza de ejecución real)")
        self.explanation.setPlaceholderText("Elige una transición de la tabla.")
        why.add(self.explanation, 1)

        results = QSplitter(Qt.Orientation.Horizontal)
        results.setChildrenCollapsible(False)
        results.addWidget(transitions)
        results.addWidget(why)
        results.setStretchFactor(0, 3)
        results.setStretchFactor(1, 2)
        results.setSizes([620, 380])  # the table has six columns; the explanation reads fine narrower
        right = QSplitter(Qt.Orientation.Vertical)
        right.setChildrenCollapsible(False)
        right.addWidget(wave)
        right.addWidget(results)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 2)
        right.setSizes([360, 280])
        transitions.setMinimumHeight(190)
        why.setMinimumHeight(190)
        main = QSplitter(Qt.Orientation.Horizontal)
        main.setChildrenCollapsible(False)
        main.addWidget(setup)
        main.addWidget(right)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setSizes([340, 800])
        setup.setMinimumWidth(300)
        self.workspace = main
        from PySide6.QtWidgets import QTabWidget
        from academic_core.ui.digital_editor import DigitalEditorPage
        self.editor = DigitalEditorPage(self.digital)
        self.editor.applied.connect(self._design_applied)
        self.tabs = QTabWidget()
        self.tabs.addTab(main, "Captura")
        self.tabs.addTab(self.editor, "Editor de circuito")
        layout.addWidget(self.tabs, 1)
        self._request = None  # request of the shown capture (None for a loaded file)
        self._trace = None  # cached pedagogical ExecutionTrace of that capture
        self._pending_row = None

        self.demo.currentIndexChanged.connect(self._refresh_channels)
        self.btn_run.clicked.connect(self.start_capture)
        self.btn_verify.clicked.connect(self.verify)
        self.btn_save.clicked.connect(self._save)
        self.btn_load.clicked.connect(self._load)
        self.btn_replay.clicked.connect(self.replay)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self._refresh_channels()

    def _fill_demos(self) -> None:
        self.demo.blockSignals(True)
        self.demo.clear()
        for info in self.digital.demos():
            self.demo.addItem(info.title, info.key)
            self.demo.setItemData(self.demo.count() - 1, info.description, Qt.ItemDataRole.ToolTipRole)
        self.demo.blockSignals(False)

    def _design_applied(self, key: str) -> None:
        self._fill_demos()
        self.demo.setCurrentIndex(self.demo.findData(key))
        self._refresh_channels()
        self.tabs.setCurrentIndex(0)

    # -- channels ---------------------------------------------------------------
    def _refresh_channels(self) -> None:
        self.context_label.setText(
            str(self.demo.itemData(self.demo.currentIndex(), Qt.ItemDataRole.ToolTipRole) or ""))
        self.channel_list.clear()
        self.trigger_channel.clear()
        self.trigger_channel.addItem(NO_TRIGGER, "")
        try:
            infos = self.digital.channels(self.demo.currentData())
        except Exception as exc:
            show_ui_error(self, exc, "Canales")
            return
        for info in infos:
            item = QListWidgetItem(f"{info.channel_id} → nodo {info.net_id} (inicio: {info.initial})")
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
        self._set_state(UiState.RUNNING, "EJECUTANDO — capturando…")
        self.btn_run.setEnabled(False)
        self._request, self._trace = request, None
        worker = ServiceWorker(self.digital.capture, request)
        worker.signals.finished.connect(self.show_view)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def show_view(self, view) -> None:
        """Render a ``CaptureView`` (runs on the UI thread)."""
        self.view = view
        self.explanation.clear()
        self.btn_run.setEnabled(True)
        self.waveform.set_view(view)
        self._fill_table(view)
        self.status.setText(f"Estado: {STATUS_TEXT.get(view.status, view.status)}")
        self.trigger_info.setText(self._trigger_text(view))
        self._set_state(UiState.WARNING if view.status == "NOT_TRIGGERED" else UiState.SUCCESS, None)

    @staticmethod
    def _trigger_text(view) -> str:
        parts = []
        if view.trigger_channel:
            parts.append(f"Disparo: canal {view.trigger_channel}, flanco {view.trigger_edge}, "
                         f"pre {view.pre_trigger} s, post {view.post_trigger} s")
        if view.status == "TRIGGERED":
            parts.append(f"Disparó: {view.fired_edge} en t = {view.trigger_time} s "
                         f"(transición #{view.trigger_index} de {view.trigger_channel})")
        if view.window is not None:
            parts.append(f"Ventana: [{view.window[0]}, {view.window[1]}] s")
        if view.requested_window is not None and view.requested_window != view.window:
            parts.append(f"pedida [{view.requested_window[0]}, {view.requested_window[1]}] s "
                         "(recortada al rango simulado)")
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
            action="La repetición vuelve a ejecutar digital-trace/1 en el motor y compara de forma exacta."), "Verificar")
        self.status.setText(f"Verificación: {result.status}")

    def trace_text(self) -> str | None:
        return None if self.view is None else self.view.trace_json

    def load_text(self, text: str) -> None:
        try:
            view = self.digital.load_trace(text)
        except Exception as exc:
            self._on_error(exc)
            return
        self._request, self._trace = None, None
        self.show_view(view)

    # -- E0.1 transition explanation -------------------------------------------------
    def _on_selection(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if rows and self.view is not None:
            self.explain_row(rows[0])

    def explain_row(self, row: int) -> None:
        """Explain one table row from the pedagogical trace of the shown capture."""
        if self.view is None or not 0 <= row < len(self.view.transitions):
            return
        if self._request is None:
            self.explanation.setPlainText("Traza cargada desde archivo: no hay circuito asociado, así que la causa "
                                          "de la transición no se puede explicar sin inventarla.")
            return
        if self._trace is None:
            self._pending_row = row
            self.explanation.setPlainText("Explicando… (ejecutando la captura en modo pedagógico)")
            worker = ServiceWorker(self.app.explain.capture_trace, self._request, True, True)
            worker.signals.finished.connect(self._on_trace)
            worker.signals.failed.connect(self._on_error)
            self.pool.start(worker)
            return
        t = self.view.transitions[row]
        self.explanation.setPlainText(self.transition_text(transition_explanation(self._trace, t.channel_id, t.index)))

    def _on_trace(self, trace) -> None:
        self._trace = trace
        if self._pending_row is not None:
            row, self._pending_row = self._pending_row, None
            self.explain_row(row)

    @staticmethod
    def transition_text(x) -> str:
        lines = [f"Tiempo: {x.time or '—'} s", f"Canal: {x.channel} (transición #{x.index})",
                 f"Anterior: {x.previous or '—'}", f"Nuevo: {x.new or '—'}", f"Driver: {x.driver or '—'}",
                 f"Por qué cambió: {x.why}"]
        if x.cause:
            lines.append(f"Causa registrada: {x.cause}")
        lines.append("Comprobaciones: " + ("; ".join(x.checks) if x.checks else "—"))
        lines.append(f"Eventos de la traza: {', '.join(x.event_ids) or '—'}")
        return "\n".join(lines)

    def replay(self) -> None:
        text = self.trace_text()
        if not text:
            show_ui_error(self, ValueError("aún no hay nada que repetir"), "Repetir")
            return
        try:
            result = self.digital.replay_trace(text)
        except Exception as exc:
            self._on_error(exc)
            return
        self.status.setText(f"Repetición: {result.status} (digest {result.digest[:16]}…)")

    def _save(self) -> None:
        text = self.trace_text()
        if not text:
            show_ui_error(self, ValueError("no hay nada capturado que guardar"), "Guardar")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar traza digital", "", "Traza digital (*.json)")
        if not path:
            return
        from pathlib import Path
        Path(path).write_text(text + "\n", encoding="utf-8")
        self.status.setText(f"Guardados {len(text)} bytes (digital-trace/1)")

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Cargar traza digital", "", "Traza digital (*.json)")
        if not path:
            return
        from pathlib import Path
        try:
            if Path(path).stat().st_size > MAX_TRACE_FILE_BYTES:
                raise ValueError(f"TRACE_LIMIT: el archivo supera {MAX_TRACE_FILE_BYTES} bytes")
            data = Path(path).read_bytes()
        except (OSError, ValueError) as exc:
            self._on_error(exc)
            return
        self.load_text(data)

    # -- helpers --------------------------------------------------------------------
    def _on_error(self, exc) -> None:
        self.btn_run.setEnabled(True)
        ui = show_ui_error(self, exc, "Analizador lógico")
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}: {ui.safe_message}")

    def _set_state(self, state: UiState, text: str | None) -> None:
        self.state = state
        if text is not None:
            self.status.setText(text)
        apply_status_style(self.status, state)
