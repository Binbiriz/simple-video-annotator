from vidnote import exporter
from vidnote.models import BLUR, TEXT, Annotation


def test_fmt_time():
    assert exporter.fmt_time(0) == "0"
    assert exporter.fmt_time(2.5) == "2.5"
    assert exporter.fmt_time(10.0) == "10"
    assert exporter.fmt_time(1.23456) == "1.235"


def test_roundtrip():
    items = [
        Annotation(TEXT, 2, 6, 50, 60, text="Hello   world"),
        Annotation(BLUR, 1.5, 4, 10, 20, 300, 120),
        Annotation(TEXT, 7, 8, 1, 2, text="a | b|c"),
    ]
    parsed, skipped = exporter.loads(exporter.dumps(items))
    assert skipped == []
    assert [a.kind for a in parsed] == [BLUR, TEXT, TEXT]  # sorted by start time
    assert parsed[0] == items[1]
    assert parsed[1].text == "Hello world"
    assert parsed[2].text == "a | b|c"


def test_dumps_uses_pipe_format():
    out = exporter.dumps([Annotation(TEXT, 2, 6, 50, 60, text="hi there"),
                          Annotation(BLUR, 1, 4, 10, 20, 30, 40)])
    assert "# text|start|end|x|y|text" in out
    data = [ln for ln in out.splitlines() if not ln.startswith("#")]
    assert data == ["blur|1|4|10|20|30|40", "text|2|6|50|60|hi there"]


def test_comments_and_blank_lines_ignored():
    parsed, skipped = exporter.loads("# c\n\n   \ntext|1|2|3|4|hi\n")
    assert len(parsed) == 1 and not skipped


def test_pipe_format_lines():
    parsed, skipped = exporter.loads("text|53.96|60.96|170|220|deneme\n")
    assert not skipped
    assert parsed[0] == Annotation(TEXT, 53.96, 60.96, 170, 220, text="deneme")
    assert exporter.to_line(parsed[0]) == "text|53.96|60.96|170|220|deneme"

    parsed, skipped = exporter.loads(" text | 1 | 2 | 10 | 20 | Hello \n")
    assert not skipped
    assert parsed[0] == Annotation(TEXT, 1, 2, 10, 20, text="Hello")

    parsed, skipped = exporter.loads("blur|1|2|3|4|5|6\r\n")
    assert not skipped
    assert parsed[0] == Annotation(BLUR, 1, 2, 3, 4, 5, 6)


def test_text_is_remainder_after_fifth_pipe():
    parsed, skipped = exporter.loads("text|1|2|3|4|a|b|c\n")
    assert not skipped
    assert parsed[0].text == "a|b|c"


def test_malformed_lines_are_reported():
    content = "\n".join([
        "1 2 3 4 hi",
        "text 1 2 3 4 hi",
        "blur 1 2 3 4 5 6",
        "blur|1|2|3",
        "blur|1|2|3|4|5|6|7",
        "text|1|2|(w-text_w)/2|5|hi",
        "text|1|2|3|4|   ",
        "text|1|2|3|4",
    ]) + "\n"
    parsed, skipped = exporter.loads(content)
    assert parsed == []
    assert [s[0] for s in skipped] == list(range(1, 9))
    assert all(s[2] for s in skipped)


def test_saved_lines_are_always_pipe_separated():
    out = exporter.dumps([Annotation(TEXT, 1, 2, 3, 4, text="x y"),
                          Annotation(BLUR, 1, 2, 3, 4, 5, 6)])
    for ln in out.splitlines():
        assert ln.startswith(("#", "text|", "blur|"))
