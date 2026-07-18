"""tests/test_engine_hold_contract.py — drives core's REAL `Ticker`
engine (not a mock, not a translated-cursor unit test) against `MLBGameCard`.

This is the technique the final review used to catch Findings 1-2: the
branch's own tests (`test_card_dispatch.py`, `test_layout_crawl.py`)
asserted the CURSOR VALUES the card/crawl returned, in isolation — they
never fed those values back into the engine's actual hold-vs-scroll
decision (`Ticker._swap_and_scroll`, core `ticker.py`) or its scroll
stop-position math. A circular test can enshrine a bug (see the project's
"no circular golden tests" rule): both bugs shipped with 100% green tests
because the assertions matched the (wrong) code, not the engine's real
contract.

`led_ticker.ticker.Ticker`, `led_ticker.frame.LedFrame`, and
`led_ticker.backends.headless.HeadlessBackend` are core-internal imports
(not on `led_ticker.plugin.__all__`) — this is fine HERE: the AST import-
purity tripwire (`test_import_purity.py`) only walks `src/led_ticker_baseball`,
not `tests/`. Do not import these from `src/`.
"""

import asyncio
from zoneinfo import ZoneInfo

from led_ticker.backends.headless import HeadlessBackend
from led_ticker.frame import LedFrame
from led_ticker.plugin import ScaledCanvas
from led_ticker.ticker import Ticker

from led_ticker_baseball._card import MLBGameCard
from led_ticker_baseball._models import GameInfo
from led_ticker_baseball._standings_card import MLBStandingsBoard
from led_ticker_baseball.standings import TeamStanding

TZ = ZoneInfo("America/New_York")


def _live_game(**over):
    kw = dict(
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
    kw.update(over)
    return GameInfo(**kw)


def _bigsign_frame() -> LedFrame:
    frame = LedFrame(backend=HeadlessBackend(256, 64))
    frame.setup()
    return frame


async def _run_visit(card, frame, *, hold_time=0.0, scroll_speed=0.0):
    """Wrap a fresh clean canvas in the bigsign's real ScaledCanvas and run
    ONE full visit through the engine's actual `_swap_and_scroll` — the
    same code path `run_slideshow` drives in production. Returns
    (cursor_pos, final_pos, backend) so callers can inspect both the
    engine's hold-vs-scroll decision inputs and the physical pixels of the
    last-displayed frame (`backend._back_buffer`)."""
    real = frame.get_clean_canvas()
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    ticker = Ticker(
        monitors=[card], frame=frame, hold_time=hold_time, scroll_speed=scroll_speed
    )
    _, cursor_pos, final_pos = await ticker._swap_and_scroll(
        canvas, card, hold_time=hold_time
    )
    return cursor_pos, final_pos, frame.backend


def test_held_two_row_card_takes_hold_branch_no_phantom_scroll():
    """Finding 1: a held layout must make the engine take the HOLD branch,
    not the scroll branch. Before the fix, `MLBGameCard.draw` returned
    `real.width` (256) for held layouts; the engine's real hold-vs-scroll
    check (`cursor_pos > canvas.width`, `canvas` being the LOGICAL-width
    ScaledCanvas wrapper — 64 on a bigsign) always saw 256 > 64 and took
    the scroll branch, decrementing `pos` for ~190 ticks with a frozen
    (non-cursor-aware) held renderer on screen, then holding a SECOND time.

    `_swap_and_scroll`'s returned `final_pos` (the third tuple element) is
    the scroll loop's terminal `pos` — it only moves off 0 inside a scroll
    branch. Asserting it stays exactly 0 proves zero scroll ticks ran."""
    frame = _bigsign_frame()
    card = MLBGameCard(
        game=_live_game(),
        team_abbr="BOS",
        tz=TZ,
        cfg_layout="two_row",
        story_index=0,
        story_total=1,
    )
    cursor_pos, final_pos, _ = asyncio.run(_run_visit(card, frame))
    assert cursor_pos == 64  # held cursor == the wrapper's LOGICAL width
    assert final_pos == 0  # never entered the scroll branch


def test_crawl_stop_position_leaves_content_visible():
    """Finding 2: the crawl's engine-driven scroll must land flush-right
    with real content on screen, not ~192 physical px past flush-right on
    a near-blank final frame (the review's repro: lit x-extent 0..39 of
    0..255 — only the trailing bullet separator, everything else scrolled
    off into the dark).

    Runs an explicit `layout="ticker"` card (forces the crawl on a
    bigsign) through one full engine visit and inspects the PHYSICAL
    pixels of the frame that was actually swapped to the display
    (`backend._back_buffer` — the argument most recently passed to
    `backend.swap()`, i.e. what's on screen after the visit)."""
    frame = _bigsign_frame()
    card = MLBGameCard(
        game=_live_game(),
        team_abbr="BOS",
        tz=TZ,
        cfg_layout="ticker",
        story_index=0,
        story_total=1,
    )
    cursor_pos, final_pos, backend = asyncio.run(_run_visit(card, frame))
    assert cursor_pos > 64  # overflowed the logical width -> scroll branch ran
    assert final_pos < 0  # did scroll (sanity check the branch actually ran)

    back_buffer = backend._back_buffer
    lit_cols = {
        x for x, y in back_buffer._pixels if back_buffer.get_pixel(x, y) != (0, 0, 0)
    }
    assert lit_cols, "final displayed frame is entirely blank"
    assert max(lit_cols) > 39, (
        f"final frame's lit extent stops at x={max(lit_cols)} (review's "
        "blank-panel repro: content scrolled ~192 physical px past "
        "flush-right, leaving only the trailing bullet lit at x<=39)"
    )


def test_held_standings_board_takes_hold_branch_no_phantom_scroll():
    """Same Finding-1 shape as MLBGameCard's held layouts, applied to
    MLBStandingsBoard: at scale>1 the board is a HELD physical layout
    (`render_standings_board`) and must return the wrapper's LOGICAL
    width so the engine's real hold-vs-scroll check (`cursor_pos >
    canvas.width`, core ticker.py) takes the hold branch — zero scroll
    ticks — rather than phantom-scrolling a static board for ~190 ticks."""
    frame = _bigsign_frame()
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
    board = MLBStandingsBoard(division_name="AL EAST", rows=rows, legacy_rows=[])
    cursor_pos, final_pos, _ = asyncio.run(_run_visit(board, frame))
    assert cursor_pos == 64  # held cursor == the wrapper's LOGICAL width
    assert final_pos == 0  # never entered the scroll branch
