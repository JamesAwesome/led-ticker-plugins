"""Layout names + resolver for football.scores.

`resolve_layout` is stateless and runs fresh on every draw tick so
hot-reloads and canvas swaps always re-resolve. `auto` is the scoreboard at
every scale (scale 1 renders it through the bitmap band board).
"""

VALID_LAYOUTS: tuple[str, ...] = ("auto", "scoreboard", "ticker")


def resolve_layout(cfg_layout: str, scale: int, phys_w: int) -> str:
    if cfg_layout != "auto":
        return cfg_layout
    return "scoreboard"
