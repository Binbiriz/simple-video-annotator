import pytest

from vidnote.models import (
    ARROW,
    BLUR,
    DEFAULT_BOX_COLOR,
    DEFAULT_END_STYLE,
    DEFAULT_SIZE,
    DEFAULT_START_STYLE,
    DEFAULT_TEXT_COLOR,
    DEFAULT_THICKNESS,
    TEXT,
    Annotation,
)


def test_is_active():
    a = Annotation(TEXT, 2, 4, 0, 0, 100, 40, text="x")
    assert a.is_active(2) and a.is_active(3) and a.is_active(4)
    assert not a.is_active(1.99) and not a.is_active(4.01)


@pytest.mark.parametrize(
    "ann",
    [
        Annotation(TEXT, 3, 3, 0, 0, 100, 40, text="x"),  # empty duration
        Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="  "),  # blank text
        Annotation(TEXT, 1, 2, 0, 0, 0, 40, text="x"),  # no box width
        Annotation(TEXT, 1, 2, 0, 0, 100, 0, text="x"),  # no box height
        Annotation(TEXT, 1, 2, 0, 0, text="x"),  # no box at all
        Annotation(BLUR, 1, 2, 0, 0, 0, 10),  # no region
        Annotation("nope", 1, 2, 0, 0),
        Annotation(TEXT, -1, 2, 0, 0, 100, 40, text="x"),
        Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="x", size=7),
        Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="x", size=73),
        Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="x", box_color="#GGG"),
        Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="x", box_color="red"),
        Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="x", text_color="#ff0000"),
    ],
)
def test_validate_rejects(ann):
    with pytest.raises(ValueError):
        ann.validate()


def test_validate_accepts():
    Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="ok").validate()
    Annotation(BLUR, 1, 2, 0, 0, 50, 50).validate()
    Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="ok", size=8).validate()
    Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="ok", size=72).validate()
    Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="ok", box_color="000000").validate()
    Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="ok", text_color="000000").validate()


def test_style_defaults():
    a = Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="x")
    assert (a.size, a.box_color, a.text_color) == (14, "#000000", "#ffffff")
    assert (DEFAULT_SIZE, DEFAULT_BOX_COLOR, DEFAULT_TEXT_COLOR) == (14, "#000000", "#ffffff")


def test_blur_ignores_text_style_fields():
    Annotation(BLUR, 1, 2, 0, 0, 50, 50, size=1, box_color="nope", text_color="nope").validate()


def _arrow(**kw):
    base = dict(x2=100, y2=50)
    base.update(kw)
    return Annotation(ARROW, 1, 2, 10, 20, **base)


def test_arrow_defaults_validate():
    a = _arrow()
    a.validate()
    assert (a.thickness, a.start_style, a.end_style) == (4, "none", "arrow")
    assert (DEFAULT_THICKNESS, DEFAULT_START_STYLE, DEFAULT_END_STYLE) == (4, "none", "arrow")


@pytest.mark.parametrize("kw", [
    dict(x2=10, y2=20),  # identical points
    dict(thickness=0),
    dict(thickness=31),
    dict(color="red"),
    dict(color="#GGG"),
    dict(start_style="dot"),
    dict(end_style="Arrow"),
])
def test_arrow_validate_rejects(kw):
    with pytest.raises(ValueError):
        _arrow(**kw).validate()


@pytest.mark.parametrize("kw", [
    dict(thickness=1), dict(thickness=30), dict(color="E03131"),
    dict(start_style="arrow", end_style="arrow"), dict(start_style="none", end_style="none"),
    dict(x2=10, y2=21),
])
def test_arrow_validate_accepts(kw):
    _arrow(**kw).validate()


def test_arrow_still_checks_times():
    with pytest.raises(ValueError):
        Annotation(ARROW, 3, 3, 0, 0, x2=5, y2=5).validate()
    with pytest.raises(ValueError):
        Annotation(ARROW, -1, 3, 0, 0, x2=5, y2=5).validate()


def test_arrow_ignores_box_size_and_text_fields():
    _arrow(w=0, h=0, text="", size=1, box_color="nope", text_color="nope").validate()
