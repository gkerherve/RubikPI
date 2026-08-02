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

- **Camera face recognition** — one face at a time. The face is located in
  the frame (contour detection), colours are classified in Lab space and
  self-calibrate from your own stickers, and steady readings auto-capture.
  A guided 6-step protocol tells you exactly how to hold the cube.
- **Solve timer** — starts on your first move, stops when the cube is
  solved, with the move count beside it.
- **Fingers are not mistaken for stickers** — skin is warm and washed out
  where white stickers are neutral, so a finger reads as "hidden" rather
  than white. Hidden stickers are left out of the matching instead of
  counted wrong, and a move whose evidence is under your fingers is
  never assumed done.
- **Follow me** — during a solve the camera keeps watching one face. The
  centre sticker tells it which side it is looking at, turning that face
  or any neighbour is recognised automatically, and the solution advances
  as you go. A turn of the face pointing away from the camera cannot be
  seen, and it says so instead of guessing.
- **Phone as camera** — the Camera field takes a device number or a stream
  URL. Use Windows 11's "connected camera" for Android (shows up as an
  extra number), or any IP-camera app (e.g. IP Webcam:
  `http://PHONE-IP:8080/video`), or Iriun/DroidCam/Camo virtual webcams.
- **Live cube view** — an isometric 3-face view plus the full unfolded net;
  every scanned face and every played move updates it instantly.
- **Solving modes**
  - *Beginner* — Cross → First layer → Second layer → Last layer.
  - *CFOP* — Cross → F2L → OLL → PLL.
  - *Speed* — Kociemba two-phase (about 20 moves).
- **Tree of possibilities** — every legal move from the current position,
  scored by distance from solved, lazily expandable a few plies deep.
- **The next move demonstrates itself** — it plays on a loop on the 3D
  cube, turning and snapping back, so you can copy it off the screen
  instead of decoding "D2". Step through move by move, or press Play and
  watch the whole solution go.
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
