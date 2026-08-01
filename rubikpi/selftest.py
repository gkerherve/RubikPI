"""Headless self-test for the cube model (no Qt, no camera needed).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Run with:  python -m rubikpi.selftest
"""

from __future__ import annotations

import random

from rubikpi.cube import (
    ALL_MOVES,
    BEGINNER_STAGES,
    Cube,
    cross_done,
    first_layer_done,
    invert_sequence,
    second_layer_done,
)


def check(name: str, ok: bool) -> bool:
    print(f"  [{'ok' if ok else 'FAIL'}] {name}")
    return ok


def main() -> int:
    print("RubikPI cube-model self-test")
    all_ok = True

    # Every quarter turn has order 4.
    for m in ("U", "D", "R", "L", "F", "B", "M", "E", "S"):
        c = Cube.solved()
        for _ in range(4):
            c.apply(m)
        all_ok &= check(f"{m} x4 = identity", c.is_solved())

    # Sexy move has order 6.
    c = Cube.solved()
    for _ in range(6):
        c.apply_sequence("R U R' U'")
    all_ok &= check("(R U R' U') x6 = identity", c.is_solved())

    # Rotations have order 4 and preserve solvedness.
    for m in ("x", "y", "z", "Rw", "Uw", "Fw"):
        c = Cube.solved()
        for _ in range(4):
            c.apply(m)
        all_ok &= check(f"{m} x4 = identity", c.is_solved())

    # A rotation of a solved cube is still "solved" (centres move with it).
    c = Cube.solved()
    c.apply("x")
    all_ok &= check("x keeps cube solved", c.is_solved())

    # Scramble + inverse scramble returns to solved.
    rng = random.Random(42)
    scr = Cube.random_scramble(30, rng)
    c = Cube.solved()
    c.apply_sequence(scr)
    all_ok &= check("scramble changes the cube", not c.is_solved())
    all_ok &= check("colour counts stay valid", c.is_valid_colors()[0])
    c.apply_sequence(invert_sequence(scr))
    all_ok &= check("inverse scramble solves it", c.is_solved())

    # Facelet string of the solved cube.
    all_ok &= check(
        "facelet string",
        Cube.solved().to_facelet_string()
        == "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB",
    )

    # Stage predicates on a solved cube.
    c = Cube.solved()
    all_ok &= check("solved cube passes all stages",
                    all(pred(c, "D") for _, pred in BEGINNER_STAGES))

    # U turn keeps the D cross and both layers, breaks nothing below.
    c = Cube.solved()
    c.apply("U")
    all_ok &= check("U keeps D-cross", cross_done(c, "D"))
    all_ok &= check("U keeps first layer", first_layer_done(c, "D"))
    all_ok &= check("U keeps second layer", second_layer_done(c, "D"))
    c = Cube.solved()
    c.apply("R")
    all_ok &= check("R breaks the D first layer", not first_layer_done(c, "D"))

    # Corner-view scan maps (vision.py imports Qt lazily enough to allow
    # headless use of its pure-geometry tables).
    from rubikpi.vision import VIEW_MAPS

    all_ok &= check(
        "scan maps are permutations",
        all(sorted(idxs) == list(range(9))
            for vmap in VIEW_MAPS for _, idxs in vmap.values()),
    )
    v0 = VIEW_MAPS[0]
    all_ok &= check(
        "view 1 front vertex is the URF corner (U8, F2, R0)",
        (v0["top"][1][0], v0["left"][1][0], v0["right"][1][0]) == (8, 2, 0),
    )
    # View 2 must read exactly what view 1 reads on the cube reoriented
    # by "y x2" (white top / green left -> yellow top / orange left).
    c = Cube.solved()
    c.apply_sequence(Cube.random_scramble(25, random.Random(11)))
    r = c.copy()
    r.apply_sequence("y x2")
    consistent = True
    for panel in ("top", "left", "right"):
        f1, m1 = VIEW_MAPS[0][panel]
        f2, m2 = VIEW_MAPS[1][panel]
        for cell in range(9):
            if c.faces[f2][m2[cell]] != r.faces[f1][m1[cell]]:
                consistent = False
    all_ok &= check("view 2 = view 1 of the cube after y x2", consistent)

    # Solvability check: accepts real states, rejects impossible ones.
    legal = all(Cube.solved().moved(m).is_solvable()[0] for m in ALL_MOVES)
    rng2 = random.Random(21)
    for _ in range(50):
        probe = Cube.solved()
        probe.apply_sequence(Cube.random_scramble(rng2.randint(1, 30), rng2))
        legal &= probe.is_solvable()[0]
    all_ok &= check("real cube states are accepted", legal)

    twisted = Cube.solved()
    a, b, d = (twisted.faces["U"][8], twisted.faces["R"][0],
               twisted.faces["F"][2])
    twisted.faces["U"][8], twisted.faces["R"][0], twisted.faces["F"][2] = \
        b, d, a
    all_ok &= check("a twisted corner is rejected",
                    not twisted.is_solvable()[0])
    flipped = Cube.solved()
    flipped.faces["U"][5], flipped.faces["R"][1] = (flipped.faces["R"][1],
                                                    flipped.faces["U"][5])
    all_ok &= check("a flipped edge is rejected", not flipped.is_solvable()[0])
    swapped = Cube.solved()
    for (f1, i1), (f2, i2) in ((("U", 5), ("U", 7)), (("R", 1), ("F", 1))):
        swapped.faces[f1][i1], swapped.faces[f2][i2] = (swapped.faces[f2][i2],
                                                        swapped.faces[f1][i1])
    all_ok &= check("two swapped edges are rejected",
                    not swapped.is_solvable()[0])

    # Colour scheme: one source of truth, and mirror schemes rejected.
    from rubikpi.cube import DEFAULT_SCHEME, scheme_is_possible
    from rubikpi.vision import EXPECTED_CENTER

    all_ok &= check("the cube's colour scheme is physically possible",
                    scheme_is_possible(DEFAULT_SCHEME))
    all_ok &= check("scan guidance uses that same scheme",
                    EXPECTED_CENTER == DEFAULT_SCHEME)
    mirrored = dict(DEFAULT_SCHEME)
    mirrored["R"], mirrored["L"] = mirrored["L"], mirrored["R"]
    all_ok &= check("a mirror-image scheme is rejected",
                    not scheme_is_possible(mirrored))
    mixed = Cube.solved()
    for i in range(9):
        mixed.faces["R"][i], mixed.faces["L"][i] = (mixed.faces["L"][i],
                                                    mixed.faces["R"][i])
    all_ok &= check("a cube with swapped red/orange centres is rejected",
                    not mixed.is_solvable()[0])

    # Camera position: your left/right depend on which side it watches.
    from rubikpi.cube import FACES, OPPOSITE, held_faces

    grips = {cam: held_faces(OPPOSITE[cam], "U") for cam in ("F", "R", "B", "L")}
    all_ok &= check(
        "camera on the back -> R is on your right; camera on the front -> "
        "R is on your left",
        grips["B"]["R"] == "R" and grips["F"]["L"] == "R",
    )
    all_ok &= check(
        "every grip is a real way to hold the cube",
        all(sorted(g.values()) == sorted(FACES) for g in grips.values()),
    )
    impossible = 0
    for front, up in (("U", "U"), ("U", "D"), ("F", "B")):
        try:
            held_faces(front, up)
        except ValueError:
            impossible += 1
    all_ok &= check("impossible grips are refused, not crashed on",
                    impossible == 3)

    # Follow-along tracker: rotations and turns, from any orientation.
    from rubikpi import tracker as tk

    c = Cube.solved()
    c.apply_sequence(Cube.random_scramble(20, random.Random(4)))
    rot_ok = True
    for o in range(len(tk.ORIENTATIONS)):
        m = tk.best_match(c, tk.predict(c, o))
        rot_ok &= m.move == "" and m.orientation == o and m.confident
    all_ok &= check("tracker: rotation-only seen in all 24 orientations",
                    rot_ok)
    turn_ok = True
    for mv in ALL_MOVES:
        turned = c.moved(mv)
        for o in (0, 7, 13, 22):
            m = tk.best_match(c, tk.predict(turned, o))
            turn_ok &= m.move == mv and m.confident
    all_ok &= check("tracker: every move recognised from any angle", turn_ok)
    noisy = tk.predict(c.moved("R'"), 7)
    noisy["U"][3] = "X"
    all_ok &= check("tracker: survives one misread sticker",
                    tk.best_match(c, noisy).move == "R'")

    # Three faces genuinely cannot determine the cube: build two legal
    # states that agree on U, F and R but differ behind.
    twin = Cube.solved()
    slots = ((("D", 3), ("L", 7)), (("D", 7), ("B", 7)), (("B", 5), ("L", 3)))
    vals = {s: [twin.faces[f][i] for f, i in s] for s in slots}
    for dst, src in zip(slots, (slots[1], slots[2], slots[0])):
        for (f, i), v in zip(dst, vals[src]):
            twin.faces[f][i] = v
    all_ok &= check(
        "two different legal cubes can share the same three faces",
        twin.is_solvable()[0]
        and all(twin.faces[f] == Cube.solved().faces[f] for f in "UFR")
        and twin.faces != Cube.solved().faces,
    )

    # Solver round-trip (only if a solver backend is installed).
    try:
        from rubikpi.solver import solve

        scr = Cube.random_scramble(25, random.Random(7))
        c = Cube.solved()
        c.apply_sequence(scr)
        result = solve(c, mode="beginner")
        if result.moves:
            d = c.copy()
            d.apply_sequence(result.moves)
            all_ok &= check(
                f"solver backend '{result.backend}' solves a scramble "
                f"({len(result.moves)} moves)",
                d.is_solved(),
            )
        else:
            print(f"  [skip] solver backend unavailable: {result.error}")
    except Exception as exc:  # pragma: no cover - informational only
        print(f"  [skip] solver test skipped: {exc}")

    print("PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
