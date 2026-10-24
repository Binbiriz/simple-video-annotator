"""Plain data model for annotations. No Qt imports, so it is easy to test."""

from __future__ import annotations

from dataclasses import dataclass

from . import colors

TEXT = "text"
BLUR = "blur"

DEFAULT_SIZE = 14  # font size, video px
MIN_SIZE = 8
MAX_SIZE = 72
DEFAULT_BOX_COLOR = "#000000"
DEFAULT_TEXT_COLOR = "#ffffff"


@dataclass
class Annotation:
    kind: str  # TEXT or BLUR
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

    def is_active(self, t: float) -> bool:
        return self.start <= t <= self.end

    def validate(self) -> None:
        if self.kind not in (TEXT, BLUR):
            raise ValueError(f"Unknown annotation type: {self.kind!r}")
        if self.start < 0:
            raise ValueError("Start time cannot be negative.")
        if self.end <= self.start:
            raise ValueError("End time must be after start time.")
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
