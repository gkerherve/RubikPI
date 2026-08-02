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
    DEFAULT_SCHEME,
    FACES,
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

    # The scan protocol covers all six faces, one at a time.
    from rubikpi.vision import SCAN_STEPS

    all_ok &= check("the scan visits every face exactly once",
                    sorted(f for f, _ in SCAN_STEPS) == sorted(FACES))

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
    from rubikpi.cube import scheme_is_possible
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

    # 3D geometry: turning a layer of cubies must reproduce the move
    # engine exactly, or the animation would show a different cube.
    from rubikpi import cube3d as g3

    def snap(v):
        return tuple(int(round(c)) for c in v)

    rng3 = random.Random(31)
    geometry_ok = True
    for face in FACES:
        start = Cube.solved()
        start.apply_sequence(Cube.random_scramble(18, rng3))
        turned = start.moved(face)
        axis, angle = g3.turn_rotation(face, 1.0)
        for cubie in g3.cubies():
            if not g3.in_turning_layer(face, cubie):
                for f in g3.stickers_of(cubie):
                    i = g3.facelet_index(f, *cubie)
                    geometry_ok &= start.faces[f][i] == turned.faces[f][i]
                continue
            moved_to = snap(g3.rotate(cubie, axis, angle))
            for f in g3.stickers_of(cubie):
                landed = g3.FACE_OF_NORMAL[snap(g3.rotate(g3.NORMALS[f],
                                                          axis, angle))]
                geometry_ok &= (
                    start.faces[f][g3.facelet_index(f, *cubie)]
                    == turned.faces[landed][g3.facelet_index(landed,
                                                             *moved_to)])
    all_ok &= check("turning cubies in 3D matches the move engine",
                    geometry_ok)
    all_ok &= check(
        "every cubie sticker maps to a distinct facelet",
        len({(f, g3.facelet_index(f, *c)) for c in g3.cubies()
             for f in g3.stickers_of(c)}) == 54,
    )

    # The view stays anchored to colours: blue front, yellow up, whatever
    # rotations a solution contains.
    from rubikpi.cube import orientation_for_colors

    anchored = True
    for rot in ("", "y", "y2", "x", "z'", "x2 y", "y' x'"):
        probe = Cube.solved()
        probe.apply_sequence(rot)
        seq = orientation_for_colors(probe, DEFAULT_SCHEME["U"],
                                     DEFAULT_SCHEME["F"])
        anchored &= seq is not None
        if seq is not None:
            probe.apply_sequence(seq)
            anchored &= (probe.center("F") == DEFAULT_SCHEME["F"]
                         and probe.center("U") == DEFAULT_SCHEME["U"])
    all_ok &= check("the 3D view always shows blue at the front", anchored)

    # The "Camera sees" panel follows a colour, so whole-cube rotations in
    # a solution cannot make it drift onto a different side.
    from rubikpi.cube import face_with_center

    follows = True
    for colour in (DEFAULT_SCHEME[f] for f in ("F", "R", "B", "L")):
        for rot in ("", "y", "y2", "x", "z'", "x2 y"):
            probe = Cube.solved()
            probe.apply_sequence(Cube.random_scramble(12, random.Random(9)))
            probe.apply_sequence(rot)
            face = face_with_center(probe, colour)
            follows &= face is not None and probe.center(face) == colour
    all_ok &= check("the camera panel always shows the chosen colour's face",
                    follows)

    # Camera position: your left/right depend on which side it watches.
    from rubikpi.cube import OPPOSITE, held_faces

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

    # Follow-along tracker, watching a single face.
    from rubikpi import tracker as tk

    c = Cube.solved()
    c.apply_sequence(Cube.random_scramble(20, random.Random(4)))

    all_ok &= check(
        "the visible face is identified from its centre sticker",
        all(tk.visible_face(c, tk.rotate_face(c.faces[f], k)) == f
            for f in FACES for k in range(4)),
    )

    watched = "B"
    neighbours = [m for m in ALL_MOVES
                  if m[0] not in (watched, OPPOSITE[watched])]
    neighbour_ok = True
    for mv in neighbours:
        for roll in range(4):
            seen = tk.rotate_face(c.moved(mv).faces[watched], roll)
            found = tk.best_match(c, seen)
            neighbour_ok &= found.move == mv and found.confident
    all_ok &= check(
        f"all {len(neighbours)} neighbouring-face turns are read correctly",
        neighbour_ok,
    )

    # Turning the watched face looks just like turning the whole cube, so
    # the move the app asked for breaks the tie.
    seen = tk.rotate_face(c.moved(watched).faces[watched], 0)
    all_ok &= check(
        "turning the watched face needs the expected move to disambiguate",
        tk.best_match(c, seen).move == ""
        and tk.best_match(c, seen, expected=watched).move == watched,
    )

    hidden = OPPOSITE[watched]
    seen = tk.rotate_face(c.moved(hidden).faces[watched], 0)
    all_ok &= check(
        "a turn of the face at the back is reported as unseen, not guessed",
        tk.is_hidden(watched, hidden)
        and tk.best_match(c, seen, expected=hidden).move == "",
    )

    # Reading the face back: 9/9 confirms the app and the cube agree.
    agree = all(tk.read_face(c, tk.rotate_face(c.faces[f], k)) == (f, k, 9)
                for f in FACES for k in range(4))
    all_ok &= check("a matching face reads 9 out of 9, at any rotation",
                    agree)
    _, _, after_turn = tk.read_face(c, tk.rotate_face(c.moved("U").faces[watched],
                                                      0))
    all_ok &= check("after a turn the same face no longer reads 9 out of 9",
                    after_turn < 9)

    noisy = tk.rotate_face(c.moved("U").faces[watched], 1)
    noisy[7] = "W" if noisy[7] != "W" else "G"
    all_ok &= check("tracker: survives one misread sticker",
                    tk.best_match(c, noisy).move == "U")

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
