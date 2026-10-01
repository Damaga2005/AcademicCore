# SPDX-License-Identifier: MIT
"""Shared laboratory workspace (UX 2026, prompt 7).

Every lab uses one skeleton: Experiment -> Setup -> (toolbar) -> Visualization
-> Instruments -> Results. ``LabKit`` builds it; ``RunPresenter`` turns a real
``LabRunSummary`` into a plot, instrument readouts, a measurement table and a
run header. Presentation only: values come from the engine; nothing here
computes physics, and a run without plottable data says so.
"""

from __future__ import annotations

import math
from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from academic_core.ui.workspace import (
    EmptyState, KeyValueList, Metric, Notice, Panel, VerificationCard,
)

LEFT_WIDTH = 340


def fmt(value, sig: int = 6) -> str:
    """Readable number: ``sig`` significant digits (full value stays in tooltips)."""
    try:
        text = format(Decimal(value), f".{sig}g")
    except Exception:
        return str(value)
    if "E" not in text and "." in text:
        text = text.rstrip("0").rstrip(".")  # 2.5000 -> 2.5
    return text


def nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    """Round tick values covering [lo, hi]."""
    if not (hi > lo):
        return [lo]
    raw = (hi - lo) / target
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if raw <= m * mag)
    tick = math.ceil(lo / step) * step
    out = []
    while tick <= hi + step * 1e-9:
        out.append(round(tick, 12))
        tick += step
    return out


def freq_label(f: float, sig: int = 3) -> str:
    """10, 100, 1k, 10k, 1.59k, 1M: a frequency as an engineer writes it."""
    for scale, suffix in ((1e6, "M"), (1e3, "k")):
        if abs(f) >= scale:
            return f"{f / scale:.{sig}g}{suffix}"
    return f"{f:.{sig}g}"


def log_ticks(lo: float, hi: float) -> list[float]:
    return [10.0 ** k for k in range(math.ceil(math.log10(lo)), math.floor(math.log10(hi)) + 1)]


