"""Test MLB_TEAM_CHIPS table structure and legibility."""

from led_ticker_baseball.teams import MLB_TEAM_CHIPS, MLB_TEAM_COLORS


def test_all_30_teams_have_two_tone_chips():
    assert set(MLB_TEAM_CHIPS) == set(MLB_TEAM_COLORS)
    for c1, c2 in MLB_TEAM_CHIPS.values():
        assert len(c1) == 3 and len(c2) == 3


def test_chip_tones_are_lifted_for_led_legibility():
    for abbr, (c1, c2) in MLB_TEAM_CHIPS.items():
        assert max(c1) >= 120, f"{abbr} c1 too dark for panel"
        assert max(c2) >= 120, f"{abbr} c2 too dark for panel"


def test_tones_differ():
    for abbr, (c1, c2) in MLB_TEAM_CHIPS.items():
        assert c1 != c2, abbr
