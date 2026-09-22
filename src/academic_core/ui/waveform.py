# SPDX-License-Identifier: MIT
"""F8-Q.6 waveform renderer (design §§25-26, 35): presentation only.

This module turns a frozen ``CaptureView`` (application view model) into
pixels. It never sees domain objects, never evaluates gates, never
detects edges and never mutates anything. Its input is data; its output
is geometry, then paint.

``layout_waveform`` is the pure, deterministic part (no Qt objects), so
tests can check it exactly. Positions are computed from the exact
Decimal time strings of the view. Pixel rounding is presentation only;
the exact values stay in the view and in the transition table.

Several transitions that fall on one pixel column (same timestamp, or
closer than a pixel) are drawn as one vertical edge. The geometry
records this, so a merge is always flagged and never silent (design
§25):

- the edge carries a ``count``
- the widget prints ``×n`` above it
- ``merged_columns`` reports how many columns hold more than one
  transition

The model keeps every transition; the panel lists each one.

Accessibility: levels are labelled ``H``/``L`` in text, every lane has a
text label (channel and net), the trigger is a dashed line plus a text
label, pre/post regions are labelled in text, and colour is never the
only cue.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

LANE_HEIGHT = 44
LEFT = 150
RIGHT = 24
TOP = 56  # row 1: trigger label, row 2: pre/post labels
AXIS = 34
TICKS = 5


@dataclass(frozen=True)
class Edge:
    x: int
    count: int  # transitions drawn on this column (>1 = merged for display only)
    before: str  # level left of the edge
    after: str  # level right of the edge


@dataclass(frozen=True)
class Lane:
    channel_id: str
    label: str
    y_high: int
    y_low: int
    initial: str
    segments: tuple[tuple[int, int, str], ...]  # (x0, x1, "HIGH"/"LOW")
    edges: tuple[Edge, ...]


@dataclass(frozen=True)
class WaveformGeometry:
    width: int
    height: int
    x_start: int
    x_end: int
    lanes: tuple[Lane, ...]
    ticks: tuple[tuple[int, str], ...]
    trigger_x: int | None
    trigger_label: str
    pre_region: tuple[int, int] | None
    post_region: tuple[int, int] | None
    transitions_total: int
    edges_drawn: int
    merged_columns: int
    message: str  # non-empty when there is nothing to draw (e.g. NOT_TRIGGERED)


def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _x(t: Decimal, ws: Decimal, span: Decimal, x0: int, plot: int) -> int:
    if span == 0:
        return x0 + plot // 2
    return x0 + int(((t - ws) * plot / span).to_integral_value(rounding=ROUND_HALF_EVEN))


def layout_waveform(view, width: int = 900) -> WaveformGeometry:
    """Pure geometry for ``view`` (a ``CaptureView``) at ``width`` pixels."""
    width = max(int(width), LEFT + RIGHT + 100)
    x0, x1 = LEFT, width - RIGHT
    plot = x1 - x0
    if view is None or view.window is None:
        message = "No capture yet."
        if view is not None and view.status == "NOT_TRIGGERED":
            message = ("NOT_TRIGGERED — no qualifying edge on channel "
                       f"{view.trigger_channel} in the arming window. Nothing was captured.")
        return WaveformGeometry(width, TOP + AXIS, x0, x1, (), (), None, "", None, None, 0, 0, 0, message)
    ws, we = Decimal(view.window[0]), Decimal(view.window[1])
    span = we - ws
    lanes, drawn, merged, total = [], 0, 0, 0
    for k, ch in enumerate(view.channels):
        y_high = TOP + k * LANE_HEIGHT + 8
        y_low = y_high + LANE_HEIGHT - 18
        columns: list[list] = []  # [x, count, before, after]
        level = ch.initial
        for t in ch.transitions:
            x = _x(Decimal(t.time), ws, span, x0, plot)
            if columns and columns[-1][0] == x:
                columns[-1][1] += 1
                columns[-1][3] = t.new
            else:
                columns.append([x, 1, level, t.new])
            level = t.new
        total += len(ch.transitions)
        edges = tuple(Edge(x, n, before, after) for x, n, before, after in columns)
        segments, cursor, level = [], x0, ch.initial
        for e in edges:
            segments.append((cursor, e.x, level))
            cursor, level = e.x, e.after
        segments.append((cursor, x1, level))
        drawn += len(edges)
        merged += sum(1 for e in edges if e.count > 1)
        lanes.append(Lane(ch.channel_id, f"{ch.channel_id} ({ch.net_id})", y_high, y_low, ch.initial,
                          tuple(segments), edges))
    ticks = tuple((_x(ws + span * i / (TICKS - 1), ws, span, x0, plot), _fmt(ws + span * i / (TICKS - 1)))
                  for i in range(TICKS)) if span else ((x0 + plot // 2, _fmt(ws)),)
    trigger_x = pre = post = None
    label = ""
    if view.status == "TRIGGERED" and view.trigger_time is not None:
        trigger_x = _x(Decimal(view.trigger_time), ws, span, x0, plot)
        label = (f"T {view.fired_edge} on {view.trigger_channel} @ {view.trigger_time} s "
                 f"(transition #{view.trigger_index})")
        pre, post = (x0, trigger_x), (trigger_x, x1)
    height = TOP + len(lanes) * LANE_HEIGHT + AXIS
    message = "" if lanes else "The capture has no channels."
    return WaveformGeometry(width, height, x0, x1, tuple(lanes), ticks, trigger_x, label, pre, post,
                            total, drawn, merged, message)


class WaveformWidget(QWidget):
    """Paints ``layout_waveform`` geometry. Holds a view; never changes it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = None
        self.geometry_cache: WaveformGeometry | None = None
        self.setMinimumHeight(TOP + AXIS + LANE_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName("Logic analyzer waveform")
        self.setAccessibleDescription("Digital channels over time; exact transitions are listed in the table")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_view(self, view) -> None:
        self.view = view
        self.geometry_cache = None
        self._geometry()
        self.setMinimumHeight(self.geometry_cache.height)
        self.setToolTip(self.summary())
        self.update()

    def summary(self) -> str:
        g = self._geometry()
        if g.message:
            return g.message
        text = f"{len(g.lanes)} channels, {g.transitions_total} transitions"
        if g.merged_columns:
            text += (f"; {g.merged_columns} display column(s) hold several transitions "
                     "(all listed in the table)")
        return text

    def _geometry(self) -> WaveformGeometry:
        """Layout is O(transitions); recompute only when the view or the width changed."""
        g = self.geometry_cache
        if g is None or g.width != max(self.width(), LEFT + RIGHT + 100):
            g = self.geometry_cache = layout_waveform(self.view, self.width())
        return g

    def resizeEvent(self, event):  # noqa: N802 — Qt override
        self.geometry_cache = None
        super().resizeEvent(event)

    def paintEvent(self, _event):  # noqa: N802 — Qt override
        g = self._geometry()
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().base())
        fg = self.palette().text().color()
        p.setPen(QPen(fg))
        if g.message:
            p.drawText(QRectF(8, 8, self.width() - 16, self.height() - 16),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), g.message)
            p.end()
            return
        small = QFont(p.font())
        small.setPointSizeF(max(small.pointSizeF() * 0.85, 6.0))
        if g.pre_region is not None:
            shade = QColor(fg)
            shade.setAlpha(18)
            p.fillRect(QRectF(g.pre_region[0], TOP - 4, g.pre_region[1] - g.pre_region[0],
                              g.height - TOP - AXIS + 4), shade)
            p.drawText(g.pre_region[0] + 4, TOP - 12, "pre-trigger")
            p.drawText(g.post_region[0] + 4, TOP - 12, "post-trigger")
        for lane in g.lanes:
            p.setPen(QPen(fg))
            p.drawText(8, (lane.y_high + lane.y_low) // 2 + 4, lane.label)
            p.setFont(small)
            p.drawText(LEFT - 16, lane.y_high + 4, "H")
            p.drawText(LEFT - 16, lane.y_low + 4, "L")
            p.setFont(QFont())
            wave = QPen(fg)
            wave.setWidth(2)
            p.setPen(wave)
            for x0, x1, level in lane.segments:
                y = lane.y_high if level == "HIGH" else lane.y_low
                p.drawLine(x0, y, x1, y)
            for e in lane.edges:
                p.drawLine(e.x, lane.y_high, e.x, lane.y_low)
                if e.count > 1:
                    p.setFont(small)
                    p.drawText(e.x + 3, lane.y_high - 2, f"×{e.count}")
                    p.setFont(QFont())
        axis_y = g.height - AXIS + 6
        p.setPen(QPen(fg))
        p.drawLine(g.x_start, axis_y, g.x_end, axis_y)
        for x, text in g.ticks:
            p.drawLine(x, axis_y, x, axis_y + 4)
            p.drawText(x - 12, axis_y + 18, text)
        p.drawText(8, axis_y + 18, "t (s)")
        if g.trigger_x is not None:
            dashed = QPen(fg)
            dashed.setStyle(Qt.PenStyle.DashLine)
            p.setPen(dashed)
            p.drawLine(g.trigger_x, 20, g.trigger_x, axis_y)
            p.drawText(min(g.trigger_x + 4, max(g.x_end - 360, g.x_start)), 16, g.trigger_label)
        p.end()
