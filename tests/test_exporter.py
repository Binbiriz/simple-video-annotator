import pytest

from vidnote import exporter
from vidnote.models import ARROW, BLUR, TEXT, Annotation


def T(start, end, x, y, w, h, text, size=14, box="#000000", color="#ffffff"):
    return Annotation(TEXT, start, end, x, y, w, h, text=text, size=size,
                      box_color=box, text_color=color)


def A(start, end, x1, y1, x2, y2, thickness=4, color="#e03131", ss="none", es="arrow"):
    return Annotation(ARROW, start, end, x1, y1, x2=x2, y2=y2, thickness=thickness,
                      color=color, start_style=ss, end_style=es)


def test_fmt_time():
    assert exporter.fmt_time(0) == "0"
    assert exporter.fmt_time(2.5) == "2.5"
    assert exporter.fmt_time(10.0) == "10"
    assert exporter.fmt_time(1.23456) == "1.235"


def test_roundtrip():
    items = [
        T(2, 6, 50, 60, 200, 80, "Hello   world", size=20, box="#ffd400", color="#000000"),
        Annotation(BLUR, 1.5, 4, 10, 20, 300, 120),
        T(7, 8, 1, 2, 30, 40, "a | b|c", size=72, box="#1e90ff"),
    ]
    parsed, skipped = exporter.loads(exporter.dumps(items))
    assert skipped == []
    assert [a.kind for a in parsed] == [BLUR, TEXT, TEXT]  # sorted by start time
    assert parsed[0] == items[1]
    assert parsed[1] == T(2, 6, 50, 60, 200, 80, "Hello world", size=20,
                          box="#ffd400", color="#000000")
    assert parsed[2] == items[2]  # size, colours and the text with '|' survive


def test_dumps_uses_pipe_format():
    out = exporter.dumps([T(2, 6, 50, 60, 200, 80, "hi there", size=18, box="#ffd400"),
                          Annotation(BLUR, 1, 4, 10, 20, 30, 40)])
    assert "# text|start|end|x|y|w|h|size|boxcolor|textcolor|text" in out
    data = [ln for ln in out.splitlines() if not ln.startswith("#")]
    assert data == ["blur|1|4|10|20|30|40",
                    "text|2|6|50|60|200|80|18|#ffd400|#ffffff|hi there"]


def test_colours_are_normalised_on_write_and_read():
    assert exporter.to_line(T(1, 2, 3, 4, 50, 20, "x", box="ABC123", color="FFFFFF")) == (
        "text|1|2|3|4|50|20|14|#abc123|#ffffff|x")
    for box in ("abc123", "#ABC123", "#abc123"):
        parsed, skipped = exporter.loads(f"text|1|2|3|4|50|20|14|{box}|000000|x\n")
        assert not skipped
        assert parsed[0].box_color == "#abc123" and parsed[0].text_color == "#000000"


def test_comments_and_blank_lines_ignored():
    parsed, skipped = exporter.loads("# c\n\n   \ntext|1|2|3|4|50|20|14|#000000|#ffffff|hi\n")
    assert len(parsed) == 1 and not skipped


def test_pipe_format_lines():
    parsed, skipped = exporter.loads(
        "text|53.96|60.96|170|220|300|60|16|#000000|#ffffff|deneme\n")
    assert not skipped
    assert parsed[0] == T(53.96, 60.96, 170, 220, 300, 60, "deneme", size=16)
    assert exporter.to_line(parsed[0]) == "text|53.96|60.96|170|220|300|60|16|#000000|#ffffff|deneme"

    parsed, skipped = exporter.loads(
        " text | 1 | 2 | 10 | 20 | 100 | 40 | 9 | #FFFFFF | #000000 | Hello \n")
    assert not skipped
    assert parsed[0] == T(1, 2, 10, 20, 100, 40, "Hello", size=9, box="#ffffff", color="#000000")

    parsed, skipped = exporter.loads("blur|1|2|3|4|5|6\r\n")
    assert not skipped
    assert parsed[0] == Annotation(BLUR, 1, 2, 3, 4, 5, 6)


def test_turkish_text_roundtrips():
    items = [T(1, 2, 3, 4, 50, 20, "Çok güzel şarkı ışığı | İ")]
    parsed, skipped = exporter.loads(exporter.dumps(items))
    assert not skipped and parsed == items


def test_text_is_remainder_after_tenth_pipe():
    parsed, skipped = exporter.loads("text|1|2|3|4|50|20|14|#000000|#ffffff|a|b|c\n")
    assert not skipped
    assert parsed[0].text == "a|b|c"


MALFORMED = [
    ("1 2 3 4 hi", False),
    ("text 1 2 3 4 hi", False),
    ("blur 1 2 3 4 5 6", False),
    ("blur|1|2|3", False),
    ("blur|1|2|3|4|5|6|7", False),
    ("text|1|2|(w-text_w)/2|5|50|20|14|#000000|#ffffff|hi", False),
    ("text|1|2|3|4|hello", True),  # old format
    ("text|1|2|3|4|50|20|hi", True),  # previous format
    ("text|1|2|3|4|a|b|c", True),
    ("text|1|2|3|4|50|20|hello|#000000|#ffffff|hi", True),  # size is not a number
    ("text|1|2|3|4|50|20|7|#000000|#ffffff|hi", False),
    ("text|1|2|3|4|50|20|73|#000000|#ffffff|hi", False),
    ("text|1|2|3|4|50|20|1.5|#000000|#ffffff|hi", True),
    ("text|1|2|3|4|50|20|14|#GGG|#ffffff|hi", False),
    ("text|1|2|3|4|50|20|14|red|#ffffff|hi", False),
    ("text|1|2|3|4|50|20|14|#000000|#ff0000|hi", False),
    ("text|1|2|3|4|0|20|14|#000000|#ffffff|hi", False),
    ("text|1|2|3|4|50|-5|14|#000000|#ffffff|hi", False),
    ("text|1|2|3|4|50|20|14|#000000|#ffffff|   ", False),
    ("text|1|2|3|4|50|20|14|#000000|#ffffff", True),  # missing text field
]


