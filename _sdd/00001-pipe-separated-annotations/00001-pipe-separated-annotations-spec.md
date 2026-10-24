# Spec for pipe-separated-annotations

branch: opencode/feature/pipe-separated-annotations

## Summary

The annotation file currently separates values on a line with whitespace, which
forces the free-form text of a text annotation to be the trailing field and
makes lines awkward to read and edit by hand. Change the annotation file format
so that values on each line are separated by the `|` character. Both the GUI
(saving and loading) and the command-line renderer must read and write the new
format, so that a file saved by the app can be rendered directly and vice versa.

Proposed line shapes:

- Text: `text|start|end|x|y|text`
- Blur: `blur|start|end|x|y|w|h`

Comments (`#`) and blank lines keep working as before.

## Functional Requirements

- Saving an annotation file from the app writes every annotation line with `|`
  between values, including the header comment lines describing the format.
- Loading an annotation file in the app understands the new `|` format.
- The command-line renderer understands the same `|` format and produces the
  same output as before for equivalent annotations.
- Surrounding whitespace around values is ignored, so
  `text | 1 | 2 | 10 | 20 | Hello` is accepted.
- The text of a text annotation may contain spaces and any other characters, so
  it is taken as the remainder of the line after the fifth separator.
- The old whitespace-separated format (including lines with no leading `text`
  keyword) is no longer supported; such lines are reported as malformed. No
  backward compatibility is required.
- Text and blur `x`/`y` values are always whole numbers (video pixels) in both
  the app and the renderer. ffmpeg expressions for text `x`/`y` (e.g.
  `(w-text_w)/2`) are no longer supported by the renderer.
- Malformed lines are reported as skipped lines with a clear reason, as today.
- The README and the example annotation file describe and use the new format.

## Possible Edge Cases

- Text that itself contains `|` characters must be preserved intact (the text
  field is the remainder of the line).
- Text that is empty or only whitespace is still rejected.
- Lines with too few or too many fields for blur lines are reported as
  malformed.
- Non-numeric `x`/`y` values (including former ffmpeg expressions) are reported
  as malformed lines rather than passed to ffmpeg.
- A line in the old whitespace-separated format is reported as malformed and not
  misinterpreted.
- Leading and trailing spaces around the keyword and fields.
- Windows line endings in hand-edited files.

## Acceptance Criteria

- A file saved by the app uses `|` between all values and can be loaded again
  with identical annotations.
- The renderer renders a `|`-separated file with the same result the old format
  produced for equivalent annotations.
- The example annotation file is converted to the new format and loads in the
  app and renders with the renderer.
- Old-format lines are rejected with a clear message in both the app and the
  renderer.
- Text annotations containing `|` and spaces round-trip through save and load
  unchanged.
- Existing automated tests are updated or extended to cover the new format,
  rejection of old-format lines, and text containing `|`, and they pass.
- Documentation and the example annotation file reflect the new format.

## Open Questions

- Should the old whitespace-separated format remain readable indefinitely, or be
  dropped after a transition period? ANSWER: There is no need backward
  compatibility right now.
- Should the app always save in the new format, or offer a choice of format?
  ANSWER: Always save in the new format
- Should ffmpeg expressions for text x/y keep being supported in the renderer?
  ANSWER: No. Hand-written expressions are not used; x/y are always integers.
