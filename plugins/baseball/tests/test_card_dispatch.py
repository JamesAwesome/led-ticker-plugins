"""tests/test_card_dispatch.py — MLBGameCard scale dispatch.

HeadlessBackend takes (width, height) positionally (see
led_ticker/backends/headless.py) — there is no rows/cols/chain_length kwarg
surface (that's an RgbMatrixBackend shape); mirrors the precedent already
established in test_layout_two_row.py.
"""

from zoneinfo import ZoneInfo

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball._card import MLBGameCard
from led_ticker_baseball._models import GameInfo

TZ = ZoneInfo("America/New_York")


def _card(layout="auto", **g_over):
    g = GameInfo(
        away_abbr="TB",
        home_abbr="BOS",
        away_score=0,
        home_score=10,
        state="live",
        inning="▼8",
        balls=1,
        strikes=2,
        outs=1,
        on_first=True,
        on_second=False,
        on_third=False,
        **g_over,
    )
    return MLBGameCard(
        game=g, team_abbr="BOS", tz=TZ, cfg_layout=layout, story_index=0, story_total=3
    )


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _smallsign():
    return HeadlessBackend(160, 16).create_canvas()


def test_auto_on_bigsign_holds_two_row_card():
    canvas, real = _bigsign()
    out, cursor = _card().draw(canvas)
    # held: cursor = canvas.width — the WRAPPER's LOGICAL width (256
    # physical // scale 4 = 64), matching the units the engine's
    # `cursor_pos > canvas.width` hold-vs-scroll check (core ticker.py)
    # actually compares against. Returning `real.width` (256) here was
    # Finding 1 of the final review: it always took the scroll branch.
    assert cursor == 64
    assert any(real.get_pixel(x, 31) != (0, 0, 0) for x in range(4, 252))  # divider


def test_auto_on_longboi_holds_scoreboard():
    canvas, real = _longboi()
    out, cursor = _card().draw(canvas)
    assert cursor == 128  # longboi: 512 physical // scale 4 = 128 logical


def test_ticker_on_bigsign_scrolls_hires_crawl():
    canvas, real = _bigsign()
    out, cursor = _card(layout="ticker").draw(canvas)
    assert cursor > 64  # logical advance width, engine will scroll


def test_scale1_delegates_to_legacy():
    real = _smallsign()
    out, cursor = _card(layout="ticker").draw(real)
    assert cursor > 0  # legacy SegmentMessage cursor contract


def test_frame_hooks_never_raise_before_first_draw():
    c = _card()
    c.advance_frame()
    c.pause_frame()
    c.resume_frame()
    c.reset_frame()


def test_scale1_two_row_final_series_text_uses_story_total():
    """Regression: the two_row legacy-delegation branch in `_legacy_story`
    must thread `self.story_total` through as `series_total_games` — not a
    hardcoded 1. `_compute_final_two_row` only emits the series-leader
    bottom-row text ("BOS leads 2-1" / "Tied 1-1") when
    `series_total_games > 1`, so a hardcoded 1 silently drops that text for
    every real multi-game series on a scale-1 sign with layout="two_row".
    """
    from led_ticker_baseball._two_row import _build_two_row_message

    game = GameInfo(
        away_abbr="TB",
        home_abbr="BOS",
        away_score=3,
        home_score=5,
        state="final",
        series_away_wins=1,
        series_home_wins=2,
    )
    card = MLBGameCard(
        game=game,
        team_abbr="BOS",
        tz=TZ,
        cfg_layout="two_row",
        story_index=0,
        story_total=3,
    )
    real = _smallsign()
    card.draw(real)  # scale=1 -> builds + caches the legacy two_row story

    # team_abbr="BOS" is the home side here, matching MLBScoreMonitor's
    # _series_sides mapping: series_wins/losses come from the monitored
    # team's own side (home -> series_home_wins/series_away_wins).
    expected = _build_two_row_message(
        game,
        "BOS",
        TZ,
        series_wins=2,
        series_losses=1,
        series_total_games=3,
    )

    card_bottom_texts = [
        text for text, _color in card._legacy_story("two_row").bottom_segments
    ]
    expected_bottom_texts = [text for text, _color in expected.bottom_segments]

    assert card_bottom_texts == expected_bottom_texts
    assert any("leads" in t for t in card_bottom_texts)
