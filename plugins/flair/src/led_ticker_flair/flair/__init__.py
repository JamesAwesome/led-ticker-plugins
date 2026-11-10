"""led-ticker-flair / flair: the wheel's own namespace — text animations
and transitions.

The entry-point name ``flair`` is the plugin namespace, so animations are
referenced in config.toml as ``animation = "flair.propeller"`` and
transitions as ``transition = "flair.spinout"`` (or the six
``flair.laser.<origin>`` beam-write variants, or the
``flair.accordion.<motion>[.alternating]`` card-deck variants).

The twinkle/blink/snow family adds ``animation = "flair.blink"`` and
``animation = "flair.twinkle"`` (per-character pixel gain), the
``background = "flair.twinkle"`` and ``background = "flair.snow"``
backgrounds, and the ``transition = "flair.snow"`` flurry transition.

Unlike the four sprite families, this namespace is named after the wheel
itself (documented exception to the namespace-per-sprite-family pattern).
"""


def _import_seam():
    """Import the core seams register() depends on; raise an actionable
    error when the installed core predates them (version-skew guard, spec
    §9).

    Probes ``LensSpec`` — the actual 4.7 export — rather than
    ``make_rotation_surface`` (a 4.6 symbol). Probing a 4.6 symbol while
    claiming '>= 4.7' is a no-op guard that lets a 4.6 core through to a
    raw ImportError inside registration. Since register() registers
    propeller, spinout, fisheye, AND stickers together and the pyproject
    floor is >= 4.18 anyway, failing the whole register() on < 4.18 is
    consistent with the versioning contract.

    Also probes ``emoji_slugs`` — the 4.18 export ``stickers.py`` needs at
    import time (its knob validation enumerates the drawable slug set).

    Also probes ``AnimationFrame.pixel_gain`` — the 4.33 field
    ``flair.twinkle`` / ``flair.blink`` deliver their per-character
    brightness through.
    """
    try:
        from led_ticker.plugin import LensSpec  # noqa: F401, PLC0415
    except ImportError as exc:
        raise ImportError(
            "flair requires led-ticker-core >= 4.7 (the LensSpec animation "
            "seam); update the core image, not the flair plugin."
        ) from exc
    try:
        from led_ticker.plugin import BackgroundEffectBase  # noqa: F401, PLC0415
    except ImportError as exc:
        raise ImportError(
            "flair requires led-ticker-core >= 4.32 (the BackgroundEffectBase "
            "seam the flair.fireworks background needs); update the core "
            "image, not the flair plugin."
        ) from exc
    try:
        from led_ticker.plugin import emoji_slugs  # noqa: F401, PLC0415
    except ImportError as exc:
        raise ImportError(
            "flair requires led-ticker-core >= 4.18 (the emoji_slugs seam "
            "flair.stickers needs); update the core image, not the flair "
            "plugin."
        ) from exc
    from led_ticker.plugin import AnimationFrame  # noqa: PLC0415

    if "pixel_gain" not in AnimationFrame.__dataclass_fields__:
        raise ImportError(
            "flair requires led-ticker-core >= 4.33 (the AnimationFrame.pixel_gain "
            "seam flair.twinkle needs); update the core image, not the flair "
            "plugin."
        )


def register(api):
    _import_seam()
    from led_ticker_flair.flair.accordion import (  # noqa: PLC0415
        AccordionStretch,
        AccordionStretchAlternating,
        AccordionSweep,
        AccordionSweepAlternating,
    )
    from led_ticker_flair.flair.blink import Blink  # noqa: PLC0415
    from led_ticker_flair.flair.fairy import (  # noqa: PLC0415
        Fairy,
        FairyAlternating,
        FairyReverse,
    )
    from led_ticker_flair.flair.fireworks import Fireworks  # noqa: PLC0415
    from led_ticker_flair.flair.fireworks_background import (  # noqa: PLC0415
        FireworksBackground,
    )
    from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415
    from led_ticker_flair.flair.laser import (  # noqa: PLC0415
        Laser,
        LaserAlternating,
        LaserBottom,
        LaserLeft,
        LaserRandom,
        LaserRight,
    )
    from led_ticker_flair.flair.lightning import Lightning  # noqa: PLC0415
    from led_ticker_flair.flair.lottery import Lottery  # noqa: PLC0415
    from led_ticker_flair.flair.poker import Poker  # noqa: PLC0415
    from led_ticker_flair.flair.propeller import Propeller  # noqa: PLC0415
    from led_ticker_flair.flair.snow import Snow  # noqa: PLC0415
    from led_ticker_flair.flair.snow_background import (  # noqa: PLC0415
        SnowBackground,
    )
    from led_ticker_flair.flair.spinout import Spinout  # noqa: PLC0415
    from led_ticker_flair.flair.stickers import Stickers  # noqa: PLC0415
    from led_ticker_flair.flair.twinkle import Twinkle  # noqa: PLC0415
    from led_ticker_flair.flair.twinkle_background import (  # noqa: PLC0415
        TwinkleBackground,
    )

    api.animation("propeller")(Propeller)
    api.animation("fisheye")(Fisheye)
    api.animation("blink")(Blink)
    api.animation("twinkle")(Twinkle)
    api.background("twinkle")(TwinkleBackground)
    api.background("snow")(SnowBackground)
    api.transition("snow")(Snow)
    api.transition("spinout")(Spinout)
    api.transition("fireworks")(Fireworks)
    api.background("fireworks")(FireworksBackground)
    api.transition("stickers")(Stickers)
    api.transition("poker")(Poker)
    api.transition("lightning")(Lightning)
    api.transition("fairy.forward")(Fairy)
    api.transition("fairy.reverse")(FairyReverse)
    api.transition("fairy.alternating")(FairyAlternating)
    api.transition("laser.top")(Laser)
    api.transition("laser.bottom")(LaserBottom)
    api.transition("laser.left")(LaserLeft)
    api.transition("laser.right")(LaserRight)
    api.transition("laser.alternating")(LaserAlternating)
    api.transition("laser.random")(LaserRandom)
    api.transition("accordion.sweep")(AccordionSweep)
    api.transition("accordion.stretch")(AccordionStretch)
    api.transition("accordion.sweep.alternating")(AccordionSweepAlternating)
    api.transition("accordion.stretch.alternating")(AccordionStretchAlternating)
    api.widget("lottery")(Lottery)
