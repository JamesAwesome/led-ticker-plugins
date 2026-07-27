"""Tests for the MLB attendance widget (league superlatives + team mode)."""

import datetime as dt
import logging
import unittest.mock as mock
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
TODAY = dt.date(2026, 6, 13)


class TestParseAttendance:
    def test_parses_att_with_commas_and_period(self):
        from led_ticker_baseball.attendance import _parse_attendance

        box = {"info": [{"label": "Att", "value": "19,587."}]}
        assert _parse_attendance(box) == 19587

    def test_missing_att_returns_none(self):
        from led_ticker_baseball.attendance import _parse_attendance

        box = {"info": [{"label": "Weather", "value": "Cloudy."}]}
        assert _parse_attendance(box) is None

    def test_empty_box_returns_none(self):
        from led_ticker_baseball.attendance import _parse_attendance

        assert _parse_attendance({}) is None

    def test_unparseable_value_returns_none(self):
        from led_ticker_baseball.attendance import _parse_attendance

        box = {"info": [{"label": "Att", "value": "n/a"}]}
        assert _parse_attendance(box) is None


class TestFillPct:
    def test_rounds_to_int_percent(self):
        from led_ticker_baseball.attendance import _fill_pct

        assert _fill_pct(19587, 38753) == 51

    def test_capacity_zero_or_missing_returns_none(self):
        from led_ticker_baseball.attendance import _fill_pct

        assert _fill_pct(19587, 0) is None
        assert _fill_pct(19587, None) is None


class TestFormatWeather:
    def test_formats_temp_condition_wind(self):
        from led_ticker_baseball.attendance import _format_weather

        w = {"condition": "Clear", "temp": "72", "wind": "5 mph, In From CF"}
        assert _format_weather(w) == "72° Clear, wind 5 mph, In From CF"

    def test_empty_weather_returns_none(self):
        from led_ticker_baseball.attendance import _format_weather

        assert _format_weather({}) is None
        assert _format_weather(None) is None

    def test_partial_weather_omits_missing_pieces(self):
        from led_ticker_baseball.attendance import _format_weather

        # No wind → just temp + condition; no temp → condition only;
        # no condition → temp alone (not dropped).
        assert _format_weather({"condition": "Clear", "temp": "72"}) == "72° Clear"
        assert _format_weather({"condition": "Clear"}) == "Clear"
        assert _format_weather({"temp": "72"}) == "72°"
        assert _format_weather({"temp": "72", "wind": "5 mph"}) == "72°, wind 5 mph"

    def test_strips_none_wind_direction(self):
        from led_ticker_baseball.attendance import _format_weather

        # MLB encodes wind as "<speed>, <direction>"; a closed roof / dead
        # calm sends the literal "None" as the direction. Strip it so the
        # line doesn't read "wind 0 mph, None" (real 6/14 TOR feed).
        w = {"condition": "Roof Closed", "temp": "68", "wind": "0 mph, None"}
        assert _format_weather(w) == "68° Roof Closed, wind 0 mph"
        # A "None" direction at non-zero speed is stripped too.
        assert (
            _format_weather({"temp": "72", "wind": "5 mph, None"}) == "72°, wind 5 mph"
        )


def sched_game(
    pk, state, home="PIT", away="MIA", venue="PNC Park", capacity=38753, game_number=1
):
    """A schedule game shaped like hydrate=venue(fieldInfo),team."""
    return {
        "gamePk": pk,
        "gameNumber": game_number,
        "status": {"abstractGameState": state},
        "teams": {
            "home": {"team": {"abbreviation": home}},
            "away": {"team": {"abbreviation": away}},
        },
        "venue": {"name": venue, "fieldInfo": {"capacity": capacity}},
    }


def schedule(*games):
    return {"dates": [{"games": list(games)}]}


class TestParseScheduleGames:
    def _parse(self, data):
        from led_ticker_baseball.attendance import _parse_schedule_games

        return _parse_schedule_games(data)

    def test_parses_fields(self):
        games = self._parse(schedule(sched_game(1, "Final")))
        g = games[0]
        assert (g.game_pk, g.state, g.home_abbr, g.away_abbr) == (
            1,
            "Final",
            "PIT",
            "MIA",
        )
        assert (g.venue, g.capacity, g.game_number) == ("PNC Park", 38753, 1)

    def test_missing_capacity_is_zero(self):
        data = schedule(
            {
                "gamePk": 2,
                "gameNumber": 1,
                "status": {"abstractGameState": "Final"},
                "teams": {
                    "home": {"team": {"abbreviation": "ATH"}},
                    "away": {"team": {"abbreviation": "LAA"}},
                },
                "venue": {"name": "Sutter Health Park", "fieldInfo": {}},
            }
        )
        assert self._parse(data)[0].capacity == 0

    def test_empty_schedule(self):
        assert self._parse({"dates": []}) == []


def sched_gv(pk, venue, home, capacity, away="OPP", state="Final"):
    from led_ticker_baseball.attendance import GameVenue

    return GameVenue(
        game_pk=pk,
        state=state,
        game_number=1,
        home_abbr=home,
        away_abbr=away,
        venue=venue,
        capacity=capacity,
    )


