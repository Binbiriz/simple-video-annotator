"""End-to-end test of scripts/annotate.sh. Skipped when ffmpeg or drawtext is missing."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "annotate.sh"

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_render_text_and_blur(tmp_path):
    src = tmp_path / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc=duration=3:size=640x360:rate=25", "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )
    ann = tmp_path / "ann.txt"
    ann.write_text("text 0.5 2 20 20 Hello world\nblur 1 2.5 100 100 200 100\n")
    out = tmp_path / "out.mp4"
    res = subprocess.run(["bash", str(SCRIPT), str(src), str(ann), str(out)],
                         capture_output=True, text=True)
    if "No such filter: 'drawtext'" in res.stderr:
        pytest.skip("ffmpeg built without drawtext")
    assert res.returncode == 0, res.stderr
    assert out.exists() and out.stat().st_size > 0


def test_empty_annotation_file_fails(tmp_path):
    ann = tmp_path / "ann.txt"
    ann.write_text("# nothing here\n")
    res = subprocess.run(["bash", str(SCRIPT), "x.mp4", str(ann), "y.mp4"],
                         capture_output=True, text=True)
    assert res.returncode != 0
