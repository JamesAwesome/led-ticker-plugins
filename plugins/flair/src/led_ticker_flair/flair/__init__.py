"""led-ticker-flair / flair: the wheel's own namespace — text animations
and transitions.

The entry-point name ``flair`` is the plugin namespace, so animations are
referenced in config.toml as ``animation = "flair.propeller"`` and
transitions as ``transition = "flair.spinout"``.

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
    """
    try:
        from led_ticker.plugin import LensSpec  # noqa: F401, PLC0415
    except ImportError as exc:
        raise ImportError(
            "flair requires led-ticker-core >= 4.7 (the LensSpec animation "
            "seam); update the core image, not the flair plugin."
        ) from exc
    try:
        from led_ticker.plugin import emoji_slugs  # noqa: F401, PLC0415
    except ImportError as exc:
        raise ImportError(
            "flair requires led-ticker-core >= 4.18 (the emoji_slugs seam "
            "flair.stickers needs); update the core image, not the flair "
            "plugin."
        ) from exc


def register(api):
    _import_seam()
    from led_ticker_flair.flair.fireworks import Fireworks  # noqa: PLC0415
    from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415
    from led_ticker_flair.flair.lottery import Lottery  # noqa: PLC0415
    from led_ticker_flair.flair.propeller import Propeller  # noqa: PLC0415
    from led_ticker_flair.flair.spinout import Spinout  # noqa: PLC0415
    from led_ticker_flair.flair.stickers import Stickers  # noqa: PLC0415

    api.animation("propeller")(Propeller)
    api.animation("fisheye")(Fisheye)
    api.transition("spinout")(Spinout)
    api.transition("fireworks")(Fireworks)
    api.transition("stickers")(Stickers)
    api.widget("lottery")(Lottery)
