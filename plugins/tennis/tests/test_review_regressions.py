from datetime import datetime, timedelta

import pytest
from led_ticker.plugin import HeadlessBackend

from led_ticker_tennis import _paint, _palette
from led_ticker_tennis._models import parse_match, status_label
from led_ticker_tennis._source import Snapshot, resolve_api_key
from led_ticker_tennis.layouts.scoreboard import _BIG, _LONG
from led_ticker_tennis.scores import TennisScoreMonitor

from .conftest import TZ, lit
from .test_models import LIVE_ROW
from .test_scores import _widget
from .test_source import Clock, FakeResp, FakeSession


def _ink_runs(text, size):
    canvas = HeadlessBackend(512, 64).create_canvas()
    shim, real = _paint.phys_wrap(canvas)
    _paint.hires(shim, text, 0, 8, _palette.LABEL_HI, size)
    columns = {x for x, _ in lit(real)}
    return sum(x - 1 not in columns for x in columns)


@pytest.mark.parametrize("geometry", [_BIG, _LONG])
def test_small_status_glyphs_stay_separate(geometry):
    assert _ink_runs("BP", geometry.badge_size) == 2
    for text in ("R16", "R32", "RET", "CINCINNATI OPEN"):
        size = _paint.fit_size(text, geometry.status_sizes, geometry.status_budget)
        fitted = _paint.fit_text(text, geometry.status_budget, size)
        assert _ink_runs(fitted, size) > 1, (text, size)


@pytest.mark.parametrize("timezone", ["Not/AZone", "", "/etc/passwd", None, 4])
def test_timezone_is_rejected_during_config_validation(timezone):
    errors = TennisScoreMonitor.validate_config({"timezone": timezone})
    assert errors and "timezone" in errors[0]


def test_environment_key_overrides_config(monkeypatch):
    monkeypatch.setenv("LIVETENNIS_API_KEY", "environment")
    assert resolve_api_key("old-config") == "environment"


def test_oversized_games_array_is_capped():
    match = parse_match({**LIVE_ROW, "score": {"games": [[6] * 40, [4] * 40]}})
    assert len(match.games) == 5


async def test_past_fixture_does_not_hide_future_fixture():
    now = datetime.now(TZ)
    rows = [
        {**LIVE_ROW, "id": i, "status": "upcoming", "scheduled_time": when.isoformat()}
        for i, when in [(1, now - timedelta(days=1)), (2, now + timedelta(days=1))]
    ]
    widget = _widget(Snapshot(upcoming=rows), max_matches=1)
    await widget.update()
    assert [card.match.match_id for card in widget.feed_stories] == [2]


async def test_cached_scores_identify_themselves_as_stale():
    widget = _widget(Snapshot(live=[LIVE_ROW], stale=True))
    await widget.update()
    assert status_label(widget.feed_stories[0].match) == "STALE"


async def test_finished_displayed_match_reaches_rotation():
    from led_ticker_tennis._source import LiveTennisSource
    from led_ticker_tennis.layouts.crawl import segments
    from led_ticker_tennis.layouts.scoreboard import _number_columns

    final = {
        **LIVE_ROW,
        "status": "completed",
        "outcome": "completed",
        "winner": 1,
        "score": {"sets": [2, 0], "games": [], "points": [None, None]},
    }
    session = FakeSession(
        FakeResp(body={"data": [LIVE_ROW]}), FakeResp(), FakeResp(body=final)
    )
    clock = Clock()
    widget = _widget()
    widget._source = LiveTennisSource(session, "test", clock=clock)
    await widget.update()
    clock.t += 900
    await widget.update()
    assert status_label(widget.feed_stories[0].match) == "STALE"
    clock.t += 900
    await widget.update()
    match = widget.feed_stories[0].match
    assert status_label(match) == "FINAL" and match.winner == 1
    assert match.sets == (2, 0) and match.games == []
    assert _number_columns(match, _LONG) == [("2", "0", "sets")]
    assert "2-0 sets" in [text for text, _ in segments(match, TZ)]
