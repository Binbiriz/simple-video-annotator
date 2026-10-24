# vidnote (v1: with rendering)

A small Linux desktop tool for annotating videos. Open a video, **click or drag on it** to pick
coordinates, set start/end times from the player, and add **text labels** or **blur regions**.
vidnote saves a plain text annotation file and can render the result with **ffmpeg**.

```
video -> click / drag to pick x, y, w, h -> annotations.txt -> annotate.sh (ffmpeg) -> output.mp4
```

Built with Python and PySide6 (Qt 6).

## Requirements

- Linux, Python 3.9+
- `ffmpeg` (with `libfreetype` for `drawtext`) and `fontconfig`
- Debian/Ubuntu: `sudo apt install python3-venv ffmpeg fontconfig fonts-dejavu-core fonts-ubuntu libxcb-cursor0`
  (`fonts-ubuntu` provides Ubuntu Mono; another monospace font is used if it is missing)

## Install and run

```bash
./run.sh                 # creates .venv on first run, installs PySide6, starts the app
./run.sh my_video.mp4    # open a video directly
```

Manual: `python3 -m venv .venv && source .venv/bin/activate && pip install -e . && vidnote video.mp4`

## Usage

1. Open a video (`Ctrl+O`).
2. Seek to the start (`Space` play/pause, `Left`/`Right` one frame, `Shift+Left`/`Right` one second)
   and press `[` to set **Start**; seek to the end and press `]` to set **End**.
3. Text and blur: drag a rectangle on the video; for text, also type the words. Resize via the
   W/H fields if needed.
4. **Add**. Select a row to **Update selected** or **Delete selected**.
5. `Ctrl+S` saves the annotation file, `Ctrl+R` renders the video through ffmpeg.

## Annotation file format

Times in seconds, positions in video pixels from the top-left. `#` starts a comment. Fields are separated by `|`; whitespace around fields is ignored. `x`, `y`, `w` and `h` are whole numbers. The text may contain spaces and `|`. Old formats (whitespace-separated lines, and `text|start|end|x|y|text` without `w`/`h`) are no longer supported: such lines are reported as malformed.

```
text|start|end|x|y|w|h|text    # text, fitted into the w x h box
blur|start|end|x|y|w|h         # blur
```

Example:

```
blur|52.24|54.68|170|220|448|176
text|53.96|60.96|170|220|300|60|deneme
```

The text is drawn left aligned in a monospace font (Ubuntu Mono preferred) inside the box. It
starts at 14 px and is never enlarged; if it is too long it wraps, and the font shrinks down to
8 px until it fits. If it still does not fit at 8 px it is drawn at 8 px and a warning is shown
(the preview outlines such boxes in red; the renderer prints a warning). The box must lie inside
the video.

## Rendering without the GUI

```bash
./scripts/annotate.sh input.mp4 annotations.txt output.mp4
```

`x`/`y`/`w`/`h` are integer video pixels. A malformed line, or a text box outside the video, stops
the script with a `file:line` message. Text that does not fit its box prints a warning.
Env vars: `FONT=/path/font.ttf`, `VIDNOTE_SCRIPT=/path/annotate.sh`.
The output file is overwritten without asking.

## Project layout

```
src/vidnote/  __main__.py, main_window.py, video_view.py, models.py, exporter.py, textfit.py
scripts/annotate.sh
tests/        test_models.py, test_exporter.py, test_textfit.py, test_annotate_sh.py
examples/annotations.txt
```

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
```

`VideoView` is a `QGraphicsView` whose scene is the video's native pixel space, so
`mapToScene()` on a click returns exact video pixels regardless of scaling or letterboxing.
`models.py` and `exporter.py` have no Qt imports and are testable without a display.

## Troubleshooting

- Black window / no playback: install ffmpeg libraries, test with `ffplay`, try `QT_MEDIA_BACKEND=ffmpeg`.
- `Could not load the Qt platform plugin "xcb"`: `sudo apt install libxcb-cursor0`.
- `No such filter: 'drawtext'`: your ffmpeg lacks libfreetype.
