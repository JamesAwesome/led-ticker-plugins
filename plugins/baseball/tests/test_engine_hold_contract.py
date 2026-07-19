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


class _RecordingRow:
    """Wraps a legacy SegmentMessage; logs (division, row_idx) for every
    draw the BOARD forwards while unpaused. Paused draws are transition
    compositing (run_transition pauses both widgets for its whole loop),
    not what the viewer holds on — exclude them so the log captures only
    the row each VISIT actually settled on."""

    def __init__(self, inner, board, row_idx, log):
        self._inner = inner
        self._board = board
        self._row_idx = row_idx
        self._log = log

    def draw(self, canvas, cursor_pos=0, *, y_offset=0, font_color=None):
        if not self._board._frame_paused:
            self._log.append((self._board.division_name, self._row_idx))
        return self._inner.draw(
            canvas, cursor_pos, y_offset=y_offset, font_color=font_color
        )

    # MLBStandingsBoard forwards frame hooks to the active legacy row (F3,
    # phase2-final-review.md) — delegate through to the wrapped
    # SegmentMessage so this recording wrapper still behaves like a real
    # legacy row instead of raising AttributeError.
    def advance_frame(self, *, visit_id=None):
        self._inner.advance_frame(visit_id=visit_id)

    def pause_frame(self):
        self._inner.pause_frame()

    def resume_frame(self):
        self._inner.resume_frame()

    def reset_frame(self):
        self._inner.reset_frame()


def _recording_board(division_name, log):
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
    from led_ticker_baseball.standings import _build_standing_message

    board = MLBStandingsBoard(division_name=division_name, rows=rows, legacy_rows=[])
    board.legacy_rows.extend(
        _RecordingRow(_build_standing_message(r), board, i, log)
        for i, r in enumerate(rows)
    )
    return board


def test_scale1_row_cycling_survives_double_reset_per_visit():
    """Reviewer's P0-2 repro, inverted: with a non-cut widget transition,
    core calls reset_frame() TWICE per visit (run_transition's
    _reset_presenter + _show_one's own reset — documented as harmless, so
    the board's row counter must tolerate it). Before the fix, each visit
    advanced _legacy_idx by 2, so with 2 legacy rows per board the rendered
    row NEVER changed across visits ([1,1,1,...] stuck). Drive the REAL
    slideshow engine — real _build_then_enqueue producer, real _run_swap
    consumer, real run_transition — for 4 section cycles at scale 1 and
    assert BOTH rows of each board get held across visits."""
    from led_ticker.config import TransitionConfig
    from led_ticker.transitions import WipeLeft

    frame = LedFrame(backend=HeadlessBackend(160, 16))
    frame.setup()

    log: list[tuple[str, int]] = []
    board_a = _recording_board("AL EAST", log)
    board_b = _recording_board("NL WEST", log)

    ticker = Ticker(
        monitors=[board_a, board_b],
        frame=frame,
        hold_time=0.0,
        scroll_speed=0.0,
        notif_queue=asyncio.Queue(maxsize=2),
        # transition_fps drives run_transition's per-frame sleep
        # (scroll_speed = 1/fps); high fps keeps the full-width wipe
        # sweeps from dominating test wall-time.
        transition_config=TransitionConfig(
            type="wipe_left", duration=0.05, transition_fps=1000.0
        ),
        transition_fn=WipeLeft(),
    )
    asyncio.run(ticker.run_slideshow(loop_count=4))

    rows_per_board: dict[str, set[int]] = {}
    for division, row_idx in log:
        rows_per_board.setdefault(division, set()).add(row_idx)

    assert set(rows_per_board) == {"AL EAST", "NL WEST"}
    for division, rendered in rows_per_board.items():
        assert rendered == {0, 1}, (
            f"{division}: only row(s) {sorted(rendered)} ever held across 4 "
            "section cycles — the double reset per transitioned visit is "
            "collapsing to an even advance and sticking the row"
        )
