# Plan: pipe-separated-annotations

## Context

Spec:
`_sdd/00001-pipe-separated-annotations/00001-pipe-separated-annotations-spec.md`

Today an annotation line is whitespace-separated (`text start end x y text...`,
`blur start end x y w h`). Text lines may omit the `text` keyword (legacy), and
the shell renderer accepts ffmpeg expressions for text `x`/`y`. The format is
implemented twice and the two must stay in sync: `src/vidnote/exporter.py`
(Python, used by the GUI save/load) and `scripts/annotate.sh` (bash `read`).

After this change every line uses `|` as the separator:

- `text|start|end|x|y|text`
- `blur|start|end|x|y|w|h`

Per the spec and its answered Open Questions:

- Whitespace around the keyword and each field is ignored.
- The text field is everything after the fifth `|`, so it may contain `|`.
- No backward compatibility: old whitespace-separated lines (with or without the
  `text` keyword) are reported as malformed in both the app and the renderer.
- The app always saves in the new format (no format choice).
- `x`/`y`/`w`/`h` are always integers; ffmpeg expressions are no longer
  supported in the renderer. Non-numeric values are reported as malformed
  instead of being passed to ffmpeg.
- `#` comments, blank lines and CRLF line endings keep working.
- Empty/whitespace-only text is rejected.

Behaviour kept as-is: `to_line` still collapses runs of whitespace (including
newlines) in text to single spaces so each annotation stays on one line.

## Files to Modify

### 1. `src/vidnote/exporter.py`

- Update the module docstring to the new format and drop the "backward
  compatibility" sentence.
- `HEADER`:
  ```python
  HEADER = (
      "# vidnote annotations\n"
      "# text|start|end|x|y|text\n"
      "# blur|start|end|x|y|w|h\n"
  )
  ```
- `to_line`: join with `|`:
  ```python
  if a.kind == BLUR:
      return "|".join(["blur", fmt_time(a.start), fmt_time(a.end),
                       str(a.x), str(a.y), str(a.w), str(a.h)])
  text = " ".join(a.text.split())
  return "|".join(["text", fmt_time(a.start), fmt_time(a.end), str(a.x), str(a.y), text])
  ```
  `|` inside the text is written as-is (it is the last field, no escaping).
- `parse_line`: after the blank/comment check (`line.strip()` already removes
  `\r`), split on `|`:
  - `kind = line.split("|", 1)[0].strip()`.
  - `blur`: `parts = [p.strip() for p in line.split("|")]`; require
    `len(parts) == 7`, else
    `ValueError("blur lines need: blur|start|end|x|y|w|h")`; parse `float` for
    start/end and `int` for x/y/w/h.
  - `text`: `parts = line.split("|", 5)`; require `len(parts) == 6` else
    `ValueError("text lines need: text|start|end|x|y|text")`; strip fields 1-4
    for numeric parsing, `text = parts[5].strip()`; raise
    `ValueError("text is empty")` if empty.
  - Anything else (including all old-format lines, which have no `|` or a
    non-keyword first field):
    `ValueError("unknown line type; expected 'text|...' or 'blur|...' (old whitespace-separated lines are no longer supported)")`.
  - Keep the `except (ValueError, IndexError)` wrapper so int/float conversion
    errors are reported with a message.

### 2. `scripts/annotate.sh`

- Update the header comment to the new format; remove the "may omit the leading
  `text` keyword" note and the ffmpeg-expression note for `x`/`y`.
- Replace the `read`-based parsing with `|` parsing. Avoid relying on
  `IFS='|' read` for the last field (trailing-delimiter handling of the final
  variable is easy to get wrong); instead add small helpers:
  ```bash
  trim() { local v="$1"; v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"; printf '%s' "$v"; }
  die() { echo "$list:$lineno: $1: $raw" >&2; exit 1; }
  ```
  and pop fields off the front with `${rest%%|*}` / `${rest#*|}`.
- In the loop: keep a `lineno` counter, strip a trailing `\r`
  (`line="${line%$'\r'}"`), keep the blank/`#` skip, then take the first field
  as the keyword (trimmed):
  - `blur`: split into exactly 6 more fields (error if too few, or if anything
    remains after `h` — i.e. a 7th `|`); `s`/`e` must match
    `^[0-9]+(\.[0-9]+)?$`, `x y w h` must match `^-?[0-9]+$`; otherwise `die`.
    The existing filter-graph construction is unchanged.
  - `text`: split off 4 fields then the remainder is the text (trim it; `die` if
    empty); validate `s e x y` as above. Keep the temp-file/`expansion=none`
    approach unchanged, so `|` and other characters in text need no escaping.
  - any other keyword (old format):
    `die "unrecognized line (expected text|... or blur|...)"`.
- Malformed lines make the script exit non-zero with a message that includes the
  file name and line number, before ffmpeg runs.
- The loop must still tolerate a final line without a trailing newline
  (`while IFS= read -r line || [ -n "$line" ]`) — optional hardening, only if
  not already handled; keep the existing behaviour otherwise.

### 3. `src/vidnote/main_window.py`

- Load warning dialog text (around line 494): drop the "only numeric x/y are
  supported in the editor" wording, e.g.
  `"{n} line(s) could not be read (expected 'text|start|end|x|y|text' or 'blur|start|end|x|y|w|h'):\n\n{lines}"`.
- No other change: saving and loading go through `exporter.save` /
  `exporter.load`, and rendering writes a temp file via `exporter.save` before
  calling `annotate.sh`, so it picks up the new format automatically.

