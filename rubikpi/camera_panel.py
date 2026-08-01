"""Left frame: live camera view and guided face scanning.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from rubikpi.vision import (
    COLOR_NAME, EXPECTED_CENTER, SCAN_VIEWS, CameraWorker,
)

#: All six faces in scan order (view 1 then view 2).
ALL_FACES: list[str] = [f for faces, _ in SCAN_VIEWS for f in faces]


class CameraPanel(QWidget):
    """Camera preview + scan progress.  Emits faces as they are captured."""

    face_captured = pyqtSignal(str, list)   # face letter, 9 colour letters
    scan_complete = pyqtSignal()
    scan_reset = pyqtSignal()
    demo_requested = pyqtSignal()
    status = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.worker: CameraWorker | None = None
        self.view_index = 0
        self.captured: dict[str, list[str]] = {}
        self._last_faces: dict[str, list[str]] = {}
        self._last_raws: dict[str, list[tuple[float, float, float]]] = {}
        self._last_stable = False
        self._build_ui()
        self._refresh_progress()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)

        title = QLabel("1 · Camera scan")
        title.setObjectName("paneTitle")
        lay.addWidget(title)

        self.video = QLabel("Camera is off.\n\nPress “Start camera”, or use a "
                            "Demo scramble\nto try RubikPI without a camera.")
        self.video.setObjectName("videoView")
        self.video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video.setMinimumSize(320, 240)
        self.video.setScaledContents(False)
        lay.addWidget(self.video, stretch=1)

        self.instruction = QLabel("")
        self.instruction.setWordWrap(True)
        self.instruction.setObjectName("instruction")
        lay.addWidget(self.instruction)

        # Scan progress: one chip per face.
        chips = QHBoxLayout()
        chips.addWidget(QLabel("Faces:"))
        self.chips: dict[str, QLabel] = {}
        for face in ALL_FACES:
            chip = QLabel(face)
            chip.setFixedSize(30, 30)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setObjectName("faceChip")
            self.chips[face] = chip
            chips.addWidget(chip)
        chips.addStretch(1)
        lay.addLayout(chips)

        grid = QGridLayout()
        self.btn_start = QPushButton("Start camera")
        self.btn_start.clicked.connect(self.toggle_camera)
        grid.addWidget(self.btn_start, 0, 0)

        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel("Camera #"))
        self.cam_index = QSpinBox()
        self.cam_index.setRange(0, 8)
        cam_row.addWidget(self.cam_index)
        cam_row.addStretch(1)
        grid.addLayout(cam_row, 0, 1)

        self.btn_capture = QPushButton("Capture view (Space)")
        self.btn_capture.clicked.connect(self.capture_now)
        self.btn_capture.setEnabled(False)
        grid.addWidget(self.btn_capture, 1, 0)

        self.auto_capture = QCheckBox("Auto-capture when steady")
        self.auto_capture.setChecked(True)
        grid.addWidget(self.auto_capture, 1, 1)

        self.btn_redo = QPushButton("Redo previous view")
        self.btn_redo.clicked.connect(self.redo_previous)
        grid.addWidget(self.btn_redo, 2, 0)

        self.btn_reset = QPushButton("Reset scan")
        self.btn_reset.clicked.connect(self.reset_scan)
        grid.addWidget(self.btn_reset, 2, 1)
        lay.addLayout(grid)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(line)

        self.btn_demo = QPushButton("🎲  Demo scramble (no camera)")
        self.btn_demo.clicked.connect(self.demo_requested.emit)
        lay.addWidget(self.btn_demo)

    # -- camera lifecycle ----------------------------------------------------

    def toggle_camera(self) -> None:
        if self.worker is not None:
            self.stop_camera()
            return
        self.worker = CameraWorker(self.cam_index.value(), self)
        self.worker.frame_ready.connect(self._on_frame)
        self.worker.camera_error.connect(self._on_camera_error)
        self.worker.set_view(self.view_index if self.view_index < 2 else 0)
        self.worker.start()
        self.btn_start.setText("Stop camera")
        self.btn_capture.setEnabled(True)
        self.status.emit("Camera started — show the cube corner-on.")
        self._refresh_progress()

    def stop_camera(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker = None
        self.btn_start.setText("Start camera")
        self.btn_capture.setEnabled(False)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.stop_camera()
        super().closeEvent(event)

    # -- frame handling ------------------------------------------------------

    def _on_frame(self, image: QImage, faces: dict, stable: bool,
                  raws: dict) -> None:
        pix = QPixmap.fromImage(image).scaled(
            self.video.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.video.setPixmap(pix)
        self._last_faces = dict(faces)
        self._last_raws = dict(raws)
        newly_stable = stable and not self._last_stable
        self._last_stable = stable
        if (newly_stable and self.auto_capture.isChecked()
                and self.view_index < len(SCAN_VIEWS)):
            wrong = self._wrong_centres()
            if not wrong:
                self.capture_now()
            else:
                self.status.emit(
                    "Wrong view? " + "; ".join(
                        f"{face} centre should be "
                        f"{COLOR_NAME[EXPECTED_CENTER[face]].upper()}, "
                        f"I see {COLOR_NAME.get(got, got)}"
                        for face, got in wrong)
                    + ". Turn the cube, or press Capture to force it.")

    def _wrong_centres(self) -> list[tuple[str, str]]:
        """(face, seen-colour) for every visible centre that mismatches."""
        wrong = []
        for face in SCAN_VIEWS[self.view_index][0]:
            got = self._last_faces.get(face, ["X"] * 9)[4]
            if got != EXPECTED_CENTER[face]:
                wrong.append((face, got))
        return wrong

    def _on_camera_error(self, message: str) -> None:
        self.stop_camera()
        self.video.setText(message)
        self.status.emit(message.replace("\n", " "))

    # -- scan flow -----------------------------------------------------------

    def capture_now(self) -> None:
        if self.view_index >= len(SCAN_VIEWS) or not self._last_faces:
            return
        view_faces = SCAN_VIEWS[self.view_index][0]
        if any("X" in self._last_faces.get(f, ["X"]) for f in view_faces):
            self.status.emit("No cube detected — hold the cube corner-on "
                             "inside the guide, close to the camera.")
            return
        for face in view_faces:
            colors = list(self._last_faces[face])
            # The protocol fixes which centres this view shows: feed the
            # measured colour back so the remaining faces classify against
            # this cube's real stickers under this lighting.
            if (self.worker is not None and face in self._last_raws
                    and colors[4] == EXPECTED_CENTER[face]):
                self.worker.learn_center(EXPECTED_CENTER[face],
                                         self._last_raws[face][4])
            self.captured[face] = colors
            self.face_captured.emit(face, colors)
        self.view_index += 1
        if self.worker is not None:
            self.worker.set_view(min(self.view_index, len(SCAN_VIEWS) - 1))
        self._refresh_progress()
        if self.view_index >= len(SCAN_VIEWS):
            self.status.emit("All 6 faces captured!")
            self.scan_complete.emit()
        else:
            _, instr = SCAN_VIEWS[self.view_index]
            self.status.emit(f"View captured ({', '.join(view_faces)}) — "
                             f"now: {instr}")

    def redo_previous(self) -> None:
        if self.view_index == 0:
            return
        self.view_index -= 1
        for face in SCAN_VIEWS[self.view_index][0]:
            self.captured.pop(face, None)
        if self.worker is not None:
            self.worker.set_view(self.view_index)
        self._refresh_progress()
        faces = ", ".join(SCAN_VIEWS[self.view_index][0])
        self.status.emit(f"Rescanning view {self.view_index + 1} ({faces}).")

    def reset_scan(self) -> None:
        self.view_index = 0
        self.captured.clear()
        if self.worker is not None:
            self.worker.set_view(0)
        self._refresh_progress()
        self.scan_reset.emit()
        self.status.emit("Scan reset — show WHITE on top, corner-on.")

    def mark_demo(self) -> None:
        """Called when a demo scramble replaces the scan."""
        self.view_index = len(SCAN_VIEWS)
        for face in ALL_FACES:
            self.captured[face] = ["?"] * 9
        self._refresh_progress()

    # -- cosmetics -----------------------------------------------------------

    def _refresh_progress(self) -> None:
        current = (SCAN_VIEWS[self.view_index][0]
                   if self.view_index < len(SCAN_VIEWS) else ())
        for face in ALL_FACES:
            chip = self.chips[face]
            if face in self.captured:
                chip.setStyleSheet(
                    "background:#2f7d4f;color:#fff;border-radius:6px;"
                    "font-weight:bold;")
            elif face in current:
                chip.setStyleSheet(
                    "background:#e8b93c;color:#222;border-radius:6px;"
                    "font-weight:bold;")
            else:
                chip.setStyleSheet(
                    "background:#3a3f46;color:#9aa0a8;border-radius:6px;")
        if self.view_index < len(SCAN_VIEWS):
            faces, instr = SCAN_VIEWS[self.view_index]
            self.instruction.setText(
                f"View {self.view_index + 1}/2 — faces "
                f"{'/'.join(faces)}:  {instr}")
        else:
            self.instruction.setText("Scan complete ✔ — cube captured. "
                                     "Press Solve, or Reset scan to start over.")
