"""Camera capture and cube-face colour recognition.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

A :class:`CameraWorker` thread grabs frames with OpenCV, samples a 3x3 grid
inside a centred region of interest, classifies each cell into one of the six
cube colours (W Y R O G B) in HSV space, draws a friendly overlay and emits
the annotated frame plus the detected grid.  Detection is considered *stable*
once the same grid has been seen for several consecutive frames — that is the
signal the scan panel uses to auto-capture a face.

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
    if v < 40:
        return "X"
    if s < 65 and v > 120:
        return "W"
    if h < 7 or h >= 165:
        return "R"
    if h < 20:
        return "O"
    if h < 38:
        return "Y"
    if h < 85:
        return "G"
    if h < 135:
        return "B"
    return "R"


class CameraWorker(QThread):
    """Grabs frames, recognises the 3x3 grid, emits annotated images."""

    frame_ready = pyqtSignal(QImage, list, bool)  # image, 9 colours, stable
    camera_error = pyqtSignal(str)

    STABLE_FRAMES = 8

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
        while self._running:
            ok, frame = cap.read()
            if not ok:
                self.camera_error.emit("Camera stream stopped.")
                break
            frame = cv2.flip(frame, 1)  # mirror: easier to aim
            h, w = frame.shape[:2]
            roi = int(min(h, w) * 0.62)
            x0, y0 = (w - roi) // 2, (h - roi) // 2
            cell = roi // 3

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            grid: list[str] = []
            for row in range(3):
                for col in range(3):
                    cx = x0 + col * cell + cell // 2
                    cy = y0 + row * cell + cell // 2
                    r = max(4, cell // 6)
                    patch = hsv[cy - r:cy + r, cx - r:cx + r]
                    hm = float(np.median(patch[:, :, 0]))
                    sm = float(np.median(patch[:, :, 1]))
                    vm = float(np.median(patch[:, :, 2]))
                    grid.append(classify_hsv(hm, sm, vm))

            if grid == self._last_grid and "X" not in grid:
                self._stable_count += 1
            else:
                self._stable_count = 0
                self._last_grid = grid
            stable = self._stable_count >= self.STABLE_FRAMES

            self._draw_overlay(cv2, frame, x0, y0, cell, grid, stable)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
            self.frame_ready.emit(img.copy(), grid, stable)
            self.msleep(30)

        cap.release()

    @staticmethod
    def _draw_overlay(cv2, frame, x0: int, y0: int, cell: int,
                      grid: list[str], stable: bool) -> None:
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
            cv2.putText(frame, "LOCKED", (x0, y0 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (90, 220, 90), 2)
