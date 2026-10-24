"""Plain data model for annotations. No Qt imports, so it is easy to test."""

from __future__ import annotations

from dataclasses import dataclass

from . import colors

TEXT = "text"
BLUR = "blur"
ARROW = "arrow"

STYLE_NONE = "none"
STYLE_ARROW = "arrow"
ARROW_STYLES = (STYLE_NONE, STYLE_ARROW)
DEFAULT_THICKNESS = 4  # video px
MIN_THICKNESS = 1
MAX_THICKNESS = 30
DEFAULT_ARROW_COLOR = "#e03131"
DEFAULT_START_STYLE = STYLE_NONE
DEFAULT_END_STYLE = STYLE_ARROW

DEFAULT_SIZE = 14  # font size, video px
MIN_SIZE = 8
MAX_SIZE = 72
DEFAULT_BOX_COLOR = "#000000"
DEFAULT_TEXT_COLOR = "#ffffff"


@dataclass
class Annotation:
    kind: str  # TEXT, BLUR or ARROW
    start: float  # seconds
    end: float  # seconds
    x: int  # video pixels, origin at top-left
    y: int
    w: int = 0  # box size, used by blur and text
    h: int = 0
    text: str = ""  # text only
    size: int = DEFAULT_SIZE  # text only: font size in video px
    box_color: str = DEFAULT_BOX_COLOR  # text only: '#rrggbb', drawn at 50% opacity
    text_color: str = DEFAULT_TEXT_COLOR  # text only: black or white
    x2: int = 0  # arrow only: end point (x, y is the start point; w and h stay 0)
    y2: int = 0
    thickness: int = DEFAULT_THICKNESS  # arrow only: line width in video px
    color: str = DEFAULT_ARROW_COLOR  # arrow only: '#rrggbb', drawn at 50% opacity
    start_style: str = DEFAULT_START_STYLE  # arrow only: STYLE_NONE or STYLE_ARROW
    end_style: str = DEFAULT_END_STYLE

    def is_active(self, t: float) -> bool:
        return self.start <= t <= self.end

    def validate(self) -> None:
        if self.kind not in (TEXT, BLUR, ARROW):
            raise ValueError(f"Unknown annotation type: {self.kind!r}")
        if self.start < 0:
            raise ValueError("Start time cannot be negative.")
        if self.end <= self.start:
            raise ValueError("End time must be after start time.")
        if self.kind == ARROW:
            self._validate_arrow()
            return
        if self.kind == BLUR and (self.w <= 0 or self.h <= 0):
            raise ValueError("A blur needs a region: drag a rectangle on the video.")
        if self.kind == TEXT and (self.w <= 0 or self.h <= 0):
            raise ValueError("A text annotation needs a box: drag a rectangle on the video.")
        if self.kind == TEXT and not self.text.strip():
            raise ValueError("A text annotation needs some text.")
        if self.kind == TEXT:
            if not MIN_SIZE <= self.size <= MAX_SIZE:
                raise ValueError(f"Font size must be between {MIN_SIZE} and {MAX_SIZE} px.")
            try:
                colors.normalize_hex(self.box_color)
            except ValueError as exc:
                raise ValueError(f"Box colour: {exc}") from None
            try:
                text_color = colors.normalize_hex(self.text_color)
            except ValueError:
                text_color = ""
            if text_color not in colors.TEXT_COLORS:
                raise ValueError("Text colour must be black or white.")

    def _validate_arrow(self) -> None:
        if (self.x, self.y) == (self.x2, self.y2):
            raise ValueError("An arrow needs two different points: drag a line on the video.")
        if not MIN_THICKNESS <= self.thickness <= MAX_THICKNESS:
            raise ValueError(
                f"Thickness must be between {MIN_THICKNESS} and {MAX_THICKNESS} px.")
        try:
            colors.normalize_hex(self.color)
        except ValueError as exc:
            raise ValueError(f"Colour: {exc}") from None
        for style in (self.start_style, self.end_style):
            if style not in ARROW_STYLES:
                raise ValueError(f"Unknown end style {style!r}.")
