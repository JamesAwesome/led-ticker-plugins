import json
from datetime import UTC, datetime
from pathlib import Path

from led_ticker_hockey._models import (
    GameInfo,
    build_demo_games,
    day_label,
    fmt_clock,
    live_clock_seconds,
    live_pp_seconds,
    parse_game,
    parse_situation,
    period_label,
    status_lines,
    winner,
)

FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text())


def _games(name):
    return _load(name)["games"]


def test_parse_live_fixture():
    g = parse_game(_games("score_live.json")[0], polled_at=100.0)
    assert g is not None
    assert (g.away, g.home) == ("PHI", "NYI")
    assert g.state == "live"
    assert (g.away_score, g.home_score) == (2, 1)
    assert (g.away_sog, g.home_sog) == (18, 22)
    assert period_label(g.period, g.period_type) == "2ND"
    assert g.clock_seconds == 754
    assert g.clock_running is True
    assert g.venue == "UBS Arena"
    assert g.start_utc == datetime(2026, 10, 22, 23, 0, tzinfo=UTC)
    assert len(g.goals) == 3
    assert g.polled_at == 100.0


def test_parse_final_ot():
    g = parse_game(_games("score_final_ot.json")[0], polled_at=0.0)
    assert g.state == "final"
    assert g.final_type == "OT"
    assert winner(g) == "PHI"


def test_parse_final_reg_has_no_type():
    g = parse_game(_games("score_live.json")[1], polled_at=0.0)
    assert g.state == "final"
    assert g.final_type is None
    assert winner(g) == "TOR"


def test_parse_future_fixture():
    rows = _games("score_future.json")
    g = parse_game(rows[0], polled_at=0.0)
    assert g.state == "future"
    assert g.away_sog is None
    assert winner(g) is None
    assert parse_game(rows[1], polled_at=0.0).state == "future"  # PRE


def test_parse_game_sparse_rows_never_raise():
    assert parse_game({}, polled_at=0.0) is None
    assert parse_game({"id": 1}, polled_at=0.0) is None
    row = {
        "id": 5,
        "gameState": "WEIRD",
        "awayTeam": {"abbrev": "PHI"},
        "homeTeam": {"abbrev": "NYI"},
    }
    g = parse_game(row, polled_at=0.0)
    assert g.state == "future"
    row["gameState"] = "LIVE"
    g = parse_game(row, polled_at=0.0)  # no clock
    assert g.state == "live"
    assert g.clock_seconds is None
    assert g.clock_running is False
    assert (g.away_score, g.home_score) == (0, 0)
    # junk everywhere
    junk = {
        "id": 6,
        "awayTeam": {"abbrev": "PHI", "score": "x"},
        "homeTeam": {"abbrev": "NYI"},
        "goals": "nope",
        "clock": [],
        "startTimeUTC": "garbage",
    }
    g = parse_game(junk, polled_at=0.0)
    assert g.goals == () and g.start_utc is None


def test_crit_is_live():
    row = {
        "id": 5,
        "gameState": "CRIT",
        "awayTeam": {"abbrev": "PHI"},
        "homeTeam": {"abbrev": "NYI"},
    }
    assert parse_game(row, polled_at=0.0).state == "live"


def test_situation_pp_and_en():
    s = parse_situation(_load("landing_pp.json"))
    assert s.pp_team == "NYI"
    assert s.pp_seconds == 102
    assert s.en_team is None
    e = parse_situation(_load("landing_en.json"))
    assert e.en_team == "PHI"
    assert e.pp_team is None
    assert parse_situation({}) is None
    assert parse_situation({"situation": {"situationCode": "12"}}) is None


def test_period_labels():
    assert period_label(1, "REG") == "1ST"
    assert period_label(2, "REG") == "2ND"
    assert period_label(3, "REG") == "3RD"
    assert period_label(4, "OT") == "OT"
    assert period_label(5, "OT") == "2OT"
    assert period_label(5, "SO") == "SO"


def _live(**kw):
    g = parse_game(_games("score_live.json")[0], polled_at=100.0)
    return GameInfo(**{**g.__dict__, **kw})


