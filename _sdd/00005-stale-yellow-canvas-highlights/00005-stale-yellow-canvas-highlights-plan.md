# Plan: stale-yellow-canvas-highlights

## Context

Spec:
`_sdd/00005-stale-yellow-canvas-highlights/00005-stale-yellow-canvas-highlights-spec.md`

Current behaviour (`src/vidnote/video_view.py`, `src/vidnote/main_window.py`):

- The "new" marker is the `_rubber` rectangle / `_rubber_line` of the view. The
  view shows it on press, on drag and on release, and hides it only in
  `set_mode`, `_cancel_drag` (tool change) and `set_selected`. Nothing clears it
  when the main window edits the x/y/w/h/x2/y2 spins, opens a video, deletes or
  loads annotations, and a plain click marker never goes away on its own.
- The "selected" highlight (`_selection`, `_sel_line`, `_handles`) is drawn from
  the stored geometry of the selected row, whatever the playhead is. The form
  spins do not move it. `_on_row_selected` returns early when no row is
  selected, so clearing the list selection (and `load_annotations`, which keeps
  the selected row index when the new list is long enough) can leave a highlight
  behind. In draw mode the press hides the highlight but the release never shows
  it again.
- The view uses the default viewport update mode (smart/minimal updates), so
  cosmetic pens and `ItemIgnoresTransformations` handles that move or hide can
  leave pixel trails.

What changes, following the spec and its answered Open Questions:

- The "new" marker becomes a state owned by the main window and derived from the
  form: it exists only after a pick, always shows the current spin values (moves
  when they change), and is cleared by every event listed in the spec. A plain
  click marker clears itself after 1 second.
- The "selected" highlight is shown for the selected row even when the row is
  not active at the playhead, but then dimmer and dashed. It follows the live
  form geometry (when the form edits the same kind and no new marker is active),
  and is cleared whenever the selection goes away.
- The view repaints the whole viewport on every change.
- The state rules go into a new Qt-free module so they can be tested without a
  display.
- No change to the annotation format; `scripts/annotate.sh`, `exporter.py`,
  `models.py`, `textfit.py` and `arrowgeom.py` are untouched.

Design decisions made in this plan (not covered by the spec):

- The marker stays visible while "Hide preview" is on (it is feedback for a
  pick, not a preview of an annotation); the highlight and handles are still
  hidden by it.
- Seeking or playing does not clear the marker: it describes the form, not a
  time.
- Escape cancels a draw drag in progress (after cancelling no marker remains).
- When the form's kind differs from the selected row's kind, or the form
  geometry is degenerate (box with w or h <= 0, arrow with identical points),
  the highlight keeps the stored geometry.
- While a marker is active the highlight keeps the stored geometry of the
  selected row (the form then describes the new pick, not the row).

## Files to Modify

### 1. `src/vidnote/canvasstate.py` (new, no Qt imports)

Pure rules for the two yellow graphics.

```python
POINT, REGION, LINE = "point", "region", "line"
POINT_MARKER_PX = 12      # side of the click marker square, video px
POINT_MARKER_MS = 1000    # a click marker disappears after this long

class FormGeometry(NamedTuple):
    x: int; y: int; w: int; h: int; x2: int; y2: int

class MarkerState:
    kind: Optional[str] = None          # None = no marker
    def pick(self, kind: str) -> None   # POINT, REGION or LINE; ValueError otherwise
    def clear(self) -> None
    def expire_point(self) -> bool      # clears only a POINT marker; True if it cleared
    @property
    def active(self) -> bool
    def shape(self, form: FormGeometry) -> Optional[Tuple[str, Tuple[float, ...]]]
```

`MarkerState.shape` returns what the view must draw for the current form values:

- no marker: `None`
- `POINT`: `("rect", (x - 6, y - 6, 12, 12))`
- `REGION`: `("rect", (x, y, w, h))`, or `None` when `w <= 0` or `h <= 0`
- `LINE`: `("line", (x, y, x2, y2))`

```python
def selection_geometry(stored: Annotation, form_kind: str, form: FormGeometry,
                       marker_active: bool) -> Tuple[int, ...]:
    """(x, y, w, h) for a box, (x1, y1, x2, y2) for an arrow."""
```

