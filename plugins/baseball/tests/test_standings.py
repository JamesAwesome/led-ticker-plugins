"""Tests for MLB standings widget."""

import unittest.mock as mock
from zoneinfo import ZoneInfo

import pytest
from led_ticker.colors import RGB_WHITE
from led_ticker.widgets.message import SegmentMessage, TickerMessage

from led_ticker_baseball._standings_card import MLBStandingsBoard
from led_ticker_baseball.standings import (
    DIVISION_NAMES,
    MLBStandingsMonitor,
    TeamStanding,
    _build_standing_message,
    _group_by_division,
)

# --- TeamStanding ---


class TestTeamStanding:
    def test_leader(self):
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        assert s.rank == 1
        assert s.games_back == "-"

    def test_non_leader(self):
        s = TeamStanding(name="Mets", wins=35, losses=30, rank=12, games_back="10.0")
        assert s.rank == 12
        assert s.games_back == "10.0"


# --- _build_standing_message ---


class TestBuildStandingMessage:
    def test_basic_format(self):
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        msg = _build_standing_message(s)
        assert isinstance(msg, SegmentMessage)
        texts = [t for t, _ in msg.segments]
        assert texts[0] == "1. "
        assert texts[1] == "Yankees"
        assert texts[2] == " 45-20"
        assert texts[3] == " -"

    def test_rank_numbers_white(self):
        s = TeamStanding(name="Dodgers", wins=42, losses=23, rank=2, games_back="3.0")
        msg = _build_standing_message(s)
        colors = [c for _, c in msg.segments]
        assert colors[0] is RGB_WHITE  # rank
        assert colors[2] is RGB_WHITE  # record
        assert colors[3] is RGB_WHITE  # GB

    def test_team_color_applied(self):
        s = TeamStanding(name="Phillies", wins=40, losses=25, rank=3, games_back="5.0")
        msg = _build_standing_message(s)
        colors = [c for _, c in msg.segments]
        # Team name should use team color, not white
        assert colors[1] is not RGB_WHITE

    def test_gb_leader(self):
        s = TeamStanding(name="Yankees", wins=50, losses=15, rank=1, games_back="-")
        msg = _build_standing_message(s)
        texts = [t for t, _ in msg.segments]
        assert texts[3] == " -"

    def test_gb_behind(self):
        s = TeamStanding(name="Orioles", wins=41, losses=24, rank=3, games_back="9.5")
        msg = _build_standing_message(s)
        texts = [t for t, _ in msg.segments]
        assert texts[3] == " 9.5"

    def test_message_is_centered(self):
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        msg = _build_standing_message(s)
        assert msg.center is True

    def test_draw_returns_canvas_and_cursor(self, canvas):
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        msg = _build_standing_message(s)
        result_canvas, cursor_pos = msg.draw(canvas)
        assert result_canvas is canvas
        assert cursor_pos > 0


# --- MLBStandingsMonitor ---


