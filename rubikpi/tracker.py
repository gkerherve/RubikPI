"""Follow-along tracking: recognise what the user just did to the cube.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

During playback the camera keeps reading the three faces it can see.
Because the app already knows the cube's state, recognising what
happened is a *matching* problem, not a general vision problem: for every
one of the 24 ways the cube can be held and every legal move (plus "no
move at all"), predict the 27 visible stickers and keep the hypothesis
that fits the camera best.

That single search answers both questions at once — whether the cube was
merely rotated (you turned it round to show the back) or actually
turned, and which move it was.

Pure Python: no Qt, no OpenCV, so it is testable headless.
"""

from __future__ import annotations

from dataclasses import dataclass

from rubikpi.cube import ALL_MOVES, Cube

#: The 24 orientations of a cube, as rotation sequences from the identity.
ORIENTATIONS: list[str] = [
    (spin + " " + tilt).strip()
    for tilt in ("", "x", "x2", "x'", "z", "z'")
    for spin in ("", "y", "y2", "y'")
]

#: Faces the camera sees in the canonical corner view (see vision.VIEW_MAPS).
VISIBLE: tuple[str, str, str] = ("U", "F", "R")

#: Basic rotations, with how they read to someone holding the cube.
ROTATION_NAMES: list[tuple[str, str]] = [
    ("y", "turned it left"),
    ("y'", "turned it right"),
    ("y2", "turned it half way round"),
    ("x", "tilted it up"),
    ("x'", "tilted it down"),
    ("x2", "flipped it over"),
    ("z", "rolled it clockwise"),
    ("z'", "rolled it anticlockwise"),
]


def _orientation_maps() -> list[dict[str, list[tuple[str, int]]]]:
    """For each orientation, where each visible facelet comes from.

    ``maps[o]["U"][i] == (face, index)`` means: when the cube is held in
    orientation *o*, the sticker seen at U[i] is the model's
    ``faces[face][index]``.
    """
    maps: list[dict[str, list[tuple[str, int]]]] = []
    for seq in ORIENTATIONS:
        probe = Cube(faces={f: [f"{f}{i}" for i in range(9)]
                            for f in ("U", "R", "F", "D", "L", "B")})
        probe.apply_sequence(seq)
        maps.append({
            face: [(probe.faces[face][i][0], int(probe.faces[face][i][1:]))
                   for i in range(9)]
            for face in VISIBLE
        })
    return maps


ORIENT_MAPS = _orientation_maps()

#: Cells compared per hypothesis (three faces of nine stickers).
CELLS = 27


@dataclass
class Match:
    """Best explanation of what the camera is showing."""

    move: str            # "" when the cube was only rotated
    orientation: int     # index into ORIENTATIONS
    score: int           # matching stickers out of 27
    runner_up: int = 0   # score of the best *different* hypothesis

    @property
    def confident(self) -> bool:
        """At most one odd sticker, and clearly better than the alternative."""
        return self.score >= CELLS - 1 and self.score > self.runner_up


def predict(cube: Cube, orientation: int) -> dict[str, list[str]]:
    """The 27 stickers a camera would see for *cube* held that way."""
    omap = ORIENT_MAPS[orientation]
    return {face: [cube.faces[f][i] for f, i in omap[face]]
            for face in VISIBLE}


def _score(cube: Cube, orientation: int,
           observed: dict[str, list[str]]) -> int:
    omap = ORIENT_MAPS[orientation]
    hits = 0
    for face in VISIBLE:
        seen = observed.get(face)
        if not seen:
            continue
        row = omap[face]
        faces = cube.faces
        for i in range(9):
            f, j = row[i]
            if faces[f][j] == seen[i]:
                hits += 1
    return hits


def best_match(cube: Cube, observed: dict[str, list[str]],
               moves: list[str] | None = None) -> Match:
    """Find the (move, orientation) that best explains *observed*.

    ``moves`` defaults to every legal quarter/half turn; "" (no move) is
    always considered, so a pure rotation is recognised as such.
    """
    candidates = [""] + list(moves if moves is not None else ALL_MOVES)
    best = Match(move="", orientation=0, score=-1)
    second = -1
    for move in candidates:
        probe = cube if not move else cube.moved(move)
        for o in range(len(ORIENTATIONS)):
            s = _score(probe, o, observed)
            if s > best.score:
                second = best.score
                best = Match(move=move, orientation=o, score=s)
            elif s > second and move != best.move:
                second = s
    best.runner_up = max(second, 0)
    return best


def describe_rotation(previous: int, current: int) -> str:
    """Plain words for how the cube was turned between two orientations."""
    if previous == current:
        return ""
    prev_seq = ORIENTATIONS[previous]
    for token, phrase in ROTATION_NAMES:
        probe = Cube(faces={f: [f] * 9 for f in
                            ("U", "R", "F", "D", "L", "B")})
        probe.apply_sequence(f"{prev_seq} {token}".strip())
        target = Cube(faces={f: [f] * 9 for f in
                             ("U", "R", "F", "D", "L", "B")})
        target.apply_sequence(ORIENTATIONS[current])
        if all(probe.center(f) == target.center(f) for f in probe.faces):
            return phrase
    return "turned it round"


def facing_description(cube: Cube, orientation: int) -> str:
    """Which face of the *solved* colour scheme is pointing at the camera."""
    probe = Cube(faces={f: [f] * 9 for f in
                        ("U", "R", "F", "D", "L", "B")})
    probe.apply_sequence(ORIENTATIONS[orientation])
    names = {"F": "front", "B": "back", "U": "top",
             "D": "bottom", "L": "left", "R": "right"}
    return names.get(probe.center("F"), "?")
