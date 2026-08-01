# RubikPI

**RubikPI** is a very visual Rubik's Cube solving companion, part of the
KherveTools family. Point your webcam at a cube, scan its six faces, and
RubikPI shows you the state, the staged solution, and a live *tree of
possibilities* from wherever you currently stand.

```
┌───────────────┬────────────────────┬─────────────────────┐
│ 1 · Camera    │ 2 · Your cube      │ 3 · Tree of         │
│               │                    │     possibilities   │
│ live preview  │   isometric U/F/R  │  Solution           │
│ 3x3 colour    │       view         │   ├─ Cross (6)      │
│ recognition   │                    │   ├─ F2L (24)       │
│ guided scan   │   unfolded net     │   ├─ OLL (9)        │
│ of all faces  │   of all 6 faces   │   └─ PLL (12)       │
│               │                    │  Possibilities      │
│ [demo mode]   │  ◀ ▶ play controls │   ├─ R  → 38 off    │
│               │                    │   └─ U' → 44 off    │
└───────────────┴────────────────────┴─────────────────────┘
```

## Features

- **Camera face recognition** — a 3x3 grid overlay with per-sticker colour
  detection (HSV) and auto-capture once the reading is steady. A guided
  6-step protocol tells you exactly how to hold the cube for each face.
- **Live cube view** — an isometric 3-face view plus the full unfolded net;
  every scanned face and every played move updates it instantly.
- **Solving modes**
  - *Beginner* — Cross → First layer → Second layer → Last layer.
  - *CFOP* — Cross → F2L → OLL → PLL.
  - *Speed* — Kociemba two-phase (about 20 moves).
- **Tree of possibilities** — every legal move from the current position,
  scored by distance from solved, lazily expandable a few plies deep.
- **Playback** — step through the solution move by move (with the turning
  face highlighted) or press Play and watch it go.
- **No camera? No problem** — the Demo scramble button loads a random
  scramble so everything works without hardware.

## Install & run

```bash
pip install -r requirements.txt
python RubikPI.py
```

Solver backends are optional but recommended:

```bash
pip install rubik-solver kociemba
```

(`rubik-solver` powers the Beginner/CFOP staged solutions, `kociemba` the
short Speed solutions. RubikPI re-verifies every solution on its own move
engine before showing it.)

## Self-test

```bash
python -m rubikpi.selftest
```

Runs headless (no Qt, no camera) and checks the move engine, the stage
predicates and — when a backend is installed — a full solve round-trip.

## License

GPL v3 — Copyright (C) 2026 Gwilherm Kerherve.
