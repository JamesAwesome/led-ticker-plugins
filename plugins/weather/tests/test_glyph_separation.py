"""Hi-res glyph separation invariants for the forecast layouts.

The pack paints every string through `paint.hires()`, which is
Inter-**Bold** only (no call site passes `bold=False`). At a low
rasterization threshold bold ink grows wider than the glyph's own
advance, so adjacent letters merge into one blob — legible as a shape,
unreadable as a word. The old `_HIRES_THRESHOLD = 80` did that to the
hero location on every sign: "BOSTON" rasterized to 2 connected
components at size 9 and 4 at size 11, where 6 is correct.

Advances stay exactly additive at any threshold, so the layout tests
that measure gaps *between* `hires()` calls cannot see this — the
collision happens *inside* one string. These tests assert on the ink
instead: paint the string and count connected components.

Deliberately invariant-based, not a pixel pin. Nothing here encodes a
size or a threshold value, so the geometry stays free to change and
these still fail if a future threshold or size choice re-fuses text.
"""

import math
import re
from pathlib import Path

import attrs
import pytest
from led_ticker.plugin import default_threshold, draw_text, resolve_font

# What `paint.hires()` resolves Inter-Bold at: it passes no threshold, so
# core's per-font default applies.
_BOLD_THRESHOLD = default_threshold("Inter-Bold")

# 4-connectivity would split the diagonal-only joins inside a glyph (and
# count one letter twice); 8-connectivity treats a glyph as one blob, so
# a component count above 1 per glyph means letters actually fused.
_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


@attrs.define
class _Color:
    red: int
    green: int
    blue: int


class _InkCanvas:
    """Collects lit pixels; `draw_text` only needs SetPixel + size."""

    def __init__(self, width: int = 512, height: int = 64) -> None:
        self.width = width
        self.height = height
        self.lit: set[tuple[int, int]] = set()

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        if r or g or b:
            self.lit.add((x, y))


def _ink_components(text: str, size: int, threshold: int) -> int:
    """Number of 8-connected ink blobs when `text` is painted at `size`."""
    font = resolve_font("Inter-Bold", size, threshold)
    canvas = _InkCanvas()
    draw_text(canvas, font, text, 2, 2 + font.ascent, _Color(200, 200, 200))

    remaining = set(canvas.lit)
    components = 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            x, y = stack.pop()
            for dx, dy in _NEIGHBOURS:
                neighbour = (x + dx, y + dy)
                if neighbour in remaining:
                    remaining.discard(neighbour)
                    stack.append(neighbour)
    return components


# Real hero-location strings plus the shortest painted labels. Long
# names keep one or two touching pairs even at the fixed threshold, which
# reads fine on a panel; what matters is that a string never collapses
# into a blob. So the floor is proportional, not exact.
_STRINGS = (
    "BOSTON",
    "TUE",
    "FEELS",
    "NEW YORK",
    "PHILADELPHIA",
    # The widest realistic API-resolved city name that still fits the
    # bigsign hero budget without shrinking.
    "SAN FRANCISCO",
)

# Every size the forecast layouts paint through `hires()`. Keep in sync
# with the call sites; `test_painted_sizes_are_covered` enforces that.
_PAINTED_SIZES = (11, 27, 28)

# A string must render at least this fraction of its glyphs as distinct
# ink blobs. Derived from measurement, not taste: at the fixed threshold
# the worst real string is SAN FRANCISCO at size 11 (10 of 12 = 0.83),
# while the pre-fix threshold put BOSTON at 0.67 and SAN FRANCISCO at
# 0.58. 0.8 sits in that gap.
_MIN_SEPARATED_FRACTION = 0.8


def _expected_floor(text: str) -> int:
    glyphs = len(text.replace(" ", ""))
    return math.ceil(glyphs * _MIN_SEPARATED_FRACTION)


@pytest.mark.parametrize("text", _STRINGS)
@pytest.mark.parametrize("size", _PAINTED_SIZES)
def test_glyphs_do_not_fuse_at_any_painted_size(text, size):
    """No painted string collapses toward a single blob.

    On failure the string is rendering as mush on a real panel. Fix the
    per-font default in core, or the size at that call site — do NOT lower
    `_MIN_SEPARATED_FRACTION` to make this pass.
    """
    glyphs = len(text.replace(" ", ""))
    floor = _expected_floor(text)
    got = _ink_components(text, size, _BOLD_THRESHOLD)
    assert got >= floor, (
        f"{text!r} at size {size}, threshold {_BOLD_THRESHOLD}: only "
        f"{got} of {glyphs} glyphs render as distinct ink blobs "
        f"(floor {floor}) — adjacent glyphs merged, so this reads as "
        f"mush on the panel"
    )


def test_painted_sizes_are_covered():
    """Meta-guard: if a layout starts painting a size this module does
    not exercise, the fusion check silently stops covering it."""
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "led_ticker_weather"
        / "forecast_layouts.py"
    ).read_text()
    painted = {int(m) for m in re.findall(r"hires\([^\n]*?,\s*(\d+)\)", source)}
    assert painted, "found no hires() call sites to check — did the regex rot?"
    uncovered = painted - set(_PAINTED_SIZES)
    assert not uncovered, (
        f"forecast_layouts.py paints hi-res text at size(s) {sorted(uncovered)} "
        f"that this module does not check — add them to _PAINTED_SIZES"
    )


def test_the_old_threshold_would_still_fuse_the_hero_location():
    """Guards the fix itself: pin that 80 is genuinely broken here, so
    nobody 'restores' it from the stale thin-stroke comment. The pack
    paints no Inter-Regular, which is what 80 existed to protect."""
    fused = _ink_components("BOSTON", 11, 80)
    assert fused < _expected_floor("BOSTON"), (
        "threshold 80 no longer fuses BOSTON at size 11 — if core's "
        "rasterizer changed, re-derive the per-font default from scratch "
        "rather than trusting this test's premise"
    )
