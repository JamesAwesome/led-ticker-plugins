"""led-ticker-storefront: always-visible OPEN/CLOSED business-hours badge.

Registers a frame overlay + a startup poller that flip the badge from a
weekly schedule and the clock. Configured via the top-level [storefront]
block (an overlay, not a playlist widget). Overlay wiring is added in a
later task; this stub registers the namespace for entry-point discovery."""


def register(api):
    from led_ticker_storefront.overlay import StorefrontOverlay

    overlay = StorefrontOverlay()
    api.on_startup(overlay.startup)
    api.overlay(overlay.paint)