Uses the form values only when `form_kind == stored.kind`, no marker is active
and the form geometry is valid (box: `w > 0 and h > 0`; arrow: points differ);
otherwise the stored geometry.

```python
def selection_dimmed(stored: Annotation, t: float) -> bool:
    return not stored.is_active(t)
```

### 2. `src/vidnote/video_view.py`

- Constructor:
  `self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)`
  (spec: redraw the whole canvas on every change). Add the `_sel_dim` flag.
- New signal `dragStarted = Signal()`, emitted in `mousePressEvent` in draw mode
  right after `_drag_start` is set, so the main window can drop the previous
  marker.
- Marker API, replacing the view-owned marker behaviour:
  - `set_marker(shape: Optional[Tuple[str, Tuple[float, ...]]])`: `None` hides
    `_rubber` and `_rubber_line`; `("rect", (x, y, w, h))` sets `_rubber` and
    hides the line; `("line", (x1, y1, x2, y2))` sets `_rubber_line` and hides
    the rectangle.
  - `_draw_release` no longer calls `_show_rubber` / shows `_rubber_line` for
    the final result; it hides both items and only emits `regionSelected` /
    `lineSelected`. The main window draws the marker from the form in its slot.
    During the drag the live rubber band is unchanged.
- `_cancel_drag()` ends with `self._refresh_selection_items()` so a cancelled
  drag restores the highlight that the press hid. `_draw_release` also calls
  `_refresh_selection_items()` once `_drag_start` is `None` (today the highlight
  stays hidden after a draw-mode drag).
- `keyPressEvent`: Escape calls `_cancel_drag()` (and accepts the event) when a
  drag is in progress; other keys go to `super()`.
- `set_selected(index, rect, arrow=None)`: stop hiding `_rubber` /
  `_rubber_line` (the marker is now cleared explicitly by the main window); keep
  `self._edit = None`.
- Dimmed style:
  - `set_selection_dim(dim: bool)`: stores `_sel_dim` and calls
    `_refresh_selection_items()` when it changed.
  - `_refresh_selection_items()` applies the style: active = current solid
    `#ffd400` 2 px pen, fill alpha 40, handles opacity 1.0; dimmed = dashed pen
    (`_cosmetic_pen(..., dashed=True)`) with alpha about 120 on the colour, fill
    alpha about 15, handles `setOpacity(0.5)`. Use two prebuilt pens/brushes so
    no objects are created per refresh.
  - Hit testing (`_hit_handle`, `_selection_contains`) stays unchanged so a
    dimmed selection can still be moved and resized.
- `set_overlays_visible` unchanged (it already calls
  `_refresh_selection_items`).

### 3. `src/vidnote/main_window.py`

State and helpers:

- Import `QRectF` (already), `canvasstate`, and `QTimer` (already). In
  `__init__`, before `_build_ui()` (because `_on_kind_changed` runs at the end
  of `__init__`): `self._marker = canvasstate.MarkerState()` and
  `self._marker_timer = QTimer(self)` with `setSingleShot(True)`,
  `setInterval(canvasstate.POINT_MARKER_MS)` and `timeout` connected to
  `_on_marker_timeout`.
- `_form_geometry() -> canvasstate.FormGeometry` from the six spins.
- `_show_marker()`:
  `self.view.set_marker(self._marker.shape(self._form_geometry()))`.
- `_clear_marker()`: `self._marker.clear()`, `self._marker_timer.stop()`,
  `self.view.set_marker(None)`, then `_sync_selection_highlight()` (the
  highlight may go back to following the form).
- `_on_marker_timeout()`:
  `if self._marker.expire_point(): self._clear_marker()`.
- `_sync_selection_highlight()`: with `row = self._selected_row()`; if `None` or
  out of range, `self.view.set_selected(None, None)`; else compute
  `canvasstate.selection_geometry(a, self._kind(), self._form_geometry(), self._marker.active)`
  and call `view.set_selected(row, QRectF(*geom), None)` for boxes or
  `view.set_selected(row, None, arrow=geom)` for arrows, then
  `_sync_selection_dim()`.
- `_sync_selection_dim()`:
  `self.view.set_selection_dim(canvasstate.selection_dimmed(a, self.player.position() / 1000.0))`
  for the selected row (nothing when there is none).
