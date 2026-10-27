"""The 32-team table: codes, LED-visible colours, ESPN id lookup."""

from led_ticker_football.teams import NFL_TEAMS, normalize_team, team, team_by_id

ALL_32 = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET",
    "GB", "HOU", "IND", "JAX", "KC", "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO",
    "NYG", "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WSH",
}  # fmt: skip


def test_all_32_teams_present():
    assert len(NFL_TEAMS) == 32
    assert set(NFL_TEAMS) == ALL_32


def test_eagles_and_giants_colors():
    assert team("phi").primary == (0, 150, 130)
    assert team("NYG").secondary == (230, 40, 60)
    assert team("PHI").nickname == "Eagles"
    assert team("NYG").city == "New York"


def test_unknown_team_is_neutral():
    t = team("XXX")
    assert t.primary == (200, 200, 200)
    assert t.secondary == (200, 200, 200)
    assert t.abbrev == "XXX"


def test_colors_are_led_visible():
    for t in NFL_TEAMS.values():
        assert max(t.primary) >= 90, t.abbrev
        assert max(t.secondary) >= 90, t.abbrev


def test_normalize_team():
    assert normalize_team("phi") == "PHI"
    assert normalize_team(" nyg ") == "NYG"
    assert normalize_team("PHL") is None


def test_team_by_id():
    assert team_by_id("21") == "PHI"
    assert team_by_id("19") == "NYG"
    assert team_by_id("999") is None
