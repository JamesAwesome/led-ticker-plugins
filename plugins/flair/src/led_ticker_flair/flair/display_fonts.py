"""Bundled display fonts: four SIL-OFL typefaces whose style (outline, drop
shade) is baked into the glyphs, so a `message` gets outlined or shadowed
text with no styling code.

Referenced in config as ``font = "flair.BungeeShade"`` (also ``BungeeOutline``,
``LondrinaShadow``, ``LondrinaOutline``) with an explicit ``font_size``.
Bigsign only: at scale 4 the strokes are 1-2 real pixels; on a 16-row sign
they are unreadable. The files live in ``fonts/`` beside this module, with
one ``OFL-<Family>.txt`` each and ``SOURCES.md``.

Threshold 45: every one of the four holds continuous outlines at 45 across
36-56 px (moonbunny measurement 2026-11-20 plus the local size-range grid);
at the loader default of 128 the hairlines rasterize dashed. Core plugin API
``(1, 3)`` lets a plugin declare that default via ``api.font(..., threshold=)``;
an older core gets the two-arg call, the fonts render at 128, and ONE warning
tells the operator to set ``font_threshold = 45`` per widget.
"""

import logging

from led_ticker.plugin import API_VERSION

logger = logging.getLogger("led_ticker_flair")

DISPLAY_FONT_THRESHOLD: int = 45

# (registered name, file under fonts/). Names drop the "-Regular" stem.
DISPLAY_FONTS: tuple[tuple[str, str], ...] = (
    ("BungeeShade", "BungeeShade-Regular.ttf"),
    ("BungeeOutline", "BungeeOutline-Regular.ttf"),
    ("LondrinaShadow", "LondrinaShadow-Regular.ttf"),
    ("LondrinaOutline", "LondrinaOutline-Regular.ttf"),
)


def register_display_fonts(api) -> None:
    """Register the four fonts under the ``flair`` namespace.

    Paths are relative to the plugin root, which for the ``flair`` entry point
    is this module's directory, so ``fonts/<file>`` (not ``flair/fonts/...``).
    """
    if API_VERSION >= (1, 3):
        for name, file in DISPLAY_FONTS:
            api.font(name, f"fonts/{file}", threshold=DISPLAY_FONT_THRESHOLD)
        return
    for name, file in DISPLAY_FONTS:
        api.font(name, f"fonts/{file}")
    logger.warning(
        "flair display fonts need `font_threshold = 45` on this core (plugin "
        "API %s < (1, 3)); set it on each widget that uses them, or update the "
        "core image",
        API_VERSION,
    )
