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
3. Text and blur: drag a rectangle on the video; for text, also type the words and choose the
   **Font size** (8-72 px, default 14), the **Box colour** and the **Text colour** (black or
   white). Resize via the W/H fields if needed. The canvas preview shows the text at that size;
   boxes whose text does not fit get a red dashed outline. With a row selected, changing the size or colours updates its preview
   immediately; press **Update selected** to keep the change.
4. **Add**. Select a row to **Update selected** or **Delete selected**.
5. Toolbar **Select** switches to select mode: click an annotation that is active at the current
   time (click again at the same spot to cycle through overlapping ones), drag it to move it, or
   drag a handle to resize it. Text and blur both work; the box stays inside the video and is at
   least 10x10 px. Resizing a text box scales its font size (you can still change it in the form).
   Annotations that are not active at the current time can be selected from the list and then
   edited on the canvas too. Switch **Select** off to draw new regions again.
6. Toolbar **Hide preview** (it then reads **Show preview**) hides every preview item on the canvas (boxes, text, highlight,
   handles) without touching the annotations; toggle it off or select a list row to bring them
   back.
7. **Edit > Text box colours...** edits the colour list, one `hex|label` per line (for example
   `#ffd400|Yellow`). It is stored in the app settings and applies to all files; invalid or
   duplicate lines are reported and skipped.
8. `Ctrl+S` saves the annotation file, `Ctrl+R` renders the video through ffmpeg.

## Annotation file format

Times in seconds, positions in video pixels from the top-left. `#` starts a comment. Fields are separated by `|`; whitespace around fields is ignored. `x`, `y`, `w`, `h` and `size` are whole numbers. The text is the rest of the line and may contain spaces and `|`. Old formats (whitespace-separated lines, `text|start|end|x|y|text`, and `text|start|end|x|y|w|h|text` without `size` and colours) are no longer supported: such lines are reported as malformed.

```
text|start|end|x|y|w|h|size|boxcolor|textcolor|text    # text in a w x h box
blur|start|end|x|y|w|h                                 # blur
```

`size` is the font size in video pixels (8-72). `boxcolor` is `#rrggbb` (written lowercase; read with or without `#`, any case) and is drawn at 50% opacity. `textcolor` is `#000000` or `#ffffff` only.

Example:

```
blur|52.24|54.68|170|220|448|176
text|53.96|60.96|170|220|300|60|14|#000000|#ffffff|deneme
text|60|64|20|20|300|80|24|#ffd400|#000000|Black text on a yellow box
```

The text is drawn left aligned in a monospace font (Ubuntu Mono preferred) inside the box. It is
wrapped to the box width and drawn at exactly `size`; there is no automatic fitting. If the
wrapped text is taller than the box (or not even one character fits its width) it is still drawn
and a warning is shown (the preview outlines such boxes in red; the renderer prints a warning).
The box must lie inside the video.

## Rendering without the GUI

```bash
./scripts/annotate.sh input.mp4 annotations.txt output.mp4
```

`x`/`y`/`w`/`h` are integer video pixels. A malformed line, or a text box outside the video, stops
the script with a `file:line` message. Text that does not fit its box at its font size prints a warning.
Env vars: `FONT=/path/font.ttf`, `VIDNOTE_SCRIPT=/path/annotate.sh`.
The output file is overwritten without asking.

## Project layout

```
src/vidnote/  __main__.py, main_window.py, video_view.py, colors_dialog.py,
              models.py, exporter.py, colors.py, textfit.py
scripts/annotate.sh
tests/        test_models.py, test_exporter.py, test_colors.py, test_textfit.py,
              test_annotate_sh.py
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
`models.py`, `exporter.py` and `colors.py` have no Qt imports and are testable without a display.

## Troubleshooting

- Black window / no playback: install ffmpeg libraries, test with `ffplay`, try `QT_MEDIA_BACKEND=ffmpeg`.
- `Could not load the Qt platform plugin "xcb"`: `sudo apt install libxcb-cursor0`.
- `No such filter: 'drawtext'`: your ffmpeg lacks libfreetype.
