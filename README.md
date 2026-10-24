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
- Debian/Ubuntu: `sudo apt install python3-venv ffmpeg fontconfig fonts-dejavu-core libxcb-cursor0`

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
3. Text: click where the text starts and type it. Blur: drag a rectangle.
4. **Add**. Select a row to **Update selected** or **Delete selected**.
5. `Ctrl+S` saves the annotation file, `Ctrl+R` renders the video through ffmpeg.

## Annotation file format

Times in seconds, positions in video pixels from the top-left. `#` starts a comment. Fields are separated by `|`; whitespace around fields is ignored. `x`, `y`, `w` and `h` are whole numbers. The text may contain spaces and `|`. The old whitespace-separated format is no longer supported: such lines are reported as malformed.

```
text|start|end|x|y|text        # text
blur|start|end|x|y|w|h         # blur
```

Example:

```
blur|52.24|54.68|170|220|448|176
text|53.96|60.96|170|220|deneme
```

## Rendering without the GUI

```bash
./scripts/annotate.sh input.mp4 annotations.txt output.mp4
```

`x`/`y` are integer video pixels. A malformed line stops the script with a `file:line` message.
Env vars: `FONT=/path/font.ttf`, `FONTSIZE=48`, `VIDNOTE_SCRIPT=/path/annotate.sh`.
The output file is overwritten without asking.

## Project layout

```
src/vidnote/  __main__.py, main_window.py, video_view.py, models.py, exporter.py
scripts/annotate.sh
tests/        test_models.py, test_exporter.py, test_annotate_sh.py
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
