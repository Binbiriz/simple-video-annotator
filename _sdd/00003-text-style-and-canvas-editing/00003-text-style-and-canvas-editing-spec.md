# Spec for text-style-and-canvas-editing

branch: opencode/feature/text-style-and-canvas-editing

## Summary

Text annotations are currently drawn white on a fixed semi-transparent black
box, with the font size calculated automatically so the text fits the box. This
feature gives the user manual control over how a text annotation looks and makes
annotations editable directly on the video canvas.

The user can choose the font size of each text annotation (no more automatic
scaling), choose the colour of the text box from a small user-editable list of
colours, and choose the text colour (black or white only). The canvas shows an
accurate preview of the text with its chosen size and colours so the size can be
adjusted by eye. A selector mode lets the user click an existing annotation on
the canvas, drag it to a new place and resize it. A button clears the preview
items from the canvas without deleting any annotation.

Because the annotation file is read by both the app and `scripts/annotate.sh`,
the text line gains new fields for font size, box colour and text colour, and
both implementations must support them.

## Functional Requirements

### Font size

- Every text annotation has its own font size, in video pixels, chosen by the
  user and saved in the annotation file.
- The automatic fit (shrinking the font until the text fits the box) is removed.
  The text is drawn at exactly the chosen size.
- Text still wraps onto multiple lines inside the box width, using the chosen
  size.
