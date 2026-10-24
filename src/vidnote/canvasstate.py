"""Rules for the two yellow canvas graphics: the "new" marker and the selection highlight.

No Qt imports, so the rules can be tested without a display.
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Tuple

from .models import ARROW, Annotation

POINT, REGION, LINE = "point", "region", "line"
POINT_MARKER_PX = 12  # side of the click marker square, video px
POINT_MARKER_MS = 1000  # a click marker disappears after this long


class FormGeometry(NamedTuple):
    x: int
    y: int
    w: int
    h: int
    x2: int
    y2: int


class MarkerState:
    """The marker for a picked point, region or line; it always follows the form values."""

    def __init__(self) -> None:
        self.kind: Optional[str] = None  # None = no marker

    def pick(self, kind: str) -> None:
        if kind not in (POINT, REGION, LINE):
            raise ValueError(f"Unknown marker kind: {kind!r}")
        self.kind = kind

    def clear(self) -> None:
        self.kind = None

    def expire_point(self) -> bool:
        """Clear a click marker only; True if it was cleared."""
        if self.kind == POINT:
            self.kind = None
            return True
        return False

    @property
    def active(self) -> bool:
        return self.kind is not None

    def shape(self, form: FormGeometry) -> Optional[Tuple[str, Tuple[float, ...]]]:
        """What the view must draw: ("rect", (x, y, w, h)), ("line", (x1, y1, x2, y2)) or None."""
        if self.kind == POINT:
            half = POINT_MARKER_PX // 2
            return "rect", (form.x - half, form.y - half, POINT_MARKER_PX, POINT_MARKER_PX)
        if self.kind == REGION:
            if form.w <= 0 or form.h <= 0:
                return None
            return "rect", (form.x, form.y, form.w, form.h)
        if self.kind == LINE:
            return "line", (form.x, form.y, form.x2, form.y2)
        return None


def selection_geometry(stored: Annotation, form_kind: str, form: FormGeometry,
                       marker_active: bool) -> Tuple[int, ...]:
    """(x, y, w, h) for a box, (x1, y1, x2, y2) for an arrow.

    The live form values are used only when the form edits the same kind of annotation, no
    marker is active and the form geometry is valid; otherwise the stored geometry.
    """
    if stored.kind == ARROW:
        stored_geom = (stored.x, stored.y, stored.x2, stored.y2)
        valid = (form.x, form.y) != (form.x2, form.y2)
        live = (form.x, form.y, form.x2, form.y2)
    else:
        stored_geom = (stored.x, stored.y, stored.w, stored.h)
        valid = form.w > 0 and form.h > 0
        live = (form.x, form.y, form.w, form.h)
    if form_kind == stored.kind and not marker_active and valid:
        return live
    return stored_geom


def selection_dimmed(stored: Annotation, t: float) -> bool:
    return not stored.is_active(t)
