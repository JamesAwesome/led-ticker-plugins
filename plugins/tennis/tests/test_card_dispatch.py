"""TennisMatchCard scale dispatch: held cursor = the wrapper's LOGICAL width
at scale>1; legacy text classes at scale 1; frame hooks forward."""

from led_ticker.plugin import SegmentMessage, unwrap_to_real

from led_ticker_tennis._card import TennisMatchCard
from led_ticker_tennis._scoreboard import TennisScoreboardMessage

from .conftest import TZ, lit, live_match


def _card(layout="auto", **over):
    return TennisMatchCard(
        match=live_match(**over), tz=TZ, cfg_layout=layout, story_index=0, story_total=3
    )


def test_auto_on_bigsign_holds_scoreboard(bigsign):
    _, cursor = _card().draw(bigsign)
    assert cursor == 64  # 256 physical // scale 4
    assert lit(unwrap_to_real(bigsign))


def test_auto_on_longboi_holds_scoreboard(longboi):
    _, cursor = _card().draw(longboi)
    assert cursor == 128


def test_ticker_on_bigsign_scrolls_hires_crawl(bigsign):
    _, cursor = _card(layout="ticker").draw(bigsign)
    assert cursor > 64  # logical advance + padding: the engine will scroll


def test_scale1_ticker_delegates_to_segment_message(smallsign):
    card = _card(layout="ticker")
    _, cursor = card.draw(smallsign)
    assert cursor > 0
    assert isinstance(card._legacy, SegmentMessage)


def test_scale1_scoreboard_delegates_to_legacy_board(smallsign):
    card = _card(layout="scoreboard")
    _, cursor = card.draw(smallsign)
    assert cursor == 160
    assert isinstance(card._legacy, TennisScoreboardMessage)
    assert lit(smallsign)


def test_legacy_story_is_cached_once(smallsign):
    card = _card(layout="ticker")
    card.draw(smallsign)
    first = card._legacy
    card.draw(smallsign)
    assert card._legacy is first


def test_frame_hooks_never_raise_before_or_after_draw(smallsign):
    c = _card(layout="ticker")
    c.advance_frame()
    c.pause_frame()
    c.resume_frame()
    c.reset_frame()
    c.draw(smallsign)
    c.advance_frame(visit_id=1)
    c.pause_frame()
    c.resume_frame()
    c.reset_frame()
    assert c._legacy is not None
