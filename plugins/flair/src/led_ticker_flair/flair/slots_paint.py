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
    if len(mids) < 2:
        return (seq[0], *(mids[i % len(mids)] for i in range(k - 1)), seq[-1])
    out = [seq[0]]
    idx = 0
    for _ in range(k - 1):
        pick = mids[idx % len(mids)]
        if _same(pick, out[-1]):
            idx += 1  # a wrap would repeat the previous symbol: skip one
            pick = mids[idx % len(mids)]
        out.append(pick)
        idx += 1
    out.append(seq[-1])
    return tuple(out)


def _same(a: FlapCell | None, b: FlapCell | None) -> bool:
    if a is None or b is None:
        return a is b
    return a.rows_key() == b.rows_key()


def paint_reel(
    set_px: SetPx,
    strip: tuple[FlapCell | None, ...],
    band: BandGeom,
    d: float,
    shade: float,
    w: int,
    h: int,
    window: tuple[int, int, float],
) -> None:
    """Paint the strip at offset ``d``, clipped to the band's rows and to the
    column ``window`` ``(left, width, centre)``; every symbol is centred on the
    unrounded ``centre`` so a glide never steps backwards."""
    wl, ww, cx = window
    xlo, xhi = max(0, wl), min(w, wl + ww)
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
        ox = round(cx - cell.width / 2)
        if ox + cell.width <= xlo or ox >= xhi:
            continue
        for y0, row in cell.rows.items():
            y = y0 + dy
            if not (band.lo <= y <= band.hi and 0 <= y < h):
                continue
            for dx, (r, g, b) in row:
                x = ox + dx
                if xlo <= x < xhi:
                    if shade == 1.0:
                        set_px(x, y, r, g, b)
                    else:
                        set_px(
                            x, y, round(r * shade), round(g * shade), round(b * shade)
                        )
