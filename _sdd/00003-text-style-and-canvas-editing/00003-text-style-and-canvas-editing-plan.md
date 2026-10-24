# Plan: text-style-and-canvas-editing

## Context

Spec:
`_sdd/00003-text-style-and-canvas-editing/00003-text-style-and-canvas-editing-spec.md`

Today a text annotation is `text|start|end|x|y|w|h|text`. The font size is
chosen automatically by `textfit.fit_text` (14 px down to 8 px until the wrapped
text fits the box), the box is always `black@0.5`, the text is always white, and
the same algorithm is mirrored in bash in `scripts/annotate.sh`. On the canvas
the user can only pick a point or drag a new rectangle (`VideoView`); existing
annotations can only be changed through the form and the list.

After this change:

- The text line is `text|start|end|x|y|w|h|size|boxcolor|textcolor|text` (text
  is the remainder after the 10th `|`, so it may still contain `|`).
  `blur|start|end|x|y|w|h` is unchanged. Old text lines are rejected as
  malformed in both the app and the renderer ("no longer supported"); no
  backward compatibility.
- `size` is an integer in video pixels, range 8-72, default 14. There is no
  auto-fit: text is wrapped to the box width and drawn at exactly `size`. If the
  wrapped text is taller than the box (or not even one character fits the box
  width) the user is warned (status bar in the app, stderr in `annotate.sh`) and
  the text is still drawn.
- `boxcolor` is a hex value chosen from a global, user-editable list of
  `hex|label` entries (stored in the app's `QSettings`; a simple text file is a
  future option). `textcolor` is `#000000` or `#ffffff` only. Both are stored in
  the file as `#rrggbb` (lowercase on write; with or without `#` and any case on
  read). Box opacity stays fixed at 50%.
- A selector mode (toolbar toggle) lets the user click an annotation that is
  active at the current time, drag it and resize it with handles (text and
  blur). Annotations that are not active at the current time are selectable only
  through the list; once selected from the list they can be moved/resized on the
  canvas too (their highlight and handles are drawn from their data).
- Resizing a text box scales its font size with the box (still editable through
  the size spin box); moving does not change the size.
- A "Hide preview" toggle hides all preview items on the canvas (rectangles,
  text previews, selection highlight and handles) without touching annotations;
  toggling it again, or selecting a row in the list, shows them again.

### Decisions beyond the spec text

- Size scaling on resize:
  `new_size = clamp(round(old_size * min(new_w / old_w, new_h / old_h)), 8, 72)`,
  computed from the box before and after the drag (pure function
  `textfit.scaled_size`, testable without Qt).
- Colour config format: exactly one `|` per line, `hex|label`; hex is 6 digits
  (3-digit and other lengths are invalid); labels cannot be empty or contain
  `|`; there are no comment lines (`#` starts a hex value), only blank lines are
  ignored. Duplicate hex values (after normalisation): the first wins, later
  ones are reported. Invalid lines are reported and skipped. If no valid entry
  remains the default list is used.
- Default colour list: `#000000|Black`, `#ffffff|White`, `#ffd400|Yellow`,
  `#1e90ff|Blue`, `#e03131|Red`, `#2f9e44|Green`.
- An annotation whose box colour is not in the list keeps its hex; the form's
  box-colour combo shows it as an extra `#hex (not in list)` entry while that
  annotation is selected.
- Overlapping annotations in selector mode: a click selects the topmost (last in
  the list); clicking again at the same spot selects the next one below
  (wrapping); the list can always select any annotation. Handles of the current
  selection take priority over selecting another annotation.
- Clicking empty canvas in selector mode keeps the current selection. Leaving
  selector mode keeps the selection and the data; any drag in progress is
  cancelled on a mode switch.
- Moving/resizing clamps the box inside the video frame (whole pixels) and
  enforces a minimum box of 10x10 px for both kinds. A text box smaller than one
  line is allowed and shows the overflow outline plus the warning.
