"""weather.forecast — held multi-day forecast card with per-sign layouts.

`resolve_forecast_layout` is stateless and runs fresh on every draw tick
(flight pattern) so hot-reloads and canvas swaps always re-resolve. The
400px physical-width threshold splits bigsign (256 -> "big") from longboi
(512 -> "long"), the same convention as baseball/flight/stocks.
"""

VALID_LAYOUTS: tuple[str, ...] = ("auto", "strip", "big", "long")

_WIDE_MIN_W = 400


def resolve_forecast_layout(cfg_layout: str, scale: int, phys_w: int) -> str:
    if scale <= 1:
        return "strip"  # hi-res layouts are impossible on a scale-1 sign
    if cfg_layout == "long" and phys_w < _WIDE_MIN_W:
        # Width-fit degrade: render_hero_long hardcodes anchors out to
        # x~506; on a 256px panel it would draw mostly off-panel — land on
        # what "auto" would already pick there instead.
        return "big"
    if cfg_layout != "auto":
        return cfg_layout
    return "big" if phys_w < _WIDE_MIN_W else "long"
