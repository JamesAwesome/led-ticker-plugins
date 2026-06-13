"""Tests for the MLB league-wide Statcast superlatives widget."""

import datetime as dt
import logging
import unittest.mock as mock
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def row(**kwargs):
    """A Savant-shaped row dict; only the columns the code reads."""
    base = {
        "events": "",
        "description": "",
        "release_speed": "",
        "launch_speed": "",
        "hit_distance_sc": "",
        "pitch_name": "",
        "batter": "1",
        "pitcher": "2",
        "home_team": "PHI",
        "away_team": "TOR",
        "inning_topbot": "Top",
    }
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def hr(dist, batter=10, **kwargs):
    return row(
        events="home_run",
        description="hit_into_play",
        hit_distance_sc=dist,
        launch_speed=100.0,
        release_speed=95.0,
        batter=batter,
        **kwargs,
    )


class TestRowHelpers:
    def test_to_float_parses(self):
        from led_ticker_baseball.statcast import _to_float

        assert _to_float({"x": "101.8"}, "x") == 101.8
        assert _to_float({"x": "0"}, "x") == 0.0

    def test_to_float_blank_and_garbage_are_none(self):
        from led_ticker_baseball.statcast import _to_float

        assert _to_float({"x": ""}, "x") is None
        assert _to_float({"x": "null"}, "x") is None
        assert _to_float({}, "x") is None

    def test_to_id(self):
        from led_ticker_baseball.statcast import _to_id

        assert _to_id({"batter": "660271"}, "batter") == 660271
        assert _to_id({"batter": ""}, "batter") == 0
        assert _to_id({"batter": "abc"}, "batter") == 0
        assert _to_id({}, "batter") == 0

    def test_row_team_batter_top_is_away(self):
        from led_ticker_baseball.statcast import _row_team

        r = row(inning_topbot="Top")
        assert _row_team(r, "batter") == "TOR"
        assert _row_team(r, "pitcher") == "PHI"

    def test_row_team_batter_bottom_is_home(self):
        from led_ticker_baseball.statcast import _row_team

        r = row(inning_topbot="Bot")
        assert _row_team(r, "batter") == "PHI"
        assert _row_team(r, "pitcher") == "TOR"

    def test_row_team_normalizes_savant_abbrs(self):
        from led_ticker_baseball.statcast import _row_team

        # Savant uses ATH/AZ; the rest of the plugin speaks OAK/ARI.
        r = row(inning_topbot="Top", away_team="ATH", home_team="AZ")
        assert _row_team(r, "batter") == "OAK"
        assert _row_team(r, "pitcher") == "ARI"

    def test_format_value(self):
        from led_ticker_baseball.statcast import _format_value

        assert _format_value("longest_hr", 463.0) == "463 ft"
        assert _format_value("fastest_pitch", 101.84) == "101.8 mph"
        assert _format_value("hardest_hit", 113.4) == "113.4 mph"


class TestDeriveRecords:
    def _derive(self, rows, stats=None):
        from led_ticker_baseball.statcast import _STAT_KEYS, _derive_records

        return _derive_records(rows, list(stats or _STAT_KEYS))

    def test_longest_hr_takes_max_distance(self):
        records = self._derive([hr(415, batter=10), hr(463, batter=11)])
        rec = records["longest_hr"]
        assert rec.value == 463.0
        assert rec.person_id == 11

    def test_hardest_hit_only_counts_balls_in_play(self):
        rows = [
            row(description="hit_into_play", launch_speed=113.4, batter=20),
            row(description="foul", launch_speed=119.9, batter=21),
        ]
        assert self._derive(rows)["hardest_hit"].person_id == 20

    def test_pitch_records_use_pitcher_attribution(self):
        rows = [
            row(release_speed=101.8, pitcher=30, inning_topbot="Top"),
            row(release_speed=69.6, pitcher=31, pitch_name="Slow Curve"),
        ]
        records = self._derive(rows)
        fast, slow = records["fastest_pitch"], records["slowest_pitch"]
        assert (fast.person_id, fast.team_abbr) == (30, "PHI")
        assert slow.value == 69.6
        assert slow.pitch_name == "Slow Curve"

    def test_pitch_name_is_stripped(self):
        records = self._derive(
            [row(release_speed=69.6, pitcher=31, pitch_name=" Slow Curve ")]
        )
        assert records["slowest_pitch"].pitch_name == "Slow Curve"

    def test_tie_keeps_first_row(self):
        records = self._derive([hr(440, batter=10), hr(440, batter=11)])
        assert records["longest_hr"].person_id == 10

    def test_slowest_pitch_tie_keeps_first_row(self):
        # The lower=True comparison path must also keep the first row on ties.
        records = self._derive(
            [
                row(release_speed=69.6, pitcher=40),
                row(release_speed=69.6, pitcher=41),
            ],
            stats=["slowest_pitch"],
        )
        assert records["slowest_pitch"].person_id == 40

    def test_missing_values_skipped(self):
        records = self._derive([row(events="home_run", hit_distance_sc="")])
        assert "longest_hr" not in records

    def test_unrequested_stats_not_derived(self):
        records = self._derive([hr(440)], stats=["fastest_pitch"])
        assert set(records) == {"fastest_pitch"}

    def test_empty_rows_empty_records(self):
        assert self._derive([]) == {}


