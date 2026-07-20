"""Layout names + geometry resolver for baseball.scores.

`resolve_layout` is stateless and runs fresh on every draw tick (flight
pattern) so hot-reloads and canvas swaps always re-resolve. The 400px
threshold splits bigsign (256 real px -> two_row) from longboi (512 ->
scoreboard), same convention as stocks/flight.

**Width-fit degrade for explicit `scoreboard`**: `layouts/scoreboard.py`'s
physical renderer hardcodes anchors (e.g. the home name/score/dashes at
`504`, the live cluster from `x=176`) that assume a >=400 physical-px panel
(longboi). An explicit `layout = "scoreboard"` on a narrower panel (e.g.
bigsign, 256 physical px) would silently clip the ENTIRE home side to
nothing — no error, no log (final review, Finding 3). So `resolve_layout`
degrades explicit `scoreboard` at `scale > 1` and `phys_w < 400` to
`two_row` instead — the same landing spot `auto` would already pick for
that panel. Explicit `two_row` (and `ticker`) are unaffected at any width:
`two_row`'s hardcoded anchors assume the WIDER of the two scale>1 panels
only cosmetically (content stays complete, just left-shifted — Finding 4,
not a data-loss bug), and `ticker` is self-scrolling at any width.
"""

VALID_LAYOUTS: tuple[str, ...] = ("auto", "ticker", "scoreboard", "two_row")

_AUTO_DASHBOARD_MIN_W = 400


def resolve_layout(cfg_layout: str, scale: int, phys_w: int) -> str:
    if cfg_layout == "scoreboard" and scale > 1 and phys_w < _AUTO_DASHBOARD_MIN_W:
        # Degrade guard — see module docstring. Mirrors what "auto" would
        # already resolve to on this panel; only an EXPLICIT "scoreboard"
        # needed the guard (auto never picks scoreboard below the
        # threshold in the first place).
        return "two_row"
    if cfg_layout != "auto":
        return cfg_layout
    if scale <= 1:
        return "ticker"
    if phys_w >= _AUTO_DASHBOARD_MIN_W:
        return "scoreboard"
    return "two_row"


# Same 400px physical-width threshold as `_AUTO_DASHBOARD_MIN_W` above
# (bigsign 256 -> narrow, longboi 512 -> wide) — kept as its own constant
# rather than shared because `resolve_promo_layout`'s outcome names ("card"
# / "ticker") differ from `resolve_layout`'s ("scoreboard" / "two_row") and
# a future change to one threshold shouldn't silently drag the other along.
# Mirrors `layouts/promo_card.py`'s own `_WIDE_MIN_W` (that module picks its
# BIG-vs-LONG geometry independently, purely off `real.width`; this constant
# is only for the WIDGET-level ticker-vs-card story-shape decision).
_PROMO_AUTO_WIDE_MIN_W = 400


def resolve_promo_layout(cfg_layout: str, scale: int, phys_w: int) -> str:
    """Resolve `baseball.promotions`' `layout` config to a draw-time shape.

    Lives here (not `promotions.py`) so `_promo_card.py` can import it
    without creating a cycle: `MLBPromoCard` needs it at draw time but must
    not import `promotions.py` at module level (that module imports
    `MLBPromoCard` back, to build `feed_stories` — the same one-directional
    dependency shape as `scores.py` -> `_card.py`).

    scale <= 1 has no hires renderer at all (mirrors `resolve_layout`'s own
    ``scale <= 1 -> "ticker"`` fallback) — MLBPromoCard forwards to its
    pre-built legacy SegmentMessage in that case regardless of what this
    returns, so "legacy" here is documentation of intent more than a value
    any caller branches on. At scale > 1, an EXPLICIT `cfg_layout`
    ("ticker" / "card") passes through unchanged; "auto" maps by physical
    width — narrow (bigsign) holds the card, wide (longboi) runs the hires
    crawl (design: docs/superpowers/specs — Phase 3 promotions).
    """
    if scale <= 1:
        return "legacy"
    if cfg_layout != "auto":
        return cfg_layout
    return "card" if phys_w < _PROMO_AUTO_WIDE_MIN_W else "ticker"