- If the wrapped text is taller than the box, the user is warned (in the app and
  in the renderer's log) but the text is still drawn at the chosen size.
- The app offers a way to set the size when creating a text annotation and when
  editing an existing one, with a sensible default.
- The canvas preview draws the text at the chosen size so the user can judge it
  before saving or rendering, and updates when the size is changed.

### Text box colour and the colour config

- The user can choose the background colour of the text box for each text
  annotation from a list of named colours.
- The colour list is defined in a simple config section the user can edit. Each
  entry is one line in the form `hex|label` (for example `#000000|Black`).
- The user can add, remove and edit entries of the list from the app; the list
  is saved and restored between sessions.
- A default list is provided the first time (including the current black box
  look) so the feature works without any configuration.
- Entries with an invalid hex value or a missing label are reported and skipped
  rather than breaking the list.
- Each text annotation stores the chosen box colour as a hex value in the
  annotation file, so the file renders correctly without the config.
- The box opacity stays as it is today unless a colour entry specifies otherwise
  (see open questions).

### Text colour

- The user can choose the text colour for each text annotation, limited to black
  or white.
- The chosen text colour is saved in the annotation file and used by the preview
  and the renderer.

### Annotation file format

- The text line gains fields for font size, box colour and text colour. Proposed
  shape: `text|start|end|x|y|w|h|size|boxcolor|textcolor|text`, with the
  free-form text still last and allowed to contain spaces and `|`.
- Blur lines are unchanged.
- Saving writes the new shape and updates the header comment lines describing
  the format.
- Loading and `scripts/annotate.sh` understand the new shape and produce the
  same look in the rendered video as in the canvas preview.
- Old text lines (without the new fields) are no longer supported and are
  reported as malformed with a clear reason, consistent with earlier format
  changes.
- The README and `examples/annotations.txt` describe and use the new format.

### Selector and editing on the canvas

- A selector tool (a toolbar button or mode) lets the user click an annotation
  shown on the canvas to select it. The selected annotation is clearly
  highlighted.
- A selected annotation can be dragged to a new position. The new `x`/`y` are
  stored in whole video pixels.
- A selected annotation can be resized by dragging handles on its box. The new
  `w`/`h` are stored in whole video pixels. This applies to both text and blur
  annotations.
- Moving and resizing keep the annotation inside the video frame.
- Changes made on the canvas update the annotation list and the data that will
  be saved, and the text preview is redrawn for the new box.
- The user can leave selector mode and return to drawing new annotations without
  losing the current selection or data.
- The selected annotation and the matching list entry stay in sync: selecting
  one selects the other.

### Clear canvas

- A button clears all annotation preview items from the canvas (rectangles, text
  previews, selection) in one action.
- Clearing the canvas does not delete, change or unsave any annotation; the
  annotation list and file contents are untouched.
- The user can bring the preview items back (for example by selecting an
  annotation in the list or through the normal time-based display) so clearing
  is not a one-way action.

## Possible Edge Cases

- Font size very large or very small, zero or negative: rejected or clamped with
  a clear message.
- Chosen size makes the text taller than the box or a single word wider than the
  box: warn, still draw at the chosen size, and make sure it does not break the
  render.
- A colour used by an annotation is later removed from the config list: the
  annotation keeps its stored hex value and still renders.
- Colour config contains duplicates, invalid hex (`#GGG`, wrong length), a
  missing `|`, empty labels, or labels containing `|`.
- Hex values written with or without `#`, or in uppercase/lowercase, are handled
  consistently.
- Text and box colour the same (for example black on black): allowed but may be
  warned about.
- Overlapping annotations at the same point: clicking selects a predictable one
  (for example the topmost), and there is a way to select the others.
- Dragging or resizing past the video edge, or resizing below a minimum size.
- Resizing a text box smaller than one line of text at the chosen size.
- Switching between selector and drawing modes while an annotation is selected
  or being drawn.
- Annotations that are only visible during part of the timeline: selecting or
  editing is possible for the ones the user can see, and the behaviour for
  annotations not active at the current time is defined.
- Clearing the canvas when nothing is shown, or while an annotation is being
  drawn or edited.
- Text containing `|`, accented and Turkish characters, and Windows line endings
  continue to round-trip.
- Blur annotations keep saving, loading and rendering unchanged.

## Acceptance Criteria

- Each text annotation can have its own font size, and the rendered text uses
  exactly that size with no automatic scaling.
- The canvas preview shows text at the chosen size and colours, and matches the
  rendered video closely.
- The user can pick the text box colour from a list, and edit that list in a
  simple config section using `hex|label` lines; the list persists between
  sessions.
- The user can pick black or white for the text colour and nothing else.
- A file saved by the app contains the font size, box colour and text colour,
  and loads again with identical values.
- `scripts/annotate.sh` renders the new text line shape with the chosen size and
  colours, and rejects old-format text lines with a clear message in both the
  app and the renderer.
- With the selector tool, the user can select any annotation on the canvas, drag
  it to a new place and resize it, and the changes are reflected in the list and
  in the saved file.
- A clear-canvas button removes all preview items from the canvas without
  deleting any annotation, and the annotations are still listed and saved.
- Blur annotations continue to work, and can also be moved and resized with the
  selector.
- Existing automated tests are updated or extended to cover the new format,
  rejection of old-format lines, colour config parsing and validation, and the
  absence of auto-fit, and they pass.
- Documentation and the example annotation file reflect the new format.

## Open Questions

- What should the default font size be, and what range is allowed? Previously
  the default was 14 px and the minimum 8 px. ANSWER: range is 8-72 px, default
  is 14 px.
- Should the box opacity stay fixed at the current 50% or be configurable, for
  example as an alpha part of the hex value or per colour entry? ANSWER: fixed
  for now.
- Where should the colour config live: a section inside the app (settings
  dialog) stored in the user's app settings, a plain text file next to the
  annotation file, or both? ANSWER: user app settings for now, with a simple
  text file as a future option.
- Is the `hex|label` list global for the app, or specific to each annotation
  file? ANSWER: global.
- Should the field order be
  `text|start|end|x|y|w|h|size|boxcolor|textcolor|text`, and should colours be
  stored as hex values (for example `#000000`) in the file? ANSWER: ok and hex
  values.
- Should the font size be changed only through a number input, or also by
  dragging on the canvas (for example scaling with the box)? ANSWER: scale it
  but also allow number input.
- When the user resizes a text box on the canvas, should the font size stay
  fixed (default assumption) or should there be an option to scale it? ANSWER:
  scale it but also allow number input.
- Should the clear-canvas action be a toggle (hide/show preview items) or a
  one-time clear that is undone by selecting or reloading? ANSWER: hide and
  show.
- Should selector mode be a separate toolbar tool or should clicking an existing
  annotation always select it while drawing new ones needs another action?
  ANSWER: toolbar button for selector mode, and clicking an existing annotation
  selects it only in that mode.
- Should annotations that are not active at the current video time be selectable
  on the canvas, or only through the list? ANSWER: only through the list.
- Is backward compatibility with old text lines needed? Proposed: no, consistent
  with earlier format changes. ANSWER: no need for backward compatibility.
