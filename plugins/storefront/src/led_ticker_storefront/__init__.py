"""led-ticker-storefront: always-visible OPEN/CLOSED business-hours badge.

Registers a frame overlay + a startup poller that flip the badge from a
weekly schedule and the clock. Configured via the top-level [storefront]
block (an overlay, not a playlist widget). Overlay wiring is added in a
later task; this stub registers the namespace for entry-point discovery."""


def register(api):
    # Overlay wiring (api.on_startup + api.overlay) is added in the wiring
    # task once the overlay module exists. Namespace discovery only for now.
    return
