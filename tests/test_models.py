import pytest

from vidnote.models import (
    BLUR,
    DEFAULT_BOX_COLOR,
    DEFAULT_SIZE,
    DEFAULT_TEXT_COLOR,
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
