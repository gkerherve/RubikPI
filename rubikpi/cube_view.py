"""Cube state widget: isometric 3-face view above an unfolded net.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Two things keep the picture readable while a solution plays:

* The view is anchored to *colours*, not to face names — the blue centre
  always faces you and the yellow centre is always on top, whatever
  rotations the solution contains.
* Turns are animated.  The cube is built from 27 cubies and drawn back to
  front, so a turning layer really rotates in 3D — the stickers on its
  sides travel with it, as on a real cube — and a curved arrow shows the
  direction.

While you are being shown what to do, the next move demonstrates itself:
the layer turns, snaps back and turns again, over and over, so the move
can be read off the cube instead of decoded from "D2".

Beside the cube sits the face the camera is pointed at — the one you are
looking at while you play, which on the isometric view is round the back.
It is found by centre colour, so it keeps following the right side of the
cube even when a solution contains whole-cube rotations.  While the camera
is following, that panel shows the *live* reading rather than the app's
belief, with a tick when the two agree: confirmation that your cube and
the plan are still in step.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QSizePolicy, QWidget

from rubikpi import cube3d as g3
from rubikpi.cube import (
    COLOR_NAME, DEFAULT_SCHEME, FACES, Cube, face_with_center,
    orientation_for_colors, position_of_faces,
)

STICKER_QCOLOR = {
    "W": QColor("#f2f3f5"), "Y": QColor("#ffd500"), "R": QColor("#c41e3a"),
    "O": QColor("#ff6c00"), "G": QColor("#00a651"), "B": QColor("#0466c8"),
    "X": QColor("#4a4f57"),
}

_NET_ORIGIN = {  # face -> (col, row) in 3-sticker units on the net grid
    "U": (3, 0), "L": (0, 3), "F": (3, 3), "R": (6, 3), "B": (9, 3),
    "D": (3, 6),
}

#: Colours the viewer always looks at: yellow up, blue front.
VIEW_TOP = DEFAULT_SCHEME["U"]
VIEW_FRONT = DEFAULT_SCHEME["F"]


class CubeViewWidget(QWidget):
    """Paints the cube twice: a 3D-looking view (U/F/R) and the full net."""

    #: Emitted when a turn animation finishes.
    animation_finished = pyqtSignal()

    #: Milliseconds for a quarter turn, and the frame interval.
    TURN_MS = 420
    FRAME_MS = 16
    #: Preview loop: pause at the end of the turn, then before repeating.
    #: It runs for as long as a move is waiting to be done, so it ticks at
    #: half the frame rate of a real turn to stay cheap.
    HOLD_MS = 520
    GAP_MS = 320
    PREVIEW_FRAME_MS = 33

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cube = Cube.unknown()
        self.highlight_face: str | None = None
        self.move_text: str = ""
        #: Colour of the face the camera is pointed at, shown beside the
        #: cube.  Held as a colour, not a face name, so whole-cube
        #: rotations cannot make the panel drift onto another side.
        self.camera_colour: str = DEFAULT_SCHEME["B"]
        #: Live 9 stickers from the camera and whether they match the
        #: model.  None means the camera is not watching.
        self.live_face: list[str] | None = None
        self.live_matches: bool = False
        self.setMinimumSize(380, 460)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

        # Animation state: the face being turned, how far through, and the
        # cube as it looked *before* the move.
        self._anim_face: str | None = None
        self._anim_quarters = 1.0      # 1 for a quarter turn, 2 for a half
        self._anim_dir = 1             # +1 clockwise, -1 anticlockwise
        self._anim_t = 0.0             # 0 -> 1
        self._anim_cube: Cube | None = None
        self._mode = ""                # "", "move" or "preview"
        self._preview_move = ""        # the move being demonstrated
        self._stage = "turn"           # preview loop: turn / hold / gap
        self._wait = 0                 # frames left in hold or gap
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # -- public API ----------------------------------------------------------

    def set_cube(self, cube: Cube) -> None:
        self.cube = cube
        self.update()

    def set_camera_colour(self, colour: str) -> None:
        """Which side the camera is on, as a sticker colour letter."""
        self.camera_colour = colour
        self.update()

    def set_live_face(self, letters: list[str] | None,
                      matches: bool = False) -> None:
        """What the camera reads right now, and whether it fits the model."""
        self.live_face = list(letters) if letters else None
        self.live_matches = matches
        self.update()

    def camera_face(self, cube: Cube) -> str | None:
        """The face of *cube* whose centre is the camera's colour."""
        return face_with_center(cube, self.camera_colour)

    def set_highlight(self, face: str | None, move_text: str = "") -> None:
        self.highlight_face = face
        self.move_text = move_text
        self.update()

    def animate_move(self, before: Cube, move: str) -> None:
        """Spin the layer *move* turns, starting from the *before* state.

        The caller has already applied the move to its own cube; this only
        plays the picture catching up.
        """
        core = move[0] if move else ""
        if core not in FACES:
            self.animation_finished.emit()
            return
        self._anim_cube = before.copy()
        self._mode = "move"
        self._set_turn(move)
        self._anim_t = 0.0
        self._timer.setInterval(self.FRAME_MS)
        self._timer.start()
        self.update()

    def set_preview_move(self, move: str) -> None:
        """Loop *move* on the current cube so its meaning is obvious.

        Nothing is committed: the layer turns, snaps back and turns
        again.  A real move animation takes over when one arrives, and
        the loop resumes afterwards with whatever is next.
        """
        core = move[0] if move else ""
        if core not in FACES:
            move = ""
        if move == self._preview_move:
            return
        self._preview_move = move
        if self._mode == "move":
            return                      # resumes when that finishes
        self._start_preview()

    def _start_preview(self) -> None:
        if not self._preview_move:
            self._mode = ""
            self._anim_face = None
            self._timer.stop()
            self.update()
            return
        self._mode = "preview"
        self._anim_cube = None          # always demonstrate on the live cube
        self._set_turn(self._preview_move)
        self._anim_t = 0.0
        self._stage = "turn"
        self._wait = 0
        self._timer.setInterval(self.PREVIEW_FRAME_MS)
        self._timer.start()
        self.update()

    def _set_turn(self, move: str) -> None:
        self._anim_face = move[0]
        self._anim_quarters = 2.0 if move.endswith("2") else 1.0
        self._anim_dir = -1 if move.endswith("'") else 1

    def stop_animation(self) -> None:
        """Drop everything, preview included (used when jumping about)."""
        if self._timer.isActive():
            self._timer.stop()
        self._anim_face = None
        self._anim_cube = None
        self._mode = ""
        self._preview_move = ""
        self.update()

    @property
    def animating(self) -> bool:
        return self._anim_face is not None

    def _tick(self) -> None:
        frame = self._timer.interval() or self.FRAME_MS
        step = frame / (self.TURN_MS * self._anim_quarters)
        if self._mode == "preview":
            if self._stage == "turn":
                self._anim_t += step
                if self._anim_t >= 1.0:
                    self._anim_t = 1.0
                    self._stage = "hold"
                    self._wait = int(self.HOLD_MS / frame)
            elif self._stage == "hold":
                self._wait -= 1
                if self._wait <= 0:     # snap back and pause before repeating
                    self._anim_t = 0.0
                    self._stage = "gap"
                    self._wait = int(self.GAP_MS / frame)
            else:
                self._wait -= 1
                if self._wait <= 0:
                    self._stage = "turn"
            self.update()
            return

        self._anim_t += step
        if self._anim_t >= 1.0:
            self._timer.stop()
            self._anim_face = None
            self._anim_cube = None
            self._anim_t = 0.0
            self._mode = ""
            self.update()
            self.animation_finished.emit()
            self._start_preview()       # back to demonstrating what is next
            return
        self.update()

    # -- display orientation --------------------------------------------------

    def _display(self) -> tuple[Cube, dict[str, str], str | None]:
        """The cube as shown (blue front, yellow up) and the face mapping.

        Returns the reoriented cube, a map from model face to the position
        it is drawn at, and the position of the highlighted face.
        """
        cube = self._anim_cube if self._anim_cube is not None else self.cube
        seq = orientation_for_colors(cube, VIEW_TOP, VIEW_FRONT)
        if seq is None:                      # not scanned yet: draw as-is
            return cube, {f: f for f in FACES}, self.highlight_face
        shown = cube.copy()
        shown.apply_sequence(seq)
        where = position_of_faces(seq)
        spot = where.get(self.highlight_face) if self.highlight_face else None
        return shown, where, spot

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        shown, where, spot = self._display()
        turning = where.get(self._anim_face) if self._anim_face else None

        iso_h = int(h * 0.58)
        panel_w = int(min(w * 0.33, iso_h * 0.8))
        self._paint_isometric(p, 0, 0, w - panel_w, iso_h, shown, spot,
                              turning)
        self._paint_camera_panel(p, w - panel_w, 0, panel_w, iso_h, shown)
        self._paint_net(p, 0, iso_h, w, h - iso_h, shown, spot)

        label = self.move_text
        colour = "#e8b93c"
        if self._mode == "preview" and self._preview_move:
            label = f"Do this:  {self._preview_move}"
            colour = "#8fd3a8"
        if label:
            p.setPen(QPen(QColor(colour)))
            f = QFont(self.font())
            f.setPointSize(15)
            f.setBold(True)
            p.setFont(f)
            p.drawText(12, 26, label)
        p.end()

    # The cube drawn as 27 cubies, back to front, so a turning layer
    # really rotates — side stickers and all.
    def _paint_isometric(self, p: QPainter, x: int, y: int, w: int, h: int,
                         shown: Cube, spot: str | None,
                         turning: str | None) -> None:
        scale = min(w / 6.0, h / 6.8)
        cx = x + w / 2.0
        cy = y + h / 2.0
        angle = 0.0
        axis_index = 0
        if turning is not None:
            t = min(max(self._anim_t, 0.0), 1.0)
            eased = 0.5 - 0.5 * math.cos(math.pi * t)   # ease in and out
            axis_index, full = g3.turn_rotation(
                turning, self._anim_quarters * self._anim_dir)
            angle = full * eased
        quads = []
        for cubie in g3.cubies():
            spin = (turning is not None
                    and g3.in_turning_layer(turning, cubie))
            for face in g3.stickers_of(cubie):
                corners = g3.sticker_quad(cubie, face)
                normal = g3.NORMALS[face]
                if spin:
                    corners = [g3.rotate(c, axis_index, angle)
                               for c in corners]
                    normal = g3.rotate(normal, axis_index, angle)
                if not g3.faces_toward_viewer(normal):
                    continue
                colour = shown.faces[face][g3.facelet_index(face, *cubie)]
                middle = (sum(c[0] for c in corners) / 4.0,
                          sum(c[1] for c in corners) / 4.0,
                          sum(c[2] for c in corners) / 4.0)
                quads.append((g3.depth(middle), corners, colour, face))
        quads.sort(key=lambda q: q[0])          # painter's algorithm
        edge = QPen(QColor("#14161a"), max(1.5, scale * 0.05))
        for _, corners, colour, face in quads:
            poly = QPolygonF([QPointF(cx + sx, cy + sy) for sx, sy in
                              (g3.project(c, scale) for c in corners)])
            p.setBrush(STICKER_QCOLOR.get(colour, STICKER_QCOLOR["X"]))
            p.setPen(edge)
            p.drawPolygon(poly)
            if face == spot and turning is None:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor("#e8b93c"), max(2.0, scale * 0.05)))
                p.drawPolygon(poly)
        if turning is not None:
            self._draw_turn_arrow(p, cx, cy, scale, turning)

    def _draw_turn_arrow(self, p: QPainter, cx: float, cy: float,
                         scale: float, face: str) -> None:
        """A curved arrow over the turning face, showing which way it goes."""
        normal = g3.NORMALS[face]
        if abs(normal[0]):
            u, v = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
        elif abs(normal[1]):
            u, v = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
        else:
            u, v = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        base = tuple(n * 2.05 for n in normal)      # float clear of the face
        _, _, sign = g3.TURN_AXIS[face]
        way = sign * self._anim_dir
        radius = 0.95
        start = math.pi * 0.15
        sweep = math.pi * 1.25 * (1 if way > 0 else -1)

        def at(ang: float) -> QPointF:
            point = tuple(base[i] + (u[i] * math.cos(ang)
                                     + v[i] * math.sin(ang)) * radius
                          for i in range(3))
            sx, sy = g3.project(point, scale)
            return QPointF(cx + sx, cy + sy)

        path = QPainterPath()
        steps = 28
        for i in range(steps + 1):
            point = at(start + sweep * (i / steps))
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#f7d774"), max(2.5, scale * 0.055),
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)

        tip = at(start + sweep)
        before = at(start + sweep * 0.94)
        dx, dy = tip.x() - before.x(), tip.y() - before.y()
        length = math.hypot(dx, dy) or 1.0
        dx, dy = dx / length, dy / length
        size = max(7.0, scale * 0.16)
        p.setBrush(QColor("#f7d774"))
        p.setPen(QPen(QColor("#f7d774"), 1))
        p.drawPolygon(QPolygonF([
            tip,
            QPointF(tip.x() - dx * size + dy * size * 0.55,
                    tip.y() - dy * size - dx * size * 0.55),
            QPointF(tip.x() - dx * size - dy * size * 0.55,
                    tip.y() - dy * size + dx * size * 0.55),
        ]))

    def _paint_camera_panel(self, p: QPainter, x: int, y: int, w: int,
                            h: int, shown: Cube) -> None:
        """The side the camera is on: what it reads, or what is expected.

        On the isometric view this side is round the back, but it is the
        one in front of *you* while you play.  With the camera following
        it shows the live reading and ticks when that agrees with the
        app — so a wrong turn, or a turn the app missed, is visible at
        once instead of silently drifting.
        """
        face = self.camera_face(shown)
        live = self.live_face is not None
        accent = QColor("#4fc3f7")
        if live:
            accent = QColor("#59c98a") if self.live_matches else QColor("#d1707c")

        title = QFont(self.font())
        title.setPointSizeF(max(8.0, min(w, h) * 0.075))
        title.setBold(True)
        p.setFont(title)
        p.setPen(QPen(accent))
        p.drawText(int(x + 8), int(y + h * 0.16), "Camera sees")

        s = min(w * 0.78, h * 0.46) / 3.0
        gx = x + (w - 3 * s) / 2.0
        gy = y + h * 0.24
        stickers = self.live_face if live else (
            shown.faces[face] if face else None)
        if stickers is None:
            p.setPen(QPen(QColor("#8a9099")))
            p.drawText(int(x + 8), int(gy + s), "—")
            return
        for row in range(3):
            for col in range(3):
                px = gx + col * s
                py = gy + row * s
                letter = stickers[row * 3 + col]
                p.setBrush(STICKER_QCOLOR.get(letter, STICKER_QCOLOR["X"]))
                p.setPen(QPen(QColor("#14161a"), max(1.0, s * 0.06)))
                p.drawRect(int(px), int(py), int(s), int(s))
                if letter == "X":
                    # Covered by a finger or lost to glare: shown as hatched
                    # rather than guessed at, so it reads as "I cannot see
                    # this one" instead of a wrong colour.
                    p.setPen(QPen(QColor("#8a9099"), max(1.0, s * 0.08)))
                    for k in range(1, 4):
                        off = k * s / 4.0
                        p.drawLine(int(px), int(py + off),
                                   int(px + off), int(py))
                        p.drawLine(int(px + s), int(py + s - off),
                                   int(px + s - off), int(py + s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(accent, 3))
        p.drawRect(int(gx), int(gy), int(3 * s), int(3 * s))

        name = QFont(self.font())
        name.setPointSizeF(max(7.5, min(w, h) * 0.062))
        p.setFont(name)
        if live:
            p.setPen(QPen(accent))
            covered = sum(1 for c in self.live_face if c == "X")
            caption = ("✔ matches the plan" if self.live_matches
                       else "✗ not what I expect yet")
            if covered:
                caption += f"  ({covered} hidden)"
        else:
            p.setPen(QPen(QColor("#c6cad1")))
            caption = f"{COLOR_NAME[self.camera_colour]} side — what you look at"
        p.drawText(int(x + 8), int(gy + 3 * s + h * 0.12), caption)

    def _paint_net(self, p: QPainter, x: int, y: int, w: int, h: int,
                   shown: Cube, spot: str | None) -> None:
        s = min(w / 12.6, h / 9.6)
        x0 = x + (w - 12 * s) / 2.0
        y0 = y + (h - 9 * s) / 2.0
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, s * 0.42))
        p.setFont(f)
        for face in FACES:
            fc, fr = _NET_ORIGIN[face]
            stickers = shown.faces[face]
            for rr in range(3):
                for cc in range(3):
                    px = x0 + (fc + cc) * s
                    py = y0 + (fr + rr) * s
                    p.setBrush(STICKER_QCOLOR.get(stickers[rr * 3 + cc],
                                                  STICKER_QCOLOR["X"]))
                    p.setPen(QPen(QColor("#14161a"), max(1.0, s * 0.05)))
                    p.drawRect(int(px), int(py), int(s), int(s))
            watched = self.camera_face(shown)
            pen = QPen(QColor("#e8b93c") if face == spot
                       else QColor("#4fc3f7") if face == watched
                       else QColor("#30343b"),
                       3 if face in (spot, watched) else 2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
            p.drawRect(int(x0 + fc * s), int(y0 + fr * s),
                       int(3 * s), int(3 * s))
            p.setPen(QPen(QColor("#9aa0a8")))
            p.drawText(int(x0 + fc * s + 3), int(y0 + fr * s + s * 0.5), face)
