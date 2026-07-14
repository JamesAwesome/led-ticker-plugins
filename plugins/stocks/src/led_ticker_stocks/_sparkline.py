"""Intraday sparkline: prev-close reference + up/down points from quote.spark."""

from led_ticker.plugin import is_scaled, unwrap_to_real

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._paint import px

_REF_BRIGHT = 0.55
_GAPFILL_BRIGHT = 0.55


def draw_sparkline(
    canvas, x: int, y: int, w: int, h: int, quote, *, dim: float
) -> None:
    real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
    samples = list(quote.spark)
    ref_color = pal.dim(pal.LABEL, dim * _REF_BRIGHT)
    mid_y = y + h // 2

    # dotted prev-close reference (1 px every 3)
    for gx in range(0, w, 3):
        px(real, x + gx, mid_y, ref_color)

    if len(samples) < 2:
        return  # cold start / market-closed-since-boot: reference only

    lo, hi = min(samples), max(samples)
    span = (hi - lo) or 1.0
    prev = quote.prev if quote.prev else samples[0]

    def sample_y(v):
        # higher value -> higher on panel (smaller y)
        return y + h - 1 - int((v - lo) / span * (h - 1))

    prev_pt = None
    for i, v in enumerate(samples):
        sx = x + int(i / (len(samples) - 1) * (w - 1))
        sy = sample_y(v)
        color = pal.dim(pal.UP if v >= prev else pal.DOWN, dim)
        px(real, sx, sy, color)
        # vertical gap-fill between adjacent samples
        if prev_pt is not None:
            _, psy = prev_pt
            side_color = pal.UP if v >= prev else pal.DOWN
            gap_color = pal.dim(side_color, dim * _GAPFILL_BRIGHT)
            step = 1 if sy >= psy else -1
            for gy in range(psy, sy, step):
                px(real, sx, gy, gap_color)
        prev_pt = (sx, sy)

    # static white endpoint (pulse is Phase 3)
    ex = x + w - 1
    ey = sample_y(samples[-1])
    px(real, ex, ey, pal.dim(pal.WHITE, dim))
