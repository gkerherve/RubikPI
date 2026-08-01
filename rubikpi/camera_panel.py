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
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from rubikpi.vision import (
    COLOR_NAME, EXPECTED_CENTER, SCAN_STEPS, SCAN_VIEWS, CameraWorker,
)

#: All six faces in corner-view order, used for the progress chips.
ALL_FACES: list[str] = [f for faces, _ in SCAN_VIEWS for f in faces]


class CameraPanel(QWidget):
    """Camera preview + scan progress.  Emits faces as they are captured."""

    face_captured = pyqtSignal(str, list)   # face letter, 9 colour letters
    scan_complete = pyqtSignal()
    scan_reset = pyqtSignal()
    demo_requested = pyqtSignal()
    status = pyqtSignal(str)
    #: Live corner-view reading for follow-along mode: {face: 9 letters}.
    live_reading = pyqtSignal(object, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.worker: CameraWorker | None = None
        self.follow = False
        self.step_index = 0
        self.captured: dict[str, list[str]] = {}
        self._last_faces: dict[str, list[str]] = {}
        self._last_raws: dict[str, list[tuple[float, float, float]]] = {}
        self._last_stable = False
        self._build_ui()
        self._refresh_progress()

    # -- protocol helpers ----------------------------------------------------

    @property
    def single_mode(self) -> bool:
        return self.scan_mode.currentIndex() == 1

    def _steps(self) -> list[tuple[tuple[str, ...], str]]:
        """Current protocol as (faces-in-step, instruction) tuples."""
        if self.single_mode:
            return [((face,), instr) for face, instr in SCAN_STEPS]
        return [(faces, instr) for faces, instr in SCAN_VIEWS]

    def _step_letters(self, face: str) -> list[str] | None:
        """The last-seen 9 letters for *face* in the current step."""
        key = "single" if self.single_mode else face
        return self._last_faces.get(key)

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

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Scan mode"))
        self.scan_mode = QComboBox()
        self.scan_mode.addItems([
            "Corner view — 3 faces, 2 shots",
            "One face at a time — 6 shots (easier)",
        ])
        self.scan_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.scan_mode, stretch=1)
        lay.addLayout(mode_row)

        grid = QGridLayout()
        self.btn_start = QPushButton("Start camera")
        self.btn_start.clicked.connect(self.toggle_camera)
        grid.addWidget(self.btn_start, 0, 0)

        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel("Camera"))
        self.cam_source = QLineEdit("0")
        self.cam_source.setPlaceholderText("0, 1, … or http://phone:8080/video")
        self.cam_source.setToolTip(
            "A camera number (0 is the default webcam) or a stream URL.\n"
            "Phone as camera:\n"
            "  • Windows 11 + Android: Settings > Bluetooth & devices >\n"
            "    Mobile devices > use phone as connected camera, then try 1 "
            "or 2 here.\n"
            "  • Any phone: run the ‘IP Webcam’ app and enter its URL, e.g.\n"
            "    http://192.168.1.23:8080/video\n"
            "  • Iriun / DroidCam / Camo appear as an extra camera number.")
        cam_row.addWidget(self.cam_source, stretch=1)
        grid.addLayout(cam_row, 0, 1)

        self.btn_capture = QPushButton("Capture (Space)")
        self.btn_capture.clicked.connect(self.capture_now)
        self.btn_capture.setEnabled(False)
        grid.addWidget(self.btn_capture, 1, 0)

        self.auto_capture = QCheckBox("Auto-capture when steady")
        self.auto_capture.setChecked(True)
        grid.addWidget(self.auto_capture, 1, 1)

        self.btn_redo = QPushButton("Redo previous step")
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
        self.worker = CameraWorker(self.cam_source.text(), self)
        self.worker.frame_ready.connect(self._on_frame)
        self.worker.camera_error.connect(self._on_camera_error)
        self._configure_worker_step()
        self.worker.start()
        self.btn_start.setText("Stop camera")
        self.btn_capture.setEnabled(True)
        self.status.emit("Camera started — follow the on-screen guide.")
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

    def set_follow(self, on: bool) -> None:
        """Follow-along mode: keep reading three faces, never auto-capture."""
        self.follow = on
        self.scan_mode.setEnabled(not on)
        self.btn_capture.setEnabled(not on and self.worker is not None)
        self._configure_worker_step()
        if on:
            self.instruction.setText(
                "Follow-along: hold the cube corner-on and make the move "
                "shown in the middle panel — RubikPI watches and keeps up.")
        else:
            self._refresh_progress()

    def _configure_worker_step(self) -> None:
        """Point the worker at the current mode and step."""
        if self.worker is None:
            return
        if self.follow:
            # Tracking always uses the canonical corner view: three faces
            # give enough evidence to tell a turn from a rotation.
            self.worker.set_mode("corner")
            self.worker.set_view(0)
            return
        steps = self._steps()
        idx = min(self.step_index, len(steps) - 1)
        if self.single_mode:
            self.worker.set_mode("single")
            self.worker.set_single_face(steps[idx][0][0])
        else:
            self.worker.set_mode("corner")
            self.worker.set_view(idx)

    def _on_mode_changed(self) -> None:
        self.reset_scan()

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
        if self.follow:
            self.live_reading.emit(dict(faces), stable)
            return
        if (newly_stable and self.auto_capture.isChecked()
                and self.step_index < len(self._steps())):
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
        for face in self._steps()[self.step_index][0]:
            letters = self._step_letters(face) or ["X"] * 9
            if letters[4] != EXPECTED_CENTER[face]:
                wrong.append((face, letters[4]))
        return wrong

    def _on_camera_error(self, message: str) -> None:
        self.stop_camera()
        self.video.setText(message)
        self.status.emit(message.replace("\n", " "))

    # -- scan flow -----------------------------------------------------------

    def capture_now(self) -> None:
        steps = self._steps()
        if self.step_index >= len(steps) or not self._last_faces:
            return
        step_faces = steps[self.step_index][0]
        if any("X" in (self._step_letters(f) or ["X"]) for f in step_faces):
            self.status.emit("No cube detected — hold the cube inside the "
                             "guide, close to the camera.")
            return
        for face in step_faces:
            colors = list(self._step_letters(face))
            # The protocol fixes which centres this step shows: feed the
            # measured colour back so the remaining faces classify against
            # this cube's real stickers under this lighting.
            raw_key = "single" if self.single_mode else face
            if (self.worker is not None and raw_key in self._last_raws
                    and colors[4] == EXPECTED_CENTER[face]):
                self.worker.learn_center(EXPECTED_CENTER[face],
                                         self._last_raws[raw_key][4])
            self.captured[face] = colors
            self.face_captured.emit(face, colors)
        self.step_index += 1
        self._configure_worker_step()
        self._refresh_progress()
        if self.step_index >= len(steps):
            self.status.emit("All 6 faces captured!")
            self.scan_complete.emit()
        else:
            _, instr = steps[self.step_index]
            self.status.emit(f"Captured {', '.join(step_faces)} — "
                             f"now: {instr}")

    def redo_previous(self) -> None:
        if self.step_index == 0:
            return
        self.step_index -= 1
        faces = self._steps()[self.step_index][0]
        for face in faces:
            self.captured.pop(face, None)
        self._configure_worker_step()
        self._refresh_progress()
        self.status.emit(f"Rescanning {', '.join(faces)}.")

    def reset_scan(self) -> None:
        self.step_index = 0
        self.captured.clear()
        self._configure_worker_step()
        self._refresh_progress()
        self.scan_reset.emit()
        self.status.emit("Scan reset — follow the on-screen guide.")

    def mark_demo(self) -> None:
        """Called when a demo scramble replaces the scan."""
        self.step_index = len(self._steps())
        for face in ALL_FACES:
            self.captured[face] = ["?"] * 9
        self._refresh_progress()

    # -- cosmetics -----------------------------------------------------------

    def _refresh_progress(self) -> None:
        steps = self._steps()
        current = (steps[self.step_index][0]
                   if self.step_index < len(steps) else ())
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
        if self.step_index < len(steps):
            faces, instr = steps[self.step_index]
            self.instruction.setText(
                f"Step {self.step_index + 1}/{len(steps)} — "
                f"{'/'.join(faces)}:  {instr}")
        else:
            self.instruction.setText("Scan complete ✔ — cube captured. "
                                     "Press Solve, or Reset scan to start over.")
