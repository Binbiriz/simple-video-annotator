# Plan: arrow-component

## Context

Spec: `_sdd/00004-arrow-component/00004-arrow-component-spec.md`

Today an annotation is either
`text|start|end|x|y|w|h|size|boxcolor|textcolor|text` or
`blur|start|end|x|y|w|h`. Both are rectangles: `Annotation` has `x, y, w, h`,
`VideoView` draws and edits rectangles with 8 handles, the form/table are built
around boxes, and `scripts/annotate.sh` builds a filter graph with one blur
stage per blur line and a single trailing `drawbox`/`drawtext` chain for all
text lines.

After this change there is a third kind, an arrow: a straight line from a start
point to an end point, shown for a time range, with a colour from the box colour
list, a thickness (1-30 px, default 4) and an independent style for each end
(`none` or `arrow`; default `none` at the start and `arrow` at the end). Per the
answered Open Questions:

- File line: `arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle`
  (times in seconds, whole video pixels, `#rrggbb`, styles lowercase). Text and
  blur lines are unchanged.
- Styles: `none` and `arrow` only (dot, bar, ... deferred).
- Fixed opacity 0.5 (like the text box background), straight line only, no
  label, arrowhead size derived from the thickness.
- The renderer draws each arrow as a transparent overlay image that ffmpeg lays
  over the video during the arrow's time range.

### Decisions beyond the spec text

- **Who draws the overlay image (resolves the "which tool" part of the renderer
  answer without a new dependency).** `annotate.sh` generates the overlay PNG
  with ffmpeg itself: a one-frame `color=...,format=rgba` source passed through
  the `geq` filter, whose alpha expression computes anti-aliased coverage of the
  arrow shape per pixel (verified in a prototype: smooth at any angle, proper
  heads, one PNG per arrow, no ImageMagick/Python needed). The PNG is added to
  the main ffmpeg command as `-loop 1 -i arrowN.png` and applied with
  `overlay=ox:oy:enable='between(t,s,e)':shortest=1`. `shortest=1` is needed so
  the looped image does not make the output infinite. The Qt preview draws the
  same geometry with `QPainterPath`.
- **Shared geometry.** Both implementations use the same formulas (pure module
  `arrowgeom.py`, mirrored in the `geq` expression; keep them in sync, like
  `textfit.py`/`annotate.sh`). With `t` = thickness:
  - head length `Lh0 = 4*t + 6`, head half-width `Hw0 = 2*t + 3` (integers);
  - `len` = distance start to end; `n` = number of `arrow` ends (at least 1 in
    the formula); scale `k = min(1, len / (n * Lh0))`, so the heads shrink on
    very short arrows and never overlap or exceed the line; `Lh = Lh0*k`,
    `Hw = Hw0*k`;
  - shaft: rectangle of width `t` along the axis from `u0` to `u1`, where
    `u0 = Lh - 1` if the start is `arrow` else `0`, and `u1 = len - Lh + 1` if
    the end is `arrow` else `len` (flat caps; the 1 px overlap hides the seam
    between shaft and head);
  - head: isosceles triangle with the tip at the end point, length `Lh`, base
    half-width `Hw`;
  - the whole arrow is **one shape** filled at alpha 0.5 (union via `max` of the
    coverages in `geq`, `QPainterPath.united` in Qt), so shaft and head never
    double-darken.
- **Pixel centres.** Point `(x, y)` is the continuous position `(x, y)` in the
  scene. In `geq` the pixel `(X, Y)` is evaluated at its centre `(X+0.5, Y+0.5)`
  so the video render lines up with the canvas.
- **Zero-length arrows are rejected** (`start and end points must differ`) in
  the app (`validate`), `exporter.parse_line` and `annotate.sh`. Canvas dragging
  cannot land one end exactly on the other (the edit is ignored).
- **Frame check.** Like text boxes, both end points must lie inside the video
  (`0 <= x <= width`, `0 <= y <= height`): enforced in the app
  (`_check_in_frame`, canvas clamping) and in `annotate.sh` (existing ffprobe
  check, message `arrow end point outside the WxH video`). Thick lines or heads
  near the edge are simply clipped by the frame.
- **Stacking order in the renderer is file order.** `annotate.sh` currently
  draws all blurs first and all text last. To honour "drawn in file order
  together with the other annotations", each text line becomes its own filter
  stage and every stage (blur, text, arrow) is chained in file order. The
  picture is identical to before except where a blur overlaps a text box that
  comes earlier in the file (the blur now covers it; before, text was always on
  top). The app writes files sorted by start time, as before.
