# Implementation: stale-yellow-canvas-highlights

Plan:
`_sdd/00005-stale-yellow-canvas-highlights/00005-stale-yellow-canvas-highlights-plan.md`

## Task List

- [x] Create `src/vidnote/canvasstate.py` (`MarkerState`, `FormGeometry`,
      `selection_geometry`, `selection_dimmed`, constants)
- [x] Create `tests/test_canvasstate.py` and run
      `pytest tests/test_canvasstate.py`
- [x] `video_view.py`: full viewport update mode, `dragStarted` signal,
      `set_marker`, release no longer draws the final marker, refresh selection
      after cancel/release, Escape cancels a drag
- [x] `video_view.py`: `set_selected` stops hiding the marker; dimmed/dashed
      selection style with `set_selection_dim`
- [x] `main_window.py`: marker state, timer and helpers (`_form_geometry`,
      `_show_marker`, `_clear_marker`, `_on_marker_timeout`)
- [x] `main_window.py`: selection helpers (`_sync_selection_highlight`,
      `_sync_selection_dim`) and rewire `_select_in_view` /
      `_sync_view_selection`
- [x] `main_window.py`: wire signals (`dragStarted`, coordinate spins, mode
      toggle) and update `_on_region`, `_on_line`, `_on_kind_changed`,
      `_on_row_selected`, `_update_overlays`
- [x] `main_window.py`: clear state in `_refresh_table`, `open_video`,
      `delete_annotation` (refill form), `load_annotations`
- [x] Update `README.md` and `AGENTS.md`
- [x] Run `pytest` and `ruff check src tests`
- [ ] Run through the `## Verification` steps

## Implementation Summary

- `src/vidnote/canvasstate.py` (new, no Qt): `MarkerState` (pick / clear /
  expire_point / shape), `FormGeometry`, `selection_geometry`,
  `selection_dimmed`, constants for the click marker size and lifetime.
- `tests/test_canvasstate.py` (new): 25 tests for the rules above.
- `src/vidnote/video_view.py`: `FullViewportUpdate`; `dragStarted` signal;
  `set_marker(shape)`; draw release hides the marker and only emits the signals;
  `_cancel_drag` and release refresh the selection items; Escape cancels a drag
  (draw drag or select-mode edit); `set_selected` no longer touches the marker;
  dimmed/dashed selection style (prebuilt pens/brushes, faded handles) via
  `set_selection_dim`.
- `src/vidnote/main_window.py`: `MarkerState` plus a 1 s single-shot timer for
  the click marker; helpers `_form_geometry`, `_show_marker`, `_clear_marker`,
  `_on_marker_timeout`, `_sync_selection_highlight`, `_sync_selection_dim`,
  `_on_geometry_field_changed`, `_on_mode_toggled`; `_on_region` / `_on_line`
  pick the marker from the form; the marker is cleared on drag start, kind
  change, mode toggle, `_refresh_table`, row selection, `open_video`; the list
  selection is cleared on open video and load; `delete_annotation` refills the
  form from the neighbour; `_update_overlays` refreshes the dim state; clearing
  the list selection clears the view highlight.
- `README.md` / `AGENTS.md`: usage notes and the new Qt-free module.

## Verification Results

- `pytest`: pass, 220 passed (existing tests unchanged, plus 25 new).
- `ruff check src tests`: reports 104 findings, but ruff 0.17.2 (no rule
  selection in `pyproject.toml`) already reported 95 on the untouched tree
  (mostly `UP006`/`UP035` for `typing.List`/`Tuple`, which the whole codebase
  uses). The new ones are the same `Tuple` style in `canvasstate.py` and
  `video_view.py`. `ruff check --select E,F,W,I` shows only 5 existing E501
  lines, none in code from this change.
- Manual steps, checked headlessly with a script under
  `QT_QPA_PLATFORM=offscreen` (window built, view sized 640x360, slots driven
  directly and mouse events sent with QTest):
  - Step 1 pass: region and line markers match the form and follow X/W/X2
    changes.
  - Step 2 pass for the click marker: it disappears after about 1 s. The "region
    drawn within a second of a click" case is only covered by the `MarkerState`
    unit test.
  - Step 3 partly checked: kind change, row selection, `_refresh_table`
    (add/update/delete/load) clear the marker. Open video, toggling Select and
    picking on the canvas were not exercised separately.
  - Step 4 pass: Escape during a draw drag leaves no rubber band and the
    selection highlight is back; a normal drag release shows the marker from the
    form.
  - Step 5 partly checked: a row not active at the playhead is shown dimmed;
    play/seek through the range and editing start/end were not run (no real
    playback).
  - Step 6 pass: the highlight follows W; a click marker keeps the stored
    geometry; with a kind mismatch the highlight keeps the stored geometry.
  - Step 7 pass: deleting (box then arrow neighbour, last row), reloading and
    clearing the list selection leave no highlight or handle.
  - Step 10 partly checked: `_refresh_table` / `clearSelection` leave a clean
    canvas; a second real video was not opened.
  - Not run (need a display and real playback): step 8 (Hide preview), step 9
    (pixel trails while playing / resizing) and step 11 (rendered output; the
    format, `exporter.py` and `scripts/annotate.sh` are unchanged and the
    existing annotate.sh test passes).

## Deviations

- The task "Run through the `## Verification` steps" is left unchecked: only the
  headless subset above was run; steps 8, 9, 11 and the playback parts of steps
  3, 5 and 10 still need a manual run with `./run.sh some.mp4`.
- Escape also cancels a select-mode edit in progress (restoring the original
  geometry), not just a draw drag; the plan only mentioned draw drags.
