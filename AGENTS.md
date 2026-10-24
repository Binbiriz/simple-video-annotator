# vidnote

PySide6 desktop tool: pick coordinates on a video, write a plain-text annotation file, render with ffmpeg via `scripts/annotate.sh`.

## Commands

- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Test: `pytest` (single: `pytest tests/test_exporter.py::test_name`). Lint: `ruff check src tests` (line length 100).
- Run app: `./run.sh [video]` (creates `.venv` and installs only runtime deps on first run, not dev extras).
- Render without GUI: `./scripts/annotate.sh in.mp4 annotations.txt out.mp4` (overwrites output, `ffmpeg -y`).
- No typecheck/CI/pre-commit config exists.

## Architecture

- `models.py` and `exporter.py` have no Qt imports; keep them that way so tests run without a display.
- `video_view.py`: `QGraphicsView` whose scene is the video's native pixel space, so `mapToScene()` gives exact video pixels regardless of scaling. Keep annotation coordinates in video pixels.
- `main_window.py` (the bulk of the GUI) uses `video_view`; `__main__:main` is the `vidnote` entrypoint.

## Annotation format (two implementations must stay in sync)

The format is parsed/written by both `src/vidnote/exporter.py` (Python) and `scripts/annotate.sh` (bash `read`). Changing the format, e.g. adding an annotation type, requires editing both plus `README.md`, `examples/annotations.txt`, and tests.

- `text start end x y text...` / `blur start end x y w h`; seconds and video pixels, `#` comments.
- Legacy text lines without the leading `text` keyword must still parse in both.
- Text goes through a per-annotation temp file with `expansion=none` in drawtext (deliberately avoids escaping); text `x`/`y` in the shell script may be ffmpeg expressions (no spaces/commas), but `exporter.parse_line` only accepts ints.

## Testing quirks

- `tests/test_annotate_sh.py` generates a video with ffmpeg `lavfi`; skipped if ffmpeg is missing and skipped if drawtext (libfreetype) is absent.
- Runtime needs `ffmpeg`, `fontconfig` (`fc-match` picks the font); `libxcb-cursor0` for Qt xcb.

## Commit conventions

Follow `ai-partial-helpers/git-conventions.md` when writing commit messages.

## Repo notes

- `.claude/skills/sdd-*-lite` are spec/plan/impl workflow skills that write to `_sdd/` (not present yet); `docs/` holds a background note on blurring. Both are untracked.
- `*.mp4`/`*.mkv` etc. are gitignored; don't commit sample media.
