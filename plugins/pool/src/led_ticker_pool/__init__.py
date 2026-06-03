"""led-ticker-pool: a pool water-temperature monitor widget for led-ticker.

Contributed to led-ticker via the ``led_ticker.plugins`` entry point (see
pyproject.toml). The entry-point name ``pool`` is the plugin namespace, so the
widget is referenced in a led-ticker config as ``type = "pool.monitor"``.
"""


def register(api):
    """led-ticker plugin entry point. Receives a namespace-bound PluginAPI.

    Phase 3 ports the real PoolMonitor here (registered as ``monitor`` →
    ``pool.monitor``). For now a trivial widget proves the entry-point channel
    resolves and the namespace is bound correctly.
    """

    @api.widget("monitor")
    class _Placeholder:
        def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
            return canvas, cursor_pos
