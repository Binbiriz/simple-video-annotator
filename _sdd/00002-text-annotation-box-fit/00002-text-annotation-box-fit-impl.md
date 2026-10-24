# Implementation: text-annotation-box-fit

Plan: `_sdd/00002-text-annotation-box-fit/00002-text-annotation-box-fit-plan.md`

## Task List

- [x] Update `src/vidnote/models.py`: text requires `w`/`h` > 0, comments
- [x] Add `src/vidnote/textfit.py`: constants, `wrap`, `fit_text`,
      `resolve_font`
- [x] Update `src/vidnote/exporter.py`: docstring, `HEADER`, `to_line`,
      `parse_line` text branch
- [x] Update `scripts/annotate.sh`: font selection, UTF-8 locale, `fit_text`
      function, new text parsing/validation, `drawbox` + `drawtext` filters,
      does-not-fit warning, frame check, `VIDNOTE_PRINT_FIT` hook, header
      comment
- [x] Update `src/vidnote/video_view.py`: fitted text preview (box background,
      per-line items, overflow outline)
- [x] Update `src/vidnote/main_window.py`: enable W/H for text, form values,
      in-frame check, fit status message, hint text, load warning text, missing
      font dialog
- [x] Update `examples/annotations.txt`
- [x] Update `README.md`
- [x] Update `tests/test_models.py`
- [x] Add `tests/test_textfit.py`
- [x] Update `tests/test_exporter.py`
- [x] Update `tests/test_annotate_sh.py` (new shape, does-not-fit, beyond-frame,
      old-format rejection, Python/bash fit parity)
- [ ] Run `ruff check src tests` and `pytest`
- [ ] Run through the manual `## Verification` steps

## Implementation Summary

- `src/vidnote/models.py`: `w`/`h` comments updated; `validate()` requires
  `w`/`h` > 0 for text.
- `src/vidnote/textfit.py` (new, no Qt): constants (14/8 px, pad 4, line height
  1.15, advance 0.605), `wrap`, `fit_text`, `line_height`, cached
  `resolve_font()` (via `fc-match`).
- `src/vidnote/exporter.py`: new header and `text|start|end|x|y|w|h|text`
  read/write; old text lines rejected with a "no longer supported" reason;
  `w`/`h` must be > 0.
- `scripts/annotate.sh`: UTF-8 locale, Ubuntu Mono with monospace fallback +
  warning, bash port of the fit algorithm, new text parsing/validation
  (octal-safe via `toint`), one `drawbox` plus one `drawtext` per wrapped line,
  does-not-fit warning, `ffprobe` frame check, `VIDNOTE_PRINT_FIT=1` test hook,
  `FONTSIZE` removed.
- `src/vidnote/video_view.py`: preview draws the box background, one text item
  per fitted line in the monospace font, and a red dashed outline when the text
  does not fit.
- `src/vidnote/main_window.py`: W/H enabled for text and always saved, in-frame
  check on add/update, status bar message when text does not fit, new hint and
  load-warning texts, one-time dialog when Ubuntu Mono is missing.
- `examples/annotations.txt`, `README.md`: new format and behaviour documented.
- Tests: `test_models.py` and `test_exporter.py` updated; new `test_textfit.py`;
  `test_annotate_sh.py` updated with does-not-fit, beyond-frame, old-format
  rejection and a bash/Python fit parity test.

## Verification Results

- `pytest`: **87 passed** (includes the bash vs Python fit parity test and
  ffmpeg renders).
- `ruff check src tests`: ruff is not in the project venv, so I installed it
  there. In this environment it enables extra rule sets (UP, PLW, FLY) and
  reports 34 findings; the same categories are reported on the untouched code
  (33). With `--select E,F,W,I` the only findings are 4 E501 lines in
  `main_window.py` that I did not touch. No new E/F/W/I issues.
- Steps 2-4 (GUI, preview/render parity), run headless with
  `QT_QPA_PLATFORM=offscreen`: `MainWindow` add/update flows work (W/H enabled
  for text; `w=0` rejected with a message; a box past the frame rejected). I
  rendered the scene preview and the ffmpeg output for the same annotations and
  compared them side by side: same font size, same line breaks, same pitch; the
  unfittable box gets the red outline in the preview and a warning in the
  renderer. Interactive mouse dragging and the Ctrl+S/Ctrl+L/Ctrl+R dialogs were
  not exercised.
- Step 5: `examples/annotations.txt` renders on a 1280x720 video (exit 0); on a
  640x240 video the renderer correctly rejects the third text box as beyond the
  frame.
- Step 6: Turkish text and text containing `|` wrap correctly and render without
  mojibake.
- Step 7: old-format lines (`text|0|1|2|3|hi`, `text 1 2 10 20 hi`) are listed
  as skipped by `exporter.load` and rejected by `annotate.sh` with a
  `file:line:` message and exit 1.
- Step 8: `w=0`, negative `h` and boxes past the frame are rejected in app and
  renderer.
- Step 9: with a stub `fc-match` that has no Ubuntu Mono, the script prints the
  fallback warning and still renders; the app's missing-font dialog was not
  shown interactively.
- Step 10: blur lines still parse, save and render unchanged (tests, plus the
  render above).
- The task "Run through the manual `## Verification` steps" is left unchecked
  because the interactive parts of steps 2-4 and 9 were not run on a real
  display.
- The task "Run `ruff check src tests`" is left unchecked because the command
  does not exit cleanly here, though only for rule sets/lines that were already
  failing before this change.

## Deviations

- **Glyph advance is 0.605 for every font, not 0.5 for Ubuntu Mono.** The
  installed Ubuntu Mono (variable font) has an advance of 0.56, not 0.5, so the
  planned value made text overflow the box. Instead of per-font detection (which
  would need font measurement), both implementations use one deliberately wide
  constant, so any monospace font fits. Consequently `FontInfo` has no `adv_pm`,
  there is no `fc-scan` branch for `FONT=`, and `UBUNTU_ADV_PM` was dropped.
- **One `drawtext` per wrapped line** instead of one `drawtext` with newlines
  and `line_spacing`. This gives an exact line pitch of `size * 1.15` that
  matches the preview and avoids relying on FreeType line metrics; no
  `line_spacing` tuning was needed.
- The `fontfile` value is single-quoted in the filtergraph because the installed
  Ubuntu Mono path contains `[wght]`, which would otherwise break the graph.
- Task "Run `ruff check src tests`" and "Run through the manual Verification
  steps" left unchecked, see Verification Results.