- **Model.** `Annotation` gets `x2`, `y2`, `thickness`, `color`, `start_style`,
  `end_style` (all after the existing fields, with defaults, so positional calls
  keep working). For an arrow `x, y` is the start point and `w`/`h` stay 0.
- **List and form.** The list shows an arrow's start point in X/Y, its colour in
  the Box column (with swatch) and a description in the Text column, e.g.
  `to (300,150), 4 px, none>arrow`. The "arrow tool" is the form's Type combo:
  with `Arrow` selected, a drag on the video draws a line instead of a rectangle
  (the start stays where the drag began, also for right-to-left or bottom-to-top
  drags). The arrow colour uses the existing colour combo (its label becomes
  "Colour" for arrows).
- **Selection on the canvas.** An arrow is hit when the click is within
  `max(t/2, 8 screen px)` of the segment. Overlapping hits cycle exactly like
  boxes (topmost first, click again to cycle). A selected arrow shows a yellow
  line plus two handles (`p1` start, `p2` end) instead of the 8 box handles;
  dragging a handle moves that end point, dragging the line moves the whole
  arrow (clamped so both end points stay in the frame). Geometry is applied on
  mouse release, as for boxes, and the preview is rebuilt then.
- A pending (not yet added) arrow has no styled preview; the rubber-band line
  shows the dragged end points.

## Files to Modify

### 1. `src/vidnote/arrowgeom.py` (new, no Qt imports)

Pure geometry shared by the preview, the tests and (as a spec) `annotate.sh`.

```python
HEAD_LEN_K, HEAD_LEN_ADD = 4, 6        # Lh0 = 4*t + 6
HEAD_HALF_K, HEAD_HALF_ADD = 2, 3      # Hw0 = 2*t + 3
ALPHA = 0.5

@dataclass
class ArrowGeometry: ...                 # len, ux, uy, head_len, head_half, u0, u1, ...

def geometry(x1, y1, x2, y2, thickness, start_style, end_style) -> ArrowGeometry
def polygons(x1, y1, x2, y2, thickness, start_style, end_style) -> list[list[tuple[float, float]]]
    # shaft rectangle + 0..2 head triangles, scene coordinates
def coverage(px, py, x1, y1, x2, y2, thickness, start_style, end_style) -> float
    # 0..1 anti-aliased coverage at a continuous point; same formulas as the geq alpha
def distance_to_segment(px, py, x1, y1, x2, y2) -> float
def padding(thickness) -> int            # 2*t + 5, bbox padding used by annotate.sh
```

`geometry` raises `ValueError` for identical points. `coverage` is
`max(shaft, head_end, head_start)` with
`shaft = clip(min(u-u0+.5, u1-u+.5, t/2-v+.5), 0, 1)` and, for a head at
distance `s` from its tip,
`head = clip(min(s+.5, Lh-s+.5, (Hw*s/Lh - v)*Lh/hypot(Lh,Hw) + .5), 0, 1)` (`u`
along the axis from the start, `v` the perpendicular distance).

### 2. `src/vidnote/models.py`

- Add `ARROW = "arrow"`, `STYLE_NONE = "none"`, `STYLE_ARROW = "arrow"`,
  `ARROW_STYLES = (STYLE_NONE, STYLE_ARROW)`, `DEFAULT_THICKNESS = 4`,
  `MIN_THICKNESS = 1`, `MAX_THICKNESS = 30`, `DEFAULT_ARROW_COLOR = "#e03131"`,
  `DEFAULT_START_STYLE = STYLE_NONE`, `DEFAULT_END_STYLE = STYLE_ARROW`.
- `Annotation`: `kind` comment gains ARROW; new fields after `text_color`:
  `x2: int = 0`, `y2: int = 0` (arrow end point),
  `thickness: int = DEFAULT_THICKNESS`, `color: str = DEFAULT_ARROW_COLOR`,
  `start_style: str = DEFAULT_START_STYLE`,
  `end_style: str = DEFAULT_END_STYLE`.
