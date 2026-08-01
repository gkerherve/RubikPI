# Changelog

All notable changes to RubikPI.

## 0.9.0 — 2026-08-01

You can watch the turns happen, and the camera works out its own side.

- **The cube is now drawn as 27 cubies in 3D** (new `cube3d` module,
  painter's algorithm, back-face removal) instead of three flat faces.
  That means **turns are animated properly**: the whole layer rotates,
  carrying the stickers on its sides with it, exactly like a real cube.
  A curved arrow shows the direction, and the motion eases in and out.
- Stepping forward, stepping back and follow-along moves all animate;
  jumping to a step does not (it is not a turn to watch).
- **The 3D view is anchored to colours**: the blue centre always faces
  you and the yellow centre is always on top, whatever rotations a
  solution contains, so the picture never spins under you.
- **The camera works out which side it is on by itself**, from the centre
  pieces it can see: hold the cube any way round and the "Camera sees"
  setting follows, keeping "on your right" honest. You can still set it
  by hand when the camera is off.
- The animation geometry is verified against the move engine rather than
  eyeballed: every cubie rotation must reproduce the model's own result,
  and the finished animation was checked pixel-for-pixel against the
  moved cube for all 12 move types.

RubikPI now knows which side of the cube the camera is on.

- New **"Camera sees"** setting (middle panel), defaulting to the green
  side — the usual way round, with you looking at the blue side. The
  camera watches from the opposite side to you, so this is what decides
  whether a move is on your right or your left.
- Every instruction now names the **colour**, which is unambiguous from
  any viewpoint, plus where it is as you hold it: "R — turn the RED face
  (on your right) clockwise". Move the camera to the blue side and the
  same move reads "turn the RED face (on your left) clockwise".
- Follow-along messages speak in colours too: "you turned it left — the
  red side now faces the camera".
- Fixed a crash: choosing the top or bottom face as the camera position
  asked for an impossible grip (bottom towards you *and* top up), and an
  exception inside a Qt signal handler terminates the whole application.
  The setting now offers only the four side faces, `held_faces()`
  rejects same-axis grips with a clear error, and the caller can no
  longer pass one.
- New self-tests: left/right flip with camera position, every grip is a
  real one, and impossible grips raise instead of crashing.

The cube's colour scheme is now yours, and defined in one place.

- Faces follow the centre colours: **yellow up, white down, blue front,
  green back, red right, orange left**. (The same physical cube as
  before, held the other way up — `x2` from white-up/green-front.)
- `cube.DEFAULT_SCHEME` is the single source of truth: expected centres,
  every scan instruction and the on-screen guides are generated from it,
  so a differently-coloured cube needs only those six letters changed.
  No colour words are hard-coded in the scan protocol any more.
- New check: six centre colours that would need a *mirror-image* cube are
  rejected with "two centres are swapped (most often red with orange, or
  white with yellow)". This catches a misread that every count-based
  check passes.
- Messages name the actual colours of the cube in use rather than
  assuming white and yellow are the top and bottom.

Follow-along tracking, plain-English steps, and honest error messages.

