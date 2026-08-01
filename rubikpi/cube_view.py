"""Cube state widget: isometric 3-face view above an unfolded net.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QSizePolicy, QWidget

from rubikpi.cube import FACES, Cube

STICKER_QCOLOR = {
    "W": QColor("#f2f3f5"), "Y": QColor("#ffd500"), "R": QColor("#c41e3a"),
    "O": QColor("#ff6c00"), "G": QColor("#00a651"), "B": QColor("#0466c8"),
    "X": QColor("#4a4f57"),
}

_NET_ORIGIN = {  # face -> (col, row) in 3-sticker units on the net grid
    "U": (3, 0), "L": (0, 3), "F": (3, 3), "R": (6, 3), "B": (9, 3),
    "D": (3, 6),
}


class CubeViewWidget(QWidget):
    """Paints the cube twice: a 3D-looking view (U/F/R) and the full net."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cube = Cube.unknown()
        self.highlight_face: str | None = None
        self.move_text: str = ""
        self.setMinimumSize(380, 460)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    # -- public API ----------------------------------------------------------

    def set_cube(self, cube: Cube) -> None:
        self.cube = cube
        self.update()

    def set_highlight(self, face: str | None, move_text: str = "") -> None:
        self.highlight_face = face
        self.move_text = move_text
        self.update()

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        iso_h = int(h * 0.56)
        self._paint_isometric(p, 0, 0, w, iso_h)
        self._paint_net(p, 0, iso_h, w, h - iso_h)

        if self.move_text:
            p.setPen(QPen(QColor("#e8b93c")))
            f = QFont(self.font())
            f.setPointSize(15)
            f.setBold(True)
            p.setFont(f)
            p.drawText(12, 26, self.move_text)
        p.end()

    # The classic axonometric cube: U on top, F down-left, R down-right.
    def _paint_isometric(self, p: QPainter, x: int, y: int,
                         w: int, h: int) -> None:
        s = min(w / 11.0, h / 7.6)  # sticker edge length
        ax, ay = 0.866 * s, 0.5 * s
        a = QPointF(ax, ay)      # cube x axis (to the right, going down)
        b = QPointF(-ax, ay)     # cube z axis (to the front, going down)
        dwn = QPointF(0.0, s)    # screen down, for the vertical faces

        cx = x + w / 2.0
        top = QPointF(cx, y + h / 2.0 - 3.4 * s)  # U back-left corner
        f0 = top + b * 3        # F top-left corner (up-front-left)
        r0 = top + a * 3 + b * 3  # R top-left corner (up-front-right)

        def cell(orig: QPointF, dx: QPointF, dy: QPointF,
                 rr: int, cc: int) -> QPolygonF:
            o = orig + dx * cc + dy * rr
            return QPolygonF([o, o + dx, o + dx + dy, o + dy])

        layouts = {
            "U": (top, a, b),
            "F": (f0, a, dwn),
            "R": (r0, QPointF(ax, -ay), dwn),
        }
        for face, (orig, dx, dy) in layouts.items():
            stickers = self.cube.faces[face]
            for rr in range(3):
                for cc in range(3):
                    poly = cell(orig, dx, dy, rr, cc)
                    p.setBrush(STICKER_QCOLOR.get(stickers[rr * 3 + cc],
                                                  STICKER_QCOLOR["X"]))
                    p.setPen(QPen(QColor("#14161a"), max(1.5, s * 0.06)))
                    p.drawPolygon(poly)
            if face == self.highlight_face:
                outline = QPolygonF([orig, orig + dx * 3,
                                     orig + dx * 3 + dy * 3, orig + dy * 3])
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor("#e8b93c"), max(3.0, s * 0.16)))
                p.drawPolygon(outline)

        # Face letters on the three visible faces.
        p.setPen(QPen(QColor(0, 0, 0, 90)))
        f = QFont(self.font())
        f.setPointSizeF(max(8.0, s * 0.45))
        p.setFont(f)
        for face, (orig, dx, dy) in layouts.items():
            p.drawText(orig + (dx + dy) * 0.28, face)

    def _paint_net(self, p: QPainter, x: int, y: int, w: int, h: int) -> None:
        s = min(w / 12.6, h / 9.6)
        x0 = x + (w - 12 * s) / 2.0
        y0 = y + (h - 9 * s) / 2.0
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, s * 0.42))
        p.setFont(f)
        for face in FACES:
            fc, fr = _NET_ORIGIN[face]
            stickers = self.cube.faces[face]
            for rr in range(3):
                for cc in range(3):
                    px = x0 + (fc + cc) * s
                    py = y0 + (fr + rr) * s
                    p.setBrush(STICKER_QCOLOR.get(stickers[rr * 3 + cc],
                                                  STICKER_QCOLOR["X"]))
                    p.setPen(QPen(QColor("#14161a"), max(1.0, s * 0.05)))
                    p.drawRect(int(px), int(py), int(s), int(s))
            pen = QPen(QColor("#e8b93c") if face == self.highlight_face
                       else QColor("#30343b"), 2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
            p.drawRect(int(x0 + fc * s), int(y0 + fr * s),
                       int(3 * s), int(3 * s))
            p.setPen(QPen(QColor("#9aa0a8")))
            p.drawText(int(x0 + fc * s + 3), int(y0 + fr * s + s * 0.5), face)
