# Plan: text-annotation-box-fit

## Context

Spec: `_sdd/00002-text-annotation-box-fit/00002-text-annotation-box-fit-spec.md`

Today a text annotation is `text|start|end|x|y|text`: it only has a start point,
is drawn at a fixed size (`FONTSIZE=48` in `scripts/annotate.sh`,
`PREVIEW_FONT_PX = 48` in `video_view.py`) in the default sans font, with a
black background box that hugs the text (`boxborderw=12`). Long text can run off
the video. In the GUI the text annotation ignores `w`/`h` (the spins are
disabled for text). Blur is `blur|start|end|x|y|w|h`.

After this change a text annotation has a bounding box, like blur:

- `text|start|end|x|y|w|h|text` (text is the remainder after the 7th `|`, so it
  may contain `|`).
- `blur|start|end|x|y|w|h` is unchanged.

Per the spec and its answered Open Questions:

- Field order is `text|start|end|x|y|w|h|text`. No backward compatibility: old
  `text|start|end|x|y|text` lines are reported as malformed in both the app and
  the renderer, with a clear reason.
- Font size: 14 px default (maximum), 8 px minimum, fixed in video pixels. Text
  that fits at 14 px is never enlarged.
- Long text wraps (greedy word wrap, left aligned) inside the box width; the
  font size is reduced from 14 towards 8 until the wrapped text also fits the
  box height. A word longer than a line is hard-broken.
