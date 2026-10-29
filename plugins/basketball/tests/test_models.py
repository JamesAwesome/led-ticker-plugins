"""GameInfo parsing, leaders, linescores, status lines, clutch, finals, demo."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from led_ticker_basketball._models import (
    GameInfo,
    Leader,
    build_demo_games,
    clock_seconds,
    final_event,
    is_clutch,
    leader_text,
    parse_event,
    period_label,
    status_lines,
)

FIX = Path(__file__).parent / "fixtures"
NOW = 1_800_000_000.0


def _load(name: str):
    return json.loads((FIX / name).read_text())


def _schedule_final() -> dict:
    return _load("schedule_phi.json")["events"][0]


def _game(**kw) -> GameInfo:
    base = {
        "game_id": "g",
        "state": "live",
        "status": "STATUS_IN_PROGRESS",
        "away": "PHI",
        "home": "NY",
        "away_score": 98,
        "home_score": 101,
        "period": 4,
        "clock": "2:13",
        "start_utc": None,
        "time_tbd": False,
        "venue": "",
        "broadcast": "",
        "away_record": "",
        "home_record": "",
        "final_ot": False,
        "neutral_site": False,
    }
    base.update(kw)
    return GameInfo(**base)


def test_parse_scheduled_event():
    g = parse_event(_load("scoreboard_20261028.json")["events"][0], polled_at=5.0)
    assert g is not None
    assert (g.game_id, g.state, g.away, g.home) == ("401909881", "future", "MIA", "ATL")
    assert g.venue == "State Farm Arena"
    assert g.away_record == "0-4" and g.home_record == "2-2"
    assert g.start_utc is not None and g.polled_at == 5.0
    assert g.away_leader is None and g.home_leader is None  # pointsPerGame ignored
    assert g.away_linescores == () and g.home_linescores == ()


def test_parse_final_event():
    g = parse_event(_schedule_final(), polled_at=0.0)
    assert g is not None
    assert (g.state, g.away, g.home) == ("final", "PHI", "NY")
    assert (g.away_score, g.home_score) == (106, 100)
    assert g.away_record == "1-0" and g.home_record == "0-1"
    assert g.final_ot is False
    assert g.away_leader == Leader("T. MAXEY", 28)


def test_parse_final_ot_event():
    g = parse_event(_load("event_final_ot.json"), polled_at=0.0)
    assert g is not None and g.final_ot is True
    assert g.status == "STATUS_FINAL" and g.period == 5
    assert status_lines(g, NOW, None) == ("FINAL", "OT")  # type: ignore[arg-type]
    assert g.away_linescores == (22, 29, 34, 20, 12)
    assert g.home_linescores == (32, 23, 30, 20, 6)


def test_parse_real_phi_final():
    # 2026-10-28 PHI @ IND, captured after the buzzer (not hand-written).
    g = parse_event(_load("event_final_phi.json"), polled_at=0.0)
    assert g is not None and (g.state, g.away, g.home) == ("final", "PHI", "IND")
    assert (g.away_score, g.home_score) == (114, 109)
    assert (g.away_record, g.home_record) == ("4-1", "2-3")
    assert g.away_leader == Leader("T. MAXEY", 27)
    assert g.home_leader == Leader("P. SIAKAM", 26)
    assert g.away_linescores == (25, 37, 13, 39) and not g.final_ot
    fe = final_event(g)
    assert fe is not None and (fe.winner, fe.loser) == ("PHI", "IND")
    assert fe.leader == g.away_leader


def test_parse_live_event_leaders_and_linescores():
    g = parse_event(_load("event_live.json"), polled_at=0.0)
    assert g is not None and g.state == "live"
    assert g.away_leader is not None and g.home_leader is not None
    assert g.away_leader.name == "J. EMBIID" and g.away_leader.points == 31
    assert g.home_leader.name == "J. BRUNSON" and g.home_leader.points == 28
    assert len(g.away_linescores) == 4 and len(g.home_linescores) == 4
    assert g.away_linescores == (24, 26, 25, 23)
    assert (g.away_score, g.home_score) == (98, 101)
    assert (g.period, g.clock) == (4, "2:13")
    assert (g.away_record, g.home_record) == ("5-2", "4-3")
    assert not is_clutch(g)  # 2:13 is outside the 2:00 clutch window


def test_parse_event_without_leaders():
    e = _load("event_live.json")
    for k in e["competitions"][0]["competitors"]:
        k.pop("leaders")
    g = parse_event(e, polled_at=0.0)
    assert g is not None
    assert g.away_leader is None and g.home_leader is None


@pytest.mark.parametrize(
    "e",
    [{}, {"id": "1"}, {"id": "1", "competitions": [None]}, {"competitions": "x"}, None],
)
def test_parse_event_sparse_never_raises(e):
    assert parse_event(e, polled_at=0.0) is None  # type: ignore[arg-type]


def test_parse_event_junk_leaders_never_raise():
    e = _load("event_live.json")
    e["competitions"][0]["competitors"][0]["leaders"] = [
        {"name": "points", "leaders": [{"displayValue": "x", "athlete": None}]}
    ]
    e["competitions"][0]["competitors"][1]["leaders"] = "junk"
    g = parse_event(e, polled_at=0.0)
    assert g is not None
    assert g.away_leader is None and g.home_leader is None


def test_postponed_and_canceled():
    e = _schedule_final()
    e["competitions"][0]["status"]["type"].update(
        name="STATUS_POSTPONED", state="pre", detail="Postponed"
    )
    g = parse_event(e, polled_at=0.0)
    assert g is not None and g.state == "future" and g.time_tbd
    e["competitions"][0]["status"]["type"].update(name="STATUS_CANCELED", state="pre")
    g = parse_event(e, polled_at=0.0)
    assert g is not None and g.state == "final"


def test_period_labels():
    assert period_label(1, "STATUS_IN_PROGRESS") == "Q1"
    assert period_label(4, "STATUS_IN_PROGRESS") == "Q4"
    assert period_label(5, "STATUS_IN_PROGRESS") == "OT"
    assert period_label(6, "STATUS_IN_PROGRESS") == "2OT"
    assert period_label(2, "STATUS_HALFTIME") == "HALF"
    assert period_label(3, "STATUS_END_PERIOD") == "END Q3"
    assert period_label(5, "STATUS_END_PERIOD") == "END OT"
    assert period_label(3, "STATUS_DELAYED") == "DELAY"
    assert period_label(3, "STATUS_SUSPENDED") == "SUSP"


def test_status_lines_end_period_hides_zero_clock(tz):
    g = _game(status="STATUS_END_PERIOD", period=3, clock="0.0")
    assert status_lines(g, NOW, tz) == ("END Q3", "")
    g = _game(status="STATUS_HALFTIME", period=2, clock="0.0")
    assert status_lines(g, NOW, tz) == ("HALF", "")
    g = _game(status="STATUS_DELAYED", clock="0.0")
    assert status_lines(g, NOW, tz) == ("DELAY", "")


def test_status_lines_live_and_future(tz):
    assert status_lines(_game(), NOW, tz) == ("Q4", "2:13")
    g = parse_event(_load("scoreboard_20261028.json")["events"][0], polled_at=0.0)
    assert g is not None
    day, clock = status_lines(g, 1_793_000_000.0, tz)  # 2026-10-26: not same day
    assert clock == "7:00 PM" and day.startswith("WED")


@pytest.mark.parametrize(
    ("clock", "expected"),
    [("2:13", 133.0), ("45.3", 45.3), ("0.0", 0.0), ("12:00", 720.0), ("", None),
     ("junk", None), ("a:b", None)],
)  # fmt: skip
def test_clock_seconds(clock, expected):
    assert clock_seconds(clock) == expected


def test_is_clutch_parses_tenths():
    assert is_clutch(_game(clock="45.3", home_score=101, away_score=98))
    assert not is_clutch(_game(clock="2:01"))
    assert is_clutch(_game(clock="2:00"))
    assert not is_clutch(_game(period=3, clock="1:00"))
    assert not is_clutch(_game(clock="45.3", home_score=104, away_score=98))
    assert is_clutch(_game(clock="45.3", home_score=103, away_score=98))
    assert is_clutch(_game(period=5, clock="1:00"))
    assert not is_clutch(_game(status="STATUS_END_PERIOD", clock="0.0"))
    assert not is_clutch(_game(state="final"))
    assert not is_clutch(_game(clock=""))


def test_leader_text_styles():
    ld = Leader("J. EMBIID", 31)
    assert leader_text(ld, style="full") == "J. EMBIID 31 PTS"
    assert leader_text(ld, style="short") == "EMBIID 31"
    assert leader_text(Leader("EMBIID", 5), style="short") == "EMBIID 5"
    assert leader_text(None, style="full") == ""
    assert leader_text(None, style="short") == ""


def test_final_event_requires_winner():
    live = parse_event(_load("event_live.json"), polled_at=0.0)
    assert live is not None and final_event(live) is None
    tie = _game(state="final", status="STATUS_FINAL", away_score=100, home_score=100)
    assert final_event(tie) is None
    canc = _game(state="final", status="STATUS_CANCELED")
    assert final_event(canc) is None


def test_final_event_carries_winner_leader():
    g = parse_event(_schedule_final(), polled_at=0.0)
    assert g is not None
    fe = final_event(g)
    assert fe is not None
    assert (fe.key, fe.game_id) == (g.game_id, g.game_id)
    assert (fe.winner, fe.loser) == ("PHI", "NY")
    assert (fe.away_score, fe.home_score) == (106, 100)
    assert fe.leader == g.away_leader
    ot = parse_event(_load("event_final_ot.json"), polled_at=0.0)
    assert ot is not None
    fe = final_event(ot)
    assert fe is not None and fe.winner == "SA" and fe.final_ot
    assert fe.leader == ot.away_leader
    assert fe == final_event(replace(ot))


def test_demo_games_cover_states():
    games, fe = build_demo_games(NOW)
    assert [g.game_id for g in games] == [
        "demo-live", "demo-half", "demo-final-ot", "demo-next",
    ]  # fmt: skip
    assert [g.state for g in games] == ["live", "live", "final", "future"]
    assert fe.winner == "PHI" and fe.key == "demo-live"
    assert (fe.loser, fe.away_score, fe.home_score) == ("NY", 112, 108)
    assert fe.leader == Leader("J. EMBIID", 31)
    live = games[0]
    assert is_clutch(live)
    assert live.away_leader == Leader("J. EMBIID", 31)
    assert live.home_leader == Leader("J. BRUNSON", 28)
    assert live.away_linescores == (24, 26, 25, 23)
    assert live.venue == "Madison Square Garden"
    assert live.clock == "1:48"
    assert games[2].final_ot
    assert games[3].broadcast == "ESPN" and games[3].start_utc is not None
