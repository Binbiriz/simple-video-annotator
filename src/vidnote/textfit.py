"""Fit text into a box: font size and line breaks. No Qt imports.

scripts/annotate.sh mirrors this algorithm (integer math, same constants); keep the two in
sync. The model assumes a monospace font with a fixed glyph advance.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import List

MAX_SIZE = 14  # default and maximum font size, px
MIN_SIZE = 8  # minimum font size, px
PAD = 4  # padding between the box edge and the text, px
LINE_H_PM = 1150  # line height = size * LINE_H_PM / 1000
# glyph advance = size * ADV_PM / 1000; a bit wide on purpose so any common monospace font
# fits (Ubuntu Mono is ~560, DejaVu Sans Mono ~602)
DEFAULT_ADV_PM = 605
PREFERRED_FAMILY = "Ubuntu Mono"


@dataclass
class FitResult:
    size: int
    lines: List[str]
    fits: bool


@dataclass
class FontInfo:
    family: str
    file: str
    preferred: bool


def line_height(size: int) -> int:
    return size * LINE_H_PM // 1000


def wrap(text: str, cols: int) -> List[str]:
    """Greedy word wrap at `cols` characters; words longer than a line are hard-broken."""
    cols = max(1, cols)
    lines: List[str] = []
    cur = ""
    for word in text.split():
        while len(word) > cols:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:cols])
            word = word[cols:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= cols:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _cols(avail_w: int, size: int, adv_pm: int) -> int:
    return max(1, max(avail_w, 0) * 1000 // (size * adv_pm))


def fit_text(text: str, w: int, h: int, adv_pm: int = DEFAULT_ADV_PM) -> FitResult:
    avail_w = w - 2 * PAD
    avail_h = h - 2 * PAD
    for size in range(MAX_SIZE, MIN_SIZE - 1, -1):
        lines = wrap(text, _cols(avail_w, size, adv_pm))
        if len(lines) * line_height(size) <= avail_h:
            return FitResult(size, lines, True)
    return FitResult(MIN_SIZE, wrap(text, _cols(avail_w, MIN_SIZE, adv_pm)), False)


def _fc_match(pattern: str) -> tuple:
    out = subprocess.run(
        ["fc-match", "-f", "%{family}|%{file}", pattern],
        capture_output=True, text=True, check=True,
    ).stdout
    family, _, path = out.partition("|")
    return family.split(",")[0].strip(), path.strip()


@lru_cache(maxsize=1)
def resolve_font() -> FontInfo:
    try:
        family, path = _fc_match(PREFERRED_FAMILY)
        if family.lower() == PREFERRED_FAMILY.lower():
            return FontInfo(family, path, True)
        family, path = _fc_match("monospace")
        return FontInfo(family or "monospace", path, False)
    except (OSError, subprocess.SubprocessError):
        return FontInfo("monospace", "", False)
