"""Cube model: facelet state, move engine and solving-stage predicates.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Conventions
-----------
Faces are named U, R, F, D, L, B.  Each face holds 9 stickers indexed

    0 1 2
    3 4 5
    6 7 8

read as if looking straight at the face with:
  * U viewed from above with B at the top,
  * D viewed from below (through the cube net) with F at the top,
  * F, R, B, L viewed straight on with U at the top.

This matches the standard Kociemba facelet convention.  Sticker values are
single colour letters: W Y R O G B, or X for "unknown / not scanned yet".
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

FACES: tuple[str, ...] = ("U", "R", "F", "D", "L", "B")

#: Colour of each face on a solved cube — the single source of truth for
#: every scan instruction and on-screen guide.  Face names are internal
#: labels; what fixes them is the centre colour, so this is simply how the
#: cube is held: yellow up, white down, blue front, green back, red right,
#: orange left.  (That is the standard Western cube held ``x2`` from the
#: white-up/green-front position — same cube, different way round.)
#:
#: Change these six letters to match a differently-coloured cube and the
#: whole app follows: expected centres, scan wording and the guides.
DEFAULT_SCHEME: dict[str, str] = {
    "U": "Y", "R": "R", "F": "B", "D": "W", "L": "O", "B": "G",
}

OPPOSITE: dict[str, str] = {"U": "D", "D": "U", "R": "L", "L": "R", "F": "B", "B": "F"}

#: Human names for the sticker letters, for every message the user reads.
COLOR_NAME: dict[str, str] = {
    "W": "white", "Y": "yellow", "R": "red",
    "O": "orange", "G": "green", "B": "blue", "X": "unknown",
}

UNKNOWN = "X"

# ---------------------------------------------------------------------------
# Move tables
# ---------------------------------------------------------------------------
# Each entry is a list of 4-cycles of (face, index) positions.  A clockwise
# quarter turn sends the sticker at position [0] to [1], [1] to [2], etc.

_SIDE_CYCLES: dict[str, list[tuple[tuple[str, int], ...]]] = {
    "U": [(("F", i), ("L", i), ("B", i), ("R", i)) for i in (0, 1, 2)],
    "D": [(("F", i), ("R", i), ("B", i), ("L", i)) for i in (6, 7, 8)],
    "R": [
        (("F", 2), ("U", 2), ("B", 6), ("D", 2)),
        (("F", 5), ("U", 5), ("B", 3), ("D", 5)),
        (("F", 8), ("U", 8), ("B", 0), ("D", 8)),
    ],
    "L": [
        (("U", 0), ("F", 0), ("D", 0), ("B", 8)),
        (("U", 3), ("F", 3), ("D", 3), ("B", 5)),
        (("U", 6), ("F", 6), ("D", 6), ("B", 2)),
    ],
    "F": [
        (("U", 6), ("R", 0), ("D", 2), ("L", 8)),
        (("U", 7), ("R", 3), ("D", 1), ("L", 5)),
        (("U", 8), ("R", 6), ("D", 0), ("L", 2)),
    ],
    "B": [
        (("U", 0), ("L", 6), ("D", 8), ("R", 2)),
        (("U", 1), ("L", 3), ("D", 7), ("R", 5)),
        (("U", 2), ("L", 0), ("D", 6), ("R", 8)),
    ],
    # Slice moves.  M follows L, E follows D, S follows F.
    "M": [
        (("U", 1), ("F", 1), ("D", 1), ("B", 7)),
        (("U", 4), ("F", 4), ("D", 4), ("B", 4)),
        (("U", 7), ("F", 7), ("D", 7), ("B", 1)),
    ],
    "E": [(("F", i), ("R", i), ("B", i), ("L", i)) for i in (3, 4, 5)],
    "S": [
        (("U", 3), ("R", 1), ("D", 5), ("L", 7)),
        (("U", 4), ("R", 4), ("D", 4), ("L", 4)),
        (("U", 5), ("R", 7), ("D", 3), ("L", 1)),
    ],
}

#: Clockwise rotation of the face's own 9 stickers: new[i] = old[_FACE_CW[i]].
_FACE_CW = (6, 3, 0, 7, 4, 1, 8, 5, 2)

# Corner and edge facelet slots (Kociemba convention).  Corners list their
# facelets clockwise starting with the U/D one; edges start with the
# reference facelet.  Used by is_solvable() to check that a scanned state
# is a physically possible cube.
_CORNER_SLOTS: tuple[tuple[tuple[str, int], ...], ...] = (
    (("U", 8), ("R", 0), ("F", 2)),   # URF
    (("U", 6), ("F", 0), ("L", 2)),   # UFL
    (("U", 0), ("L", 0), ("B", 2)),   # ULB
    (("U", 2), ("B", 0), ("R", 2)),   # UBR
    (("D", 2), ("F", 8), ("R", 6)),   # DFR
    (("D", 0), ("L", 8), ("F", 6)),   # DLF
    (("D", 6), ("B", 8), ("L", 6)),   # DBL
    (("D", 8), ("R", 8), ("B", 6)),   # DRB
)

_EDGE_SLOTS: tuple[tuple[tuple[str, int], ...], ...] = (
    (("U", 5), ("R", 1)), (("U", 7), ("F", 1)),
    (("U", 3), ("L", 1)), (("U", 1), ("B", 1)),
    (("D", 5), ("R", 7)), (("D", 1), ("F", 7)),
    (("D", 3), ("L", 7)), (("D", 7), ("B", 7)),
    (("F", 5), ("R", 3)), (("F", 3), ("L", 5)),
    (("B", 5), ("L", 3)), (("B", 3), ("R", 5)),
)

#: Compound moves expressed with the primitives above.
_COMPOUND: dict[str, str] = {
    "x": "R M' L'", "y": "U E' D'", "z": "F S B'",
    "Rw": "R M'", "Lw": "L M", "Uw": "U E'", "Dw": "D E",
    "Fw": "F S", "Bw": "B S'",
    "r": "R M'", "l": "L M", "u": "U E'", "d": "D E", "f": "F S", "b": "B S'",
}

ALL_MOVES: tuple[str, ...] = (
    "U", "U'", "U2", "D", "D'", "D2", "R", "R'", "R2",
    "L", "L'", "L2", "F", "F'", "F2", "B", "B'", "B2",
)


@dataclass
class Cube:
    """A 3x3x3 cube held as 6 faces of 9 colour letters."""

    faces: dict[str, list[str]] = field(
        default_factory=lambda: {f: [DEFAULT_SCHEME[f]] * 9 for f in FACES}
    )

    # -- construction -------------------------------------------------------

    @classmethod
    def solved(cls) -> "Cube":
        return cls()

    @classmethod
    def unknown(cls) -> "Cube":
        """A cube with every sticker unscanned."""
        return cls(faces={f: [UNKNOWN] * 9 for f in FACES})

    def copy(self) -> "Cube":
        return Cube(faces={f: list(s) for f, s in self.faces.items()})

    # -- basic queries -------------------------------------------------------

    def center(self, face: str) -> str:
        return self.faces[face][4]

    def is_full(self) -> bool:
        return all(UNKNOWN not in s for s in self.faces.values())

    def is_solved(self) -> bool:
        return all(all(c == s[4] for c in s) and s[4] != UNKNOWN
                   for s in self.faces.values())

    def scanned_faces(self) -> list[str]:
        return [f for f in FACES if UNKNOWN not in self.faces[f]]

    def misplaced_count(self) -> int:
        """Number of stickers that do not match their face centre."""
        return sum(1 for f in FACES for c in self.faces[f] if c != self.faces[f][4])

    def color_scheme(self) -> dict[str, str]:
        """face -> centre colour (falls back to the default scheme)."""
        return {
            f: (self.center(f) if self.center(f) != UNKNOWN else DEFAULT_SCHEME[f])
            for f in FACES
        }

    def is_valid_colors(self) -> tuple[bool, str]:
        """Cheap sanity check: 6 distinct centres, 9 stickers per colour."""
        centers = [self.center(f) for f in FACES]
        if UNKNOWN in centers:
            return False, "Not all faces scanned yet."
        if len(set(centers)) != 6:
            return False, "Two faces share the same centre colour — rescan."
        counts: dict[str, int] = {}
        for f in FACES:
            for c in self.faces[f]:
                counts[c] = counts.get(c, 0) + 1
        bad = [c for c, n in counts.items() if n != 9]
        if bad:
            return False, "Colour count is off for: " + ", ".join(sorted(bad))
        return True, "ok"

    def is_solvable(self) -> tuple[bool, str]:
        """Full physical check: could this state exist on a real cube?

        Beyond colour counts this verifies that every corner and edge slot
        holds a real piece, that no piece appears twice, and the three
        classic invariants (corner twist, edge flip, permutation parity).
        A scan that fails here has at least one misread sticker — the
        message names the slots to look at.
        """
        ok, why = self.is_valid_colors()
        if not ok:
            return False, why

        scheme = self.color_scheme()             # face -> colour
        if not scheme_is_possible(scheme):
            return False, ("Those six centre colours cannot sit on one cube "
                           "— two centres are swapped (most often red with "
                           "orange, or white with yellow).")
        face_of = {c: f for f, c in scheme.items()}
        ud = {scheme["U"], scheme["D"]}
        fb = {scheme["F"], scheme["B"]}

        def slot_name(slot) -> str:
            return "".join(f for f, _ in slot)

        # -- corners: real piece, right twist, no duplicates ----------------
        solved_corners = {frozenset(face_of[c] for c in
                                    (scheme[f] for f, _ in slot)): i
                          for i, slot in enumerate(_CORNER_SLOTS)}
        corner_perm: list[int] = []
        twist = 0
        for slot in _CORNER_SLOTS:
            colors = [self.faces[f][i] for f, i in slot]
            key = frozenset(face_of.get(c, "?") for c in colors)
            if len(set(colors)) != 3 or key not in solved_corners:
                return False, (f"Corner {slot_name(slot)} is not a real "
                               "cube corner — recheck those three stickers.")
            corner_perm.append(solved_corners[key])
            oriented = [j for j, c in enumerate(colors) if c in ud]
            if len(oriented) != 1:
                pair = " or ".join(COLOR_NAME[c] for c in sorted(ud))
                return False, (f"Corner {slot_name(slot)} has no single "
                               f"{pair} sticker — recheck it.")
            twist += oriented[0]
        if len(set(corner_perm)) != 8:
            return False, ("The same corner piece appears twice — at least "
                           "one corner is misread.")
        if twist % 3:
            return False, ("A corner is twisted in place — one corner's "
                           "three stickers are read in the wrong order.")

        # -- edges: real piece, right flip, no duplicates -------------------
        solved_edges = {frozenset(face_of[c] for c in
                                  (scheme[f] for f, _ in slot)): i
                        for i, slot in enumerate(_EDGE_SLOTS)}
        edge_perm: list[int] = []
        flip = 0
        for slot in _EDGE_SLOTS:
            colors = [self.faces[f][i] for f, i in slot]
            key = frozenset(face_of.get(c, "?") for c in colors)
            if len(set(colors)) != 2 or key not in solved_edges:
                return False, (f"Edge {slot_name(slot)} is not a real cube "
                               "edge — recheck those two stickers.")
            edge_perm.append(solved_edges[key])
            ref, other = colors
            if ref in ud:
                pass
            elif other in ud or ref not in fb:
                flip += 1
        if len(set(edge_perm)) != 12:
            return False, ("The same edge piece appears twice — at least "
                           "one edge is misread.")
        if flip % 2:
            return False, ("An edge is flipped in place — one edge's two "
                           "stickers are swapped.")

        if _perm_parity(corner_perm) != _perm_parity(edge_perm):
            return False, ("Two pieces are swapped — this state cannot be "
                           "reached by turning a real cube.")
        return True, "ok"

    # -- moves ---------------------------------------------------------------

    def _turn_primitive(self, token: str) -> None:
        base, times = token[0], 1
        if token.endswith("2"):
            times = 2
        elif token.endswith("'"):
            times = 3
        for _ in range(times):
            old = {f: list(s) for f, s in self.faces.items()}
            if base in FACES:
                self.faces[base] = [old[base][_FACE_CW[i]] for i in range(9)]
            for cycle in _SIDE_CYCLES[base]:
                for i in range(4):
                    src_f, src_i = cycle[i]
                    dst_f, dst_i = cycle[(i + 1) % 4]
                    self.faces[dst_f][dst_i] = old[src_f][src_i]

    def apply(self, move: str) -> None:
        """Apply one move in standard notation (U, R', F2, M, x, Rw, ...)."""
        move = move.strip()
        if not move:
            return
        suffix = ""
        core = move
        if move.endswith(("'", "2")):
            core, suffix = move[:-1], move[-1]
        if core in ("X", "Y", "Z"):  # some solvers emit uppercase rotations
            core = core.lower()
        if core in _COMPOUND:
            seq = _COMPOUND[core].split()
            if suffix == "'":
                seq = [_invert(t) for t in reversed(seq)]
            elif suffix == "2":
                seq = seq + seq
            for t in seq:
                self._turn_primitive(t)
            return
        if core in _SIDE_CYCLES:
            self._turn_primitive(core + suffix)
            return
        raise ValueError(f"Unknown move: {move!r}")

    def apply_sequence(self, moves: "str | list[str]") -> None:
        if isinstance(moves, str):
            moves = moves.split()
        for m in moves:
            self.apply(m)

    def moved(self, move: str) -> "Cube":
        c = self.copy()
        c.apply(move)
        return c

    # -- scrambling ----------------------------------------------------------

    @staticmethod
    def random_scramble(length: int = 22, rng: random.Random | None = None) -> list[str]:
        rng = rng or random.Random()
        moves: list[str] = []
        last = ""
        for _ in range(length):
            face = rng.choice([f for f in FACES if f != last])
            last = face
            moves.append(face + rng.choice(["", "'", "2"]))
        return moves

    # -- serialisation -------------------------------------------------------

    def to_facelet_string(self) -> str:
        """54-char string in URFDLB order using *face letters* (Kociemba)."""
        scheme = {v: k for k, v in self.color_scheme().items()}
        out = []
        for f in ("U", "R", "F", "D", "L", "B"):
            for c in self.faces[f]:
                out.append(scheme.get(c, "?"))
        return "".join(out)

    def to_color_string(self, order: str = "ULFRBD") -> str:
        """54-char lowercase colour string (rubik_solver uses ULFRBD)."""
        return "".join(c.lower() for f in order for c in self.faces[f])

    def serialise(self) -> str:
        """Compact 54-char colour snapshot (URFDLB order, keeps unknowns)."""
        return "".join(c for f in FACES for c in self.faces[f])

    @classmethod
    def from_serialised(cls, data: str) -> "Cube":
        faces = {f: list(data[i * 9:(i + 1) * 9]) for i, f in enumerate(FACES)}
        return cls(faces=faces)


#: Rotation sequences reaching each of the 24 ways to hold a cube.
_ORIENTATIONS: tuple[str, ...] = tuple(
    (spin + " " + tilt).strip()
    for tilt in ("", "x", "x2", "x'", "z", "z'")
    for spin in ("", "y", "y2", "y'")
)


def possible_schemes() -> list[dict[str, str]]:
    """Every centre arrangement a real cube can show (24 orientations)."""
    out: list[dict[str, str]] = []
    for seq in _ORIENTATIONS:
        probe = Cube(faces={f: [DEFAULT_SCHEME[f]] * 9 for f in FACES})
        probe.apply_sequence(seq)
        out.append({f: probe.center(f) for f in FACES})
    return out


def held_faces(front: str, up: str) -> dict[str, str]:
    """Which face sits at each position when the cube is held a given way.

    ``held_faces("B", "U")["R"]`` answers "with the B face towards me and
    U on top, which face is on my right?".  This is what turns an
    abstract move like ``R`` into "the face on your left" when you are
    looking at the cube from the opposite side to the camera.
    """
    if front == up or OPPOSITE[front] == up:
        raise ValueError(f"cannot hold a cube with {front} towards you and "
                         f"{up} up — they are the same axis")
    for seq in _ORIENTATIONS:
        probe = Cube(faces={f: [f] * 9 for f in FACES})
        probe.apply_sequence(seq)
        if probe.center("F") == front and probe.center("U") == up:
            return {pos: probe.center(pos) for pos in FACES}
    raise ValueError(f"cannot hold a cube with {front} front and {up} up")


def scheme_is_possible(scheme: dict[str, str]) -> bool:
    """Could these six centre colours sit on one physical cube?

    Catches mirror-image arrangements, which pass every "9 of each
    colour" style check yet cannot exist — typically a red/orange or
    white/yellow mix-up in the scan.
    """
    return any(all(scheme.get(f) == s[f] for f in FACES)
               for s in possible_schemes())


def _perm_parity(perm: list[int]) -> int:
    """0 for an even permutation, 1 for an odd one."""
    seen = [False] * len(perm)
    parity = 0
    for i in range(len(perm)):
        if seen[i]:
            continue
        length = 0
        j = i
        while not seen[j]:
            seen[j] = True
            j = perm[j]
            length += 1
        parity ^= (length - 1) & 1
    return parity


def _invert(token: str) -> str:
    if token.endswith("'"):
        return token[:-1]
    if token.endswith("2"):
        return token
    return token + "'"


def invert_sequence(moves: list[str]) -> list[str]:
    return [_invert(m) for m in reversed(moves)]


# ---------------------------------------------------------------------------
# Stage predicates (used to split a solution into human stages)
# ---------------------------------------------------------------------------

# The four side faces around the U/D axis, and the sticker row on each that
# touches the given face (row 0-1-2 touches U, row 6-7-8 touches D).
_SIDES = ("F", "R", "B", "L")
_ADJ_ROW: dict[str, tuple[int, int, int]] = {"U": (0, 1, 2), "D": (6, 7, 8)}


def cross_done(cube: Cube, face: str) -> bool:
    """The four edges of *face* placed and aligned with the side centres."""
    centre = cube.center(face)
    if not all(cube.faces[face][i] == centre for i in (1, 3, 5, 7)):
        return False
    if face not in _ADJ_ROW:
        return True  # generic fallback: only the face itself is checked
    mid = _ADJ_ROW[face][1]
    return all(cube.faces[s][mid] == cube.center(s) for s in _SIDES)


def first_layer_done(cube: Cube, face: str = "D") -> bool:
    """The whole first layer (cross + corners) of *face* is in place."""
    centre = cube.center(face)
    if not all(c == centre for c in cube.faces[face]):
        return False
    if face not in _ADJ_ROW:
        return False
    row = _ADJ_ROW[face]
    return all(cube.faces[s][i] == cube.center(s) for s in _SIDES for i in row)


def second_layer_done(cube: Cube, face: str = "D") -> bool:
    if not first_layer_done(cube, face):
        return False
    return all(cube.faces[s][i] == cube.center(s) for s in _SIDES for i in (3, 4, 5))


def last_layer_oriented(cube: Cube, face: str = "D") -> bool:
    """Second layer done and the opposite face is one colour (OLL done)."""
    if not second_layer_done(cube, face):
        return False
    top = OPPOSITE[face]
    centre = cube.center(top)
    return all(c == centre for c in cube.faces[top])


def solved(cube: Cube, face: str = "D") -> bool:
    return cube.is_solved()


#: Ordered stage lists per solving mode: (label, predicate(cube, cross_face)).
BEGINNER_STAGES = [
    ("Cross", cross_done),
    ("First layer", first_layer_done),
    ("Second layer", second_layer_done),
    ("Last layer — orient", last_layer_oriented),
    ("Last layer — finish", solved),
]

CFOP_STAGES = [
    ("Cross", cross_done),
    ("F2L — first two layers", second_layer_done),
    ("OLL — orient last layer", last_layer_oriented),
    ("PLL — permute last layer", solved),
]