- If the text does not fit even at 8 px: warn (renderer: message on stderr,
  which the app's render dialog already shows; app: status bar message), but
  still render at 8 px.
- Monospace font, Ubuntu Mono preferred, fallback to the fontconfig `monospace`
  match with a warning. No font choice in the UI; always left aligned.
- Both implementations must produce the same size and the same line breaks, so
  the fit algorithm is written once in Python (`textfit.py`, no Qt imports) and
  ported 1:1 to bash in `annotate.sh`. A test hook makes the bash result
  checkable without ffmpeg.

### Fit model (shared by Python and bash, integer math only)

Constants (kept identical in both files):

| Name        | Value                                       | Meaning                                        |
| ----------- | ------------------------------------------- | ---------------------------------------------- |
| `MAX_SIZE`  | 14                                          | default / maximum font size, px                |
| `MIN_SIZE`  | 8                                           | minimum font size, px                          |
| `PAD`       | 4                                           | inner padding between box edge and text, px    |
| `LINE_H_PM` | 1150                                        | line height = `size * 1150 / 1000` (floor), px |
| `ADV_PM`    | 500 for Ubuntu Mono, 605 for any other font | glyph advance = `size * ADV_PM / 1000`         |

Algorithm `fit_text(text, w, h, adv_pm)`:

1. `avail_w = w - 2*PAD`, `avail_h = h - 2*PAD`.
2. For `size` from `MAX_SIZE` down to `MIN_SIZE`:
   - `cols = max(1, avail_w * 1000 // (size * adv_pm))`
   - `lines = wrap(text, cols)`
   - `line_h = size * LINE_H_PM // 1000`
   - if `len(lines) * line_h <= avail_h`: return `(size, lines, fits=True)`.
3. Otherwise return `(MIN_SIZE, wrap(text, cols at MIN_SIZE), fits=False)`.

`wrap(text, cols)`: split on single spaces (text was already whitespace
collapsed on save, but runs of spaces from a hand-edited file are collapsed
too); greedy fill lines up to `cols` characters; a word longer than `cols` is
cut into `cols`-sized pieces. Length is counted in characters (code points), not
bytes, so accented/Turkish letters count as one.

The text is drawn inside the box starting at `(x + PAD, y + PAD)`; the box
itself (`x, y, w, h`) is drawn as a semi-transparent black background, replacing
the old text-hugging `boxborderw` box. (This is a decision made in this plan,
the spec only requires the text to stay inside the box.)

## Files to Modify

### 1. `src/vidnote/models.py`

- Update field comments: `w`/`h` are used by blur and text.
- `validate()`: require `w > 0 and h > 0` for text as well:
  ```python
  if self.kind == BLUR and (self.w <= 0 or self.h <= 0):
      raise ValueError("A blur needs a region: drag a rectangle on the video.")
  if self.kind == TEXT and (self.w <= 0 or self.h <= 0):
      raise ValueError("A text annotation needs a box: drag a rectangle on the video.")
  ```

### 2. `src/vidnote/textfit.py` (new, no Qt imports)

- Constants from the table above and `@dataclass FitResult(size, lines, fits)`.
- `wrap(text: str, cols: int) -> list[str]` and
  `fit_text(text, w, h, adv_pm=DEFAULT_ADV_PM) -> FitResult` as described above.
- `resolve_font() -> FontInfo(family, file, preferred, adv_pm)`: runs
  `fc-match -f '%{family}|%{file}' 'Ubuntu Mono'`; `preferred` is true when the
  returned family (first name) equals `Ubuntu Mono` (case-insensitive). If not,
  run `fc-match -f '%{family}|%{file}' monospace`; `adv_pm` is 500 when
  preferred else 605. If `fc-match` is missing or fails, return family
  `monospace`, empty file, `preferred=False`, `adv_pm=605`. Cache with
  `functools.lru_cache`.
- A short module docstring stating that `scripts/annotate.sh` mirrors this
  algorithm and the constants must be kept in sync.

### 3. `src/vidnote/exporter.py`

- Update module docstring and `HEADER`:
  ```python
  HEADER = (
      "# vidnote annotations\n"
      "# text|start|end|x|y|w|h|text\n"
      "# blur|start|end|x|y|w|h\n"
  )
  ```
- `to_line`: text branch becomes
  ```python
  return "|".join(["text", fmt_time(a.start), fmt_time(a.end),
                   str(a.x), str(a.y), str(a.w), str(a.h), text])
  ```
- `parse_line`, text branch: `parts = line.split("|", 7)`; require
  `len(parts) == 8`, else
  `ValueError("text lines need: text|start|end|x|y|w|h|text (the old text|start|end|x|y|text format is no longer supported)")`.
  Parse `float` start/end and `int` x/y/w/h (this rejects an old line such as
  `text|1|2|3|4|hello` because `parts` has 6 items, and `text|1|2|3|4|a|b|c`
  because `a` is not an int). Raise
  `ValueError("w and h must be greater than 0")` when `w <= 0 or h <= 0`. Strip
  the text and raise `ValueError("text is empty")` if empty. The returned
  `Annotation` carries `w`/`h`.
- Blur branch and the `unknown line type` message stay unchanged.

### 4. `scripts/annotate.sh`

- Header comment: new text line shape; describe the fit rules (14 px max, 8 px
  min, wrapping, monospace, left aligned); remove `FONTSIZE` from the env
  overrides (keep `FONT`).
- Font selection (replaces the `fc-match ... sans` block):
  ```bash
  font="${FONT:-}"
  adv_pm=605
  if [ -z "$font" ]; then
    um="$(fc-match -f '%{family}|%{file}' 'Ubuntu Mono' 2>/dev/null || true)"
    if [[ "${um%%|*}" == *"Ubuntu Mono"* ]]; then font="${um#*|}"; adv_pm=500
    else
      echo "warning: Ubuntu Mono not found, using fallback monospace font" >&2
      font="$(fc-match -f '%{file}' monospace 2>/dev/null || true)"
    fi
  else
    fam="$(fc-scan --format '%{family}\n' "$font" 2>/dev/null | head -n1 || true)"
    [[ "$fam" == *"Ubuntu Mono"* ]] && adv_pm=500
  fi
  [ -z "$font" ] && font=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
  ```
- Add `export LC_ALL=C.UTF-8` (or `en_US.UTF-8` fallback, picked once) at the
  top so `${#var}` and `${var:i:n}` count characters, not bytes, matching
  Python.
- Add a `fit_text` bash function mirroring `textfit.fit_text`: takes `text w h`,
  sets globals `fit_size`, `fit_ok` and writes the wrapped lines to a file
  (`$tmp/$nt.txt`, joined with `\n`, no trailing newline). Integer arithmetic
  only: `cols=$(( avail_w * 1000 / (size * adv_pm) ))`,
  `[ $cols -lt 1 ] && cols=1`, `line_h=$(( size * 1150 / 1000 ))`. Wrapping
  loop: split the text on spaces with `read -ra words <<< "$text"` (this also
  collapses space runs), greedy fill, hard-break words longer than `cols` using
  `${word:0:cols}` / `${word:cols}`.
- `text` branch of the line loop:
  - require at least 7 `|`
    (`[ "${#pipes}" -ge 7 ] || die "text lines need: text|start|end|x|y|w|h|text (the old text|start|end|x|y|text format is no longer supported)"`);
  - pop `s e x y w h`, remainder is the text (trimmed, `die "text is empty"` if
    empty);
  - validate `s`/`e` with the existing number regex, `x y` with `^-?[0-9]+$`,
    `w h` with `^[0-9]+$` and then `-gt 0`
    (`die "w and h must be whole numbers greater than 0"`);
  - an old-format line (5 `|` or fewer, or a non-numeric `w`) is rejected by the
    checks above with a `file:line:` message;
  - call `fit_text`; if `fit_ok` is false print
    `warning: $list:$lineno: text does not fit in ${w}x${h}, rendering at ${MIN_SIZE}px`
    to stderr and continue;
  - record `boxes+=("$lineno:$x:$y:$w:$h")` for the frame check below;
  - filters (joined into `texts` with `,`):
    ```bash
    f="drawbox=x=$x:y=$y:w=$w:h=$h:color=black@0.5:t=fill:enable='between(t,$s,$e)',"
    f+="drawtext=fontfile=$font:textfile=$tmp/$nt.txt:expansion=none:fontsize=$fit_size"
    f+=":fontcolor=white:x=$((x+PAD)):y=$((y+PAD)):line_spacing=0"
    f+=":enable='between(t,$s,$e)'"
    ```
    (`fontsize` must be an integer; `line_spacing` is tuned during verification
    so the real line pitch matches `size * 1.15`, see Verification step 4).
- Frame check (after the loop, before ffmpeg, only if `boxes` is non-empty and
  `ffprobe` is available): read the video size with
  `ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$in"`;
  if it succeeds, for each recorded text box with
  `x < 0 || y < 0 || x+w > W || y+h > H` print
  `$list:$lineno: text box extends beyond the ${W}x${H} video` and exit 1. If
  `ffprobe` fails (e.g. a missing input in tests) skip the check silently. This
  is the "rejected with a clear message" behaviour from the spec's edge cases
  for the renderer; blur is not checked (unchanged).
- Test hook for a display/ffmpeg-free parity check: when `VIDNOTE_PRINT_FIT=1`,
  after parsing, print one line per text annotation as
  `fit|<lineno>|<size>|<fits 0/1>` followed by the wrapped lines each prefixed
  with `  |`, and exit 0 before touching ffmpeg/ffprobe. Document it only in a
  script comment (it is a test hook, not a user feature).

### 5. `src/vidnote/video_view.py`

- Remove `PREVIEW_FONT_PX` and `BOX_BORDER`; import `textfit`.
- In `set_overlays`, text branch (replace lines ~162-177): compute
  `res = textfit.fit_text(a.text, a.w, a.h, font.adv_pm)` where `font` comes
  from a module-level `textfit.resolve_font()`. Draw:
  - a background `QGraphicsRectItem(a.x, a.y, a.w, a.h)` filled
    `QColor(0, 0, 0, 128)`, no pen, z = 51;
  - one `QGraphicsSimpleTextItem` per wrapped line, `QFont(font.family)` with
    `setStyleHint(QFont.StyleHint.Monospace)` and `setPixelSize(res.size)`,
    white brush, z = 52, positioned at
    `(a.x + PAD, a.y + PAD + i * (res.size * LINE_H_PM // 1000))`. One item per
    line makes the preview line pitch match the renderer instead of Qt's own
    line spacing.
  - if `not res.fits`, also add a dashed red cosmetic outline around the box
    (`_cosmetic_pen("#ff4040", 2, dashed=True)`) so the overflow is visible in
    the preview.
- The overlay cache key (`astuple(a)`) already covers `w`/`h`, no change needed.

### 6. `src/vidnote/main_window.py`

- `_on_kind_changed`: enable `w_spin`/`h_spin` for both kinds (only `text_edit`
  stays blur-disabled).
- `_form_annotation`: always pass `w=self.w_spin.value()`,
  `h=self.h_spin.value()`.
- `add_annotation` / `update_annotation`: after `a.validate()`, call a new
  helper `_check_in_frame(a)`: if the video size is known and
  `a.x + a.w > video_w or a.y + a.h > video_h` (text only), raise
  `ValueError("The box extends beyond the video frame (WxH).")` so the existing
  "Cannot add/update" dialog is shown. After a successful add/update of a text
  annotation, run `textfit.fit_text`; if `fits` is false, show a status bar
  message
  `"Text does not fit in the box even at 8 px; it will be rendered at 8 px."`.
- Hint label:
  `"Click the video for a point, drag for a region (text and blur both need a drag)."`.
- Load warning dialog (~line 494): expected formats are now
  `'text|start|end|x|y|w|h|text'` or `'blur|start|end|x|y|w|h'`.
- Font warning: at the end of `__init__`, if
  `not textfit.resolve_font().preferred`, schedule `QTimer.singleShot(0, ...)`
  showing a `QMessageBox.information` "Ubuntu Mono is not installed. Using
  <family> instead; text fitting may differ slightly." Import `QTimer` from
  `QtCore`.
- `_refresh_table` / `_on_row_selected` already show and restore `w`/`h`;
  `view.show_selection` now highlights the text box too. No change.

### 7. `examples/annotations.txt`

```
# vidnote annotations
# text|start|end|x|y|w|h|text
# blur|start|end|x|y|w|h
text|2|6|50|50|400|60|Welcome to the tutorial
blur|3|8|100|200|300|120
text|10|14|80|400|220|80|Click the Save button, then choose a folder to store the file
```

(The last line deliberately wraps/shrinks to demonstrate the fit.)

### 8. `README.md`

- Requirements: add `fonts-ubuntu` (provides Ubuntu Mono) to the apt line and
  note that a fallback monospace font is used if it is missing.
- Usage step 3: "Text and blur: drag a rectangle on the video (text also needs
  its words typed)".
