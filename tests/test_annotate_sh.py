"""End-to-end test of scripts/annotate.sh. Skipped when ffmpeg or drawtext is missing."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from vidnote import textfit

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
    _render(tmp_path, "text|0.5|2|20|20|300|60|Hello world\nblur|1|2.5|100|100|200|100\n")


def test_render_padded_fields_pipe_in_text_and_crlf(tmp_path):
    _render(tmp_path,
            " text | 0.5 | 2 | 20 | 20 | 300 | 60 | a | b \r\nblur|1|2.5|100|100|200|100\r\n")


def test_render_long_text_in_small_box_warns_but_succeeds(tmp_path):
    res = _render(tmp_path, "text|0.5|2|20|20|60|30|" + "word " * 50 + "\n")
    assert "does not fit" in res.stderr and "ann.txt:1:" in res.stderr


def test_render_text_that_fits_does_not_warn(tmp_path):
    res = _render(tmp_path, "text|0.5|2|20|20|300|60|Hello\n")
    assert "does not fit" not in res.stderr


def test_text_box_beyond_frame_is_rejected(tmp_path):
    with pytest.raises(AssertionError) as exc:
        _render(tmp_path, "text|0|1|600|10|100|50|hi\n")
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
    "text 0.5 2 20 20 Hello",
    "0.5 2 20 20 Hello",
    "text|0|1|(w-text_w)/2|5|50|20|hi",
    "text|0|1|2|3|a|b|c",
    "text|0|1|2|3|0|20|hi",
    "text|0|1|2|3|50|-5|hi",
    "text|0|1|2|3|50|20|   ",
    "text|0|1|2|3|50|20",
    "blur|1|2|3|4",
    "blur|1|2|3|4|5|6|7",
])
def test_malformed_line_fails_with_line_number(tmp_path, line):
    err = _run_bad(tmp_path, f"# header\ntext|0|1|2|3|50|20|ok\n{line}\n")
    assert "ann.txt:3:" in err


def test_empty_annotation_file_fails(tmp_path):
    ann = tmp_path / "ann.txt"
    ann.write_text("# nothing here\n")
    res = subprocess.run(["bash", str(SCRIPT), "x.mp4", str(ann), "y.mp4"],
                         capture_output=True, text=True)
    assert res.returncode != 0


FIT_CASES = [
    ("Hello world", 300, 60),
    ("This is a rather long sentence that needs to be wrapped inside a small box", 200, 60),
    ("Supercalifragilisticexpialidocious", 60, 120),
    ("Çok güzel bir şarkı ışığı | ve bir boru", 150, 50),
    ("word " * 100, 60, 30),
    ("hello", 2, 2),
]


@pytest.mark.skipif(shutil.which("fc-match") is None, reason="fontconfig not installed")
def test_fit_matches_python(tmp_path):
    ann = tmp_path / "ann.txt"
    ann.write_text("".join(f"text|0|1|0|0|{w}|{h}|{t}\n" for t, w, h in FIT_CASES),
                   encoding="utf-8")
    res = subprocess.run(["bash", str(SCRIPT), "missing.mp4", str(ann), "y.mp4"],
                         capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "VIDNOTE_PRINT_FIT": "1"})
    assert res.returncode == 0, res.stderr
    got = []
    for ln in res.stdout.splitlines():
        if ln.startswith("fit|"):
            _, _no, size, ok = ln.split("|")
            got.append([int(size), ok == "1", []])
        else:
            got[-1][2].append(ln[len("  |"):])
    assert len(got) == len(FIT_CASES)
    for (text, w, h), (size, ok, lines) in zip(FIT_CASES, got):
        want = textfit.fit_text(text, w, h)
        assert (size, ok, lines) == (want.size, want.fits, want.lines), text
