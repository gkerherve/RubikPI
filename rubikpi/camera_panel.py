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
    COLOR_NAME, EXPECTED_CENTER, SCAN_STEPS, CameraWorker, unmirror,
)


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
        self.scan_index = 0
        self.captured: dict[str, list[str]] = {}
        self._last_grid: list[str] = []
        self._last_raw: list[tuple[float, float, float]] = []
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
        for face, _ in SCAN_STEPS:
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

        self.btn_capture = QPushButton("Capture face (Space)")
        self.btn_capture.clicked.connect(self.capture_now)
        self.btn_capture.setEnabled(False)
        grid.addWidget(self.btn_capture, 1, 0)

        self.auto_capture = QCheckBox("Auto-capture when steady")
        self.auto_capture.setChecked(True)
        grid.addWidget(self.auto_capture, 1, 1)

        self.btn_redo = QPushButton("Redo previous face")
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
        self.worker.start()
        self.btn_start.setText("Stop camera")
        self.btn_capture.setEnabled(True)
        self.status.emit("Camera started — show the first face.")
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

    def _on_frame(self, image: QImage, grid: list, stable: bool,
                  raw: list) -> None:
        pix = QPixmap.fromImage(image).scaled(
            self.video.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.video.setPixmap(pix)
        self._last_grid = list(grid)
        self._last_raw = list(raw)
        newly_stable = stable and not self._last_stable
        self._last_stable = stable
        if (newly_stable and self.auto_capture.isChecked()
                and self.scan_index < len(SCAN_STEPS)):
            face, _ = SCAN_STEPS[self.scan_index]
            want = EXPECTED_CENTER[face]
            got = grid[4]
            if got == want:
                self.capture_now()
            else:
                self.status.emit(
                    f"Face {face} needs a {COLOR_NAME[want].upper()} centre "
                    f"— I see {COLOR_NAME.get(got, got)}. Turn the cube, or "
                    "press Capture to force it.")

    def _on_camera_error(self, message: str) -> None:
        self.stop_camera()
        self.video.setText(message)
        self.status.emit(message.replace("\n", " "))

    # -- scan flow -----------------------------------------------------------

    def capture_now(self) -> None:
        if self.scan_index >= len(SCAN_STEPS) or not self._last_grid:
            return
        if "X" in self._last_grid:
            self.status.emit("No cube detected — hold the face flat towards "
                             "the camera, filling the green square.")
            return
        face, _ = SCAN_STEPS[self.scan_index]
        colors = unmirror(self._last_grid)
        # The protocol fixes which centre this step shows: feed its measured
        # colour back to the worker so later faces classify against this
        # cube's real stickers under this lighting.
        if (self.worker is not None and self._last_raw
                and colors[4] == EXPECTED_CENTER[face]):
            self.worker.learn_center(EXPECTED_CENTER[face], self._last_raw[4])
        self.captured[face] = colors
        self.face_captured.emit(face, colors)
        self.scan_index += 1
        self._refresh_progress()
        if self.scan_index >= len(SCAN_STEPS):
            self.status.emit("All 6 faces captured!")
            self.scan_complete.emit()
        else:
            nxt, instr = SCAN_STEPS[self.scan_index]
            self.status.emit(f"Face {face} captured — next: {nxt}. {instr}")

    def redo_previous(self) -> None:
        if self.scan_index == 0:
            return
        self.scan_index -= 1
        face, _ = SCAN_STEPS[self.scan_index]
        self.captured.pop(face, None)
        self._refresh_progress()
        self.status.emit(f"Rescanning face {face}.")

    def reset_scan(self) -> None:
        self.scan_index = 0
        self.captured.clear()
        self._refresh_progress()
        self.scan_reset.emit()
        self.status.emit("Scan reset — show the green-centre face.")

    def mark_demo(self) -> None:
        """Called when a demo scramble replaces the scan."""
        self.scan_index = len(SCAN_STEPS)
        for face, _ in SCAN_STEPS:
            self.captured[face] = ["?"] * 9
        self._refresh_progress()

    # -- cosmetics -----------------------------------------------------------

    def _refresh_progress(self) -> None:
        for i, (face, _) in enumerate(SCAN_STEPS):
            chip = self.chips[face]
            if face in self.captured:
                chip.setStyleSheet(
                    "background:#2f7d4f;color:#fff;border-radius:6px;"
                    "font-weight:bold;")
            elif i == self.scan_index:
                chip.setStyleSheet(
                    "background:#e8b93c;color:#222;border-radius:6px;"
                    "font-weight:bold;")
            else:
                chip.setStyleSheet(
                    "background:#3a3f46;color:#9aa0a8;border-radius:6px;")
        if self.scan_index < len(SCAN_STEPS):
            face, instr = SCAN_STEPS[self.scan_index]
            self.instruction.setText(f"Scan {self.scan_index + 1}/6 — face "
                                     f"{face}:  {instr}")
        else:
            self.instruction.setText("Scan complete ✔ — cube captured. "
                                     "Press Solve, or Reset scan to start over.")
