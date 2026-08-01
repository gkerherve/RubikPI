"""Camera capture and cube-face colour recognition.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

A :class:`CameraWorker` thread grabs frames with OpenCV and *locates the
cube* before reading any colour: sticker-sized squares are found with a
contour scan, clustered into a face, and the 3x3 grid is sampled from the
detected face only.  While no cube is visible the grid stays unknown
("X"), so nothing can lock onto a wall or a person's face.  Detection is
considered *stable* once the same full grid has been seen for several
consecutive frames — that is the signal the scan panel uses to
auto-capture a face.

OpenCV is imported lazily so the rest of the app works without it.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

#: Guided scan protocol: (face, instruction).  Holding the cube with the
#: white centre up and the green centre facing the camera, every captured
#: grid maps 1:1 onto the face's sticker indices — no mental rotation needed.
SCAN_STEPS: list[tuple[str, str]] = [
    ("F", "Show the GREEN centre face, WHITE centre on top."),
    ("R", "Turn the cube LEFT (y): show the RED centre, white still on top."),
    ("B", "Turn LEFT again: show the BLUE centre, white still on top."),
    ("L", "Turn LEFT again: show the ORANGE centre, white still on top."),
    ("U", "Back to green in front, then TILT the cube DOWN: white faces you."),
    ("D", "From green in front, TILT the cube UP: yellow faces you."),
]

#: Centre sticker each scan step must show (standard colour scheme).
EXPECTED_CENTER: dict[str, str] = {
    "F": "G", "R": "R", "B": "B", "L": "O", "U": "W", "D": "Y",
}

#: Human names for the colour letters, for status messages.
COLOR_NAME = {
    "W": "white", "Y": "yellow", "R": "red",
    "O": "orange", "G": "green", "B": "blue", "X": "unknown",
}

#: Display colours (BGR for OpenCV overlays) for each sticker letter.
BGR = {
    "W": (245, 245, 245), "Y": (60, 210, 235), "R": (55, 45, 210),
    "O": (30, 130, 240), "G": (85, 170, 40), "B": (190, 100, 20),
    "X": (90, 90, 90),
}


def unmirror(grid: list[str]) -> list[str]:
    """Convert a grid sampled from the mirrored preview to true face order.

    The preview is horizontally flipped so that aiming feels natural; the
    real face (as seen when looking straight at the cube) is the mirror of
    what is on screen, i.e. each row reversed.
    """
    return [grid[r * 3 + (2 - c)] for r in range(3) for c in range(3)]


def classify_hsv(h: float, s: float, v: float) -> str:
    """Map an OpenCV HSV sample (h in 0..179) to a cube colour letter."""
    if v < 45:
        return "X"
    if s < 70 and v > 110:
        return "W"
    if h < 9 or h >= 160:
        return "R"
    if h < 22:
        return "O"
    if h < 40:
        return "Y"
    if h < 88:
        return "G"
    if h < 140:
        return "B"
    return "R"


class CameraWorker(QThread):
    """Grabs frames, locates the cube, reads the 3x3 grid, emits images."""

    frame_ready = pyqtSignal(QImage, list, bool)  # image, 9 colours, stable
    camera_error = pyqtSignal(str)

    STABLE_FRAMES = 8
    #: Frames a lost cube position is kept before detection resets.
    KEEP_LOST = 12

    def __init__(self, camera_index: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self._last_grid: list[str] = []
        self._stable_count = 0

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    # -- thread body ---------------------------------------------------------

    def run(self) -> None:  # noqa: C901 - one linear capture loop
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.camera_error.emit(
                "OpenCV is not installed.\n"
                "Install it with:  pip install opencv-python numpy"
            )
            return

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.camera_error.emit(
                f"Could not open camera #{self.camera_index}.\n"
                "Pick another index or use a Demo scramble instead."
            )
            return

        self._running = True
        rect: tuple[float, float, float] | None = None  # smoothed x0, y0, size
        lost = 0
        while self._running:
            ok, frame = cap.read()
            if not ok:
                self.camera_error.emit("Camera stream stopped.")
                break
            frame = cv2.flip(frame, 1)  # mirror: easier to aim
            h, w = frame.shape[:2]

            found = self._find_cube(cv2, np, frame)
            if found is not None:
                # Exponential smoothing keeps the grid from jittering.
                rect = found if rect is None else tuple(
                    0.35 * n + 0.65 * o for n, o in zip(found, rect))
                lost = 0
            elif rect is not None:
                lost += 1
                if lost > self.KEEP_LOST:
                    rect = None

            if rect is not None:
                grid = self._sample_grid(cv2, np, frame, rect)
            else:
                grid = ["X"] * 9  # no cube in view — never stabilises

            if grid == self._last_grid and "X" not in grid:
                self._stable_count += 1
            else:
                self._stable_count = 0
                self._last_grid = grid
            stable = self._stable_count >= self.STABLE_FRAMES

            self._draw_overlay(cv2, frame, rect, grid, stable)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
            self.frame_ready.emit(img.copy(), grid, stable)
            self.msleep(30)

        cap.release()

    # -- cube localisation ---------------------------------------------------

    @staticmethod
    def _find_cube(cv2, np, frame) -> tuple[float, float, float] | None:
        """Locate the cube face in the frame.

        Finds sticker-sized convex quads, keeps the densest cluster of
        similar-sized ones and returns the square (x0, y0, size) that spans
        the whole 3x3 face, or None when no plausible cube is visible.
        """
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, 30, 90)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST,
                                       cv2.CHAIN_APPROX_SIMPLE)

        lo = (min(h, w) * 0.035) ** 2   # sticker area bounds
        hi = (min(h, w) * 0.28) ** 2
        cand: list[tuple[float, float, float]] = []  # cx, cy, side
        for c in contours:
            area = cv2.contourArea(c)
            if not lo < area < hi:
                continue
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.06 * peri, True)
            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue
            x, y, bw, bh = cv2.boundingRect(approx)
            if not 0.65 < bw / bh < 1.55:       # roughly square
                continue
            if area / (bw * bh) < 0.62:         # actually fills its box
                continue
            cand.append((x + bw / 2.0, y + bh / 2.0, (bw + bh) / 2.0))

        if len(cand) < 5:
            return None

        sides = sorted(s for _, _, s in cand)
        med = sides[len(sides) // 2]
        cand = [c for c in cand if 0.55 * med < c[2] < 1.7 * med]
        if len(cand) < 5:
            return None

        # Densest spatial cluster: stickers of one face sit within about
        # 3.4 sticker-widths of the face centre (grid diagonal + margin).
        reach = 3.4 * med
        best: list[tuple[float, float, float]] = []
        for cx, cy, _ in cand:
            near = [c for c in cand
                    if abs(c[0] - cx) < reach and abs(c[1] - cy) < reach]
            if len(near) > len(best):
                best = near
        if len(best) < 5:
            return None

        xs = [c[0] for c in best]
        ys = [c[1] for c in best]
        x0 = min(xs) - med / 2.0
        x1 = max(xs) + med / 2.0
        y0 = min(ys) - med / 2.0
        y1 = max(ys) + med / 2.0
        bw, bh = x1 - x0, y1 - y0
        if bw < 2.0 * med or bh < 2.0 * med:    # cluster too small for 3x3
            return None
        if not 0.65 < bw / bh < 1.55:           # face must be squarish
            return None

        size = max(bw, bh)
        # Centre the square on the cluster and clamp inside the frame.
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        x0 = min(max(cx - size / 2.0, 0.0), w - size)
        y0 = min(max(cy - size / 2.0, 0.0), h - size)
        if size > min(h, w):
            return None
        return (x0, y0, size)

    @staticmethod
    def _sample_grid(cv2, np, frame, rect: tuple[float, float, float]
                     ) -> list[str]:
        """Read the nine sticker colours inside the detected face square."""
        h, w = frame.shape[:2]
        x0, y0, size = rect
        cell = size / 3.0
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        grid: list[str] = []
        for row in range(3):
            for col in range(3):
                cx = int(x0 + col * cell + cell / 2)
                cy = int(y0 + row * cell + cell / 2)
                r = max(4, int(cell / 6))
                px0, px1 = max(cx - r, 0), min(cx + r, w)
                py0, py1 = max(cy - r, 0), min(cy + r, h)
                patch = hsv[py0:py1, px0:px1]
                if patch.size == 0:
                    grid.append("X")
                    continue
                hm = float(np.median(patch[:, :, 0]))
                sm = float(np.median(patch[:, :, 1]))
                vm = float(np.median(patch[:, :, 2]))
                grid.append(classify_hsv(hm, sm, vm))
        return grid

    # -- overlay -------------------------------------------------------------

    @staticmethod
    def _draw_overlay(cv2, frame, rect: tuple[float, float, float] | None,
                      grid: list[str], stable: bool) -> None:
        h, w = frame.shape[:2]
        if rect is None:
            cv2.putText(frame, "Looking for the cube...",
                        (w // 2 - 150, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 230), 2)
            return
        x0, y0, size = (int(v) for v in rect)
        cell = size // 3
        color = (90, 220, 90) if stable else (230, 230, 230)
        for i in range(4):
            cv2.line(frame, (x0 + i * cell, y0), (x0 + i * cell, y0 + 3 * cell),
                     color, 2)
            cv2.line(frame, (x0, y0 + i * cell), (x0 + 3 * cell, y0 + i * cell),
                     color, 2)
        # Detected colour chips in each cell corner.
        for row in range(3):
            for col in range(3):
                c = grid[row * 3 + col]
                px = x0 + col * cell + 6
                py = y0 + row * cell + 6
                cv2.rectangle(frame, (px, py), (px + 22, py + 22),
                              BGR.get(c, BGR["X"]), -1)
                cv2.rectangle(frame, (px, py), (px + 22, py + 22),
                              (20, 20, 20), 1)
        if stable:
            cv2.putText(frame, "LOCKED", (x0, max(y0 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (90, 220, 90), 2)
