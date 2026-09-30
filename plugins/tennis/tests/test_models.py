"""Pure helpers: surname, points, break point, status labels, parsing."""

from datetime import datetime, timedelta

import pytest

from led_ticker_tennis._models import (
    MatchInfo,
    build_demo_matches,
    format_points,
    format_start_time,
    is_break_point,
    parse_match,
    receiver,
    score_line,
    sort_key,
    status_label,
    surname,
    tour_matches,
)

from .conftest import TZ, live_match


class TestSurname:
    @pytest.mark.parametrize(
        ("name", "want"),
        [
            ("Jiri Lehecka", "Lehecka"),
            ("Sebastián Báez", "Báez"),
            ("Nadal", "Nadal"),
            ("Cash/Glasspool", "Cash/Glasspool"),
            ("  Arthur Fils  ", "Fils"),
            ("", ""),
        ],
    )
    def test_cases(self, name, want):
        assert surname(name) == want


class TestFormatPoints:
    def test_game_points(self):
        assert format_points(("15", "40")) == "15-40"

    def test_tiebreak_points_are_plain_numbers(self):
        assert format_points(("6", "6")) == "6-6"

    def test_null_side_renders_nothing(self):
        assert format_points((None, None)) == ""
        assert format_points(("40", None)) == ""

    def test_malformed_tuple(self):
        assert format_points(("40",)) == ""  # type: ignore[arg-type]


class TestBreakPoint:
    @pytest.mark.parametrize(
        ("points", "server", "want"),
        [
            # server = 1, receiver = p2 (points[1])
            (("0", "40"), 1, True),
            (("15", "40"), 1, True),
            (("30", "40"), 1, True),
            (("40", "40"), 1, False),
            (("40", "AD"), 1, True),
            (("AD", "40"), 1, False),
            (("40", "0"), 1, False),
            (("0", "0"), 1, False),
            # server = 2, receiver = p1 (points[0])
            (("40", "0"), 2, True),
            (("40", "15"), 2, True),
            (("40", "30"), 2, True),
            (("AD", "40"), 2, True),
            (("40", "AD"), 2, False),
            (("40", "40"), 2, False),
        ],
    )
    def test_truth_table(self, points, server, want):
        assert is_break_point(points, server, False) is want

    def test_never_in_a_tiebreak(self):
        assert is_break_point(("6", "6"), 1, True) is False
        assert is_break_point(("40", "AD"), 1, True) is False

    def test_null_safe(self):
        assert is_break_point(("0", "40"), None, False) is False
        assert is_break_point((None, "40"), 1, False) is False
        assert is_break_point(("0", None), 1, False) is False
        assert is_break_point(("0", "40"), 3, False) is False

    def test_receiver(self):
        assert receiver(1) == 2
        assert receiver(2) == 1
        assert receiver(None) is None


class TestStatusLabel:
    def test_live_set_number(self):
        assert status_label(live_match()) == "SET 2"

    def test_live_before_first_game(self):
        assert status_label(live_match(games=[])) == "LIVE"

    def test_interrupted_is_suspended(self):
        assert status_label(live_match(event_status="Interrupted")) == "SUSP"

    @pytest.mark.parametrize(
        ("outcome", "want"),
        [
            ("completed", "FINAL"),
            ("", "FINAL"),
            ("unresolved", "FINAL"),
            ("retired", "RET"),
            ("walkover", "W/O"),
            ("default", "DEF"),
            ("abandoned", "ABD"),
            ("cancelled", "CANC"),
            ("something-new", "FINAL"),
        ],
    )
    def test_final_outcomes(self, outcome, want):
        assert status_label(live_match(state="final", outcome=outcome)) == want

    def test_staleness_does_not_replace_the_state(self):
        assert status_label(live_match(stale=True)) == "SET 2"
        assert status_label(live_match(state="final", stale=True)) == "FINAL"

    def test_upcoming_is_blank(self):
        assert status_label(live_match(state="upcoming")) == ""