- Text colour equal to box colour (e.g. black on black) is allowed; the app
  shows a status bar warning. The renderer does not warn.
- Canvas geometry changes are applied when the mouse is released (the yellow
  highlight rectangle follows the mouse during the drag), then the annotation,
  list, form and preview are refreshed.
- The `VIDNOTE_PRINT_FIT` test hook in `annotate.sh` is renamed
  `VIDNOTE_PRINT_LAYOUT`, because there is no fitting any more.

## Files to Modify

### 1. `src/vidnote/colors.py` (new, no Qt imports)

Pure helpers for hex colours and the colour list config.

```python
TEXT_COLORS = ("#000000", "#ffffff")          # allowed text colours
DEFAULT_COLOR_LIST = [("#000000", "Black"), ("#ffffff", "White"), ...]

def normalize_hex(value: str) -> str: ...     # "ABC123" / "#abc123" -> "#abc123"; ValueError otherwise
def parse_color_list(text: str) -> tuple[list[tuple[str, str]], list[tuple[int, str, str]]]:
    """(entries, skipped) where skipped holds (lineno, line, error)."""
def dump_color_list(entries) -> str:          # one "hex|label" per line
def default_color_list_text() -> str
```

`parse_color_list` ignores blank lines, handles `\r\n`, rejects lines with no or
more than one `|`, an invalid hex, an empty label, or a duplicate hex, and
returns the valid entries in order.

### 2. `src/vidnote/models.py`

- Constants `DEFAULT_SIZE = 14`, `MIN_SIZE = 8`, `MAX_SIZE = 72`,
  `DEFAULT_BOX_COLOR = "#000000"`, `DEFAULT_TEXT_COLOR = "#ffffff"`.
- `Annotation` gets three fields after `text` (so existing positional calls keep
  working): `size: int = DEFAULT_SIZE`, `box_color: str = DEFAULT_BOX_COLOR`,
  `text_color: str = DEFAULT_TEXT_COLOR`.
