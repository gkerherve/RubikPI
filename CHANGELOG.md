# Changelog

All notable changes to RubikPI.

## 0.15.0 — 2026-08-01

Move detection rebuilt around what a camera actually delivers.

Measured on simulated frame streams, detection went from **0% to 99%**
once two stickers are misread — which a webcam does constantly.

- **Frames are steadied before matching.** Each cell takes the colour it
  is read as most often over the last five frames, so a sticker
  flickering between red and orange settles instead of poisoning every
  comparison.
- **Decisions are made on the margin over rival explanations**, not on a
  reading being near-perfect. The old rule allowed at most one wrong
  sticker out of nine; at two it detected nothing at all, silently.
- **Weak evidence is allowed to take longer.** A turn sometimes alters
  only one sticker the camera can see, so instead of discarding those,
  they simply need more agreeing frames.
- **Turning the watched face now needs proof something moved.** That turn
  is genuinely indistinguishable from rolling the cube in your hands, so
  the app leans on the move it asked for — but only if the face has
  actually changed since it was last at rest. Without that check, noise
  alone produced phantom moves in 17% of idle runs; now none at
  realistic noise.
- **"I have lost track"** — if nothing explains the picture for a couple
  of seconds, it says so and suggests a rescan instead of staying quiet.

Detection rate with 15% of stickers misread and 10% hidden: 98%, with no
false detections. All 15 visible moves, including turns of the watched
face.

## 0.14.0 — 2026-08-01

A solve clock, and fingers no longer read as white stickers.

- **Solve timer** in the middle panel: starts on your first move, stops
  the moment the cube is solved, with "move 7 of 20" beside it.
- **Fingers are recognised as fingers.** Lit skin sits within ~17 of
  white in Lab — closer than any two sticker colours are to each other —
  so a finger over a sticker was confidently read as white. Skin of
  every tone is *warm and washed out* (chroma 12-25) while white stays
  neutral (0-2 even in shade) and red and orange keep chroma above 41
  even at half light; that gap is now used to mark such samples unknown.
  Green, blue and yellow are not warm at all, so they are never at risk
  however dim they get, and the white edge follows your calibrated white
  so a tungsten-tinted cube still reads correctly.
- **Unknown stickers are left out rather than counted wrong.** The
  tracker scores only what it can read, needs at least 6 of the 9, and
  will not credit a move whose evidence is under your fingers — it says
  so instead of assuming. A finger alone can never be read as a move.
- Hidden stickers appear as grey hatching in the "Camera sees" panel,
  captioned "(2 hidden)", so it is obvious what the camera cannot see.
- Fixed: any frame containing an unreadable sticker was being discarded
  outright, which would have thrown away most real frames now that
  fingers are detected.

## 0.13.0 — 2026-08-01

Fixes follow-along never firing, and turns the panel into a confirmation.

- **Detection no longer needs a perfectly steady reading.** It waited for
  the nine stickers to come back *pixel-identical six frames running*;
  with a real webcam a single borderline sticker flickering means that
  never happens, so nothing was ever detected and nothing said why. The
  vote is now taken on the *interpretation* — three frames agreeing on
  the same move — which shrugs off a wobbling sticker.
- **The "Camera sees" panel shows the live reading** while following, not
  the app's belief, with a green border and "✔ matches the plan" when the
  two agree and a red "✗ not what I expect yet" when they do not. That is
  the confirmation that you turned the right face, and it evolves as you
  solve.
- **It says what is wrong instead of going quiet**: no cube in view, a
  centre colour that matches no side of your cube, or an unclear change
  all now produce a message (each said once, not every frame).
- The cube and the unfolded net update as soon as a move is recognised,
  which is what was missing while detection never fired.

## 0.12.0 — 2026-08-01

The move you have to make demonstrates itself, over and over.

- **The next move now plays on a loop** on the 3D cube: the layer turns,
  holds, snaps back and turns again, for as long as that move is
  outstanding. No need to know what "D2" or "R'" means — you can copy it
  off the screen. Labelled "Do this: D2" above the cube.
- Nothing is committed by the loop; it demonstrates on the cube's real
  current state, so it re-bases itself automatically when you step
  forward, step back or make the move in front of the camera.
- A real turn takes priority: when you (or Step) actually make the move
  it animates once at full speed, then the loop picks up the next move.
- Play suspends the loop — there the moves animate for real, one after
  another — and pressing Pause hands it straight back.
- The loop runs at half frame rate (30fps) since it never stops, while
  real turns stay at 60fps; a turn takes the same ~430ms either way.

## 0.11.0 — 2026-08-01

See the side the camera is on, and change it whenever you like.

- New **"Camera sees" panel** beside the 3D cube, showing that face flat
  and full size — on the isometric view it is round the back, but it is
  the one in front of *you* while you play. It updates with every move.
- The same face is now outlined in **cyan on the unfolded net**, so it is
  easy to place among the six.
- The panel follows a **colour**, not a face name, so whole-cube
  rotations inside a solution can never make it drift onto another side.
- The "Camera sees" setting can be changed **at any time, mid-solve
  included** — it re-draws the panel, re-words the instructions
  ("on your right" swaps sides) and leaves your progress untouched.
  While Follow me is running the camera sets it from the centre sticker
  by itself.

## 0.10.0 — 2026-08-01

One face, everywhere.  Corner (3-face) detection is gone.

- Scanning and follow-along both watch **a single face**, which is far
  easier to hold steady than a corner. The scan-mode choice is gone —
  there is one way to do it now, six flat-on shots.
- **Follow-along works from one face**, and gets more out of it than you
  might expect:
  - the centre sticker names the face, so the app knows which side the
    camera is on by itself and keeps "on your right" honest;
  - turning any of the four neighbouring faces swaps one row or column,
    which identifies the face *and* the direction;
  - turning the watched face rotates all nine stickers — indistinguishable
    from turning the whole cube in your hands, so the move the app just
    asked for breaks the tie;
  - turning the face pointing away from the camera changes nothing it can
    see, so it says "that face is facing away — turn the cube to show it,
    or press the right arrow" instead of pretending to know.
- Removed the corner-view machinery: `SCAN_VIEWS`, `VIEW_MAPS`, the
  hexagon fitting and the 27-sticker sampler.
- Self-tests rewritten for single-face tracking: face identification from
  the centre, all 12 neighbouring turns from every rotation, the
  watched-face tie-break, and the hidden-face case.

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

## 0.8.0 — 2026-08-01

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

## 0.7.0 — 2026-08-01

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

## 0.6.0 — 2026-08-01

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

## 0.5.0 — 2026-08-01

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

## 0.4.0 — 2026-08-01

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

## 0.3.0 — 2026-08-01

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

## 0.2.0 — 2026-08-01

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

## 0.1.0 — 2026-08-01

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
