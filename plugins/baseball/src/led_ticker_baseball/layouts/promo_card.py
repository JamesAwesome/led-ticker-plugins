"""Held promo card — port of design `promoBig` (dc.html ~477-488) and a
MERGED `promoLongCard` + `promoLongScroll` (dc.html ~540-555 / ~528-539).

The prototype ships `promoLongCard` (plain-drawn name, "PROMOTION" label,
paging dots, cycles through several promos on its own clock) and
`promoLongScroll` (a SEPARATE static demo of one over-wide promo name via
`maskScroll`, plus a `fitText`-ellipsized sub line) as two different pages.
This module ports ONE long-layout renderer that has both behaviors: the
promo name always goes through `_mask.mask_scroll` (band `[6, 300)`;
px26/y21 rather than the prototype's px22/y18 — see `_render_long`'s
vertical-rhythm comment) — for a promo name that fits the band that's
equivalent to `promoLongCard`'s plain draw (mask_scroll's own fast path is
a single static blit), and for an over-wide name it scrolls like
`promoLongScroll`.
The 256px BIG layout gets the same treatment (band `[4, 252)` at px16) for
consistency, even though the prototype's `promoBig` never scrolls its name
— the handoff's own promo fixtures are all short enough there anyway.

Selected by `real.width >= 400` (same threshold + rationale as
`layouts/standings_board.py`).

Vertical-metrics conversion: every RAW `hires()` call in this module (i.e.
every draw NOT routed through `mask_scroll`) takes a dc.html cap-top
`y_target` and goes through `_t` (this module's local wrapper, same shape
as `standings_board._t`) which applies `_paint.cap_top`. Calls THROUGH
`mask_scroll` do NOT get this treatment — `_mask.py`'s own contract is that
its `y` argument is ALREADY cap-top-space (baked into `TextMask.pixels`'
offsets), so a caller applying `cap_top()` before calling it would double
the correction. See `_mask.py`'s module docstring for the derivation.

Uppercasing: the handoff fixtures are all-caps; `PromoInfo` fields come
from the live MLB API in whatever case the feed provides (mixed/title
case), so `name`/`offer_type`/`presented_by`/`opponent_abbr` are upper()'d
at render time here — never persisted upstream, so a future consumer of
the raw `PromoInfo` (e.g. a plain-text ticker story) isn't affected.
"""

from typing import TYPE_CHECKING

from led_ticker.plugin import safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._mask import mask_scroll
from led_ticker_baseball._paint import (
    _hires_safe,
    cap_top,
    fit_text,
    hires,
    paging_dots,
    phys_wrap,
    text_width,
)
from led_ticker_baseball._primitives import chip

if TYPE_CHECKING:
    # Deferred: led_ticker_baseball.promotions has no reason to import this
    # module today, but this mirrors standings_board.py's guard against a
    # future cycle — string-quoted so PEP 649 introspection can't NameError.
    from led_ticker_baseball.promotions import PromoInfo

_WIDE_MIN_W = 400

# Physical-px gap enforced between the BIG layout's fit_text-ellipsized sub
# line and the right-anchored time block, on top of the sub line's own x
# origin (4) — see `_render_big`'s `sub_max_w` derivation. Not part of the
# dc.html handoff (`promoBig` never calls `fitText` on its sub line at all,
# trusting the fixture data to fit); added here because a live promo's
# offerType + presentedBy combo can run long enough to collide with the
# time ("FAN EXPERIENCE · BY NEW ERA" is the worst case in practice).
_BIG_SUB_TIME_GAP = 4


def _t(shim, text, x, y_target, color, size, *, bold=True):
    return hires(shim, text, x, cap_top(y_target, size), color, size, bold=bold)


def _promo_sub(promo: "PromoInfo") -> str:  # noqa: UP037 — introspection-safe forward ref
    """Port of `promoSub` (dc.html ~476): "<OFFER> · BY <SPONSOR>".

    The JS source is `p.offerType + (p.presentedBy ? " · BY "+sponsor : "")`
    — literally ported, an empty `offerType` with a `presentedBy` set would
    render a bare " · BY SPONSOR" (leading space + dot, no offer text
    before it). Guarded here: the dot separator only appears when BOTH
    sides are present; sponsor-only degrades to "BY SPONSOR" (no dot),
    offer-only to "OFFER", and both-empty to "" (never raises).

    `offer`/`sponsor` are sanitized through `_paint._hires_safe` (F1: a
    mapped Unicode emoji paints wider than it measures — see that
    function's docstring) before composing the returned string, so this
    line's `fit_text`/`hires` calls stay measure/paint-consistent regardless
    of what a live feed's `offer_type`/`presented_by` strings contain.
    """
    offer = _hires_safe(promo.offer_type.upper()) if promo.offer_type else ""
    sponsor = _hires_safe(promo.presented_by.upper()) if promo.presented_by else ""
    if offer and sponsor:
        return f"{offer} · BY {sponsor}"
    if sponsor:
        return f"BY {sponsor}"
    return offer


