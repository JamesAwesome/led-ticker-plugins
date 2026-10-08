"""Hi-res glyph separation invariants for the card and dashboard layouts.

Bold Inter at a low rasterization threshold grows ink wider than the
glyph's own advance, so adjacent letters merge into one blob — legible as
a shape, unreadable as a word. The old module-level `_HIRES_THRESHOLD =
80` (copied from the thin-font guidance that protects Inter-*Regular*)
did that to every bold string the pack paints; the live docs' dashboard
GIF shows `MSFT`/`NVDA`/`TSLA` as blobs. Core now defaults the threshold
per font (Inter-Bold 128, Inter-Regular 80), and `_paint.hires()` passes
none, so each weight gets the value measured for it.

Advances stay exactly additive at any threshold, so the layout tests that
measure gaps *between* `hires()` calls cannot see this — the collision
happens *inside* one string. These tests assert on the ink instead: paint
the string and count 8-connected components.

Below ~11px Inter is unreadable at *any* threshold (even Bold at 128
leaves `NVDA` at 1–3 blobs of 4), which is why the dashboard's watch rows
moved to the Spleen pixel font — `test_dashboard.py` covers those.
"""

import math
import re
from pathlib import Path

import attrs
import pytest
from led_ticker.plugin import draw_text, resolve_font

from led_ticker_stocks import _paint
from led_ticker_stocks.layouts import card, dashboard

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
    """Blobs when `text` is painted the way the layouts paint it: through
    `_paint.hires(bold=True)`, whatever threshold that resolves to."""
    canvas = _InkCanvas()
    shim, _ = _paint.phys_wrap(canvas)
    _paint.hires(shim, text, 2, 2, _Color(200, 200, 200), size, bold=True)
    return _components(canvas.lit)


# Symbols the hero / card paint in bold, at every size that ladder reaches:
# the dashboard hero (26 -> 18) and the card's fixed 22.
_SYMBOLS = ("MSFT", "NVDA", "TSLA", "DKS", "AAPL", "EUR/USD")
_SYMBOL_SIZES = (18, 20, 22, 26)

# Prices the card / dashboard paint in bold: the card's price ladder
# (22 -> 11) and the dashboard's fixed 24. Digit strings, never letters.
_PRICES = ("1,234.56", "64906.62", "0.0421", "317.00")
_PRICE_SIZES = (11, 12, 14, 16, 18, 22, 24)

# At least this fraction of a string's glyphs must render as distinct
# blobs. For the 4-letter symbols that is every glyph; longer strings get
# one touching pair of slack (kerned pairs like `VA` sit close by design).
_MIN_SEPARATED_FRACTION = 0.8


def _floor(text: str) -> int:
    glyphs = len(text.replace(" ", "").replace(",", ""))
    return math.ceil(glyphs * _MIN_SEPARATED_FRACTION)


def _assert_separated(text: str, size: int) -> None:
    """On failure the string renders as mush on a real panel. Raise the
    size at that call site or fix the threshold in core — do NOT lower
    `_MIN_SEPARATED_FRACTION` to make this pass."""
    got = _bold_components(text, size)
    assert got >= _floor(text), (
        f"{text!r} at size {size}: only {got} distinct ink blobs for "
        f"{len(text)} glyphs (floor {_floor(text)}) — adjacent glyphs merged"
    )


@pytest.mark.parametrize("text", _SYMBOLS)
@pytest.mark.parametrize("size", _SYMBOL_SIZES)
def test_bold_symbols_do_not_fuse_at_any_painted_size(text, size):
    _assert_separated(text, size)


@pytest.mark.parametrize("text", _PRICES)
@pytest.mark.parametrize("size", _PRICE_SIZES)
def test_bold_prices_do_not_fuse_at_any_painted_size(text, size):
    _assert_separated(text, size)


def _literal_bold_sizes(module) -> set[int]:
    source = Path(module.__file__).read_text()
    sizes: set[int] = set()
    for call in re.findall(r"hires\((.*?)\)\n", source, re.S):
        if "bold=False" in call:
            continue
        args = [a.strip() for a in re.split(r",(?![^()]*\))", call)]
        if len(args) > 5 and args[5].isdigit():
            sizes.add(int(args[5]))
    return sizes


def test_painted_bold_sizes_are_covered():
    """Meta-guard: every literal bold size and every ladder entry in the
    card and dashboard is exercised above, so a new small bold size can't
    slip in unmeasured."""
    painted = _literal_bold_sizes(card) | _literal_bold_sizes(dashboard)
    painted |= set(dashboard._HERO_SYM_SIZES)
    painted |= set(card._PRICE_SIZES)
    assert painted, "found no bold hires() sizes — did the regex rot?"
    uncovered = painted - set(_SYMBOL_SIZES) - set(_PRICE_SIZES)
    assert not uncovered, (
        f"layouts paint Inter-Bold at size(s) {sorted(uncovered)} that this "
        f"module does not check — add them to _SYMBOL_SIZES or _PRICE_SIZES"
    )


def test_the_thin_font_threshold_fuses_bold_symbols():
    """Pins the premise: 80 — the value this pack used to hard-code — fuses
    a 4-letter bold symbol at the hero floor size. If this stops failing,
    core's rasterizer changed; re-measure rather than trusting it."""
    font = resolve_font("Inter-Bold", 18, 80)
    canvas = _InkCanvas()
    draw_text(canvas, font, "MSFT", 2, 2 + font.ascent, _Color(200, 200, 200))
    assert _components(canvas.lit) < 4