- Replace the body of `_select_in_view(row)` and `_sync_view_selection()` so
  both go through `_sync_selection_highlight()`.

Wiring:

- `_connect()`: connect `view.dragStarted` to `_clear_marker`; connect
  `valueChanged` of `x_spin`, `y_spin`, `w_spin`, `h_spin`, `x2_spin`, `y2_spin`
  to `_on_geometry_field_changed`; replace
  `self.select_action.toggled.connect(self.view.set_mode)` (in `_build_actions`)
  with `self._on_mode_toggled`.
- `_on_geometry_field_changed()`: `_show_marker()` when the marker is active
  (the marker moves with the form), then `_sync_selection_highlight()` so the
  highlight follows the form (or stays on the stored geometry while a marker is
  active).
- `_on_mode_toggled(select: bool)`: `self._clear_marker()` then
  `self.view.set_mode(select)`.
- `_on_region(x, y, w, h)`: set the spins as today, then
  `self._marker.pick(REGION if w > 0 and h > 0 and self._kind() != ARROW else POINT)`;
  `_show_marker()`; for `POINT` start `self._marker_timer` (restart if running)
  else stop it. The marker must be picked before the spins are set so the spin
  handler already redraws it, or `_show_marker()` is called after; either way
  the final call uses the final spin values.
- `_on_line(...)`: set the spins, `self._marker.pick(LINE)`, stop the timer,
  `_show_marker()`.
- `_on_kind_changed()`: call `self._clear_marker()` before
  `self.view.set_draw_line(is_arrow)`.
- `_refresh_table()`: call `self._clear_marker()` at the start (add, update,
  delete, load, canvas geometry/arrow edits all go through it). Its existing
  `_sync_view_selection()` / `_update_overlays()` calls stay.
- `_on_row_selected()`: when `row is None or row >= len(self.annotations)`, call
  `self.view.set_selected(None, None)` and return; otherwise call
  `_clear_marker()` before `_fill_form(a)` (so the spin signals do not redraw a
  marker), keep the unhide logic, then `_select_in_view(row)`.
- `_update_overlays()`: at the end call `_sync_selection_dim()` (runs on every
  position change, and `set_selection_dim` is a no-op when nothing changed).
- `open_video()`: after `setSource`, call `self._clear_marker()` and
  `self.table.clearSelection()` (this clears the highlight through
  `_on_row_selected`); the new video's size is applied by `_on_native_size`.
- `delete_annotation()`: after `_refresh_table(...)`, if a neighbour row ends up
  selected, `self._fill_form(self.annotations[new_row])` so the form (and
  therefore the highlight that follows it) describes the newly selected row,
  including a neighbour of another kind.
- `load_annotations()`: call `self.table.clearSelection()` before
  `_refresh_table()` so no stale selection survives the reload.

### 4. `tests/test_canvasstate.py` (new)

No Qt needed. Cover:

- `MarkerState`: no marker -> `shape` is `None`; `pick(POINT)` -> 12x12 square
  centred on x,y that follows changed form values; `pick(REGION)` follows
  x,y,w,h and is `None` when w or h is 0; `pick(LINE)` follows the four
  coordinates; `clear()` -> `None`; `pick` with an unknown kind raises
  `ValueError`.
- `expire_point()`: clears and returns `True` for a point; leaves a region or
  line marker alone and returns `False`; returns `False` with no marker. A
  region picked after a click survives the click's expiry.
- `selection_geometry`: box and arrow with form equal to stored; form differing
  (same kind) -> form values; kind mismatch -> stored; marker active -> stored;
  degenerate form (w == 0, identical arrow points) -> stored.
- `selection_dimmed`: false inside `[start, end]` including both bounds, true
  before start and after end.

### 5. `README.md`

In "Using the app" (items 1 and 6/7), add short notes: the yellow marker follows
the position/size fields and a click marker disappears after about a second; the
selected annotation is highlighted with a solid outline while active at the
current time and a dimmer dashed one otherwise (still editable); Escape cancels
a drag in progress.

### 6. `AGENTS.md`

Architecture section: add `canvasstate.py` to the list of modules without Qt
imports and describe it in one line (marker and selection-highlight rules);
mention that the view's marker is driven by `set_marker` from the main window.

