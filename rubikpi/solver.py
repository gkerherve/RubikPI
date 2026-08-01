"""Solver backends and stage segmentation for RubikPI.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Two optional backends are used, in this order of preference per mode:

* ``rubik_solver`` (pure Python) — provides the human "Beginner" and "CFOP"
  methods, which map naturally onto the staged modes.
* ``kociemba`` (two-phase algorithm) — near-optimal move counts for the
  "Speed" mode.

Both are optional; :func:`solve` degrades gracefully and reports what is
missing so the UI can tell the user to ``pip install`` the backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rubikpi.cube import BEGINNER_STAGES, CFOP_STAGES, Cube

MODES = {
    "beginner": "Beginner — layer by layer",
    "cfop": "CFOP — Cross / F2L / OLL / PLL",
    "speed": "Speed — Kociemba two-phase",
}


@dataclass
class Stage:
    label: str
    moves: list[str] = field(default_factory=list)
    start_index: int = 0  # index of the first move within the full solution


@dataclass
class Solution:
    moves: list[str] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)
    backend: str = ""
    mode: str = "beginner"
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

#: The 24 cube orientations, as rotation sequences from the identity.
_ORIENTATIONS: list[str] = [
    (spin + " " + tilt).strip()
    for tilt in ("", "x", "x2", "x'", "z", "z'")
    for spin in ("", "y", "y2", "y'")
]

#: Whole-cube rotation / slice move equivalent to turning a given face.
_ROTATION_LIKE = {"U": "y", "D": "y'", "R": "x", "L": "x'", "F": "z", "B": "z'"}
_SLICE_LIKE = {"L": "M", "R": "M'", "D": "E", "U": "E'", "F": "S", "B": "S'"}


def _orient_sequence(cube: Cube, top: str, front: str) -> str | None:
    """Rotation sequence putting colour *top* on U and *front* on F."""
    for seq in _ORIENTATIONS:
        probe = cube.copy()
        probe.apply_sequence(seq)
        if probe.center("U") == top and probe.center("F") == front:
            return seq
    return None


def _face_map(orient_seq: str) -> dict[str, str]:
    """solver-frame face -> user-frame face, for a given reorientation."""
    probe = Cube(faces={f: [f] * 9 for f in Cube.solved().faces})
    probe.apply_sequence(orient_seq)
    return {f: probe.center(f) for f in probe.faces}


def _merge_suffix(token: str, suffix: str) -> str:
    """Compose a translated base token (may carry ') with a move suffix."""
    base, prime = (token[:-1], True) if token.endswith("'") else (token, False)
    if suffix == "2":
        return base + "2"
    if suffix == "'":
        prime = not prime
    return base + ("'" if prime else "")


def _translate_moves(moves: list[str], fmap: dict[str, str]) -> list[str]:
    """Rewrite solver-frame moves into the user's frame."""
    out: list[str] = []
    for m in moves:
        core, suffix = m, ""
        if m.endswith(("'", "2")):
            core, suffix = m[:-1], m[-1]
        if core in fmap:  # plain face turn
            out.append(fmap[core] + suffix)
        elif core.upper() in ("X", "Y", "Z"):
            like = {"X": "R", "Y": "U", "Z": "F"}[core.upper()]
            out.append(_merge_suffix(_ROTATION_LIKE[fmap[like]], suffix))
        elif core in ("M", "E", "S"):
            like = {"M": "L", "E": "D", "S": "F"}[core]
            out.append(_merge_suffix(_SLICE_LIKE[fmap[like]], suffix))
        else:
            raise ValueError(f"Cannot translate solver move {m!r}")
    return out


def _solve_rubik_solver(cube: Cube, method: str) -> list[str]:
    from rubik_solver import utils  # type: ignore

    # rubik_solver silently loops unless the cube is oriented its way:
    # yellow centre up, red centre front.  Reorient a copy, solve, then
    # translate the moves back into the user's orientation.
    orient = _orient_sequence(cube, top="Y", front="R")
    if orient is None:
        raise ValueError("cube has no yellow/red centres to orient by")
    probe = cube.copy()
    probe.apply_sequence(orient)
    # rubik_solver wants 54 lowercase colour letters in ULFRBD order.
    moves = [str(m) for m in utils.solve(probe.to_color_string("ULFRBD"),
                                         method)]
    return _translate_moves(moves, _face_map(orient))


def _solve_kociemba(cube: Cube) -> list[str]:
    import kociemba  # type: ignore

    return kociemba.solve(cube.to_facelet_string()).split()


def solve(cube: Cube, mode: str = "beginner") -> Solution:
    """Solve *cube* with the requested mode, returning moves + stages."""
    if cube.is_solved():
        return Solution(backend="none needed", mode=mode)
    # Check the state is physically possible *before* asking a backend:
    # kociemba would only answer "cubestring is invalid", which tells the
    # user nothing about which sticker to look at.
    ok, why = cube.is_solvable()
    if not ok:
        return Solution(mode=mode, error=f"The scan cannot be a real cube. "
                                         f"{why}")

    attempts: list[tuple[str, str]] = {
        "beginner": [("rubik_solver", "Beginner"), ("kociemba", "")],
        "cfop": [("rubik_solver", "CFOP"), ("rubik_solver", "Beginner"),
                 ("kociemba", "")],
        "speed": [("kociemba", ""), ("rubik_solver", "Kociemba"),
                  ("rubik_solver", "Beginner")],
    }.get(mode, [("rubik_solver", "Beginner"), ("kociemba", "")])

    errors: list[str] = []
    for backend, method in attempts:
        try:
            if backend == "kociemba":
                moves = _solve_kociemba(cube)
                name = "kociemba"
            else:
                moves = _solve_rubik_solver(cube, method)
                name = f"rubik_solver/{method}"
            moves = _normalise(moves)
            # Trust nothing: verify the solution on our own model.
            probe = cube.copy()
            probe.apply_sequence(moves)
            if not probe.is_solved():
                errors.append(f"{name}: produced a non-solving sequence")
                continue
            sol = Solution(moves=moves, backend=name, mode=mode)
            sol.stages = segment_stages(cube, moves, mode, name)
            return sol
        except ImportError as exc:
            # rubik_solver 0.2.0 imports the `imp` module, which Python 3.12
            # removed — that is a version problem, not a missing package.
            if "imp" in str(exc):
                errors.append(f"{backend}: needs Python 3.11 or older")
            else:
                errors.append(f"{backend}: not installed")
        except Exception as exc:  # noqa: BLE001 - report to the UI
            errors.append(f"{backend}: {exc}")

    # De-duplicate: the same backend is tried several times per mode, and
    # repeating "not installed" three times helps nobody.
    seen: list[str] = []
    for e in errors:
        if e not in seen:
            seen.append(e)
    missing = [e.split(":")[0] for e in seen if e.endswith("not installed")]
    if len(missing) == len(seen):
        return Solution(mode=mode, error=(
            f"No solver installed for this mode ({', '.join(missing)} "
            f"missing).  Install one with:  pip install rubik-solver kociemba"))
    return Solution(mode=mode, error="; ".join(seen))


def _normalise(moves: list[str]) -> list[str]:
    """Canonicalise notation variants like R3 -> R', drop empty tokens."""
    out: list[str] = []
    for m in moves:
        m = m.strip()
        if not m:
            continue
        if m.endswith("3"):
            m = m[:-1] + "'"
        if m.endswith("1"):
            m = m[:-1]
        out.append(m)
    return out


# ---------------------------------------------------------------------------
# Stage segmentation
# ---------------------------------------------------------------------------

def segment_stages(cube: Cube, moves: list[str], mode: str,
                   backend: str = "") -> list[Stage]:
    """Split *moves* into human stages by replaying them on a copy.

    Only layer-by-layer solutions have real stages.  A two-phase
    (Kociemba) solution scrambles and reassembles the cube in a way no
    human method follows, so labelling parts of it "Cross" or "F2L" would
    be a lie — it is reported as one block instead.
    """
    stage_defs = CFOP_STAGES if mode == "cfop" else BEGINNER_STAGES
    if mode == "speed" or backend.startswith("kociemba"):
        return [Stage("Fewest-moves solution (not layer by layer)",
                      list(moves), 0)]

    # The cross face is whichever of U/D completes its cross first: trying
    # only one can latch onto the *other* face's cross forming late in the
    # solve and lump everything into one giant stage.
    candidates = [b for b in (_find_boundaries(cube, moves, stage_defs, f)
                              for f in ("D", "U")) if b is not None]
    if not candidates:
        return [Stage("Solution", list(moves), 0)]
    boundaries = min(candidates, key=lambda b: (b[0], sum(b)))

    stages: list[Stage] = []
    start = 0
    for (label, _), end in zip(stage_defs, boundaries):
        stages.append(Stage(label, moves[start:end], start))
        start = end
    if start < len(moves):
        stages.append(Stage("Finish", moves[start:], start))
    return [s for s in stages if s.moves]


def _find_boundaries(cube: Cube, moves: list[str],
                     stage_defs: list, face: str) -> list[int] | None:
    """Move index (exclusive) at which each stage first completes, or None."""
    probe = cube.copy()
    boundaries: list[int] = []
    stage_i = 0
    # A stage may already be complete before any move is played.
    while stage_i < len(stage_defs) and stage_defs[stage_i][1](probe, face):
        boundaries.append(0)
        stage_i += 1
    for i, m in enumerate(moves):
        probe.apply(m)
        while stage_i < len(stage_defs) and stage_defs[stage_i][1](probe, face):
            boundaries.append(i + 1)
            stage_i += 1
    return boundaries if stage_i == len(stage_defs) else None
