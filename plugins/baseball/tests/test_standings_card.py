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

        board.reset_frame()  # -> idx 1
        board.reset_frame()  # -> idx 2 % 2 == 0, wraps back to row 0

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