def make_widget(**kwargs):
    from led_ticker_baseball.statcast import MLBStatcastMonitor

    widget = MLBStatcastMonitor(session=kwargs.pop("session", mock.Mock()), **kwargs)
    widget._tz = NY
    return widget


TODAY = dt.date(2026, 6, 12)


class TestSkeleton:
    def test_default_stats_all_four_in_order(self):
        from led_ticker_baseball.statcast import _STAT_KEYS

        assert make_widget().stats == list(_STAT_KEYS)

    def test_default_title(self):
        widget = make_widget()
        widget._set_title()
        assert widget.feed_title.text == "Statcast"

    def test_title_override(self):
        widget = make_widget(title="Robot Numbers")
        widget._set_title()
        assert widget.feed_title.text == "Robot Numbers"

    def test_font_color_override_selected_for_body(self):
        from led_ticker.plugin import make_color

        c = make_color(255, 0, 0)
        widget = make_widget(font_color=c)
        assert widget._body_color() is c
        assert widget._plain_body_color() is c

    def test_default_body_color_is_white(self):
        from led_ticker.colors import RGB_WHITE

        widget = make_widget()
        assert widget._body_color() is RGB_WHITE
        assert widget._plain_body_color() is RGB_WHITE


class TestShouldSkip:
    def test_no_prior_derive_never_skips(self):
        assert make_widget()._should_skip(TODAY, (0, 5)) is False

    def test_gate_fetch_failure_fails_open(self):
        widget = make_widget()
        widget._last_derive = (TODAY, 5)
        assert widget._should_skip(TODAY, None) is False

    def test_skips_when_nothing_changed(self):
        widget = make_widget()
        widget._last_derive = (TODAY, 5)
        assert widget._should_skip(TODAY, (0, 5)) is True

    def test_live_game_forces_derive(self):
        widget = make_widget()
        widget._last_derive = (TODAY, 5)
        assert widget._should_skip(TODAY, (1, 5)) is False

    def test_new_final_forces_derive(self):
        widget = make_widget()
        widget._last_derive = (TODAY, 5)
        assert widget._should_skip(TODAY, (0, 6)) is False

    def test_date_rollover_forces_derive(self):
        widget = make_widget()
        widget._last_derive = (TODAY - dt.timedelta(days=1), 15)
        assert widget._should_skip(TODAY, (0, 15)) is False


def rec(value, person_id=10, team="TOR", pitch_name=""):
    from led_ticker_baseball.statcast import StatRecord

    return StatRecord(
        value=value, person_id=person_id, team_abbr=team, pitch_name=pitch_name
    )


def line_text(story):
    """Full visible text of a segment story line."""
    return "".join(seg[0] for seg in story.segments)


