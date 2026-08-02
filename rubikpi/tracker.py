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

Stickers the camera cannot read — a finger resting on the cube, a patch
of glare — arrive as "X" and are simply left out of the comparison
rather than counted as wrong.  A move is only credited while enough of
the face is visible to tell it from the alternatives.

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

#: How many of the nine must be readable before anything is decided.
MIN_KNOWN = 6

#: Stickers the camera is allowed to get wrong.  A real webcam misreads
#: one or two on most frames — glare on a corner, a shadow across a row —
#: so insisting on a near-perfect reading simply never fires.
TOLERANCE = 2

#: How far the winning explanation must beat the runner-up.  A
#: neighbouring turn changes three stickers, so a clear win is 2 or more;
#: below that the reading genuinely does not say which turn it was.
MIN_MARGIN = 2

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
    score: int = 0          # matching stickers among the readable ones
    known: int = 0          # stickers the camera could actually read
    margin: int = 0         # how far this beats the next explanation
    by_plan: bool = False   # a genuine tie, settled by the move asked for
    ambiguous: bool = False  # several different moves fit equally well
    options: list[str] = field(default_factory=list)

    @property
    def hidden(self) -> int:
        """Stickers a finger or glare is covering."""
        return CELLS - self.known

    @property
    def fits(self) -> bool:
        """Close enough to the app's cube to be the same cube."""
        return (bool(self.face) and self.known >= MIN_KNOWN
                and self.score >= self.known - TOLERANCE)

    @property
    def sole(self) -> bool:
        """Nothing else explains the picture as well as this does."""
        return len(self.options) <= 1

    @property
    def believable(self) -> bool:
        """Either the only explanation, or a tie the plan settles.

        Turning the face you are watching genuinely looks the same as
        rolling the whole cube in your hands, so that tie can only ever
        be settled by what the app asked for — never by looking harder.
        """
        return self.by_plan or (self.sole and self.margin >= 1)

    @property
    def confident(self) -> bool:
        """Fits, and there is a believable reading of what happened."""
        return (self.fits and not self.ambiguous
                and (not self.move or self.believable))


def visible_face(cube: Cube, observed: list[str]) -> str:
    """Which face the camera is looking at, from the centre sticker."""
    centre = observed[4] if len(observed) == 9 else ""
    seen = [f for f in FACES if cube.center(f) == centre]
    return seen[0] if len(seen) == 1 else ""


def agreement(predicted: list[str], observed: list[str]) -> tuple[int, int]:
    """(matching, readable) — stickers the camera could not read are skipped."""
    matching = readable = 0
    for want, seen in zip(predicted, observed):
        if seen == "X":
            continue           # hidden by a finger or glare: no opinion
        readable += 1
        matching += want == seen
    return matching, readable