def test_malformed_lines_are_reported():
    parsed, skipped = exporter.loads("\n".join(line for line, _ in MALFORMED) + "\n")
    assert parsed == []
    assert [s[0] for s in skipped] == list(range(1, len(MALFORMED) + 1))
    assert all(s[2] for s in skipped)


@pytest.mark.parametrize("line,old", MALFORMED)
def test_malformed_line_message(line, old):
    with pytest.raises(ValueError) as exc:
        exporter.parse_line(line)
    if old:
        assert "no longer supported" in str(exc.value)


def test_blur_lines_unchanged():
    parsed, skipped = exporter.loads("blur|1|2|3|4|5|6\n")
    assert not skipped
    assert parsed == [Annotation(BLUR, 1, 2, 3, 4, 5, 6)]


def test_saved_lines_are_always_pipe_separated():
    out = exporter.dumps([T(1, 2, 3, 4, 50, 20, "x y"),
                          Annotation(BLUR, 1, 2, 3, 4, 5, 6)])
    for ln in out.splitlines():
        assert ln.startswith(("#", "text|", "blur|"))


def test_arrow_roundtrip():
    items = [
        A(1, 3, 10, 20, 300, 150),
        A(2.5, 4, 600, 300, 50, 40, thickness=30, color="#1e90ff", ss="arrow", es="arrow"),
        A(5, 6, 5, 5, 5, 90, thickness=1, ss="arrow", es="none"),
        A(7, 8, 0, 0, 1, 1, ss="none", es="none"),
        T(0, 1, 1, 2, 30, 40, "text stays"),
        Annotation(BLUR, 9, 10, 1, 2, 3, 4),
    ]
    parsed, skipped = exporter.loads(exporter.dumps(items))
    assert skipped == []
    assert sorted(parsed, key=lambda a: (a.start, a.end)) == sorted(
        items, key=lambda a: (a.start, a.end))


def test_arrow_dumps_line_and_header():
    out = exporter.dumps([A(1, 4, 10, 20, 300, 150, thickness=6, color="E03131", ss="arrow")])
    assert "# arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle" in out
    data = [ln for ln in out.splitlines() if not ln.startswith("#")]
    assert data == ["arrow|1|4|10|20|300|150|6|#e03131|arrow|arrow"]


def test_arrow_parse_normalises_and_ignores_whitespace():
    parsed, skipped = exporter.loads(
        "# note\r\n arrow | 1 | 2.5 | 10 | 20 | 30 | 40 | 8 | E03131 | NONE | Arrow \r\n")
    assert skipped == []
    assert parsed == [A(1, 2.5, 10, 20, 30, 40, thickness=8, color="#e03131")]


ARROW_MALFORMED = [
    "arrow|1|2|3|4|5|6|4|#ffffff|none",  # too few fields
    "arrow|1|2|3|4|5|6|4|#ffffff|none|arrow|x",  # too many fields
    "arrow|1|2|3|4|5|6|4|#ffffff",
    "arrow|1|2|3.5|4|5|6|4|#ffffff|none|arrow",  # non-integer coordinate
    "arrow|1|2|a|4|5|6|4|#ffffff|none|arrow",
    "arrow|1|2|3|4|3|4|4|#ffffff|none|arrow",  # identical points
    "arrow|1|2|3|4|5|6|0|#ffffff|none|arrow",  # thickness out of range
    "arrow|1|2|3|4|5|6|31|#ffffff|none|arrow",
    "arrow|1|2|3|4|5|6|x|#ffffff|none|arrow",
    "arrow|1|2|3|4|5|6|4|red|none|arrow",  # bad colour
    "arrow|1|2|3|4|5|6|4|#GGG|none|arrow",
    "arrow|1|2|3|4|5|6|4|#ffffff|dot|arrow",  # unknown style
    "arrow|1|2|3|4|5|6|4|#ffffff|none|",
    "arrow|a|2|3|4|5|6|4|#ffffff|none|arrow",  # bad time
]


@pytest.mark.parametrize("line", ARROW_MALFORMED)
def test_malformed_arrow_lines_are_rejected_with_a_reason(line):
    with pytest.raises(ValueError) as exc:
        exporter.parse_line(line)
    assert str(exc.value)


def test_malformed_arrow_lines_are_skipped_in_a_mixed_file():
    content = "text|1|2|3|4|50|20|14|#000000|#ffffff|ok\n" + "\n".join(ARROW_MALFORMED) + (
        "\narrow|1|2|3|4|5|6|4|#ffffff|none|arrow\n")
    parsed, skipped = exporter.loads(content)
    assert [a.kind for a in parsed] == [TEXT, ARROW]
    assert [n for n, _l, _e in skipped] == list(range(2, 2 + len(ARROW_MALFORMED)))


def test_unknown_type_message_lists_arrow():
    with pytest.raises(ValueError) as exc:
        exporter.parse_line("circle|1|2|3|4")
    assert "arrow|" in str(exc.value)
