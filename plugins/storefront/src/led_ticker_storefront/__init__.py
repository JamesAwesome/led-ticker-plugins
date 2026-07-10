"""led-ticker-storefront: always-visible OPEN/CLOSED business-hours badge.

register(api) wires the real overlay: an api.on_startup hook that reads the
top-level [storefront] block, parses + validates the weekly schedule, does
an eager first evaluation, and spawns a background poll loop that flips the
badge from the schedule and the clock; plus an api.overlay hook that paints
the active badge on the real canvas every frame, before the hardware swap.
Configured via the top-level [storefront] block (an overlay, not a playlist
widget)."""


def register(api):
    from led_ticker_storefront.overlay import StorefrontOverlay

    overlay = StorefrontOverlay()
    api.on_startup(overlay.startup)
    api.overlay(overlay.paint)
