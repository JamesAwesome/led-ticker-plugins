"""Hires ticker crawl segment run for ONE promo — port of design `promoLong`
(dc.html ~489-511), adapted to the ENGINE-scrolled cursor contract exactly
like `layouts/crawl.py` (scores). See that module's docstring for the full
rationale of the logical/physical seam (`cursor_pos`/return value are
LOGICAL; segments paint at physical resolution).

Text segments in `promoLong` are actually drawn through the prototype's
`drawStream` (which itself calls `hiresMask`+`blit`, not a raw `hires()`
draw) — but for an UNCLIPPED crawl (no fixed band to clip against, unlike
`promoLongScroll`'s `maskScroll`) a raw `hires()` draw produces the
identical frame with less machinery. `layouts/crawl.py` (scores) already
made this same simplification for its own segments (`tickerScores` also
routes through `drawStream`) — this module follows that precedent rather
than reaching for `_mask.py`.

The trailing inter-game "•" bullet dc.html draws between promos is DROPPED
here, same repo decision (2026-07-18) as `layouts/crawl.py`'s scores
segments: each promo is its own engine story, so the bullet would trail as
a lone grey dot in slideshow/ticker mode with nothing to separate. The
trailing gap left in its place (22px) matches `layouts/crawl.py`'s own
constant for the same reason.
"""

from led_ticker.plugin import resolve_font, safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import hires, js_round, phys_wrap, text_width
from led_ticker_baseball._primitives import chip

# Trailing inter-story gap — see module docstring ("bullet dropped").
_TRAILING_GAP = 22


def _promo_sub(promo) -> str:
    """Port of `promoSub` (dc.html ~476). Duplicated from
    `layouts/promo_card.py` rather than cross-imported — same precedent as
    `_score_color` being defined separately in `crawl.py`/`two_row.py`;
    each renderer stays self-contained. See `promo_card._promo_sub`'s
    docstring for the "never a bare '· BY X'" rationale.
    """
    offer = promo.offer_type.upper() if promo.offer_type else ""
    sponsor = promo.presented_by.upper() if promo.presented_by else ""
    if offer and sponsor:
        return f"{offer} · BY {sponsor}"
    if sponsor:
        return f"BY {sponsor}"
    return offer


def _y_for(px_size: int, *, bold: bool = True) -> int:
    """Vertical top for one crawl segment's text, ascent-corrected.

    Same derivation as `layouts/crawl.py`'s `_y_for` (see that module's
    docstring for the full explanation of why a naive port of the
    prototype's `y = round((64 - px*k)/2)` renders low) — but this crawl's
    segments use the design's `yc(px)` helper (dc.html ~225, factor 0.74),
    NOT `tickerScores`'/`ycP`'s 0.72. Each segment here also has its OWN px
    size (unlike the scores crawl's single shared `px_size` for the whole
    run), so this is called once per distinct (size, bold) pair rather than
    once for the whole segment run.
    """
    font = resolve_font("Inter-Bold" if bold else "Inter-Regular", px_size, 80)
    return js_round((64 + px_size * 0.74) / 2) - font.ascent


def _segments(promo):
    """Yield (kind, payload) segments; kind in {'text','gap','chip'}.
    text payload = (string, color, bold, size); chip payload = (team, h)."""
    opp = (promo.opponent_abbr or "").upper()
    name = (promo.name or "").upper()
    time_text = f"{promo.time_label} {promo.am_pm}".strip()
    return [
        ("text", (promo.date_label, pal.AMBER, True, 13)),
        ("gap", 9),
        ("text", (name, pal.IDENT, True, 17)),
        ("gap", 9),
        ("chip", (opp, 12)),
        ("gap", 5),
        ("text", (f"VS {opp}", pal.VIOLET, True, 13)),
        ("gap", 9),
        ("text", (_promo_sub(promo), pal.CYAN, False, 12)),
        ("gap", 9),
        ("text", (time_text, pal.AMBER, False, 12)),
        ("gap", _TRAILING_GAP),
    ]


def _seg_w(kind, payload):
    if kind == "gap":
        return payload
    if kind == "chip":
        _team, h = payload
        return h
    text, _color, bold, size = payload
    return text_width(size, text, bold=bold)


def render_promo_crawl(
    canvas, promo, cursor_pos: int, *, y_offset: int = 0, hold_padding: int = 0
) -> int:
    """Draw at LOGICAL `cursor_pos`; return the segment run's advance width,
    also in LOGICAL px. Mirrors `layouts/crawl.py`'s `render_crawl` engine
    contract exactly (logical cursor in, logical width out; held segments
    center, excluding the trailing gap; scrolling segments keep the left
    origin) — see that function's docstring for the full contract.
    """
    shim, real = phys_wrap(canvas)
    scale = safe_scale(canvas)
    yo = y_offset * scale
    segs = _segments(promo)
    seg_widths = [_seg_w(kind, payload) for kind, payload in segs]
    run_phys = sum(seg_widths)
    content_phys = (
        run_phys - seg_widths[-1] if segs and segs[-1][0] == "gap" else run_phys
    )
    logical_advance = -(-run_phys // scale)
    held = logical_advance + hold_padding <= canvas.width
    center_off = js_round((real.width - content_phys) / 2) if held else 0
    x = cursor_pos * scale + center_off
    total_phys = 0
    for (kind, payload), w in zip(segs, seg_widths, strict=True):
        # Culls are a performance guard only — hires()/chip() (via px())
        # clip safely at canvas edges, so a partially off-canvas segment
        # still renders correctly if the cull is skipped or slightly off.
        if kind == "text" and -w < x < real.width:
            text, color, bold, size = payload
            y = _y_for(size, bold=bold) + yo
            hires(shim, text, js_round(x), y, color, size, bold=bold)
        elif kind == "chip" and -w < x < real.width:
            team, h = payload
            cy = js_round((64 - h) / 2)
            chip(real, js_round(x), cy + yo, h, team)
        x += w
        total_phys += w
    return -(-total_phys // scale)
