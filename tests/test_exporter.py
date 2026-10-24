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
    ]
    parsed, skipped = exporter.loads(exporter.dumps(items))
    assert skipped == []
    assert [a.kind for a in parsed] == [BLUR, TEXT]  # sorted by start time
    assert parsed[0] == items[1]
    assert parsed[1].text == "Hello world"


def test_comments_and_blank_lines_ignored():
    parsed, skipped = exporter.loads("# c\n\n   \n1 2 3 4 hi\n")
    assert len(parsed) == 1 and not skipped


def test_text_keyword_and_legacy_lines():
    parsed, skipped = exporter.loads("text 53.96 60.96 170 220 deneme\n1 2 3 4 old style\n")
    assert not skipped
    assert parsed[0] == Annotation(TEXT, 53.96, 60.96, 170, 220, text="deneme")
    assert parsed[1].text == "old style"
    assert exporter.to_line(parsed[0]) == "text 53.96 60.96 170 220 deneme"


def test_malformed_lines_are_reported():
    parsed, skipped = exporter.loads("1 2 3\nblur 1 2 3\n1 2 (w-text_w)/2 5 hi\n")
    assert parsed == []
    assert [s[0] for s in skipped] == [1, 2, 3]