class TestDeriveSuperlatives:
    def _derive(self, pairs, stats=None):
        from led_ticker_baseball.attendance import _STAT_KEYS, _derive_superlatives

        return _derive_superlatives(pairs, list(stats or _STAT_KEYS))

    def _pairs(self):
        # (GameVenue, attendance) for three final games of varying fill.
        return [
            (sched_gv(1, "Dodger Stadium", "LAD", 56000), 45123),  # 81%
            (sched_gv(2, "Wrigley Field", "CHC", 41649), 41600),  # ~100%
            (sched_gv(3, "PNC Park", "PIT", 38753), 8201),  # 21%
        ]

    def test_biggest_and_smallest_crowd(self):
        recs = self._derive(self._pairs())
        assert recs["biggest_crowd"].value == 45123
        assert recs["biggest_crowd"].venue == "Dodger Stadium"
        assert recs["smallest_crowd"].value == 8201
        assert recs["smallest_crowd"].venue == "PNC Park"

    def test_fullest_and_emptiest_pct(self):
        recs = self._derive(self._pairs())
        assert recs["fullest"].value == 100  # 41600/41649
        assert recs["fullest"].venue == "Wrigley Field"
        assert recs["emptiest"].value == 21  # 8201/38753
        assert recs["emptiest"].venue == "PNC Park"

    def test_pct_skips_zero_capacity_but_crowd_counts_it(self):
        pairs = [
            (sched_gv(1, "PNC Park", "PIT", 38753), 20000),
            (sched_gv(2, "Sutter Health", "ATH", 0), 9000),  # no capacity
        ]
        recs = self._derive(pairs)
        # Smallest crowd still considers the no-capacity game...
        assert recs["smallest_crowd"].value == 9000
        # ...but emptiest/fullest only consider games with capacity.
        assert recs["emptiest"].venue == "PNC Park"
        assert recs["fullest"].venue == "PNC Park"

    def test_record_carries_home_abbr(self):
        recs = self._derive(self._pairs())
        assert recs["biggest_crowd"].home_abbr == "LAD"

    def test_tie_keeps_first(self):
        pairs = [
            (sched_gv(1, "A Park", "PIT", 40000), 30000),
            (sched_gv(2, "B Park", "CHC", 40000), 30000),
        ]
        assert self._derive(pairs)["biggest_crowd"].venue == "A Park"

    def test_unrequested_stats_not_derived(self):
        recs = self._derive(self._pairs(), stats=["biggest_crowd"])
        assert set(recs) == {"biggest_crowd"}

    def test_empty_pairs(self):
        assert self._derive([]) == {}

    def test_computes_fill_frac(self):
        pairs = [(sched_gv(1, "Dodger Stadium", "LAD", 50000), 40000)]
        recs = self._derive(pairs, stats=["biggest_crowd", "fullest"])
        assert abs(recs["biggest_crowd"].fill_frac - 0.8) < 1e-6  # 40000/50000
        assert recs["biggest_crowd"].attendance == 40000
        assert recs["biggest_crowd"].capacity == 50000
        # fullest: value is the pct (80), fill_frac == pct/100
        assert recs["fullest"].value == 80
        assert abs(recs["fullest"].fill_frac - 0.8) < 1e-6

    def test_zero_capacity_fill_frac_is_zero(self):
        pairs = [(sched_gv(1, "Sutter Health", "ATH", 0), 30000)]
        recs = self._derive(pairs, stats=["biggest_crowd"])
        assert recs["biggest_crowd"].fill_frac == 0.0  # no capacity -> no bar fill


class TestAttendanceGame:
    def test_record_shape(self):
        from led_ticker_baseball.attendance import AttendanceGame

        g = AttendanceGame(
            paid=46537,
            capacity=56000,
            avg=39442,
            venue="Dodger Stadium",
            home_abbr="LAD",
        )
        assert g.paid == 46537 and g.avg == 39442 and g.home_abbr == "LAD"

    def test_temp_and_condition_default_empty(self):
        from led_ticker_baseball.attendance import AttendanceGame

        g = AttendanceGame(
            paid=46537,
            capacity=56000,
            avg=39442,
            venue="Dodger Stadium",
            home_abbr="LAD",
        )
        assert g.temp == "" and g.condition == ""


class TestBuildTeamCardWeather:
    """`_build_team_card` threads the fetched weather dict's temp/condition
    onto the `AttendanceGame` record it builds — the long-card layout reads
    these off the record to render its new weather line (task-5)."""

    async def test_weather_dict_threads_temp_and_condition(self):
        w = make_widget(team="TOR")
        w._team_id = 0  # season-avg fetch short-circuits without a team id
        card = await w._build_team_card(
            game_venue=sched_gv(99, "Rogers Centre", "TOR", 46000),
            att=41212,
            cap=46000,
            weather={"condition": "Clear", "temp": "72", "wind": "5 mph"},
            day_label="",
        )
        assert card.record.temp == "72°"
        assert card.record.condition == "Clear"

    async def test_missing_weather_yields_empty_strings(self):
        w = make_widget(team="TOR")
        w._team_id = 0
        card = await w._build_team_card(
            game_venue=sched_gv(99, "Rogers Centre", "TOR", 46000),
            att=41212,
            cap=46000,
            weather=None,
            day_label="",
        )
        assert card.record.temp == ""
        assert card.record.condition == ""

    async def test_empty_weather_dict_yields_empty_strings(self):
        w = make_widget(team="TOR")
        w._team_id = 0
        card = await w._build_team_card(
            game_venue=sched_gv(99, "Rogers Centre", "TOR", 46000),
            att=41212,
            cap=46000,
            weather={},
            day_label="",
        )
        assert card.record.temp == ""
        assert card.record.condition == ""

    async def test_weather_missing_temp_condition_only(self):
        """`condition` alone (no `temp`) -> temp `""`, condition passes through."""
        w = make_widget(team="TOR")
        w._team_id = 0
        card = await w._build_team_card(
            game_venue=sched_gv(99, "Rogers Centre", "TOR", 46000),
            att=41212,
            cap=46000,
            weather={"condition": "Cloudy"},
            day_label="",
        )
        assert card.record.temp == ""
        assert card.record.condition == "Cloudy"


def make_widget(**kwargs):
    from led_ticker_baseball.attendance import MLBAttendanceMonitor

    widget = MLBAttendanceMonitor(session=kwargs.pop("session", mock.Mock()), **kwargs)
    widget._tz = NY
    return widget


class TestSkeleton:
    def test_default_is_league_mode_all_stats(self):
        from led_ticker_baseball.attendance import _STAT_KEYS

        w = make_widget()
        assert w.team == ""
        assert w.stats == list(_STAT_KEYS)

    def test_team_mode_when_team_set(self):
        # The field converter upper-cases at construction so the abbr matches
        # the API regardless of build path.
        assert make_widget(team="tor").team == "TOR"

    def test_default_title(self):
        w = make_widget()
        w._set_title()
        assert w.feed_title.text == "Attendance"

    def test_title_override(self):
        w = make_widget(title="Turnstiles")
        w._set_title()
        assert w.feed_title.text == "Turnstiles"

    def test_font_color_selected_for_body(self):
        from led_ticker.plugin import make_color

        c = make_color(255, 0, 0)
        w = make_widget(font_color=c)
        assert w._body_color() is c
        assert w._plain_body_color() is c

    def test_default_body_color_is_white(self):
        from led_ticker.colors import RGB_WHITE

        w = make_widget()
        assert w._body_color() is RGB_WHITE
        assert w._plain_body_color() is RGB_WHITE


