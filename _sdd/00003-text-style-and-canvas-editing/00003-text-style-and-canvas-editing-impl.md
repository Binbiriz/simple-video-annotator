# Implementation: text-style-and-canvas-editing

Plan:
`_sdd/00003-text-style-and-canvas-editing/00003-text-style-and-canvas-editing-plan.md`

## Task List

- [x] Add `src/vidnote/colors.py` (`normalize_hex`, `TEXT_COLORS`, default list,
      `parse_color_list`, `dump_color_list`)
- [x] Update `src/vidnote/models.py` (size/colour constants, new `Annotation`
      fields, `validate()` rules)
- [x] Rework `src/vidnote/textfit.py` (remove auto-fit, add `layout_text`,
      `LayoutResult`, `scaled_size`)
- [x] Update `src/vidnote/exporter.py` (new header, `to_line`, `parse_line`)
- [x] Update `scripts/annotate.sh` (new fields and validation, `layout_text`,
      colours, warning, `VIDNOTE_PRINT_LAYOUT` hook, header comment)
- [x] Add `tests/test_colors.py` and update `tests/test_models.py`,
      `tests/test_textfit.py`, `tests/test_exporter.py`,
      `tests/test_annotate_sh.py`; run `pytest` and `ruff check src tests`
- [x] Update `src/vidnote/video_view.py` (new signals, indexed overlays, styled
      text preview, select mode with move/resize/handles, selection API, hide
      toggle)
- [x] Add `src/vidnote/colors_dialog.py`
- [x] Update `src/vidnote/main_window.py` (form widgets, colour list +
      `QSettings`, Edit menu, toolbar, new columns, `_fill_form`, geometry-edit
      handling with size scaling, warnings)
- [x] Update `README.md`, `examples/annotations.txt` and `AGENTS.md`
- [ ] Run through the `## Verification` section

## Implementation Summary

- `src/vidnote/colors.py` (new): `normalize_hex`, `TEXT_COLORS`,
  `DEFAULT_COLOR_LIST`, `parse_color_list`, `dump_color_list`,
  `default_color_list_text`.
- `src/vidnote/models.py`: size/colour constants;
  `Annotation.size/box_color/text_color`; `validate()` rules for text.
- `src/vidnote/textfit.py`: removed `fit_text`; added `LayoutResult`,
  `layout_text`, `scaled_size`. `MIN_SIZE`/`MAX_SIZE` now come from `models`.
- `src/vidnote/exporter.py`: new header, `to_line`/`parse_line` for
  `text|start|end|x|y|w|h|size|boxcolor|textcolor|text`; old shapes rejected
  with "no longer supported".
- `scripts/annotate.sh`: new fields and validation, `layout_text`, colours as
  `0xrrggbb`, "does not fit ... at Npx, drawing it anyway" warning,
  `VIDNOTE_PRINT_LAYOUT` hook, header comment.
- `src/vidnote/video_view.py`: rewritten with draw/select modes, indexed
  overlays with styled text preview, handles (move/resize, clamped, min 10x10),
  click cycling for overlaps, `annotationPicked`/`geometryEdited` signals,
  `set_selected`, `set_overlays_visible`.
- `src/vidnote/colors_dialog.py` (new): `ColorListDialog`.
- `src/vidnote/main_window.py`: Font size / Box colour / Text colour form
  widgets, colour list in `QSettings` (`boxColors`) with Edit > Text box
  colours..., toolbar Select and Hide preview toggles, new table columns,
  `_fill_form`, `_on_geometry_edited` with font scaling, unfit/equal-colour
  warnings, "(not in list)" combo entry.
- Tests: new `tests/test_colors.py`; updated `test_models.py`,
  `test_textfit.py`, `test_exporter.py`, `test_annotate_sh.py` (including
  `test_layout_matches_python`).
- `README.md`, `examples/annotations.txt`, `AGENTS.md` updated to the new format
  and features.

