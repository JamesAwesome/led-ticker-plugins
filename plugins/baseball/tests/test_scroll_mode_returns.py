"""Hi-res `draw()` returns an ABSOLUTE end (`cursor_pos + width`), the core
contract (`widgets/message.py`). Core's `ticker` / `one_at_a_time` loops pop
a widget only when that end goes below 0; a cursor-relative return never
does, so the section wedged on its first baseball card forever.

`led_ticker.ticker.Ticker` is a core-internal import — fine in tests (the
import-purity tripwire walks `src/` only)."""

import asyncio
import unittest.mock as mock
from zoneinfo import ZoneInfo

import pytest
from led_ticker.plugin import HeadlessBackend, ScaledCanvas, SegmentMessage, colors
from led_ticker.ticker import Ticker

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._attendance_card import MLBAttendanceCard
from led_ticker_baseball._card import MLBGameCard
from led_ticker_baseball._hires_line import HiresLine
from led_ticker_baseball._models import GameInfo
from led_ticker_baseball._promo_card import MLBPromoCard
from led_ticker_baseball._standings_card import MLBStandingsBoard
from led_ticker_baseball._statcast_card import MLBStatcastCard
from led_ticker_baseball.attendance import AttendanceGame
from led_ticker_baseball.promotions import PromoInfo
from led_ticker_baseball.standings import TeamStanding
from led_ticker_baseball.statcast import StatRecord

TZ = ZoneInfo("America/New_York")


def _legacy(text="x"):
    return SegmentMessage([(text, colors.RGB_WHITE)], center=True)


def _game(layout="auto"):
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
    )
    return MLBGameCard(game=g, team_abbr="BOS", tz=TZ, cfg_layout=layout)


def _promo(layout="auto"):
    p = PromoInfo(
        name="Bobblehead Night",
        offer_type="Giveaway",
        presented_by="Chase",
        opponent_abbr="BOS",
        date_label="FRI JUL 18",
        time_label="7:05",
        am_pm="PM",
        game_date="2026-07-18",
    )
    return MLBPromoCard(
        promo=p, story_index=0, story_total=1, legacy=_legacy(), cfg_layout=layout
    )


def _standings():
    rows = [
        TeamStanding(
            name="Yankees",
            wins=45,
            losses=20,
            rank=1,
            games_back="-",
            division_rank=1,
            division_id=201,
        ),
        TeamStanding(
            name="Red Sox",
            wins=40,
            losses=25,
            rank=5,
            games_back="5.0",
            division_rank=2,
            division_id=201,
        ),
    ]
    return MLBStandingsBoard(division_name="AL EAST", rows=rows, legacy_rows=[])


def _statcast():
    rec = StatRecord(
        value=451,
        person_id=1,
        team_abbr="PHI",
        exit_velo=114.2,
        launch_angle=28,
        distance=451,
        bb_type="fly_ball",
        result="HOME RUN",
        pitch_velo=94.1,
        pitch_name="SL",
    )
    return MLBStatcastCard(record=rec, player_name="RAMIREZ", legacy=_legacy())


def _attendance():
    rec = AttendanceGame(
        paid=46537, capacity=56000, avg=39442, venue="Dodger Stadium", home_abbr="LAD"
    )
    return MLBAttendanceCard(record=rec, legacy=_legacy())


def _line():
    segs = [("NYY · Yankee Stadium", pal.IDENT)]
    return HiresLine(segments=segs, legacy=SegmentMessage(segs))


HELD = {
    "game": _game,
    "promo": lambda: _promo("card"),
    "standings": _standings,
    "statcast": _statcast,
    "attendance": _attendance,
    "hires_line": _line,
}
CRAWLS = {
    "game_crawl": lambda: _game("ticker"),
    "promo_crawl": lambda: _promo("ticker"),
}


