"""Follow-along tracking from a single face.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

The camera watches one face — the easy thing to hold steady — and the app
already knows the cube's state, so working out what you did is a matching
problem over nine stickers.

What one face tells you:

* **Which side the camera is on.**  Centres never move, so the middle
  sticker names the face.
* **A turn of that face**: all nine stickers rotate.
* **A turn of any of the four neighbouring faces**: one row or column is
  replaced, which identifies the face and the direction.
* **A turn of the opposite face**: nothing changes — genuinely invisible,
  and reported as such rather than guessed at.

One ambiguity is unavoidable: turning the face you are looking at looks
exactly like turning the whole cube in your hands.  Passing the move the
app just asked for as *expected* settles it — if what the camera sees
fits that move, it counts; otherwise it is read as the cube being turned
round, which changes nothing.

Pure Python: no Qt, no OpenCV, so it is testable headless.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rubikpi.cube import ALL_MOVES, FACES, OPPOSITE, Cube, _FACE_CW

#: Stickers compared per hypothesis: one face.
CELLS = 9

#: Human names for the four ways a face can be rotated in view.
ROLL_NAMES = {0: "", 1: "rolled it clockwise",
              2: "turned it upside down", 3: "rolled it anticlockwise"}


def rotate_face(letters: list[str], quarters: int) -> list[str]:
    """The same nine stickers seen after turning the face clockwise."""
    out = list(letters)
    for _ in range(quarters % 4):
        out = [out[_FACE_CW[i]] for i in range(9)]
    return out


@dataclass
class Match:
    """What the camera is most likely showing."""

    face: str = ""          # the face pointing at the camera
    move: str = ""          # "" when nothing turned
    roll: int = 0           # quarter turns the view is rotated by
    score: int = 0          # matching stickers out of 9
    ambiguous: bool = False  # several different moves fit equally well
    options: list[str] = field(default_factory=list)

    @property
    def confident(self) -> bool:
        """At most one odd sticker, one face identified, one reading."""
        return bool(self.face) and self.score >= CELLS - 1 \
            and not self.ambiguous


def visible_face(cube: Cube, observed: list[str]) -> str:
    """Which face the camera is looking at, from the centre sticker."""
    centre = observed[4] if len(observed) == 9 else ""
    seen = [f for f in FACES if cube.center(f) == centre]
    return seen[0] if len(seen) == 1 else ""


def read_face(cube: Cube, observed: list[str]) -> tuple[str, int, int]:
    """Compare what the camera sees with the cube as the app believes it.

    Returns the face being shown, how far round it is turned in view, and
    how many of the nine stickers agree.  Nine out of nine means the app
    and the real cube are in step — the confirmation the user wants.
    """
    face = visible_face(cube, observed)
    if not face:
        return "", 0, 0
    best_roll, best_score = 0, -1
    for roll in range(4):
        predicted = rotate_face(cube.faces[face], roll)
        score = sum(1 for a, b in zip(predicted, observed) if a == b)
        if score > best_score:
            best_roll, best_score = roll, score
    return face, best_roll, best_score


def is_hidden(face: str, move: str) -> bool:
    """Would this move be invisible while looking at *face*?"""
    return bool(move) and move[0] == OPPOSITE.get(face, "")


def best_match(cube: Cube, observed: list[str],
               expected: str = "") -> Match:
    """Explain *observed* as a move (or none) plus how the cube is held.

    *expected* is the move the app has asked for; when the evidence fits
    it as well as anything else, it wins — that is what separates
    "you turned this face" from "you turned the whole cube round".
    """
    if len(observed) != CELLS or "X" in observed:
        return Match()
    face = visible_face(cube, observed)
    if not face:
        return Match()

    best = -1
    fits: list[tuple[str, int]] = []          # (move, roll) scoring best
    for move in [""] + list(ALL_MOVES):
        probe = cube if not move else cube.moved(move)
        for roll in range(4):
            predicted = rotate_face(probe.faces[face], roll)
            score = sum(1 for a, b in zip(predicted, observed) if a == b)
            if score > best:
                best, fits = score, [(move, roll)]
            elif score == best:
                fits.append((move, roll))

    moves = {m for m, _ in fits}
    # A move on the hidden face explains nothing the camera can see, so it
    # is never evidence of anything on its own.
    visible_moves = {m for m in moves if m and not is_hidden(face, m)}

    def pick(move: str) -> Match:
        roll = next(r for m, r in fits if m == move)
        return Match(face=face, move=move, roll=roll, score=best,
                     options=sorted(moves))

    if expected and expected in moves and not is_hidden(face, expected):
        return pick(expected)
    if "" in moves:
        return pick("")
    if len(visible_moves) == 1:
        return pick(next(iter(visible_moves)))
    result = pick(sorted(visible_moves)[0]) if visible_moves else Match()
    result.ambiguous = True
    return result


def describe_change(previous: Match | None, current: Match) -> str:
    """Plain words for how the cube is being held now."""
    if not current.face:
        return ""
    if previous is None or not previous.face:
        return ""
    if previous.face != current.face:
        return "turned the cube round"
    if previous.roll != current.roll:
        return ROLL_NAMES.get((current.roll - previous.roll) % 4, "")
    return ""