class TestShouldSkip:
    def test_no_prior_derive_never_skips(self):
        assert make_widget()._should_skip(TODAY, (0, 5)) is False

    def test_gate_failure_fails_open(self):
        w = make_widget()
        w._last_derive = (TODAY, 5)
        assert w._should_skip(TODAY, None) is False

    def test_skips_when_unchanged(self):
        w = make_widget()
        w._last_derive = (TODAY, 5)
        assert w._should_skip(TODAY, (0, 5)) is True

    def test_live_forces_derive(self):
        w = make_widget()
        w._last_derive = (TODAY, 5)
        assert w._should_skip(TODAY, (1, 5)) is False

    def test_new_final_forces_derive(self):
        w = make_widget()
        w._last_derive = (TODAY, 5)
        assert w._should_skip(TODAY, (0, 6)) is False

    def test_date_rollover_forces_derive(self):
        w = make_widget()
        w._last_derive = (TODAY - dt.timedelta(days=1), 5)
        assert w._should_skip(TODAY, (0, 5)) is False


def crowd_rec(value, venue="Dodger Stadium", home="LAD", is_pct=False):
    from led_ticker_baseball.attendance import CrowdRecord

    return CrowdRecord(value=value, venue=venue, home_abbr=home, is_pct=is_pct)


def line_text(story):
    return "".join(seg[0] for seg in story.segments)


class TestBuildLeagueStories:
    def test_crowd_line_format(self):
        w = make_widget(stats=["biggest_crowd"])
        recs = {"biggest_crowd": crowd_rec(45123)}
        stories = w._build_league_stories(recs, "Today")
        assert line_text(stories[0]) == "Today · Biggest crowd 45,123 — Dodger Stadium"

    def test_pct_line_format(self):
        w = make_widget(stats=["emptiest"])
        recs = {"emptiest": crowd_rec(51, venue="PNC Park", home="PIT", is_pct=True)}
        stories = w._build_league_stories(recs, "Today")
        assert line_text(stories[0]) == "Today · Emptiest 51% — PNC Park"

    def test_stats_order_controls_display(self):
        w = make_widget(stats=["emptiest", "biggest_crowd"])
        recs = {
            "biggest_crowd": crowd_rec(45123),
            "emptiest": crowd_rec(51, is_pct=True),
        }
        stories = w._build_league_stories(recs, "Today")
        assert "Emptiest" in line_text(stories[0])
        assert "Biggest crowd" in line_text(stories[1])

    def test_missing_stat_omits_line(self):
        w = make_widget()
        stories = w._build_league_stories({"biggest_crowd": crowd_rec(45123)}, "Today")
        assert len(stories) == 1

    def test_colors_day_grey_value_amber_venue_branded(self):
        w = make_widget(stats=["biggest_crowd"])
        stories = w._build_league_stories({"biggest_crowd": crowd_rec(45123)}, "Today")
        segs = stories[0].segments
        day_c, value_c, venue_c = segs[0][1], segs[2][1], segs[-1][1]
        assert (day_c.red, day_c.green, day_c.blue) == (150, 150, 150)
        assert (value_c.red, value_c.green, value_c.blue) == (255, 200, 60)
        from led_ticker_baseball.teams import _team_color

        lad = _team_color("LAD")
        assert (venue_c.red, venue_c.green, venue_c.blue) == (
            lad.red,
            lad.green,
            lad.blue,
        )

    def test_stories_centered(self):
        w = make_widget(stats=["biggest_crowd"])
        stories = w._build_league_stories({"biggest_crowd": crowd_rec(45123)}, "Today")
        assert stories[0].center is True


class TestBuildTeamLine:
    def _w(self):
        w = make_widget(team="TOR")
        return w

    def test_final_line_has_attendance_pct_and_weather(self):
        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre",
            attendance=41212,
            capacity=46000,
            weather={"condition": "Clear", "temp": "72", "wind": "5 mph, In From CF"},
            day_label="",
        )
        assert line_text(story) == (
            "TOR · Rogers Centre 41,212 (90%) · 72° Clear, wind 5 mph, In From CF"
        )

    def test_pregame_line_omits_attendance(self):
        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre",
            attendance=None,
            capacity=46000,
            weather={"condition": "Clear", "temp": "72"},
            day_label="",
        )
        assert line_text(story) == "TOR · Rogers Centre · 72° Clear"

    def test_capacity_missing_drops_pct(self):
        w = self._w()
        story = w._build_team_line(
            venue="Sutter Health Park",
            attendance=9000,
            capacity=0,
            weather=None,
            day_label="",
        )
        assert line_text(story) == "TOR · Sutter Health Park 9,000"

    def test_missing_weather_omitted(self):
        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre",
            attendance=None,
            capacity=46000,
            weather=None,
            day_label="",
        )
        assert line_text(story) == "TOR · Rogers Centre"

    def test_yesterday_prefixes_short_date(self):
        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre",
            attendance=41212,
            capacity=46000,
            weather=None,
            day_label="6/12",
        )
        assert line_text(story) == "6/12 · TOR · Rogers Centre 41,212 (90%)"

    def test_team_prefix_brand_color(self):
        from led_ticker_baseball.teams import _team_color

        w = self._w()
        story = w._build_team_line(
            venue="Rogers Centre",
            attendance=None,
            capacity=0,
            weather=None,
            day_label="",
        )
        prefix_c = story.segments[0][1]
        tor = _team_color("TOR")
        assert (prefix_c.red, prefix_c.green, prefix_c.blue) == (
            tor.red,
            tor.green,
            tor.blue,
        )


def _ctx(payload):
    resp = mock.AsyncMock()
    resp.raise_for_status = mock.Mock()
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


def boxscore(att):
    info = [{"label": "Att", "value": att}] if att is not None else []
    return {"info": info}


