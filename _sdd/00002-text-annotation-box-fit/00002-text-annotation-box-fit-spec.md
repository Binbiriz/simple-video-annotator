# Spec for text-annotation-box-fit

branch: opencode/feature/text-annotation-box-fit

## Summary

A text annotation currently only has a start position (`x`, `y`) and is drawn at
a fixed font size, so long text can run past the edge of the video or over
things it should not cover. Give every text annotation a bounding box by adding
a width and height, in the same way a blur annotation has one. The rendered text
must stay inside that box: the font size is calculated automatically so the text
fits, and text that already fits is drawn at the normal (maximum) size. Text is
drawn in a monospace font (Ubuntu Mono is the preferred choice) so that the
width of the text is predictable and the fitting calculation is simple and
consistent between the app preview and the renderer.

Proposed line shape:

- Text: `text|start|end|x|y|w|h|text`
- Blur: `blur|start|end|x|y|w|h` (unchanged)

Both the GUI (drawing, preview, saving, loading) and the command-line renderer
must support the new shape so that a file saved by the app can be rendered
directly.

## Functional Requirements

- A text annotation has `x`, `y`, `w` and `h` (whole numbers, video pixels) that
  define the box the text must fit in, with `x`/`y` as the top-left corner.
- The text line format becomes `text|start|end|x|y|w|h|text`; the text is still
  the remainder of the line and may contain spaces and `|`.
- In the app, creating a text annotation lets the user define the box by
  dragging a rectangle (as for blur) and then typing the text.
- The font size is calculated so the text fits inside the box. Text that fits at
  the default size keeps the default size and is not enlarged to fill the box.
- Long text wraps onto multiple lines inside the box width where needed, and the
  font size is reduced until the wrapped text also fits the box height.
- A readable minimum font size applies; if the text cannot fit even at that
  size, behaviour is defined (see edge cases) rather than silently overflowing
  beyond the video.
- Text is rendered in a monospace font, preferring Ubuntu Mono, with a fallback
  to another available monospace font if Ubuntu Mono is not installed.
- The same fitting result (font size and line breaks) is produced in the app's
  preview and in the rendered video, as closely as possible.
- Saving writes the new text line shape; the header comment lines describing the
  format are updated accordingly.
- Loading and the command-line renderer understand the new text line shape. Old
  text lines without `w`/`h` (`text|start|end|x|y|text`) are no longer supported
  and are reported as malformed lines with a clear reason.
- Existing text annotations shown in the app can be edited, including resizing
  the box, and the fit is recalculated.
- The README and the example annotation file describe and use the new format.

## Possible Edge Cases

- Very short text in a large box: stays at the default size, not scaled up.
- Very long text in a small box: reduced to the minimum size and, if still too
  large, handled according to the chosen overflow behaviour.
- Single long word with no spaces wider than the box: needs breaking or size
  reduction instead of overflowing.
- Text containing `|`, multiple spaces, or non-ASCII characters (accented and
  Turkish letters): must be preserved and measured correctly.
- Explicit line breaks in the text, if the format supports them.
- Zero or negative `w`/`h`, or a box that extends beyond the video frame, are
  rejected or clamped with a clear message.
- Ubuntu Mono is not installed on the machine: fallback monospace font is used
  and a warning is shown rather than failing.
- Old-format text lines (without `w`/`h`) are reported as malformed and not
  misinterpreted as a different field layout.
- Blur lines are not affected by this change.
- Windows line endings and whitespace around fields in hand-edited files.

## Acceptance Criteria

- A text annotation saved by the app contains `x`, `y`, `w` and `h` and can be
  loaded again with identical values.
- Text that is too long for its box is rendered in the output video entirely
  within the box, with a smaller font size and/or wrapping.
- Text that fits is rendered at the default size.
- Rendered text uses a monospace font (Ubuntu Mono when available).
- The preview in the app and the rendered video fit the text in the same way.
- Old-format text lines are rejected with a clear message in both the app and
  the renderer.
- Blur annotations continue to save, load and render unchanged.
- Existing automated tests are updated or extended to cover the new format, fit
  calculation, rejection of old-format lines and text containing `|`, and they
  pass.
- Documentation and the example annotation file reflect the new format.

## Open Questions

- What should the field order be for the text line? Proposed:
  `text|start|end|x|y|w|h|text`, keeping the free-form text last. ANSWER:
  'text|start|end|x|y|w|h|text'
- Should long text wrap onto multiple lines inside the box, or stay on a single
  line and only shrink the font? ANSWER: There is height available, so should be
  wrapped.
- What are the default (maximum) and minimum font sizes, and is the default
  fixed in video pixels or relative to the video height? ANSWER: 14px default, 8
  px minimum, fixed in video pixels.
- If the text does not fit even at the minimum size, should it be clipped,
  allowed to overflow, or should the annotation be rejected/warned about?
  ANSWER: Warn but still render at the minimum size, with a warning in the log.
- Should the user be able to choose the font, or is Ubuntu Mono (with a
  monospace fallback) fixed for all text? ANSWER: won't select now. Ubuntu mono
  with a fallback is fine.
- Is backward compatibility with old text lines (without `w`/`h`) needed?
  Proposed: no, consistent with the previous format change. ANSWER: No need for
  backward compat yet.
- Should the box also control alignment (left/center) of the text inside it?
  ANSWER: always left-aligned for now, no alignment control.
