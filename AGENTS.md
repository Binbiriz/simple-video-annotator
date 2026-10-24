# vidnote

PySide6 desktop tool: pick coordinates on a video, write a plain-text annotation file, render with ffmpeg via `scripts/annotate.sh`.

## Commands

- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Test: `pytest` (single: `pytest tests/test_exporter.py::test_name`). Lint: `ruff check src tests` (line length 100).
- Run app: `./run.sh [video]` (creates `.venv` and installs only runtime deps on first run, not dev extras).
- Render without GUI: `./scripts/annotate.sh in.mp4 annotations.txt out.mp4` (overwrites output, `ffmpeg -y`).
- No typecheck/CI/pre-commit config exists.

## Architecture

- `models.py`, `exporter.py` and `colors.py` have no Qt imports (`textfit.py` and `arrowgeom.py` too); keep them that way so tests run without a display.
- `video_view.py`: `QGraphicsView` whose scene is the video's native pixel space, so `mapToScene()` gives exact video pixels regardless of scaling. Keep annotation coordinates in video pixels.
- `main_window.py` (the bulk of the GUI) uses `video_view` (draw and select modes, move/resize handles); `colors_dialog.py` edits the box colour list stored in `QSettings`; `__main__:main` is the `vidnote` entrypoint.
- `textfit.py`: text layout at a user-chosen font size (`layout_text`); there is no auto-fit. `scripts/annotate.sh` mirrors it (`PAD`, `LINE_H_PM`, `ADV_PM`); keep both in sync.
- `arrowgeom.py`: arrow shape (shaft + heads, head size from thickness) used by the canvas preview and the tests. `scripts/annotate.sh` mirrors it in the `geq` alpha expression of the per-arrow overlay PNG (`HEAD_*`, `ARROW_ALPHA`, padding); keep both in sync. `overlay` rounds positions down to even coordinates on yuv420p, so the script rounds the image origin itself.

## Annotation format (two implementations must stay in sync)

The format is parsed/written by both `src/vidnote/exporter.py` (Python) and `scripts/annotate.sh` (bash `read`). Changing the format, e.g. adding an annotation type, requires editing both plus `README.md`, `examples/annotations.txt`, and tests.

- `text|start|end|x|y|w|h|size|boxcolor|textcolor|text` / `blur|start|end|x|y|w|h` / `arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle`; `|` separated, seconds and video pixels, `#` comments. Text is the remainder after the 10th `|`. `size` 8-72, colours `#rrggbb`, text colour only `#000000`/`#ffffff`. Arrow: thickness 1-30, styles `none`/`arrow`, 50% opacity, points must differ and lie inside the video; annotations are drawn in file order.
- No backward compatibility: older text shapes must be rejected as malformed ("no longer supported") in both.
- Text goes through a per-annotation temp file with `expansion=none` in drawtext (deliberately avoids escaping). `x`/`y`/`w`/`h` must be integers in both.

## Testing quirks

- `tests/test_annotate_sh.py` generates a video with ffmpeg `lavfi`; skipped if ffmpeg is missing and skipped if drawtext (libfreetype) is absent.
- Runtime needs `ffmpeg`, `fontconfig` (`fc-match` picks the font); `libxcb-cursor0` for Qt xcb.

## Commit conventions

Follow `ai-partial-helpers/git-conventions.md` when writing commit messages.

## Repo notes

- `.claude/skills/sdd-*-lite` are spec/plan/impl workflow skills that write to `_sdd/` (not present yet); `docs/` holds a background note on blurring. Both are untracked.
- `*.mp4`/`*.mkv` etc. are gitignored; don't commit sample media.
