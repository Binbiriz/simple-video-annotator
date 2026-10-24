import subprocess

import pytest

from vidnote import textfit
from vidnote.textfit import MAX_SIZE, MIN_SIZE, PAD, fit_text, line_height, wrap


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


def test_short_text_in_large_box_keeps_default_size():
    res = fit_text("Hi", 600, 300)
    assert res.size == MAX_SIZE and res.fits and res.lines == ["Hi"]


def test_long_text_shrinks_and_wraps_inside_box():
    text = "This is a rather long sentence that needs to be wrapped inside a small box"
    res = fit_text(text, 200, 60)
    assert MIN_SIZE <= res.size < MAX_SIZE
    assert res.fits and len(res.lines) > 1
    assert len(res.lines) * line_height(res.size) <= 60 - 2 * PAD
    cols = (200 - 2 * PAD) * 1000 // (res.size * textfit.DEFAULT_ADV_PM)
    assert all(len(ln) <= cols for ln in res.lines)


def test_unfittable_text_uses_minimum_size_and_reports_it():
    res = fit_text("word " * 100, 60, 30)
    assert res.size == MIN_SIZE and not res.fits


def test_single_long_word_is_broken():
    res = fit_text("Supercalifragilisticexpialidocious", 60, 200)
    assert res.fits and len(res.lines) > 1
    assert "".join(res.lines) == "Supercalifragilisticexpialidocious"


def test_tiny_box_does_not_crash():
    res = fit_text("hello", 2, 2)
    assert res.size == MIN_SIZE and not res.fits and res.lines


@pytest.mark.parametrize("w", [30, 80, 150, 400])
@pytest.mark.parametrize("h", [20, 50, 120])
@pytest.mark.parametrize("text", ["x", "hello world", "çok güzel bir şarkı ışığı " * 4])
def test_fit_invariants(text, w, h):
    res = fit_text(text, w, h)
    cols = max(1, (w - 2 * PAD) * 1000 // (res.size * textfit.DEFAULT_ADV_PM))
    assert all(len(ln) <= cols for ln in res.lines)
    if res.fits:
        assert len(res.lines) * line_height(res.size) <= h - 2 * PAD
    else:
        assert res.size == MIN_SIZE


def test_wider_advance_never_gives_larger_size():
    text = "some text that is long enough to need shrinking in a small box"
    assert fit_text(text, 150, 40, 700).size <= fit_text(text, 150, 40, 500).size


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
