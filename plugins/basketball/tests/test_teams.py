"""The 30-team table: codes, LED-visible colours, ESPN id lookup."""

from led_ticker_basketball.teams import NBA_TEAMS, normalize_team, team, team_by_id

ALL_30 = {
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS", "HOU",
    "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NO", "NY", "OKC", "ORL",
    "PHI", "PHX", "POR", "SA", "SAC", "TOR", "UTAH", "WSH",
}  # fmt: skip


def test_all_30_teams_present():
    assert len(NBA_TEAMS) == 30
    assert set(NBA_TEAMS) == ALL_30


def test_sixers_and_knicks_colors():
    assert team("phi").primary == (0, 107, 182)
    assert team("PHI").secondary == (237, 23, 76)
    assert team("NY").primary == (245, 132, 38)
    assert team("NY").secondary == (0, 107, 182)
    assert team("PHI").nickname == "76ers"


def test_knicks_code_is_ny():
    assert normalize_team("NYK") is None
    assert normalize_team("ny") == "NY"


def test_unknown_team_is_neutral():
    t = team("XXX")
    assert t.primary == (200, 200, 200)
    assert t.secondary == (200, 200, 200)
    assert t.abbrev == "XXX"


def test_colors_are_led_visible():
    for t in NBA_TEAMS.values():
        assert max(t.primary) >= 90, t.abbrev
        assert max(t.secondary) >= 90, t.abbrev


def test_team_by_id():
    assert team_by_id("20") == "PHI"
    assert team_by_id("999") is None
    assert len({t.espn_id for t in NBA_TEAMS.values()}) == 30
