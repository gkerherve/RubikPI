"""Deciding all 54 sticker colours together rather than one at a time.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Classifying each sticker on its own throws away the one thing that is
certain about a cube: **there are exactly nine of every colour.**  Judged
alone, a washed-out red only has to look more like orange than like red
to be called orange, and nothing notices that the cube now has eleven
oranges and seven reds.

Deciding all of them together turns that count into a constraint.  Each
sticker no longer has to *be* red in absolute terms — it only has to be a
better red than its competitors, which is exactly the question the
red/orange and white/yellow pairs turn on.  The scan's own centres serve
as the reference colours, so the comparison is against this cube under
this lighting.

The result is the cheapest set of assignments that uses each colour nine
times, found exactly (not greedily) with the Hungarian algorithm.  At
48 stickers this takes well under a millisecond, so there is no reason to
approximate and no need for scipy.
"""

from __future__ import annotations

from rubikpi.cube import FACES

#: A colour reading in OpenCV's Lab space.
Lab = tuple[float, float, float]

#: Stickers of each colour on a cube, and how many are not centres.
PER_COLOUR = 9
NON_CENTRE = PER_COLOUR - 1


def distance(a: Lab, b: Lab) -> float:
    """Perceptual distance, with lightness down-weighted as elsewhere."""
    return 0.30 * (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def hungarian(cost: list[list[float]]) -> list[int]:
    """Cheapest one-to-one assignment of rows to columns.

    The classic O(n^3) shortest-augmenting-path method with potentials.
    Returns the column chosen for each row; requires rows <= columns.
    """
    rows = len(cost)
    cols = len(cost[0]) if rows else 0
    if rows > cols:
        raise ValueError("need at least as many columns as rows")
    inf = float("inf")
    # 1-based bookkeeping, as the algorithm is usually written.
    u = [0.0] * (rows + 1)
    v = [0.0] * (cols + 1)
    match = [0] * (cols + 1)      # column -> row
    trail = [0] * (cols + 1)      # column -> previous column on the path
    for row in range(1, rows + 1):
        match[0] = row
        col = 0
        least = [inf] * (cols + 1)
        used = [False] * (cols + 1)
        while True:
            used[col] = True
            here = match[col]
            delta = inf
            nxt = -1
            for j in range(1, cols + 1):
                if used[j]:
                    continue
                weight = cost[here - 1][j - 1] - u[here] - v[j]
                if weight < least[j]:
                    least[j] = weight
                    trail[j] = col
                if least[j] < delta:
                    delta = least[j]
                    nxt = j
            for j in range(cols + 1):
                if used[j]:
                    u[match[j]] += delta
                    v[j] -= delta
                else:
                    least[j] -= delta
            col = nxt
            if match[col] == 0:
                break
        while col:
            previous = trail[col]
            match[col] = match[previous]
            col = previous

    chosen = [0] * rows
    for j in range(1, cols + 1):
        if match[j]:
            chosen[match[j] - 1] = j - 1
    return chosen


def assign(samples: list[Lab], refs: dict[str, Lab],
           capacity: int) -> tuple[list[str], list[float]]:
    """Give every sample a colour, using each colour *capacity* times.

    Also returns, per sample, how much worse the next-best colour would
    have been — small numbers mark the stickers worth a second look.
    """
    letters = sorted(refs)
    slots = [letter for letter in letters for _ in range(capacity)]
    if len(samples) != len(slots):
        raise ValueError(f"{len(samples)} samples cannot fill "
                         f"{len(slots)} slots")
    cost = [[distance(sample, refs[slot]) for slot in slots]
            for sample in samples]
    chosen = hungarian(cost)

    picked = [slots[c] for c in chosen]
    margins = []
    for sample, letter in zip(samples, picked):
        mine = distance(sample, refs[letter])
        others = [distance(sample, refs[other])
                  for other in letters if other != letter]
        margins.append(min(others) - mine)
    return picked, margins


def resolve_scan(samples: dict[str, list[Lab]], scheme: dict[str, str],
                 ) -> tuple[dict[str, list[str]], list[tuple[str, int, float]]]:
    """Turn 54 raw readings into a cube with nine of every colour.

    Each face's centre is that colour's reference — the protocol fixes
    which centre every scan step shows, so those six readings are ground
    truth for this cube in this light.  The other 48 stickers are then
    assigned eight slots per colour.

    Returns the six faces, and the stickers whose colour was the closest
    call, worst first, as (face, index, margin).
    """
    missing = [f for f in FACES if len(samples.get(f, [])) != 9]
    if missing:
        raise ValueError("no readings for face " + ", ".join(missing))

    refs = {scheme[face]: samples[face][4] for face in FACES}
    if len(refs) != 6:
        raise ValueError("the colour scheme does not name six colours")

    spots = [(face, i) for face in FACES for i in range(9) if i != 4]
    picked, margins = assign([samples[f][i] for f, i in spots], refs,
                             NON_CENTRE)

    faces = {face: ["X"] * 9 for face in FACES}
    for face in FACES:
        faces[face][4] = scheme[face]
    for (face, i), letter in zip(spots, picked):
        faces[face][i] = letter

    doubtful = sorted(
        ((face, i, margin) for (face, i), margin in zip(spots, margins)),
        key=lambda item: item[2],
    )
    return faces, doubtful
