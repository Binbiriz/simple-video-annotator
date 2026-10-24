"""End-to-end test of scripts/annotate.sh. Skipped when ffmpeg or drawtext is missing."""

import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_render_text_and_blur(tmp_path):
    _render(tmp_path, "text|0.5|2|20|20|Hello world\nblur|1|2.5|100|100|200|100\n")


def test_render_padded_fields_pipe_in_text_and_crlf(tmp_path):
    _render(tmp_path, " text | 0.5 | 2 | 20 | 20 | a | b \r\nblur|1|2.5|100|100|200|100\r\n")


def _run_bad(tmp_path, content):
    ann = tmp_path / "ann.txt"
    ann.write_text(content)
    res = subprocess.run(["bash", str(SCRIPT), "missing.mp4", str(ann), "y.mp4"],
                         capture_output=True, text=True)
    assert res.returncode != 0
    return res.stderr


@pytest.mark.parametrize("line", [
    "text 0.5 2 20 20 Hello",
    "0.5 2 20 20 Hello",
    "text|0|1|(w-text_w)/2|5|hi",
    "blur|1|2|3|4",
    "blur|1|2|3|4|5|6|7",
    "text|0|1|2|3|   ",
])
def test_malformed_line_fails_with_line_number(tmp_path, line):
    err = _run_bad(tmp_path, f"# header\ntext|0|1|2|3|ok\n{line}\n")
    assert "ann.txt:3:" in err


def test_empty_annotation_file_fails(tmp_path):
    ann = tmp_path / "ann.txt"
    ann.write_text("# nothing here\n")
    res = subprocess.run(["bash", str(SCRIPT), "x.mp4", str(ann), "y.mp4"],
                         capture_output=True, text=True)
    assert res.returncode != 0