class PlotView(QWidget):
    """Line plot of real series. Floats are for painting only."""

    ML, MR, MT, MB = 56, 16, 30, 34

    def __init__(self, title: str = "", x_label: str = "", y_label: str = "",
                 x_log: bool = False, parent=None):
        super().__init__(parent)
        self.title, self.x_label, self.y_label, self.x_log = title, x_label, y_label, x_log
        self.series: list[tuple[str, list[float], list[float]]] = []
        self.setMinimumHeight(170)
        self.setAccessibleName(title or "Gráfico")

    def set_series(self, series) -> None:
        """``[(label, xs, ys)]`` with finite floats; other points are dropped."""
        clean = []
        for label, xs, ys in series:
            pts = [(float(x), float(y)) for x, y in zip(xs, ys)
                   if x is not None and y is not None and (not self.x_log or float(x) > 0)]
            if pts:
                clean.append((label, [p[0] for p in pts], [p[1] for p in pts]))
        self.series = clean
        if clean:
            xs_all = [x for _, xs, _ in clean for x in xs]
            ys_all = [y for _, _, ys in clean for y in ys]
            self.setAccessibleDescription(
                f"{sum(len(xs) for _, xs, _ in clean)} puntos; x {min(xs_all):.4g} a {max(xs_all):.4g}"
                f" {self.x_label}; y {min(ys_all):.4g} a {max(ys_all):.4g} {self.y_label}")
        else:
            self.setAccessibleDescription("Sin datos")
        self.update()

    def _range(self, values, log: bool = False):
        lo, hi = min(values), max(values)
        if log:
            lo, hi = math.log10(lo), math.log10(hi)
        if hi - lo < 1e-15:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.06
        return lo - pad, hi + pad

    def paintEvent(self, _event) -> None:  # noqa: N802 — Qt override
        from academic_core.ui.theme import current_tokens
        tk = current_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        head = f"{self.title} ({self.y_label})" if self.title and self.y_label else self.title
        bold = QFont(p.font())
        bold.setBold(True)
        p.setFont(bold)
        p.setPen(QColor(tk.ink))
        p.drawText(QRectF(0, 0, w, self.MT - 6), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), head)
        p.setFont(QFont(bold.family(), max(bold.pointSize() - 1, 7)))
        plot = QRectF(self.ML, self.MT, w - self.ML - self.MR, h - self.MT - self.MB)
        if not self.series or plot.width() < 40 or plot.height() < 40:
            p.setPen(QColor(tk.secondary))
            p.drawText(plot, int(Qt.AlignmentFlag.AlignCenter), "Sin datos")
            p.end()
            return
        x_lo, x_hi = self._range([x for _, xs, _ in self.series for x in xs], self.x_log)
        y_lo, y_hi = self._range([y for _, _, ys in self.series for y in ys])

        def sx(x: float) -> float:
            v = math.log10(x) if self.x_log else x
            return plot.left() + (v - x_lo) / (x_hi - x_lo) * plot.width()

        def sy(y: float) -> float:
            return plot.bottom() - (y - y_lo) / (y_hi - y_lo) * plot.height()

        grid = QPen(QColor(tk.hairline), 1)
        p.setPen(grid)
        p.drawRect(plot)
        y_ticks = nice_ticks(y_lo, y_hi)
        x_ticks = (log_ticks(10 ** x_lo, 10 ** x_hi) if self.x_log else nice_ticks(x_lo, x_hi))
        for t in y_ticks:
            y = sy(t)
            p.setPen(grid)
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(tk.secondary))
            p.drawText(QRectF(0, y - 9, self.ML - 6, 18),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), f"{t:.4g}")
        for t in x_ticks:
            x = sx(t)
            p.setPen(grid)
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            p.setPen(QColor(tk.secondary))
            p.drawText(QRectF(x - 34, plot.bottom() + 4, 68, 16), int(Qt.AlignmentFlag.AlignCenter),
                       freq_label(t) if self.x_log else f"{t:.4g}")
        p.setPen(QColor(tk.secondary))
        p.drawText(QRectF(plot.left(), h - 16, plot.width(), 16), int(Qt.AlignmentFlag.AlignCenter), self.x_label)
        p.save()
        p.setClipRect(plot)
        for i, (_, xs, ys) in enumerate(self.series):
            pen = QPen(QColor(tk.series[i % len(tk.series)]), 2)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(QPolygonF([QPointF(sx(x), sy(y)) for x, y in zip(xs, ys)]))
        p.restore()
        if len(self.series) > 1:  # direct labels: name next to its colour, never colour alone
            x = plot.right() - 8
            for i, (label, _, _) in reversed(list(enumerate(self.series))):
                p.setPen(QColor(tk.series[i % len(tk.series)]))
                p.drawText(QRectF(plot.left(), plot.top() + 4 + 16 * i, plot.width() - 10, 16),
                           int(Qt.AlignmentFlag.AlignRight), f"— {label}")
        p.end()