class TestFormatStartTime:
    def test_none_is_tbd(self):
        assert format_start_time(None, TZ) == ("", "TBD")

    def test_today(self):
        now = datetime.now(TZ)
        dt = now.replace(hour=15, minute=0, second=0, microsecond=0)
        assert format_start_time(dt, TZ) == ("Today", "3:00 PM")

    def test_tomorrow(self):
        now = datetime.now(TZ) + timedelta(days=1)
        dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
        assert format_start_time(dt, TZ) == ("Tmrw", "9:30 AM")

    def test_this_week_uses_weekday(self):
        dt = (datetime.now(TZ) + timedelta(days=3)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        day, clock = format_start_time(dt, TZ)
        assert day == dt.strftime("%a")
        assert clock == "12:00 PM"

    def test_far_out_uses_date(self):
        dt = (datetime.now(TZ) + timedelta(days=20)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        day, _ = format_start_time(dt, TZ)
        assert day == dt.strftime("%b %-d")


class TestScoreLine:
    def test_live(self):
        assert score_line(live_match()) == "4-6 3-4 (15-40)"

    def test_final_has_no_points(self):
        assert (
            score_line(live_match(state="final", games=[(6, 2), (6, 3)])) == "6-2 6-3"
        )

    def test_tiebreak(self):
        m = live_match(games=[(6, 6)], points=("5", "6"), is_tiebreak=True)
        assert score_line(m) == "6-6 (5-6)"


class TestTourFilter:
    @pytest.mark.parametrize(
        ("tour", "wanted", "want"),
        [
            ("atp", ["atp"], True),
            ("ATP", ["atp"], True),
            ("challenger_men", ["challenger"], True),
            ("juniors_girls", ["juniors"], True),
            ("wta", ["atp"], False),
            ("atpx", ["atp"], False),
            (None, [], True),
            ("", [], True),
            (None, ["atp"], False),
        ],
    )
    def test_cases(self, tour, wanted, want):
        assert tour_matches(tour, wanted) is want

    def test_sort_key_main_tours_first_then_earliest(self):
        t0 = datetime(2026, 9, 12, 12, tzinfo=TZ)
        ms = [
            live_match(tour="itf", start_time=t0),
            live_match(tour="wta", start_time=t0 + timedelta(hours=1)),
            live_match(tour="wta", start_time=t0),
            live_match(tour="atp", start_time=None),
            live_match(tour="", start_time=t0),
        ]
        ms.sort(key=sort_key)
        assert [(m.tour, m.start_time) for m in ms] == [
            ("atp", None),
            ("wta", t0),
            ("wta", t0 + timedelta(hours=1)),
            ("itf", t0),
            ("", t0),
        ]


LIVE_ROW = {
    "id": 90211,
    "tournament": "Cincinnati Open",
    "tour": "atp",
    "round_code": "R16",
    "status": "live",
    "event_status": None,
    "is_doubles": False,
    "scheduled_time": "2026-08-18T01:15:00Z",
    "players": {
        "p1": {"id": 50101, "name": "Jiri Lehecka", "ranking": 21},
        "p2": {"id": 50102, "name": "Arthur Fils", "ranking": 15},
    },
    "score": {
        "sets": [0, 1],
        "games": [[4, 3], [6, 4]],
        "points": ["15", "40"],
        "server": 1,
        "is_tiebreak": False,
    },
    "winner": None,
    "outcome": None,
}

COMPLETED_ROW = {
    "id": 90209,
    "tournament": "Cincinnati Open",
    "tour": "atp",
    "round_code": "R32",
    "status": "completed",
    "event_status": "Retired",
    "outcome": "retired",
    "players": {
        "p1": {"id": 50601, "name": "Tommy Paul", "ranking": 12},
        "p2": {"id": 50602, "name": "Adolfo Vallejo", "ranking": 480},
    },
    "score": {
        "sets": [1, 0],
        "games": [],
        "points": [None, None],
        "server": None,
        "is_tiebreak": False,
    },
    "winner": 1,
    "withdrew": 2,
}


class TestParseMatch:
    def test_live_row(self):
        m = parse_match(LIVE_ROW)
        assert (m.match_id, m.p1, m.p2) == (90211, "Lehecka", "Fils")
        assert (m.p1_full, m.p1_rank, m.p2_rank) == ("Jiri Lehecka", 21, 15)
        assert m.state == "live" and m.outcome == ""
        assert m.sets == (0, 1)
        assert m.games == [(4, 6), (3, 4)]  # player-major -> per-set pairs
        assert m.points == ("15", "40") and m.server == 1
        assert m.is_tiebreak is False and m.winner is None
        assert (m.tour, m.tournament, m.round_code) == ("atp", "Cincinnati Open", "R16")
        assert m.start_time is not None and m.start_time.year == 2026
        assert m.current_set == 2 and m.current_games == (3, 4)
        assert is_break_point(m.points, m.server, m.is_tiebreak)

    def test_tiebreak_row(self):
        row = {
            **LIVE_ROW,
            "score": {
                "sets": [0, 0],
                "games": [[5], [6]],
                "points": ["6", "6"],
                "server": 1,
                "is_tiebreak": True,
            },
        }
        m = parse_match(row)
        assert m.is_tiebreak and m.games == [(5, 6)] and m.points == ("6", "6")

    def test_completed_retired_row(self):
        m = parse_match(COMPLETED_ROW)
        assert m.state == "final" and m.outcome == "retired"
        assert m.winner == 1 and m.games == [] and m.points == (None, None)
        assert m.server is None
        assert status_label(m) == "RET"

    def test_cancelled_status_forces_outcome(self):
        m = parse_match({**COMPLETED_ROW, "status": "cancelled", "outcome": None})
        assert m.state == "final" and m.outcome == "cancelled"
        assert status_label(m) == "CANC"

    def test_upcoming_row(self):
        m = parse_match({**LIVE_ROW, "status": "upcoming", "score": None})
        assert m.state == "upcoming" and m.games == [] and m.outcome == ""

    def test_doubles_detected_from_pairing(self):
        row = {
            **LIVE_ROW,
            "is_doubles": False,
            "players": {
                "p1": {"name": "Cash/Glasspool"},
                "p2": {"name": "Ram/Salisbury"},
            },
        }
        m = parse_match(row)
        assert m.is_doubles and m.p1 == "Cash/Glasspool"

    def test_sparse_row_never_raises(self):
        m = parse_match({})
        assert m.p1 == "?" and m.p2 == "?" and m.state == "upcoming"
        assert m.games == [] and m.points == (None, None) and m.server is None

    def test_garbage_types_never_raise(self):
        m = parse_match(
            {
                "id": "x",
                "players": None,
                "score": {"games": "nope", "points": "40", "server": "1", "sets": [1]},
                "status": 7,
                "winner": 5,
            }
        )
        assert m.match_id == 0 and m.games == [] and m.server is None
        assert m.points == (None, None) and m.winner is None

    def test_ragged_games_keep_agreed_sets(self):
        row = {**LIVE_ROW, "score": {**LIVE_ROW["score"], "games": [[6, 3], [4]]}}
        assert parse_match(row).games == [(6, 4)]

    def test_missing_sets_are_derived_from_games(self):
        row = {
            **LIVE_ROW,
            "score": {
                **LIVE_ROW["score"],
                "sets": None,
                "games": [[6, 7, 2], [4, 6, 1]],
            },
        }
        assert parse_match(row).sets == (2, 0)  # 6-4, 7-6 won; 2-1 in progress


def test_demo_matches_cover_every_renderer_branch():
    ms = build_demo_matches(TZ)
    assert {m.state for m in ms} == {"live", "final", "upcoming"}
    assert any(is_break_point(m.points, m.server, m.is_tiebreak) for m in ms)
    assert any(m.is_tiebreak for m in ms)
    assert any(m.outcome == "retired" for m in ms)
    assert all(isinstance(m, MatchInfo) for m in ms)