class TestBuildStatStories:
    def test_line_format_and_order(self):
        widget = make_widget()
        records = {
            "longest_hr": rec(463, person_id=10),
            "fastest_pitch": rec(101.8, person_id=30, team="MIL"),
        }
        stories = widget._build_stat_stories(
            records, "Today", {10: "Butler", 30: "Misiorowski"}
        )
        assert line_text(stories[0]) == "Today · Longest HR 463 ft — Butler TOR"
        assert (
            line_text(stories[1]) == "Today · Fastest pitch 101.8 mph — Misiorowski MIL"
        )

    def test_stats_config_order_controls_display_order(self):
        widget = make_widget(stats=["fastest_pitch", "longest_hr"])
        records = {"longest_hr": rec(463), "fastest_pitch": rec(101.8)}
        stories = widget._build_stat_stories(records, "Today", {})
        assert "Fastest pitch" in line_text(stories[0])
        assert "Longest HR" in line_text(stories[1])

    def test_missing_stat_omits_line(self):
        widget = make_widget()
        stories = widget._build_stat_stories({"longest_hr": rec(463)}, "Today", {})
        assert len(stories) == 1

    def test_slowest_pitch_appends_pitch_name(self):
        widget = make_widget(stats=["slowest_pitch"])
        records = {
            "slowest_pitch": rec(69.6, person_id=31, team="KC", pitch_name="Slow Curve")
        }
        stories = widget._build_stat_stories(records, "Today", {31: "Pederson"})
        assert line_text(stories[0]) == (
            "Today · Slowest pitch 69.6 mph (Slow Curve) — Pederson KC"
        )

    def test_fastest_pitch_never_appends_pitch_name(self):
        widget = make_widget(stats=["fastest_pitch"])
        records = {"fastest_pitch": rec(101.8, pitch_name="4-Seam Fastball")}
        stories = widget._build_stat_stories(records, "Today", {})
        assert "4-Seam" not in line_text(stories[0])

    def test_unresolved_name_drops_name_keeps_team(self):
        widget = make_widget(stats=["longest_hr"])
        stories = widget._build_stat_stories({"longest_hr": rec(463)}, "6/12", {})
        assert line_text(stories[0]) == "6/12 · Longest HR 463 ft — TOR"

    def test_colors_day_grey_value_amber_team_branded(self):
        from led_ticker_baseball.teams import _team_color

        widget = make_widget(stats=["longest_hr", "fastest_pitch"])
        stories = widget._build_stat_stories(
            {
                "longest_hr": rec(463, team="TOR"),
                "fastest_pitch": rec(101.8, team="MIL"),
            },
            "Today",
            {10: "Butler"},
        )
        segs = stories[0].segments
        day_c, value_c, team_c = segs[0][1], segs[2][1], segs[-1][1]
        assert (day_c.red, day_c.green, day_c.blue) == (150, 150, 150)
        assert (value_c.red, value_c.green, value_c.blue) == (255, 200, 60)
        # Exact brand color, not merely "not white" — and per-team, so a wrong
        # attribution or hardcoded default would fail.
        tor = _team_color("TOR")
        assert (team_c.red, team_c.green, team_c.blue) == (tor.red, tor.green, tor.blue)
        mil_c = stories[1].segments[-1][1]
        mil = _team_color("MIL")
        assert (mil_c.red, mil_c.green, mil_c.blue) == (mil.red, mil.green, mil.blue)

    def test_plain_font_color_tints_body_not_callouts(self):
        from led_ticker.plugin import make_color

        c = make_color(0, 255, 0)
        widget = make_widget(stats=["longest_hr"], font_color=c)
        stories = widget._build_stat_stories(
            {"longest_hr": rec(463)}, "Today", {10: "Butler"}
        )
        segs = stories[0].segments
        assert segs[1][1] is c  # "Longest HR " label
        assert segs[3][1] is c  # " — Butler "
        assert (segs[2][1].red, segs[2][1].green, segs[2][1].blue) == (255, 200, 60)

    def test_stories_centered(self):
        widget = make_widget(stats=["longest_hr"])
        stories = widget._build_stat_stories({"longest_hr": rec(463)}, "Today", {})
        assert stories[0].center is True


def _ctx(payload):
    """Async-context response mock: str payloads serve .text(), dicts .json()."""
    resp = mock.AsyncMock()
    # raise_for_status() is synchronous on real aiohttp responses; a plain
    # Mock keeps it a no-op (no un-awaited coroutine) for success fixtures.
    resp.raise_for_status = mock.Mock()
    if isinstance(payload, str):
        resp.text.return_value = payload
    else:
        resp.json.return_value = payload
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = resp
    return ctx


