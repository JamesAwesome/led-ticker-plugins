from led_ticker import _plugin_loader as L


def test_entry_point_registers_football_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "football" in loaded, f"football plugin not discovered: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("football.scores") is not None

        from led_ticker.plugin import emoji_slugs

        assert "football.ball" in emoji_slugs()
    finally:
        L.reset_plugins()


def test_team_logo_emoji_registered():
    L.reset_plugins()
    try:
        L.load_plugins(None, entry_points_enabled=True)
        from led_ticker.plugin import (
            HeadlessCanvas,
            ScaledCanvas,
            emoji_slugs,
            measure_emoji_at,
        )

        from led_ticker_football import _logos

        assert "football.phi" in emoji_slugs()
        # A scaled canvas advances by the hi-res sprite, an unscaled one by the
        # 8x8; the shared padding cancels in the difference.
        lo, hi = _logos.emoji("PHI")
        scaled = ScaledCanvas(HeadlessCanvas(512, 64), scale=4, content_height=16)
        plain = HeadlessCanvas(160, 16)
        lo_w = max(x for x, *_ in lo) + 1
        assert (
            measure_emoji_at(scaled, "football.phi")
            - measure_emoji_at(plain, "football.phi")
            == hi.logical_width(4) - lo_w
        )
    finally:
        L.reset_plugins()


def test_team_without_a_logo_is_skipped_not_fatal(monkeypatch):
    from led_ticker_football import _logos

    real = _logos.emoji
    monkeypatch.setattr(
        _logos, "emoji", lambda abbrev: None if abbrev == "PHI" else real(abbrev)
    )
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        assert "football" in {info.namespace for info in result.loaded}
        from led_ticker.plugin import emoji_slugs

        assert "football.phi" not in emoji_slugs()
        assert "football.nyg" in emoji_slugs()
    finally:
        L.reset_plugins()
