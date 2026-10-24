# Implementation: arrow-component

Plan: `_sdd/00004-arrow-component/00004-arrow-component-plan.md`

## Task List

- [x] Create `src/vidnote/arrowgeom.py` (geometry, polygons, coverage, distance,
      padding)
- [x] Update `src/vidnote/models.py` (arrow constants, new `Annotation` fields,
      `validate()`)
- [x] Update `src/vidnote/exporter.py` (docstring, `HEADER`, `to_line`,
      `parse_line`, unknown-type message)
- [x] Update `scripts/annotate.sh` (header, arrow parsing and validation,
      file-order stages, frame check, geq PNG rendering, extra inputs,
      `shortest=1`)
- [x] Update `src/vidnote/video_view.py` (line drawing, arrow preview, hit
      testing, arrow selection/handles/editing, new signals)
- [x] Update `src/vidnote/main_window.py` (Arrow type, form fields, table row,
      in-frame check, live style preview, canvas signals, load warning text)
- [x] Add `tests/test_arrowgeom.py` and extend `tests/test_models.py`,
      `tests/test_exporter.py`, `tests/test_annotate_sh.py`
- [x] Update `examples/annotations.txt`, `README.md` and `AGENTS.md`
- [x] Run `pytest` and `ruff check src tests`
- [ ] Run through the `## Verification` steps (GUI and `annotate.sh`)

## Implementation Summary

- `src/vidnote/arrowgeom.py` (new, no Qt): `geometry`, `polygons`, `coverage`
  (anti-aliased, same formulas as the `geq` alpha), `distance_to_segment`,
  `padding`.
- `src/vidnote/models.py`: `ARROW`, style/thickness/colour constants and the new
  `Annotation` fields (`x2`, `y2`, `thickness`, `color`, `start_style`,
  `end_style`); `validate()` checks them via `_validate_arrow()`.
- `src/vidnote/exporter.py`: `arrow|...` line in the docstring, `HEADER`,
  `to_line` and `parse_line` (11 fields, integer points/thickness, points must
  differ, thickness 1-30, normalised colour, lowercase `none`/`arrow` styles);
  the unknown-type message lists `arrow|...`.
- `scripts/annotate.sh`: `arrow` parsing/validation with `file:line` errors;
  every stage (blur, text, arrow) is now chained in file order (text lines emit
  their own stage; the final `[$cur]$texts[vout]` step is gone); arrow end
  points are frame-checked (`arrow end point outside the WxH video`); each arrow
  is drawn into a PNG by ffmpeg (`geq` alpha, ffmpeg-only) and applied with
  `overlay=...:enable='between(t,s,e)':shortest=1` via extra `-loop 1 -i` inputs.
- `src/vidnote/video_view.py`: arrow tool (`set_draw_line`, rubber line,
  `lineSelected`), styled arrow preview (`QPainterPath` union of the shared
  polygons, 50% alpha, hidden with the other previews), arrow hit testing
  (`max(t/2, 8 screen px)`, cycling like boxes), arrow selection with `p1`/`p2`
  handles, moving the whole arrow and `arrowEdited`; both end points stay in the
  frame and never coincide.
- `src/vidnote/main_window.py`: Type combo gains `Arrow`; End point, Thickness,
  Start/End style fields; colour combo relabelled "Colour"; table row (start
  point, colour swatch, `to (x2,y2), N px, none>arrow`); in-frame check; live
  preview of thickness/colour/styles for the selected arrow; canvas signals;
  load warning text; menu entry "Box and arrow colours...".
- `src/vidnote/colors_dialog.py`: window title "Box and arrow colours" (small
  extra, consistent with the menu entry).
- Tests: new `tests/test_arrowgeom.py`; arrow cases added to `test_models.py`,
  `test_exporter.py` and `test_annotate_sh.py` (duration with `shortest=1`,
  time range and pixel comparison against `arrowgeom.coverage` for horizontal,
  vertical, diagonal, reversed, both-ends, very short and plain-bar arrows,
  colour, frame-edge checks, malformed lines, blur-after-text graph).
