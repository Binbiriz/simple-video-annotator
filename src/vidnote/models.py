"""Plain data model for annotations. No Qt imports, so it is easy to test."""

from __future__ import annotations

from dataclasses import dataclass

TEXT = "text"
BLUR = "blur"


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
