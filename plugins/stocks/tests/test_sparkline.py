from led_ticker.plugin import HeadlessBackend

from led_ticker_stocks._sparkline import draw_sparkline
from led_ticker_stocks.model import SymbolQuote


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
