import unittest.mock as mock

import pytest
from led_ticker.plugin import unwrap_to_real

from led_ticker_weather.forecast import ForecastWidget


def _demo():
    return ForecastWidget(location="", demo=True)


class TestConstruction:
    def test_demo_seeds_handoff_week(self):
        w = _demo()
        assert w.should_display()

    def test_location_required_without_demo(self):
        with pytest.raises(ValueError, match="location"):
            ForecastWidget(location="")

    def test_dict_location_becomes_lat_lon_query(self):
        w = ForecastWidget(location={"lat": 40.71, "lon": -74.01})
        assert w.location == "40.71,-74.01"


class TestHeldCursor:
    def test_returns_logical_width_on_every_sign(self, smallsign, bigsign, longboi):
        w = _demo()
        for canvas in (smallsign, bigsign, longboi):
            _, cursor = w.draw(canvas)
            assert cursor == canvas.width  # LOGICAL width — never real.width

    def test_bigsign_cursor_is_wrapper_width_not_physical(self, bigsign):
        w = _demo()
        _, cursor = w.draw(bigsign)
        assert cursor == 64
        assert unwrap_to_real(bigsign).width == 256


class TestLayoutDispatch:
    def test_smallsign_renders_strip(self, smallsign):
        _demo().draw(smallsign)
        assert smallsign.count_nonzero() > 0

    def test_bigsign_renders_hero_big(self, bigsign, lit):
        _demo().draw(bigsign)
        real = unwrap_to_real(bigsign)
        assert lit(real, 112, 6, 113, 58)  # big layout's divider column

    def test_longboi_renders_hero_long(self, longboi, lit):
        _demo().draw(longboi)
        real = unwrap_to_real(longboi)
        assert lit(real, 156, 6, 157, 58)  # long layout's divider column

    def test_no_data_draws_nothing_and_holds(self, smallsign):
        w = ForecastWidget(location="Boston")
        assert not w.should_display()
        _, cursor = w.draw(smallsign)
        assert cursor == smallsign.width
        assert smallsign.count_nonzero() == 0


class TestUpdate:
    async def test_update_parses_and_flips_visibility(self, monkeypatch):
        # NOTE: brief specified a bare `from test_forecast_data import
        # _payload`; under this workspace's `--import-mode=importlib` +
        # `pythonpath = ["."]` config, `tests/` is never itself put on
        # sys.path, so the bare import 404s (verified: fails identically
        # whether this file alone or the whole `plugins` tree is
        # collected). `plugins/weather/tests` has no __init__.py, making
        # it a PEP 420 namespace package reachable from repo root, which
        # IS on sys.path — same root `make test` always runs from.
        from plugins.weather.tests.test_forecast_data import _payload

        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        w = ForecastWidget(location="Boston")
        with mock.patch(
            "led_ticker_weather.forecast.fetch_forecast",
            mock.AsyncMock(return_value=_payload()),
        ):
            await w.update()
        assert w.should_display()

    async def test_update_never_closes_shared_session(self, monkeypatch):
        from plugins.weather.tests.test_forecast_data import _payload

        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        session = mock.MagicMock()
        session.close = mock.AsyncMock()
        w = ForecastWidget(location="Boston", session=session)
        with mock.patch(
            "led_ticker_weather.forecast.fetch_forecast",
            mock.AsyncMock(return_value=_payload()),
        ):
            await w.update()
        session.close.assert_not_called()

    async def test_start_survives_failed_initial_fetch(self, monkeypatch):
        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
        with mock.patch(
            "led_ticker_weather.forecast.fetch_forecast",
            mock.AsyncMock(side_effect=ValueError("boom")),
        ):
            w = await ForecastWidget.start(location="Boston")
        assert not w.should_display()  # hidden, retrying in background

    async def test_start_polls_immediately_after_failed_eager_fetch(self, monkeypatch):
        # F1: a failed eager fetch must not fall into run_monitor_loop's
        # default immediate=False (a full update_interval, ~3h, of blind
        # should_display()==False before the first retry). Patch both
        # spawn_tracked and run_monitor_loop so no real background task is
        # created — the assertion is purely on the kwargs the loop is
        # invoked with.
        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")

        async def _noop_coro():
            return None

        mock_loop = mock.MagicMock(return_value=_noop_coro())
        # spawn_tracked normally create_task()s the coroutine; here just
        # close it so nothing runs and no "never awaited" warning leaks.
        mock_spawn = mock.Mock(side_effect=lambda coro: coro.close())
        with (
            mock.patch(
                "led_ticker_weather.forecast.fetch_forecast",
                mock.AsyncMock(side_effect=ValueError("boom")),
            ),
            mock.patch("led_ticker_weather.forecast.run_monitor_loop", mock_loop),
            mock.patch("led_ticker_weather.forecast.spawn_tracked", mock_spawn),
        ):
            w = await ForecastWidget.start(location="Boston")

        assert not w.should_display()
        mock_loop.assert_called_once_with(w, w.update_interval, immediate=True)
        mock_spawn.assert_called_once_with(mock_loop.return_value)

    async def test_start_does_not_poll_immediately_after_successful_eager_fetch(
        self, monkeypatch
    ):
        from plugins.weather.tests.test_forecast_data import _payload

        monkeypatch.setenv("WEATHERAPI_KEY", "test-key")

        async def _noop_coro():
            return None

        mock_loop = mock.MagicMock(return_value=_noop_coro())
        mock_spawn = mock.Mock(side_effect=lambda coro: coro.close())
        with (
            mock.patch(
                "led_ticker_weather.forecast.fetch_forecast",
                mock.AsyncMock(return_value=_payload()),
            ),
            mock.patch("led_ticker_weather.forecast.run_monitor_loop", mock_loop),
            mock.patch("led_ticker_weather.forecast.spawn_tracked", mock_spawn),
        ):
            w = await ForecastWidget.start(location="Boston")

        assert w.should_display()
        mock_loop.assert_called_once_with(w, w.update_interval, immediate=False)
        mock_spawn.assert_called_once_with(mock_loop.return_value)


class TestValidateConfig:
    def test_clean_config_passes(self):
        assert ForecastWidget.validate_config({"location": "Boston"}) == []

    def test_bad_layout_rejected(self):
        errs = ForecastWidget.validate_config({"location": "x", "layout": "dashboard"})
        assert any("layout" in e for e in errs)

    def test_bad_units_rejected(self):
        errs = ForecastWidget.validate_config({"location": "x", "units": "kelvin"})
        assert any("units" in e for e in errs)

    def test_location_required_unless_demo(self):
        assert any("location" in e for e in ForecastWidget.validate_config({}))
        assert ForecastWidget.validate_config({"demo": True}) == []

    def test_update_interval_bool_and_nonpositive_rejected(self):
        for bad in (True, 0, -5):
            errs = ForecastWidget.validate_config(
                {"location": "x", "update_interval": bad}
            )
            assert any("update_interval" in e for e in errs), bad

    def test_warnings_for_impossible_layouts(self):
        ctx = mock.Mock(scale=1, panel_width=160)
        warns = ForecastWidget.validate_config_warnings(
            {"location": "x", "layout": "big"}, ctx
        )
        assert any("strip" in w for w in warns)
        ctx = mock.Mock(scale=4, panel_width=256)
        warns = ForecastWidget.validate_config_warnings(
            {"location": "x", "layout": "long"}, ctx
        )
        assert any("big" in w for w in warns)
