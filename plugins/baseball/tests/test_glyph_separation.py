"""Hi-res glyph separation invariants for the bold text the layouts paint.

Bold Inter at a low rasterization threshold grows ink wider than the
glyph's own advance, so adjacent letters merge into one blob. The old
module-level `_HIRES_THRESHOLD = 80` (copied from the thin-font guidance
that protects Inter-*Regular*) did that to every bold string in this
pack. Core now defaults the threshold per font (Inter-Bold 128,
Inter-Regular 80) and `_paint.hires()` passes none.

Advances stay exactly additive at any threshold, so the layout tests that
measure gaps *between* calls cannot see this — the collision happens
*inside* one string. These tests assert on the ink instead.

Known limit, deliberately NOT asserted here: the layouts also paint bold
at 8–10px (venue line, standings cells, stat labels). Below ~11px Inter is
unreadable at *any* threshold — even Bold at 128 leaves a 4-letter cap
word at 1–3 blobs — and those slots are too short for the 8-row Spleen
caps. Raising them is a layout decision, not a threshold one.
"""

import math

import attrs
import pytest
from led_ticker.plugin import draw_text, resolve_font

from led_ticker_baseball import _paint

_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


@attrs.define
class _Color:
    red: int
    green: int
    blue: int


class _InkCanvas:
    def __init__(self, width: int = 512, height: int = 64) -> None:
        self.width = width
        self.height = height
        self.lit: set[tuple[int, int]] = set()

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        if r or g or b:
            self.lit.add((x, y))


def _components(lit: set[tuple[int, int]]) -> int:
    remaining = set(lit)
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


def _bold_components(text: str, size: int) -> int:
    canvas = _InkCanvas()
    shim, _ = _paint.phys_wrap(canvas)
    _paint.hires(shim, text, 2, 2, _Color(200, 200, 200), size, bold=True)
    return _components(canvas.lit)


# Team codes, venue words, labels and scores the cards paint in bold.
_STRINGS = ("NYY", "BOS", "WRIGLEY", "ATTENDANCE", "PAID", "7-4", "FINAL")

# Bold sizes >= 11 the layouts paint (promo, statcast, attendance,
# scoreboard, two_row). 8–10 are exempt per the module docstring.
_PAINTED_BOLD_SIZES = (11, 12, 13, 14, 15, 18, 20, 22, 24, 26, 34)

_MIN_SEPARATED_FRACTION = 0.8


def _floor(text: str) -> int:
    return math.ceil(len(text.replace(" ", "")) * _MIN_SEPARATED_FRACTION)


@pytest.mark.parametrize("text", _STRINGS)
@pytest.mark.parametrize("size", _PAINTED_BOLD_SIZES)
def test_bold_glyphs_do_not_fuse_at_any_painted_size(text, size):
    """On failure the string renders as mush on a real panel. Raise the
    size at that call site or fix the threshold in core — do NOT lower
    `_MIN_SEPARATED_FRACTION` to make this pass."""
    got = _bold_components(text, size)
    assert got >= _floor(text), (
        f"{text!r} at size {size}: only {got} distinct ink blobs for "
        f"{len(text)} glyphs (floor {_floor(text)}) — adjacent glyphs merged"
    )


def test_the_thin_font_threshold_fuses_bold_text():
    """Pins the premise: 80 — the value this pack used to hard-code — fuses
    a bold venue word at the promo size. If this stops failing, core's
    rasterizer changed; re-measure rather than trusting it."""
    font = resolve_font("Inter-Bold", 14, 80)
    canvas = _InkCanvas()
    draw_text(canvas, font, "WRIGLEY", 2, 2 + font.ascent, _Color(200, 200, 200))
    assert _components(canvas.lit) < _floor("WRIGLEY")
