"""Arrow geometry shared by the canvas preview and the tests. No Qt imports.

scripts/annotate.sh mirrors these formulas in the `geq` alpha expression it uses to draw the
overlay image of each arrow; keep both in sync (constants and formulas).

With t = thickness, an arrow from (x1, y1) to (x2, y2) is one shape:

- head length Lh0 = 4*t + 6 and head half-width Hw0 = 2*t + 3;
- len = distance between the points, n = number of ends with an arrowhead (at least 1);
  k = min(1, len / (n * Lh0)) shrinks the heads of very short arrows (Lh = Lh0*k, Hw = Hw0*k);
- the shaft is a rectangle of width t along the axis from u0 to u1, with flat caps:
  u0 = Lh - 1 if the start has a head else 0, u1 = len - Lh + 1 if the end has a head else len
  (the 1 px overlap hides the seam between shaft and head);
- a head is an isosceles triangle with its tip at the end point, length Lh, base half-width Hw.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from .models import STYLE_ARROW

HEAD_LEN_K, HEAD_LEN_ADD = 4, 6  # Lh0 = 4*t + 6
HEAD_HALF_K, HEAD_HALF_ADD = 2, 3  # Hw0 = 2*t + 3
ALPHA = 0.5  # fixed opacity of the whole arrow

Point = Tuple[float, float]


@dataclass
class ArrowGeometry:
    length: float
    ux: float  # unit vector along the axis, start -> end
    uy: float
    head_len: float  # Lh, after scaling
    head_half: float  # Hw, after scaling
    u0: float  # shaft extent along the axis
    u1: float
    start_head: bool
    end_head: bool


def padding(thickness: int) -> int:
    """Padding around the end points' bounding box used for the overlay image (= Hw0 + 2)."""
    return HEAD_HALF_K * thickness + HEAD_HALF_ADD + 2


def geometry(x1: float, y1: float, x2: float, y2: float, thickness: int,
             start_style: str, end_style: str) -> ArrowGeometry:
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        raise ValueError("start and end points must differ")
    start_head = start_style == STYLE_ARROW
    end_head = end_style == STYLE_ARROW
    lh0 = HEAD_LEN_K * thickness + HEAD_LEN_ADD
    hw0 = HEAD_HALF_K * thickness + HEAD_HALF_ADD
    n = max(1, int(start_head) + int(end_head))
    k = min(1.0, length / (n * lh0))
    lh, hw = lh0 * k, hw0 * k
    u0 = lh - 1 if start_head else 0.0
    u1 = length - lh + 1 if end_head else length
    return ArrowGeometry(length, (x2 - x1) / length, (y2 - y1) / length, lh, hw, u0, u1,
                         start_head, end_head)


def polygons(x1: float, y1: float, x2: float, y2: float, thickness: int,
             start_style: str, end_style: str) -> List[List[Point]]:
    """Shaft rectangle plus 0-2 head triangles, in scene coordinates."""
    g = geometry(x1, y1, x2, y2, thickness, start_style, end_style)
    nx, ny = -g.uy, g.ux  # unit normal
    half = thickness / 2

    def at(u: float, v: float) -> Point:
        return (x1 + g.ux * u + nx * v, y1 + g.uy * u + ny * v)

    result = [[at(g.u0, -half), at(g.u1, -half), at(g.u1, half), at(g.u0, half)]]
    if g.end_head:
        result.append([at(g.length, 0), at(g.length - g.head_len, -g.head_half),
                       at(g.length - g.head_len, g.head_half)])
    if g.start_head:
        result.append([at(0, 0), at(g.head_len, -g.head_half), at(g.head_len, g.head_half)])
    return result


def _clip01(v: float) -> float:
    return min(max(v, 0.0), 1.0)


def coverage(px: float, py: float, x1: float, y1: float, x2: float, y2: float, thickness: int,
             start_style: str, end_style: str) -> float:
    """Anti-aliased coverage (0..1) of the arrow at a continuous point (same as the geq alpha)."""
    g = geometry(x1, y1, x2, y2, thickness, start_style, end_style)
    dx, dy = px - x1, py - y1
    u = dx * g.ux + dy * g.uy
    v = abs(-dx * g.uy + dy * g.ux)
    best = _clip01(min(u - g.u0 + 0.5, g.u1 - u + 0.5, thickness / 2 - v + 0.5))
    norm = math.hypot(g.head_len, g.head_half)

    def head(s: float) -> float:
        return _clip01(min(s + 0.5, g.head_len - s + 0.5,
                           (g.head_half * s / g.head_len - v) * g.head_len / norm + 0.5))

    if g.end_head:
        best = max(best, head(g.length - u))
    if g.start_head:
        best = max(best, head(u))
    return best


def distance_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - x1, py - y1)
    t = min(max(((px - x1) * dx + (py - y1) * dy) / length_sq, 0.0), 1.0)
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