## Out of Scope

- The annotation file format, `scripts/annotate.sh`, `exporter.py`, `models.py`,
  `textfit.py`, `arrowgeom.py` (no sync needed).
- The look of blur boxes, text boxes, arrows, the red "text does not fit"
  outline and the preview of unsaved style changes.
- Clearing the marker on seek or playback, or hiding it with "Hide preview".
- Clearing the annotation list when a new video is opened.
- Automated tests that need a display (the Qt wiring is checked manually below).

## Verification

Automated: `pytest` and `ruff check src tests` pass (existing tests unchanged).

Manual (`./run.sh some.mp4`; optionally also offscreen with
`QT_QPA_PLATFORM=offscreen` for a smoke check that the window builds and the new
signals connect):

1. Draw mode: drag a region. The yellow rectangle matches X/Y/W/H. Change X, Y,
   W or H in the form: the rectangle moves/resizes with the values. Repeat with
   the arrow tool and X, Y, X2, Y2.
2. Plain click: a small square appears and disappears after about 1 second.
   Click, then drag a region within a second: the square is gone and the region
   marker stays (no later removal).
3. After a pick, each of these removes the marker: Add, Update selected, Delete
   selected, Load annotations, opening another video, changing Type
   (Text/Blur/Arrow), toggling Select, selecting a list row, picking an
   annotation on the canvas.
4. Draw mode, start dragging and press Escape (and, separately, release outside
   the window): no yellow rectangle or line remains; a selected row's highlight
   is back after the drag.
5. Select a row that is not active at the playhead: a dimmer dashed highlight
   with faded handles stays and can still be moved or resized on the canvas.
   Play or seek through its time range: it turns solid while active and dashed
   again after. Edit its start/end so it is no longer active at the playhead: it
   turns dashed immediately on the next position update or seek.
6. With a row selected, change X/Y/W/H (or arrow points) in the form: the
   highlight and handles follow. Change Type with a row selected: the highlight
   stays on the stored geometry.
7. Delete the selected row (also when the neighbour is of a different kind, and
   the last remaining one), load a file while a row is selected, and click empty
   list space to deselect: no highlight or handle is left. Deleting a row moves
   the selection to the neighbour and the form shows its values.
8. Hide preview on: highlight and handles are hidden; pick a point (the marker
   still shows); toggle it off or select a row: only valid items come back.
9. Drag a handle during playback, hide/show the preview and resize the window:
   no pixel trails or partial yellow remnants. Zoom (resize the window to very
   small and very large): outline and handles stay crisp with no leftovers.
10. Open a second video of a different size with a marker and a highlight
    visible: the canvas starts clean (no marker, no highlight, no selected row).
11. Render with `./scripts/annotate.sh` or the app: output is unchanged.

## Task List

- [ ] Create `src/vidnote/canvasstate.py` (`MarkerState`, `FormGeometry`,
      `selection_geometry`, `selection_dimmed`, constants)
- [ ] Create `tests/test_canvasstate.py` and run
      `pytest tests/test_canvasstate.py`
- [ ] `video_view.py`: full viewport update mode, `dragStarted` signal,
      `set_marker`, release no longer draws the final marker, refresh selection
      after cancel/release, Escape cancels a drag
- [ ] `video_view.py`: `set_selected` stops hiding the marker; dimmed/dashed
      selection style with `set_selection_dim`
- [ ] `main_window.py`: marker state, timer and helpers (`_form_geometry`,
      `_show_marker`, `_clear_marker`, `_on_marker_timeout`)
- [ ] `main_window.py`: selection helpers (`_sync_selection_highlight`,
      `_sync_selection_dim`) and rewire `_select_in_view` /
      `_sync_view_selection`
- [ ] `main_window.py`: wire signals (`dragStarted`, coordinate spins, mode
      toggle) and update `_on_region`, `_on_line`, `_on_kind_changed`,
      `_on_row_selected`, `_update_overlays`
- [ ] `main_window.py`: clear state in `_refresh_table`, `open_video`,
      `delete_annotation` (refill form), `load_annotations`
- [ ] Update `README.md` and `AGENTS.md`
- [ ] Run `pytest` and `ruff check src tests`
- [ ] Run through the `## Verification` steps
