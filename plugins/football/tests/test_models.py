"""Pure parsing and formatting over the ESPN fixtures."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from led_ticker_football._models import (
    GameInfo,
    ScoringPlay,
    build_demo_games,
    diff_scores,
    parse_event,
    period_label,
    status_lines,
    winner,
)

FIX = Path(__file__).parent / "fixtures"
T0 = 1_761_000_000.0


def _week7():
    return json.loads((FIX / "scoreboard_week7.json").read_text())


def _event(name):
    return json.loads((FIX / name).read_text())


def _week7_event(gid):
    return next(e for e in _week7()["events"] if e["id"] == gid)


def _game(**kw) -> GameInfo:
    base = dict(
        game_id="1",
        state="live",
        status="STATUS_IN_PROGRESS",
        away="PHI",
        home="NYG",
        away_score=20,
        home_score=17,
        period=4,
        clock="2:13",
        start_utc=None,
        time_tbd=False,
        venue="",
        broadcast="",
        away_record="",
        home_record="",
        final_ot=False,
        neutral_site=False,
        week=7,
        polled_at=T0,
    )
    base.update(kw)
    return GameInfo(**base)


def test_parse_scheduled_event():
    g = parse_event(_week7_event("401873009"), polled_at=T0)
    assert g is not None
    assert g.state == "future"
    assert g.start_utc == datetime(2026, 10, 27, 0, 15, tzinfo=UTC)
    assert g.venue == "Lincoln Financial Field"
    assert g.broadcast == "ESPN"
    assert (g.away, g.home) == ("DAL", "PHI")
    assert (g.away_record, g.home_record) == ("2-4", "2-4")
    assert g.week == 7
    assert g.time_tbd is False
    assert g.situation is None


def test_parse_final_ot_event():
    g = parse_event(_week7_event("401873016"), polled_at=T0)
    assert g.state == "final"
    assert g.final_ot is True
    assert (g.away_score, g.home_score) == (27, 21)
    assert winner(g) == "NYG"
    assert g.period == 5


def test_parse_final_regulation():
    g = parse_event(_week7_event("401873010"), polled_at=T0)
    assert g.final_ot is False
    assert winner(g) == "CHI"


def test_parse_live_event_situation():
    g = parse_event(_event("event_live.json"), polled_at=T0)
    assert g.state == "live"
    assert g.status == "STATUS_IN_PROGRESS"
    assert g.clock == "2:13"
    s = g.situation
    assert s is not None
    assert s.possession == "NYG"
    assert s.down_distance == "2ND & 7"
    assert s.spot == "PHI 24"
    assert s.red_zone is False
    assert (s.away_timeouts, s.home_timeouts) == (1, 2)
    assert s.last_play is not None
    assert s.last_play.score_value == 6
    assert s.last_play.team == "PHI"
    assert s.last_play.type_text == "Rushing Touchdown"


def test_parse_situation_dead_ball():
    g = parse_event(_event("event_live_deadball.json"), polled_at=T0)
    s = g.situation
    assert s is not None
    assert s.possession is None
    assert s.down_distance == ""
    assert s.spot == ""
    assert s.red_zone is True
    assert (s.away_timeouts, s.home_timeouts) == (1, 2)


def test_parse_halftime_event(tz):
    g = parse_event(_event("event_halftime.json"), polled_at=T0)
    assert g.state == "live"
    assert g.status == "STATUS_HALFTIME"
    assert g.situation is None
    assert status_lines(g, T0, tz) == ("HALF", "")


def test_schedule_shape_object_scores():
    sched = _event("schedule_phi.json")
    g = parse_event(sched["events"][0], polled_at=T0)
    assert g is not None
    assert g.state == "final"
    assert (g.away, g.home) == ("WSH", "PHI")
    assert (g.away_score, g.home_score) == (22, 24)
    assert winner(g) == "PHI"
    assert g.week == 1


def test_parse_event_sparse_never_raises():
    assert parse_event({}, polled_at=T0) is None
    assert parse_event({"id": "1"}, polled_at=T0) is None
    no_team = {
        "id": "2",
        "competitions": [{"competitors": [{"homeAway": "home"}, {"homeAway": "away"}]}],
    }
    assert parse_event(no_team, polled_at=T0) is None
    weird = {
        "id": "3",
        "status": {"type": {"name": "WEIRD", "state": "in"}},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "team": {"abbreviation": "NYG"}},
                    {"homeAway": "away", "team": {"abbreviation": "PHI"}},
                ]
            }
        ],
    }
    g = parse_event(weird, polled_at=T0)
    assert g is not None
    assert g.state == "live"
    assert g.status == "WEIRD"
    assert (g.away_score, g.home_score) == (0, 0)
    assert g.clock == ""
    assert g.start_utc is None


def test_tbd_kickoff(tz):
    sched = _event("schedule_phi.json")
    g = parse_event(sched["events"][2], polled_at=T0)
    assert g.time_tbd is True
    day, kickoff = status_lines(g, T0, tz)
    assert kickoff == "TBD"
    assert day == "SUN JAN 10"


@pytest.mark.parametrize(
    "period,status,expected",
    [
        (1, "STATUS_IN_PROGRESS", "Q1"),
        (4, "STATUS_IN_PROGRESS", "Q4"),
        (2, "STATUS_HALFTIME", "HALF"),
        (3, "STATUS_END_PERIOD", "END Q3"),
        (5, "STATUS_IN_PROGRESS", "OT"),
        (6, "STATUS_IN_PROGRESS", "2OT"),
        (1, "STATUS_DELAYED", "DELAY"),
        (2, "STATUS_SUSPENDED", "SUSP"),
    ],
)
def test_period_labels(period, status, expected):
    assert period_label(period, status) == expected


def test_status_lines_states(tz):
    live = _game()
    assert status_lines(live, T0, tz) == ("Q4", "2:13")
    half = _game(status="STATUS_HALFTIME", period=2, clock="0:00")
    assert status_lines(half, T0, tz) == ("HALF", "")
    endq = _game(status="STATUS_END_PERIOD", period=3, clock="0:00")
    assert status_lines(endq, T0, tz) == ("END Q3", "")
    final_ot = _game(state="final", status="STATUS_FINAL", period=5, final_ot=True)
    assert status_lines(final_ot, T0, tz) == ("FINAL", "OT")
    final = _game(state="final", status="STATUS_FINAL")
    assert status_lines(final, T0, tz) == ("FINAL", "")
    ppd = _game(state="future", status="STATUS_POSTPONED", time_tbd=True)
    assert status_lines(ppd, T0, tz) == ("PPD", "")
    canc = _game(state="final", status="STATUS_CANCELED")
    assert status_lines(canc, T0, tz) == ("CANC", "")
    assert winner(canc) is None
    tonight = datetime.fromtimestamp(T0, UTC)
    tonight = tonight.replace(hour=0, minute=15)  # 8:15 PM EDT previous local day
    fut = _game(state="future", status="STATUS_SCHEDULED", start_utc=tonight)
    day, kick = status_lines(fut, tonight.timestamp() - 3600, tz)
    assert kick == "8:15 PM"
    assert day == "TONIGHT"


def _td(**kw) -> ScoringPlay:
    base = dict(
        key="1:26:17",
        team="PHI",
        kind="TD",
        extra="",
        text="",
        period_label="Q4",
        clock="2:13",
        away_score=26,
        home_score=17,
    )
    base.update(kw)
    return ScoringPlay(**base)


@pytest.mark.parametrize(
    "prev,new,last_td,kinds,extra,follow_extra",
    [
        ((20, 17), (26, 17), None, ["TD"], "", None),
        ((20, 17), (27, 17), None, ["TD"], "+PAT", None),
        ((20, 17), (28, 17), None, ["TD"], "+2PT", None),
        ((20, 17), (23, 17), None, ["FG"], "", None),
        ((20, 17), (22, 17), None, ["SAFETY"], "", None),
        ((26, 17), (27, 17), _td(), [], None, "+PAT"),
        ((26, 17), (28, 17), _td(), [], None, "+2PT"),
        ((27, 17), (20, 17), None, [], None, None),
        ((20, 17), (29, 17), None, ["TD"], "", None),
        ((20, 17), (20, 24), None, ["TD"], "+PAT", None),
    ],
)
def test_diff_scores_table(prev, new, last_td, kinds, extra, follow_extra):
    game = _game(away_score=new[0], home_score=new[1])
    plays, follow = diff_scores(game, prev, last_td)
    assert [p.kind for p in plays] == kinds
    if kinds:
        p = plays[0]
        assert p.extra == extra
        assert (p.away_score, p.home_score) == new
        assert p.key == f"1:{new[0]}:{new[1]}"
        assert p.period_label == "Q4"
        assert p.clock == "2:13"
        assert p.team == ("NYG" if new[1] != prev[1] else "PHI")
    if follow_extra is None:
        assert follow is None
    else:
        assert follow is not None
        assert follow.extra == follow_extra
        assert follow.key == f"1:{new[0]}:{new[1]}"
        assert (follow.away_score, follow.home_score) == new
        assert follow.kind == "TD"


def test_diff_scores_text_from_last_play():
    live = parse_event(_event("event_live.json"), polled_at=T0)
    bumped = GameInfo(**{**live.__dict__, "away_score": 26})
    plays, _ = diff_scores(bumped, (20, 17), None)
    assert plays[0].text == "JALEN HURTS 12 YD RUSH"
    # A last play by the other team never decorates this team's score.
    bumped_home = GameInfo(**{**live.__dict__, "home_score": 23})
    plays, _ = diff_scores(bumped_home, (20, 17), None)
    assert plays[0].team == "NYG"
    assert plays[0].text == ""


def test_demo_games_cover_states():
    games, td = build_demo_games(T0)
    assert len(games) == 5
    assert [g.state for g in games] == ["live", "live", "final", "future", "future"]
    assert games[1].status == "STATUS_HALFTIME"
    assert games[2].final_ot is True
    assert td.team == "PHI"
    assert td.kind == "TD"
    assert td.extra == "+PAT"
    assert games[0].situation is not None
    assert games[0].situation.possession == "NYG"
    assert all({g.away, g.home} == {"PHI", "NYG"} for g in games)
    assert games[3].start_utc is not None and games[3].start_utc.timestamp() > T0
