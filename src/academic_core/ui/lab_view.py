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

from academic_core.ui.workspace import EmptyState, KeyValueList, Metric, Panel

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
        self.setAccessibleName(title or "Plot")

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
                f"{sum(len(xs) for _, xs, _ in clean)} points; x {min(xs_all):.4g} to {max(xs_all):.4g}"
                f" {self.x_label}; y {min(ys_all):.4g} to {max(ys_all):.4g} {self.y_label}")
        else:
            self.setAccessibleDescription("No data")
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
            p.drawText(plot, int(Qt.AlignmentFlag.AlignCenter), "No data")
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
            p.drawText(QRectF(x - 34, plot.bottom() + 4, 68, 16), int(Qt.AlignmentFlag.AlignCenter), f"{t:.4g}")
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

    MEASURE_COLUMNS = ("Measurement", "Value", "Unit", "Status")

    def __init__(self, viz: Panel, instruments: Panel, header: KeyValueList):
        self.viz, self.instruments, self.header = viz, instruments, header
        self.plots: list[PlotView] = []
        self.metrics: list[Metric] = []
        self.measure_table: QTableWidget | None = None
        self.clear()

    def clear(self, viz_text=("No run yet", "Set up the experiment and run it."),
              inst_text=("No readings yet", "Instruments and measurements appear after a run.")) -> None:
        _clear(self.viz.body)
        _clear(self.instruments.body)
        self.plots, self.metrics, self.measure_table = [], [], None
        self.viz.body.addWidget(EmptyState(*viz_text))
        self.instruments.body.addWidget(EmptyState(*inst_text))
        self.header.set_rows([])

    # -- one run ------------------------------------------------------------------------
    def show_run(self, summary) -> None:
        _clear(self.viz.body)
        _clear(self.instruments.body)
        self.plots, self.metrics, self.measure_table = [], [], None
        self.header.set_rows([("Run", summary.run_id), ("Status", summary.status),
                              ("Engine", summary.engine_status or "—"),
                              ("Digest", summary.result_digest[:16] + "…")])
        self.header.setToolTip(f"Result digest {summary.result_digest}")
        for reading in summary.readings:
            self._reading(reading)
        self._measurements(summary.measurements)
        if not self.plots:
            self.viz.body.addWidget(EmptyState("Nothing to plot", "This run produced no waveform or sweep."))
        if not self.metrics and not summary.measurements:
            self.instruments.body.addWidget(EmptyState("No readings", "No instrument or measurement was requested."))

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
            m = Metric(f"{r.key} · phasor @ {fmt(data.frequency_hz)} Hz", data.unit_label)
            m.set_value(f"{fmt(re, 5)} {'−' if im < 0 else '+'} j{fmt(abs(im), 5)}")
            m.setToolTip(f"re {re}\nim {im}")
            self.metrics.append(m)
            self.instruments.body.addWidget(m)
        elif kind == "ScopeData":
            plot = PlotView(r.key, "time (s)", data.channels[0].unit_label if data.channels else "")
            plot.set_series([(ch.probe_key, ch.times, ch.raw) for ch in data.channels])
            self._add_plot(plot)
        elif kind == "BodeData":
            pts = [q for q in data.points if q.db is not None]
            freqs = [q.frequency_hz for q in pts]
            mag = PlotView("Gain", "frequency (Hz)", "dB", x_log=True)
            mag.set_series([("gain", freqs, [q.db for q in pts])])
            ph = PlotView("Phase", "frequency (Hz)", "°", x_log=True)
            phased = [q for q in pts if q.unwrapped_rad is not None]
            ph.set_series([("phase", [q.frequency_hz for q in phased],
                            [math.degrees(q.unwrapped_rad) for q in phased])])
            self._add_plot(mag)
            self._add_plot(ph)
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
        t.setAccessibleName("Measurements")
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
        self.notice = QLabel("")
        self.notice.setObjectName("CardStatus")
        self.notice.setWordWrap(True)
        root.addWidget(self.notice)
        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(16)
        self.experiment = Panel("Experiment")
        self.setup = Panel("Setup")
        left.addWidget(self.experiment)
        left.addWidget(self.setup)
        left.addStretch(1)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(LEFT_WIDTH)
        body.addWidget(left_w)

        right = QVBoxLayout()
        right.setSpacing(16)
        self.viz = Panel("Visualization")
        right.addWidget(self.viz, 3)
        lower = QHBoxLayout()
        lower.setSpacing(16)
        self.instruments = Panel("Instruments")
        self.results = Panel("Results")
        lower.addWidget(self.instruments, 3)
        lower.addWidget(self.results, 2)
        right.addLayout(lower, 2)
        body.addLayout(right, 1)

        self.header = KeyValueList()
        self.results.add(self.header)
        self.log_toggle = QPushButton("Run log")
        self.log_toggle.setProperty("class", "subtle")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setToolTip("Machine-readable text of the last action")
        self.results.actions.addWidget(self.log_toggle)
        self.output = output
        self.output.setVisible(False)
        self.log_toggle.toggled.connect(self.output.setVisible)
        self.results.add(self.output, 1)
        self.presenter = RunPresenter(self.viz, self.instruments, self.header)

    def show_log(self) -> None:
        self.log_toggle.setChecked(True)