- Annotation file format section: new text line shape, explain that the text is
  fitted into the `w`x`h` box (14 px max, 8 px min, wraps, left aligned,
  monospace; does not grow beyond 14 px), that a text which cannot fit at 8 px
  is rendered at 8 px with a warning, that old `text|start|end|x|y|text` lines
  are no longer supported, and update the example lines (e.g.
  `text|53.96|60.96|170|220|300|60|deneme`).
- "Rendering without the GUI": remove `FONTSIZE=48` from the env vars, mention
  the `FONT` override and the beyond-frame rejection and the does-not-fit
  warning.
- Project layout: add `textfit.py` and `test_textfit.py`.

### 9. `tests/test_models.py`

- Update existing text annotations to carry a box (e.g.
  `Annotation(TEXT, 2, 4, 0, 0, 100, 40, text="x")`).
- Add rejecting cases: text with `w == 0`, text with `h == 0`.
- `test_validate_accepts`: text with a box.

### 10. `tests/test_textfit.py` (new)

- `wrap`: short text single line; greedy wrap at word boundaries; a word longer
  than `cols` is hard-broken; Turkish/accented characters count as one
  (`"çğıöşü"` with `cols=3` -> two lines); multiple spaces collapsed; `cols=1`.
- `fit_text`: short text in a large box -> size 14, `fits` true (not enlarged);
  long text in a medium box -> size between 8 and 13, all lines within
  `avail_w // char_w` columns and total height within the box; very long text in
  a tiny box -> size 8, `fits` false; single long word wider than the box ->
  hard-broken, no line longer than `cols`; box smaller than `2*PAD` does not
  crash.
