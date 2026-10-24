"""Reading and writing the annotation text file used by scripts/annotate.sh.

Format (one annotation per line, '#' starts a comment):

    text|start|end|x|y|w|h|size|boxcolor|textcolor|text
                                     text in a box; size is the font size in px (8-72), colours
                                     are #rrggbb (text colour: #000000 or #ffffff only); the
                                     text is the rest of the line and may contain '|'
    blur|start|end|x|y|w|h           blur region
    arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle
                                     straight arrow from (x1,y1) to (x2,y2); thickness is 1-30 px,
                                     color #rrggbb (drawn at 50% opacity), styles are 'none' or
                                     'arrow' (an arrowhead) for the start and the end

Whitespace around the keyword and each field is ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from . import colors
from .models import (
    ARROW,
    ARROW_STYLES,
    BLUR,
    MAX_SIZE,
    MAX_THICKNESS,
    MIN_SIZE,
    MIN_THICKNESS,
    TEXT,
    Annotation,
)

HEADER = (
    "# vidnote annotations\n"
    "# text|start|end|x|y|w|h|size|boxcolor|textcolor|text\n"
    "# blur|start|end|x|y|w|h\n"
    "# arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle\n"
)


OLD_FORMATS = "older text formats are no longer supported"
TEXT_FORMAT_ERROR = (
    "text lines need: text|start|end|x|y|w|h|size|boxcolor|textcolor|text "
    f"({OLD_FORMATS})"
)
ARROW_FORMAT_ERROR = (
    "arrow lines need: arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle"
)


def fmt_time(t: float) -> str:
    """3 decimals, trailing zeros removed: 2.5 -> '2.5', 3.0 -> '3', 0 -> '0'."""
    return f"{t:.3f}".rstrip("0").rstrip(".") or "0"


def to_line(a: Annotation) -> str:
    if a.kind == BLUR:
        return "|".join(["blur", fmt_time(a.start), fmt_time(a.end),
                         str(a.x), str(a.y), str(a.w), str(a.h)])
    if a.kind == ARROW:
        return "|".join(["arrow", fmt_time(a.start), fmt_time(a.end),
                         str(a.x), str(a.y), str(a.x2), str(a.y2), str(a.thickness),
                         colors.normalize_hex(a.color), a.start_style, a.end_style])
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
        if kind == "arrow":
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 11:
                raise ValueError(ARROW_FORMAT_ERROR)
            s, e = float(parts[1]), float(parts[2])
            try:
                x1, y1, x2, y2 = (int(p) for p in parts[3:7])
            except ValueError:
                raise ValueError("x1, y1, x2 and y2 must be whole numbers") from None
            try:
                thickness = int(parts[7])
            except ValueError:
                raise ValueError("thickness must be a whole number") from None
            if (x1, y1) == (x2, y2):
                raise ValueError("start and end points must differ")
            if not MIN_THICKNESS <= thickness <= MAX_THICKNESS:
                raise ValueError(f"thickness must be between {MIN_THICKNESS} and {MAX_THICKNESS}")
            color = colors.normalize_hex(parts[8])
            styles = [p.lower() for p in parts[9:11]]
            for style in styles:
                if style not in ARROW_STYLES:
                    raise ValueError(
                        f"unknown end style {style!r}; expected {' or '.join(ARROW_STYLES)}")
            return Annotation(ARROW, s, e, x1, y1, x2=x2, y2=y2, thickness=thickness,
                              color=color, start_style=styles[0], end_style=styles[1])
        raise ValueError(
            "unknown line type; expected 'text|...', 'blur|...' or 'arrow|...' "
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