- **Follow me** (new button next to Play): the camera watches your cube
  while you solve it. Turn the cube any way you like — it recognises the
  rotation and says what you did ("you turned it left — now showing the
  back face") — and every face turn is matched and ticked off. Make a
  different move than suggested and it re-solves from where your cube
  actually is.
- The tracker matches the 27 visible stickers against all 24 orientations
  x 19 possibilities (18 moves + no move), so it separates a rotation
  from a turn. It tolerates one misread sticker and needs two agreeing
  frames before accepting a move. ~1 ms per frame, no GPU.
- **Panel 3 is now "What to do"**: a large card shows the next move
  spelled out ("R' — turn the RIGHT face anticlockwise") with stage and
  progress, then the numbered steps grouped by stage, each in words.
  The old move-explorer is folded away behind "What-if explorer",
  collapsed by default.
- **Cube validity check**: a scan is now verified against the physics of
  a real cube (every corner/edge a real piece, corner-twist, edge-flip
  and permutation parity). Instead of kociemba's "Probably cubestring is
  invalid" you get "A corner is twisted in place — one corner's three
  stickers are read in the wrong order."
- Solver errors are de-duplicated, and `rubik_solver` failing on Python
  3.12 (it imports the removed `imp` module) is reported as "needs
  Python 3.11 or older" rather than "not installed"; requirements.txt
  marks it accordingly.
- Two-phase (kociemba) solutions are no longer mislabelled with human
  stage names like "Cross" or "F2L" — they are shown as one
  "Fewest-moves solution (not layer by layer)" block.
- New self-tests: solvability accept/reject cases, tracker recognition
  across all orientations, and a proof that three faces cannot determine
  a cube (two legal states sharing the same three faces).

Easier scanning: single-face mode is back, and phones can be the camera.

- New "Scan mode" choice: *Corner view — 3 faces, 2 shots* or *One face
  at a time — 6 shots (easier)*. Single-face mode keeps every
  improvement (cube localisation, Lab self-calibration, centre checks)
  and shows the expected-centre badge above the grid.
- The Camera field now accepts a device number **or a stream URL**, so a
  phone can be the camera: Windows 11 "connected camera" (Android shows
  up as an extra number), IP-camera apps
  (`http://PHONE-IP:8080/video`), or Iriun/DroidCam/Camo virtual
  webcams. The tooltip explains each option.
- Colour-aware edge detection (union of per-channel Canny): dark blue
  and red stickers on dark backgrounds no longer vanish from the
  detector — found by the synthetic-render test, which now covers all
  six flat faces plus both corner views.
- Single-face sampling runs on the true (unmirrored) frame, mapping
  grids 1:1 onto facelets with no mirror bookkeeping.

Corner-view scanning: three faces at once, whole cube in two captures.

- The camera now reads the cube corner-on — top face plus both visible
  side panels (27 stickers per frame) — so a full scan is 2 views
  instead of 6 flat-on faces: white-top/green/red, then flip to
  yellow-top/orange/blue.
- The detector finds sticker-shaped quads (rhombi and leaning
  parallelograms), clusters them and fits the isometric hexagon; the
  guide wireframe with per-panel colour labels follows the cube.
- Detection and sampling run on the true (unmirrored) frame; only the
  display is mirrored, so captured faces need no mirror correction.
- New self-tests prove the view-to-facelet maps: permutation check, URF
  anchor check, and view 2 must equal view 1 of the cube reoriented by
  "y x2" (verified through the move engine).
- White vs yellow: unchanged Lab classifier, but centre calibration now
  happens three faces at a time, so by view 2 white/yellow and
  red/orange are matched against this cube's measured stickers.

Self-calibrating colours, inspired by cubed-core's calibration step
(ideas only — its AGPL code is not used).

- Sticker colours are now classified by nearest reference in Lab space
  (lightness down-weighted), replacing the fixed HSV hue bands.
- The scanner calibrates itself as you scan: each captured centre sticker
  is ground truth for its colour (the protocol fixes which centre each
  step shows), so later faces are matched against your cube's real
  stickers under your lighting — the classic red/orange confusion fades
  after the first few faces.
- References start from the nominal sticker colours and are blended, not
  replaced, so one bad frame cannot poison the calibration.

The camera now finds the cube instead of hoping it is in the middle.

- Cube localisation: sticker-sized squares are detected with a contour scan,
  clustered into a face, and the 3x3 grid is sampled from the detected face
  only — the overlay follows the cube around the frame.
- While no cube is visible the grid reads "unknown" and can never stabilise,
  so auto-capture no longer locks onto walls or faces.
- Auto-capture checks the centre sticker against the face being scanned
  (F=green, R=red, B=blue, L=orange, U=white, D=yellow) and tells you which
  colour it sees when it refuses; manual Capture can still force it.
- Manual capture is refused while no cube is detected.
- Slightly wider white and orange bands in the HSV classifier.

First release.

- Three-frame layout: camera scan (left), cube view (middle), tree of
  possibilities (right).
- Camera face recognition: 3x3 HSV colour detection, guided 6-face scan
  protocol, stability-based auto-capture, mirrored preview.
- Cube view: isometric U/F/R view plus full unfolded net, with the turning
  face highlighted during playback.
- Pure-Python cube model with full move engine (face turns, slices, wide
  moves, rotations), scramble generator and headless self-test
  (`python -m rubikpi.selftest`).
- Solving modes: Beginner (layer by layer), CFOP (Cross/F2L/OLL/PLL) and
  Speed (Kociemba two-phase), via optional `rubik-solver` / `kociemba`
  backends; every solution is verified on the internal model and split into
  human stages.
- Tree of possibilities: all 18 legal moves from the current state, scored
  by distance from solved, lazily expandable to 3 plies; solution stages
  with double-click-to-jump playback.
- Demo scramble mode so the whole app works without a camera.
