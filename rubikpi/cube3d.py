"""Geometry for drawing the cube as 27 little cubies.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Coordinates run -1..+1 on each axis: x to the right (+1 is the R face),
y up (+1 is U), z towards the viewer (+1 is F).  Every sticker is a
square on the outside of one cubie, so turning a layer is an honest 3D
rotation of the cubies in it — the stickers on the *sides* of the layer
travel with it, which is what makes a turn read as a turn.

Pure geometry: no Qt here, so :mod:`rubikpi.selftest` can check the
sticker mapping against the move engine without a display.
"""

from __future__ import annotations

import math

#: Outward normal of each face.
NORMALS: dict[str, tuple[int, int, int]] = {
    "U": (0, 1, 0), "D": (0, -1, 0), "F": (0, 0, 1),
    "B": (0, 0, -1), "R": (1, 0, 0), "L": (-1, 0, 0),
}

FACE_OF_NORMAL = {n: f for f, n in NORMALS.items()}

#: Axis index and rotation sign for a clockwise turn of each face.
#: Faces on the positive side of their axis turn the negative way round
#: when seen from outside — hence the sign.
TURN_AXIS: dict[str, tuple[int, int, int]] = {
    "R": (0, 1, -1), "L": (0, -1, 1),
    "U": (1, 1, -1), "D": (1, -1, 1),
    "F": (2, 1, -1), "B": (2, -1, 1),
}


def facelet_index(face: str, x: int, y: int, z: int) -> int:
    """Which of a face's nine stickers sits on the cubie at (x, y, z).

    Follows the convention in :mod:`rubikpi.cube`: U seen from above with
    B at the top, D seen from below with F at the top, and the four sides
    seen straight on with U at the top.
    """
    if face == "U":
        return (z + 1) * 3 + (x + 1)
    if face == "D":
        return (1 - z) * 3 + (x + 1)
    if face == "F":
        return (1 - y) * 3 + (x + 1)
    if face == "B":
        return (1 - y) * 3 + (1 - x)
    if face == "R":
        return (1 - y) * 3 + (1 - z)
    if face == "L":
        return (1 - y) * 3 + (z + 1)
    raise ValueError(f"unknown face {face!r}")


def rotate(point: tuple[float, float, float], axis: int, angle: float
           ) -> tuple[float, float, float]:
    """Rotate a point (or a normal) about one of the three axes."""
    x, y, z = point
    c, s = math.cos(angle), math.sin(angle)
    if axis == 0:                       # about x
        return (x, y * c - z * s, y * s + z * c)
    if axis == 1:                       # about y
        return (x * c + z * s, y, -x * s + z * c)
    return (x * c - y * s, x * s + y * c, z)   # about z


def turn_rotation(face: str, quarters: float) -> tuple[int, float]:
    """Axis and angle that turn *face* clockwise by *quarters* turns."""
    axis, _, sign = TURN_AXIS[face]
    return axis, sign * quarters * math.pi / 2.0


def in_turning_layer(face: str, cubie: tuple[int, int, int]) -> bool:
    """Is this cubie part of the layer that *face* turns?"""
    axis, layer, _ = TURN_AXIS[face]
    return cubie[axis] == layer


def cubies() -> list[tuple[int, int, int]]:
    """Every cubie position that has at least one sticker."""
    return [(x, y, z)
            for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)
            if (x, y, z) != (0, 0, 0)]


def stickers_of(cubie: tuple[int, int, int]) -> list[str]:
    """The faces this cubie shows to the outside world."""
    x, y, z = cubie
    out = []
    if x == 1:
        out.append("R")
    if x == -1:
        out.append("L")
    if y == 1:
        out.append("U")
    if y == -1:
        out.append("D")
    if z == 1:
        out.append("F")
    if z == -1:
        out.append("B")
    return out


def sticker_quad(cubie: tuple[int, int, int], face: str, gap: float = 0.06,
                 ) -> list[tuple[float, float, float]]:
    """The four corners of one sticker, in cube coordinates."""
    nx, ny, nz = NORMALS[face]
    # Two in-plane axes perpendicular to the normal.
    if abs(nx):
        u, v = (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
    elif abs(ny):
        u, v = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    else:
        u, v = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    cx, cy, cz = cubie
    # Cubie centres sit 1 apart; the sticker sits on the outer surface.
    ox = cx + nx * 0.5
    oy = cy + ny * 0.5
    oz = cz + nz * 0.5
    half = 0.5 - gap
    corners = []
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        corners.append((ox + (u[0] * su + v[0] * sv) * half,
                        oy + (u[1] * su + v[1] * sv) * half,
                        oz + (u[2] * su + v[2] * sv) * half))
    return corners


#: Direction the scene is viewed from, for depth sorting and back-face
#: removal.  Matches the isometric projection below.
VIEW = (1.0, 1.0, 1.0)


def project(point: tuple[float, float, float], scale: float,
            ) -> tuple[float, float]:
    """Isometric projection: U on top, F to the lower left, R lower right."""
    x, y, z = point
    return ((x - z) * 0.8660254 * scale, ((x + z) * 0.5 - y) * scale)


def depth(point: tuple[float, float, float]) -> float:
    """Bigger means nearer the viewer."""
    return point[0] * VIEW[0] + point[1] * VIEW[1] + point[2] * VIEW[2]


def faces_toward_viewer(normal: tuple[float, float, float]) -> bool:
    return depth(normal) > 0.15