class TestMLBStandingsMonitor:
    def test_default_top_n(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        assert widget.top_n == 3

    def test_custom_top_n(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
            top_n=5,
        )
        assert widget.top_n == 5

    def test_default_title(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        assert widget.title == "MLB Standings"

    def test_custom_title(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
            title="NL Standings",
        )
        assert widget.title == "NL Standings"


# --- Parsing ---


class TestStandingsParsing:
    def _make_api_response(self, team_records):
        """Build a mock MLB API standings response."""
        return {"records": [{"teamRecords": team_records}]}

    def _make_team_record(self, name, wins, losses, rank, gb="-"):
        return {
            "team": {"name": name},
            "wins": wins,
            "losses": losses,
            "sportRank": str(rank),
            "sportGamesBack": gb,
        }

    def test_parse_and_sort(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        data = self._make_api_response(
            [
                self._make_team_record("Orioles", 41, 24, 3, "4.0"),
                self._make_team_record("Yankees", 45, 20, 1, "-"),
                self._make_team_record("Dodgers", 42, 23, 2, "3.0"),
            ]
        )
        standings = widget._parse_standings(data)
        assert len(standings) == 3
        assert standings[0].name == "Yankees"
        assert standings[1].name == "Dodgers"
        assert standings[2].name == "Orioles"

    def test_top_n_and_tracked(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM", "PHI"],
            top_n=2,
        )
        data = self._make_api_response(
            [
                self._make_team_record("Yankees", 45, 20, 1, "-"),
                self._make_team_record("Dodgers", 42, 23, 2, "3.0"),
                self._make_team_record("Orioles", 41, 24, 3, "4.0"),
                self._make_team_record("Mets", 35, 30, 12, "10.0"),
                self._make_team_record("Phillies", 33, 32, 15, "12.0"),
            ]
        )
        standings = widget._parse_standings(data)

        from led_ticker_baseball.teams import MLB_NAME_TO_ABBR

        # Simulate update logic (title not in stories, only in feed_title)
        stories: list = []
        top_names = set()
        for s in standings[: widget.top_n]:
            top_names.add(s.name)
            stories.append(_build_standing_message(s))
        standings_by_abbr: dict = {}
        for s in standings:
            abbr = MLB_NAME_TO_ABBR.get(s.name, "")
            if abbr:
                standings_by_abbr[abbr] = s
        for team in widget.teams:
            s = standings_by_abbr.get(team)
            if s and s.name not in top_names:
                stories.append(_build_standing_message(s))

        # 2 top + 2 tracked = 4
        assert len(stories) == 4
        # Stories 0-1 are top 2
        texts_0 = [t for t, _ in stories[0].segments]
        assert texts_0[0] == "1. "
        texts_1 = [t for t, _ in stories[1].segments]
        assert texts_1[0] == "2. "
        # Stories 2-3 are tracked teams
        texts_2 = [t for t, _ in stories[2].segments]
        assert texts_2[1] == "Mets"
        texts_3 = [t for t, _ in stories[3].segments]
        assert texts_3[1] == "Phillies"

    def test_tracked_team_skipped_if_in_top_n(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYY"],
            top_n=3,
        )
        data = self._make_api_response(
            [
                self._make_team_record("Yankees", 45, 20, 1, "-"),
                self._make_team_record("Dodgers", 42, 23, 2, "3.0"),
                self._make_team_record("Orioles", 41, 24, 3, "4.0"),
                self._make_team_record("Mets", 35, 30, 12, "10.0"),
            ]
        )
        standings = widget._parse_standings(data)

        from led_ticker_baseball.teams import MLB_NAME_TO_ABBR

        stories: list = []
        top_names = set()
        for s in standings[: widget.top_n]:
            top_names.add(s.name)
            stories.append(_build_standing_message(s))
        standings_by_abbr: dict = {}
        for s in standings:
            abbr = MLB_NAME_TO_ABBR.get(s.name, "")
            if abbr:
                standings_by_abbr[abbr] = s
        for team in widget.teams:
            s = standings_by_abbr.get(team)
            if s and s.name not in top_names:
                stories.append(_build_standing_message(s))

        # 3 top, NYY skipped in tracked section = 3
        assert len(stories) == 3

    def test_empty_response(self):
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        data = {"records": []}
        standings = widget._parse_standings(data)
        assert standings == []

    def test_multiple_divisions(self):
        """API returns multiple division records; all should be flattened."""
        widget = MLBStandingsMonitor(
            session=mock.Mock(),
            teams=["NYM"],
        )
        data = {
            "records": [
                {
                    "teamRecords": [
                        self._make_team_record("Yankees", 45, 20, 1, "-"),
                    ]
                },
                {
                    "teamRecords": [
                        self._make_team_record("Dodgers", 42, 23, 2, "3.0"),
                    ]
                },
            ],
        }
        standings = widget._parse_standings(data)
        assert len(standings) == 2
        assert standings[0].name == "Yankees"
        assert standings[1].name == "Dodgers"


# --- Division-aware parsing ---


class TestDivisionAwareParsing:
    def _make_division_response(self, division_id, team_records):
        """Build a mock MLB API standings response for a single division."""
        return {
            "records": [
                {
                    "division": {"id": division_id},
                    "teamRecords": team_records,
                }
            ]
        }

    def _make_full_team_record(
        self,
        name,
        abbreviation,
        wins,
        losses,
        rank,
        *,
        gb="-",
        pct="",
        division_rank="99",
        division_gb="-",
        streak_code="",
        split_records=None,
    ):
        record: dict = {
            "team": {"name": name, "abbreviation": abbreviation},
            "wins": wins,
            "losses": losses,
            "sportRank": str(rank),
            "sportGamesBack": gb,
            "winningPercentage": pct,
            "divisionRank": division_rank,
            "divisionGamesBack": division_gb,
        }
        if streak_code:
            record["streak"] = {"streakCode": streak_code}
        if split_records is not None:
            record["records"] = {"splitRecords": split_records}
        return record

    def test_all_new_fields_populate(self):
        widget = MLBStandingsMonitor(session=mock.Mock(), teams=["NYM"])
        data = self._make_division_response(
            201,
            [
                self._make_full_team_record(
                    "Yankees",
                    "NYY",
                    45,
                    20,
                    1,
                    gb="-",
                    pct=".692",
                    division_rank="1",
                    division_gb="-",
                    streak_code="W3",
                    split_records=[
                        {"type": "lastTen", "wins": 7, "losses": 3},
                        {"type": "home", "wins": 20, "losses": 10},
                        {"type": "away", "wins": 25, "losses": 10},
                    ],
                ),
                self._make_full_team_record(
                    "Orioles",
                    "BAL",
                    40,
                    25,
                    5,
                    gb="5.0",
                    pct=".615",
                    division_rank="2",
                    division_gb="3.0",
                    streak_code="L2",
                    split_records=[
                        {"type": "lastTen", "wins": 4, "losses": 6},
                        {"type": "home", "wins": 18, "losses": 12},
                    ],
                ),
            ],
        )
        standings = widget._parse_standings(data)
        assert len(standings) == 2

        yanks = next(s for s in standings if s.name == "Yankees")
        assert yanks.abbr == "NYY"
        assert yanks.pct == ".692"
        assert yanks.l10 == "7-3"
        assert yanks.streak == "W3"
        assert yanks.division_rank == 1
        assert yanks.division_gb == "-"
        assert yanks.division_id == 201

        os = next(s for s in standings if s.name == "Orioles")
        assert os.abbr == "BAL"
        assert os.pct == ".615"
        assert os.l10 == "4-6"
        assert os.streak == "L2"
        assert os.division_rank == 2
        assert os.division_gb == "3.0"
        assert os.division_id == 201

    def test_abbr_normalizes_az_to_ari(self):
        widget = MLBStandingsMonitor(session=mock.Mock(), teams=["NYM"])
        data = self._make_division_response(
            203,
            [
                self._make_full_team_record(
                    "Diamondbacks",
                    "AZ",
                    40,
                    25,
                    5,
                    division_rank="1",
                ),
            ],
        )
        standings = widget._parse_standings(data)
        assert standings[0].abbr == "ARI"

    def test_missing_optional_fields_yield_defaults(self):
        widget = MLBStandingsMonitor(session=mock.Mock(), teams=["NYM"])
        data = {
            "records": [
                {
                    "teamRecords": [
                        {
                            "team": {"name": "Mets"},
                            "wins": 35,
                            "losses": 30,
                            "sportRank": "12",
                            "sportGamesBack": "10.0",
                        }
                    ]
                }
            ]
        }
        standings = widget._parse_standings(data)
        assert len(standings) == 1
        s = standings[0]
        assert s.abbr == ""
        assert s.pct == ""
        assert s.l10 == ""
        assert s.streak == ""
        assert s.division_rank == 99
        assert s.division_gb == "-"
        assert s.division_id == 0

    def test_legacy_fields_untouched(self):
        """Existing legacy fields keep working when constructed positionally."""
        s = TeamStanding(name="Yankees", wins=45, losses=20, rank=1, games_back="-")
        assert s.abbr == ""
        assert s.pct == ""
        assert s.l10 == ""
        assert s.streak == ""
        assert s.division_rank == 99
        assert s.division_gb == "-"
        assert s.division_id == 0


class TestGroupByDivision:
    def test_groups_and_sorts_by_division_rank(self):
        standings = [
            TeamStanding(
                name="Orioles",
                wins=41,
                losses=24,
                rank=3,
                games_back="4.0",
                division_id=201,
                division_rank=2,
            ),
            TeamStanding(
                name="Yankees",
                wins=45,
                losses=20,
                rank=1,
                games_back="-",
                division_id=201,
                division_rank=1,
            ),
            TeamStanding(
                name="Dodgers",
                wins=42,
                losses=23,
                rank=2,
                games_back="3.0",
                division_id=203,
                division_rank=1,
            ),
        ]
        groups = _group_by_division(standings)
        assert set(groups.keys()) == {201, 203}
        assert [s.name for s in groups[201]] == ["Yankees", "Orioles"]
        assert [s.name for s in groups[203]] == ["Dodgers"]

    def test_excludes_division_id_zero(self):
        standings = [
            TeamStanding(
                name="Yankees",
                wins=45,
                losses=20,
                rank=1,
                games_back="-",
                division_id=0,
                division_rank=1,
            ),
        ]
        groups = _group_by_division(standings)
        assert groups == {}

    def test_empty_input(self):
        assert _group_by_division([]) == {}


class TestDivisionNames:
    def test_all_six_divisions_present(self):
        assert DIVISION_NAMES == {
            200: "AL WEST",
            201: "AL EAST",
            202: "AL CENTRAL",
            203: "NL WEST",
            204: "NL EAST",
            205: "NL CENTRAL",
        }


# --- Offseason ---


class TestOffseason:
    def test_all_zeros_detected(self):
        """When all teams have 0-0 records, season hasn't started."""
        standings = [
            TeamStanding(name="Yankees", wins=0, losses=0, rank=1, games_back="-"),
            TeamStanding(name="Dodgers", wins=0, losses=0, rank=2, games_back="-"),
            TeamStanding(name="Mets", wins=0, losses=0, rank=3, games_back="-"),
        ]
        assert all(s.wins == 0 and s.losses == 0 for s in standings)

    def test_not_all_zeros_when_games_played(self):
        standings = [
            TeamStanding(name="Yankees", wins=1, losses=0, rank=1, games_back="-"),
            TeamStanding(name="Dodgers", wins=0, losses=1, rank=2, games_back="1.0"),
        ]
        assert not all(s.wins == 0 and s.losses == 0 for s in standings)

    def _make_session(self, *, all_zero: bool = True, schedule_dates=None):
        """Mock aiohttp session that routes by URL.

        - /standings -> records with all-zero records (offseason) or sample data
        - /teams -> abbr->id map for tracked teams
        - /schedule -> game dates (or empty for fallback path)
        """
        session = mock.MagicMock()

        def make_ctx(url, *args, **kwargs):
            resp = mock.AsyncMock()
            if "/standings" in url:
                if all_zero:
                    resp.json.return_value = {
                        "records": [
                            {
                                "teamRecords": [
                                    {
                                        "team": {"name": "New York Mets"},
                                        "wins": 0,
                                        "losses": 0,
                                        "sportRank": "1",
                                        "sportGamesBack": "-",
                                    },
                                    {
                                        "team": {"name": "New York Yankees"},
                                        "wins": 0,
                                        "losses": 0,
                                        "sportRank": "2",
                                        "sportGamesBack": "-",
                                    },
                                ]
                            }
                        ]
                    }
                else:
                    resp.json.return_value = {
                        "records": [
                            {
                                "teamRecords": [
                                    {
                                        "team": {"name": "New York Mets"},
                                        "wins": 5,
                                        "losses": 2,
                                        "sportRank": "1",
                                        "sportGamesBack": "-",
                                    }
                                ]
                            }
                        ]
                    }
            elif "/teams" in url:
                resp.json.return_value = {
                    "teams": [
                        {"id": 121, "abbreviation": "NYM"},
                        {"id": 147, "abbreviation": "NYY"},
                    ]
                }
            elif "/schedule" in url:
                if schedule_dates:
                    resp.json.return_value = {
                        "dates": [{"games": [{"gameDate": d} for d in schedule_dates]}]
                    }
                else:
                    resp.json.return_value = {"dates": []}
            else:
                resp.json.return_value = {}

            ctx = mock.AsyncMock()
            ctx.__aenter__.return_value = resp
            return ctx

        session.get.side_effect = make_ctx
        return session

    @pytest.mark.asyncio
    async def test_update_routes_to_offseason_when_all_zero(self):
        # Drive update() — assert behavior, not pre-set state.
        session = self._make_session(
            all_zero=True,
            schedule_dates=["2026-03-27T17:00:00Z"],
        )
        widget = MLBStandingsMonitor(session=session, teams=["NYM"])
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        await widget.update()

        assert len(widget.feed_stories) == 1
        # Offseason path produced an "Opens <date>" message
        assert widget.feed_stories[0].text.startswith("Opens ")
        # Title is set
        assert widget.feed_title is not None

    @pytest.mark.asyncio
    async def test_update_offseason_fallback_when_no_schedule(self):
        # All-zero standings + empty schedule → "Opens soon"
        session = self._make_session(all_zero=True, schedule_dates=None)
        widget = MLBStandingsMonitor(session=session, teams=["NYM"])
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        await widget.update()

        assert len(widget.feed_stories) == 1
        assert widget.feed_stories[0].text == "Opens soon"

    @pytest.mark.asyncio
    async def test_update_skips_offseason_when_games_played(self):
        # Some non-zero records → normal path, NOT offseason. This fixture
        # carries no division data, so it exercises layout="ticker"
        # explicitly rather than the new "auto" default (which builds
        # per-division boards and would legitimately yield zero stories
        # here — there's no division to group by).
        session = self._make_session(all_zero=False)
        widget = MLBStandingsMonitor(
            session=session, teams=["NYM"], top_n=1, layout="ticker"
        )
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        await widget.update()

        # Should have a real standings story, not "Opens ..."
        assert len(widget.feed_stories) >= 1
        first_msg = widget.feed_stories[0]
        # SegmentMessage doesn't have a single .message; just verify it's not
        # the offseason TickerMessage.
        if isinstance(first_msg, TickerMessage):
            assert not first_msg.text.startswith("Opens")

    @pytest.mark.asyncio
    async def test_update_handles_api_error_gracefully(self):
        # Network failure → _set_error_state() puts a "No Data" story.
        session = mock.MagicMock()
        session.get.side_effect = RuntimeError("network down")
        widget = MLBStandingsMonitor(session=session, teams=["NYM"])
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        # Should not propagate the exception
        await widget.update()

        assert len(widget.feed_stories) == 1
        assert widget.feed_stories[0].text == "No Data"

    @pytest.mark.asyncio
    async def test_offseason_fetches_teams_endpoint_once(self):
        # Regression: _fetch_opening_day previously refetched /teams once
        # per tracked team. With 5 tracked teams and ~50KB JSON each, that
        # was 5 round-trips at startup. Now should be exactly 1.
        session = self._make_session(
            all_zero=True,
            schedule_dates=["2026-03-27T17:00:00Z"],
        )
        widget = MLBStandingsMonitor(session=session, teams=["NYM", "NYY"])
        widget._tz = __import__("zoneinfo").ZoneInfo("America/New_York")

        await widget.update()

        # Count calls to /teams (vs /standings, /schedule)
        teams_calls = [c for c in session.get.call_args_list if "/teams" in c.args[0]]
        assert len(teams_calls) == 1, (
            f"Expected exactly one /teams round-trip; got {len(teams_calls)}. "
            "Per-team refetch regression."
        )


class TestMlbStandingsBgColor:
    def test_field_exists(self):
        names = {a.name for a in MLBStandingsMonitor.__attrs_attrs__}
        assert "bg_color" in names

    def test_accepts_bg_color(self):
        from led_ticker.plugin import make_color

        w = MLBStandingsMonitor(
            session=mock.Mock(), teams=[], bg_color=make_color(11, 22, 33)
        )
        assert w.bg_color.green == 22


class TestMLBStandingsUpdateLogging:
    """Periodic update() must log INFO so users can verify the background
    task is firing — silent success vs silent failure must be distinguishable.
    """

    async def test_standings_update_logs_info(self, caplog) -> None:
        import logging
        from unittest.mock import AsyncMock, MagicMock

        from led_ticker_baseball.standings import MLBStandingsMonitor

        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json = AsyncMock(return_value={"records": []})
        session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        widget = MLBStandingsMonitor(session=session, teams=["NYM"])
        from zoneinfo import ZoneInfo

        widget._tz = ZoneInfo("America/New_York")

        with caplog.at_level(logging.INFO, logger="led_ticker_baseball.standings"):
            await widget.update()

        matching = [
            r
            for r in caplog.records
            if r.levelno == logging.INFO and "standings" in r.message.lower()
        ]
        assert matching, f"expected INFO log; got {[r.message for r in caplog.records]}"


def _empty_json_session():
    """Session returning empty JSON for every URL (no standings records)."""
    session = mock.MagicMock()

    def make_ctx(url, *args, **kwargs):
        resp = mock.AsyncMock()
        resp.json.return_value = {}
        ctx = mock.AsyncMock()
        ctx.__aenter__.return_value = resp
        return ctx

    session.get.side_effect = make_ctx
    return session


class TestStart:
    async def test_resolves_state_runs_update_and_spawns_loop(self):
        import led_ticker_baseball.standings as mod

        # Empty /standings drives update() to its error state; we only assert
        # the wiring around it.
        spawn = mock.Mock()
        loop = mock.Mock(return_value="LOOP")
        with (
            mock.patch.object(mod, "spawn_tracked", spawn),
            mock.patch.object(mod, "run_monitor_loop", loop),
        ):
            widget = await MLBStandingsMonitor.start(
                _empty_json_session(), ["nym"], update_interval=88
            )

        assert isinstance(widget, MLBStandingsMonitor)
        assert widget.teams == ["NYM"]  # upper-cased
        assert widget._tz is not None
        assert widget.feed_stories  # update() ran
        loop.assert_called_once_with(widget, 88)
        spawn.assert_called_once_with("LOOP")


# --- layout field + validate_config ---


class TestStandingsLayoutField:
    def test_default_is_auto(self):
        widget = MLBStandingsMonitor(session=mock.Mock(), teams=["NYM"])
        assert widget.layout == "auto"

    def test_accepts_ticker_and_board(self):
        for layout in ("auto", "ticker", "board"):
            widget = MLBStandingsMonitor(
                session=mock.Mock(), teams=["NYM"], layout=layout
            )
            assert widget.layout == layout


class TestStandingsValidateConfig:
    """Mirrors MLBScoreMonitor.validate_config's layout-value guardrail
    pattern (see test_scores.py TestScoresValidateConfig)."""

    def test_valid_layouts_pass(self):
        for layout in ("auto", "ticker", "board"):
            assert MLBStandingsMonitor.validate_config({"layout": layout}) == []

    def test_default_layout_passes(self):
        assert MLBStandingsMonitor.validate_config({}) == []

    def test_invalid_layout_suggests_close_match(self):
        msgs = MLBStandingsMonitor.validate_config({"layout": "bord"})
        assert len(msgs) == 1
        assert "Did you mean 'board'?" in msgs[0]
        assert "'auto'" in msgs[0]
        assert "'ticker'" in msgs[0]
        assert "'board'" in msgs[0]

    def test_invalid_layout_no_close_match(self):
        msgs = MLBStandingsMonitor.validate_config({"layout": "zzzzz"})
        assert len(msgs) == 1
        assert "is not valid" in msgs[0]
        assert "Did you mean" not in msgs[0]

    def test_callable_as_classmethod(self):
        assert MLBStandingsMonitor.validate_config({"layout": "auto"}) == []


# --- update() layout="auto"/"board" wiring ---


def _division_team_record(
    name, abbreviation, wins, losses, rank, division_rank, division_gb="-"
):
    return {
        "team": {"name": name, "abbreviation": abbreviation},
        "wins": wins,
        "losses": losses,
        "sportRank": str(rank),
        "sportGamesBack": "-",
        "divisionRank": str(division_rank),
        "divisionGamesBack": division_gb,
    }


def _two_division_session():
    """API response spanning two divisions: AL EAST (201, 6 teams — to
    verify the top-5 cap) and NL WEST (203, 2 teams)."""
    al_east_teams = [
        ("Yankees", "NYY"),
        ("Red Sox", "BOS"),
        ("Orioles", "BAL"),
        ("Rays", "TB"),
        ("Blue Jays", "TOR"),
        ("Guardians", "CLE"),  # 6th team — must be excluded by the top-5 cap
    ]
    nl_west_teams = [
        ("Dodgers", "LAD"),
        ("Padres", "SD"),
    ]
    records = [
        {
            "division": {"id": 201},
            "teamRecords": [
                _division_team_record(name, abbr, 50 - i, 20 + i, i + 1, i + 1)
                for i, (name, abbr) in enumerate(al_east_teams)
            ],
        },
        {
            "division": {"id": 203},
            "teamRecords": [
                _division_team_record(name, abbr, 48 - i, 22 + i, i + 1, i + 1)
                for i, (name, abbr) in enumerate(nl_west_teams)
            ],
        },
    ]

    session = mock.MagicMock()

    def make_ctx(url, *args, **kwargs):
        resp = mock.AsyncMock()
        if "/standings" in url:
            resp.json.return_value = {"records": records}
        else:
            resp.json.return_value = {}
        ctx = mock.AsyncMock()
        ctx.__aenter__.return_value = resp
        return ctx

    session.get.side_effect = make_ctx
    return session


class TestStandingsUpdateLayoutTicker:
    """layout="ticker" must build the legacy story shape exactly as
    before — untouched by the board wiring."""

    @pytest.mark.asyncio
    async def test_ticker_builds_legacy_segment_messages(self):
        widget = MLBStandingsMonitor(
            session=_two_division_session(),
            teams=["NYY", "LAD"],
            layout="ticker",
            top_n=1,
        )
        widget._tz = ZoneInfo("America/New_York")

        await widget.update()

        assert widget.feed_stories
        assert all(isinstance(s, SegmentMessage) for s in widget.feed_stories)
        assert not any(isinstance(s, MLBStandingsBoard) for s in widget.feed_stories)


class TestStandingsUpdateLayoutAutoAndBoard:
    @pytest.mark.parametrize("layout", ["auto", "board"])
    @pytest.mark.asyncio
    async def test_builds_one_board_per_tracked_division_in_config_order(self, layout):
        widget = MLBStandingsMonitor(
            session=_two_division_session(),
            teams=["NYY", "LAD"],
            layout=layout,
        )
        widget._tz = ZoneInfo("America/New_York")

        await widget.update()

        assert len(widget.feed_stories) == 2
        assert all(isinstance(s, MLBStandingsBoard) for s in widget.feed_stories)
        assert widget.feed_stories[0].division_name == "AL EAST"
        assert widget.feed_stories[1].division_name == "NL WEST"

    @pytest.mark.asyncio
    async def test_rows_capped_at_five(self):
        widget = MLBStandingsMonitor(
            session=_two_division_session(),
            teams=["NYY"],
            layout="board",
        )
        widget._tz = ZoneInfo("America/New_York")

        await widget.update()

        al_east = next(s for s in widget.feed_stories if s.division_name == "AL EAST")
        assert len(al_east.rows) == 5
        assert len(al_east.legacy_rows) == 5

    @pytest.mark.asyncio
    async def test_dedups_tracked_teams_in_same_division(self):
        widget = MLBStandingsMonitor(
            session=_two_division_session(),
            teams=["NYY", "BOS"],  # both AL EAST
            layout="board",
        )
        widget._tz = ZoneInfo("America/New_York")

        await widget.update()

        assert len(widget.feed_stories) == 1
        assert widget.feed_stories[0].division_name == "AL EAST"

    @pytest.mark.asyncio
    async def test_config_order_preserved_regardless_of_team_rank(self):
        widget = MLBStandingsMonitor(
            session=_two_division_session(),
            teams=["LAD", "NYY"],  # NL WEST first in config order
            layout="board",
        )
        widget._tz = ZoneInfo("America/New_York")

        await widget.update()

        assert [s.division_name for s in widget.feed_stories] == [
            "NL WEST",
            "AL EAST",
        ]

    @pytest.mark.asyncio
    async def test_empty_teams_falls_back_to_overall_leader_division(self):
        widget = MLBStandingsMonitor(
            session=_two_division_session(),
            teams=[],
            layout="board",
        )
        widget._tz = ZoneInfo("America/New_York")

        await widget.update()

        assert len(widget.feed_stories) == 1
        assert widget.feed_stories[0].division_name == "AL EAST"  # overall leader

    @pytest.mark.asyncio
    async def test_feed_title_unchanged(self):
        widget = MLBStandingsMonitor(
            session=_two_division_session(),
            teams=["NYY"],
            layout="board",
            title="MLB Standings",
        )
        widget._tz = ZoneInfo("America/New_York")

        await widget.update()

        assert isinstance(widget.feed_title, TickerMessage)
        assert widget.feed_title.text == "MLB Standings"

    @pytest.mark.asyncio
    async def test_legacy_rows_built_from_same_rows(self):
        widget = MLBStandingsMonitor(
            session=_two_division_session(),
            teams=["LAD"],
            layout="board",
        )
        widget._tz = ZoneInfo("America/New_York")

        await widget.update()

        board = widget.feed_stories[0]
        assert board.division_name == "NL WEST"
        assert len(board.legacy_rows) == len(board.rows) == 2
        assert any("Dodgers" in t for t, _ in board.legacy_rows[0].segments)
