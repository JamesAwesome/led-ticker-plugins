"""Layout names + resolver for tennis.scores.

`resolve_layout` is stateless and runs fresh on every draw tick (the
flight/baseball pattern) so hot-reloads and canvas swaps always re-resolve.

Unlike baseball there is no width-fit degrade: the physical scoreboard
(`layouts/scoreboard.py`) carries its own geometry for BOTH scale>1 panels
(bigsign 256px: sets-won + current-set games; longboi 512px: every set's
games), so `scoreboard` is safe at either width. Scale 1 renders through
the legacy text-glyph classes (`_scoreboard.py`).
"""

VALID_LAYOUTS: tuple[str, ...] = ("auto", "ticker", "scoreboard")


def resolve_layout(cfg_layout: str, scale: int, phys_w: int) -> str:
    if cfg_layout != "auto":
        return cfg_layout
    return "ticker" if scale <= 1 else "scoreboard"
