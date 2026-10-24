# Spec for stale-yellow-canvas-highlights

branch: opencode/feature/stale-yellow-canvas-highlights

## Summary

The yellow helper graphics that the app draws on top of the video (the marker
for a newly picked point or region, and the highlight for the selected
annotation) sometimes stay on the canvas when they no longer mean anything. They
look like ghost residue: a yellow rectangle, line or handle squares that do not
match the current state, the current time, or any annotation the user is working
on. This is most visible in the preview while seeking or playing, switching
modes, deleting or loading annotations, and changing the form values.

The user wants the canvas to show a yellow helper graphic only while it reflects
something real, and to remove it as soon as it stops doing so.

Two kinds of yellow graphics are involved:

- The "new" marker: the small square for a clicked point, the rectangle for a
  dragged region, or the line for a dragged arrow, shown in draw mode after the
  user picks coordinates.
- The "selected" highlight: the rectangle or line, with its handles, drawn
  around the annotation selected in the list or on the canvas.

Likely causes seen while reading the current behaviour (to be confirmed while
reproducing):

- The "new" marker is only cleared by a few events (starting a new drag,
  changing mode or tool, selecting something, adding an annotation). It stays
  after the user edits the position or size fields, seeks the video, opens
  another video, deletes rows, loads a file, or clicks elsewhere, so it points
  at coordinates the form no longer holds.
- The "selected" highlight is drawn from the stored geometry of the selected row
  and stays visible when the playhead is outside that annotation's time range,
  while the annotation itself is not drawn. The highlight then floats over empty
  video and looks like residue.
- Edits made through the form fields do not move the highlight until the
  annotation is updated, so the highlight and the live preview can disagree.
- Partial repaints of the canvas may leave pixel trails of the yellow outlines
  and handles when they move or hide (for example while dragging a handle during
  playback), which only goes away after a full redraw such as a window resize.

## Functional Requirements

### The "new" marker

- The marker is shown only while it describes the coordinates currently in the
  position and size fields (or the arrow end points, for arrows).
- The marker is removed when:
  - the user changes any coordinate or size field so that it no longer matches,
    or the marker is redrawn to match the new values (see open questions);
  - an annotation is added, updated, deleted or loaded from a file;
  - a different video is opened;
  - the annotation kind or tool is changed;
  - the mode is switched between draw and select;
  - the user selects an annotation, in the list or on the canvas.
- A plain click still shows a short-lived point marker so the user sees what was
  picked.

### The "selected" highlight

- The highlight and handles are shown only while the selected annotation is
  meaningful on the canvas. Whether that means "only while active at the current
  time" or "always, but visibly different when inactive" is an open question.
- The highlight follows the live form values for the selected annotation in the
  same way the text and arrow previews already do, or is hidden while the form
  differs from the stored annotation.
- The highlight is removed when the selected row is deleted, when the list is
  reloaded from a file, and when the selection is cleared.
- Hiding the preview still hides the highlight and handles, and showing it again
  restores only what is still valid.

### Canvas redraw

- Moving, hiding or resizing any yellow graphic leaves no pixel trails on the
  canvas, including while the video is playing, while the window is resized, and
  after zooming changes the on-screen size of the outlines.

### No other changes

- Annotation coordinates stay in whole video pixels and the annotation file
  format is unchanged, so `scripts/annotate.sh` is not affected.
- Blur boxes, text boxes, arrows, the red "text does not fit" outline and the
  preview of unsaved style changes keep their current look.

## Possible Edge Cases

- Dragging a region, then pressing Escape or leaving the window before releasing
  the mouse.
- Picking a point, then immediately using the arrow keys, the slider or the
  frame step buttons to move the playhead.
- Selecting an annotation that is not active at the current time, then playing
  the video through its time range.
- Selecting an annotation, then editing only its start and end times so it is no
  longer active at the playhead.
- Switching to select mode with a "new" marker visible, then back to draw mode.
- Switching between the rectangle tool and the arrow tool while a marker of the
  other shape is visible.
- Deleting the last remaining annotation, or deleting the selected one so the
  selection moves to a neighbour of a different kind (box versus arrow).
- Loading an annotation file while an annotation is selected.
- Opening a second video of a different size while a marker or highlight is
  visible.
- Hide preview on, then picking a point or selecting a row.
- Very small or very large video scaling, where the thin outline and handles
  have a different size on screen than in video pixels.
- Several annotations stacked on the same spot: only the selected one is
  highlighted.

## Acceptance Criteria

- After picking a point or region and then doing any of the actions listed under
  "The new marker", no yellow marker is left on the canvas that does not match
  the form.
- After deleting, loading, or clearing the selection, no yellow highlight or
  handle is left on the canvas.
- Seeking or playing past the time range of the selected annotation does not
  leave an unexplained yellow highlight over empty video (behaviour as decided
  in the open questions).
- Editing the position or size fields never leaves a yellow graphic at the old
  location.
- Dragging a handle or moving an annotation during playback, hiding the preview,
  and resizing the window leave no pixel trails or partial yellow remnants.
- Opening another video starts with a clean canvas.
- Text, blur and arrow previews, the annotation file format and the rendered
  output are unchanged.
- Automated tests cover the state rules that can be tested without a display
  (when each yellow graphic is shown or hidden), and they pass together with the
  existing tests.

## Open Questions

- Which yellow graphic does the user see most often as residue: the marker right
  after clicking or dragging in draw mode, the highlight of a selected row, or
  both? Is it more visible while the video is paused or while playing? ANSWER:
  Yes that is it. Both appear to leave residue; the exact trigger is not known
  yet.
- Should the "selected" highlight be hidden when the selected annotation is not
  active at the current time, or stay visible in a visibly different style (for
  example dimmer or dashed) so the user can still see and edit it? Answer:
  dimmer and dashed.
- When the user edits a position or size field, should the "new" marker move to
  match the new values, or simply disappear? Answer: move to match the new
  values.
- Should a plain click marker disappear on its own after a short time, or stay
  until the next action? Ansewer: disappear after a short time (for example 1
  second).
- If part of the problem is repaint trails, is it acceptable to redraw the whole
  canvas on every change, at the cost of some extra work while the video plays?
  Answer: yes, redraw the whole canvas on every change.
