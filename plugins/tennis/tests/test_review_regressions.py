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
    match = widget.feed_stories[0].match
    assert match.stale and status_label(match) == "SET 2"


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
    vanished = widget.feed_stories[0].match
    assert vanished.stale and status_label(vanished) == "SET 2"
    clock.t += 900
    await widget.update()
    match = widget.feed_stories[0].match
    assert status_label(match) == "FINAL" and match.winner == 1
    assert match.sets == (2, 0) and match.games == []
    assert _number_columns(match, _LONG) == [("2", "0", "sets")]
    assert "2-0 sets" in [text for text, _ in segments(match, TZ)]


async def test_missing_detail_leaves_other_live_matches_current():
    """Two displayed live matches; match 1 leaves the listing and its
    detail lookup 404s. Only match 1 is stale, and backoff is untouched."""
    from led_ticker_tennis._source import LiveTennisSource
    from led_ticker_tennis.layouts.crawl import segments

    one = {**LIVE_ROW, "id": 1}
    two = {**LIVE_ROW, "id": 2, "tour": "wta"}
    session = FakeSession(
        FakeResp(body={"data": [one, two]}),
        FakeResp(body={"data": [two]}),
        FakeResp(404),
    )
    clock = Clock()
    widget = _widget()
    source = LiveTennisSource(session, "test", clock=clock)
    widget._source = source
    await widget.update()
    for _ in range(2):
        clock.t += 900
        await widget.update()
    assert session.urls[-1].endswith("/matches/1")
    assert not source.snapshot.stale and source.snapshot.last_error is None
    assert source._backoff == 0 and source.seconds_until_allowed() == 900
    by_id = {card.match.match_id: card.match for card in widget.feed_stories}
    assert by_id[1].stale and status_label(by_id[1]) == "SET 2"
    assert not by_id[2].stale and status_label(by_id[2]) == "SET 2"
    assert "STALE" not in [text for text, _ in segments(by_id[2], TZ)]


async def test_missing_detail_does_not_reset_an_existing_backoff():
    from led_ticker_tennis._source import LiveTennisSource

    session = FakeSession(
        FakeResp(body={"data": [LIVE_ROW]}),
        FakeResp(),  # match leaves the listing -> queued for a lookup
        FakeResp(503),  # the lookup fails
        FakeResp(503),  # so does the next live poll
        FakeResp(404),  # the retried lookup: match not retrievable
    )
    clock = Clock()
    source = LiveTennisSource(session, "test", clock=clock)
    await source.poll()
    source.remember_displayed([LIVE_ROW["id"]])
    for _ in range(3):
        clock.t += source.seconds_until_allowed()
        await source.poll()
    before = source._backoff
    assert before == 3600 and source.snapshot.stale
    clock.t += source.seconds_until_allowed()
    snap = await source.poll()
    assert session.urls[-1].endswith(f"/matches/{LIVE_ROW['id']}")
    assert source._backoff == before and snap.stale
    assert snap.recent[0]["_stale"] is True


async def test_live_matches_rank_ahead_of_finished_results():
    final = {**LIVE_ROW, "id": 7, "status": "completed", "outcome": "completed"}
    live_itf = {**LIVE_ROW, "id": 8, "tour": "itf"}
    widget = _widget(Snapshot(live=[live_itf], recent=[final]), max_matches=1)
    await widget.update()
    assert [card.match.match_id for card in widget.feed_stories] == [8]
    widget = _widget(Snapshot(live=[live_itf], recent=[final]))
    await widget.update()
    assert [card.match.state for card in widget.feed_stories] == ["live", "final"]