def read_face(cube: Cube, observed: list[str]) -> tuple[str, int, int, int]:
    """Compare what the camera sees with the cube as the app believes it.

    Returns the face being shown, how far round it is turned in view, how
    many readable stickers agree, and how many were readable at all.
    Agreement on everything readable means the app and the real cube are
    in step — the confirmation the user wants — and hidden stickers count
    against neither side.
    """
    face = visible_face(cube, observed)
    if not face:
        return "", 0, 0, 0
    best_roll, best_score, best_known = 0, -1, 0
    for roll in range(4):
        predicted = rotate_face(cube.faces[face], roll)
        score, known = agreement(predicted, observed)
        if score > best_score:
            best_roll, best_score, best_known = roll, score, known
    return face, best_roll, best_score, best_known


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
    if len(observed) != CELLS:
        return Match()
    face = visible_face(cube, observed)
    if not face:
        return Match()
    readable = sum(1 for c in observed if c != "X")
    if readable < MIN_KNOWN:
        # Too much of the face is covered to say anything about it.
        return Match(face=face, known=readable)

    # Best score each move can manage, at whichever rotation suits it.
    per_move: dict[str, tuple[int, int]] = {}
    for move in [""] + list(ALL_MOVES):
        probe = cube if not move else cube.moved(move)
        top, top_roll = -1, 0
        for roll in range(4):
            predicted = rotate_face(probe.faces[face], roll)
            score, _ = agreement(predicted, observed)
            if score > top:
                top, top_roll = score, roll
        per_move[move] = (top, top_roll)

    best = max(score for score, _ in per_move.values())
    fits = [(move, roll) for move, (score, roll) in per_move.items()
            if score == best]
    moves = {m for m, _ in fits}
    # A move on the hidden face explains nothing the camera can see, so it
    # is never evidence of anything on its own.
    visible_moves = {m for m in moves if m and not is_hidden(face, m)}

    def pick(move: str) -> Match:
        roll = per_move[move][1]
        # How much better this reading is than the best rival explanation.
        # Deciding on the margin rather than on being near-perfect is what
        # lets a couple of misread stickers through without inventing moves.
        rivals = [score for other, (score, _) in per_move.items()
                  if other != move]
        margin = best - max(rivals) if rivals else best
        return Match(face=face, move=move, roll=roll, score=best,
                     known=readable, margin=margin, options=sorted(moves))

    def picture(move: str) -> list[str]:
        roll = next(r for m, r in fits if m == move)
        probe = cube if not move else cube.moved(move)
        return rotate_face(probe.faces[face], roll)

    if expected and expected in moves and not is_hidden(face, expected):
        if "" not in moves:
            chosen = pick(expected)     # something plainly changed
            chosen.by_plan = len(moves) > 1
            return chosen
        # Both fit.  If they would look identical even with nothing
        # covered, the ambiguity is inherent — turning the face you are
        # watching looks like turning the whole cube — and the move the
        # app asked for is the better bet.  If they only agree because a
        # finger is over the stickers that would tell them apart, say so
        # instead of guessing.
        if picture(expected) == picture(""):
            chosen = pick(expected)
            chosen.by_plan = True
            return chosen
        result = pick("")
        result.ambiguous = True
        return result
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


@dataclass
class Reading:
    """One frame's worth of conclusion, ready for the UI."""

    grid: list[str] = field(default_factory=list)   # the steadied nine
    match: Match = field(default_factory=Match)
    accepted: str = ""      # a move the user has definitely made
    note: str = ""          # something worth telling them
    lost: bool = False      # the cube no longer resembles the app's copy

    @property
    def agrees(self) -> bool:
        """Everything readable matches the app's cube."""
        return self.match.known > 0 and self.match.score == self.match.known