- `validate()`: accept `ARROW` in the kind check; for arrows require
  `(x, y) != (x2, y2)` ("An arrow needs two different points: drag a line on the
  video."), `MIN_THICKNESS <= thickness <= MAX_THICKNESS` ("Thickness must be
  between 1 and 30 px."), a valid `color` via `colors.normalize_hex` ("Colour:
  ..."), and both styles in `ARROW_STYLES` ("Unknown end style ..."). The
  existing box/text checks stay under their `TEXT` guards.

### 3. `src/vidnote/exporter.py`

- Docstring and `HEADER` gain
  `# arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle` (after the
  blur line).
- `to_line`: `ARROW` branch writing
  `arrow|start|end|x|y|x2|y2|thickness|<normalize_hex(color)>|start_style|end_style`
  (times via `fmt_time`).
- `parse_line`: `arrow` branch: `parts = [p.strip() for p in line.split("|")]`,
  require 11 fields
  (`ValueError("arrow lines need: arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle")`);
  integers for x1, y1, x2, y2 and thickness (messages "x1, y1, x2 and y2 must be
  whole numbers", "thickness must be a whole number"); points must differ;
  thickness in 1-30; `colors.normalize_hex(color)`; styles lowercase and in
  `ARROW_STYLES` ("unknown end style 'x'; expected none or arrow"). Returns
  `Annotation(ARROW, s, e, x1, y1, x2=x2, y2=y2, thickness=..., color=..., start_style=..., end_style=...)`.
- Unknown-type message becomes
  `unknown line type; expected 'text|...', 'blur|...' or 'arrow|...' (old whitespace-separated lines are no longer supported)`.

### 4. `scripts/annotate.sh`

- Header comment: document the `arrow` line, its fields, ranges, colour at 50%
  opacity, the two styles, and that the geometry mirrors
  `src/vidnote/arrowgeom.py` (keep constants in sync). Update the "Render text
  and blur annotations" title.
- Constants next to the text ones: `MIN_THICK=1; MAX_THICK=30` and the head
  formulas `Lh0=4*t+6`, `Hw0=2*t+3`, `pad=Hw0+2` (= `arrowgeom.padding`).
- New `arrow` branch in the parse loop (before the final `die`; update the final
  message to `expected text|..., blur|... or arrow|...`):
  - `[ "${#pipes}" -eq 10 ] || die "arrow lines need: arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle"`;
    `pop_field` for each field; validate start/end numbers, `x1 y1 x2 y2` with
    `^-?[0-9]+$` and thickness `^[0-9]+$` (via `toint`), points differ,
    thickness range, colour `^#?[0-9a-fA-F]{6}$` (strip `#`, lowercase), each
    style lowercased and `none` or `arrow` (`die "unknown end style ..."`).
  - Record `arrows+=("x1:y1:x2:y2:t:color:ss:es")`, add
    `points+=("lineno:x1:y1:x2:y2")` for the frame check, increment `na`, and
    append the stage
    `[$cur][${input_index}:v]overlay=$ox:$oy:enable='between(t,$s,$e)':shortest=1[vN]`
    where `ox = min(x1,x2) - pad`, `oy = min(y1,y2) - pad`, input index = `na`
    (input 0 is the video).
- Restructure the graph building so every stage is chained in file order: the
  text branch now emits its own stage `[$cur]<drawbox,drawtext...>[tN]` instead
  of appending to `$texts`, and the final `[$cur]$texts[vout]` step is removed
  (`cur` is simply the label of the last stage). Blur stages are unchanged.
- The "No annotations found" check counts `nb + nt + na`.
- Frame check: extend the existing ffprobe check to the `points` array
  (`arrow end point outside the ${vw}x${vh} video`, `exit 1` with `file:line:`
  like the text-box message). Condition
  `|| [ ${#boxes[@]} -gt 0 ] || [ ${#points[@]} -gt 0 ]`.
- After the checks and before ffmpeg, render one PNG per arrow into `$tmp` (new
  function `render_arrow_png n`): bounding box `W = |x2-x1| + 2*pad + 1`,
  `H = |y2-y1| + 2*pad + 1`, local points `a = (x1-ox, y1-oy)`,
  `b = (x2-ox, y2-oy)`:

  ```bash
  ffmpeg -y -nostdin -loglevel error -f lavfi -i "color=c=0x$color:s=${W}x${H},format=rgba" \
    -frames:v 1 -vf "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='$expr'" "$tmp/arrow$n.png"
  ```

  `$expr` = `st(...)` assignments (only 10 `ld/st` slots exist in ffmpeg
  expressions, so only these are stored: 0 len, 1 ux, 2 uy, 3 u, 4 v, 5 k, 6 Lh,
  7 Hw; everything else is inlined as integer literals from bash) followed by
  `128*max(shaft, head_end, head_start)`, with `X+0.5`/`Y+0.5` as the pixel
  position and the head terms included only for ends with style `arrow`. Cap
  `128` is the fixed 0.5 opacity. Failure of this ffmpeg call: `die`-style
  message with the arrow's line number.

- The final ffmpeg command adds the PNG inputs:
  `inputs+=(-loop 1 -i "$tmp/arrow$n.png")` for each arrow, in order, before
  `-filter_complex`.
- Test hooks: none new; `VIDNOTE_PRINT_LAYOUT` keeps working (it exits before
  the arrow PNGs are made).

### 5. `src/vidnote/video_view.py`

- Imports: `QGraphicsLineItem`, `QGraphicsPathItem`, `QPainterPath`,
  `QPolygonF`; `arrowgeom`; `ARROW` from models.
- New signals: `lineSelected = Signal(int, int, int, int)` (draw mode, x1, y1,
  x2, y2 in whole video pixels) and
  `arrowEdited = Signal(int, int, int, int, int)` (index, x1, y1, x2, y2).
- Draw mode: `set_draw_line(enabled: bool)`; when on, the press creates a rubber
  `QGraphicsLineItem` (yellow, cosmetic) instead of the rubber rectangle, the
  move updates `QLineF(start, clamped current)` (no normalisation, so the start
  stays where the drag began), and `_draw_release` emits
  `lineSelected(round x1, y1, x2, y2)` when the drag is at least
  `CLICK_THRESHOLD_PX`, otherwise `regionSelected(x, y, 0, 0)` as today (sets
  the start only). `_cancel_drag`, `set_mode` and `set_selected` hide the rubber
  line too.
- Preview (`set_overlays`): `_overlay_boxes` becomes
  `_overlay_hits: List[Tuple[int, Annotation]]`; new `_add_arrow_overlay(a)`
  builds a `QPainterPath` from `arrowgeom.polygons(...)` (`addPolygon` per
  polygon, then `.simplified()` to get the union), fills it with the colour at
  alpha 128 (colour via `normalize_hex`, black on error), no pen,
  `setZValue(54)`, added through `_add_overlay_items` so hide/show covers it. A
  zero-length/invalid arrow adds nothing.
- Hit testing: `_boxes_at(scene_pos)` keeps its name and order but, for arrows,
  uses `arrowgeom.distance_to_segment(...) <= max(thickness / 2, 8 / scale)`
  with `scale = self.transform().m11()`; for boxes the existing rectangle test.
- Selection: new `_sel_arrow: Optional[Tuple[int, int, int, int]]`;
  `set_selected(index, rect, arrow=None)` (`rect` may be `None` when `arrow` is
  given). `_selection_visible()` is true when either is set.
  `_refresh_selection_items` shows, for an arrow, a yellow `QGraphicsLineItem`
  (cosmetic, width 2) and the two new handle items `p1`/`p2` (created like the
  others, kept in `_handles`) and hides the box highlight and the 8 box handles;
  for a box it hides the line and `p1`/`p2`. `_hit_handle` iterates
  `("p1", "p2")` for an arrow selection and `HANDLES` otherwise;
  `_HANDLE_CURSORS` gets `p1`/`p2` -> `SizeAllCursor`.
- Editing: `_begin_edit` stores `orig_arrow` too. `_select_press` treats a press
  within the hit distance of the selected arrow as "move". New
  `_edit_arrow(scene_pos)` returns the new points: `move` clamps `dx`/`dy` so
  both points stay in `[0, vw] x [0, vh]`; `p1`/`p2` clamp the dragged point to
  the frame and keep the original if it would equal the other point.
  `_edit_move` updates `_sel_arrow` and refreshes; `_edit_release` emits
  `arrowEdited` when the points changed (the click-without-drag cycling through
  `hits` is shared); `_cancel_drag` restores `_sel_arrow`.

### 6. `src/vidnote/main_window.py`

- Imports `ARROW`, `ARROW_STYLES`, `DEFAULT_*` arrow constants, `MIN_THICKNESS`,
  `MAX_THICKNESS`.
- Form: `kind_combo` items `["Text", "Blur", "Arrow"]` (index 2 = arrow; replace
  the `currentIndex() == 1` blur checks with a `_kind()` helper returning
  `TEXT`/`BLUR`/`ARROW`). New widgets: `x2_spin`, `y2_spin` ("End point" row,
  X/Y like Position), `thickness_spin` (1-30, suffix " px", default 4),
  `start_style_combo` and `end_style_combo` (items "None" -> `none`, "Arrowhead"
  -> `arrow`; defaults None / Arrowhead). `_on_kind_changed` enables/disables by
  kind (text controls only for text; W/H for text and blur; end point, thickness
  and style combos only for arrow; the colour combo for text and arrow,
  relabelled "Colour" for arrows, "Box colour" otherwise) and calls
  `view.set_draw_line(kind == ARROW)`. The hint label gains a line about arrows.
- `_connect`: `view.lineSelected -> _on_line`,
  `view.arrowEdited -> _on_arrow_edited`; `thickness_spin.valueChanged`,
  `start_style_combo`/`end_style_combo` `currentIndexChanged` ->
  `_update_overlays`.
- `_on_line(x1, y1, x2, y2)` fills X/Y and the end point spins. `_on_region` for
  the arrow kind sets only X/Y (a click).
- `_form_annotation`: builds an `ARROW` annotation (x/y/x2/y2, thickness,
  `color=box_combo.currentData() or DEFAULT_ARROW_COLOR`, styles from
  `currentData()`), w/h = 0, no text.
- `_check_in_frame`: for arrows both points must satisfy `0 <= x <= vw`,
  `0 <= y <= vh` ("The arrow extends beyond the video frame (WxH)."); text logic
  unchanged; blur still unchecked.
- `_update_overlays`: the selected arrow gets live form style via an extended
  `_with_form_style` (thickness, colour from the combo, styles) the same way
  text does.
- `_refresh_table`: arrow row cells: Type `arrow`, Start, End, X, Y = start
  point, W/H empty, Size `-`, Box = colour (with swatch), Color `-`, Text =
  `to (x2,y2), N px, none>arrow`. `COLUMN_TIPS["Box"]` becomes "Text box / arrow
  colour". Swatch condition covers `is_text or is_arrow`.
- `_sync_view_selection`, `_on_row_selected`: pass `arrow=(x, y, x2, y2)` to
  `view.set_selected` for arrows (with `rect=None`).
- `_fill_form`: arrow fields (end point, thickness, styles, colour via
  `_set_box_color(a.color)`) and the kind index 2.
- `_on_arrow_edited(index, x1, y1, x2, y2)`: update the annotation, refresh the
  table, refill the form (like `_on_geometry_edited`).
- `load_annotations` warning text lists the three accepted shapes. `edit_colors`
  and the status text "Text box colours..." stay (the menu entry can read "Box
  and arrow colours..."; update its status message too).

### 7. Tests

- `tests/test_arrowgeom.py` (new): `geometry` rejects identical points;
  `coverage` is ~1 inside the shaft and head, 0 well outside, ~0.5 at the edges;
  horizontal, vertical, diagonal and reversed (right-to-left) arrows are
  symmetric; `none`/`none` is a plain bar and `arrow`/`arrow` has a head at both
  ends; a very short arrow with a large thickness keeps `u0 <= u1` and heads
  within the line; `polygons` bounding box matches `coverage` support;
  `distance_to_segment` (inside, beyond the end, on the line).
- `tests/test_models.py`: arrow `validate()` passes for defaults; fails for
  identical points, thickness 0 and 31, bad colour and unknown style; text and
  blur validation unchanged.
- `tests/test_exporter.py`: arrow round trip (all fields, both style
  combinations, reversed drag, colour normalised to lowercase `#`), `dumps`
  writes the arrow line and the new header comment, `\r\n` and a `#` comment
  next to arrow lines, malformed arrow lines are skipped with a reason (wrong
  field count, non-integer coordinates, identical points, thickness 0/31, bad
  colour, unknown style), mixed file keeps text/blur values unchanged.
- `tests/test_annotate_sh.py`:
  - extend `_render` with an optional source (default `testsrc`); add a solid
    black source variant;
  - `test_render_arrow`: renders a text+blur+arrow file successfully; output
    duration equals the input duration (ffprobe), proving `shortest=1` works;
  - `test_arrow_is_drawn_only_in_its_time_range` and
    `test_arrow_pixels_match_geometry`: white arrow on a black video, extract
    frames inside and outside the range as raw gray and compare sample pixels
    with `arrowgeom.coverage(...) * 0.5 * 255` (tolerance about 20 for the h264
    round trip, points away from edges); horizontal, vertical, diagonal,
    reversed and `arrow`/`arrow` cases;
  - malformed arrow lines added to the parametrised
    `test_malformed_line_fails_with_line_number` (wrong field count, non-integer
    coordinates, identical points, thickness 0 and 31, bad colour, unknown
    style);
  - `test_arrow_end_point_beyond_frame_is_rejected`;
  - file-order stacking: a blur line after a text line is drawn without error
    (graph builds), plus existing text/blur tests pass unchanged.

### 8. Docs and example

- `examples/annotations.txt`: header comment and sample arrow lines (e.g. a red
  4 px arrowhead at the end, and a white 8 px arrow with heads at both ends).
- `README.md`: intro and Usage step 3/5 mention arrows (Type = Arrow, drag from
  the start point to the end point, thickness, end styles, colour from the list,
  fixed 50% opacity, selector mode end-point handles); the "Annotation file
  format" section gets the arrow line, field description and example; Rendering
  section notes the overlay-image approach (ffmpeg only, no new dependency) and
  the end-point frame check; Project layout lists `arrowgeom.py` and
  `test_arrowgeom.py`.
- `AGENTS.md`: add `arrowgeom.py` to the "no Qt imports" list, mention that
  `scripts/annotate.sh` mirrors it (like `textfit.py`), and add the arrow line
  to the format section
  (`arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle`, thickness
  1-30, styles `none`/`arrow`, 50% opacity).

## Out of Scope

- Other end styles (dot, open arrowhead, bar, diamond), curved arrows, an
  adjustable opacity, a text label on an arrow, a separate arrowhead size field.
- A free colour picker or separate arrow colour list.
- A styled live preview of an arrow that has not been added yet.
- Changing text or blur file syntax or their rendering look (only the stacking
  order of blur vs. earlier text lines follows file order now).
- Backward compatibility work for any older formats (none needed; arrow is new).

## Verification

1. `pytest` and `ruff check src tests` pass (the ffmpeg tests need ffmpeg; the
   drawtext ones skip without libfreetype).
2. `./run.sh <video>`: set Type to Arrow, drag right-to-left and bottom-to-top
   and confirm the rubber line starts where the drag began; click Add; the row
   shows start in X/Y, the colour swatch, and `to (x2,y2), N px, none>arrow`.
3. Change thickness, colour and both end styles with the row selected: the
   canvas arrow updates immediately; Update selected keeps the change; both
   `none` and both `arrowhead` look right.
4. Select mode: click the arrow (also a 1 px one), drag the start handle, the
   end handle, and the line itself; points stay inside the frame; click again on
   overlapping annotations cycles through them; arrows not active at the current
   time can be picked from the list and edited on the canvas.
5. Hide preview hides the arrow and its handles; selecting a row brings them
   back.
6. Save, reload: the file has an `arrow|...` line with all fields and the header
   comment, and loads with identical values; a file with a bad arrow line
   reports the reason in the skipped-lines dialog.
7. `./scripts/annotate.sh in.mp4 examples/annotations.txt out.mp4`: arrows
   appear only in their time range with the chosen colour, thickness and ends,
   at 50% opacity, matching the canvas preview closely; check horizontal,
   vertical, diagonal, a very short thick arrow, and one near the frame edge;
   stacking follows file order with text and blur; output length equals the
   input length.
8. Bad lines (identical points, thickness 0/31, bad colour, unknown style, wrong
   field count, end point outside the video) fail with `file:line:` messages.

## Task List

- [ ] Create `src/vidnote/arrowgeom.py` (geometry, polygons, coverage, distance,
      padding)
- [ ] Update `src/vidnote/models.py` (arrow constants, new `Annotation` fields,
      `validate()`)
- [ ] Update `src/vidnote/exporter.py` (docstring, `HEADER`, `to_line`,
      `parse_line`, unknown-type message)
- [ ] Update `scripts/annotate.sh` (header, arrow parsing and validation,
      file-order stages, frame check, geq PNG rendering, extra inputs,
      `shortest=1`)
- [ ] Update `src/vidnote/video_view.py` (line drawing, arrow preview, hit
      testing, arrow selection/handles/editing, new signals)
- [ ] Update `src/vidnote/main_window.py` (Arrow type, form fields, table row,
      in-frame check, live style preview, canvas signals, load warning text)
- [ ] Add `tests/test_arrowgeom.py` and extend `tests/test_models.py`,
      `tests/test_exporter.py`, `tests/test_annotate_sh.py`
- [ ] Update `examples/annotations.txt`, `README.md` and `AGENTS.md`
- [ ] Run `pytest` and `ruff check src tests`
- [ ] Run through the `## Verification` steps (GUI and `annotate.sh`)
