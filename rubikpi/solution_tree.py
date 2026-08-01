"""Right frame: solution stages and the tree of possibilities.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Two roots live in the tree:

* **Solution** — the solver's moves grouped by stage (Cross, F2L, ...).
  Double-clicking a move asks the main window to play up to that point.
* **Possibilities from here** — every legal move from the current state,
  expanded lazily up to a few plies.  Each node shows how far from solved
  the resulting position is, so you can literally see which branches make
  progress and which ones drift away.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from rubikpi.cube import ALL_MOVES, Cube
from rubikpi.solver import Solution

_ROLE_MOVE_INDEX = Qt.ItemDataRole.UserRole
_ROLE_STATE = Qt.ItemDataRole.UserRole + 1   # facelet snapshot for lazy nodes
_ROLE_LAZY = Qt.ItemDataRole.UserRole + 2

MAX_DEPTH = 3

_GOOD = QBrush(QColor("#59c98a"))
_BAD = QBrush(QColor("#d1707c"))
_NEUTRAL = QBrush(QColor("#c6cad1"))
_DIM = QBrush(QColor("#8a9099"))


class SolutionTreePanel(QWidget):
    """Tree of the solution stages and of the possible next moves."""

    jump_requested = pyqtSignal(int)  # play the solution up to move index

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cube = Cube.unknown()
        self.solution: Solution | None = None
        self.progress = 0  # moves of the solution already played

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        title = QLabel("3 · Tree of possibilities")
        title.setObjectName("paneTitle")
        lay.addWidget(title)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Move / stage", "Off"])
        self.tree.setColumnWidth(0, 240)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        lay.addWidget(self.tree, stretch=1)

        self.hint = QLabel("Double-click a solution move to jump there.\n"
                           "“Off” = stickers away from solved.")
        self.hint.setObjectName("hintLabel")
        lay.addWidget(self.hint)

    # -- public API ----------------------------------------------------------

    def set_state(self, cube: Cube, solution: Solution | None,
                  progress: int) -> None:
        """Rebuild the tree for a new cube state / solution / progress."""
        self.cube = cube.copy()
        self.solution = solution
        self.progress = progress
        self.tree.clear()
        if solution is not None and solution.moves:
            self._build_solution_root()
        self._build_possibilities_root()

    # -- solution root -------------------------------------------------------

    def _build_solution_root(self) -> None:
        assert self.solution is not None
        sol = self.solution
        done = self.progress
        root = QTreeWidgetItem(
            [f"Solution — {len(sol.moves)} moves ({sol.backend})", ""])
        bold = QFont(self.tree.font())
        bold.setBold(True)
        root.setFont(0, bold)
        self.tree.addTopLevelItem(root)

        for stage in sol.stages:
            end = stage.start_index + len(stage.moves)
            state = ("✔" if end <= done
                     else "▶" if stage.start_index <= done else "•")
            item = QTreeWidgetItem(
                [f"{state} {stage.label}  ({len(stage.moves)} moves)", ""])
            item.setFont(0, bold)
            item.setForeground(0, _GOOD if end <= done else _NEUTRAL)
            root.addChild(item)
            for k, move in enumerate(stage.moves):
                idx = stage.start_index + k
                child = QTreeWidgetItem([f"{idx + 1:>3}.  {move}", ""])
                child.setData(0, _ROLE_MOVE_INDEX, idx)
                if idx < done:
                    child.setForeground(0, _DIM)
                elif idx == done:
                    child.setForeground(0, QBrush(QColor("#e8b93c")))
                    child.setFont(0, bold)
                item.addChild(child)
            item.setExpanded(stage.start_index <= done < end
                             or (done == 0 and stage.start_index == 0))
        root.setExpanded(True)

    # -- possibilities root ---------------------------------------------------

    def _build_possibilities_root(self) -> None:
        root = QTreeWidgetItem(
            [f"Possibilities from here — {self.cube.misplaced_count()} off",
             ""])
        bold = QFont(self.tree.font())
        bold.setBold(True)
        root.setFont(0, bold)
        self.tree.addTopLevelItem(root)
        if not self.cube.is_full():
            root.addChild(QTreeWidgetItem(
                ["(scan the cube or load a demo scramble first)", ""]))
            return
        self._add_children(root, self.cube, depth=1)
        root.setExpanded(True)

    def _add_children(self, parent: QTreeWidgetItem, cube: Cube,
                      depth: int) -> None:
        base = cube.misplaced_count()
        entries = []
        for move in ALL_MOVES:
            nxt = cube.moved(move)
            entries.append((nxt.misplaced_count(), move, nxt))
        entries.sort(key=lambda e: (e[0], e[1]))
        for off, move, nxt in entries:
            item = QTreeWidgetItem([move, str(off)])
            delta = off - base
            item.setForeground(0, _GOOD if delta < 0
                               else _BAD if delta > 0 else _NEUTRAL)
            item.setForeground(1, item.foreground(0))
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight)
            if off == 0:
                item.setText(0, f"{move}   🎉 solves it!")
            parent.addChild(item)
            if depth < MAX_DEPTH and off != 0:
                item.setData(0, _ROLE_STATE, nxt.serialise())
                item.setData(0, _ROLE_LAZY, depth)
                item.addChild(QTreeWidgetItem(["…", ""]))  # placeholder

    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        depth = item.data(0, _ROLE_LAZY)
        if depth is None:
            return
        item.setData(0, _ROLE_LAZY, None)
        item.takeChildren()
        cube = Cube.from_serialised(item.data(0, _ROLE_STATE))
        self._add_children(item, cube, depth + 1)

    def _on_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        idx = item.data(0, _ROLE_MOVE_INDEX)
        if idx is not None:
            self.jump_requested.emit(int(idx) + 1)
