"""Hex colours and the user-editable box colour list. No Qt imports.

The list is plain text, one `hex|label` entry per line, e.g. `#000000|Black`.
"""

from __future__ import annotations

import re
from typing import List, Tuple

TEXT_COLORS = ("#000000", "#ffffff")  # the only allowed text colours

DEFAULT_COLOR_LIST: List[Tuple[str, str]] = [
    ("#000000", "Black"),
    ("#ffffff", "White"),
    ("#ffd400", "Yellow"),
    ("#1e90ff", "Blue"),
    ("#e03131", "Red"),
    ("#2f9e44", "Green"),
]

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def normalize_hex(value: str) -> str:
    """'ABC123' or '#abc123' -> '#abc123'. Raises ValueError for anything but 6 hex digits."""
    m = _HEX_RE.match(value.strip())
    if not m:
        raise ValueError(f"invalid colour {value.strip()!r}: expected 6 hex digits like #1e90ff")
    return "#" + m.group(1).lower()


def parse_color_list(
    text: str,
) -> Tuple[List[Tuple[str, str]], List[Tuple[int, str, str]]]:
    """Return (entries, skipped); skipped holds (lineno, line, error). Blank lines are ignored."""
    entries: List[Tuple[str, str]] = []
    skipped: List[Tuple[int, str, str]] = []
    seen = set()
    for no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.count("|") != 1:
            skipped.append((no, raw, "expected exactly one '|' (hex|label)"))
            continue
        hex_part, label = (p.strip() for p in line.split("|"))
        try:
            hex_value = normalize_hex(hex_part)
        except ValueError as exc:
            skipped.append((no, raw, str(exc)))
            continue
        if not label:
            skipped.append((no, raw, "label is empty"))
            continue
        if hex_value in seen:
            skipped.append((no, raw, f"duplicate colour {hex_value}"))
            continue
        seen.add(hex_value)
        entries.append((hex_value, label))
    return entries, skipped


def dump_color_list(entries) -> str:
    return "".join(f"{hex_value}|{label}\n" for hex_value, label in entries)


def default_color_list_text() -> str:
    return dump_color_list(DEFAULT_COLOR_LIST)
