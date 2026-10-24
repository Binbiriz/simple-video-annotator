import pytest

from vidnote.canvasstate import (
    LINE,
    POINT,
    REGION,
    FormGeometry,
    MarkerState,
    selection_dimmed,
    selection_geometry,
)
from vidnote.models import ARROW, BLUR, TEXT, Annotation


def form(x=10, y=20, w=100, h=50, x2=200, y2=150) -> FormGeometry:
    return FormGeometry(x, y, w, h, x2, y2)


def box(kind=BLUR) -> Annotation:
    return Annotation(kind=kind, start=1.0, end=3.0, x=10, y=20, w=100, h=50,
                      text="hi" if kind == TEXT else "")


def arrow() -> Annotation:
    return Annotation(kind=ARROW, start=1.0, end=3.0, x=10, y=20, x2=200, y2=150)


def test_no_marker_has_no_shape():
    m = MarkerState()
    assert not m.active
    assert m.shape(form()) is None


def test_point_marker_is_square_centred_and_follows_form():
    m = MarkerState()
    m.pick(POINT)
    assert m.active
    assert m.shape(form(x=50, y=60)) == ("rect", (44, 54, 12, 12))
    assert m.shape(form(x=70, y=80)) == ("rect", (64, 74, 12, 12))


def test_region_marker_follows_form():
    m = MarkerState()
    m.pick(REGION)
    assert m.shape(form(x=1, y=2, w=30, h=40)) == ("rect", (1, 2, 30, 40))
    assert m.shape(form(x=5, y=6, w=70, h=80)) == ("rect", (5, 6, 70, 80))


@pytest.mark.parametrize("w,h", [(0, 50), (100, 0), (0, 0)])
def test_region_marker_without_size_has_no_shape(w, h):
    m = MarkerState()
    m.pick(REGION)
    assert m.shape(form(w=w, h=h)) is None


def test_line_marker_follows_four_coordinates():
    m = MarkerState()
    m.pick(LINE)
    assert m.shape(form(x=1, y=2, x2=3, y2=4)) == ("line", (1, 2, 3, 4))
    assert m.shape(form(x=5, y=6, x2=7, y2=8)) == ("line", (5, 6, 7, 8))


def test_clear_removes_marker():
    m = MarkerState()
    m.pick(REGION)
    m.clear()
    assert not m.active
    assert m.shape(form()) is None


def test_pick_unknown_kind_raises():
    m = MarkerState()
    with pytest.raises(ValueError):
        m.pick("circle")
    assert not m.active


def test_expire_point_clears_point_only():
    m = MarkerState()
    m.pick(POINT)
    assert m.expire_point() is True
    assert not m.active


@pytest.mark.parametrize("kind", [REGION, LINE])
def test_expire_point_leaves_other_markers(kind):
    m = MarkerState()
    m.pick(kind)
    assert m.expire_point() is False
    assert m.kind == kind


def test_expire_point_without_marker():
    assert MarkerState().expire_point() is False


def test_region_picked_after_click_survives_click_expiry():
    m = MarkerState()
    m.pick(POINT)
    m.pick(REGION)
    assert m.expire_point() is False
    assert m.shape(form()) is not None


def test_selection_geometry_box_form_equal_to_stored():
    assert selection_geometry(box(), BLUR, form(), False) == (10, 20, 100, 50)


def test_selection_geometry_arrow_form_equal_to_stored():
    assert selection_geometry(arrow(), ARROW, form(), False) == (10, 20, 200, 150)


def test_selection_geometry_box_follows_form():
    assert selection_geometry(box(), BLUR, form(x=11, y=22, w=33, h=44), False) == (11, 22, 33, 44)
    assert selection_geometry(box(TEXT), TEXT, form(w=60), False) == (10, 20, 60, 50)


def test_selection_geometry_arrow_follows_form():
    f = form(x=1, y=2, x2=3, y2=4)
    assert selection_geometry(arrow(), ARROW, f, False) == (1, 2, 3, 4)


def test_selection_geometry_kind_mismatch_uses_stored():
    f = form(x=1, y=2, w=3, h=4, x2=5, y2=6)
    assert selection_geometry(box(), ARROW, f, False) == (10, 20, 100, 50)
    assert selection_geometry(arrow(), BLUR, f, False) == (10, 20, 200, 150)


def test_selection_geometry_text_and_blur_are_different_kinds():
    f = form(x=1, y=2, w=3, h=4)
    assert selection_geometry(box(BLUR), TEXT, f, False) == (10, 20, 100, 50)


def test_selection_geometry_marker_active_uses_stored():
    assert selection_geometry(box(), BLUR, form(x=1), True) == (10, 20, 100, 50)
    assert selection_geometry(arrow(), ARROW, form(x=1), True) == (10, 20, 200, 150)


@pytest.mark.parametrize("w,h", [(0, 50), (100, 0)])
def test_selection_geometry_degenerate_box_uses_stored(w, h):
    assert selection_geometry(box(), BLUR, form(w=w, h=h), False) == (10, 20, 100, 50)


def test_selection_geometry_identical_arrow_points_use_stored():
    f = form(x=5, y=6, x2=5, y2=6)
    assert selection_geometry(arrow(), ARROW, f, False) == (10, 20, 200, 150)


def test_selection_dimmed_bounds():
    a = box()
    assert selection_dimmed(a, 1.0) is False
    assert selection_dimmed(a, 2.0) is False
    assert selection_dimmed(a, 3.0) is False
    assert selection_dimmed(a, 0.999) is True
    assert selection_dimmed(a, 3.001) is True
