"""RubikPI main window: camera | cube view | tree of possibilities.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from __future__ import annotations

import random

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from rubikpi import __app_name__, __version__
from rubikpi.camera_panel import CameraPanel
from rubikpi.cube import Cube, invert_sequence
from rubikpi.cube_view import CubeViewWidget
from rubikpi.solution_tree import SolutionTreePanel
from rubikpi.solver import MODES, Solution, solve

STYLE = """
QMainWindow, QWidget { background: #1d2026; color: #d8dce2;
                       font-size: 13px; }
QLabel#paneTitle { font-size: 15px; font-weight: bold; color: #e8b93c;
                   padding: 2px 0 6px 0; }
QLabel#videoView { background: #14161a; border: 1px solid #30343b;
                   border-radius: 8px; color: #9aa0a8; }
QLabel#instruction { color: #8fd3a8; font-weight: bold; }
QLabel#hintLabel { color: #8a9099; font-size: 12px; }
QPushButton { background: #2b2f36; border: 1px solid #3a3f46;
              border-radius: 6px; padding: 6px 10px; }
QPushButton:hover { background: #343943; }
QPushButton:pressed { background: #23272e; }
QPushButton:disabled { color: #6a6f77; }
QPushButton#accent { background: #b7791f; border-color: #d69e2e;
                     color: #fff; font-weight: bold; }
QPushButton#accent:hover { background: #d69e2e; }
QComboBox, QSpinBox { background: #2b2f36; border: 1px solid #3a3f46;
                      border-radius: 6px; padding: 4px 8px; }
QTreeWidget { background: #171a1f; alternate-background-color: #1c2027;
              border: 1px solid #30343b; border-radius: 8px; }
QTreeWidget::item { padding: 2px; }
QHeaderView::section { background: #232730; border: none; padding: 4px;
                       color: #9aa0a8; }
QCheckBox { spacing: 6px; }
QStatusBar { color: #9aa0a8; }
QSplitter::handle { background: #30343b; width: 3px; }
"""


class SolverWorker(QThread):
    """Runs the (possibly slow) solver off the GUI thread."""

    solved_ready = pyqtSignal(object)

    def __init__(self, cube: Cube, mode: str, parent=None) -> None:
        super().__init__(parent)
        self._cube = cube.copy()
        self._mode = mode

    def run(self) -> None:
        self.solved_ready.emit(solve(self._cube, self._mode))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cube = Cube.unknown()
        self.solution: Solution | None = None
        self.progress = 0
        self.scramble: list[str] = []
        self._solver: SolverWorker | None = None

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(900)
        self.play_timer.timeout.connect(self._play_tick)

        self._build_ui()
        self._refresh_title()
        self._sync_views()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setStyleSheet(STYLE)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(splitter)

        # Left: camera.
        self.camera = CameraPanel(self)
        self.camera.face_captured.connect(self._on_face_captured)
        self.camera.scan_complete.connect(self._on_scan_complete)
        self.camera.scan_reset.connect(self._on_scan_reset)
        self.camera.demo_requested.connect(self._on_demo)
        self.camera.status.connect(self._say)
        splitter.addWidget(self.camera)

        # Middle: cube view + controls.
        mid = QWidget(self)
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(8, 8, 8, 8)
        title = QLabel("2 · Your cube")
        title.setObjectName("paneTitle")
        mv.addWidget(title)
        self.view = CubeViewWidget(mid)
        mv.addWidget(self.view, stretch=1)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        self.mode_box = QComboBox()
        for key, label in MODES.items():
            self.mode_box.addItem(label, key)
        self.mode_box.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_box, stretch=1)
        mv.addLayout(mode_row)

        ctrl = QHBoxLayout()
        self.btn_solve = QPushButton("Solve ▸")
        self.btn_solve.setObjectName("accent")
        self.btn_solve.clicked.connect(self.solve_now)
        ctrl.addWidget(self.btn_solve)
        self.btn_first = QPushButton("⏮")
        self.btn_first.clicked.connect(lambda: self.jump_to(0))
        self.btn_prev = QPushButton("◀")
        self.btn_prev.clicked.connect(self.step_back)
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next = QPushButton("▶|")
        self.btn_next.clicked.connect(self.step_forward)
        for b in (self.btn_first, self.btn_prev, self.btn_play, self.btn_next):
            ctrl.addWidget(b)
        mv.addLayout(ctrl)

        self.stage_label = QLabel("Scan your cube to begin.")
        self.stage_label.setObjectName("instruction")
        self.stage_label.setWordWrap(True)
        mv.addWidget(self.stage_label)
        splitter.addWidget(mid)

        # Right: solution tree.
        self.tree_panel = SolutionTreePanel(self)
        self.tree_panel.jump_requested.connect(self.jump_to)
        splitter.addWidget(self.tree_panel)

        splitter.setSizes([420, 480, 380])
        self.statusBar().showMessage(
            "Welcome to RubikPI — scan your cube or try a demo scramble.")

        QShortcut(QKeySequence(Qt.Key.Key_Space), self,
                  activated=self.camera.capture_now)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self,
                  activated=self.step_forward)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.step_back)
        self.resize(1320, 760)

    def _refresh_title(self) -> None:
        mode = self.mode_box.currentText() if hasattr(self, "mode_box") else ""
        self.setWindowTitle(f"{__app_name__} v{__version__} — {mode}")

    def _say(self, text: str) -> None:
        self.statusBar().showMessage(text)

    # -- scanning ------------------------------------------------------------

    def _on_face_captured(self, face: str, colors: list) -> None:
        self.cube.faces[face] = list(colors)
        self._invalidate_solution()
        self._sync_views()

    def _on_scan_complete(self) -> None:
        ok, why = self.cube.is_valid_colors()
        if ok:
            self._say("Cube captured and colour-checked — press Solve!")
            self.stage_label.setText("Cube captured ✔ — choose a mode and "
                                     "press Solve.")
        else:
            self._say(f"Scan finished but looks wrong: {why}")
            self.stage_label.setText(f"⚠ {why}  Use “Redo previous face” "
                                     "to fix the bad face.")

    def _on_scan_reset(self) -> None:
        self.cube = Cube.unknown()
        self.scramble = []
        self._invalidate_solution()
        self._sync_views()
        self.stage_label.setText("Scan your cube to begin.")

    def _on_demo(self) -> None:
        self.scramble = Cube.random_scramble(rng=random.Random())
        self.cube = Cube.solved()
        self.cube.apply_sequence(self.scramble)
        self.camera.mark_demo()
        self._invalidate_solution()
        self._sync_views()
        text = " ".join(self.scramble)
        self._say(f"Demo scramble: {text}")
        self.stage_label.setText(f"Demo scramble loaded ({text}). "
                                 "Press Solve!")

    # -- solving -------------------------------------------------------------

    def current_mode(self) -> str:
        return self.mode_box.currentData() or "beginner"

    def _on_mode_changed(self) -> None:
        self._refresh_title()
        if self.solution is not None:
            self.solve_now()  # re-solve in the new mode from current state

    def solve_now(self) -> None:
        if not self.cube.is_full():
            self._say("Scan all six faces (or load a demo scramble) first.")
            return
        if self.cube.is_solved():
            self._say("Already solved — nice cube!")
            return
        if self._solver is not None and self._solver.isRunning():
            return
        self.btn_solve.setEnabled(False)
        self.btn_solve.setText("Solving…")
        self._say("Solving…  (CFOP mode can take a little while)")
        self._solver = SolverWorker(self.cube, self.current_mode(), self)
        self._solver.solved_ready.connect(self._on_solution)
        self._solver.finished.connect(lambda: self.btn_solve.setEnabled(True))
        self._solver.start()

    def _on_solution(self, solution: Solution) -> None:
        self.btn_solve.setText("Solve ▸")
        self.btn_solve.setEnabled(True)
        if not solution.ok:
            self._say(f"Solver problem: {solution.error}")
            self.stage_label.setText(f"⚠ {solution.error}")
            return
        self.solution = solution
        self.progress = 0
        stages = ", ".join(f"{s.label} ({len(s.moves)})"
                           for s in solution.stages)
        self._say(f"Solution found: {len(solution.moves)} moves via "
                  f"{solution.backend} — {stages}")
        self._sync_views()

    def _invalidate_solution(self) -> None:
        self.play_timer.stop()
        self.btn_play.setText("▶ Play")
        self.solution = None
        self.progress = 0

    # -- playback ------------------------------------------------------------

    def step_forward(self) -> None:
        if self.solution is None or self.progress >= len(self.solution.moves):
            return
        move = self.solution.moves[self.progress]
        self.cube.apply(move)
        self.progress += 1
        self._sync_views(highlight_move=move)

    def step_back(self) -> None:
        if self.solution is None or self.progress == 0:
            return
        self.progress -= 1
        move = self.solution.moves[self.progress]
        self.cube.apply_sequence(invert_sequence([move]))
        self._sync_views(highlight_move=move + " (undone)")

    def jump_to(self, target: int) -> None:
        if self.solution is None:
            return
        target = max(0, min(target, len(self.solution.moves)))
        while self.progress < target:
            self.cube.apply(self.solution.moves[self.progress])
            self.progress += 1
        while self.progress > target:
            self.progress -= 1
            self.cube.apply_sequence(
                invert_sequence([self.solution.moves[self.progress]]))
        self._sync_views()

    def toggle_play(self) -> None:
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.btn_play.setText("▶ Play")
        elif self.solution is not None:
            self.play_timer.start()
            self.btn_play.setText("⏸ Pause")

    def _play_tick(self) -> None:
        if (self.solution is None
                or self.progress >= len(self.solution.moves)):
            self.play_timer.stop()
            self.btn_play.setText("▶ Play")
            return
        self.step_forward()

    # -- shared refresh -------------------------------------------------------

    def _sync_views(self, highlight_move: str = "") -> None:
        face = highlight_move[0] if highlight_move else None
        if face not in ("U", "R", "F", "D", "L", "B"):
            face = None
        self.view.set_cube(self.cube)
        self.view.set_highlight(face, highlight_move)
        self.tree_panel.set_state(self.cube, self.solution, self.progress)
        if self.solution is not None:
            self._update_stage_label()

    def _update_stage_label(self) -> None:
        assert self.solution is not None
        sol = self.solution
        n = len(sol.moves)
        if self.cube.is_solved() and self.progress >= n:
            self.stage_label.setText(f"🎉 Solved in {n} moves — congratulations!")
            return
        current = None
        for stage in sol.stages:
            if self.progress < stage.start_index + len(stage.moves):
                current = stage
                break
        if current is None:
            self.stage_label.setText(f"Move {self.progress}/{n}.")
            return
        nxt = (sol.moves[self.progress]
               if self.progress < n else "—")
        self.stage_label.setText(
            f"Stage: {current.label}   ·   move {self.progress}/{n}"
            f"   ·   next: {nxt}")

    # -- shutdown --------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.camera.stop_camera()
        self.play_timer.stop()
        super().closeEvent(event)
