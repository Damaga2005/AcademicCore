# SPDX-License-Identifier: MIT
"""Generate the AcademicCore product icon (reproducible, no third-party assets).

Renders offscreen with Qt only: ink tile + accent beam + "A" mark.
Output: packaging/windows/academicore.ico (256px).
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPixmap


def render(size: int = 256) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0
    # Ink tile.
    path = QPainterPath()
    path.addRoundedRect(8 * s, 8 * s, 240 * s, 240 * s, 56 * s, 56 * s)
    p.fillPath(path, QColor("#1D1D1F"))
    # Accent beam (ascending rule).
    beam = QPainterPath()
    beam.moveTo(48 * s, 176 * s)
    beam.lineTo(208 * s, 176 * s)
    beam.lineTo(208 * s, 160 * s)
    beam.lineTo(48 * s, 160 * s)
    beam.closeSubpath()
    p.fillPath(beam, QColor("#007AFF"))
    # "A" mark as vectors (no font engine: reproducible everywhere).
    pen = p.pen()
    from PySide6.QtGui import QPen
    pen = QPen(QColor("#FFFFFF"), 22 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    # Left leg: (88,188) -> (128,84). Right leg: (168,188) -> (128,84).
    p.drawLine(int(88 * s), int(188 * s), int(128 * s), int(84 * s))
    p.drawLine(int(168 * s), int(188 * s), int(128 * s), int(84 * s))
    # Crossbar.
    pen.setWidth(int(16 * s))
    p.setPen(pen)
    p.drawLine(int(104 * s), int(152 * s), int(152 * s), int(152 * s))
    p.end()
    return px


def main() -> None:
    _app = QGuiApplication([])
    out = sys.argv[1] if len(sys.argv) > 1 else "academicore.ico"
    ok = render().save(out, "ICO")
    if not ok:
        raise SystemExit("icon write failed")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
