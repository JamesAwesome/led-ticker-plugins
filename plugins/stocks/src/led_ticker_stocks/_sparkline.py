"""Intraday sparkline: prev-close reference + up/down points from quote.spark."""

from led_ticker.plugin import is_scaled, unwrap_to_real

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._paint import px

_REF_BRIGHT = 0.55
_GAPFILL_BRIGHT = 0.55


def draw_sparkline(
    canvas, x: int, y: int, w: int, h: int, quote, *, dim: float, green_up: bool = True
) -> None:
    real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
    samples = list(quote.spark)
    ref_color = pal.dim(pal.LABEL, dim * _REF_BRIGHT)
    prev = quote.prev if quote.prev else (samples[0] if samples else 0.0)
    up_color = pal.UP if green_up else pal.DOWN
    down_color = pal.DOWN if green_up else pal.UP

    if len(samples) < 2:
        # Cold start / market-closed-since-boot: no range to plot against, so
        # there's no meaningful lo/hi span — draw the dotted reference at
        # box-center (there's nothing for it to be "relative to" yet).
        ref_y = y + h // 2
        for gx in range(0, w, 3):
            px(real, x + gx, ref_y, ref_color)
        return

    # Fold `prev` into the vertical range so the reference line always sits
    # in-box (Spec §7): the dotted line marks the prev-close LEVEL, not the
    # box mid-height, so above-prev (green) samples land above it and
    # below-prev (red) samples land below it, even if every sample in
    # `spark` happens to be on one side of prev.
    lo = min(*samples, prev)
    hi = max(*samples, prev)
    span = (hi - lo) or 1.0

    def sample_y(v):
        # higher value -> higher on panel (smaller y)
        return y + h - 1 - int((v - lo) / span * (h - 1))

    ref_y = min(max(sample_y(prev), y), y + h - 1)
    for gx in range(0, w, 3):
        px(real, x + gx, ref_y, ref_color)

    prev_pt = None
    for i, v in enumerate(samples):
        sx = x + int(i / (len(samples) - 1) * (w - 1))
        sy = sample_y(v)
        color = pal.dim(up_color if v >= prev else down_color, dim)
        px(real, sx, sy, color)
        # vertical gap-fill between adjacent samples
        if prev_pt is not None:
            _, psy = prev_pt
            side_color = up_color if v >= prev else down_color
            gap_color = pal.dim(side_color, dim * _GAPFILL_BRIGHT)
            step = 1 if sy >= psy else -1
            for gy in range(psy, sy, step):
                px(real, sx, gy, gap_color)
        prev_pt = (sx, sy)

    # static white endpoint (pulse is Phase 3)
    ex = x + w - 1
    ey = sample_y(samples[-1])
    px(real, ex, ey, pal.dim(pal.WHITE, dim))
