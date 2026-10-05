"""Legacy scale-1 renderers: the two-band board and the ticker line."""

from led_ticker.plugin import FONT_SMALL, SegmentMessage

from led_ticker_tennis._scoreboard import (
    TennisScoreboardMessage,
    _build_match_message,
    _build_scoreboard_message,
    _short_status,
)

from .conftest import TZ, lit, live_match


def test_short_status():
    assert _short_status("SET 3") == "S3"
    assert _short_status("FINAL") == "F"
    assert _short_status("RET") == "RET"
    assert _short_status("SUSP") == "SUSP"


def test_board_rows_content():
    msg = _build_scoreboard_message(live_match(), TZ)
    assert isinstance(msg, TennisScoreboardMessage) and msg.font is FONT_SMALL
    r1, r2 = msg._rows()
    assert [t for t, _ in r1] == ["LEHECKA*", "4", "3", "15", "S2"]
    assert [t for t, _ in r2] == ["FILS", "6", "4", "40", "BP", "R16"]


def test_board_rows_tiebreak_final_upcoming():
    tb = live_match(games=[(6, 6)], points=("5", "6"), is_tiebreak=True, server=2)
    r1, r2 = _build_scoreboard_message(tb, TZ)._rows()
    assert [t for t, _ in r2] == ["FILS*", "6", "6", "TB"]
    fin = live_match(state="final", outcome="retired", winner=1, games=[(6, 2), (3, 1)])
    r1, r2 = _build_scoreboard_message(fin, TZ)._rows()
    assert [t for t, _ in r1] == ["LEHECKA", "6", "3", "RET"]
    assert "BP" not in [t for t, _ in r2]
    up = live_match(state="upcoming", games=[], points=(None, None), start_time=None)
    r1, r2 = _build_scoreboard_message(up, TZ)._rows()
    assert [t for t, _ in r1] == ["LEHECKA", "NEXT"]
    assert [t for t, _ in r2] == ["FILS", "TBD"]


def test_board_rows_keep_the_state_when_stale():
    r1, r2 = _build_scoreboard_message(live_match(stale=True), TZ)._rows()
    assert r1[-1][0] == "S2" and r2[-1][0] == "STALE"
    tb = live_match(games=[(6, 6)], points=("5", "6"), is_tiebreak=True, stale=True)
    r1, r2 = _build_scoreboard_message(tb, TZ)._rows()
    assert r1[-1][0] == "S1" and r2[-1][0] == "STALE"
    fin = live_match(state="final", outcome="retired", winner=1, stale=True)
    r1, r2 = _build_scoreboard_message(fin, TZ)._rows()
    assert r1[-1][0] == "RET" and r2[-1][0] == "STALE"


def test_stale_board_still_fits(smallsign):
    msg = _build_scoreboard_message(live_match(stale=True), TZ)
    _, cursor = msg.draw(smallsign, 0)
    assert cursor == 160
    assert all(x < 160 for x, _ in lit(smallsign))


def test_board_draws_both_bands_and_returns_width(smallsign):
    msg = _build_scoreboard_message(live_match(), TZ)
    _, cursor = msg.draw(smallsign, 0)
    assert cursor == 160
    rows = {y for _, y in lit(smallsign)}
    assert rows & set(range(0, 8)) and rows & set(range(8, 16))


def test_board_truncates_a_long_name_instead_of_overlapping(smallsign):
    long = live_match(
        p1="Bopanna/Kokkinakis",
        p2="Gonzalez/Molteni",
        games=[(10, 10), (10, 10), (10, 10), (10, 10), (10, 10)],
        points=("40", "AD"),
    )
    msg = _build_scoreboard_message(long, TZ)
    msg.draw(smallsign, 0)
    assert lit(smallsign)  # no raise, still paints


def test_board_bg_color_and_offset(smallsign):
    from led_ticker.plugin import make_color

    msg = _build_scoreboard_message(live_match(), TZ, bg_color=make_color(10, 10, 40))
    msg.draw(smallsign, 0, y_offset=0)
    assert (0, 0) in smallsign._pixels


def test_ticker_message_segments_and_centering():
    msg = _build_match_message(live_match(), TZ)
    assert isinstance(msg, SegmentMessage) and msg.center
    texts = [t for t, _ in msg.segments]
    assert texts[:4] == ["LEHECKA", "*", " ", "v"]  # "*" hugs its name
    assert "".join(texts) == (
        "LEHECKA* v FILS 4-6 3-4 (15-40) BP · SET 2 · R16 CINCINNATI OPEN"
    )


def test_ticker_message_show_ranking():
    msg = _build_match_message(live_match(), TZ, show_ranking=True)
    assert msg.segments[0][0] == "LEHECKA (21)"