- Property-style loop: for a range of texts and boxes, if `fits` then
  `len(lines) * line_h <= h - 2*PAD` and every line is `<= cols` characters.
- Adv difference: the same text/box gives a size less than or equal with
  `adv_pm=605` than with `500`.
- `resolve_font` with `fc-match` monkeypatched to return a non-Ubuntu family:
  `preferred` is false and `adv_pm == 605`; with Ubuntu Mono: `preferred` true,
  `adv_pm == 500`; with `subprocess.run` raising `FileNotFoundError`: fallback
  values, no exception. Clear the `lru_cache` between cases.

### 11. `tests/test_exporter.py`

- `test_roundtrip`: all text annotations get `w`/`h`; assert
  `parsed[i] == items[i]` for the text items too (identical x, y, w, h after
  save/load) and that `"a | b|c"` still round-trips.
- `test_dumps_uses_pipe_format`: header contains
  `# text|start|end|x|y|w|h|text`; text data line is
  `text|2|6|50|60|200|80|hi there`.
- `test_comments_and_blank_lines_ignored`: `text|1|2|3|4|50|20|hi`.
- `test_pipe_format_lines`: parse `text|53.96|60.96|170|220|300|60|deneme`,
  assert the `Annotation` and that `to_line` returns the same string; whitespace
  tolerance (`" text | 1 | 2 | 10 | 20 | 100 | 40 | Hello "`).
