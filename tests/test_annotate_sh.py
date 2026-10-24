"""End-to-end test of scripts/annotate.sh. Skipped when ffmpeg or drawtext is missing."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from vidnote import colors, textfit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "annotate.sh"

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _render(tmp_path, content):
    src = tmp_path / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc=duration=3:size=640x360:rate=25", "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )
    ann = tmp_path / "ann.txt"
    ann.write_bytes(content.encode())
    out = tmp_path / "out.mp4"
    res = subprocess.run(["bash", str(SCRIPT), str(src), str(ann), str(out)],
                         capture_output=True, text=True)
    if "No such filter: 'drawtext'" in res.stderr:
        pytest.skip("ffmpeg built without drawtext")
    assert res.returncode == 0, res.stderr
    assert out.exists() and out.stat().st_size > 0
    return res


def test_render_text_and_blur(tmp_path):
    _render(tmp_path,
            "text|0.5|2|20|20|300|60|14|#000000|#ffffff|Hello world\n"
            "blur|1|2.5|100|100|200|100\n")


@pytest.mark.parametrize("size,box,color", [
    (8, "#000000", "#ffffff"),
    (30, "#ffd400", "#000000"),
    (72, "1E90FF", "FFFFFF"),
])
def test_render_sizes_and_colours(tmp_path, size, box, color):
    res = _render(tmp_path, f"text|0.5|2|10|10|600|300|{size}|{box}|{color}|Hello\n")
    assert "does not fit" not in res.stderr


def test_render_padded_fields_pipe_in_text_and_crlf(tmp_path):
    _render(tmp_path,
            " text | 0.5 | 2 | 20 | 20 | 300 | 60 | 14 | #ffd400 | #000000 | a | b \r\n"
            "blur|1|2.5|100|100|200|100\r\n")


def test_render_long_text_in_small_box_warns_but_succeeds(tmp_path):
    res = _render(tmp_path,
                  "text|0.5|2|20|20|60|30|14|#000000|#ffffff|" + "word " * 50 + "\n")
    assert "does not fit" in res.stderr and "ann.txt:1:" in res.stderr


def test_render_text_that_fits_does_not_warn(tmp_path):
    res = _render(tmp_path, "text|0.5|2|20|20|300|60|14|#000000|#ffffff|Hello\n")
    assert "does not fit" not in res.stderr


def test_text_box_beyond_frame_is_rejected(tmp_path):
    with pytest.raises(AssertionError) as exc:
        _render(tmp_path, "text|0|1|600|10|100|50|14|#000000|#ffffff|hi\n")
    assert "beyond" in str(exc.value) and "ann.txt:1:" in str(exc.value)


def _run_bad(tmp_path, content):
    ann = tmp_path / "ann.txt"
    ann.write_text(content)
    res = subprocess.run(["bash", str(SCRIPT), "missing.mp4", str(ann), "y.mp4"],
                         capture_output=True, text=True)
    assert res.returncode != 0
    return res.stderr


@pytest.mark.parametrize("line", [
    "text|0|1|2|3|hi",  # old format
    "text|0|1|2|3|50|20|hi",  # previous format
    "text 0.5 2 20 20 Hello",
    "0.5 2 20 20 Hello",
    "text|0|1|(w-text_w)/2|5|50|20|14|#000000|#ffffff|hi",
    "text|0|1|2|3|a|b|c",
    "text|0|1|2|3|50|20|big|#000000|#ffffff|hi",
    "text|0|1|2|3|50|20|7|#000000|#ffffff|hi",
    "text|0|1|2|3|50|20|73|#000000|#ffffff|hi",
    "text|0|1|2|3|50|20|14|#GGG|#ffffff|hi",
    "text|0|1|2|3|50|20|14|red|#ffffff|hi",
    "text|0|1|2|3|50|20|14|#000000|#ff0000|hi",
    "text|0|1|2|3|0|20|14|#000000|#ffffff|hi",
    "text|0|1|2|3|50|-5|14|#000000|#ffffff|hi",
    "text|0|1|2|3|50|20|14|#000000|#ffffff|   ",
    "text|0|1|2|3|50|20|14|#000000|#ffffff",
    "blur|1|2|3|4",
    "blur|1|2|3|4|5|6|7",
])
def test_malformed_line_fails_with_line_number(tmp_path, line):
    err = _run_bad(tmp_path, f"# header\ntext|0|1|2|3|50|20|14|#000000|#ffffff|ok\n{line}\n")
    assert "ann.txt:3:" in err


def test_old_text_format_says_no_longer_supported(tmp_path):
    err = _run_bad(tmp_path, "text|0|1|2|3|50|20|hi\n")
    assert "no longer supported" in err


def test_empty_annotation_file_fails(tmp_path):
    ann = tmp_path / "ann.txt"
    ann.write_text("# nothing here\n")
    res = subprocess.run(["bash", str(SCRIPT), "x.mp4", str(ann), "y.mp4"],
                         capture_output=True, text=True)
    assert res.returncode != 0


# (text, w, h, size, box colour, text colour)
LAYOUT_CASES = [
    ("Hello world", 300, 60, 14, "#000000", "#ffffff"),
    ("This is a rather long sentence that needs to be wrapped inside a small box",
     200, 60, 14, "#FFD400", "#000000"),
    ("Supercalifragilisticexpialidocious", 60, 120, 20, "1e90ff", "ffffff"),
    ("Çok güzel bir şarkı ışığı | ve bir boru", 150, 50, 8, "#e03131", "#ffffff"),
    ("word " * 100, 60, 30, 14, "#000000", "#ffffff"),
    ("hello", 2, 2, 72, "#000000", "#ffffff"),
    ("hello", 12, 200, 40, "#000000", "#ffffff"),
    ("some text", 400, 100, 72, "#2f9e44", "#000000"),
]


def _print_layout(tmp_path, cases):
    ann = tmp_path / "ann.txt"
    ann.write_text("".join(f"text|0|1|0|0|{w}|{h}|{sz}|{bc}|{tc}|{t}\n"
                           for t, w, h, sz, bc, tc in cases), encoding="utf-8")
    res = subprocess.run(["bash", str(SCRIPT), "missing.mp4", str(ann), "y.mp4"],
                         capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "VIDNOTE_PRINT_LAYOUT": "1"})
    assert res.returncode == 0, res.stderr
    got = []
    for ln in res.stdout.splitlines():
        if ln.startswith("layout|"):
            _, _no, size, ok, box, color = ln.split("|")
            got.append([int(size), ok == "1", box, color, []])
        else:
            got[-1][4].append(ln[len("  |"):])
    return got


@pytest.mark.skipif(shutil.which("fc-match") is None, reason="fontconfig not installed")
def test_layout_matches_python(tmp_path):
    got = _print_layout(tmp_path, LAYOUT_CASES)
    assert len(got) == len(LAYOUT_CASES)
    for (text, w, h, size, bc, tc), (gsize, ok, box, color, lines) in zip(LAYOUT_CASES, got):
        want = textfit.layout_text(text, w, h, size)
        assert (gsize, ok, lines) == (want.size, want.fits, want.lines), text
        assert box == "0x" + colors.normalize_hex(bc)[1:]
        assert color == "0x" + colors.normalize_hex(tc)[1:]


@pytest.mark.skipif(shutil.which("fc-match") is None, reason="fontconfig not installed")
def test_text_is_drawn_at_exactly_the_given_size(tmp_path):
    text = "word " * 40  # the old auto-fit would have shrunk this to fit
    got = _print_layout(tmp_path, [(text, 100, 60, size, "#000000", "#ffffff")
                                   for size in (8, 14, 40)])
    assert [g[0] for g in got] == [8, 14, 40]
