# vidnote (v1: with rendering)

[![Release](https://github.com/Binbiriz/simple-video-annotator/actions/workflows/release.yml/badge.svg)](https://github.com/Binbiriz/simple-video-annotator/actions/workflows/release.yml)

A small Linux desktop tool for annotating videos. Open a video, **click or drag
on it** to pick coordinates, set start/end times from the player, and add **text
labels**, **blur regions** or **arrows**. vidnote saves a plain text annotation
file and can render the result with **ffmpeg**.

```plaintext
video -> click / drag to pick x, y, w, h (or an arrow's end points) -> annotations.txt -> annotate.sh (ffmpeg) -> output.mp4
```

Built with Python and PySide6 (Qt 6).

## Requirements

- Linux, Python 3.9+
- `ffmpeg` (with `libfreetype` for `drawtext`) and `fontconfig`
- Debian/Ubuntu:
  `sudo apt install python3-venv ffmpeg fontconfig fonts-dejavu-core fonts-ubuntu libxcb-cursor0`
  (`fonts-ubuntu` provides Ubuntu Mono; another monospace font is used if it is
  missing)

### AppImage runtime requirements

The AppImage runs on x86_64 Linux (Ubuntu 22.04 or newer). It needs these on the
host:

|                                                | In the AppImage | Needed on the host                 |
| ---------------------------------------------- | --------------- | ---------------------------------- |
| Python, PySide6 (Qt 6), `libxcb-cursor`        | yes             | no                                 |
| `ffmpeg` with `libfreetype` (`drawtext`)       | no              | yes                                |
| `fontconfig` (`fc-match`) and a monospace font | no              | yes                                |
| FUSE 2 (`libfuse2`)                            | no              | only to run it directly; see below |

Install them:

```bash
# Debian/Ubuntu
sudo apt install ffmpeg fontconfig fonts-dejavu-core fonts-ubuntu
# Fedora (or the full ffmpeg from RPM Fusion instead of ffmpeg-free)
sudo dnf install ffmpeg-free fontconfig dejavu-sans-mono-fonts
# Arch
sudo pacman -S ffmpeg fontconfig ttf-dejavu
```

`fonts-ubuntu` provides Ubuntu Mono; another monospace font is used if it is
missing. Without FUSE (`libfuse2` on Ubuntu 22.04+; Ubuntu 24.04 ships only FUSE
3), start the AppImage with `--appimage-extract-and-run`, see "Releases and the
AppImage".

Check the host:

```bash
ffmpeg -hide_banner -filters | grep drawtext   # must print a line; if empty, ffmpeg lacks libfreetype
fc-match monospace                             # must print a font, not an error
```

## Install and run

```bash
./run.sh                 # creates .venv on first run, installs PySide6, starts the app
./run.sh my_video.mp4    # open a video directly
```

Manual:
`python3 -m venv .venv && source .venv/bin/activate && pip install -e . && vidnote video.mp4`

## Usage

1. Open a video (`Ctrl+O`). In draw mode, the yellow marker for a picked region
   or line follows the position and size fields; a plain click shows a small
   square that disappears after about a second. The marker is also removed when
   you add, update, delete or load annotations, open a video, change the type,
   toggle **Select** or select an annotation. `Escape` cancels a drag in
   progress.
2. Seek to the start (`Space` play/pause, `Left`/`Right` one frame,
   `Shift+Left`/`Right` one second) and press `[` to set **Start**; seek to the
   end and press `]` to set **End**.
3. Text and blur: drag a rectangle on the video; for text, also type the words
   and choose the **Font size** (8-72 px, default 14), the **Box colour** and
   the **Text colour** (black or white). Resize via the W/H fields if needed.
   The canvas preview shows the text at that size; boxes whose text does not fit
   get a red dashed outline. With a row selected, changing the size or colours
   updates its preview immediately; press **Update selected** to keep the
   change.
4. Arrows: set **Type** to **Arrow** and drag on the video from the start point
   to the end point (the start stays where the drag began, also for
   right-to-left or bottom-to-top drags). Choose the **Thickness** (1-30 px,
   default 4), the **Colour** (from the same list as the box colours) and a
   style for each end (**None** or **Arrowhead**; default none at the start,
   arrowhead at the end). Arrowheads scale with the thickness. Arrows are always
   drawn at 50% opacity, as one shape, and both end points must lie inside the
   video. Changing thickness, colour or styles with a row selected updates the
   canvas immediately.
5. **Add**. Select a row to **Update selected** or **Delete selected**.
6. Toolbar **Select** switches to select mode: click an annotation that is
   active at the current time (click again at the same spot to cycle through
   overlapping ones), drag it to move it, or drag a handle to resize it. Text
   and blur both work; the box stays inside the video and is at least 10x10 px.
   Resizing a text box scales its font size (you can still change it in the
   form). A selected arrow shows a handle on each end point: drag a handle to
   move that end, or drag the line to move the whole arrow (both end points stay
   inside the video). A thin arrow can still be clicked: the click area is at
   least 8 screen pixels wide. Annotations that are not active at the current
   time can be selected from the list and then edited on the canvas too. Switch
   **Select** off to draw new regions again. The selected annotation is outlined
   in yellow: solid while it is active at the current time, dimmer and dashed
   otherwise (still editable). The outline follows the position and size fields.
7. Toolbar **Hide preview** (it then reads **Show preview**) hides every preview
   item on the canvas (boxes, text, arrows, highlight, handles) without touching
   the annotations; toggle it off or select a list row to bring them back.
8. **Edit > Box and arrow colours...** edits the colour list, one `hex|label`
   per line (for example `#ffd400|Yellow`). It is stored in the app settings and
   applies to all files; invalid or duplicate lines are reported and skipped.
9. `Ctrl+S` saves the annotation file, `Ctrl+R` renders the video through
   ffmpeg.

## Annotation file format

Times in seconds, positions in video pixels from the top-left. `#` starts a
comment. Fields are separated by `|`; whitespace around fields is ignored. `x`,
`y`, `w`, `h`, `size`, the arrow points and `thickness` are whole numbers. The
text is the rest of the line and may contain spaces and `|`. Old formats
(whitespace-separated lines, `text|start|end|x|y|text`, and
`text|start|end|x|y|w|h|text` without `size` and colours) are no longer
supported: such lines are reported as malformed.

```plaintext
text|start|end|x|y|w|h|size|boxcolor|textcolor|text    # text in a w x h box
blur|start|end|x|y|w|h                                 # blur
arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle   # arrow from (x1,y1) to (x2,y2)
```

`size` is the font size in video pixels (8-72). `boxcolor` is `#rrggbb` (written
lowercase; read with or without `#`, any case) and is drawn at 50% opacity.
`textcolor` is `#000000` or `#ffffff` only.

For an arrow, `thickness` is 1-30 px, `color` is `#rrggbb` (same rules as
`boxcolor`, drawn at 50% opacity) and `startstyle`/`endstyle` are `none` or
`arrow` (an arrowhead), lowercase. Both points must differ and lie inside the
video. Annotations are drawn in file order, so later lines are on top.

Example:

```plaintext
blur|52.24|54.68|170|220|448|176
text|53.96|60.96|170|220|300|60|14|#000000|#ffffff|deneme
text|60|64|20|20|300|80|24|#ffd400|#000000|Black text on a yellow box
arrow|55|58|400|300|240|240|4|#e03131|none|arrow
arrow|60|64|500|60|300|60|8|#ffffff|arrow|arrow
```

The text is drawn left aligned in a monospace font (Ubuntu Mono preferred)
inside the box. It is wrapped to the box width and drawn at exactly `size`;
there is no automatic fitting. If the wrapped text is taller than the box (or
not even one character fits its width) it is still drawn and a warning is shown
(the preview outlines such boxes in red; the renderer prints a warning). The box
must lie inside the video.

## Rendering without the GUI

```bash
./scripts/annotate.sh input.mp4 annotations.txt output.mp4
```

`x`/`y`/`w`/`h` and the arrow points are integer video pixels. A malformed line,
a text box outside the video, or an arrow end point outside the video stops the
script with a `file:line` message. Text that does not fit its box at its font
size prints a warning. Env vars: `FONT=/path/font.ttf`,
`VIDNOTE_SCRIPT=/path/annotate.sh`. The output file is overwritten without
asking.

Blur, text and arrows are drawn in file order. Each arrow is drawn as a
transparent PNG that ffmpeg itself generates (the `geq` filter computes an
anti-aliased alpha mask, mirroring `src/vidnote/arrowgeom.py`) and lays over the
video during the arrow's time range, so no additional tool is needed.

## Releases and the AppImage

Releases are published on the GitHub Releases page, with one asset:
`vidnote-<version>-x86_64.AppImage` (Linux x86_64, Ubuntu 22.04 and newer).

Run it:

```bash
chmod +x vidnote-<version>-x86_64.AppImage
./vidnote-<version>-x86_64.AppImage [video.mp4]
```

It needs `ffmpeg` and `fontconfig` on the host (see AppImage runtime
requirements above). Without FUSE, run
`./vidnote-<version>-x86_64.AppImage --appimage-extract-and-run [video.mp4]` (or
set `APPIMAGE_EXTRACT_AND_RUN=1`). `VIDNOTE_SCRIPT` and `FONT` still work.

Publish a release (maintainers):

1. Bump `version` in `pyproject.toml` and merge to `main`.
2. Run the **Release** workflow from the Actions tab, or
   `gh workflow run release.yml --ref main -f tag=v0.2.0`.

The tag must be `vMAJOR.MINOR.PATCH` and equal the `pyproject.toml` version. The
workflow only runs from `main` and only by hand. It fails without creating
anything if the tag has another format or suffix (such as `-rc1`), if the tag or
a release for it already exists, or if lint or tests fail. The tag is created on
the commit of the run when the release is published.

Build the AppImage locally (needs Python 3.11+, network access and
`libxcb-cursor0`): `./packaging/appimage/build.sh` writes
`dist/vidnote-<version>-x86_64.AppImage`. The image is large (about 235 MB)
because it bundles the full PySide6 wheel (`QtMultimedia` is not in
`PySide6-Essentials`).

## Project layout

```plaintext
src/vidnote/  __main__.py, main_window.py, video_view.py, colors_dialog.py,
              models.py, exporter.py, colors.py, textfit.py, arrowgeom.py
scripts/annotate.sh
tests/        test_models.py, test_exporter.py, test_colors.py, test_textfit.py,
              test_arrowgeom.py, test_annotate_sh.py
examples/annotations.txt
packaging/appimage/        AppImage recipe and build.sh
.github/workflows/         release.yml (manual release workflow)
```

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
```

`VideoView` is a `QGraphicsView` whose scene is the video's native pixel space,
so `mapToScene()` on a click returns exact video pixels regardless of scaling or
letterboxing. `models.py`, `exporter.py`, `colors.py`, `textfit.py` and
`arrowgeom.py` have no Qt imports and are testable without a display.

## Troubleshooting

- Black window / no playback: install ffmpeg libraries, test with `ffplay`, try
  `QT_MEDIA_BACKEND=ffmpeg`.
- `Could not load the Qt platform plugin "xcb"`:
  `sudo apt install libxcb-cursor0`.
- `No such filter: 'drawtext'`: your ffmpeg lacks libfreetype.
- AppImage does not start: without FUSE use `--appimage-extract-and-run` (or
  `APPIMAGE_EXTRACT_AND_RUN=1`); `sudo apt install libfuse2` also fixes it on
  Ubuntu.