class FollowTracker:
    """Turns a stream of noisy camera frames into moves.

    Two things make this work on a real webcam rather than on tidy test
    data.  First the frames are *steadied*: each cell takes the colour it
    is read as most often across the last few frames, so a sticker that
    flickers between red and orange settles instead of poisoning every
    comparison.  Second a move is accepted on the *margin* over rival
    explanations and on a majority of recent frames, rather than on any
    single frame being near-perfect — which is what a camera never
    delivers.
    """

    WINDOW = 5          # frames blended into one steady reading
    VOTES = 3           # agreeing readings before a move is believed
    RECENT = 8          # how far back those votes are counted
    LOST_AFTER = 45     # frames of nothing fitting before we admit it

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._frames: list[list[str]] = []
        self._recent: list[str] = []
        self._misfits = 0
        self._settled: list[str] | None = None   # the picture at rest
        self.last: Match | None = None

    def notice_change(self) -> None:
        """The cube has just changed: forget readings of the old state."""
        self._frames.clear()
        self._recent.clear()
        self._settled = None
        self._misfits = 0

    def _unchanged(self, steady: list[str]) -> bool:
        """Does the face still look like it did while sitting still?

        Turning the face you are watching cannot be told from rolling the
        cube by looking at that face alone, so the app leans on the move
        it asked for.  That lean is only safe if something actually
        moved: without this, a few noisy frames while the cube sits
        untouched would be read as the requested turn.
        """
        if self._settled is None:
            return False
        same, both = 0, 0
        for was, now in zip(self._settled, steady):
            if was == "X" or now == "X":
                continue
            both += 1
            same += was == now
        return both >= MIN_KNOWN and same >= both - TOLERANCE

    # -- steadying -----------------------------------------------------------

    def steady(self) -> list[str]:
        """Per cell, the colour seen most often lately; "X" when unsure."""
        if not self._frames:
            return ["X"] * CELLS
        out: list[str] = []
        for cell in range(CELLS):
            seen = [f[cell] for f in self._frames if f[cell] != "X"]
            if len(seen) * 2 < len(self._frames):
                out.append("X")          # hidden more often than not
                continue
            winner = max(set(seen), key=seen.count)
            # Only trust it if that colour is what most of the looks said.
            out.append(winner if seen.count(winner) * 2 > len(seen) else "X")
        return out

    # -- the decision --------------------------------------------------------

    def observe(self, cube: Cube, grid: list[str],
                expected: str = "") -> Reading:
        """Take one camera frame and say what, if anything, happened."""
        if len(grid) == CELLS:
            self._frames.append(list(grid))
            del self._frames[:-self.WINDOW]
        steady = self.steady()

        match = best_match(cube, steady, expected=expected)
        self.last = match

        if not match.face:
            self._recent.clear()
            note = ("Your finger is over the middle sticker — I need that "
                    "one to know which side I am looking at."
                    if steady[4] == "X" else
                    "That centre colour is not on your cube — check the "
                    "scan, or the lighting.")
            return Reading(grid=steady, match=match, note=note)

        if match.known < MIN_KNOWN:
            self._recent.clear()
            return Reading(grid=steady, match=match,
                           note=f"Too much of the face is covered "
                                f"({CELLS - match.known} stickers) — move "
                                "your fingers off it for a moment.")

        if not match.fits:
            # Nothing explains this, not even "nothing happened".
            self._recent.clear()
            self._misfits += 1
            if self._misfits >= self.LOST_AFTER:
                return Reading(grid=steady, match=match, lost=True,
                               note="I have lost track of your cube — press "
                                    "Reset scan and show me the faces again.")
            return Reading(grid=steady, match=match,
                           note="That does not look like the cube I have — "
                                "hold it steady in the guide.")
        self._misfits = 0

        if self._settled is None:
            # First good look since the cube last changed.  Whatever it
            # shows is the starting point; a turn has to differ from it.
            self._settled = list(steady)
            self._recent.clear()
            return Reading(grid=steady, match=match)

        if not match.move:
            self._recent.append("")
            del self._recent[:-self.RECENT]
            self._settled = list(steady)     # this is the cube at rest
            return Reading(grid=steady, match=match)

        if match.by_plan and self._unchanged(steady):
            # The plan says a turn is due, but the face has not actually
            # changed since it was last at rest: nothing has happened yet.
            self._recent.clear()
            return Reading(grid=steady, match=match)

        if match.ambiguous or not match.believable:
            self._recent.clear()
            return Reading(grid=steady, match=match,
                           note="Something turned but I cannot tell which "
                                "way — show me a bit more of the cube.")

        # Weak evidence is still evidence; it just has to hold up longer.
        # A turn sometimes alters only one sticker the camera can see, so
        # demanding a wide margin every time would miss those entirely.
        needed = (self.VOTES if match.by_plan or match.margin >= MIN_MARGIN
                  else self.VOTES + 2)
        self._recent.append(match.move)
        del self._recent[:-self.RECENT]
        agreeing = self._recent.count(match.move)
        rivals = {m for m in self._recent if m and m != match.move}
        if agreeing >= needed and not rivals:
            self.notice_change()
            return Reading(grid=steady, match=match, accepted=match.move)
        return Reading(grid=steady, match=match)
