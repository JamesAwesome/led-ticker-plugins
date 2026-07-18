"""tests/test_standings_card.py — MLBStandingsBoard scale dispatch.

Mirrors test_card_dispatch.py's conventions (HeadlessBackend takes
(width, height) positionally; ScaledCanvas wraps it for scale>1 signs).
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball._standings_card import MLBStandingsBoard
from led_ticker_baseball.standings import TeamStanding, _build_standing_message


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _smallsign():
    return HeadlessBackend(160, 16).create_canvas()


def _lit(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _standing(name, wins, losses, rank, division_rank):
    return TeamStanding(
        name=name,
        wins=wins,
        losses=losses,
        rank=rank,
        games_back="-" if division_rank == 1 else "3.0",
        division_rank=division_rank,
        division_id=201,
    )


def _rows():
    return [
        _standing("Yankees", 45, 20, 1, 1),
        _standing("Red Sox", 40, 25, 5, 2),
    ]


class TestScaleGreaterThanOne:
    def test_draws_pixels_and_returns_logical_width(self):
        canvas, real = _bigsign()
        board = MLBStandingsBoard(division_name="AL EAST", rows=_rows(), legacy_rows=[])
        out, cursor = board.draw(canvas)
        assert out is canvas
        assert cursor == 64  # wrapper's LOGICAL width, not real.width (256)
        assert _lit(real), "board draw lit no pixels"

    def test_legacy_rows_ignored_at_scale_greater_than_one(self):
        # Even with legacy_rows populated, scale>1 always renders the
        # physical board — legacy is only a scale<=1 fallback.
        canvas, real = _bigsign()
        rows = _rows()
        legacy = [_build_standing_message(rows[0]), _build_standing_message(rows[1])]
        board = MLBStandingsBoard(
            division_name="AL EAST", rows=rows, legacy_rows=legacy
        )
        out, cursor = board.draw(canvas)
        assert cursor == 64


class TestScaleOneDelegatesToLegacy:
    def test_forwards_first_legacy_row_cursor(self):
        real = _smallsign()
        rows = _rows()
        legacy = [_build_standing_message(rows[0]), _build_standing_message(rows[1])]
        board = MLBStandingsBoard(
            division_name="AL EAST", rows=rows, legacy_rows=legacy
        )
        out, cursor = board.draw(real)
        assert out is real
        assert cursor > 0  # legacy SegmentMessage cursor contract

    def test_cycles_across_reset_frame(self):
        rows = _rows()
        legacy = [_build_standing_message(rows[0]), _build_standing_message(rows[1])]
        board = MLBStandingsBoard(
            division_name="AL EAST", rows=rows, legacy_rows=legacy
        )

        real1 = _smallsign()
        board.draw(real1)
        pixels1 = _lit(real1)

        board.reset_frame()

        real2 = _smallsign()
        board.draw(real2)
        pixels2 = _lit(real2)

        assert pixels1, "first legacy row lit no pixels"
        assert pixels2, "second legacy row lit no pixels"
        assert pixels1 != pixels2, "reset_frame did not advance the legacy row"

    def test_cycles_wrap_back_to_first_row(self):
        rows = _rows()
        legacy = [_build_standing_message(rows[0]), _build_standing_message(rows[1])]
        board = MLBStandingsBoard(
            division_name="AL EAST", rows=rows, legacy_rows=legacy
        )

        real_first = _smallsign()
        board.draw(real_first)
        first_pixels = _lit(real_first)

        board.reset_frame()  # visit 2 -> row 1
        real_second = _smallsign()
        board.draw(real_second)

        board.reset_frame()  # visit 3 -> wraps back to row 0
        real_wrapped = _smallsign()
        board.draw(real_wrapped)
        wrapped_pixels = _lit(real_wrapped)

        assert first_pixels == wrapped_pixels

    def test_empty_legacy_rows_never_raises(self):
        real = _smallsign()
        board = MLBStandingsBoard(division_name="AL EAST", rows=_rows(), legacy_rows=[])
        out, cursor = board.draw(real)
        assert out is real
        assert cursor == 0


class TestVisitIdempotentCycling:
    """Core calls reset_frame() TWICE per visit when a widget transition is
    configured (run_transition's _reset_presenter + _show_one's own reset —
    core documents the double reset as harmless, so the row counter must
    tolerate it). The advance must be idempotent per visit: reset arms a
    pending advance; the first UNPAUSED draw consumes it. Compositing draws
    (which run under pause_frame(), between the two resets) must not consume
    the pending advance — otherwise the double reset re-arms and the row
    sticks forever on even-length legacy_rows.
    """

    def _board(self):
        rows = _rows()
        legacy = [_build_standing_message(rows[0]), _build_standing_message(rows[1])]
        return MLBStandingsBoard(division_name="AL EAST", rows=rows, legacy_rows=legacy)

    def _row_pixels(self, board_action):
        real = _smallsign()
        board_action(real)
        return _lit(real)

    def test_first_visit_renders_row_zero(self):
        # Engine flow: reset_frame() fires at visit entry BEFORE the first
        # draw. The first visit must still render row 0, not row 1.
        no_reset = self._board()
        row0 = self._row_pixels(lambda c: no_reset.draw(c))

        engine_flow = self._board()
        engine_flow.reset_frame()
        first_visit = self._row_pixels(lambda c: engine_flow.draw(c))

        assert first_visit == row0

    def test_double_reset_collapses_to_one_advance(self):
        # Reference: single reset between draws -> row 1 on the second draw.
        single = self._board()
        self._row_pixels(lambda c: single.draw(c))  # visit 1: row 0
        single.reset_frame()
        row1 = self._row_pixels(lambda c: single.draw(c))

        # Double reset between draws must land on the SAME row 1 (the
        # reviewer's stuck repro: two advances on len-2 legacy_rows = stuck).
        double = self._board()
        self._row_pixels(lambda c: double.draw(c))  # visit 1: row 0
        double.reset_frame()
        double.reset_frame()
        second_visit = self._row_pixels(lambda c: double.draw(c))

        assert second_visit == row1

    def test_paused_compositing_draw_does_not_consume_advance(self):
        # run_transition pauses BOTH widgets, resets incoming, then draws it
        # repeatedly for compositing. Those paused draws must neither advance
        # the row nor burn the pending advance for the upcoming visit.
        board = self._board()
        row0 = self._row_pixels(lambda c: board.draw(c))  # visit 1: row 0

        board.pause_frame()
        board.reset_frame()  # run_transition's _reset_presenter
        composited = self._row_pixels(lambda c: board.draw(c))
        assert composited == row0  # paused draw: still the old row

        board.resume_frame()
        board.reset_frame()  # _show_one's own reset (the double)
        visit2 = self._row_pixels(lambda c: board.draw(c))
        assert visit2 != row0  # the visit itself advanced exactly once


class TestFrameHooks:
    def test_frame_hooks_never_raise_before_first_draw(self):
        board = MLBStandingsBoard(division_name="AL EAST", rows=_rows(), legacy_rows=[])
        board.advance_frame()
        board.pause_frame()
        board.resume_frame()
        board.reset_frame()

    def test_reset_frame_still_calls_super(self):
        # super().reset_frame() clears the frame-paused flag; verify our
        # override doesn't skip it.
        board = MLBStandingsBoard(division_name="AL EAST", rows=_rows(), legacy_rows=[])
        board.pause_frame()
        assert board._frame_paused is True
        board.reset_frame()
        assert board._frame_paused is True  # reset does NOT clear pause (base contract)


class TestFrameHookForwarding:
    """F3 regression (phase2-final-review.md): pre-branch, each legacy row
    WAS the engine-visited story, so the engine's per-tick advance_frame()
    animated its rainbow/color_cycle font_color. Post-branch the engine
    advances the BOARD's counters while the forwarded row's stayed frozen —
    rainbow rendered as a static gradient at scale<=1 under the default
    layout. Fix: forward advance_frame/pause_frame/resume_frame/reset_frame
    to whichever legacy row is currently active."""

    def _board(self):
        rows = _rows()
        legacy = [_build_standing_message(rows[0]), _build_standing_message(rows[1])]
        return MLBStandingsBoard(division_name="AL EAST", rows=rows, legacy_rows=legacy)

    def test_advance_frame_increments_active_row_counter(self):
        board = self._board()
        board.draw(_smallsign())  # visit 1: row 0 becomes active

        active = board._active_legacy_row()
        before = active._frame_count
        board.advance_frame()
        assert active._frame_count == before + 1

    def test_advance_frame_does_not_touch_the_inactive_row(self):
        board = self._board()
        board.draw(_smallsign())  # visit 1: row 0 active, row 1 dormant

        inactive_row = board.legacy_rows[1]
        before = inactive_row._frame_count
        board.advance_frame()
        assert inactive_row._frame_count == before

    def test_paused_advance_frame_does_not_increment_active_row(self):
        # Mirrors FrameAwareBase.advance_frame's own no-op-while-paused
        # contract: run_transition pauses widgets around its compositing
        # loop, so a (hypothetical) advance_frame call landing on a paused
        # board must not sneak the forwarded row's counter forward either.
        board = self._board()
        board.draw(_smallsign())  # visit 1: row 0 active
        active = board._active_legacy_row()
        before = active._frame_count

        board.pause_frame()
        board.advance_frame()
        assert active._frame_count == before  # paused advance: no increment

        board.resume_frame()
        board.advance_frame()
        assert active._frame_count == before + 1  # resumed: increments again

    def test_reset_frame_forwards_to_the_active_row(self):
        board = self._board()
        board.draw(_smallsign())  # visit 1: row 0 active
        active = board._active_legacy_row()
        active.advance_frame()
        active.advance_frame()
        assert active._frame_count == 2

        board.reset_frame()

        assert active._frame_count == 0  # forwarded reset zeroed the row
        assert board._pending_row_advance is True  # arm-flag behavior kept

    def test_hooks_never_raise_with_empty_legacy_rows(self):
        board = MLBStandingsBoard(division_name="AL EAST", rows=_rows(), legacy_rows=[])
        board.advance_frame()
        board.pause_frame()
        board.resume_frame()
        board.reset_frame()
