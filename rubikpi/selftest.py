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
