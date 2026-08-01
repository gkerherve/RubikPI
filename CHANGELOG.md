# Changelog

All notable changes to RubikPI.

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