def render_promo_card(
    canvas,
    promo: "PromoInfo",  # noqa: UP037 — introspection-safe forward ref
    clock_ms: float,
    *,
    y_offset: int = 0,
    story_index: int = 0,
    story_total: int = 1,
) -> None:
    """Draw one promo. `clock_ms` only drives the name's scroll-if-overflow
    (`_mask.mask_scroll`) — WHICH promo to show is the caller's job (unlike
    the prototype's own `Math.floor(ctx.t/period)%len` self-rotation);
    `story_index`/`story_total` size the paging dots, same convention as
    `layouts/two_row.py`/`layouts/scoreboard.py`.
    """
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)
    if real.width >= _WIDE_MIN_W:
        _render_long(shim, real, promo, clock_ms, yo, story_index, story_total)
    else:
        _render_big(shim, real, promo, clock_ms, yo, story_index, story_total)


def _render_big(shim, real, promo, clock_ms, yo, story_index, story_total):
    opp = (promo.opponent_abbr or "").upper()
    # F1: sanitize free-form promo text (name) before it reaches
    # `mask_scroll` — see `_paint._hires_safe`'s docstring.
    name = _hires_safe((promo.name or "").upper())
    time_text = f"{promo.time_label} {promo.am_pm}".strip()

    _t(shim, promo.date_label, 4, 1 + yo, pal.AMBER, 9)
    mask_scroll(real, name, 4, 252, 14 + yo, pal.IDENT, 16, clock_ms)
    chip(real, 4, 35 + yo, 11, opp)
    _t(shim, f"VS {opp}", 19, 35 + yo, pal.VIOLET, 12)

    tw = text_width(11, time_text, bold=False)
    time_x = 252 - tw
    sub_max_w = time_x - _BIG_SUB_TIME_GAP - 4
    sub = fit_text(_promo_sub(promo), sub_max_w, 11, bold=False)
    _t(shim, sub, 4, 50 + yo, pal.CYAN, 11, bold=False)
    _t(shim, time_text, time_x, 50 + yo, pal.AMBER, 11, bold=False)

    if story_total > 1:
        paging_dots(real, story_total, story_index, 256 - story_total * 8 - 4, 2 + yo)


def _render_long(shim, real, promo, clock_ms, yo, story_index, story_total):
    opp = (promo.opponent_abbr or "").upper()
    # F1: sanitize free-form promo text (name) before it reaches
    # `mask_scroll` — see `_paint._hires_safe`'s docstring.
    name = _hires_safe((promo.name or "").upper())
    time_text = f"{promo.time_label} {promo.am_pm}".strip()

    # Left column vertical rhythm (deviation from the prototype's px22 name
    # at y18 — hardware feedback, longboi 2026-07-20 round 2): the
    # prototype's spacing read as date -> 5px gap -> name -> 15px gap ->
    # PROMOTION on the panel. The name marquee is px26 seated at y21 so
    # both gaps land at 8-9px (the date-bottom..PROMOTION-top span is fixed
    # at 36 rows; cap(26) ~= 19 rows leaves ~8.5 per side).
    _t(shim, promo.date_label, 6, 4 + yo, pal.AMBER, 12)
    mask_scroll(real, name, 6, 300, 21 + yo, pal.IDENT, 26, clock_ms)
    _t(shim, "PROMOTION", 6, 50 + yo, pal.LABEL, 9)

    # Right block, right-justified (deviation from the prototype's fixed
    # rx=308 + left-flowed time, `promoLongCard` dc.html ~544-548 — same
    # hardware findings, longboi 2026-07-20): the time right-anchors at
    # width-6 (mirroring the BIG layout's `252 - tw` anchor and the left
    # column's x=6 margin), the chip + "VS OPP" block anchors off the
    # time's x with a fixed 14px gap (the prototype's fixed rx stranded
    # ~67px of dead space before a right-anchored time), and the sub line
    # right-anchors under the time so the block's right edge is a single
    # clean line. `rx` floors at the prototype's 308 so pathological data
    # (an absurdly wide time/opponent string) widens the VS->time gap
    # instead of invading the name band's [300,308) buffer.
    tw = text_width(14, time_text, bold=False)
    time_x = real.width - 6 - tw
    vs_text = f"VS {opp}"
    rx = max(308, time_x - 14 - text_width(16, vs_text) - 18)
    chip(real, rx, 8 + yo, 13, opp)
    _t(shim, vs_text, rx + 18, 8 + yo, pal.VIOLET, 16)
    _t(shim, time_text, time_x, 10 + yo, pal.AMBER, 14, bold=False)
    sub = fit_text(_promo_sub(promo), 196, 14, bold=False)
    sub_x = real.width - 6 - text_width(14, sub, bold=False)
    _t(shim, sub, sub_x, 36 + yo, pal.CYAN, 14, bold=False)

    if story_total > 1:
        paging_dots(
            real,
            story_total,
            story_index,
            real.width - story_total * 8 - 6,
            real.height - 10 + yo,
        )