class BodePlotView(QWidget):
    """Gain (dB, left axis) and phase (degrees, right axis) of one sweep in a single plot.

    Hover shows a cursor with the exact frequency, gain and phase of the nearest solved point.
    Floats are for painting only; the points come from the engine.
    """

    ML, MR, MT, MB = 56, 56, 30, 34
    x_log = True

    def __init__(self, title: str = "Bode", parent=None):
        super().__init__(parent)
        self.title = title
        self.freqs: list[float] = []
        self.db: list[float | None] = []
        self.phase: list[float | None] = []
        self._hover: int | None = None
        self.series: list = []  # (label, xs, ys) per trace, for tests and the accessible description
        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.setAccessibleName(title)

    def set_data(self, freqs, db, phase_deg) -> None:
        rows = [(float(f), None if g is None else float(g), None if ph is None else float(ph))
                for f, g, ph in zip(freqs, db, phase_deg) if f is not None and float(f) > 0]
        self.freqs = [r[0] for r in rows]
        self.db = [r[1] for r in rows]
        self.phase = [r[2] for r in rows]
        g = [(f, v) for f, v, _ in rows if v is not None]
        ph = [(f, v) for f, _, v in rows if v is not None]
        self.series = [("Ganancia", [a for a, _ in g], [b for _, b in g]),
                       ("Fase", [a for a, _ in ph], [b for _, b in ph])]
        self._hover = None
        if g:
            self.setAccessibleDescription(
                f"{len(rows)} puntos de {freq_label(self.freqs[0])} Hz a {freq_label(self.freqs[-1])} Hz; "
                f"ganancia de {min(v for _, v in g):.4g} a {max(v for _, v in g):.4g} dB")
        else:
            self.setAccessibleDescription("Sin datos")
        self.update()

    # -- geometry -------------------------------------------------------------------------
    def _plot_rect(self) -> QRectF:
        return QRectF(self.ML, self.MT, self.width() - self.ML - self.MR, self.height() - self.MT - self.MB)

    @staticmethod
    def _span(values):
        lo, hi = min(values), max(values)
        if hi - lo < 1e-12:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.06
        return lo - pad, hi + pad

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        rect = self._plot_rect()
        if not self.freqs or not rect.contains(event.position()):
            self._hover = None
        else:
            lo, hi = self._span([math.log10(f) for f in self.freqs])
            fx = lo + (event.position().x() - rect.left()) / rect.width() * (hi - lo)
            self._hover = min(range(len(self.freqs)), key=lambda i: abs(math.log10(self.freqs[i]) - fx))
        self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802 - Qt override
        self._hover = None
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        from academic_core.ui.theme import current_tokens
        tk = current_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bold = QFont(p.font())
        bold.setBold(True)
        small = QFont(bold.family(), max(bold.pointSize() - 1, 7))
        c_gain, c_phase = QColor(tk.series[0]), QColor(tk.series[1])
        p.setFont(bold)
        p.setPen(QColor(tk.ink))
        p.drawText(QRectF(0, 0, w, self.MT - 6), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   self.title)
        p.setFont(small)
        rect = self._plot_rect()
        if not self.freqs or not any(v is not None for v in self.db) or rect.width() < 60 or rect.height() < 60:
            p.setPen(QColor(tk.secondary))
            p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "Sin datos")
            p.end()
            return
        x_lo, x_hi = self._span([math.log10(f) for f in self.freqs])
        g_lo, g_hi = self._span([v for v in self.db if v is not None])
        ph_vals = [v for v in self.phase if v is not None]
        p_lo, p_hi = self._span(ph_vals) if ph_vals else (-1.0, 1.0)

        def sx(f: float) -> float:
            return rect.left() + (math.log10(f) - x_lo) / (x_hi - x_lo) * rect.width()

        def sg(v: float) -> float:
            return rect.bottom() - (v - g_lo) / (g_hi - g_lo) * rect.height()

        def sp(v: float) -> float:
            return rect.bottom() - (v - p_lo) / (p_hi - p_lo) * rect.height()

        grid = QPen(QColor(tk.hairline), 1)
        p.setPen(grid)
        p.drawRect(rect)
        for t in nice_ticks(g_lo, g_hi):  # gain grid and left labels
            y = sg(t)
            p.setPen(grid)
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(c_gain)
            p.drawText(QRectF(0, y - 9, self.ML - 6, 18),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), f"{t:.4g}")
        if ph_vals:
            for t in nice_ticks(p_lo, p_hi):  # phase labels on the right
                p.setPen(c_phase)
                p.drawText(QRectF(rect.right() + 6, sp(t) - 9, self.MR - 6, 18),
                           int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), f"{t:.4g}")
        for t in log_ticks(10 ** x_lo, 10 ** x_hi):
            x = sx(t)
            p.setPen(grid)
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            p.setPen(QColor(tk.secondary))
            p.drawText(QRectF(x - 34, rect.bottom() + 4, 68, 16), int(Qt.AlignmentFlag.AlignCenter), freq_label(t))
        p.setPen(QColor(tk.secondary))
        p.drawText(QRectF(rect.left(), h - 16, rect.width(), 16), int(Qt.AlignmentFlag.AlignCenter), "Frecuencia (Hz)")
        p.save()
        p.setClipRect(rect)
        for values, scale, colour in ((self.db, sg, c_gain), (self.phase, sp, c_phase)):
            pen = QPen(colour, 2)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            pts = [QPointF(sx(f), scale(v)) for f, v in zip(self.freqs, values) if v is not None]
            if len(pts) > 1:
                p.drawPolyline(QPolygonF(pts))
        p.restore()
        # direct labels, never colour alone
        p.setPen(c_gain)
        p.drawText(QRectF(rect.right() - 208, rect.top() + 4, 200, 16), int(Qt.AlignmentFlag.AlignRight), "Ganancia (dB) \u2014")
        p.setPen(c_phase)
        p.drawText(QRectF(rect.right() - 208, rect.top() + 20, 200, 16), int(Qt.AlignmentFlag.AlignRight), "Fase (\u00b0) \u2014")
        if self._hover is not None:
            i = self._hover
            x = sx(self.freqs[i])
            p.setPen(QPen(QColor(tk.ink), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            for values, scale, colour in ((self.db, sg, c_gain), (self.phase, sp, c_phase)):
                if values[i] is not None:
                    p.setPen(QPen(colour, 2))
                    p.setBrush(QColor(tk.card))
                    p.drawEllipse(QPointF(x, scale(values[i])), 4, 4)
            parts = [f"f = {freq_label(self.freqs[i], 4)} Hz"]
            if self.db[i] is not None:
                parts.append(f"{self.db[i]:.4g} dB")
            if self.phase[i] is not None:
                parts.append(f"{self.phase[i]:.4g}\u00b0")
            text = "  \u00b7  ".join(parts)
            box_w = p.fontMetrics().horizontalAdvance(text) + 16
            bx = min(max(x + 10, rect.left()), rect.right() - box_w)
            box = QRectF(bx, rect.bottom() - 26, box_w, 20)
            p.setPen(QPen(QColor(tk.hairline), 1))
            p.setBrush(QColor(tk.card))
            p.drawRoundedRect(box, 4, 4)
            p.setPen(QColor(tk.ink))
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)
        p.end()


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class RunPresenter:
    """Fills visualization, instruments and results from one ``LabRunSummary``."""

    MEASURE_COLUMNS = ("Medida", "Valor", "Unidad", "Estado")

    def __init__(self, viz: Panel, instruments: Panel, header: KeyValueList,
                 verification: VerificationCard | None = None):
        self.viz, self.instruments, self.header = viz, instruments, header
        self.verification = verification
        self.run_action: tuple[str, object] | None = None  # (label, callback) shown while no run exists
        self.plots: list[PlotView] = []
        self.metrics: list[Metric] = []
        self.measure_table: QTableWidget | None = None
        self.clear()

    def clear(self, viz_text=("Aún sin ejecución", "Configura el experimento y ejecútalo."),
              inst_text=("Aún sin lecturas", "Los instrumentos y las medidas aparecen tras una ejecución.")) -> None:
        _clear(self.viz.body)
        _clear(self.instruments.body)
        self.plots, self.metrics, self.measure_table = [], [], None
        empty = EmptyState(*viz_text)
        if self.run_action and viz_text[0] == "Aún sin ejecución":
            empty.set_action(*self.run_action)
        self.viz.body.addWidget(empty)
        self.instruments.body.addWidget(EmptyState(*inst_text))
        self.header.set_rows([])
        if self.verification is not None:
            self.verification.clear()

    # -- one run ------------------------------------------------------------------------
    def show_run(self, summary) -> None:
        _clear(self.viz.body)
        _clear(self.instruments.body)
        self.plots, self.metrics, self.measure_table = [], [], None
        self.header.set_rows([("Ejecución", summary.run_id), ("Estado", summary.status),
                              ("Motor", summary.engine_status or "—"),
                              ("Digest", summary.result_digest[:16] + "…")])
        self.header.setToolTip(f"Digest del resultado {summary.result_digest}")
        if self.verification is not None:
            self.verification.show_conservation(getattr(summary, "conservation", None))
            self.verification.show_oracle(getattr(summary, "oracle", None))
        for reading in summary.readings:
            self._reading(reading)
        self._measurements(summary.measurements)
        if not self.plots:
            self.viz.body.addWidget(EmptyState("Nada que dibujar", "Esta ejecución no produjo forma de onda ni barrido."))
        if not self.metrics and not summary.measurements:
            self.instruments.body.addWidget(EmptyState("Sin lecturas", "No se pidió ningún instrumento ni medida."))

    def _add_plot(self, plot: PlotView) -> None:
        self.plots.append(plot)
        self.viz.body.addWidget(plot, 1)

    def _reading(self, r) -> None:
        data = r.data
        kind = type(data).__name__
        if r.status != "OK" or data is None:
            self.instruments.body.addWidget(self._note(f"{r.key}: {r.status.lower()} {r.reason}".strip()))
            return
        if kind == "Scalar":
            m = Metric(f"{r.key} · {r.kind.replace('_', ' ')}", data.unit_label)
            m.set_value(fmt(data.value))
            m.setToolTip(str(data.value))
            self.metrics.append(m)
            self.instruments.body.addWidget(m)
        elif kind == "ComplexScalar":
            re, im = data.value.re, data.value.im
            m = Metric(f"{r.key} · fasor @ {fmt(data.frequency_hz)} Hz", data.unit_label)
            m.set_value(f"{fmt(re, 5)} {'−' if im < 0 else '+'} j{fmt(abs(im), 5)}")
            m.setToolTip(f"re {re}\nim {im}")
            self.metrics.append(m)
            self.instruments.body.addWidget(m)
        elif kind == "ScopeData":
            plot = PlotView(r.key, "tiempo (s)", data.channels[0].unit_label if data.channels else "")
            plot.set_series([(ch.probe_key, ch.times, ch.raw) for ch in data.channels])
            self._add_plot(plot)
        elif kind == "BodeData":
            pts = [q for q in data.points if q.db is not None]
            freqs = [q.frequency_hz for q in pts]
            bode = BodePlotView("Bode")
            bode.set_data(freqs, [q.db for q in pts],
                          [None if q.unwrapped_rad is None else math.degrees(q.unwrapped_rad) for q in pts])
            self._add_plot(bode)
        elif kind == "SweepData":
            plot = PlotView(data.axis_label or r.key, data.axis_label, data.unit_label)
            plot.set_series([(r.key, data.axis, data.values)])
            self._add_plot(plot)
        else:
            self.instruments.body.addWidget(self._note(f"{r.key}: {str(data)[:120]}"))

    @staticmethod
    def _note(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("CardStatus")
        label.setWordWrap(True)
        return label

    def _measurements(self, rows) -> None:
        if not rows:
            return
        t = QTableWidget(len(rows), len(self.MEASURE_COLUMNS))
        t.setHorizontalHeaderLabels(self.MEASURE_COLUMNS)
        t.setAccessibleName("Medidas")
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.verticalHeader().hide()
        t.setShowGrid(False)
        t.horizontalHeader().setStretchLastSection(True)
        for i, m in enumerate(rows):
            value = m.value
            cells = (m.key, fmt(value.value) if value is not None else "—",
                     value.unit_label if value is not None else "", m.status)
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if value is None and getattr(m, "reason", ""):
                    item.setToolTip(m.reason)
                elif c == 1:
                    item.setToolTip(str(value.value))
                t.setItem(i, c, item)
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)
        t.setMinimumHeight(min(60 + 32 * len(rows), 200))
        self.measure_table = t
        self.instruments.body.addWidget(t)


class LabKit:
    """Experiment / Setup / Visualization / Instruments / Results around a toolbar."""

    def __init__(self, host: QWidget, output: QTextEdit):
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(8)
        root.addLayout(self.toolbar)
        self.notice = Notice("")
        root.addWidget(self.notice)
        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(16)
        self.experiment = Panel("Experimento")
        self.setup = Panel("Configuración")
        left.addWidget(self.experiment)
        left.addWidget(self.setup)
        left.addStretch(1)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(LEFT_WIDTH)
        body.addWidget(left_w)

        right = QVBoxLayout()
        right.setSpacing(16)
        self.viz = Panel("Visualización")
        right.addWidget(self.viz, 3)
        lower = QHBoxLayout()
        lower.setSpacing(16)
        self.instruments = Panel("Instrumentos")
        self.results = Panel("Resultados")
        lower.addWidget(self.instruments, 3)
        lower.addWidget(self.results, 2)
        right.addLayout(lower, 2)
        body.addLayout(right, 1)

        self.verification = VerificationCard()
        self.results.add(self.verification)
        self.header = KeyValueList()
        self.header.set_rows([("Estado", "Aún sin ejecución. Los resultados aparecen aquí.")])  # F-09: never an empty box
        self.results.add(self.header)
        self.log_toggle = QPushButton("Registro de la ejecución")
        self.log_toggle.setProperty("class", "subtle")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setToolTip("Texto legible por máquina de la última acción")
        self.results.actions.addWidget(self.log_toggle)
        self.output = output
        self.output.setVisible(False)
        self.log_toggle.toggled.connect(self.output.setVisible)
        self.results.add(self.output, 1)
        self.presenter = RunPresenter(self.viz, self.instruments, self.header, self.verification)

    def show_log(self) -> None:
        self.log_toggle.setChecked(True)
