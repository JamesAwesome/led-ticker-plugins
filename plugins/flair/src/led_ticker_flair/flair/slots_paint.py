"""flair.slots — reel geometry and painter. Pure: writes go through
``set_px`` and are clipped to the band window and the panel.

A reel is a vertical strip of symbols (cells) spaced ``pitch`` rows apart.
Symbol ``j`` sits at its home position when the strip offset ``d`` equals
``j * pitch``; as ``d`` grows the strip travels downward through the window.
"""

import math

from led_ticker_flair.flair.splitflap_board import BandGeom, FlapCell
from led_ticker_flair.flair.splitflap_paint import SetPx

SPIN_SHADE = 0.6  # brightness of symbols while the reel is spinning


def reel_pitch(band: BandGeom) -> tuple[int, int]:
    """``(pitch, gap)``: the window height plus a blank gap between symbols."""
    p = band.hi - band.lo + 1
    gap = max(1, round(p / 4))
    return p + gap, gap


def overshoot_rows(pitch: int, gap: int) -> int:
    """How far a reel dips past its stop before settling back."""
    return min(gap, max(1, round(pitch / 8)))


def strip_symbols(
    seq: tuple[FlapCell | None, ...], k: int
) -> tuple[FlapCell | None, ...]:
    """The reel strip: ``seq[0]``, ``k - 1`` cycled in-betweens, ``seq[-1]``."""
    mids = seq[1:-1] or (None, seq[0])
    return (seq[0], *(mids[i % len(mids)] for i in range(k - 1)), seq[-1])


def paint_reel(
    set_px: SetPx,
    strip: tuple[FlapCell | None, ...],
    band: BandGeom,
    d: float,
    shade: float,
    w: int,
    h: int,
) -> None:
    """Paint the strip at offset ``d``, clipped to the band window."""
    k = len(strip) - 1
    pitch, gap = reel_pitch(band)
    p = pitch - gap
    # The visit bound below assumes every cell's rows lie within the P-tall
    # band extent: true by construction (``lo``/``hi`` span every out and in
    # card in the band); a future board change could break it silently.
    shift = round(d)
    first = max(0, math.ceil((d - p) / pitch))
    last = min(k, math.floor((d + p) / pitch))
    for j in range(first, last + 1):
        cell = strip[j]
        if cell is None:
            continue
        dy = shift - j * pitch
        for y0, row in cell.rows.items():
            y = y0 + dy
            if not (band.lo <= y <= band.hi and 0 <= y < h):
                continue
            for dx, (r, g, b) in row:
                x = cell.slot + dx
                if 0 <= x < w:
                    if shade == 1.0:
                        set_px(x, y, r, g, b)
                    else:
                        set_px(
                            x, y, round(r * shade), round(g * shade), round(b * shade)
                        )
