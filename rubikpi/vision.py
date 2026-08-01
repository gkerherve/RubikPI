"""Camera capture and cube-face colour recognition.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

One face at a time: a :class:`CameraWorker` thread grabs frames with
OpenCV, finds the face in the picture (sticker-shaped squares, clustered
and fitted to a 3x3 grid) and reads its nine colours.  While no cube is
visible the grid stays unknown ("X"), so nothing can lock onto a wall or
a person's face, and a reading is *stable* once it has repeated for
several frames — the signal to capture, or to hand a move to the
follow-along tracker.

Colours are classified by nearest reference in Lab space; references are
recalibrated from each captured centre sticker (see ``learn_center``),
which is what separates the hard pairs (red/orange, white/yellow) under
real lighting.

OpenCV is imported lazily so the rest of the app works without it.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from rubikpi.cube import COLOR_NAME, DEFAULT_SCHEME

#: Centre sticker each face must show.  The centres *are* the face names,
#: so this is just the cube's colour scheme (see cube.DEFAULT_SCHEME):
#: change it there and every instruction below follows.
EXPECTED_CENTER: dict[str, str] = dict(DEFAULT_SCHEME)


def _name(face: str, caps: bool = True) -> str:
    """Colour word for a face, e.g. "BLUE" for F on a blue-front cube."""
    word = COLOR_NAME[EXPECTED_CENTER[face]]
    return word.upper() if caps else word


#: Guided scan: one face per step, held with the U colour on top and the
#: F colour towards you, so every captured grid maps 1:1 onto the face's
#: sticker indices — no mental rotation needed.
SCAN_STEPS: list[tuple[str, str]] = [
    ("F", f"Show the {_name('F')} centre face, {_name('U')} centre on top."),
    ("R", f"Turn the cube LEFT (y): show the {_name('R')} centre, "
          f"{_name('U', False)} still on top."),
    ("B", f"Turn LEFT again: show the {_name('B')} centre, "
          f"{_name('U', False)} still on top."),
    ("L", f"Turn LEFT again: show the {_name('L')} centre, "
          f"{_name('U', False)} still on top."),
    ("U", f"Back to {_name('F', False)} in front, then TILT the cube DOWN: "
          f"{_name('U', False)} faces you."),
    ("D", f"From {_name('F', False)} in front, TILT the cube UP: "
          f"{_name('D', False)} faces you."),
]

#: Display colours (BGR for OpenCV overlays) for each sticker letter.
BGR = {
    "W": (245, 245, 245), "Y": (60, 210, 235), "R": (55, 45, 210),
    "O": (30, 130, 240), "G": (85, 170, 40), "B": (190, 100, 20),
    "X": (90, 90, 90),
}


def classify_lab(lab: tuple[float, float, float],
                 refs: dict[str, tuple[float, float, float]]) -> str:
    """Nearest-reference classification in OpenCV Lab space.

    Lightness is down-weighted so shadows and lamp brightness matter less
    than the actual chroma of the sticker.  White vs yellow separates on
    the b (blue-yellow) axis, red vs orange on a/b together.
    """
    L, a, b = lab
    if L < 35:
        return "X"
    best = None
    letter = "X"
    for name, (rl, ra, rb) in refs.items():
        d = 0.30 * (L - rl) ** 2 + (a - ra) ** 2 + (b - rb) ** 2
        if best is None or d < best:
            best, letter = d, name
    return letter


class CameraWorker(QThread):
    """Grabs frames, finds one cube face, reads its nine colours."""

    # image, 9 colour letters, stable, 9 raw Lab samples
    frame_ready = pyqtSignal(QImage, object, bool, object)
    camera_error = pyqtSignal(str)

    STABLE_FRAMES = 6
    #: Frames a lost cube position is kept before detection resets.
    KEEP_LOST = 12

    def __init__(self, camera_source: str = "0", parent=None) -> None:
        super().__init__(parent)
        #: A device number ("0", "1", ...) or a stream URL — e.g. a phone
        #: running IP Webcam exposes http://PHONE-IP:8080/video.
        self.camera_source = str(camera_source)
        self._running = False
        self._expected_face = "F"   # for the scan badge; "" while following
        self._last_grid: list[str] = []
        self._stable_count = 0
        self._refs: dict[str, tuple[float, float, float]] | None = None

    def set_expected_face(self, face: str) -> None:
        """Face the scan wants next; "" during follow-along (any face)."""
        self._expected_face = face
        self._stable_count = 0
        self._last_grid = []

    def learn_center(self, letter: str, lab: tuple[float, float, float]
                     ) -> None:
        """Calibrate one colour reference from a captured centre sticker.

        The scan protocol fixes which centre each step shows, so the
        measured Lab value is ground truth for that colour under the
        user's lighting.  Blended, not replaced, to survive one bad frame.
        """
        if self._refs is None or letter not in self._refs:
            return
        old = self._refs[letter]
        self._refs[letter] = tuple(
            0.4 * o + 0.6 * n for o, n in zip(old, lab))

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

        src = self.camera_source.strip()
        cap = cv2.VideoCapture(int(src) if src.isdigit() else src)
        if not cap.isOpened():
            self.camera_error.emit(
                f"Could not open camera '{src}'.\n"
                "Pick another index, enter a stream URL such as\n"
                "http://PHONE-IP:8080/video (IP Webcam app),\n"
                "or use a Demo scramble instead."
            )
            return

        if self._refs is None:
            self._refs = self._default_refs(cv2, np)

        self._running = True
        rect: tuple[float, float, float] | None = None  # smoothed x0, y0, size
        lost = 0
        while self._running:
            ok, frame = cap.read()
            if not ok:
                self.camera_error.emit("Camera stream stopped.")
                break
            # The frame stays in *true* (unmirrored) orientation for all
            # detection and sampling; only the displayed image is flipped.
            h, w = frame.shape[:2]

            found = self._find_face(cv2, np, frame)
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
                grid, raw = self._sample_face(cv2, np, frame, rect, self._refs)
            else:
                grid = ["X"] * 9  # no cube in view — never stabilises
                raw = [(0.0, 128.0, 128.0)] * 9

            if grid == self._last_grid and "X" not in grid:
                self._stable_count += 1
            else:
                self._stable_count = 0
                self._last_grid = grid
            stable = self._stable_count >= self.STABLE_FRAMES

            self._draw_grid(cv2, frame, rect, grid, stable)
            frame = cv2.flip(frame, 1)  # mirror for natural aiming
            self._draw_labels(cv2, frame, rect, grid, stable)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
            self.frame_ready.emit(img.copy(), grid, stable, raw)
            self.msleep(30)

        cap.release()

    # -- face localisation ---------------------------------------------------

    @staticmethod
    def _edge_map(cv2, np, frame):
        """Colour-aware edge map: union of Canny over the B, G, R channels.

        A grayscale-only Canny loses edges between a dark sticker (blue,
        red) and a dark background even though the colours differ plainly.
        """
        blur = cv2.GaussianBlur(frame, (5, 5), 0)
        edges = None
        for ch in cv2.split(blur):
            e = cv2.Canny(ch, 30, 90)
            edges = e if edges is None else cv2.bitwise_or(edges, e)
        return cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    @staticmethod
    def _find_face(cv2, np, frame) -> tuple[float, float, float] | None:
        """Locate one cube face held flat towards the camera.

        Finds sticker-sized squares, keeps the densest cluster of
        similar-sized ones and returns the square (x0, y0, size) spanning
        the 3x3 face, or None when no plausible face is visible.
        """
        h, w = frame.shape[:2]
        edges = CameraWorker._edge_map(cv2, np, frame)
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

        # Densest spatial cluster: the stickers of one face sit within
        # about 3.4 sticker-widths of the face centre.
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
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        x0 = min(max(cx - size / 2.0, 0.0), w - size)
        y0 = min(max(cy - size / 2.0, 0.0), h - size)
        if size > min(h, w):
            return None
        return (x0, y0, size)

    # -- colour sampling -----------------------------------------------------

    @staticmethod
    def _default_refs(cv2, np) -> dict[str, tuple[float, float, float]]:
        """Starting Lab references derived from the nominal sticker colours."""
        refs: dict[str, tuple[float, float, float]] = {}
        for letter, bgr in BGR.items():
            if letter == "X":
                continue
            px = np.uint8([[list(bgr)]])
            lab = cv2.cvtColor(px, cv2.COLOR_BGR2LAB)[0][0]
            refs[letter] = tuple(float(v) for v in lab)
        return refs

    @staticmethod
    def _sample_face(cv2, np, frame, rect: tuple[float, float, float], refs,
                     ) -> tuple[list[str], list[tuple[float, float, float]]]:
        """Read the nine stickers of the detected face, row-major.

        Sampled on the true (unmirrored) frame, so the grid order matches
        the face's own sticker order with no mirror bookkeeping.
        """
        h, w = frame.shape[:2]
        x0, y0, size = rect
        cell = size / 3.0
        lab_img = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        letters: list[str] = []
        labs: list[tuple[float, float, float]] = []
        for row in range(3):
            for col in range(3):
                cx = int(x0 + col * cell + cell / 2)
                cy = int(y0 + row * cell + cell / 2)
                r = max(4, int(cell / 6))
                px0, px1 = max(cx - r, 0), min(cx + r, w)
                py0, py1 = max(cy - r, 0), min(cy + r, h)
                patch = lab_img[py0:py1, px0:px1]
                if patch.size == 0:
                    letters.append("X")
                    labs.append((0.0, 128.0, 128.0))
                    continue
                sample = (float(np.median(patch[:, :, 0])),
                          float(np.median(patch[:, :, 1])),
                          float(np.median(patch[:, :, 2])))
                letters.append(classify_lab(sample, refs))
                labs.append(sample)
        return letters, labs

    # -- overlay -------------------------------------------------------------

    @staticmethod
    def _draw_grid(cv2, frame, rect, grid: list[str], stable: bool) -> None:
        """3x3 overlay, drawn on the true frame before the display flip."""
        h, w = frame.shape[:2]
        found = rect is not None
        if not found:                      # faint aiming guide
            size = min(h, w) * 0.55
            rect = ((w - size) / 2.0, (h - size) / 2.0, size)
            color = (110, 110, 110)
        else:
            color = (90, 220, 90) if stable else (230, 230, 230)
        x0, y0, size = (int(v) for v in rect)
        cell = size // 3
        for i in range(4):
            cv2.line(frame, (x0 + i * cell, y0),
                     (x0 + i * cell, y0 + 3 * cell), color, 2)
            cv2.line(frame, (x0, y0 + i * cell),
                     (x0 + 3 * cell, y0 + i * cell), color, 2)
        if not found:
            return
        for row in range(3):
            for col in range(3):
                c = grid[row * 3 + col]
                px = x0 + col * cell + cell // 2
                py = y0 + row * cell + cell // 2
                cv2.rectangle(frame, (px - 9, py - 9), (px + 9, py + 9),
                              BGR.get(c, BGR["X"]), -1)
                cv2.rectangle(frame, (px - 9, py - 9), (px + 9, py + 9),
                              (20, 20, 20), 1)

    def _draw_labels(self, cv2, frame, rect, grid: list[str],
                     stable: bool) -> None:
        """Text and badges, drawn after the flip so they read normally."""
        h, w = frame.shape[:2]
        if rect is None:
            cv2.putText(frame, "Looking for the cube...", (w // 2 - 150, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 230), 2)
            return
        x0, y0, size = rect
        cx = int(w - (x0 + size / 2.0))     # mirror the centre
        top = max(int(y0) - 22, 24)
        if self._expected_face:             # scanning: show the target colour
            want = EXPECTED_CENTER[self._expected_face]
            cv2.circle(frame, (cx, top), 14, BGR[want], -1)
            cv2.circle(frame, (cx, top), 14, (20, 20, 20), 2)
            cv2.putText(frame, self._expected_face, (cx - 8, top + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
        else:                               # following: show what it sees
            seen = grid[4]
            if seen != "X":
                cv2.circle(frame, (cx, top), 14, BGR[seen], -1)
                cv2.circle(frame, (cx, top), 14, (20, 20, 20), 2)
        if stable:
            cv2.putText(frame, "LOCKED", (cx + 28, top + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (90, 220, 90), 2)
