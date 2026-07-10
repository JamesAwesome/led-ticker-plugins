"""led-ticker-flair / flair: the wheel's own namespace — text animations
and transitions.

The entry-point name ``flair`` is the plugin namespace, so animations are
referenced in config.toml as ``animation = "flair.propeller"`` and
transitions as ``transition = "flair.spinout"``.

Unlike the four sprite families, this namespace is named after the wheel
itself (documented exception to the namespace-per-sprite-family pattern).
"""


def _import_seam():
    """Import the core lens seam; raise an actionable error when the
    installed core predates it (version-skew guard, spec §9).

    Probes ``LensSpec`` — the actual 4.7 export — rather than
    ``make_rotation_surface`` (a 4.6 symbol). Probing a 4.6 symbol while
    claiming '>= 4.7' is a no-op guard that lets a 4.6 core through to a
    raw ImportError inside registration. Since register() registers
    propeller, spinout, AND fisheye together and the pyproject floor is
    >= 4.7 anyway, failing the whole register() on < 4.7 is consistent
    with the versioning contract.
    """
    try:
        from led_ticker.plugin import LensSpec  # noqa: F401, PLC0415
    except ImportError as exc:
        raise ImportError(
            "flair requires led-ticker-core >= 4.7 (the LensSpec animation "
            "seam); update the core image, not the flair plugin."
        ) from exc


def register(api):
    _import_seam()
    from led_ticker_flair.flair.fireworks import Fireworks  # noqa: PLC0415
    from led_ticker_flair.flair.fisheye import Fisheye  # noqa: PLC0415
    from led_ticker_flair.flair.lottery import Lottery  # noqa: PLC0415
    from led_ticker_flair.flair.propeller import Propeller  # noqa: PLC0415
    from led_ticker_flair.flair.spinout import Spinout  # noqa: PLC0415

    api.animation("propeller")(Propeller)
    api.animation("fisheye")(Fisheye)
    api.transition("spinout")(Spinout)
    api.transition("fireworks")(Fireworks)
    api.widget("lottery")(Lottery)
