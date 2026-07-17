"""Layout names + geometry resolver for baseball.scores.

`resolve_layout` is stateless and runs fresh on every draw tick (flight
pattern) so hot-reloads and canvas swaps always re-resolve. The 400px
threshold splits bigsign (256 real px -> two_row) from longboi (512 ->
scoreboard), same convention as stocks/flight.
"""

VALID_LAYOUTS: tuple[str, ...] = ("auto", "ticker", "scoreboard", "two_row")

_AUTO_DASHBOARD_MIN_W = 400


def resolve_layout(cfg_layout: str, scale: int, phys_w: int) -> str:
    if cfg_layout != "auto":
        return cfg_layout
    if scale <= 1:
        return "ticker"
    if phys_w >= _AUTO_DASHBOARD_MIN_W:
        return "scoreboard"
    return "two_row"
