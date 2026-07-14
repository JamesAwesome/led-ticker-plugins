from led_ticker.plugin import HeadlessBackend

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._sparkline import _REF_BRIGHT, draw_sparkline
from led_ticker_stocks.model import SymbolQuote


def _rgb(color) -> tuple:
    """Convert a `Color` to a plain (r, g, b) tuple — HeadlessBackend stores
    pixels as plain tuples, and `Color` doesn't compare equal to a tuple
    even with matching channel values."""
    return (color.red, color.green, color.blue)


def _real(w=200, h=24):
    return HeadlessBackend(w, h).create_canvas()


def _lit(real):
    return {xy: v for xy, v in real._pixels.items() if v != (0, 0, 0)}


def test_empty_spark_draws_only_reference_line_no_crash():
    real = _real()
    q = SymbolQuote(sym="X", price=100.0, prev=100.0)  # empty deque
    draw_sparkline(real, 0, 0, 200, 24, q, dim=1.0)
    lit = _lit(real)
    assert lit  # a flat reference line was drawn
    # reference is roughly one horizontal row (small y-spread)
    ys = {y for (x, y) in lit}
    assert len(ys) <= 2


def test_up_points_green_down_points_red_relative_to_prev():
    real = _real()
    q = SymbolQuote(sym="X", price=110.0, prev=100.0)
    for p in [100.0, 105.0, 95.0, 110.0]:  # above, above, below, above prev
        q.spark.append(p)
    draw_sparkline(real, 0, 0, 200, 24, q, dim=1.0)
    lit = _lit(real)
    greens = [v for v in lit.values() if v[1] > v[0] and v[1] > v[2]]
    reds = [v for v in lit.values() if v[0] > v[1] and v[0] > v[2]]
    # both an above-prev (green) and below-prev (red) sample rendered
    assert greens and reds


def test_endpoint_is_white():
    real = _real()
    q = SymbolQuote(sym="X", price=110.0, prev=100.0)
    for p in [100.0, 108.0, 110.0]:
        q.spark.append(p)
    draw_sparkline(real, 0, 0, 200, 24, q, dim=1.0)
    assert any(v == (255, 255, 255) for v in real._pixels.values())


def test_reference_line_sits_at_prev_level_not_box_mid_height():
    """Spec §7: the dotted reference marks the prev-close LEVEL, not the box
    mid-height. All samples here are ABOVE prev, so folding `prev` into the
    vertical range pushes the reference to the BOTTOM of the box — a
    mid-height reference (the pre-fix behavior) would instead land it in
    the middle of the sample cluster, contradicting "above-prev renders
    above the reference"."""
    real = _real(w=200, h=24)
    q = SymbolQuote(sym="X", price=110.0, prev=90.0)
    for p in [100.0, 102.0, 105.0, 110.0]:  # every sample is above prev=90
        q.spark.append(p)
    draw_sparkline(real, 0, 0, 200, 24, q, dim=1.0)
    lit = _lit(real)

    # The reference row is the dimmed LABEL color (not white/green/red).
    ref_color = _rgb(pal.dim(pal.LABEL, 1.0 * _REF_BRIGHT))
    ref_ys = {y for (x, y), v in lit.items() if v == ref_color}
    assert ref_ys, "no reference-colored pixels found"
    ref_y = next(iter(ref_ys))
    assert len(ref_ys) == 1  # a single flat reference row

    # prev=90 is the box-range MINIMUM (all samples are above it), so the
    # reference should sit at the very bottom of the box — box mid-height
    # (row 11 or 12 of a 24-tall box) would be a clear miss.
    assert ref_y == 24 - 1

    # every above-prev (green) sample must render ABOVE the reference row
    # (smaller y = higher on the panel).
    greens = {y for (x, y), v in lit.items() if v[1] > v[0] and v[1] > v[2]}
    assert greens
    assert all(y < ref_y for y in greens)


def test_reference_line_relocates_when_samples_are_below_prev():
    """Mirror of the above with every sample BELOW prev: the reference
    should land at the box TOP, and every red (below-prev) sample should
    render BELOW it."""
    real = _real(w=200, h=24)
    q = SymbolQuote(sym="X", price=85.0, prev=110.0)
    for p in [100.0, 95.0, 90.0, 85.0]:  # every sample is below prev=110
        q.spark.append(p)
    draw_sparkline(real, 0, 0, 200, 24, q, dim=1.0)
    lit = _lit(real)

    ref_color = _rgb(pal.dim(pal.LABEL, 1.0 * _REF_BRIGHT))
    ref_ys = {y for (x, y), v in lit.items() if v == ref_color}
    assert ref_ys
    ref_y = next(iter(ref_ys))
    assert len(ref_ys) == 1
    assert ref_y == 0  # prev=110 is the box-range MAXIMUM -> reference at top

    reds = {y for (x, y), v in lit.items() if v[0] > v[1] and v[0] > v[2]}
    assert reds
    assert all(y > ref_y for y in reds)


def test_green_up_false_flips_sparkline_point_colors():
    """`green_up=False` swaps the above-/below-prev point colors (Phase 2
    final-review Fix 1). Checks the exact pixel each sample lands on (rather
    than an aggregate "any green"/"any red" over the whole sparkline, which
    can't tell a color flip apart from a merely-different mix — both above-
    and below-prev samples are present here, so flipping swaps which one is
    which rather than eliminating a color outright)."""
    q = SymbolQuote(sym="X", price=110.0, prev=100.0)
    for p in [100.0, 105.0, 95.0, 110.0]:  # above, above, below, above prev
        q.spark.append(p)

    default = _real()
    draw_sparkline(default, 0, 0, 200, 24, q, dim=1.0)
    flipped = _real()
    draw_sparkline(flipped, 0, 0, 200, 24, q, dim=1.0, green_up=False)

    def green(v):
        return v[1] > v[0] and v[1] > v[2]

    def red(v):
        return v[0] > v[1] and v[0] > v[2]

    # Sample index 1 (p=105.0) is ABOVE prev=100.0 -> its plotted point
    # lands at (sx, sy) = (66, 8) given w=200, h=24, lo=95, hi=110 (prev
    # folded into the range per Fix 2). Sample index 2 (p=95.0) is BELOW
    # prev -> lands at (132, 23).
    above_pt = (66, 8)
    below_pt = (132, 23)

    assert green(default._pixels[above_pt])
    assert red(default._pixels[below_pt])
    assert red(flipped._pixels[above_pt])  # flipped: above-prev now renders red
    assert green(flipped._pixels[below_pt])  # flipped: below-prev now renders green


def test_dim_lowers_brightness():
    q = SymbolQuote(sym="X", price=110.0, prev=100.0)
    for p in [100.0, 108.0, 110.0]:
        q.spark.append(p)
    full = _real()
    draw_sparkline(full, 0, 0, 200, 24, q, dim=1.0)
    dimmed = _real()
    draw_sparkline(dimmed, 0, 0, 200, 24, q, dim=0.45)

    def bright(real):
        return sum(sum(v) for v in real._pixels.values())

    assert bright(dimmed) < bright(full)