- `test_text_is_remainder_after_seventh_pipe`: `text|1|2|3|4|50|20|a|b|c` ->
  text `"a|b|c"`.
- `test_malformed_lines_are_reported`: old format `text|1|2|3|4|hello` (reason
  mentions "no longer supported"), `text|1|2|3|4|a|b|c` (non-numeric w),
  `text|1|2|3|4|0|20|hi` (w zero), `text|1|2|3|4|50|-5|hi` (h negative),
  `text|1|2|3|4|50|20|   ` (empty), `text|1|2|3|4|50|20` (too few), plus the
  existing blur and whitespace-separated cases; all skipped with correct line
  numbers and non-empty reasons. Also assert a blur line still parses unchanged.
- Update `test_saved_lines_are_always_pipe_separated` inputs to include a box.

### 12. `tests/test_annotate_sh.py`

- Update the render tests to the new shape, e.g.
  `"text|0.5|2|20|20|300|60|Hello world\nblur|1|2.5|100|100|200|100\n"` and the
  padded/CRLF/`|`-in-text test
  `" text | 0.5 | 2 | 20 | 20 | 300 | 60 | a | b \r\n..."`.
- Add a render test with a long text in a small box (e.g. `120x40`) that must
  still succeed (warning printed, exit 0), and assert `"does not fit"` appears
  in stderr (extend `_render` to return the `CompletedProcess`).
- `test_malformed_line_fails_with_line_number`: replace the parameter list with
  new-format cases: old `text|0|1|2|3|hi`, `text 0.5 2 20 20 Hello`,
  `0.5 2 20 20 Hello`, `text|0|1|2|3|0|20|hi` (w zero), `text|0|1|2|3|50|-5|hi`,
  `text|0|1|2|3|50|20|   ` (empty), `blur|1|2|3|4`, `blur|1|2|3|4|5|6|7`; the
  good first data line becomes `text|0|1|2|3|50|20|ok`. Still assert
  `"ann.txt:3:"` in stderr.
- Add a test that a text box extending beyond the frame is rejected (renders a
  640x360 test video, line `text|0|1|600|10|100|50|hi`; expects non-zero exit
  and `"beyond"` in stderr). Shares the lavfi video generation with `_render`.
- Add `test_fit_matches_python` (no ffmpeg video needed but needs `fc-match`;
  skip if `fc-match` is missing): for a set of `(text, w, h)` cases run
  `VIDNOTE_PRINT_FIT=1 bash annotate.sh missing.mp4 ann.txt y.mp4`, parse the
  `fit|...` output and the indented lines, and compare size, `fits` and the
  wrapped lines with
  `textfit.fit_text(text, w, h, textfit.resolve_font().adv_pm)`. Cases include
  short text, wrapping text, a long word, Turkish letters, and an unfittable
  case.

## Out of Scope

