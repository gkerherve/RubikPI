# RubikPI — project rules for Claude

RubikPI is a member of the **KherveTools** family and follows the same
conventions as the other tools (KhervePY, KherveBook, KherveSheet, …).

## What RubikPI is

A very visual Rubik's Cube solving companion written in **Python + Qt**
(PyQt6) with **OpenCV** for camera capture. Three frames side by side:

1. **Camera** (left) — sees the cube, recognises each face's 3x3 colours.
2. **Your cube** (middle) — isometric 3-face view + full unfolded net,
   updating live as faces are scanned and as solution moves play.
3. **Tree of possibilities** (right) — the staged solution plus a lazy tree
   of every legal move from the current position with a distance score.

Solving modes: **Beginner** (Cross → first layer → second layer → last
layer), **CFOP** (Cross → F2L → OLL → PLL) and **Speed** (Kociemba
two-phase). Solver backends (`rubik-solver`, `kociemba`) are optional and
every solution is re-verified on RubikPI's own move engine before display.

## Workflow rules (KherveTools)

1. **Commit and push on every message.** Each change the user asks for ends
   with a commit and a push to the designated branch.
2. **Bump the version on every push.** Update `__version__` in
   `rubikpi/__init__.py` and the version in `pyproject.toml`/`CHANGELOG.md`
   before each push. Use semantic-ish bumps: patch for fixes, minor for
   features. The version is shown in the window title.
3. **Keep `CHANGELOG.md` current** — add an entry describing what changed
   for the new version.
4. **Never overwrite user data.** Files are written UTF-8 with `\n` endings.
5. **Match the house style.** Every module starts with the GPL v3 header
   block and `Copyright (C) 2026 Gwilherm Kerherve`.

## Code conventions

- Python 3.10+ with `from __future__ import annotations`.
- Qt bindings: **PyQt6**. OpenCV (`opencv-python`) is imported lazily so the
  app and the headless self-test run without it.
- Camera capture and solving run on worker threads (`QThread`), never on the
  GUI thread.
- The cube model (`rubikpi/cube.py`) is pure Python with no Qt imports; keep
  it that way so `python -m rubikpi.selftest` stays headless.
- After touching `cube.py` or `solver.py`, run `python -m rubikpi.selftest`
  and make sure it prints `PASS`.

## Layout

```
RubikPI.py             entry-point shim  ->  rubikpi.app.main()
rubikpi/
  __init__.py          __version__ lives here
  app.py               main(): builds QApplication + MainWindow
  main_window.py       3-frame splitter, modes, solve worker, playback
  cube.py              facelet cube model, move engine, stage predicates
  solver.py            backends (rubik-solver / kociemba) + stage split
  vision.py            CameraWorker thread + HSV colour classification
  camera_panel.py      left frame: preview, guided 6-face scan
  cube_view.py         middle frame: isometric view + unfolded net
  solution_tree.py     right frame: staged solution + possibility tree
  selftest.py          headless checks: python -m rubikpi.selftest
```

## Running

```bash
pip install -r requirements.txt
python RubikPI.py
```
