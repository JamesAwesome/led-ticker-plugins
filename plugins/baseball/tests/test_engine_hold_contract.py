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
from led_ticker.plugin import ScaledCanvas, SegmentMessage, colors
from led_ticker.ticker import Ticker

from led_ticker_baseball._attendance_card import MLBAttendanceCard
from led_ticker_baseball._card import MLBGameCard
from led_ticker_baseball._models import GameInfo
from led_ticker_baseball._promo_card import MLBPromoCard
from led_ticker_baseball._standings_card import MLBStandingsBoard
from led_ticker_baseball._statcast_card import MLBStatcastCard
from led_ticker_baseball.attendance import AttendanceGame
from led_ticker_baseball.promotions import PromoInfo
from led_ticker_baseball.standings import TeamStanding
from led_ticker_baseball.statcast import StatRecord

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


def _longboi_frame() -> LedFrame:
    frame = LedFrame(backend=HeadlessBackend(512, 64))
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
    # Hardware finding (longboi promos, 2026-07-20, same defect here): the
    # advance used to include a 22-physical-px trailing spacer the engine's
    # stop compensation knows nothing about, so the rest position sat 22px
    # past flush-right (head clipped, dead right edge). The resting frame
    # must end flush-right, modulo the last glyph's advance slack.
    assert max(lit_cols) >= 256 - 14, (
        f"final frame's lit extent stops at x={max(lit_cols)} — the scroll "
        "stop overshot flush-right (a spacer baked into the advance?)"
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


def _promo(**over):
    kw = dict(
        name="Bobblehead Night",
        offer_type="Giveaway",
        presented_by="Chase",
        opponent_abbr="BOS",
        date_label="FRI JUL 18",
        time_label="7:05",
        am_pm="PM",
        game_date="2026-07-18",
    )
    kw.update(over)
    return PromoInfo(**kw)


def _promo_legacy():
    return SegmentMessage(
        [("TOR ", colors.RGB_WHITE), ("Bobblehead Night", colors.RGB_WHITE)],
        center=True,
    )


def test_held_promo_card_takes_hold_branch_no_phantom_scroll():
    """Same Finding-1 shape as MLBGameCard's held layouts (see module
    docstring), applied to MLBPromoCard: at scale>1 on a narrow (bigsign)
    panel, `layout="auto"` resolves to the held card
    (`layouts.resolve_promo_layout`), and the card must return the
    WRAPPER's LOGICAL width so the engine's real hold-vs-scroll check
    (`cursor_pos > canvas.width`, core ticker.py) takes the hold branch —
    zero scroll ticks — rather than phantom-scrolling a static card."""
    frame = _bigsign_frame()
    card = MLBPromoCard(
        promo=_promo(), story_index=0, story_total=1, legacy=_promo_legacy()
    )
    cursor_pos, final_pos, _ = asyncio.run(_run_visit(card, frame))
    assert cursor_pos == 64  # held cursor == the wrapper's LOGICAL width
    assert final_pos == 0  # never entered the scroll branch


def test_promo_crawl_scrolls_on_longboi_under_auto():
    """`layout="auto"` on a WIDE (longboi, 512 physical px) panel resolves
    to the hires crawl (`layouts.resolve_promo_layout`'s `phys_w >= 400`
    branch); an over-wide promo's logical cursor must overflow
    `canvas.width` so the engine actually takes the scroll branch
    (Finding-2 shape: a crawl that never gets fed back through the real
    engine can hide a stop-position bug — see module docstring)."""
    frame = _longboi_frame()
    card = MLBPromoCard(
        promo=_promo(name="Hawaiian Shirt & Beach Towel Giveaway"),
        story_index=0,
        story_total=1,
        legacy=_promo_legacy(),
    )
    cursor_pos, final_pos, _ = asyncio.run(_run_visit(card, frame))
    assert cursor_pos > 128  # overflowed the logical width -> scroll branch ran
    assert final_pos < 0  # did scroll (sanity check the branch actually ran)


def test_promo_crawl_short_line_holds_on_longboi():
    """The flip side of the trailing-spacer fix (hardware finding, longboi
    2026-07-20): a promo line that visibly fits the panel must be engine-
    HELD (and centered by the crawl renderer), not classified as
    overflowing by a spacer gap it doesn't paint. Uses a terse promo
    (~276 physical px — mirrors test_layout_promo_crawl.py's
    `_minimal_promo`); the default `_promo()` fixture measures ~521px and
    legitimately scrolls on a 512px panel either way."""
    frame = _longboi_frame()
    card = MLBPromoCard(
        promo=_promo(
            name="Cap Day", offer_type="", presented_by="", date_label="TODAY"
        ),
        story_index=0,
        story_total=1,
        legacy=_promo_legacy(),
    )
    cursor_pos, final_pos, _ = asyncio.run(_run_visit(card, frame))
    assert cursor_pos <= 128  # fits -> engine takes the hold branch
    assert final_pos == 0  # never entered the scroll branch


def test_promo_crawl_stop_position_lands_flush_right():
    """Hardware finding (longboi, 2026-07-20): the crawl's returned advance
    included its 22-physical-px trailing inter-story spacer, and core's
    stop compensation (`stop_pos = -(cursor_pos - canvas.width) + padding`,
    ticker.py) only adds back `widget.padding` — so every overflowing promo
    rested 22px past flush-right: head clipped off the left edge, ~24px of
    dead panel at the right ("the horizontal centering is off"). The
    resting frame must end flush-right, modulo the last glyph's advance
    slack."""
    frame = _longboi_frame()
    card = MLBPromoCard(
        promo=_promo(name="Hawaiian Shirt & Beach Towel Giveaway"),
        story_index=0,
        story_total=1,
        legacy=_promo_legacy(),
    )
    cursor_pos, final_pos, backend = asyncio.run(_run_visit(card, frame))
    assert cursor_pos > 128  # sanity: this fixture does overflow
    assert final_pos < 0  # sanity: the scroll branch actually ran
    back_buffer = backend._back_buffer
    lit_cols = {
        x for x, y in back_buffer._pixels if back_buffer.get_pixel(x, y) != (0, 0, 0)
    }
    assert lit_cols, "final displayed frame is entirely blank"
    assert max(lit_cols) >= 512 - 14, (
        f"final frame's lit extent stops at x={max(lit_cols)} — the scroll "
        "stop overshot flush-right (a spacer baked into the advance?)"
    )


def test_clock_ticks_advance_only_unpaused_and_survive_reset_frame():
    """Phase-3 plan's per-card clock lesson (flight precedent): `advance_frame`
    only ticks the clock while unpaused (a paused advance is transition
    compositing and must not tick it), and — unlike `MLBStandingsBoard`'s
    `_legacy_idx`, which DOES arm/consume across `reset_frame()` — this
    clock must be COMPLETELY untouched by `reset_frame()`, including the
    documented double-call-per-transitioned-visit (core calls it twice when
    a widget transition is configured). A clock that resets on section
    re-entry would snap the clipped name-scroll back to its start every
    time this promo card reappears."""
    card = MLBPromoCard(
        promo=_promo(), story_index=0, story_total=1, legacy=_promo_legacy()
    )

    card.advance_frame()
    card.advance_frame()
    assert card._clock_ticks == 2

    card.pause_frame()
    card.advance_frame()  # paused -> must not tick
    card.advance_frame()
    assert card._clock_ticks == 2

    card.resume_frame()
    card.advance_frame()
    assert card._clock_ticks == 3

    # reset_frame can fire twice per visit (core's documented shape) — the
    # clock must survive BOTH calls untouched.
    card.reset_frame()
    card.reset_frame()
    assert card._clock_ticks == 3

    card.advance_frame()
    assert card._clock_ticks == 4


def _statcast_legacy():
    return SegmentMessage([("Today · HR 451 ft", colors.RGB_WHITE)], center=True)


def test_held_statcast_long_card_takes_hold_branch_no_phantom_scroll():
    """Same Finding-1 shape as the other cards (see module docstring),
    applied to MLBStatcastCard: on a WIDE (longboi, 512 physical px) panel,
    `layout="auto"` resolves to the held long card
    (`layouts.resolve_statcast_layout`'s `phys_w >= _STATCAST_AUTO_WIDE_MIN_W`
    branch), and the card must return the WRAPPER's LOGICAL width so the
    engine's real hold-vs-scroll check (`cursor_pos > canvas.width`, core
    ticker.py) takes the hold branch — zero scroll ticks — rather than
    phantom-scrolling a static held card. A card that returned `real.width`
    (512) instead of `canvas.width` (128) would fail HERE even though its
    own unit test (`test_statcast_card_dispatch.py`) passes in isolation."""
    frame = _longboi_frame()
    card = MLBStatcastCard(
        record=StatRecord(
            value=451,
            person_id=1,
            team_abbr="PHI",
            exit_velo=114.2,
            launch_angle=28,
            distance=451,
            bb_type="fly_ball",
            result="HOME RUN",
            pitch_velo=94.1,
        ),
        player_name="RAMIREZ",
        legacy=_statcast_legacy(),
        story_index=0,
        story_total=1,
    )
    cursor_pos, final_pos, _ = asyncio.run(_run_visit(card, frame))
    assert cursor_pos == 128  # wrapper logical width -> hold branch
    assert final_pos == 0  # never scrolled


def test_held_statcast_big_card_takes_hold_branch():
    """Same Finding-1 shape as the long card, but on a BIGSIGN (256 physical
    px, scale 4 -> 64 logical). `cfg_layout="big"` forces the held big card;
    its returned cursor must be the wrapper's LOGICAL width (64) so the
    engine's real hold-vs-scroll check takes the hold branch. The big/long
    branches share the `return canvas, canvas.width` line, so this closes the
    coverage gap the long-card test left (the big renderer was untested at
    the engine level)."""
    frame = _bigsign_frame()
    card = MLBStatcastCard(
        record=StatRecord(
            value=451,
            person_id=1,
            team_abbr="PHI",
            exit_velo=114.2,
            launch_angle=28,
            distance=451,
            bb_type="fly_ball",
            result="HOME RUN",
            pitch_velo=94.1,
        ),
        player_name="RAMIREZ",
        legacy=_statcast_legacy(),
        story_index=0,
        story_total=1,
        cfg_layout="big",
    )
    cursor_pos, final_pos, _ = asyncio.run(_run_visit(card, frame))
    assert cursor_pos == 64  # wrapper logical width -> hold branch
    assert final_pos == 0  # never scrolled


def test_held_attendance_card_takes_hold_branch():
    """Same Finding-1 shape as MLBGameCard, MLBPromoCard, and MLBStatcastCard
    (see module docstring), applied to MLBAttendanceCard: on a WIDE (longboi,
    512 physical px) panel, `layout="auto"` resolves to the held attendance
    card, and the card must return the WRAPPER's LOGICAL width (128) so the
    engine's real hold-vs-scroll check (`cursor_pos > canvas.width`, core
    ticker.py) takes the hold branch — zero scroll ticks — rather than
    phantom-scrolling a static held card. A card that returned `real.width`
    (512) instead of `canvas.width` (128) would fail HERE even though its
    own unit test passes in isolation."""
    frame = _longboi_frame()
    card = MLBAttendanceCard(
        record=AttendanceGame(
            paid=46537,
            capacity=56000,
            avg=39442,
            venue="Dodger Stadium",
            home_abbr="LAD",
        ),
        legacy=SegmentMessage([("LAD 46,537", colors.RGB_WHITE)], center=True),
        story_index=0,
        story_total=1,
    )
    cursor_pos, final_pos, _ = asyncio.run(_run_visit(card, frame))
    assert cursor_pos == 128  # wrapper logical width -> hold branch
    assert final_pos == 0  # never scrolled