- Backward compatibility with, or conversion of, old `text|start|end|x|y|text`
  files.
- Font selection UI, alignment (left/center) control, colours.
- Explicit line breaks in the text (the format stays one line per annotation;
  `to_line` still collapses whitespace).
- Exact glyph measurement (FreeType/`text_w`); fitting uses the fixed-advance
  model above, which is accurate for monospace fonts.
- Changing blur behaviour or the blur frame handling (blur is not checked
  against the video size).
- Resizing/moving boxes by dragging handles in the preview; the box is edited
  via the W/H spins or by dragging a new rectangle.

## Verification

1. `ruff check src tests` and `pytest` pass (including `test_textfit.py` and the
   bash/Python fit parity test).
2. Launch `./run.sh sample.mp4`, drag a rectangle, type short text, add: the
   preview shows a semi-transparent box with the text at 14 px at the top-left
   inside the box (not enlarged). Resize the box with the W/H spins and **Update
   selected**: the text re-fits.
3. Type a long sentence into a small box: the preview wraps it and shrinks it
   (>= 8 px). Make the box tiny: the status bar warns and a red dashed outline
   appears; the text is still shown at 8 px.
4. Save (`Ctrl+S`): the header and every text line use
   `text|start|end|x|y|w|h|text`. Load it back: the table (including W/H) is
   identical. Render (`Ctrl+R`) the same annotations: in the output video the
   text sits inside the box, uses the same size and the same line breaks as the
   preview, with the monospace font. Compare a frame against the preview; if the
   rendered line pitch differs from `size * 1.15`, tune `line_spacing` in
   `annotate.sh` (and the `LINE_H_PM` constant in both files) until they match.
5. Render `examples/annotations.txt` with `./scripts/annotate.sh`: the third
   text wraps/shrinks inside its box.
6. Check the Turkish text `Çok güzel bir şarkı ışığı` and a text with `|` in a
   box: preserved, wrapped correctly, no mojibake.
7. Hand-write old-format lines (`text|1|2|10|20|hi`, `text 1 2 10 20 hi`) and
   load them in the app: the "Some lines were skipped" dialog lists them with a
   clear reason; run them through `annotate.sh`: non-zero exit with a
   `file:line:` message.
8. Try `w=0`, `h=-5`, and a box extending past the frame in the app (rejected in
   the "Cannot add" dialog) and in `annotate.sh` (rejected with a message).
9. Temporarily hide Ubuntu Mono (e.g. a `FONTCONFIG_FILE` that excludes it, or
   `FONT=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf` for the script):
   the app shows the information dialog once at startup, and the script prints
   the fallback warning; rendering still succeeds.
10. Blur annotations still save, load, preview and render as before.

## Task List

- [ ] Update `src/vidnote/models.py`: text requires `w`/`h` > 0, comments
- [ ] Add `src/vidnote/textfit.py`: constants, `wrap`, `fit_text`,
      `resolve_font`
- [ ] Update `src/vidnote/exporter.py`: docstring, `HEADER`, `to_line`,
      `parse_line` text branch
- [ ] Update `scripts/annotate.sh`: font selection, UTF-8 locale, `fit_text`
      function, new text parsing/validation, `drawbox` + `drawtext` filters,
      does-not-fit warning, frame check, `VIDNOTE_PRINT_FIT` hook, header
      comment
- [ ] Update `src/vidnote/video_view.py`: fitted text preview (box background,
      per-line items, overflow outline)
- [ ] Update `src/vidnote/main_window.py`: enable W/H for text, form values,
      in-frame check, fit status message, hint text, load warning text, missing
      font dialog
- [ ] Update `examples/annotations.txt`
- [ ] Update `README.md`
- [ ] Update `tests/test_models.py`
- [ ] Add `tests/test_textfit.py`
- [ ] Update `tests/test_exporter.py`
- [ ] Update `tests/test_annotate_sh.py` (new shape, does-not-fit, beyond-frame,
      old-format rejection, Python/bash fit parity)
- [ ] Run `ruff check src tests` and `pytest`
- [ ] Run through the manual `## Verification` steps
