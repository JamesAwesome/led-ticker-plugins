"""Tests for shared helpers in led_ticker_baseball.teams."""

import datetime as dt
import unittest.mock as mock


def _ctx(payload):
    resp = mock.AsyncMock()
    resp.json.return_value = payload
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = resp
    return ctx


def make_session(routes):
    session = mock.MagicMock()

    def side_effect(url, *args, **kwargs):
        for key, payload in routes.items():
            if key in url:
                return _ctx(payload)
        return _ctx({})

    session.get.side_effect = side_effect
    return session


TODAY = dt.date(2026, 6, 15)


class TestNextGameDate:
    async def test_returns_first_valid_date(self):
        from led_ticker_baseball.teams import next_game_date

        session = make_session(
            {"/schedule": {"dates": [{"date": "2026-06-20"}, {"date": "2026-06-21"}]}}
        )
        assert await next_game_date(session, TODAY) == dt.date(2026, 6, 20)

    async def test_team_scoped_url_has_teamid(self):
        captured = {}

        def side_effect(url, *args, **kwargs):
            captured["url"] = url
            return _ctx({"dates": [{"date": "2026-06-20"}]})

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        from led_ticker_baseball.teams import next_game_date

        await next_game_date(session, TODAY, team_id=143)
        assert "teamId=143" in captured["url"]
        assert "gameType=R" in captured["url"]

    async def test_league_url_has_no_teamid(self):
        captured = {}

        def side_effect(url, *args, **kwargs):
            captured["url"] = url
            return _ctx({"dates": []})

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        from led_ticker_baseball.teams import next_game_date

        await next_game_date(session, TODAY)
        assert "teamId" not in captured["url"]

    async def test_skips_malformed_date(self):
        from led_ticker_baseball.teams import next_game_date

        session = make_session(
            {
                "/schedule": {
                    "dates": [
                        {"date": ""},
                        {"date": "nope"},
                        {"date": "2026-06-22"},
                    ]
                }
            }
        )
        assert await next_game_date(session, TODAY) == dt.date(2026, 6, 22)

    async def test_empty_returns_none(self):
        from led_ticker_baseball.teams import next_game_date

        session = make_session({"/schedule": {"dates": []}})
        assert await next_game_date(session, TODAY) is None

    async def test_failure_returns_none(self):
        from led_ticker_baseball.teams import next_game_date

        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        assert await next_game_date(session, TODAY) is None
