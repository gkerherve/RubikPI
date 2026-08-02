"""Right frame: the steps to solve, in plain words.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

The panel leads with what to do *now* — a big card showing the next move
spelled out ("turn the RIGHT face clockwise") — followed by the numbered
list of remaining moves grouped by stage.  Double-clicking any move jumps
there.

The old move-by-move explorer is still available, folded away behind
"What-if explorer", for when you want to see where other moves lead
rather than be told what to do.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QGroupBox, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from rubikpi.cube import (
    ALL_MOVES, COLOR_NAME, DEFAULT_SCHEME, Cube, held_faces,
)
from rubikpi.solver import Solution

_ROLE_MOVE_INDEX = Qt.ItemDataRole.UserRole
_ROLE_STATE = Qt.ItemDataRole.UserRole + 1   # facelet snapshot for lazy nodes
_ROLE_LAZY = Qt.ItemDataRole.UserRole + 2

MAX_DEPTH = 3

_GOOD = QBrush(QColor("#59c98a"))
_BAD = QBrush(QColor("#d1707c"))
_NEUTRAL = QBrush(QColor("#c6cad1"))
_DIM = QBrush(QColor("#8a9099"))

#: Which face each letter turns, in words.
FACE_WORDS = {
    "U": "top", "D": "bottom", "L": "left", "R": "right",
    "F": "front", "B": "back",
    "M": "middle slice (follow the left face)",
    "E": "middle slice (follow the bottom face)",
    "S": "middle slice (follow the front face)",
}

#: Where each position sits from the point of view of the person holding
#: the cube (the camera is on the other side, looking back at them).
POSITION_WORDS = {
    "R": "on your right", "L": "on your left", "U": "on top",
    "D": "underneath", "F": "facing you", "B": "facing the camera",
}


def move_in_words(move: str, held: dict[str, str] | None = None,
                  scheme: dict[str, str] | None = None) -> str:
    """Spell a move out unambiguously.

    Face letters alone are ambiguous when the camera looks at the cube
    from the opposite side to you — your right is its left.  Naming the
    *colour* removes all doubt, and *held* (see :func:`cube.held_faces`)
    adds where that colour is as you are holding it.
    """
    if not move:
        return "—"
    core = move[0]
    if move.endswith("2"):
        turn = "half a turn (180°)"
    elif move.endswith("'"):
        turn = "anticlockwise"
    else:
        turn = "clockwise"
    if core in ("M", "E", "S"):
        return f"turn the {FACE_WORDS[core]} {turn}"

    scheme = scheme or DEFAULT_SCHEME
    colour = COLOR_NAME.get(scheme.get(core, ""), "").upper()
    where = ""
    if held:
        position = {face: pos for pos, face in held.items()}.get(core)
        if position:
            where = f" ({POSITION_WORDS[position]})"
    wide = " and the slice behind it" if move[1:2] == "w" else ""
    if colour:
        return f"turn the {colour} face{where}{wide} {turn}"
    return f"turn the {FACE_WORDS.get(core, core).upper()} face{wide} {turn}"


class SolutionTreePanel(QWidget):
    """Next-move card, the staged move list, and an optional explorer."""

    jump_requested = pyqtSignal(int)  # play the solution up to move index

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cube = Cube.unknown()
        self.solution: Solution | None = None
        self.progress = 0  # moves of the solution already played
        #: How the user holds the cube — set from the camera position, so
        #: "on your right" is right for them and not for the camera.
        self.held: dict[str, str] = held_faces("F", "U")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        title = QLabel("3 · What to do")
        title.setObjectName("paneTitle")
        lay.addWidget(title)

        # -- the "do this now" card -----------------------------------------
        self.card = QGroupBox("Next move")
        card_lay = QVBoxLayout(self.card)
        self.next_move = QLabel("—")
        self.next_move.setObjectName("nextMove")
        self.next_move.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self.next_move)
        self.next_words = QLabel("Scan your cube and press Solve.")
        self.next_words.setObjectName("nextWords")
        self.next_words.setWordWrap(True)
        self.next_words.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self.next_words)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("hintLabel")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self.progress_label)
        lay.addWidget(self.card)

        # -- the staged move list -------------------------------------------
        self.steps = QTreeWidget()
        self.steps.setHeaderLabels(["Step", "Do this"])
        self.steps.setColumnWidth(0, 120)
        self.steps.setAlternatingRowColors(True)
        self.steps.itemDoubleClicked.connect(self._on_double_clicked)
        lay.addWidget(self.steps, stretch=3)

        # -- optional explorer ----------------------------------------------
        self.explorer_box = QGroupBox("What-if explorer")
        self.explorer_box.setCheckable(True)
        self.explorer_box.setChecked(False)
        self.explorer_box.toggled.connect(self._on_explorer_toggled)
        box_lay = QVBoxLayout(self.explorer_box)
        hint = QLabel("Every move you could make from here. “Off” counts the "
                      "stickers still out of place — smaller is better.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        box_lay.addWidget(hint)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Move", "Off"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.setVisible(False)
        box_lay.addWidget(self.tree)
        lay.addWidget(self.explorer_box, stretch=2)

        self.hint = QLabel("← → step through the moves · double-click a step to jump to it.")
        self.hint.setObjectName("hintLabel")
        lay.addWidget(self.hint)

    # -- public API ----------------------------------------------------------

    def set_holding(self, held: dict[str, str]) -> None:
        """Tell the panel how the cube is being held (see camera setting)."""
        self.held = dict(held)
        self._refresh_card()
        self._refresh_steps()

    def set_state(self, cube: Cube, solution: Solution | None,
                  progress: int) -> None:
        """Rebuild the panel for a new cube state / solution / progress."""
        self.cube = cube.copy()
        self.solution = solution
        self.progress = progress
        self._refresh_card()
        self._refresh_steps()
        if self.explorer_box.isChecked():
            self._build_possibilities()

    # -- next-move card ------------------------------------------------------

    def _refresh_card(self) -> None:
        sol = self.solution
        if sol is None or not sol.moves:
            self.next_move.setText("—")
            self.next_words.setText(
                "Scan your cube and press Solve." if not self.cube.is_full()
                else "Press Solve to get the steps.")
            self.progress_label.setText("")
            return
        n = len(sol.moves)
        if self.progress >= n:
            self.next_move.setText("🎉")
            self.next_words.setText(f"Finished — solved in {n} moves.")
            self.progress_label.setText("")
            return
        move = sol.moves[self.progress]
        self.next_move.setText(move)
        self.next_words.setText(move_in_words(move, self.held))
        stage = self._stage_at(self.progress)
        stage_txt = f"{stage.label}  ·  " if stage else ""
        self.progress_label.setText(
            f"{stage_txt}move {self.progress + 1} of {n}")

    def _stage_at(self, index: int):
        if self.solution is None:
            return None
        for stage in self.solution.stages:
            if index < stage.start_index + len(stage.moves):
                return stage
        return None

    # -- staged move list ----------------------------------------------------

    def _refresh_steps(self) -> None:
        self.steps.clear()
        sol = self.solution
        if sol is None or not sol.moves:
            item = QTreeWidgetItem(
                ["", "No steps yet — scan the cube and press Solve."])
            self.steps.addTopLevelItem(item)
            return
        done = self.progress
        bold = QFont(self.steps.font())
        bold.setBold(True)
        for stage in sol.stages:
            end = stage.start_index + len(stage.moves)
            mark = "✔" if end <= done else "▶" if stage.start_index <= done \
                else "•"
            root = QTreeWidgetItem(
                [f"{mark} {stage.label}", f"{len(stage.moves)} moves"])
            root.setFont(0, bold)
            root.setForeground(0, _GOOD if end <= done else _NEUTRAL)
            self.steps.addTopLevelItem(root)
            for k, move in enumerate(stage.moves):
                idx = stage.start_index + k
                child = QTreeWidgetItem(
                    [f"{idx + 1}.  {move}", move_in_words(move, self.held)])
                child.setData(0, _ROLE_MOVE_INDEX, idx)
                if idx < done:
                    child.setForeground(0, _DIM)
                    child.setForeground(1, _DIM)
                elif idx == done:
                    child.setForeground(0, QBrush(QColor("#e8b93c")))
                    child.setForeground(1, QBrush(QColor("#e8b93c")))
                    child.setFont(0, bold)
                    child.setFont(1, bold)
                root.addChild(child)
            root.setExpanded(stage.start_index <= done < end
                             or (done == 0 and stage.start_index == 0))
        current = self._current_item()
        if current is not None:
            self.steps.scrollToItem(current)

    def _current_item(self) -> QTreeWidgetItem | None:
        """The row for the move about to be played, if it is on screen."""
        for r in range(self.steps.topLevelItemCount()):
            root = self.steps.topLevelItem(r)
            for c in range(root.childCount()):
                child = root.child(c)
                if child.data(0, _ROLE_MOVE_INDEX) == self.progress:
                    return child
        return None

    # -- what-if explorer -----------------------------------------------------

    def _on_explorer_toggled(self, on: bool) -> None:
        self.tree.setVisible(on)
        if on:
            self._build_possibilities()
        else:
            self.tree.clear()

    def _build_possibilities(self) -> None:
        self.tree.clear()
        if not self.cube.is_full():
            self.tree.addTopLevelItem(QTreeWidgetItem(
                ["(scan the cube or load a demo scramble first)", ""]))
            return
        root = QTreeWidgetItem(
            [f"From here — {self.cube.misplaced_count()} stickers off", ""])
        bold = QFont(self.tree.font())
        bold.setBold(True)
        root.setFont(0, bold)
        self.tree.addTopLevelItem(root)
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
            item = QTreeWidgetItem(
                [f"{move} — {move_in_words(move, self.held)}", str(off)])
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