## Verification Results

- **Verification incomplete:** steps 3, 4 (app restart part), 6 and 7 need an
  interactive GUI session and a real playing video, which was not available;
  they were only exercised programmatically (see below). Step 1 `ruff check`
  still exits non-zero (see below).
- Step 1: `pytest` passes (125 passed; `annotate.sh` tests ran, ffmpeg with
  drawtext is installed). `ruff check src tests` fails: 70 findings, all `UP0xx`
  (`typing.List`/`Optional`), `PLW1510` and `FLY002` style rules. The baseline
  before this change already had 34 of the same kinds (the code base uses
  `List`/`Optional`/`subprocess.run` without `check`); the new code follows the
  same style. No other rule categories are reported.
- Step 2: `annotate.sh` rendered `examples/annotations.txt` on a generated
  640x480 video; frames show correct sizes and box/text colours (white on black,
  black on yellow, blur). A 40x20 box with long text printed
  `warning: ...c.txt:1: text does not fit in 40x20 at 14px, drawing it anyway`
  and still rendered. The old line `text|0|1|2|3|50|20|hi` failed with
  `d.txt:1: ... (older text formats are no longer supported)`, exit 1.
- Step 3: not run in a real window. Offscreen: the form picks up size/box/text
  colours from a selected row; `_form_annotation` carries them into the
  annotation.
- Step 4: offscreen with real `QSettings`: list with an invalid line was loaded
  with the line skipped and reported in the status bar; an annotation with a
  colour not in the list showed `#ffd400 (not in list)`; a saved list was read
  back by a second `MainWindow`. The dialog was not opened and the
  render-keeps-colour check was covered by step 2 (hex stored in the file).
- Step 5: save/load round trip is covered by `tests/test_exporter.py` (header,
  `#rrggbb` normalisation, identical values after reload).
- Step 6: offscreen `VideoView` driven with `QTest` mouse events: topmost pick,
  click cycling through overlapping boxes, move, handle resize, clamping to the
  frame (move to 0,0; resize clamped to the frame), 10x10 minimum, drag
  cancelled by a mode switch with no change, selection surviving a mode switch,
  draw mode still emitting `regionSelected`. Font scaling on resize checked
  through `_on_geometry_edited` (a 2x box doubled 20 -> 40; a tiny box clamped
  to 8 with a status message). Selecting a not-active annotation from the list
  was not tried on a real video.
- Step 7: offscreen: with Hide preview on, overlay items, highlight and handles
  are hidden, select-mode clicks do nothing, annotations are unchanged;
  selecting a list row turns it off and shows the highlight again.
- Step 8: Turkish text and `|` round trip in `test_exporter.py` and
  `test_annotate_sh.py` (layout comparison with Turkish text); CRLF and padded
  fields are covered in `test_annotate_sh.py`; blur tests unchanged and passing.

## Deviations

- The last task ("Run through the `## Verification` section") is left unchecked:
  the interactive GUI steps (3, 6, 7 on a real video, the colour dialog in
  step 4) were not run, and `ruff check` fails on pre-existing style rule
  categories.
- The two new table columns are named `Size`, `Box` and `Color` (header tooltips
  explain them) instead of `Size`, `Box`, `Text`, because `Text` is already the
  annotation text column.
- In `video_view.py` a separate `_rubber` highlight item is used for the
  draw-mode rubber band and click marker, so the selected annotation's highlight
  (`_selection`) is not lost when the user draws in draw mode. A click on the
  body of the current selection that does not move cycles through overlapping
  annotations; a click on an unselected box selects it and can drag straight
  away.
- Packages for the dev tools were installed into the existing `.venv`
  (`pip install -e ".[dev]"`) because `pytest` was missing there.
- Sample videos/annotation files were written under `/tmp/opencode` for
  verification (`sample.mp4`, `out.mp4`, `a.txt`..`d.txt`), which overwrote
  same-named files that were already there.
