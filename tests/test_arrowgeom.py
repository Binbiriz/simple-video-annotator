import math

import pytest

from vidnote import arrowgeom as ag

T = 4


def cov(px, py, x1, y1, x2, y2, t=T, ss="none", es="arrow"):
    return ag.coverage(px, py, x1, y1, x2, y2, t, ss, es)


def test_geometry_rejects_identical_points():
    with pytest.raises(ValueError):
        ag.geometry(5, 5, 5, 5, T, "none", "arrow")
    with pytest.raises(ValueError):
        ag.polygons(5, 5, 5, 5, T, "none", "arrow")


def test_padding():
    assert ag.padding(4) == 2 * 4 + 5
    assert ag.padding(30) == 65


def test_horizontal_shaft_and_head_coverage():
    # arrow from (50,100) to (250,100), t=4: head length 22, half-width 11
    assert cov(100.5, 100.5, 50, 100, 250, 100) == pytest.approx(1)  # inside the shaft
    assert cov(100.5, 99.5, 50, 100, 250, 100) == pytest.approx(1)
    assert cov(100.5, 104.5, 50, 100, 250, 100) == 0  # well outside
    assert cov(100.5, 102, 50, 100, 250, 100) == pytest.approx(0.5)  # t/2 away: edge, 50%
    assert cov(230, 100, 50, 100, 250, 100) == pytest.approx(1)  # inside the head
    assert cov(230, 111, 50, 100, 250, 100) == 0  # head half-width at s=20 is 10: outside
    assert cov(260, 100, 50, 100, 250, 100) == 0  # beyond the tip
    assert cov(40, 100, 50, 100, 250, 100) == 0  # before the start


def test_none_none_is_a_plain_bar_and_arrow_arrow_has_two_heads():
    # a head is wide (half-width 9 at 18 px from the tip); the bar is only 2 px each side
    def at(x, y, ss, es):
        return cov(x, y, 50, 100, 250, 100, ss=ss, es=es)

    assert at(232, 100, "none", "none") == pytest.approx(1)
    assert at(232, 106, "none", "none") == 0
    assert at(68, 106, "none", "none") == 0
    assert at(232, 106, "none", "arrow") == pytest.approx(1)  # end head
    assert at(68, 106, "none", "arrow") == 0  # plain start
    assert at(68, 106, "arrow", "arrow") == pytest.approx(1)  # head at both ends
    assert at(232, 106, "arrow", "arrow") == pytest.approx(1)
    assert at(150, 106, "arrow", "arrow") == 0


@pytest.mark.parametrize("ss,es", [("none", "none"), ("none", "arrow"), ("arrow", "arrow")])
def test_reversed_arrow_is_the_mirror_image(ss, es):
    # an arrow from (250,100) to (50,100) with swapped styles equals the original one
    for x in (45, 55, 100, 200, 235, 245, 255):
        for y in (92, 97.5, 100, 103, 108):
            a = cov(x, y, 50, 100, 250, 100, ss=ss, es=es)
            b = cov(x, y, 250, 100, 50, 100, ss=es, es=ss)
            assert a == pytest.approx(b, abs=1e-9)


def test_vertical_and_diagonal_match_the_horizontal_one():
    # the sample (u, v) along/across the axis gives the same coverage at any angle
    for dx, dy in [(0, 200), (141.4213562373095, 141.4213562373095), (-200, 0)]:
        ux, uy = dx / 200, dy / 200
        for u, v in [(10, 0), (100, 1.5), (100, 2.4), (190, 6), (199, 0.5), (215, 0), (5, 3)]:
            px, py = 100 + ux * u - uy * v, 100 + uy * u + ux * v
            rot = cov(px, py, 100, 100, 100 + dx, 100 + dy, ss="arrow")
            horiz = cov(100 + u, 100 + v, 100, 100, 300, 100, ss="arrow")
            assert rot == pytest.approx(horiz, abs=1e-6)


def test_short_arrow_with_large_thickness_keeps_heads_inside_the_line():
    for ss, es in [("none", "arrow"), ("arrow", "arrow")]:
        g = ag.geometry(10, 10, 20, 10, 30, ss, es)  # length 10, head length 126 unscaled
        assert g.u0 <= g.u1
        n = int(g.start_head) + int(g.end_head)
        assert n * g.head_len <= g.length + 1e-9
        assert g.head_len > 0 and g.head_half > 0
        for poly in ag.polygons(10, 10, 20, 10, 30, ss, es)[1:]:
            xs = [p[0] for p in poly]
            assert min(xs) >= 10 - 1e-9 and max(xs) <= 20 + 1e-9


def test_polygons_bounding_box_matches_the_coverage_support():
    cases = [(50, 100, 250, 100, "none", "arrow"), (60, 40, 200, 180, "arrow", "arrow"),
             (200, 180, 60, 40, "none", "none"), (30, 30, 34, 31, "arrow", "arrow")]
    for x1, y1, x2, y2, ss, es in cases:
        polys = ag.polygons(x1, y1, x2, y2, T, ss, es)
        xs = [p[0] for poly in polys for p in poly]
        ys = [p[1] for poly in polys for p in poly]
        for px in range(0, 260, 3):
            for py in range(0, 220, 3):
                inside = min(xs) - 1 <= px <= max(xs) + 1 and min(ys) - 1 <= py <= max(ys) + 1
                if not inside:
                    assert ag.coverage(px + 0.5, py + 0.5, x1, y1, x2, y2, T, ss, es) == 0
        pad = ag.padding(T)  # everything painted lies inside the overlay image bounds
        assert min(xs) >= min(x1, x2) - pad and max(xs) <= max(x1, x2) + pad
        assert min(ys) >= min(y1, y2) - pad and max(ys) <= max(y1, y2) + pad


def test_polygon_shapes():
    polys = ag.polygons(0, 0, 100, 0, 4, "none", "arrow")
    assert len(polys) == 2 and len(polys[0]) == 4 and len(polys[1]) == 3
    tip = polys[1][0]
    assert tip == pytest.approx((100, 0))
    assert len(ag.polygons(0, 0, 100, 0, 4, "none", "none")) == 1
    assert len(ag.polygons(0, 0, 100, 0, 4, "arrow", "arrow")) == 3


def test_distance_to_segment():
    assert ag.distance_to_segment(5, 3, 0, 0, 10, 0) == pytest.approx(3)  # beside it
    assert ag.distance_to_segment(5, 0, 0, 0, 10, 0) == 0  # on the line
    assert ag.distance_to_segment(13, 4, 0, 0, 10, 0) == pytest.approx(5)  # beyond the end
    assert ag.distance_to_segment(-3, -4, 0, 0, 10, 0) == pytest.approx(5)  # before the start
    assert ag.distance_to_segment(3, 4, 0, 0, 0, 0) == pytest.approx(5)  # degenerate segment
    assert ag.distance_to_segment(5, 5, 0, 0, 10, 10) == pytest.approx(0)
    assert ag.distance_to_segment(0, 10, 0, 0, 10, 10) == pytest.approx(10 / math.sqrt(2))