def test_clock_ticks_while_running():
    g = _live()
    assert live_clock_seconds(g, 110.0) == 744
    assert live_clock_seconds(g, 10_000.0) == 0
    assert live_clock_seconds(_live(clock_running=False), 110.0) == 754
    assert live_clock_seconds(_live(clock_seconds=None), 110.0) is None


def test_live_pp_seconds():
    s = parse_situation(_load("landing_pp.json"))
    g = _live(situation=s)
    assert live_pp_seconds(g, 110.0) == 92
    assert live_pp_seconds(_live(situation=s, clock_running=False), 110.0) == 102
    assert live_pp_seconds(_live(), 110.0) is None


def test_fmt_clock():
    assert fmt_clock(754) == "12:34"
    assert fmt_clock(42) == "0:42"
    assert fmt_clock(None) == ""


def test_day_label(tz):
    now = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)  # 11:00 ET Thu
    eve = datetime(2026, 10, 22, 23, 0, tzinfo=UTC)  # 19:00 ET
    aft = datetime(2026, 10, 22, 17, 0, tzinfo=UTC)  # 13:00 ET
    nxt = datetime(2026, 10, 23, 23, 0, tzinfo=UTC)
    assert day_label(eve, now, tz) == "TONIGHT"
    assert day_label(aft, now, tz) == "TODAY"
    assert day_label(nxt, now, tz) == "FRI OCT 23"


def test_status_lines(tz):
    g = _live()
    assert status_lines(g, 100.0, tz) == ("2ND", "12:34")
    assert status_lines(_live(in_intermission=True), 100.0, tz) == ("2ND INT", "12:34")
    f = parse_game(_games("score_final_ot.json")[0], polled_at=0.0)
    assert status_lines(f, 0.0, tz) == ("FINAL", "OT")
    fut = parse_game(_games("score_future.json")[0], polled_at=0.0)
    now = datetime(2026, 10, 22, 15, 0, tzinfo=UTC).timestamp()
    assert status_lines(fut, now, tz) == ("TONIGHT", "8:00 PM")


def test_goal_key_and_names():
    g = parse_game(_games("score_live.json")[0], polled_at=0.0)
    goal = g.goals[0]
    assert goal.key == "1:07:26:8477404"
    assert goal.team == "PHI"
    assert goal.scorer == "KONECNY"
    assert goal.season_total == 4
    assert goal.assists == ("MICHKOV",)
    assert goal.period_label == "1ST"
    assert goal.strength == "pp"
    assert goal.empty_net is False
    assert (goal.away_score, goal.home_score) == (1, 0)


def test_goal_empty_net_and_plain_string_fields():
    row = {
        "id": 9,
        "awayTeam": {"abbrev": "PHI", "name": "Flyers"},
        "homeTeam": {"abbrev": "NYI"},
        "goals": [
            {
                "period": 3,
                "timeInPeriod": "19:01",
                "playerId": 1,
                "name": "T. Konecny",
                "teamAbbrev": "PHI",
                "goalModifier": "empty-net",
                "assists": [{"name": "M. Michkov"}, 5],
            }
        ],
    }
    goal = parse_game(row, polled_at=0.0).goals[0]
    assert goal.empty_net is True
    assert goal.team == "PHI"
    assert goal.scorer == "KONECNY"
    assert goal.assists == ("MICHKOV",)
    assert goal.season_total is None
    assert goal.period_label == "3RD"


def test_demo_games(tz):
    now = 1_790_000_000.0
    games = build_demo_games(now)
    assert len(games) == 4
    assert all(g.polled_at == now for g in games)
    assert {g.state for g in games} == {"live", "final", "future"}
    live = games[0]
    assert (live.away_score, live.home_score) == (2, 1)
    assert live.situation.pp_team == "NYI"
    assert live_pp_seconds(live, now) == 102
    assert live.goals[0].scorer == "KONECNY"
    assert live.goals[0].assists == ("MICHKOV", "SANHEIM")
    assert games[1].in_intermission
    assert games[2].final_type == "OT" and winner(games[2]) == "PHI"
    assert games[3].venue == "UBS Arena"
    assert status_lines(games[3], now, tz)[1] == "7:00 PM"
    assert status_lines(games[3], now, tz)[0].startswith("FRI")