- `examples/annotations.txt`, `README.md`, `AGENTS.md` describe the arrow line,
  the overlay approach and the new module.

## Verification Results

1. `pytest`: **pass**, 195 passed (ffmpeg and drawtext available).
   `ruff check src tests` with the installed ruff 0.17.2 reports 95 findings,
   all `UP006/UP035/UP045/PLW1510/FLY002` style rules that the existing code
   already violates (70 on the unmodified tree; the extra ones are new code using
   the same `List`/`Optional` style as its surroundings). Restricted to
   `E,F,I,W` there are 5 `E501` findings, the same 5 as before the change.
2. - 6. (GUI, interactive): **not run by hand** (no interactive display here).
   Scripted offscreen equivalents with `QT_QPA_PLATFORM=offscreen`:
   - Adding an arrow through the form gives the expected row
     (`arrow | 0 | 5 | 100 | 100 | ... | to (300,200), 4 px, none>arrow`), Update
     selected keeps thickness/style changes, `_on_arrow_edited` updates the row
     and form, switching the form kind works.
   - With `QTest` mouse events on `VideoView`: a right-to-left drag in arrow mode
     emits `lineSelected(300, 200, 100, 100)` (start stays where the drag began);
     the hit test finds the arrow on the line and not 50 px away; dragging the end
     handle emits `arrowEdited` with the new end point; dragging the line far
     right moves the whole arrow and clamps it to the frame (`440,100 -> 640,200`).
   - The preview was compared with `arrowgeom.coverage` by rendering the scene to
     an image for three arrows (diagonal, both ends, very short and thick): after
     a fix (see Deviations) no pixel differs by more than 40/255.
   Not checked: Hide preview toggle, save/reload through the file dialogs and
   the skipped-lines dialog in the real window (the file round trip and the
   skipped-line reasons are covered by `test_exporter.py`).
7. `annotate.sh`: **pass**. `examples/annotations.txt` renders on a 1280x720
   video (the file's text boxes need that size); output length equals input
   length (16 s) and audio is kept; frames at 4 s and 12 s show the red 4 px
   arrow and the white 8 px double-headed arrow with 50% opacity only in their
   ranges, and file-order stacking with text and blur. A frame-edge case (arrow
   from corner to corner, 10 px thick short arrow, arrow ending at the frame
   corner) renders without error.
8. Bad lines: **pass**. Identical points, thickness 0 and 31, bad colour, unknown
   style, wrong field count and an end point outside the video all exit non-zero
   with `file:line` messages (also covered by `test_annotate_sh.py`).

## Deviations

- Unchecked: "Run through the `## Verification` steps (GUI and `annotate.sh`)":
  the `annotate.sh` steps (7, 8) were done, the interactive GUI steps (2-6) were
  only exercised with the scripted offscreen checks listed above, not by hand.
- Overlay origin is rounded to even coordinates in `annotate.sh`: ffmpeg's
  `overlay` rounds the position down to even values on yuv420p video, which
  shifted the arrow by 1 px for odd positions (found by the pixel comparison
  test). The script now rounds `ox`/`oy` itself and draws the image relative to
  them (the `arrows` entries carry `ox`/`oy`). `AGENTS.md` notes this. The
  existing blur stage has the same odd-offset rounding; not changed (out of scope).
- Preview union: the plan said `QPainterPath.addPolygon` + `.simplified()`. With
  the default odd-even fill rule that cancelled the shaft/head overlap and left a
  dim seam, so `video_view.py` unions one path per polygon with `united()` instead.
- `colors_dialog.py` title changed to "Box and arrow colours" (not in the plan).
- New arrows get the first colour in the list (Black by default) rather than the
  default red, because the shared colour combo is used as the plan describes;
  `DEFAULT_ARROW_COLOR` is only the fallback.