def _fresh(width):
    real = HeadlessBackend(width, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _cols(real):
    return {x for (x, _y), v in real._pixels.items() if v != (0, 0, 0)}


@pytest.mark.parametrize(
    "make", [*HELD.values(), *CRAWLS.values()], ids=[*HELD, *CRAWLS]
)
async def test_one_at_a_time_advances_past_hires_cards(make, monkeypatch):
    real_sleep = asyncio.sleep

    async def _zero_sleep(_s):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _zero_sleep)
    canvas, _ = _fresh(256)
    frame = mock.Mock()
    frame.swap.side_effect = lambda r: r
    queue: asyncio.Queue = asyncio.Queue()
    for w in (make(), make(), None):
        queue.put_nowait(w)
    ticker = Ticker(monitors=[], frame=frame, notif_queue=queue, scroll_speed=0)
    await asyncio.wait_for(ticker._scroll_one_by_one(canvas), 1.5)
    assert queue.empty()


@pytest.mark.parametrize("width", [256, 512])
@pytest.mark.parametrize("make", HELD.values(), ids=HELD)
def test_held_end_is_absolute_and_paints_shifted(make, width):
    c0, r0 = _fresh(width)
    _, end0 = make().draw(c0)
    assert end0 == c0.width  # slideshow (cursor 0) unchanged
    cols0 = _cols(r0)
    assert any(x >= 160 for x in cols0)

    c, r = _fresh(width)
    _, end = make().draw(c, -40)
    assert end == -40 + c.width
    assert _cols(r) == {x - 160 for x in cols0 if x >= 160}


@pytest.mark.parametrize("make", CRAWLS.values(), ids=CRAWLS)
def test_crawl_end_is_absolute(make):
    c0, _ = _fresh(256)
    _, end0 = make().draw(c0)
    c, _ = _fresh(256)
    _, end = make().draw(c, -40)
    assert end == -40 + end0


def test_scale1_standings_without_rows_still_leaves():
    real = HeadlessBackend(160, 16).create_canvas()
    _, end = _standings().draw(real, -1)
    assert end < 0


def test_shifted_real_subfill_shifts_and_clips():
    from led_ticker_baseball._paint import ShiftedReal, shift_canvas

    real = HeadlessBackend(16, 4).create_canvas()
    ShiftedReal(real, -2).SubFill(0, 0, 4, 9, 255, 0, 0)
    assert _cols(real) == {0, 1}
    ShiftedReal(real, 20).SubFill(0, 0, 4, 4, 255, 0, 0)  # wholly off-panel
    assert _cols(real) == {0, 1}
    canvas, _ = _fresh(256)
    assert shift_canvas(canvas, 0) is canvas


def _short_promo_crawl():
    p = PromoInfo(
        name="Cap Day",
        offer_type="",
        presented_by="",
        opponent_abbr="BOS",
        date_label="TODAY",
        time_label="7:05",
        am_pm="PM",
        game_date="2026-07-18",
    )
    return MLBPromoCard(
        promo=p, story_index=0, story_total=1, legacy=_legacy(), cfg_layout="ticker"
    )


FITTING = {"game_crawl": lambda: _game("ticker"), "promo_crawl": _short_promo_crawl}


@pytest.mark.parametrize("make", FITTING.values(), ids=FITTING)
def test_fitting_crawl_end_covers_its_centred_paint(make):
    """A crawl that fits is painted CENTRED across the panel, so its end
    must be the panel's right edge, not `cursor + run + padding` (which
    let core pop it / butt the next widget into it with its tail lit)."""
    width = 128  # longboi logical
    for cursor in (0, -40, -(width - 1)):
        c, real = _fresh(512)
        _, end = make().draw(c, cursor)
        assert end == cursor + width
        cols = _cols(real)
        assert cursor != 0 or cols
        assert not cols or max(cols) < end * 4


def test_shifted_real_drops_pixels_outside_the_cards_own_box():
    from led_ticker_baseball._paint import ShiftedReal

    real = HeadlessBackend(16, 4).create_canvas()
    s = ShiftedReal(real, 4)
    s.SetPixel(-1, 0, 255, 0, 0)  # outside the card's own box: dropped
    s.SubFill(-3, 0, 5, 1, 255, 0, 0)  # clamped to pre-shift [0, 2)
    assert _cols(real) == {4, 5}
