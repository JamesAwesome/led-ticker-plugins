from led_ticker import _plugin_loader as L


def test_entry_point_registers_baseball_namespace():
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        loaded = {info.namespace for info in result.loaded}
        assert "baseball" in loaded, f"baseball plugin not discovered: {result}"

        from led_ticker.widgets import get_widget_class

        assert get_widget_class("baseball.scores") is not None
        assert get_widget_class("baseball.standings") is not None
        assert get_widget_class("baseball.promotions") is not None
        assert get_widget_class("baseball.statcast") is not None
        assert get_widget_class("baseball.attendance") is not None

        from led_ticker.transitions import get_transition_class

        assert get_transition_class("baseball.roll") is not None
        assert get_transition_class("baseball.roll_reverse") is not None
        assert get_transition_class("baseball.roll_alternating") is not None

        from led_ticker.pixel_emoji import EMOJI_REGISTRY, HIRES_REGISTRY

        assert "baseball.ball" in EMOJI_REGISTRY
        assert "baseball.ball" in HIRES_REGISTRY
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

        from led_ticker_baseball import _logos

        assert "baseball.phi" in emoji_slugs()
        # A scaled canvas advances by the hi-res sprite, an unscaled one by the
        # 8x8; the shared padding cancels in the difference.
        lo, hi = _logos.emoji("PHI")
        scaled = ScaledCanvas(HeadlessCanvas(512, 64), scale=4, content_height=16)
        plain = HeadlessCanvas(160, 16)
        lo_w = max(x for x, *_ in lo) + 1
        assert (
            measure_emoji_at(scaled, "baseball.phi")
            - measure_emoji_at(plain, "baseball.phi")
            == hi.logical_width(4) - lo_w
        )
    finally:
        L.reset_plugins()


def test_team_without_a_logo_is_skipped_not_fatal(monkeypatch):
    from led_ticker_baseball import _logos

    real = _logos.emoji
    monkeypatch.setattr(
        _logos, "emoji", lambda abbrev: None if abbrev == "PHI" else real(abbrev)
    )
    L.reset_plugins()
    try:
        result = L.load_plugins(None, entry_points_enabled=True)
        assert "baseball" in {info.namespace for info in result.loaded}
        from led_ticker.plugin import emoji_slugs

        assert "baseball.phi" not in emoji_slugs()
        assert "baseball.nyy" in emoji_slugs()
        assert "baseball.ball" in emoji_slugs()
    finally:
        L.reset_plugins()
