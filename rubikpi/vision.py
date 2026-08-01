"""Camera capture and cube-face colour recognition.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

A :class:`CameraWorker` thread grabs frames with OpenCV and reads the cube
*corner-on*: three faces at once (top rhombus + two side panels), so the
whole cube is captured in just two views.  Sticker-sized quads are found
with a contour scan, clustered, and an isometric hexagon is fitted over
the cluster; the 27 sticker cells are sampled inside it.  While no cube
is visible the grid stays unknown ("X"), so nothing can lock onto a wall
or a person's face.  Detection is *stable* once the same 27 colours have
been seen for several consecutive frames — the auto-capture signal.

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


#: Guided scan protocol: two corner views of three faces each.
SCAN_VIEWS: list[tuple[tuple[str, str, str], str]] = [
    (("U", "F", "R"),
     f"Hold the cube corner-on: {_name('U')} on top, {_name('F')} and "
     f"{_name('R')} on the two panels shown by the guide."),
    (("D", "L", "B"),
     f"Flip the cube over: {_name('D')} on top, {_name('L')} and "
     f"{_name('B')} on the two panels shown by the guide."),
]

#: Easy-mode protocol: one flat-on face per step, (face, instruction).
#: Held with the U colour on top and the F colour towards you, every
#: captured grid maps 1:1 onto the face's sticker indices — no mental
#: rotation needed.
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

#: Facelet index for each sampled cell, per view and panel.
#:
#: Cells are sampled with ``a`` running along the panel's top edge away
#: from the front vertex and ``b`` along its other edge; list position is
#: ``a * 3 + b``.  The maps convert that to the cube model's facelet
#: numbering (Kociemba convention, see cube.py), derived from which
#: physical cube corner sits at the front vertex in each view.
VIEW_MAPS: list[dict[str, tuple[str, list[int]]]] = [
    {   # view 1 — front vertex is the U/F/R corner
        "top": ("U", [(2 - b) * 3 + (2 - a)
                      for a in range(3) for b in range(3)]),
        "left": ("F", [b * 3 + (2 - a) for a in range(3) for b in range(3)]),
        "right": ("R", [b * 3 + a for a in range(3) for b in range(3)]),
    },
    {   # view 2 — front vertex is the D/L/B corner
        "top": ("D", [(2 - a) * 3 + b for a in range(3) for b in range(3)]),
        "left": ("L", [(2 - b) * 3 + a for a in range(3) for b in range(3)]),
        "right": ("B", [(2 - b) * 3 + (2 - a)
                        for a in range(3) for b in range(3)]),
    },
]

#: 2D basis vectors of the isometric projection (screen y grows down).
SQRT3_2 = 0.8660254
UL = (-SQRT3_2, -0.5)   # up-left edge direction
UR = (SQRT3_2, -0.5)    # up-right edge direction
DN = (0.0, 1.0)         # front vertical edge direction

#: Panel name -> its two basis directions from the front vertex.
PANEL_BASIS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "top": (UL, UR), "left": (UL, DN), "right": (UR, DN),
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
    """Grabs frames, locates the cube, reads three faces, emits images."""

    # image, {face: 9 letters}, stable, {face: 9 raw Lab samples}
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
        self._mode = "corner"      # "corner" (3 faces) or "single" (1 face)
        self._view = 0
        self._single_face = "F"
        self._last_key: str = ""
        self._stable_count = 0
        self._refs: dict[str, tuple[float, float, float]] | None = None

    def set_mode(self, mode: str) -> None:
        """Switch between "corner" (3 faces at once) and "single" scanning."""
        self._mode = mode if mode in ("corner", "single") else "corner"
        self._stable_count = 0
        self._last_key = ""

    def set_view(self, index: int) -> None:
        """Select which corner view (0 or 1) is being captured."""
        self._view = max(0, min(index, len(VIEW_MAPS) - 1))
        self._stable_count = 0
        self._last_key = ""

    def set_single_face(self, face: str) -> None:
        """Tell the worker which face the single-face protocol expects."""
        self._single_face = face
        self._stable_count = 0
        self._last_key = ""

    def learn_center(self, letter: str, lab: tuple[float, float, float]
                     ) -> None:
        """Calibrate one colour reference from a captured centre sticker.

        The scan protocol fixes which centre each view shows, so the
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
        geom: tuple[float, float, float] | None = None  # smoothed geometry
        lost = 0
        last_mode = self._mode
        while self._running:
            ok, frame = cap.read()
            if not ok:
                self.camera_error.emit("Camera stream stopped.")
                break
            # The frame stays in *true* (unmirrored) orientation for all
            # detection and sampling; only the displayed image is flipped.
            h, w = frame.shape[:2]
            single = self._mode == "single"
            if self._mode != last_mode:
                geom, lost, last_mode = None, 0, self._mode

            if single:
                found = self._find_flat(cv2, np, frame)
            else:
                found = self._find_cube(cv2, np, frame)
            if found is not None:
                geom = found if geom is None else tuple(
                    0.35 * n + 0.65 * o for n, o in zip(found, geom))
                lost = 0
            elif geom is not None:
                lost += 1
                if lost > self.KEEP_LOST:
                    geom = None

            if single:
                if geom is not None:
                    letters, labs = self._sample_flat(cv2, np, frame, geom,
                                                      self._refs)
                else:
                    letters = ["X"] * 9
                    labs = [(0.0, 128.0, 128.0)] * 9
                faces = {"single": letters}
                raws = {"single": labs}
                key = "".join(letters)
            else:
                vmap = VIEW_MAPS[self._view]
                if geom is not None:
                    faces, raws = self._sample_view(cv2, np, frame, geom,
                                                    self._refs, vmap)
                else:
                    faces = {f: ["X"] * 9 for f, _ in vmap.values()}
                    raws = {f: [(0.0, 128.0, 128.0)] * 9
                            for f, _ in vmap.values()}
                key = "".join("".join(faces[f]) for f, _ in vmap.values())

            if key == self._last_key and "X" not in key:
                self._stable_count += 1
            else:
                self._stable_count = 0
                self._last_key = key
            stable = self._stable_count >= self.STABLE_FRAMES

            if single:
                self._draw_flat(cv2, frame, geom, faces["single"], stable)
                frame = cv2.flip(frame, 1)  # mirror for natural aiming
                self._draw_flat_text(cv2, frame, geom, self._single_face,
                                     stable)
            else:
                self._draw_wireframe(cv2, frame, geom, faces, vmap, stable)
                frame = cv2.flip(frame, 1)  # mirror for natural aiming
                self._draw_text(cv2, frame, geom, vmap, stable)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
            self.frame_ready.emit(img.copy(), faces, stable, raws)
            self.msleep(30)

        cap.release()

    # -- cube localisation ---------------------------------------------------

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
    def _find_cube(cv2, np, frame) -> tuple[float, float, float] | None:
        """Locate the corner-on cube.

        Finds sticker-like quads (squares on the top face project to
        rhombi, side stickers to leaning parallelograms — hence loose
        aspect/fill limits), keeps the densest cluster of similar-sized
        ones and fits the isometric hexagon: returns (cx, cy, e) where
        (cx, cy) is the front vertex and e the projected edge length,
        or None when no plausible cube is visible.
        """
        h, w = frame.shape[:2]
        edges = CameraWorker._edge_map(cv2, np, frame)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST,
                                       cv2.CHAIN_APPROX_SIMPLE)

        lo = (min(h, w) * 0.028) ** 2   # sticker area bounds
        hi = (min(h, w) * 0.25) ** 2
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
            if not 0.40 < bw / bh < 2.30:
                continue
            if area / (bw * bh) < 0.40:
                continue
            cand.append((x + bw / 2.0, y + bh / 2.0, (bw + bh) / 2.0))

        if len(cand) < 6:
            return None

        sides = sorted(s for _, _, s in cand)
        med = sides[len(sides) // 2]
        cand = [c for c in cand if 0.5 * med < c[2] < 1.9 * med]
        if len(cand) < 6:
            return None

        # Densest spatial cluster: all 27 stickers sit within about 4.5
        # sticker-widths of any one of them.
        reach = 4.5 * med
        best: list[tuple[float, float, float]] = []
        for cx, cy, _ in cand:
            near = [c for c in cand
                    if abs(c[0] - cx) < reach and abs(c[1] - cy) < reach]
            if len(near) > len(best):
                best = near
        if len(best) < 6:
            return None

        xs = [c[0] for c in best]
        ys = [c[1] for c in best]
        cw = max(xs) - min(xs)
        ch = max(ys) - min(ys)
        if cw < 1.5 * med or ch < 1.5 * med:
            return None
        if not 0.55 < cw / ch < 1.35:   # hexagon bbox is 0.87 wide/high
            return None

        # Sticker *centres* span 1.44e horizontally and 1.67e vertically.
        e = (cw / 1.444 + ch / 1.667) / 2.0
        cx = (max(xs) + min(xs)) / 2.0
        cy = (max(ys) + min(ys)) / 2.0
        if not min(h, w) * 0.10 < e < min(h, w) * 0.75:
            return None
        return (cx, cy, e)

    @staticmethod
    def _find_flat(cv2, np, frame) -> tuple[float, float, float] | None:
        """Locate a single flat-on cube face.

        Same contour approach as :meth:`_find_cube` but with strict
        square filters, since flat-on stickers project to squares.
        Returns (x0, y0, size) of the 3x3 area or None.
        """
        h, w = frame.shape[:2]
        edges = CameraWorker._edge_map(cv2, np, frame)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST,
                                       cv2.CHAIN_APPROX_SIMPLE)

        lo = (min(h, w) * 0.035) ** 2
        hi = (min(h, w) * 0.28) ** 2
        cand: list[tuple[float, float, float]] = []
        for c in contours:
            area = cv2.contourArea(c)
            if not lo < area < hi:
                continue
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.06 * peri, True)
            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue
            x, y, bw, bh = cv2.boundingRect(approx)
            if not 0.65 < bw / bh < 1.55:
                continue
            if area / (bw * bh) < 0.62:
                continue
            cand.append((x + bw / 2.0, y + bh / 2.0, (bw + bh) / 2.0))

        if len(cand) < 5:
            return None
        sides = sorted(s for _, _, s in cand)
        med = sides[len(sides) // 2]
        cand = [c for c in cand if 0.55 * med < c[2] < 1.7 * med]
        if len(cand) < 5:
            return None

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
        if bw < 2.0 * med or bh < 2.0 * med:
            return None
        if not 0.65 < bw / bh < 1.55:
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
    def _cell_center(hexa: tuple[float, float, float], panel: str,
                     a: int, b: int) -> tuple[int, int]:
        cx, cy, e = hexa
        A, B = PANEL_BASIS[panel]
        fa, fb = (a + 0.5) / 3.0, (b + 0.5) / 3.0
        return (int(cx + e * (A[0] * fa + B[0] * fb)),
                int(cy + e * (A[1] * fa + B[1] * fb)))

    @classmethod
    def _sample_view(cls, cv2, np, frame, hexa, refs, vmap
                     ) -> tuple[dict[str, list[str]],
                                dict[str, list[tuple[float, float, float]]]]:
        """Read the 27 sticker colours of the three visible faces."""
        h, w = frame.shape[:2]
        _, _, e = hexa
        lab_img = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        r = max(3, int(e / 14))
        faces: dict[str, list[str]] = {}
        raws: dict[str, list[tuple[float, float, float]]] = {}
        for panel, (face, idx_map) in vmap.items():
            letters = ["X"] * 9
            labs = [(0.0, 128.0, 128.0)] * 9
            for a in range(3):
                for b in range(3):
                    px, py = cls._cell_center(hexa, panel, a, b)
                    px0, px1 = max(px - r, 0), min(px + r, w)
                    py0, py1 = max(py - r, 0), min(py + r, h)
                    patch = lab_img[py0:py1, px0:px1]
                    idx = idx_map[a * 3 + b]
                    if patch.size == 0:
                        continue
                    sample = (float(np.median(patch[:, :, 0])),
                              float(np.median(patch[:, :, 1])),
                              float(np.median(patch[:, :, 2])))
                    letters[idx] = classify_lab(sample, refs)
                    labs[idx] = sample
            faces[face] = letters
            raws[face] = labs
        return faces, raws

    @staticmethod
    def _sample_flat(cv2, np, frame, geom: tuple[float, float, float], refs
                     ) -> tuple[list[str], list[tuple[float, float, float]]]:
        """Read the nine stickers of a flat-on face, row-major.

        Sampled on the true (unmirrored) frame while the protocol has the
        user look straight at each face, so grid order equals facelet
        order directly.
        """
        h, w = frame.shape[:2]
        x0, y0, size = geom
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
    def _draw_flat(cv2, frame, geom, letters, stable) -> None:
        """Square 3x3 overlay for single-face mode (true frame)."""
        h, w = frame.shape[:2]
        if geom is None:
            size = min(h, w) * 0.55
            geom = ((w - size) / 2.0, (h - size) / 2.0, size)
            color = (110, 110, 110)
            letters = None
        else:
            color = (90, 220, 90) if stable else (230, 230, 230)
        x0, y0, size = (int(v) for v in geom)
        cell = size // 3
        for i in range(4):
            cv2.line(frame, (x0 + i * cell, y0),
                     (x0 + i * cell, y0 + 3 * cell), color, 2)
            cv2.line(frame, (x0, y0 + i * cell),
                     (x0 + 3 * cell, y0 + i * cell), color, 2)
        if letters is None:
            return
        for row in range(3):
            for col in range(3):
                c = letters[row * 3 + col]
                px = x0 + col * cell + cell // 2
                py = y0 + row * cell + cell // 2
                cv2.rectangle(frame, (px - 8, py - 8), (px + 8, py + 8),
                              BGR.get(c, BGR["X"]), -1)
                cv2.rectangle(frame, (px - 8, py - 8), (px + 8, py + 8),
                              (20, 20, 20), 1)

    @staticmethod
    def _draw_flat_text(cv2, frame, geom, face: str, stable) -> None:
        """Text and expected-centre label, drawn after the display flip."""
        h, w = frame.shape[:2]
        if geom is None:
            cv2.putText(frame, "Looking for the cube...",
                        (w // 2 - 150, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 230), 2)
            size = min(h, w) * 0.55
            gx, gy = w / 2.0, (h - size) / 2.0
        else:
            x0, y0, size = geom
            gx, gy = w - (x0 + size / 2.0), y0   # mirror the x centre
        want = EXPECTED_CENTER[face]
        px, py = int(gx), max(int(gy) - 22, 22)
        cv2.circle(frame, (px, py), 14, BGR[want], -1)
        cv2.circle(frame, (px, py), 14, (20, 20, 20), 2)
        cv2.putText(frame, face, (px - 8, py + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
        if stable and geom is not None:
            cv2.putText(frame, "LOCKED", (px + 28, py + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (90, 220, 90), 2)

    @classmethod
    def _draw_wireframe(cls, cv2, frame, hexa, faces, vmap, stable) -> None:
        """Drawn on the *true* frame, before the display flip."""
        h, w = frame.shape[:2]
        found = hexa is not None
        if not found:   # faint aiming guide in the middle
            hexa = (w / 2.0, h / 2.0 - min(h, w) * 0.05, min(h, w) * 0.30)
            color = (110, 110, 110)
        else:
            color = (90, 220, 90) if stable else (230, 230, 230)
        cx, cy, e = hexa

        def pt(vx: float, vy: float) -> tuple[int, int]:
            return (int(cx + e * vx), int(cy + e * vy))

        # Outline + the three edges meeting at the front vertex.
        hexagon = [pt(0, 1), pt(-SQRT3_2, 0.5), pt(-SQRT3_2, -0.5),
                   pt(0, -1), pt(SQRT3_2, -0.5), pt(SQRT3_2, 0.5)]
        for i in range(6):
            cv2.line(frame, hexagon[i], hexagon[(i + 1) % 6], color, 2)
        for vx, vy in (UL, UR, DN):
            cv2.line(frame, pt(0, 0), pt(vx, vy), color, 2)
        # Grid subdivisions: two lines per direction per panel.
        for A, B in (PANEL_BASIS[p] for p in ("top", "left", "right")):
            for t in (1 / 3, 2 / 3):
                cv2.line(frame,
                         pt(A[0] * t, A[1] * t),
                         pt(A[0] * t + B[0], A[1] * t + B[1]), color, 1)
                cv2.line(frame,
                         pt(B[0] * t, B[1] * t),
                         pt(B[0] * t + A[0], B[1] * t + A[1]), color, 1)
        # Detected colour chips at each cell centre.
        if found:
            for panel, (face, idx_map) in vmap.items():
                for a in range(3):
                    for b in range(3):
                        px, py = cls._cell_center(hexa, panel, a, b)
                        c = faces[face][idx_map[a * 3 + b]]
                        cv2.rectangle(frame, (px - 8, py - 8),
                                      (px + 8, py + 8),
                                      BGR.get(c, BGR["X"]), -1)
                        cv2.rectangle(frame, (px - 8, py - 8),
                                      (px + 8, py + 8), (20, 20, 20), 1)

    @staticmethod
    def _draw_text(cv2, frame, hexa, vmap, stable) -> None:
        """Drawn after the flip so text reads normally on screen."""
        h, w = frame.shape[:2]
        if hexa is None:
            cv2.putText(frame, "Looking for the cube...",
                        (w // 2 - 150, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (230, 230, 230), 2)
            cx, cy, e = w / 2.0, h / 2.0 - min(h, w) * 0.05, min(h, w) * 0.30
        else:
            cx, cy, e = hexa
            cx = w - cx  # mirror
        # Expected-colour labels at each panel centre.
        centres = {
            "top": (cx, cy - 0.55 * e),
            "left": (cx + 0.433 * e, cy + 0.25 * e),   # mirrored: F on right
            "right": (cx - 0.433 * e, cy + 0.25 * e),
        }
        for panel, (face, _) in vmap.items():
            want = EXPECTED_CENTER[face]
            px, py = (int(v) for v in centres[panel])
            cv2.circle(frame, (px, py), 14, BGR[want], -1)
            cv2.circle(frame, (px, py), 14, (20, 20, 20), 2)
            cv2.putText(frame, face, (px - 8, py + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (20, 20, 20), 2)
        if stable and hexa is not None:
            cv2.putText(frame, "LOCKED", (int(cx) - 55, max(int(cy - e) - 12,
                                                            25)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (90, 220, 90), 2)