### 4. `examples/annotations.txt`

Convert to the new format:

```
# vidnote annotations
# text|start|end|x|y|text
# blur|start|end|x|y|w|h
text|2|6|50|50|Welcome to the tutorial
blur|3|8|100|200|300|120
text|10|14|80|400|Click the Save button
```

### 5. `README.md`

- Annotation-format section (lines ~39-51): describe the `|`-separated format,
  remove "Old lines without the leading `text` keyword are still read", state
  that the old whitespace-separated format is no longer supported, that the text
  may contain spaces and `|`, and update the example lines
  (`blur|52.24|54.68|170|220|448|176`, `text|53.96|60.96|170|220|deneme`).
- "Rendering without the GUI" (line ~59): remove the sentence about ffmpeg
  expressions for text `x`/`y` and say `x`/`y` are integer video pixels.

### 6. `tests/test_exporter.py`

- `test_roundtrip`: keep; add a text annotation containing `|` and spaces (e.g.
  `"a | b|c"`) and assert it round-trips with the same text.
- `test_comments_and_blank_lines_ignored`: change the data line to
  `"1|..."`-style new format, i.e. `"# c\n\n   \ntext|1|2|3|4|hi\n"`.
- Replace `test_text_keyword_and_legacy_lines` with `test_pipe_format_lines`:
  parse `text|53.96|60.96|170|220|deneme`, assert the `Annotation`, assert
  `to_line` returns the same string; also check whitespace tolerance
  (`" text | 1 | 2 | 10 | 20 | Hello "` → text `"Hello"`) and CRLF input
  (`"blur|1|2|3|4|5|6\r\n"`).
- Add a test that the text field is the remainder after the fifth `|`
  (`text|1|2|3|4|a|b|c` → text `"a|b|c"`).
- `test_malformed_lines_are_reported`: new inputs, all skipped with correct line
  numbers: old format `"1 2 3 4 hi"`, `"text 1 2 3 4 hi"`, `"blur 1 2 3 4 5 6"`,
  `"blur|1|2|3"`, `"blur|1|2|3|4|5|6|7"` (too many),
  `"text|1|2|(w-text_w)/2|5|hi"` (expression), `"text|1|2|3|4|   "` (empty
  text), `"text|1|2|3|4"` (too few).
- Assert the header written by `dumps` uses `|` (e.g. contains
  `"# text|start|end|x|y|text"`) and that no saved annotation line contains a
  space-separated value layout (every non-comment line starts with `text|` or
  `blur|`).

### 7. `tests/test_annotate_sh.py`

- Update `test_render_text_and_blur` input to
  `"text|0.5|2|20|20|Hello world\nblur|1|2.5|100|100|200|100\n"`.
- Add a render test with text containing `|` and spaces and padded fields
  (`" text | 0.5 | 2 | 20 | 20 | a | b "`), CRLF line endings; it should succeed
  (same drawtext skip logic as the existing test).
- Add tests (no ffmpeg video needed, like `test_empty_annotation_file_fails`)
  that the script exits non-zero and prints a message containing the line number
  for: an old-format line (`text 0.5 2 20 20 Hello`), a legacy line without
  keyword, a non-numeric x (`text|0|1|(w-text_w)/2|5|hi`), a blur with too few
  fields, and empty text. Because validation happens before ffmpeg runs, these
  can pass a nonexistent input video path.
- Extract the drawtext-skip helper if the duplication gets noisy, but only if
  needed.

## Out of Scope

- Any backward compatibility or auto-conversion tool for old-format files.
- A format-choice option in the app.
- Escaping `|` (the text field is the last field, so none is needed).
- Supporting ffmpeg expressions for `x`/`y` in the renderer.
- Adding new annotation types or changing the GUI beyond the warning message
  text.
- Changing how text whitespace is normalized on save.

## Verification

1. `ruff check src tests` and `pytest` pass.
2. Launch the app (`./run.sh`), add a text annotation containing `|` and spaces
   and a blur annotation, save with `Ctrl+S`, and open the file: the header and
   all lines use `|`, and no whitespace-separated lines are written.
3. Load that file back in the app: annotations are identical (table matches).
4. Run `./scripts/annotate.sh in.mp4 saved.txt out.mp4` on the saved file and
   check the text and blur appear at the right times and positions.
5. Load `examples/annotations.txt` in the app and render it with `annotate.sh`.
6. Load a hand-written old-format file (`text 1 2 10 20 hi`, `1 2 3 4 hi`) in
   the app: the "Some lines were skipped" dialog lists them; run it through
   `annotate.sh`: it exits non-zero with a line-numbered message.
7. Try `text|1|2|(w-text_w)/2|20|hi` in both the app and the renderer: both
   reject it as malformed.
8. Check a hand-edited file with CRLF line endings loads and renders.

## Task List

- [ ] Update `src/vidnote/exporter.py`: docstring, `HEADER`, `to_line`,
      `parse_line`
- [ ] Update `scripts/annotate.sh`: header comment, `|` parsing with helpers,
      validation, line-numbered errors, CRLF handling
- [ ] Update the skipped-lines warning text in `src/vidnote/main_window.py`
- [ ] Convert `examples/annotations.txt` to the new format
- [ ] Update `README.md` (format section, example, rendering section)
- [ ] Update and extend `tests/test_exporter.py`
- [ ] Update and extend `tests/test_annotate_sh.py`
- [ ] Run `ruff check src tests` and `pytest`
- [ ] Run through the manual `## Verification` steps
