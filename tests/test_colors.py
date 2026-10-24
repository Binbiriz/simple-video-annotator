import pytest

from vidnote import colors


@pytest.mark.parametrize("value,want", [
    ("#abc123", "#abc123"),
    ("ABC123", "#abc123"),
    ("#ABC123", "#abc123"),
    ("  #1E90FF ", "#1e90ff"),
])
def test_normalize_hex(value, want):
    assert colors.normalize_hex(value) == want


@pytest.mark.parametrize("value", ["#abc", "abc", "#abcde", "#abcdef0", "#GGG123", "", "#", "red"])
def test_normalize_hex_rejects(value):
    with pytest.raises(ValueError):
        colors.normalize_hex(value)


def test_parse_valid_list_with_crlf_and_blank_lines():
    entries, skipped = colors.parse_color_list("#000000|Black\r\n\r\n  \nFFD400 | Sun yellow \r\n")
    assert skipped == []
    assert entries == [("#000000", "Black"), ("#ffd400", "Sun yellow")]


def test_parse_reports_and_skips_invalid_lines():
    text = "\n".join([
        "#000000|Black",       # 1 ok
        "#ffffff White",       # 2 no pipe
        "#ffffff|Wh|ite",      # 3 extra pipe
        "#ffffff|   ",         # 4 empty label
        "#GGG|Bad",            # 5 bad hex
        "#abc|Short",          # 6 3 digits
        "#000000|Again",       # 7 duplicate
        "#ff0000|Red",         # 8 ok
    ])
    entries, skipped = colors.parse_color_list(text)
    assert entries == [("#000000", "Black"), ("#ff0000", "Red")]
    assert [s[0] for s in skipped] == [2, 3, 4, 5, 6, 7]
    assert all(s[2] for s in skipped)
    assert "duplicate" in skipped[-1][2]


def test_duplicate_after_normalisation_keeps_first():
    entries, skipped = colors.parse_color_list("#ABCDEF|One\nabcdef|Two\n")
    assert entries == [("#abcdef", "One")]
    assert len(skipped) == 1


def test_dump_parse_roundtrip():
    entries = [("#123456", "A"), ("#abcdef", "B c")]
    assert colors.parse_color_list(colors.dump_color_list(entries)) == (entries, [])


def test_default_list_is_valid():
    text = colors.default_color_list_text()
    entries, skipped = colors.parse_color_list(text)
    assert skipped == [] and entries == colors.DEFAULT_COLOR_LIST
    assert text.splitlines()[0] == "#000000|Black"
