"""Reading and writing the annotation text file used by scripts/annotate.sh.

Format (one annotation per line, '#' starts a comment):

    text|start|end|x|y|w|h|size|boxcolor|textcolor|text
                                     text in a box; size is the font size in px (8-72), colours
                                     are #rrggbb (text colour: #000000 or #ffffff only); the
                                     text is the rest of the line and may contain '|'
    blur|start|end|x|y|w|h           blur region

Whitespace around the keyword and each field is ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from . import colors
from .models import BLUR, MAX_SIZE, MIN_SIZE, TEXT, Annotation

HEADER = (
    "# vidnote annotations\n"
    "# text|start|end|x|y|w|h|size|boxcolor|textcolor|text\n"
    "# blur|start|end|x|y|w|h\n"
)


OLD_FORMATS = "older text formats are no longer supported"
TEXT_FORMAT_ERROR = (
    "text lines need: text|start|end|x|y|w|h|size|boxcolor|textcolor|text "
    f"({OLD_FORMATS})"
)


def fmt_time(t: float) -> str:
    """3 decimals, trailing zeros removed: 2.5 -> '2.5', 3.0 -> '3', 0 -> '0'."""
    return f"{t:.3f}".rstrip("0").rstrip(".") or "0"


def to_line(a: Annotation) -> str:
    if a.kind == BLUR:
        return "|".join(["blur", fmt_time(a.start), fmt_time(a.end),
                         str(a.x), str(a.y), str(a.w), str(a.h)])
    text = " ".join(a.text.split())  # single line, collapse whitespace
    return "|".join(["text", fmt_time(a.start), fmt_time(a.end),
                     str(a.x), str(a.y), str(a.w), str(a.h), str(a.size),
                     colors.normalize_hex(a.box_color), colors.normalize_hex(a.text_color),
                     text])


def parse_line(line: str) -> Optional[Annotation]:
    """Return an Annotation, or None for blank/comment lines. Raises ValueError if malformed."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    kind = line.split("|", 1)[0].strip()
    try:
        if kind == "blur":
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 7:
                raise ValueError("blur lines need: blur|start|end|x|y|w|h")
            s, e = float(parts[1]), float(parts[2])
            x, y, w, h = (int(p) for p in parts[3:7])
            return Annotation(BLUR, s, e, x, y, w, h)
        if kind == "text":
            parts = line.split("|", 10)
            if len(parts) != 11:
                raise ValueError(TEXT_FORMAT_ERROR)
            try:
                x, y, w, h = (int(p) for p in parts[3:7])
            except ValueError:
                raise ValueError(f"x, y, w and h must be whole numbers ({OLD_FORMATS})") from None
            try:
                size = int(parts[7])
            except ValueError:
                raise ValueError(f"size must be a whole number ({OLD_FORMATS})") from None
            if w <= 0 or h <= 0:
                raise ValueError("w and h must be greater than 0")
            if not MIN_SIZE <= size <= MAX_SIZE:
                raise ValueError(f"size must be between {MIN_SIZE} and {MAX_SIZE}")
            box_color = colors.normalize_hex(parts[8])
            text_color = colors.normalize_hex(parts[9])
            if text_color not in colors.TEXT_COLORS:
                raise ValueError("text colour must be #000000 or #ffffff")
            text = parts[10].strip()
            if not text:
                raise ValueError("text is empty")
            return Annotation(TEXT, float(parts[1]), float(parts[2]), x, y, w, h, text=text,
                              size=size, box_color=box_color, text_color=text_color)
        raise ValueError(
            "unknown line type; expected 'text|...' or 'blur|...' "
            "(old whitespace-separated lines are no longer supported)"
        )
    except (ValueError, IndexError) as exc:
        raise ValueError(str(exc) or "invalid line") from exc


def dumps(annotations: List[Annotation]) -> str:
    ordered = sorted(annotations, key=lambda a: (a.start, a.end))
    return HEADER + "".join(to_line(a) + "\n" for a in ordered)


def save(annotations: List[Annotation], path) -> None:
    Path(path).write_text(dumps(annotations), encoding="utf-8")


def loads(content: str) -> Tuple[List[Annotation], List[Tuple[int, str, str]]]:
    """Parse text. Returns (annotations, skipped) where skipped holds (lineno, line, error)."""
    result: List[Annotation] = []
    skipped: List[Tuple[int, str, str]] = []
    for no, line in enumerate(content.splitlines(), start=1):
        try:
            a = parse_line(line)
        except ValueError as exc:
            skipped.append((no, line, str(exc)))
            continue
        if a is not None:
            result.append(a)
    return result, skipped


def load(path) -> Tuple[List[Annotation], List[Tuple[int, str, str]]]:
    return loads(Path(path).read_text(encoding="utf-8"))
