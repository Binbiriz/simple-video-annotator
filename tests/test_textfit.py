import subprocess

import pytest

from vidnote import textfit
from vidnote.models import MAX_SIZE, MIN_SIZE
from vidnote.textfit import PAD, layout_text, line_height, scaled_size, wrap


def test_wrap_short_text_is_one_line():
    assert wrap("Hello world", 20) == ["Hello world"]


def test_wrap_breaks_at_word_boundaries():
    assert wrap("aaa bbb ccc", 7) == ["aaa bbb", "ccc"]
    assert wrap("aaa bbb ccc", 6) == ["aaa", "bbb", "ccc"]


def test_wrap_hard_breaks_long_words():
    assert wrap("abcdefghij", 4) == ["abcd", "efgh", "ij"]
    assert wrap("ab abcdefghij", 4) == ["ab", "abcd", "efgh", "ij"]


def test_wrap_counts_characters_not_bytes():
    assert wrap("çğıöşü", 3) == ["çğı", "öşü"]


def test_wrap_collapses_spaces_and_handles_one_column():
    assert wrap("a    b", 10) == ["a b"]
    assert wrap("ab c", 1) == ["a", "b", "c"]


@pytest.mark.parametrize("size", [8, 14, 20, 40, 72])
@pytest.mark.parametrize("w,h", [(30, 20), (150, 50), (400, 200)])
def test_layout_uses_exactly_the_requested_size(size, w, h):
    text = "This is a rather long sentence that needs to be wrapped inside a small box"
    res = layout_text(text, w, h, size)
    assert res.size == size  # no auto-shrink, even when the text overflows
    cols = max(1, (w - 2 * PAD) * 1000 // (size * textfit.DEFAULT_ADV_PM))
    assert all(len(ln) <= cols for ln in res.lines)
    if res.fits:
        assert len(res.lines) * line_height(size) <= h - 2 * PAD


def test_short_text_in_large_box_fits():
    res = layout_text("Hi", 600, 300, 14)
    assert res.size == 14 and res.fits and res.lines == ["Hi"]


def test_larger_size_wraps_into_more_lines():
    text = "word " * 20
    assert len(layout_text(text, 300, 400, 30).lines) > len(layout_text(text, 300, 400, 10).lines)


def test_fits_is_false_when_lines_are_too_tall():
    res = layout_text("word " * 100, 60, 30, 14)
    assert res.size == 14 and not res.fits


def test_fits_is_false_when_box_is_narrower_than_one_glyph():
    res = layout_text("hi", 12, 200, 40)
    assert not res.fits and res.lines


def test_single_long_word_is_hard_broken_at_given_size():
    res = layout_text("Supercalifragilisticexpialidocious", 60, 400, 14)
    assert res.fits and len(res.lines) > 1
    assert "".join(res.lines) == "Supercalifragilisticexpialidocious"


def test_tiny_box_does_not_crash():
    res = layout_text("hello", 2, 2, 72)
    assert res.size == 72 and not res.fits and res.lines


def test_scaled_size():
    assert scaled_size(14, 100, 50, 100, 50) == 14
    assert scaled_size(14, 100, 50, 200, 100) == 28
    assert scaled_size(20, 100, 50, 200, 50) == 20  # smaller ratio wins
    assert scaled_size(20, 100, 50, 100, 25) == 10
    assert scaled_size(10, 100, 50, 10, 5) == MIN_SIZE
    assert scaled_size(60, 100, 50, 500, 250) == MAX_SIZE


def _fake_fc_match(monkeypatch, answers):
    textfit.resolve_font.cache_clear()

    def fake(pattern):
        return answers[pattern]

    monkeypatch.setattr(textfit, "_fc_match", fake)


def test_resolve_font_prefers_ubuntu_mono(monkeypatch):
    _fake_fc_match(monkeypatch, {"Ubuntu Mono": ("Ubuntu Mono", "/f/um.ttf")})
    info = textfit.resolve_font()
    assert info.preferred and info.family == "Ubuntu Mono" and info.file == "/f/um.ttf"
    textfit.resolve_font.cache_clear()


def test_resolve_font_falls_back_to_monospace(monkeypatch):
    _fake_fc_match(monkeypatch, {"Ubuntu Mono": ("DejaVu Sans", "/f/d.ttf"),
                                 "monospace": ("DejaVu Sans Mono", "/f/dm.ttf")})
    info = textfit.resolve_font()
    assert not info.preferred and info.family == "DejaVu Sans Mono"
    textfit.resolve_font.cache_clear()


def test_resolve_font_without_fontconfig(monkeypatch):
    textfit.resolve_font.cache_clear()

    def boom(*_a, **_k):
        raise FileNotFoundError("fc-match")

    monkeypatch.setattr(subprocess, "run", boom)
    info = textfit.resolve_font()
    assert not info.preferred and info.family == "monospace"
    textfit.resolve_font.cache_clear()