class TestFetchSchedule:
    async def test_returns_games_and_counts(self):
        session = make_session(
            {
                "hydrate=venue(fieldInfo),team": schedule(
                    sched_game(1, "Live"),
                    sched_game(2, "Final"),
                    sched_game(3, "Preview"),
                )
            }
        )
        w = make_widget(session=session)
        games, counts = await w._fetch_schedule(TODAY)
        assert counts == (1, 1)  # (live, final)
        assert len(games) == 3

    async def test_failure_returns_none(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("down")
        w = make_widget(session=session)
        assert await w._fetch_schedule(TODAY) == (None, None)


class TestFetchAttendance:
    async def test_parses_boxscore(self):
        session = make_session({"/boxscore": boxscore("19,587.")})
        w = make_widget(session=session)
        assert await w._fetch_attendance(823370) == 19587

    async def test_missing_returns_none(self):
        session = make_session({"/boxscore": boxscore(None)})
        w = make_widget(session=session)
        assert await w._fetch_attendance(823370) is None

    async def test_failure_returns_none(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("down")
        w = make_widget(session=session)
        assert await w._fetch_attendance(1) is None


class TestFetchSeasonAvg:
    async def test_no_team_id_returns_none_without_fetching(self):
        session = mock.MagicMock()
        w = make_widget(session=session)
        assert await w._fetch_season_avg() is None
        session.get.assert_not_called()

    async def test_returns_attendance_average_home(self):
        session = make_session(
            {"attendance?": {"records": [{"attendanceAverageHome": 39442}]}}
        )
        w = make_widget(team="LAD", session=session)
        w._team_id = 119
        assert await w._fetch_season_avg() == 39442

    async def test_missing_records_returns_none(self):
        session = make_session({"attendance?": {"records": []}})
        w = make_widget(team="LAD", session=session)
        w._team_id = 119
        assert await w._fetch_season_avg() is None

    async def test_non_int_average_returns_none(self):
        session = make_session(
            {"attendance?": {"records": [{"attendanceAverageHome": None}]}}
        )
        w = make_widget(team="LAD", session=session)
        w._team_id = 119
        assert await w._fetch_season_avg() is None

    async def test_fetch_failure_returns_none(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("down")
        w = make_widget(team="LAD", session=session)
        w._team_id = 119
        assert await w._fetch_season_avg() is None


class TestFetchGameData:
    async def test_returns_attendance_weather_venue_capacity(self):
        feed = {
            "gameData": {
                "gameInfo": {"attendance": 19587},
                "weather": {"condition": "Clear", "temp": "72", "wind": "5 mph"},
                "venue": {"name": "PNC Park", "fieldInfo": {"capacity": 38753}},
            }
        }
        session = make_session({"/feed/live": feed})
        w = make_widget(session=session)
        att, weather, venue, cap = await w._fetch_game_data(823370)
        assert att == 19587
        assert weather["condition"] == "Clear"
        assert venue == "PNC Park"
        assert cap == 38753

    async def test_pregame_attendance_none(self):
        feed = {
            "gameData": {
                "gameInfo": {},
                "weather": {"condition": "Clear", "temp": "72"},
                "venue": {"name": "PNC Park", "fieldInfo": {}},
            }
        }
        session = make_session({"/feed/live": feed})
        w = make_widget(session=session)
        att, weather, venue, cap = await w._fetch_game_data(823370)
        assert att is None
        assert cap == 0


class TestFallbackStates:
    def test_error_state(self):
        w = make_widget()
        w._set_error_state()
        assert w.feed_stories[0].text == "No Data"

    def test_attendance_error_state_stays_bdf(self):
        """The error state ("No Data") is a bare TickerMessage — it never
        went through the v1.8.0 hires-fallback MVP and isn't wrapped in
        MLBAttendanceCard/HiresLine, so it always renders BDF regardless of
        scale."""
        from led_ticker_baseball._hires_line import HiresLine

        w = make_widget()
        w._set_error_state()
        story = w.feed_stories[0]
        assert not isinstance(story, HiresLine)

    async def test_team_set_but_unresolved_says_next_games(self):
        # team configured but id failed to resolve (_team_id == 0): the label
        # and the (absent) teamId query must agree — league fallback, not a
        # mislabeled "Next game" over a league-wide date.
        captured = {}

        def side_effect(url, *args, **kwargs):
            captured["url"] = url
            return _ctx({"dates": [{"date": "2027-03-26"}]})

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        widget = make_widget(session=session, team="TOR")
        widget._team_id = 0  # resolve failed
        await widget._set_no_games_state(TODAY)
        # Wrapped in an MLBAttendanceCard now (hires fallback at scale>1) —
        # the plain text lives on its `.legacy` TickerMessage.
        assert widget.feed_stories[0].legacy.text == "Next games: Mar 26"
        assert "teamId" not in captured["url"]

    async def test_probe_finds_next_game_team_mode(self):
        # Team mode → "Next game: <date>".
        session = make_session({"startDate": {"dates": [{"date": "2027-03-26"}]}})
        w = make_widget(session=session, team="TOR")
        w._team_id = 141
        await w._set_no_games_state(TODAY)
        assert w.feed_stories[0].legacy.text == "Next game: Mar 26"

    async def test_probe_empty_says_no_games_soon(self):
        session = make_session({"startDate": {"dates": []}})
        w = make_widget(session=session, team="TOR")
        w._team_id = 141
        await w._set_no_games_state(TODAY)
        assert w.feed_stories[0].legacy.text == "No games soon"

    async def test_probe_league_mode_next_games(self):
        # League mode (no team) names the next slate: "Next games: <date>".
        session = make_session({"startDate": {"dates": [{"date": "2027-03-26"}]}})
        w = make_widget(session=session)
        await w._set_no_games_state(TODAY)
        assert w.feed_stories[0].legacy.text == "Next games: Mar 26"

    async def test_probe_failure_degrades(self):
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("down")
        w = make_widget(session=session, team="TOR")
        w._team_id = 141
        await w._set_no_games_state(TODAY)
        assert w.feed_stories[0].legacy.text == "No games soon"

    async def test_no_data_hide_off_day_empties_feed(self):
        session = make_session({"startDate": {"dates": [{"date": "2027-03-26"}]}})
        w = make_widget(session=session, team="TOR", no_data="hide")
        w._team_id = 141
        await w._set_no_games_state(TODAY)
        assert w.feed_stories == []

    async def test_no_data_show_off_day_renders_hires(self):
        import attrs
        from led_ticker.plugin import HeadlessBackend, ScaledCanvas

        from led_ticker_baseball._attendance_card import MLBAttendanceCard

        session = make_session({"startDate": {"dates": [{"date": "2027-03-26"}]}})
        w = make_widget(session=session, team="TOR", no_data="show")
        w._team_id = 141
        await w._set_no_games_state(TODAY)
        assert len(w.feed_stories) == 1
        card = w.feed_stories[0]
        assert isinstance(card, MLBAttendanceCard)
        assert card.fallback_segments  # sanity: the hires branch is reachable

        real = HeadlessBackend(512, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        card.draw(canvas, 0)
        lit_rows = {y for (_x, y), v in real._pixels.items() if v != (0, 0, 0)}
        assert lit_rows
        # Hires span, upper-bounded below the ~35px a block-scaled BDF line
        # would produce through the same wrapper.
        assert 12 <= max(lit_rows) - min(lit_rows) <= 30

        # Mutation-proof: the same card with fallback_segments=[] forwards
        # to the BDF `legacy` line instead (the actual regression this test
        # guards against — a scale>1 no-attendance branch that forwards to
        # `legacy` unconditionally). The renders must differ pixel-for-pixel.
        bdf_card = attrs.evolve(card, fallback_segments=[])
        real_bdf = HeadlessBackend(512, 64).create_canvas()
        canvas_bdf = ScaledCanvas(real_bdf, scale=4, content_height=16)
        bdf_card.draw(canvas_bdf, 0)
        assert real._pixels != real_bdf._pixels


def _freeze_today():
    now = dt.datetime.now(NY)
    frozen = mock.Mock(wraps=dt.datetime)
    frozen.now.return_value = now
    patcher = mock.patch("led_ticker_baseball.attendance.datetime", frozen)
    return patcher, now.date()


def feed(att=None, condition="Clear", temp="72", venue="Rogers Centre", cap=46000):
    gi = {"attendance": att} if att is not None else {}
    return {
        "gameData": {
            "gameInfo": gi,
            "weather": {"condition": condition, "temp": temp, "wind": "5 mph"},
            "venue": {"name": venue, "fieldInfo": {"capacity": cap}},
        }
    }


class TestUpdateLeague:
    def _widget(self, routes, **kwargs):
        w = make_widget(session=make_session(routes), **kwargs)
        w._tz = NY
        return w

    async def test_today_finals_build_superlatives(self):
        patcher, today = _freeze_today()
        sched = schedule(
            sched_game(11, "Final", home="LAD", venue="Dodger Stadium", capacity=56000),
            sched_game(22, "Final", home="PIT", venue="PNC Park", capacity=38753),
        )
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/11/boxscore": boxscore("45,123."),
            "/game/22/boxscore": boxscore("8,201."),
        }
        w = self._widget(routes, stats=["biggest_crowd", "smallest_crowd"])
        with patcher:
            await w.update()
        assert line_text(w.feed_stories[0].legacy) == (
            "Today · Biggest crowd 45,123 — Dodger Stadium"
        )
        assert line_text(w.feed_stories[1].legacy) == (
            "Today · Smallest crowd 8,201 — PNC Park"
        )
        assert w._last_derive == (today, 2)

    async def test_no_finals_today_falls_back_to_yesterday(self):
        patcher, today = _freeze_today()
        yest = today - dt.timedelta(days=1)
        empty = schedule(sched_game(1, "Preview"))
        ysched = schedule(
            sched_game(33, "Final", home="CHC", venue="Wrigley Field", capacity=41649)
        )
        # Route schedule by date param so today vs yesterday differ.
        routes = {
            f"date={today.isoformat()}": empty,
            f"date={yest.isoformat()}": ysched,
            "/game/33/boxscore": boxscore("41,600."),
        }
        w = self._widget(routes, stats=["biggest_crowd"])
        with patcher:
            await w.update()
        assert line_text(w.feed_stories[0].legacy).startswith(
            f"{yest.strftime('%-m/%-d')} · "
        )
        # Today has a (Preview) game whose attendance is still pending, so the
        # yesterday fallback must NOT durably snapshot — otherwise the gate
        # would mask today's attendance once it is announced. _last_derive must
        # stay None so the next tick re-derives.
        assert w._last_derive is None

    async def test_today_final_without_attendance_keeps_polling(self):
        # Today's game is Final but its boxscore has no crowd yet → show
        # yesterday but keep the gate open (no snapshot) so the late-arriving
        # attendance is picked up rather than masked all day.
        patcher, today = _freeze_today()
        yest = today - dt.timedelta(days=1)
        routes = {
            f"date={today.isoformat()}": schedule(
                sched_game(44, "Final", home="LAD", venue="Dodger Stadium")
            ),
            f"date={yest.isoformat()}": schedule(
                sched_game(33, "Final", home="CHC", venue="Wrigley Field")
            ),
            "/game/44/boxscore": boxscore(None),  # today: no Att yet
            "/game/33/boxscore": boxscore("41,600."),
        }
        w = self._widget(routes, stats=["biggest_crowd"])
        with patcher:
            await w.update()
        assert line_text(w.feed_stories[0].legacy).startswith(
            f"{yest.strftime('%-m/%-d')} · "
        )
        assert w._last_derive is None  # keep re-deriving until today reports

    async def test_today_finals_all_reported_snapshots(self):
        # When every today Final has reported a crowd, the result is stable and
        # the gate may snapshot.
        patcher, today = _freeze_today()
        routes = {
            "hydrate=venue(fieldInfo),team": schedule(
                sched_game(11, "Final", home="LAD", venue="Dodger Stadium")
            ),
            "/game/11/boxscore": boxscore("45,123."),
        }
        w = self._widget(routes, stats=["biggest_crowd"])
        with patcher:
            await w.update()
        assert line_text(w.feed_stories[0].legacy).startswith("Today · ")
        assert w._last_derive == (today, 1)

    async def test_error_sets_no_data(self):
        patcher, today = _freeze_today()

        def side_effect(url, *args, **kwargs):
            if "/boxscore" in url:
                raise RuntimeError("boxscore down")
            return _ctx(schedule(sched_game(11, "Final")))

        session = mock.MagicMock()
        session.get.side_effect = side_effect
        w = make_widget(session=session)
        w._tz = NY
        with patcher:
            await w.update()
        # A single boxscore failure is skipped (not fatal); with the only game's
        # attendance unavailable, there are no superlatives → yesterday probe.
        # Yesterday also empty here → no-games fallback.
        assert w.feed_stories  # something rendered, not a crash


class TestPickTeamGame:
    def _gv(self, pk, state, game_number, home="TOR", away="BOS"):
        from led_ticker_baseball.attendance import GameVenue

        return GameVenue(
            game_pk=pk,
            state=state,
            game_number=game_number,
            home_abbr=home,
            away_abbr=away,
            venue="Rogers Centre",
            capacity=46000,
        )

    def test_doubleheader_both_final_picks_game_two(self):
        w = make_widget(team="TOR")
        games = [self._gv(1, "Final", 1), self._gv(2, "Final", 2)]
        assert w._pick_team_game(games).game_pk == 2

    def test_doubleheader_live_wins_over_final(self):
        w = make_widget(team="TOR")
        games = [self._gv(1, "Final", 1), self._gv(2, "Live", 2)]
        assert w._pick_team_game(games).game_pk == 2

    def test_doubleheader_final_game1_beats_unplayed_game2(self):
        # Completed game 1 must not be masked by an unplayed (Preview) game 2.
        w = make_widget(team="TOR")
        games = [self._gv(1, "Final", 1), self._gv(2, "Preview", 2)]
        assert w._pick_team_game(games).game_pk == 1

    def test_picks_team_on_either_side(self):
        w = make_widget(team="TOR")
        # Tracked team is the away side of the only game.
        games = [self._gv(5, "Final", 1, home="BOS", away="TOR")]
        assert w._pick_team_game(games).game_pk == 5

    def test_no_team_game_returns_none(self):
        w = make_widget(team="TOR")
        games = [self._gv(9, "Final", 1, home="NYY", away="BOS")]
        assert w._pick_team_game(games) is None


class TestUpdateTeam:
    def _widget(self, routes, **kwargs):
        w = make_widget(session=make_session(routes), team="TOR", **kwargs)
        w._tz = NY
        w._team_id = 141
        return w

    async def test_team_final_line(self):
        patcher, today = _freeze_today()
        sched = schedule(
            sched_game(
                99,
                "Final",
                home="TOR",
                away="BOS",
                venue="Rogers Centre",
                capacity=46000,
            )
        )
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/99/feed/live": feed(att=41212),
        }
        w = self._widget(routes)
        with patcher:
            await w.update()
        assert line_text(w.feed_stories[0].legacy).startswith(
            "TOR · Rogers Centre 41,212"
        )

    async def test_team_no_game_today_then_probe(self):
        patcher, today = _freeze_today()
        yest = today - dt.timedelta(days=1)
        routes = {
            f"date={today.isoformat()}": schedule(
                sched_game(1, "Final", home="NYY", away="BOS")
            ),
            f"date={yest.isoformat()}": schedule(
                sched_game(2, "Final", home="NYY", away="BOS")
            ),
            "startDate": {"dates": [{"date": "2026-06-20"}]},
        }
        w = self._widget(routes)
        with patcher:
            await w.update()
        assert w.feed_stories[0].legacy.text == "Next game: Jun 20"
        # The team has no game today, so the probe result is stable for the
        # day → snapshot and gate-skip until the date rolls (or the slate
        # changes). The today schedule had 1 Final game → count 1.
        assert w._last_derive == (today, 1)

    async def test_no_data_hide_not_final_empties_feed(self):
        # A Live (not yet Final) game has no attendance yet — no_data="hide"
        # drops the widget from the rotation instead of showing the fallback.
        patcher, today = _freeze_today()
        sched = schedule(
            sched_game(
                99,
                "Live",
                home="TOR",
                away="BOS",
                venue="Rogers Centre",
                capacity=46000,
            )
        )
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/99/feed/live": feed(att=None),
        }
        w = self._widget(routes, no_data="hide")
        with patcher:
            await w.update()
        assert w.feed_stories == []

    async def test_no_data_show_not_final_renders_hires(self):
        # Default no_data="show": the not-yet-Final game still yields one
        # MLBAttendanceCard, whose no-attendance fallback renders hires at
        # scale>1 (not the block-scaled BDF legacy line).
        import attrs
        from led_ticker.plugin import HeadlessBackend, ScaledCanvas

        patcher, today = _freeze_today()
        sched = schedule(
            sched_game(
                99,
                "Live",
                home="TOR",
                away="BOS",
                venue="Rogers Centre",
                capacity=46000,
            )
        )
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/99/feed/live": feed(att=None),
        }
        w = self._widget(routes, no_data="show")
        with patcher:
            await w.update()
        assert len(w.feed_stories) == 1
        card = w.feed_stories[0]
        assert card.fallback_segments  # sanity: the hires branch is reachable

        real = HeadlessBackend(512, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        card.draw(canvas, 0)
        lit_rows = {y for (_x, y), v in real._pixels.items() if v != (0, 0, 0)}
        assert lit_rows
        # Hires span, upper-bounded below the ~35px a block-scaled BDF line
        # would produce through the same wrapper.
        assert 12 <= max(lit_rows) - min(lit_rows) <= 30

        # Mutation-proof: the same card with fallback_segments=[] forwards
        # to the BDF `legacy` line instead (the actual regression this test
        # guards against). The renders must differ pixel-for-pixel.
        bdf_card = attrs.evolve(card, fallback_segments=[])
        real_bdf = HeadlessBackend(512, 64).create_canvas()
        canvas_bdf = ScaledCanvas(real_bdf, scale=4, content_height=16)
        bdf_card.draw(canvas_bdf, 0)
        assert real._pixels != real_bdf._pixels

    async def test_team_fallback_includes_weather_hires(self):
        """The no-attendance fallback line restores the weather segment the
        v1.8.0 `_draw_fallback_line` MVP dropped: a game not yet Final, with
        weather present, renders a temp/wind token ("°"/"mph") in its hires
        fallback segments — not just team/venue. Guards both the content
        (weather text present in the segments) and the render (hi-res span,
        differs pixel-for-pixel from its own `legacy` BDF line at scale=4)."""
        from led_ticker.plugin import HeadlessBackend, ScaledCanvas

        patcher, today = _freeze_today()
        sched = schedule(
            sched_game(
                99,
                "Live",
                home="TOR",
                away="BOS",
                venue="Rogers Centre",
                capacity=46000,
            )
        )
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/99/feed/live": feed(att=None, condition="Clear", temp="72"),
        }
        w = self._widget(routes, no_data="show")
        with patcher:
            await w.update()
        assert len(w.feed_stories) == 1
        card = w.feed_stories[0]
        segment_text = "".join(text for text, _color in card.fallback_segments)
        assert "°" in segment_text or "mph" in segment_text

        real = HeadlessBackend(512, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        card.draw(canvas, 0)
        lit_rows = {y for (_x, y), v in real._pixels.items() if v != (0, 0, 0)}
        assert lit_rows
        assert 12 <= max(lit_rows) - min(lit_rows) <= 30

        real_legacy = HeadlessBackend(512, 64).create_canvas()
        canvas_legacy = ScaledCanvas(real_legacy, scale=4, content_height=16)
        card.legacy.draw(canvas_legacy, 0)
        assert real._pixels != real_legacy._pixels

    async def test_update_logs_info(self, caplog):
        patcher, today = _freeze_today()
        sched = schedule(sched_game(99, "Final", home="TOR", venue="Rogers Centre"))
        routes = {
            "hydrate=venue(fieldInfo),team": sched,
            "/game/99/feed/live": feed(att=41212),
        }
        w = self._widget(routes)
        with (
            patcher,
            caplog.at_level(logging.INFO, logger="led_ticker_baseball.attendance"),
        ):
            await w.update()
        assert any(
            r.levelno == logging.INFO and "attendance" in r.message.lower()
            for r in caplog.records
        )


class TestStart:
    async def test_league_mode_spawns_loop(self):
        import led_ticker_baseball.attendance as mod
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        session = make_session({"hydrate=venue(fieldInfo),team": schedule()})
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            w = await MLBAttendanceMonitor.start(session, update_interval=55)
        assert isinstance(w, MLBAttendanceMonitor)
        assert w._tz is not None
        assert w._team_id == 0  # league mode: no resolution
        assert w.feed_stories
        loop.assert_called_once_with(w, 55)
        spawn.assert_called_once_with("LOOP")

    async def test_team_mode_resolves_id(self):
        import led_ticker_baseball.attendance as mod
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        routes = {
            "/teams": {"teams": [{"id": 141, "abbreviation": "TOR"}]},
            "hydrate=venue(fieldInfo),team": schedule(),
            "startDate": {"dates": []},
        }
        session = make_session(routes)
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            w = await MLBAttendanceMonitor.start(
                session, team="tor", update_interval=55
            )
        assert w.team == "TOR"
        assert w._team_id == 141
        spawn.assert_called_once_with("LOOP")


class TestBuildLeagueCards:
    def test_league_feed_stories_are_cards(self):
        from led_ticker_baseball._attendance_card import MLBAttendanceCard
        from led_ticker_baseball.attendance import CrowdRecord

        mon = make_widget(stats=["biggest_crowd", "fullest"])
        records = {
            "biggest_crowd": CrowdRecord(
                value=45123,
                venue="Dodger Stadium",
                home_abbr="LAD",
                is_pct=False,
                fill_frac=0.9,
                attendance=45123,
                capacity=50000,
            ),
            "fullest": CrowdRecord(
                value=99,
                venue="Fenway Park",
                home_abbr="BOS",
                is_pct=True,
                fill_frac=0.99,
                attendance=37000,
                capacity=37500,
            ),
        }
        cards = mon._build_league_cards(records, "Today")
        assert all(isinstance(c, MLBAttendanceCard) for c in cards)
        assert cards[0].label == "BIGGEST CROWD"
        assert cards[0].story_total == 2


class TestValidateConfig:
    def _v(self, cfg):
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        return MLBAttendanceMonitor.validate_config(cfg)

    def test_empty_passes(self):
        assert self._v({}) == []

    def test_rejects_bad_layout(self):
        msgs = self._v({"layout": "sideways"})
        assert any("layout" in m for m in msgs)

    def test_team_only_passes(self):
        assert self._v({"team": "TOR"}) == []

    def test_league_stats_pass(self):
        assert self._v({"stats": ["fullest", "emptiest"]}) == []

    def test_non_string_team_rejected(self):
        msgs = self._v({"team": 42})
        assert len(msgs) == 1
        assert "team" in msgs[0]

    def test_unknown_stat_named(self):
        msgs = self._v({"stats": ["fullest", "rowdiest"]})
        assert len(msgs) == 1
        assert "rowdiest" in msgs[0]
        assert "fullest" in msgs[0]  # valid keys listed

    def test_non_list_stats_rejected(self):
        msgs = self._v({"stats": "fullest"})
        assert len(msgs) == 1
        assert "stats" in msgs[0]

    def test_stats_with_team_is_not_rejected(self):
        # validate_config messages become a fatal pre-flight ValueError, so a
        # valid stats list alongside team must NOT be flagged — team mode just
        # ignores stats at runtime.
        assert self._v({"team": "TOR", "stats": ["fullest"]}) == []

    def test_bad_stats_still_rejected_even_with_team(self):
        # An actually-invalid stats value is still caught regardless of mode.
        msgs = self._v({"team": "TOR", "stats": ["rowdiest"]})
        assert len(msgs) == 1
        assert "rowdiest" in msgs[0]

    def test_rejects_bad_no_data(self):
        msgs = self._v({"no_data": "bogus"})
        assert len(msgs) == 1
        assert "no_data" in msgs[0]

    def test_no_data_show_passes(self):
        assert self._v({"no_data": "show"}) == []

    def test_no_data_hide_passes(self):
        assert self._v({"no_data": "hide"}) == []

    def test_no_data_absent_passes(self):
        assert self._v({}) == []


class TestScheduleAbbrNormalization:
    def _parse(self, data):
        from led_ticker_baseball.attendance import _parse_schedule_games

        return _parse_schedule_games(data)

    def test_savant_api_abbrs_normalized_to_canonical(self):
        data = schedule(
            sched_game(1, "Final", home="ATH", away="AZ", venue="Sutter Health Park")
        )
        g = self._parse(data)[0]
        assert g.home_abbr == "OAK"
        assert g.away_abbr == "ARI"

    def test_other_abbrs_unchanged(self):
        g = self._parse(schedule(sched_game(2, "Final", home="TOR", away="NYY")))[0]
        assert (g.home_abbr, g.away_abbr) == ("TOR", "NYY")

    def test_team_mode_matches_canonical_for_athletics(self):
        # User configures canonical "OAK"; schedule says "ATH" → still matched.
        w = make_widget(team="OAK")
        games = self._parse(schedule(sched_game(3, "Final", home="ATH", away="SEA")))
        assert w._pick_team_game(games) is not None

    def test_athletics_venue_uses_brand_color_not_white(self):
        from led_ticker.colors import RGB_WHITE

        from led_ticker_baseball.teams import _team_color

        w = make_widget(stats=["biggest_crowd"])  # league mode
        gv = self._parse(
            schedule(sched_game(4, "Final", home="ATH", away="SEA", capacity=46000))
        )[0]
        # Build a league story for that game's crowd; venue colored by home abbr.
        from led_ticker_baseball.attendance import CrowdRecord

        rec = CrowdRecord(
            value=10000, venue=gv.venue, home_abbr=gv.home_abbr, is_pct=False
        )
        story = w._build_league_stories({"biggest_crowd": rec}, "Today")[0]
        venue_c = story.segments[-1][1]
        oak = _team_color("OAK")
        assert (venue_c.red, venue_c.green, venue_c.blue) == (
            oak.red,
            oak.green,
            oak.blue,
        )
        assert venue_c is not RGB_WHITE


class TestValidateConfigDemo:
    def _v(self, cfg):
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        return MLBAttendanceMonitor.validate_config(cfg)

    def test_demo_true_passes(self):
        assert self._v({"demo": True}) == []

    def test_demo_false_passes(self):
        assert self._v({"demo": False}) == []

    def test_validate_demo_must_be_bool(self):
        msgs = self._v({"demo": "yes"})
        assert len(msgs) == 1
        assert "demo" in msgs[0]
        assert "bool" in msgs[0]

    def test_demo_with_team_passes(self):
        # team is optional at any time — demo doesn't add a team requirement.
        assert self._v({"demo": True, "team": "TOR"}) == []


class TestBuildTeamCardFromAvg:
    """`_build_team_card` now delegates its card construction to
    `_build_team_card_from_avg` (split out for `_load_demo()`'s benefit —
    see that method's docstring). This locks down the split didn't change
    `_build_team_card`'s own observable behavior."""

    async def test_build_team_card_still_fetches_avg_and_builds_record(self):
        w = make_widget(team="TOR")
        w._team_id = 0  # season-avg fetch short-circuits without a team id
        card = await w._build_team_card(
            game_venue=sched_gv(99, "Rogers Centre", "TOR", 46000),
            att=41212,
            cap=46000,
            weather={"condition": "Clear", "temp": "72"},
            day_label="",
        )
        assert card.record.paid == 41212
        assert card.record.avg is None  # no team id → _fetch_season_avg() -> None
        assert card.record.temp == "72°"
        assert card.record.condition == "Clear"

    def test_build_team_card_from_avg_threads_supplied_avg(self):
        w = make_widget(team="TOR")
        card = w._build_team_card_from_avg(
            game_venue=sched_gv(99, "Rogers Centre", "TOR", 46000),
            att=41212,
            cap=46000,
            weather=None,
            day_label="",
            avg=12345,
        )
        assert card.record.avg == 12345
        assert card.record.paid == 41212


# --- demo = true (fixture data, no live fetch) ---


class TestAttendanceDemo:
    """`demo = true` builds feed_stories from a curated fixture team game
    PLUS league superlative cards, in one rotation — never fetching the
    MLB API (schedule/boxscore/live-feed/season-avg) or spawning the
    background poll loop."""

    async def test_demo_populates_feed_without_fetch(self):
        import led_ticker_baseball.attendance as mod
        from led_ticker_baseball._attendance_card import MLBAttendanceCard
        from led_ticker_baseball.attendance import (
            AttendanceGame,
            CrowdRecord,
            MLBAttendanceMonitor,
        )

        # A session whose .get() would raise if ever called — start() must
        # never touch it in demo mode.
        session = mock.Mock()
        session.get.side_effect = AssertionError(
            "demo mode must never call session.get()"
        )
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            widget = await MLBAttendanceMonitor.start(session, demo=True)

        assert isinstance(widget, MLBAttendanceMonitor)
        assert widget.feed_stories
        assert widget.feed_title is not None
        # Every story is a real MLBAttendanceCard — demo reuses the SAME
        # story builders, not a re-implemented rendering path.
        assert all(isinstance(s, MLBAttendanceCard) for s in widget.feed_stories)
        # Both shapes are present: a team game (AttendanceGame) AND league
        # superlatives (CrowdRecord).
        records = [s.record for s in widget.feed_stories]
        assert any(isinstance(r, AttendanceGame) for r in records)
        assert any(isinstance(r, CrowdRecord) for r in records)
        # The team fixture carries a full card's worth of data: paid,
        # capacity, season avg, venue, and weather.
        team_record = next(r for r in records if isinstance(r, AttendanceGame))
        assert team_record.paid is not None
        assert team_record.capacity > 0
        assert team_record.avg is not None
        assert team_record.venue
        assert team_record.temp
        assert team_record.condition
        # Never fetched, never spawned the background poll loop.
        session.get.assert_not_called()
        loop.assert_not_called()
        spawn.assert_not_called()

    async def test_demo_works_without_session_in_league_mode(self):
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        widget = await MLBAttendanceMonitor.start(session=None, demo=True)

        assert widget.feed_stories

    async def test_demo_works_without_session_in_team_mode(self):
        # Demo shows BOTH shapes regardless of the configured mode — a
        # `team=` config doesn't change which fetches would happen (none).
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        widget = await MLBAttendanceMonitor.start(session=None, team="TOR", demo=True)

        assert widget.feed_stories

    def test_demo_construct_directly(self):
        from led_ticker_baseball._attendance_card import MLBAttendanceCard
        from led_ticker_baseball.attendance import MLBAttendanceMonitor

        widget = MLBAttendanceMonitor(session=None, demo=True)
        widget._load_demo()

        assert widget.feed_stories
        assert any(isinstance(s, MLBAttendanceCard) for s in widget.feed_stories)

    def test_demo_respects_configured_stats_subset(self):
        # DEMO_CROWD_RECORDS only has biggest_crowd + fullest; a narrower
        # `stats` config restricts further, same "missing stat omitted"
        # behavior as live league data.
        from led_ticker_baseball.attendance import AttendanceGame, MLBAttendanceMonitor

        widget = MLBAttendanceMonitor(session=None, demo=True, stats=["fullest"])
        widget._load_demo()

        league_records = [
            s.record
            for s in widget.feed_stories
            if not isinstance(s.record, AttendanceGame)
        ]
        assert len(league_records) == 1
        assert league_records[0].is_pct is True
