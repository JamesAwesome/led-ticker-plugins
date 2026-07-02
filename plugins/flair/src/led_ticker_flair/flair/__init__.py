"""led-ticker-flair / flair: the wheel's own namespace — text animations.

The entry-point name ``flair`` is the plugin namespace, so animations are
referenced in config.toml as ``animation = "flair.propeller"``.

Unlike the four sprite families, this namespace is named after the wheel
itself (documented exception to the namespace-per-sprite-family pattern).
"""


def _import_seam():
    """Import the core rotation seam; raise an actionable error when the
    installed core predates it (version-skew guard, spec §9)."""
    try:
        from led_ticker.plugin import ENGINE_TICK_MS  # noqa: F401, PLC0415
    except ImportError as exc:
        raise ImportError(
            "flair.propeller requires led-ticker-core >= 4.3 (the "
            "AnimationFrame.rotation seam and the ENGINE_TICK_MS export). "
            "Update the core image, not the flair plugin."
        ) from exc


def register(api):
    _import_seam()
    from led_ticker_flair.flair.propeller import Propeller  # noqa: PLC0415

    api.animation("propeller")(Propeller)
