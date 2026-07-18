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