def make_session(routes):
    """Mock aiohttp session routing by URL substring; first match wins."""
    session = mock.MagicMock()

    def side_effect(url, *args, **kwargs):
        for key, payload in routes.items():
            if key in url:
                return _ctx(payload)
        return _ctx({})

    session.get.side_effect = side_effect
    return session


_CSV_COLS = [
    "release_speed",
    "batter",
    "pitcher",
    "events",
    "description",
    "home_team",
    "away_team",
    "inning_topbot",
    "launch_speed",
    "hit_distance_sc",
    "pitch_name",
]


def make_csv(*rows):
    """Savant-shaped CSV text, BOM included like the real endpoint."""
    lines = [",".join(_CSV_COLS)]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")) for c in _CSV_COLS))
    return "﻿" + "\n".join(lines) + "\n"


def sched_game(state):
    return {"status": {"abstractGameState": state}}


class TestFetchScheduleCounts:
    async def test_counts_live_and_final(self):
        session = make_session(
            {
                "sportId=1&date=": {
                    "dates": [
                        {
                            "games": [
                                sched_game("Live"),
                                sched_game("Final"),
                                sched_game("Final"),
                                sched_game("Preview"),
                            ]
                        }
                    ]
                }
            }
        )
        widget = make_widget(session=session)
        assert await widget._fetch_schedule_counts(TODAY) == (1, 2)

    async def test_failure_returns_none(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        assert await widget._fetch_schedule_counts(TODAY) is None


class TestDeriveDay:
    async def test_parses_bom_csv_and_derives(self):
        csv_text = make_csv(hr(463, batter=11), row(release_speed=101.8, pitcher=30))
        session = make_session({"statcast_search": csv_text})
        widget = make_widget(session=session)
        records = await widget._derive_day(TODAY)
        assert records["longest_hr"].value == 463.0
        assert records["fastest_pitch"].person_id == 30

    async def test_sends_user_agent(self):
        session = make_session({"statcast_search": make_csv()})
        widget = make_widget(session=session)
        await widget._derive_day(TODAY)
        savant_calls = [
            c for c in session.get.call_args_list if "statcast_search" in c.args[0]
        ]
        ua = savant_calls[0].kwargs["headers"]["User-Agent"]
        assert ua.startswith("led-ticker-baseball")

    async def test_requests_the_given_day(self):
        session = make_session({"statcast_search": make_csv()})
        widget = make_widget(session=session)
        await widget._derive_day(dt.date(2026, 6, 11))
        url = session.get.call_args_list[0].args[0]
        assert "game_date_gt=2026-06-11" in url
        assert "game_date_lt=2026-06-11" in url


class TestResolveNames:
    async def test_resolves_last_names(self):
        session = make_session(
            {
                "/people": {
                    "people": [
                        {"id": 10, "lastName": "Butler"},
                        {"id": 30, "lastName": "Misiorowski"},
                    ]
                }
            }
        )
        widget = make_widget(session=session)
        assert await widget._resolve_names({10, 30}) == {
            10: "Butler",
            30: "Misiorowski",
        }

    async def test_empty_ids_no_request(self):
        session = make_session({})
        widget = make_widget(session=session)
        assert await widget._resolve_names({0}) == {}
        session.get.assert_not_called()

    async def test_failure_returns_empty(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        assert await widget._resolve_names({10}) == {}

    async def test_missing_lastname_and_id_handled(self):
        # A person with no lastName maps to ""; an entry with no id is skipped.
        session = make_session(
            {
                "/people": {
                    "people": [
                        {"id": 10, "lastName": "Butler"},
                        {"id": 11},  # no lastName → ""
                        {"lastName": "Ghost"},  # no id → excluded
                    ]
                }
            }
        )
        widget = make_widget(session=session)
        assert await widget._resolve_names({10, 11}) == {10: "Butler", 11: ""}


class TestFallbackStates:
    def test_error_state(self):
        widget = make_widget()
        widget._set_error_state()
        assert widget.feed_stories[0].text == "No Data"

    async def test_no_games_probe_finds_next_date(self):
        session = make_session(
            {"startDate": {"dates": [{"date": "2027-03-26"}, {"date": "2027-03-27"}]}}
        )
        widget = make_widget(session=session)
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "Next games: Mar 26"

    async def test_no_games_probe_skips_malformed_dates(self):
        # First entry has no usable date, second is unparseable, third is good.
        session = make_session(
            {
                "startDate": {
                    "dates": [
                        {"date": ""},
                        {"date": "not-a-date"},
                        {"date": "2027-03-28"},
                    ]
                }
            }
        )
        widget = make_widget(session=session)
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "Next games: Mar 28"

    async def test_no_games_probe_empty(self):
        session = make_session({"startDate": {"dates": []}})
        widget = make_widget(session=session)
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "No games soon"

    async def test_no_games_probe_failure_degrades(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = make_widget(session=session)
        await widget._set_no_games_state(TODAY)
        assert widget.feed_stories[0].text == "No games soon"


def _freeze_today():
    """(patcher, today) freezing statcast.datetime.now at the current time.

    The frozen mock wraps the real datetime so classmethods (fromisoformat)
    still work.
    """
    now = dt.datetime.now(NY)
    frozen = mock.Mock(wraps=dt.datetime)
    frozen.now.return_value = now
    patcher = mock.patch("led_ticker_baseball.statcast.datetime", frozen)
    return patcher, now.date()


PEOPLE = {"people": [{"id": 11, "lastName": "Butler"}]}
QUIET_SCHEDULE = {"dates": [{"games": [sched_game("Final")] * 3}]}


class TestValidateConfig:
    def _validate(self, cfg):
        from led_ticker_baseball.statcast import MLBStatcastMonitor

        return MLBStatcastMonitor.validate_config(cfg)

    def test_clean_config_passes(self):
        assert self._validate({"stats": ["longest_hr", "fastest_pitch"]}) == []

    def test_stats_omitted_passes(self):
        assert self._validate({}) == []

    def test_unknown_key_named(self):
        msgs = self._validate({"stats": ["longest_hr", "biggest_yeet"]})
        assert len(msgs) == 1
        assert "biggest_yeet" in msgs[0]
        assert "longest_hr" in msgs[0]  # valid keys listed

    def test_non_list_stats_rejected(self):
        msgs = self._validate({"stats": "longest_hr"})
        assert len(msgs) == 1
        assert "stats" in msgs[0]

    def test_messages_returned_not_raised(self):
        assert isinstance(self._validate({"stats": 42}), list)


class TestUpdate:
    def _widget(self, routes, **kwargs):
        widget = make_widget(session=make_session(routes), **kwargs)
        widget._tz = NY
        return widget

    async def test_today_records_build_stories(self):
        patcher, today = _freeze_today()
        widget = self._widget(
            {
                "sportId=1&date=": QUIET_SCHEDULE,
                f"game_date_gt={today.isoformat()}": make_csv(hr(463, batter=11)),
                "/people": PEOPLE,
            },
            stats=["longest_hr"],
        )
        with patcher:
            await widget.update()
        assert line_text(widget.feed_stories[0]) == (
            "Today · Longest HR 463 ft — Butler TOR"
        )
        assert widget.feed_title is not None
        assert widget._last_derive == (today, 3)

    async def test_empty_today_falls_back_to_yesterday(self):
        patcher, today = _freeze_today()
        yest = today - dt.timedelta(days=1)
        widget = self._widget(
            {
                "sportId=1&date=": QUIET_SCHEDULE,
                f"game_date_gt={today.isoformat()}": make_csv(),
                f"game_date_gt={yest.isoformat()}": make_csv(hr(463, batter=11)),
                "/people": PEOPLE,
            },
            stats=["longest_hr"],
        )
        with patcher:
            await widget.update()
        assert line_text(widget.feed_stories[0]).startswith(
            f"{yest.strftime('%-m/%-d')} · "
        )

    async def test_both_days_empty_routes_to_no_games(self):
        patcher, today = _freeze_today()
        widget = self._widget(
            {
                "sportId=1&date=": {"dates": []},
                "statcast_search": make_csv(),
                "startDate": {"dates": []},
            }
        )
        with patcher:
            await widget.update()
        assert widget.feed_stories[0].text == "No games soon"
        assert widget._last_derive is None

    async def test_gate_skip_keeps_stories_and_skips_savant(self):
        patcher, today = _freeze_today()
        widget = self._widget({"sportId=1&date=": QUIET_SCHEDULE})
        widget._last_derive = (today, 3)
        sentinel = ["sentinel"]
        widget.feed_stories = sentinel
        with patcher:
            await widget.update()
        assert widget.feed_stories is sentinel
        savant_calls = [
            c
            for c in widget.session.get.call_args_list
            if "statcast_search" in c.args[0]
        ]
        assert savant_calls == []

    async def test_fetch_error_sets_no_data_and_clears_snapshot(self):
        patcher, today = _freeze_today()

        def side_effect(url, *args, **kwargs):
            if "statcast_search" in url:
                raise RuntimeError("savant down")
            return _ctx(QUIET_SCHEDULE)

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        widget = make_widget(session=session)
        widget._tz = NY
        widget._last_derive = (today - dt.timedelta(days=1), 1)
        with patcher:
            await widget.update()
        assert widget.feed_stories[0].text == "No Data"
        assert widget._last_derive is None

    async def test_savant_http_error_sets_no_data_not_off_day(self):
        # A Savant rate-limit / outage returns an HTTP error with a non-CSV
        # body; raise_for_status() must route it to "No Data", not let it
        # parse to zero rows and masquerade as an off-day ("No games soon").
        patcher, today = _freeze_today()

        def side_effect(url, *args, **kwargs):
            if "statcast_search" in url:
                resp = mock.AsyncMock()
                resp.raise_for_status = mock.Mock(
                    side_effect=RuntimeError("429 Too Many Requests")
                )
                ctx = mock.AsyncMock()
                ctx.__aenter__.return_value = resp
                return ctx
            return _ctx(QUIET_SCHEDULE)

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        widget = make_widget(session=session)
        widget._tz = NY
        with patcher:
            await widget.update()
        assert widget.feed_stories[0].text == "No Data"
        assert widget._last_derive is None

    async def test_gate_failure_then_success_stores_minus_one_sentinel(self):
        # Gate fetch fails (counts=None) but a derive succeeds — _last_derive
        # records final=-1 so the next tick can never gate-skip (fail open).
        patcher, today = _freeze_today()

        def side_effect(url, *args, **kwargs):
            if "sportId=1&date=" in url:
                raise RuntimeError("schedule down")
            if "statcast_search" in url:
                return _ctx(make_csv(hr(463, batter=11)))
            return _ctx(PEOPLE)

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        widget = make_widget(session=session, stats=["longest_hr"])
        widget._tz = NY
        with patcher:
            await widget.update()
        assert widget._last_derive == (today, -1)
        assert line_text(widget.feed_stories[0]).startswith("Today · ")

    async def test_update_logs_info(self, caplog):
        patcher, today = _freeze_today()
        widget = self._widget(
            {
                "sportId=1&date=": QUIET_SCHEDULE,
                f"game_date_gt={today.isoformat()}": make_csv(hr(463, batter=11)),
                "/people": PEOPLE,
            },
            stats=["longest_hr"],
        )
        with (
            patcher,
            caplog.at_level(logging.INFO, logger="led_ticker_baseball.statcast"),
        ):
            await widget.update()
        matching = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "statcast" in r.message.lower()
        ]
        assert matching, f"expected INFO log; got {[r.message for r in caplog.records]}"


class TestBgColor:
    def test_field_exists(self):
        from led_ticker_baseball.statcast import MLBStatcastMonitor

        names = {a.name for a in MLBStatcastMonitor.__attrs_attrs__}
        assert "bg_color" in names

    def test_bg_color_propagates_to_title_and_stories(self):
        from rgbmatrix.graphics import Color

        bg = Color(11, 22, 33)
        widget = make_widget(bg_color=bg, stats=["longest_hr"])
        widget._set_title()
        assert widget.feed_title.bg_color is bg
        story = widget._build_stat_stories({"longest_hr": rec(463)}, "Today", {})[0]
        assert story.bg_color is bg
        widget._set_error_state()
        assert widget.feed_stories[0].bg_color is bg
