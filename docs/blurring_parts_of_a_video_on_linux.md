---
title: "Blurring parts of a video on Linux"
source: "https://claude.ai/chat/80221935-1e5e-40f3-badd-5e7b2cd08b06"
model: "claude-sonnet-5-5"
exported: 2026-10-24
---

# Human — Oct 24, 2026, 1:56 PM

What is the easiest way to blur some parts of a video? İ use linux

# Claude — Oct 24, 2026, 1:56 PM

The easiest free option is **Kdenlive**, a video editor you can install from your distro's software center or with Flatpak (`flatpak install flathub org.kde.kdenlive`). Put your clip on the timeline, add a blur effect (or a mask/rectangle effect in newer versions), and set its start and end times to cover only the part you want blurred.

If the blurred area stays in one fixed rectangle for a set time, **ffmpeg** is quicker. Install it with `sudo apt install ffmpeg` (or your distro's equivalent), then run:

```bash
ffmpeg -i input.mp4 -filter_complex "[0:v]crop=300:200:100:50,boxblur=10:2[blur];[0:v][blur]overlay=100:50:enable='between(t,5,12)'" -c:a copy output.mp4
```

This blurs a 300×200 pixel box at position (100, 50) from second 5 to second 12. Adjust the numbers to fit your video:
- `crop=width:height:x:y` sets the region to blur.
- `overlay=x:y` must use the same x and y as the crop.
- `between(t,start,end)` sets the time range in seconds.
- `boxblur=10:2` controls blur strength; increase the first number for a stronger blur.

If the subject moves, a fixed box won't follow it. In that case, use Kdenlive's mask tools with keyframes or a dedicated tracking tool like Shotcut's tracker.

# Human — Oct 24, 2026, 1:57 PM

Ffmpeg is nice but how to give coordinates

# Claude — Oct 24, 2026, 1:57 PM

You need the video's pixel coordinates, with (0,0) at the top-left corner. Here's how to find them with ffmpeg:

**1. Check the video's resolution:**
```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 input.mp4
```
This prints something like `1920,1080`.

**2. Save a frame from where the blur should appear:**
```bash
ffmpeg -ss 00:00:05 -i input.mp4 -frames:v 1 frame.png
```

**3. Add a grid so you can read positions:**
```bash
ffmpeg -i frame.png -vf "drawgrid=w=100:h=100:t=1:c=red@0.6" grid.png
```
Open `grid.png`. Each grid cell is 100×100 pixels, so you can count cells from the top-left corner to estimate the box's edges. For more precision, use a smaller spacing, such as `w=50:h=50`.

For exact numbers, open `frame.png` in GIMP or Krita and hover the mouse over the corners of the area. The status bar shows the pixel coordinates.

**4. Calculate the crop values:**
- `x` = distance from the left edge to the box's left side
- `y` = distance from the top edge to the box's top side
- `width` = right side minus left side
- `height` = bottom side minus top side

For example, if the box runs from x=100 to x=400 and y=50 to y=250, then `crop=300:200:100:50`. Use the same `x:y` in the `overlay` part of the command, as mentioned before.

# Human — Oct 24, 2026, 2:00 PM

Simple annotations on screen text read from a text file for ffmpeg time and coordinates and text for example

# Claude — Oct 24, 2026, 2:00 PM

Put one annotation per line in a text file, with start time, end time, x, y, and then the text:

```
# start end x y text
2 6 50 50 Welcome to the tutorial
8 12 (w-text_w)/2 h-120 Click the Save button
```

Lines starting with `#` are ignored. Coordinates start at (0,0) in the top-left corner. `w` and `h` are the video's width and height, and `text_w` is the width of the text, so `(w-text_w)/2` centers the text horizontally and `h-120` places it 120 pixels above the bottom.

Save this script as `annotate.sh`:

```bash
#!/bin/bash
# usage: ./annotate.sh input.mp4 annotations.txt output.mp4
in="$1"; list="$2"; out="$3"
font=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf   # change if this path doesn't exist
tmp=$(mktemp -d)
filters=""
n=0

while read -r start end x y text; do
  [[ -z "$start" || "$start" == \#* ]] && continue
  n=$((n+1))
  printf '%s' "$text" > "$tmp/$n.txt"   # text goes in its own file, so no escaping needed
  f="drawtext=fontfile=$font:textfile=$tmp/$n.txt:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=12:x=$x:y=$y:enable='between(t,$start,$end)'"
  filters="${filters:+$filters,}$f"
done < "$list"

ffmpeg -i "$in" -vf "$filters" -c:a copy "$out"
rm -rf "$tmp"
```

Make it executable and run it:

```bash
chmod +x annotate.sh
./annotate.sh input.mp4 annotations.txt output.mp4
```

You can adjust `fontsize`, `fontcolor`, and the box settings in the script to change the look. If you want the box removed, delete `box=1:boxcolor=black@0.5:boxborderw=12`.

If you only need one annotation, you can skip the script and run:

```bash
ffmpeg -i input.mp4 -vf "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile=note.txt:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.5:x=50:y=50:enable='between(t,2,6)'" -c:a copy output.mp4
```

# Human — Oct 24, 2026, 2:01 PM

İs it difficult to develope a software to at least get the coordinates and timestamps visually using a mouse for simple videos with electron or your suggestion?

# Claude — Oct 24, 2026, 2:02 PM

It's not very difficult for a basic version. A minimal tool that plays a video, lets you click to mark positions, records timestamps, and exports the annotation file is a weekend project for someone comfortable with web development. Polishing it takes longer.

I'd skip Electron for this. A plain HTML page opened in your browser can do the same job, with no packaging, no extra runtime, and an easier path to later sharing. Electron only makes sense if you want a native app with file dialogs and an installer.

The core pieces are:

- **Playback:** An HTML `<video>` element with a frame-by-frame step button (for example, nudging `currentTime` by 1/30 second) for precise timestamps.
- **Coordinate capture:** A click handler that converts mouse position into video pixels. This is the trickiest part. The displayed video is scaled and may have letterboxing, so you need to use `videoWidth` and `videoHeight` along with the element's bounding box and the scale factor, not the raw mouse position.
- **Timestamp capture:** Reading `video.currentTime` when you press a key or button to mark the start and end.
- **Preview:** Drawing a rectangle or a text label on a canvas overlay, so you can see roughly where things will land.
- **Export:** Generating the same `start end x y text` lines that the `annotate.sh` script reads.

The main difficulties are:

- Letterboxing and scaling math, which is easy to get subtly wrong.
- Accurate seeking, since browsers don't always land exactly on the frame you requested.
- Codec support, since some formats (like HEVC in some browser builds) won't play in the browser.
- Text preview that matches ffmpeg's rendering. Expect approximate, not identical, results.

If you want to try it, I can write a single-file HTML starter that handles playback, click-to-coordinate, timestamp marking, and export. It would be a good base to extend.

# Human — Oct 24, 2026, 2:03 PM

What if we use a desktop tech

# Claude — Oct 24, 2026, 2:03 PM

Yes, a desktop framework makes sense, and it avoids the browser codec limits. For a Linux-only tool, I'd pick one of these:

- **PySide6 (Qt for Python):** My top pick. Qt 6's media player uses FFmpeg under the hood, so most codecs play. Python can write the annotation file and call `annotate.sh` or ffmpeg directly with `subprocess`. Qt also gives you mouse events, a frame-accurate seek, and an overlay you can draw on.
- **Tauri (Rust backend, HTML/JS frontend):** Small and modern, and you can reuse the HTML approach from earlier. On Linux it runs on WebKitGTK, so codec support depends on your system's GStreamer packages, which can be a hassle.
- **GTK4 with PyGObject:** Native and fine on GNOME, but video handling through GStreamer is more fiddly.
- **Tkinter:** Easiest to start, but its video support is weak, so you'd need workarounds like extracting frames with ffmpeg.

The coordinate math is the same in every option. You still map the click from widget space to video pixels, accounting for letterboxing, so pick the framework that makes the rest of the tool easiest to build.

For your case, I'd go with PySide6. The tool would need about 300 lines: a player with frame stepping, click-to-coordinate with a live rectangle preview, a list of annotations you can edit, and an export button that writes the file `annotate.sh` reads. Install it with `pip install PySide6`.

Want me to write that starter?

# Human — Oct 24, 2026, 2:06 PM

Yes go but give me a zip file with all folder structure readme.md installation and dev instructions

# Claude — Oct 24, 2026, 2:10 PM

Core logic and the ffmpeg script both work in tests, so I'm now writing the PySide6 GUI files.

**vidnote.zip** is ready. Unzip it, `cd vidnote`, and run `./run.sh my_video.mp4`. It creates a venv, installs PySide6, and opens the app. The README covers system packages, manual install, dev setup and troubleshooting.

- **Picking:** click the video for a point (text) or drag for a rectangle (blur). Coordinates come out in true video pixels, even when the video is scaled.
- **Timing:** press `[` and `]` to set start and end at the current frame. `Space` plays, and the arrow keys step by frame.
- **Annotations:** you can add, edit and delete text and blur entries, with a live preview on the video.
- **Output:** `Ctrl+S` saves the annotation file. `Ctrl+R` renders the video through `scripts/annotate.sh`, which also works on its own from the command line.

The file format now has a second line type for blurs, `blur start end x y w h`. Your earlier text lines still work unchanged.

I tested `annotate.sh` against a real ffmpeg render (text, blur and an expression-based position) and checked the save/load logic. I couldn't install PySide6 in my sandbox, so the GUI code compiled but has not actually been run. Expect to hit a small bug or two on first launch. If you do, send me the error message and I'll fix it.

# Human — Oct 24, 2026, 2:11 PM

Keep it simple i just want the blur or text annotaion coordinates and timestamps that it i will put it in a text file and write text if it is a text annotation. Maybe beginning timestamp and duration is much simpler. İt doesnt have to run the script and edit the video

# Claude — Oct 24, 2026, 2:12 PM

Understood: I'll make it a pure coordinate picker that uses start + duration, with no rendering. It will save or copy the text file and nothing more.

I simplified it and rebuilt **vidnote.zip**. It now only picks coordinates and timestamps and saves them to a text file. There is no rendering from inside the app.

- **Format:** a text line is `start duration x y text`, for example `2 4 50 50 Welcome`. A blur line is `blur start duration x y w h`.
- **Workflow:** open a video, press `[` to set the start at the current frame, and set the duration (default 3 s). Click the video for a text position or drag for a blur region, then click Add.
- **Output:** Save (`Ctrl+S`) writes the text file, and Copy all (`Ctrl+Shift+C`) puts it on the clipboard. You can also load a file back to edit it.
- **ffmpeg script:** `scripts/annotate.sh` is still in the zip as an optional helper, updated to read start + duration. The app never calls it, and you can delete it.

As before, I could only check the text-file code and the ffmpeg script here, not the window itself, because PySide6 wasn't installable in my sandbox. If the app errors on first launch, send me the message and I'll fix it.

# Human — Oct 24, 2026, 2:12 PM

But also keep the first version for me to evaluate

# Claude — Oct 24, 2026, 2:13 PM

I overwrote the first version when I simplified, so I'm rebuilding it from the earlier code and will ship both versions as separate zips.

You now have both versions as separate zips.

- **vidnote-v1-with-render.zip:** the first version. It uses start and end times (`start end x y text`) and renders the annotated video with ffmpeg via `Ctrl+R`.
- **vidnote-v2-simple.zip:** the simplified version. It uses start and duration (`start duration x y text`), has no rendering, and adds a "Copy all" button.

I had overwritten the original v1 when I simplified, so I rebuilt it by reversing those changes. I checked it the same way as v2: the annotation file code and `annotate.sh` pass, but the window itself hasn't been run. It should match what I first sent, but I can't promise it is byte-for-byte identical.

Each zip unpacks into its own folder (`vidnote-v1` and `vidnote-v2`), so you can try both without them clashing. Each has its own `run.sh`, which creates a separate virtual environment.

# Human — Oct 24, 2026, 4:39 PM

lets go on with v1 only

please make text the same syntax

# vidnote annotations
# text: start end x y text
# blur: blur start end x y w h
blur 52.24 54.68 170 220 448 176
text 53.96 60.96 170 220 deneme

# Claude — Oct 24, 2026, 4:39 PM

Text lines now start with `text`, the same as blur lines. I reran your example and it round-trips unchanged:

```
# vidnote annotations
# text: text start end x y text
# blur: blur start end x y w h
blur 52.24 54.68 170 220 448 176
text 53.96 60.96 170 220 deneme
```

- **Saving:** the app writes this format, sorted by start time.
- **Loading:** it reads the same format. Older text lines without the `text` word still load, so any files you made earlier keep working.
- **Rendering:** `scripts/annotate.sh` reads both forms too. I ran it on a test video with text, blur and an old-style line, and it rendered fine.
- **Other files:** the README, `examples/annotations.txt` and the tests use the new format. The new zip is **vidnote-v1-with-render.zip**, and I removed the v2 zip from the outputs since you're continuing with v1 only.

I still haven't been able to run the app window itself here. If it errors when you launch it, send me the message.

# Human — Oct 24, 2026, 4:40 PM

can you make in a local git repo with added gitignore

# Claude — Oct 24, 2026, 4:40 PM

I put the project in a local git repo on branch `main` with one commit, "Initial commit: vidnote v1 (video annotation picker with ffmpeg rendering)". The zip is **vidnote-v1-git.zip**. Unzip it and run `git log` inside the `vidnote-v1` folder to see the commit.

The `.gitignore` covers:
- Python junk such as `__pycache__`, `*.egg-info`, `build/` and `dist/`.
- Virtual environments (`.venv/`, `venv/`).
- Tool caches and editor/OS files (`.pytest_cache/`, `.ruff_cache/`, `.vscode/`, `.idea/`, `.DS_Store`).
- Video files and rendered outputs (`*.mp4`, `*.mkv`, `*.webm`, `*.mov`, `*.avi`, `*_annotated.*`) and `*.annotations.txt`, so test videos and your own annotation files don't get committed by accident. `examples/annotations.txt` is still tracked.

The commit's author is a placeholder (`vidnote dev <dev@localhost>`), set only for this repo. If you want your own name on it, run `git config user.name "Your Name"` and `git config user.email "you@example.com"`, then `git commit --amend --reset-author --no-edit`.