- `validate()` for TEXT additionally: `MIN_SIZE <= size <= MAX_SIZE` ("Font size
  must be between 8 and 72 px."), `box_color` valid via `colors.normalize_hex`,
  `text_color` in `colors.TEXT_COLORS` ("Text colour must be black or white.").
  Blur ignores the new fields.

### 3. `src/vidnote/textfit.py`

Remove the auto-fit: delete `fit_text`, `MAX_SIZE`, `MIN_SIZE`, `FitResult`'s
fit-search usage. Keep `PAD`, `LINE_H_PM`, `DEFAULT_ADV_PM`, `wrap`,
`line_height`, `_cols`, `resolve_font`, `FontInfo` (the module keeps its name to
limit churn; update the docstring to "text layout in a box").

```python
@dataclass
class LayoutResult:
    size: int
    lines: List[str]
    fits: bool            # False = taller than the box, or not even one glyph wide

def layout_text(text, w, h, size, adv_pm=DEFAULT_ADV_PM) -> LayoutResult:
    avail_w, avail_h = w - 2 * PAD, h - 2 * PAD
    lines = wrap(text, _cols(avail_w, size, adv_pm))
    one_glyph = size * adv_pm // 1000
    fits = len(lines) * line_height(size) <= avail_h and avail_w >= one_glyph
    return LayoutResult(size, lines, fits)

def scaled_size(size, old_w, old_h, new_w, new_h) -> int:   # min ratio, rounded, clamped 8..72
```

`MIN_SIZE`/`MAX_SIZE` come from `models`. The bash mirror stays integer-only and
uses the same constants (`PAD`, `LINE_H_PM`, `ADV_PM`).

### 4. `src/vidnote/exporter.py`

- New `HEADER` comment line:
  `# text|start|end|x|y|w|h|size|boxcolor|textcolor|text`.
- Module docstring updated.
- `to_line` for TEXT:
  `text|start|end|x|y|w|h|size|<box_color>|<text_color>|text` (colours
  normalised through `colors.normalize_hex`, text collapsed to one line as
  today).
- `parse_line` for TEXT: `parts = line.split("|", 10)`; need 11 parts, else
  `ValueError("text lines need: text|start|end|x|y|w|h|size|boxcolor|textcolor|text (older text formats are no longer supported)")`.
  Parse ints for x, y, w, h, size (message "no longer supported" when the size
  is not an integer, which catches old lines such as
  `text|1|2|3|4|50|20|hello|...`), `w, h > 0`, size in 8-72, colours via
  `normalize_hex`, text colour must be black or white, text not empty. Blur
  parsing unchanged.

### 5. `scripts/annotate.sh`

- Header comment: new line shape, remove the auto-fit paragraph, describe size,
  colours and the warning; rename the hook to `VIDNOTE_PRINT_LAYOUT`.
- Constants: replace `MAX_SIZE=14; MIN_SIZE=8` by `MIN_SIZE=8; MAX_SIZE=72`
  (range check only); keep `PAD`, `LINE_H_PM`, `ADV_PM`.
- Replace `fit_text` with `layout_text size w h` that wraps with
  `cols = max(1, avail_w*1000/(size*ADV_PM))` and sets `$layout_ok` using the
  same rule as Python (`lines*line_h <= avail_h` and
  `avail_w >= size*ADV_PM/1000`). `wrap_text` is unchanged.
- Text branch: require `${#pipes} >= 10`; pop fields
  `s e x y w h size boxcolor textcolor`; the rest is the text. Validate: size
  matches `^[0-9]+$` and is in 8-72; `boxcolor` matches `^#?[0-9a-fA-F]{6}$`;
  `textcolor` (normalised, lowercased with `${var,,}`) is `000000` or `ffffff`.
  Use the new `msg` ("text lines need: ...; older text formats are no longer
  supported") for field-count/format errors, same `die` helper with `file:line`.
- Colours go to ffmpeg as `0xrrggbb`: `drawbox=...:color=0xRRGGBB@0.5` and
  `fontcolor=0xRRGGBB`; `fontsize=$size` replaces `fontsize=$fit_size`.
- If `layout_ok` is 0:
  `warning: file:line: text does not fit in WxH at SIZEpx, drawing it anyway` on
  stderr (keeps the "does not fit" wording and `file:line:` prefix).
- Test hook: with `VIDNOTE_PRINT_LAYOUT=1` print
  `layout|lineno|size|ok|0xbox|0xtext` followed by the wrapped lines as
  `  |line`, and exit before ffmpeg.

### 6. `src/vidnote/video_view.py`

- New signals: `annotationPicked = Signal(int)` (index into the full annotation
  list), `geometryEdited = Signal(int, int, int, int, int)` (index, x, y, w, h
  in whole video pixels).
- `set_overlays(items)` takes a list of `(index, Annotation)` for the
  annotations active at the current time; the cache key includes the indices.
  The text overlay uses `a.size`, `a.box_color` (alpha 128) and `a.text_color`,
  calls `textfit.layout_text(a.text, a.w, a.h, a.size)`, keeps the red dashed
  outline when `not fits`, and keeps one text item per line with
  `line_height(a.size)` pitch (`font.setPixelSize(a.size)`).
- Mode: `set_mode(select: bool)` / `mode`. Draw mode is today's rubber-band
  behaviour. Select mode:
  - `mousePressEvent`: if there is a selection, hit-test its 8 handles (handle
    size ~8 screen px, tested in view coordinates via `mapFromScene`) then its
    body (move). Otherwise hit-test the active overlay boxes, topmost first,
    cycling to the next one below when the click lands on the current
    selection's spot; emit `annotationPicked(index)`. Empty click does nothing.
  - `mouseMoveEvent`: update `_selection` rect from the drag (move or resize),
    clamped to the video rect, min 10x10 px, rounded to ints.
  - `mouseReleaseEvent`: emit `geometryEdited(index, x, y, w, h)` if the rect
    changed.
  - Cursor: arrow in select mode, cross in draw mode; resize cursors over
    handles.
  - `set_mode` cancels any drag in progress (`_drag_start = None`, edit state
    reset) and keeps the selection.
- Selection: `set_selected(index: Optional[int], rect: Optional[QRectF])`
  replaces `show_selection` for rows (the drawing-mode rubber band keeps using
  `_show_selection`). Handles are small `QGraphicsRectItem`s with
  `ItemIgnoresTransformations`, visible only in select mode with a selection;
  the highlight is drawn from the given rect, so annotations not active at the
  current time are still shown/editable once chosen from the list.
- Hide toggle: `set_overlays_visible(bool)` shows/hides overlay items, the
  selection highlight and the handles; a visible rubber band while dragging a
  new region in draw mode is still shown; select-mode hit-testing ignores hidden
  items.

### 7. `src/vidnote/colors_dialog.py` (new)

`ColorListDialog(QDialog)`: a `QPlainTextEdit` holding the `hex|label` lines
(from `colors.dump_color_list`), a short help label, "Restore defaults",
OK/Cancel. On OK it calls `colors.parse_color_list`; when lines were skipped it
shows them (`line N: reason`) and still saves the valid entries; if no valid
entries remain it shows an error and keeps the dialog open. Exposes `entries()`
after `exec()`.

### 8. `src/vidnote/main_window.py`

- Imports: `colors`, `ColorListDialog`, `QSettings`, `QToolBar`/`QAction`,
  `QPixmap`/`QIcon` for colour swatches.
- Colour list: `self.color_list = self._load_color_list()` reading `QSettings`
  key `boxColors` (text in the same `hex|label` form; defaults on first run;
  invalid lines reported in the status bar and skipped); `_save_color_list()`.
  Menu "Edit" → "Text box colours..." opens `ColorListDialog`, saves the result
  and repopulates the combo.
- Form: new rows after Size: `self.size_spin` (QSpinBox, 8-72, default 14, label
  "Font size"), `self.box_combo` (swatch icon + label, item data = hex),
  `self.text_color_combo` (Black / White, data `#000000` / `#ffffff`). All three
  are disabled for Blur in `_on_kind_changed`. `_populate_box_combo(extra=None)`
  rebuilds the combo and appends `#hex (not in list)` when needed.
- `_form_annotation()` fills `size`, `box_color`, `text_color`.
- `_fill_form(a)` extracted from `_on_row_selected` (also sets the new widgets
  and the "not in list" entry); `_on_row_selected` calls it, turns the hide
  toggle off, and calls `self.view.set_selected(row, QRectF(...))`.
  `_refresh_table` adds the three new columns (`Size`, `Box`, `Text`; update
  `COLUMNS` and the cells, `-` for blur) and ends by re-syncing the view
  selection (clearing it when the list is empty).
- `_update_overlays` passes
  `[(i, a) for i, a in enumerate(self.annotations) if a.is_active(t)]`.
- `_warn_if_unfit(a)` uses `textfit.layout_text(...)`: status bar message "Text
  is taller than the box at N px; it will still be drawn at N px." Also warn
  when `box_color == text_color`.
- Toolbar (`QToolBar`, no shortcuts to avoid stealing keys from the text field):
  checkable "Select" action (`view.set_mode`) and checkable "Hide preview"
  action (`view.set_overlays_visible(not checked)`).
- Signals: `view.annotationPicked` → select that table row (which fills the form
  and highlights); `view.geometryEdited` →
  `_on_geometry_edited(index, x, y, w, h)`: update the annotation; for TEXT, if
  `w`/`h` changed set `size = textfit.scaled_size(...)` (status message when
  clamped); refresh table, form and overlays; call `_warn_if_unfit`.
- `load_annotations` warning text and `README`-style hint updated to the new
  line shape. Hint label mentions Select mode.
- `_check_in_frame` stays for add/update via the form (TEXT only, as today).

### 9. `tests/test_models.py`

Add rejects for `size` 7 and 73, bad `box_color` (`"#GGG"`, `"red"`), text
colour `#ff0000`; accepts for size 8/72 and `box_color="000000"`; defaults check
(`14`, `#000000`, `#ffffff`); blur ignores the new fields.

### 10. `tests/test_colors.py` (new)

`normalize_hex` (with/without `#`, upper/lower case, 3 digits, 5/7 digits,
`#GGG`, empty); `parse_color_list` (valid list, CRLF, blank lines, missing `|`,
extra `|`, empty label, invalid hex, duplicate hex reported and first kept);
dump/parse roundtrip; default list is valid and starts with `#000000|Black`.

### 11. `tests/test_textfit.py`

Remove the `fit_text` tests and `MAX_SIZE`/`MIN_SIZE` imports from `textfit`.
Keep the `wrap` and `resolve_font` tests. Add: `layout_text` returns exactly the
requested size for several sizes and box dimensions (no auto-shrink even when
text overflows); `fits` is False when lines are too tall or the box is narrower
than one glyph; hard-break of a long word at a given size; tiny box does not
crash; `scaled_size` (same box → same size, doubled box → doubled size, one axis
scaled uses the smaller ratio, clamps to 8 and 72).

### 12. `tests/test_exporter.py`

Update every text example to the new shape. Cover: roundtrip including size and
colours (and `|` in text), normalisation of colours on write (`ABC123` →
`#abc123`) and read (with/without `#`), `dumps` header line and data lines, text
as remainder after the 10th pipe, blur unchanged, saved lines still always
pipe-separated. Malformed list: old shapes (`text|1|2|3|4|hi`,
`text|1|2|3|4|50|20|hi`, `text|1|2|3|4|a|b|c`), size 7/73/non-integer, bad box
colour, text colour not black/white, w/h <= 0, empty text, missing text field;
old-format ones must contain "no longer supported".

### 13. `tests/test_annotate_sh.py`

Update all text lines to the new shape. Replace the fit tests:

- renders succeed with various sizes and colours, padded fields, CRLF and `|` in
  text;
- a too-small box warns (`does not fit`, `ann.txt:1:`) but still succeeds; a
  roomy box does not warn; a text that would previously have been shrunk is
  drawn at exactly the given size (checked through `VIDNOTE_PRINT_LAYOUT`);
- malformed lines (old format, bad size, size 7/73, bad box colour, text colour
  `#ff0000`, missing fields, `blur` field-count errors) fail with `ann.txt:3:`;
- box beyond frame still rejected;
- `test_layout_matches_python`: for several `(text, w, h, size)` cases compare
  the hook's `layout|...` output (size, ok, wrapped lines, colours) with
  `textfit.layout_text` and `colors.normalize_hex`.

### 14. `README.md`, `examples/annotations.txt`, `AGENTS.md`

- README: new usage steps (font size, colours, Select mode, Hide preview, colour
  list editor), new format section
  (`text|start|end|x|y|w|h|size|boxcolor|textcolor|text`, size 8-72, colours
  hex, text colour black/white only, no auto-fit, warning when the text does not
  fit, old text lines unsupported), env var / hook rename if mentioned, project
  layout (`colors.py`, `colors_dialog.py`, `test_colors.py`).
- `examples/annotations.txt`: header comment and sample lines in the new shape
  (include different sizes, a non-black box colour and black text).
- `AGENTS.md`: update the "Annotation format" section (new text shape; the file
  still says `text start end x y text...`), mention `colors.py` as Qt-free next
  to `models.py`/`exporter.py`, and that `textfit.py` has no auto-fit.

## Out of Scope

- Configurable box opacity (fixed at 50%).
- Storing the colour list in a plain text file or per annotation file (app
  settings only; global).
- Text colours other than black and white; fonts other than the monospace font
  already used; text alignment.
- Backward compatibility for old text lines.
- Changes to blur rendering or the blur file format.
- Live (during-drag) text preview redraw; the preview is redrawn on release.
- Undo/redo, multi-selection, keyboard nudging of the selection.
- Warning about equal box and text colours in the renderer.

## Verification

1. `ruff check src tests` and `pytest` pass (the `annotate.sh` tests skip only
   when ffmpeg/drawtext is missing).
2. `./scripts/annotate.sh` on a sample video with `examples/annotations.txt`:
   text is drawn at the given sizes with the given box and text colours; a text
   box too small for its text prints `warning: ...: text does not fit ...` and
   still renders; an old-format line (`text|0|1|2|3|50|20|hi`) fails with a
   `file:line` message and "no longer supported".
3. `./run.sh sample.mp4`: add a text annotation, change Font size (spin box) and
   confirm the canvas preview text size changes immediately after Update; pick
   different box colours and Black/White text; the preview matches the rendered
   video (`Ctrl+R`) closely, including line breaks.
4. Edit the colour list via Edit → Text box colours...: add, remove and edit
   entries, enter an invalid line and see it reported and skipped; restart the
   app and confirm the list persisted; select an annotation whose colour was
   removed and see `#hex (not in list)`; render it and confirm the colour is
   kept.
5. Save (`Ctrl+S`) and open the file: lines have size and `#rrggbb` colours and
   the new header; load it again and confirm identical values in the list.
6. Select mode: click a text and a blur annotation, drag them, resize with the
   handles; confirm they stay inside the frame, the list/form values change, the
   text font size scales when resizing a text box, and the size spin box can
   override it. Click at an overlap spot repeatedly to cycle. Switch back to
   draw mode mid-drag and confirm no change; confirm the selection survives the
   mode switch. Select an annotation that is not active at the current time
   through the list and move it.
7. Hide preview: the canvas shows no rectangles, text, highlight or handles;
   list and saved file are unchanged; toggling it off, or selecting a row,
   brings the preview back. Toggle with nothing shown and during a drag without
   errors.
8. Turkish characters, `|` in text and Windows line endings still round-trip;
   blur annotations still save, load and render as before.

## Task List

- [ ] Add `src/vidnote/colors.py` (`normalize_hex`, `TEXT_COLORS`, default list,
      `parse_color_list`, `dump_color_list`)
- [ ] Update `src/vidnote/models.py` (size/colour constants, new `Annotation`
      fields, `validate()` rules)
- [ ] Rework `src/vidnote/textfit.py` (remove auto-fit, add `layout_text`,
      `LayoutResult`, `scaled_size`)
- [ ] Update `src/vidnote/exporter.py` (new header, `to_line`, `parse_line`)
- [ ] Update `scripts/annotate.sh` (new fields and validation, `layout_text`,
      colours, warning, `VIDNOTE_PRINT_LAYOUT` hook, header comment)
- [ ] Add `tests/test_colors.py` and update `tests/test_models.py`,
      `tests/test_textfit.py`, `tests/test_exporter.py`,
      `tests/test_annotate_sh.py`; run `pytest` and `ruff check src tests`
- [ ] Update `src/vidnote/video_view.py` (new signals, indexed overlays, styled
      text preview, select mode with move/resize/handles, selection API, hide
      toggle)
- [ ] Add `src/vidnote/colors_dialog.py`
- [ ] Update `src/vidnote/main_window.py` (form widgets, colour list +
      `QSettings`, Edit menu, toolbar, new columns, `_fill_form`, geometry-edit
      handling with size scaling, warnings)
- [ ] Update `README.md`, `examples/annotations.txt` and `AGENTS.md`
- [ ] Run through the `## Verification` section
