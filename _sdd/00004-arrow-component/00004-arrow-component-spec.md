# Spec for arrow-component

branch: opencode/feature/arrow-component

## Summary

Besides text and blur annotations, the user can add an arrow annotation that
points at something in the video. An arrow goes from a start point to an end
point, is shown for a time range like the other annotations, and is drawn on top
of the video in the rendered output.

For each arrow the user chooses the colour, the thickness, and the style of each
end (the start and the end can look different, for example a plain start and an
arrowhead at the end, or arrowheads on both ends).

Because the annotation file is read by both the app and `scripts/annotate.sh`,
the file format gains a new arrow line type, and both implementations must
support it and produce the same look as the canvas preview.

## Functional Requirements

### Drawing and editing arrows on the canvas

- The user can add an arrow by choosing an arrow tool and dragging on the video
  from the start point to the end point.
- The arrow's start and end points are stored in whole video pixels.
- Arrows have a time range (start and end seconds), set the same way as for text
  and blur annotations.
- Arrows appear in the annotation list with their time range and a short
  description, and can be edited and deleted like other annotations.
- In selector mode an arrow can be selected, and both of its end points can be
  dragged individually; the whole arrow can also be moved.
- Moving or editing keeps both end points inside the video frame.
- The canvas shows a preview of the arrow with its chosen colour, thickness and
  end styles, and updates when any of them is changed.

### Colour

- The user can choose the arrow colour for each arrow.
- The colour is chosen from the same user-editable box colour list used by text
  boxes, and is saved in the file as a hex value (`#rrggbb`) so the file renders
  without the app's colour list.

### Thickness

- The user can choose the line thickness of each arrow, in video pixels.
- A sensible default is provided and the allowed range is validated.
- Arrowheads scale with the thickness so they stay proportionate.

### End styles

- The start and the end each have their own style, chosen independently.
- Styles offered: none (plain line end), arrowhead, and at least one more simple
  marker such as a dot. The exact list is an open question.
- The default is no marker at the start and an arrowhead at the end.

### Annotation file format

- A new arrow line type is added. Proposed shape:
  `arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle`.
- Times are in seconds, coordinates are whole video pixels, the colour is
  `#rrggbb`, and styles are short lowercase names.
- Text and blur lines are unchanged.
- Saving writes arrow lines and updates the header comment lines describing the
  format.
- Loading and `scripts/annotate.sh` understand arrow lines and render the same
  look as the canvas preview.
- Malformed arrow lines (wrong number of fields, non-integer coordinates, bad
  colour, unknown style, out-of-range thickness) are reported with a clear
  reason in both the app and the renderer.
- The README and `examples/annotations.txt` describe and include arrow lines.

### Rendering

- `scripts/annotate.sh` draws each arrow only during its time range, with the
  chosen colour, thickness and end styles.
- Arrows are drawn in file order together with the other annotations, so the
  stacking order is predictable.
- The renderer needs no new runtime dependencies beyond what it already uses.

## Possible Edge Cases

- Start and end point identical (zero-length arrow): rejected, or drawn as a
  marker only, with a clear defined behaviour.
- Very short arrow with large thickness or large arrowheads, where the heads
  would overlap or exceed the line length.
- Arrows that are perfectly horizontal, vertical or diagonal, and arrows at any
  other angle, all draw cleanly.
- Thickness of zero, negative or too large: rejected or clamped with a message.
- Both ends set to "none", or both ends set to arrowheads.
- End points on or near the video edge, so the head or thickness would be partly
  clipped.
- Colour hex with or without `#`, uppercase or lowercase, handled consistently
  with text colours.
- Colour used by an arrow later removed from the colour list: the arrow keeps
  its stored hex value and still renders.
- Arrow drawn in the opposite direction to the usual drag (right-to-left,
  bottom-to-top): the start remains the point where the drag began.
- Overlapping arrows or arrows over text and blur boxes: selection picks a
  predictable one, and there is a way to select the others.
- Selecting a thin arrow with the mouse: the click area is large enough to hit
  reliably.
- Arrows only visible during part of the timeline: selectable through the list
  when not active at the current time, consistent with other annotations.
- The hide/show canvas preview action also covers arrows.
- Windows line endings and a `#` comment line near arrow lines keep
  round-tripping.
- Text and blur annotations keep saving, loading and rendering unchanged.

## Acceptance Criteria

- The user can add an arrow by dragging on the video and set its colour,
  thickness, start style and end style.
- The canvas preview shows the arrow with the chosen options and matches the
  rendered video closely.
- Arrows can be selected, moved and have their end points adjusted with the
  selector tool, and changes are reflected in the list and in the saved file.
- A file saved by the app contains arrow lines with all fields and loads again
  with identical values.
- `scripts/annotate.sh` renders arrow lines with the chosen colour, thickness
  and end styles, only during their time range.
- Malformed arrow lines are rejected with a clear message in both the app and
  the renderer.
- The hide/show canvas action affects arrows too, without deleting them.
- Text and blur annotations continue to work unchanged.
- Existing automated tests are extended to cover arrow parsing, writing,
  validation and rendering, and they pass.
- Documentation and the example annotation file reflect the new arrow line.

## Open Questions

- Which end styles should be offered? Proposed: none, arrowhead, dot (and
  possibly open arrowhead, bar or diamond). Answer: none and arrowhead only for
  now, with the others deferred to a future version.
- What default thickness and allowed range? Proposed: default 4 px, range 1-30
  px. Answer: 4 px, range 1-30 px.
- Should the arrow colour come from the existing box colour list, or from its
  own list or a free colour picker? Answer: the existing box colour list.
- Should the arrow have a fixed opacity (fully opaque proposed), or an
  adjustable one? Answer: 0.5 opacity fixed for now.
- Should the arrow be a straight line only, or also support curves? Answer:
  straight only.
- How should the renderer draw arrows without new dependencies: with ffmpeg
  filters only (for example rotated or drawn shapes), or by generating an
  overlay image? The choice affects how closely it can match the canvas preview.
  Answer: Option B: generate an overlay image - Something draws the arrow as a
  transparent PNG, and ffmpeg lays it on the video during the arrow's time
  range. - The arrow can then be smooth at any angle, with proper heads and
  dots, and it can match the app's preview almost exactly. - The catch is who
  draws the PNG. The app can do it (it has Qt), but annotate.sh is meant to work
  on its own from the text file, so it would need another tool such as
  ImageMagick or Python. That is the "new dependency" the question refers to.
- Should arrowhead size be derived from thickness only, or be a separate
  configurable value? Answer: derived from thickness.
- Should the arrow support an optional text label? Answer: no, use a separate
  text annotation.
