from led_ticker_hockey.teams import NHL_TEAMS, normalize_team, team

EXPECTED = set(
    [
        "ANA",
        "BOS",
        "BUF",
        "CGY",
        "CAR",
        "CHI",
        "COL",
        "CBJ",
        "DAL",
        "DET",
        "EDM",
        "FLA",
        "LAK",
        "MIN",
        "MTL",
        "NSH",
        "NJD",
        "NYI",
        "NYR",
        "OTT",
        "PHI",
        "PIT",
        "SJS",
        "SEA",
        "STL",
        "TBL",
        "TOR",
        "UTA",
        "VAN",
        "VGK",
        "WSH",
        "WPG",
    ]
)


def test_all_32_teams_present():
    assert len(NHL_TEAMS) == 32
    assert set(NHL_TEAMS) == EXPECTED


def test_flyers_and_islanders_colors():
    assert team("phi").primary == (255, 90, 0)
    assert team("NYI").primary == (40, 110, 255)
    assert team("NYI").secondary == (255, 130, 40)


def test_unknown_team_is_neutral():
    t = team("XXX")
    assert t.primary == (200, 200, 200)
    assert t.secondary == (200, 200, 200)
    assert t.abbrev == "XXX"


def test_colors_are_led_visible():
    for t in NHL_TEAMS.values():
        assert max(t.primary) >= 90, t.abbrev
        assert max(t.secondary) >= 90, t.abbrev


def test_normalize_team():
    assert normalize_team("phi") == "PHI"
    assert normalize_team("PHL") is None
