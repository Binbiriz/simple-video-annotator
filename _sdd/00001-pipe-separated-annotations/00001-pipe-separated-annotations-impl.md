# Implementation: pipe-separated-annotations

Plan:
`_sdd/00001-pipe-separated-annotations/00001-pipe-separated-annotations-plan.md`

## Task List

- [x] Update `src/vidnote/exporter.py`: docstring, `HEADER`, `to_line`,
      `parse_line`
- [x] Update `scripts/annotate.sh`: header comment, `|` parsing with helpers,
      validation, line-numbered errors, CRLF handling
- [x] Update the skipped-lines warning text in `src/vidnote/main_window.py`
- [x] Convert `examples/annotations.txt` to the new format
- [x] Update `README.md` (format section, example, rendering section)
- [x] Update and extend `tests/test_exporter.py`
- [x] Update and extend `tests/test_annotate_sh.py`
- [ ] Run `ruff check src tests` and `pytest`
- [ ] Run through the manual `## Verification` steps

## Implementation Summary

- `src/vidnote/exporter.py`: docstring and `HEADER` describe the `|` format;
  `to_line` joins with `|`; `parse_line` splits on `|` (blur: exactly 7 fields,
  text: text is everything after the fifth `|`, rejected if empty), and any
  other keyword (all old-format lines) raises a "no longer supported"
  `ValueError`.
- `scripts/annotate.sh`: new header comment; added `trim`, `die` and `pop_field`
  helpers; loop tracks `lineno`, strips `\r`, tolerates a final line without a
  newline, validates the field count and numbers (integers for x/y/w/h) before
  ffmpeg runs, and exits 1 with `file:line: reason: line` on malformed input.
  Filter-graph construction and the temp-file/`expansion=none` text handling are
  unchanged.
- `src/vidnote/main_window.py`: load warning text now states the expected `|`
  formats.
- `examples/annotations.txt` and `README.md`: converted to the new format
  (format section, example, rendering section).
- `tests/test_exporter.py`: round-trip with `|` in text, pipe-format
  header/lines, whitespace and CRLF tolerance, remainder-after-fifth-pipe,
  malformed-line cases, saved lines always pipe-separated.
- `tests/test_annotate_sh.py`: render helper; new-format render test, padded
  fields + `|` in text + CRLF render test, parametrized malformed-line tests
  that check the `ann.txt:3:` line number and non-zero exit.

## Verification Results

- Step 1 (`pytest`): pass, 24 passed, none skipped (ffmpeg and drawtext
  present). **`ruff check src tests`: not run**, `ruff` is not installed here
  and `pip install ruff` hung (no network). Four pre-existing lines in
  `main_window.py` (81, 94, 276, 480) exceed 100 chars; none are in code touched
  by this change.
- Steps 2-3 (GUI save/load): not run in the GUI. Checked headlessly with
  `exporter.save`/`exporter.load` instead: the file has the `|` header and
  `text|1|5|20|20|a | b c` / `blur|2|6|100|100|200|100`, and loads back with
  identical annotations, no skipped lines.
- Step 4: pass, `annotate.sh` rendered the saved file (exit 0, output produced).
  The text/blur positions and timing were not inspected visually.
- Step 5: `examples/annotations.txt` loads via the exporter (3 annotations, none
  skipped) and renders with `annotate.sh` (exit 0). Not loaded in the GUI.
- Step 6: old-format file (`text 1 2 10 20 hi`, `1 2 3 4 hi`): `exporter.load`
  skips both lines with the "no longer supported" reason; `annotate.sh` exits 1
  with `old.txt:1: unrecognized line ...`. The GUI dialog itself was not viewed.
- Step 7: `text|1|2|(w-text_w)/2|20|hi` is skipped by `exporter.load` (int
  conversion error) and rejected by `annotate.sh` (exit 1,
  `expr.txt:1: x and y must be whole numbers`).
- Step 8: CRLF file with no trailing newline on the last line renders with
  `annotate.sh` (exit 0).

## Deviations

- Tasks "Run `ruff check src tests` and `pytest`" and "Run through the manual
  `## Verification` steps" are left unchecked: ruff could not be installed, and
  the GUI-based parts of steps 2, 3, 5 and 6 were replaced by headless
  exporter/script checks. Output was not inspected visually in step 4.
