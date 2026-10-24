import pytest

from vidnote.models import BLUR, TEXT, Annotation


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
    ],
)
def test_validate_rejects(ann):
    with pytest.raises(ValueError):
        ann.validate()


def test_validate_accepts():
    Annotation(TEXT, 1, 2, 0, 0, 100, 40, text="ok").validate()
    Annotation(BLUR, 1, 2, 0, 0, 50, 50).validate()
