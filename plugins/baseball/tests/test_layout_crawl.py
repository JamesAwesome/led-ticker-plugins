"""tests/test_layout_crawl.py — hires text asserted by EXTENT only (never
exact freetype pins). GameInfo fixtures mirror the sibling renderers.

HeadlessBackend takes (width, height) positionally (see
led_ticker/backends/headless.py) — there is no rows/cols/chain_length kwarg
surface (that's an RgbMatrixBackend shape). HeadlessCanvas has no
iter_coords()/iter_pixels(); its supported read surface is get_pixel(x, y)
plus the `_pixels` dict it serializes from — sibling plugin tests
(test_layout_two_row.py, test_paint.py, test_primitives.py) already reach
into `_pixels` directly for "any lit pixel" checks, so we follow that
precedent here.

`render_crawl`'s `cursor_pos` and return value are LOGICAL (same units as
`canvas.width` on the bigsign wrapper: 64), NOT physical — see the
function's module docstring. A cursor offset of N logical px shifts
content N*scale (4 on bigsign) physical px; width assertions compare
against the wrapper's logical width (64), not the real canvas's physical
width (256).
"""

from zoneinfo import ZoneInfo

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball._models import GameInfo
from led_ticker_baseball.layouts.crawl import render_crawl

TZ = ZoneInfo("America/New_York")


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


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


def _lit_cols(real):
    return {x for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}


def test_advance_has_no_trailing_spacer():
    """Hardware finding (longboi promos, 2026-07-20 — same defect in this
    scores crawl): a spacer gap baked into the returned advance makes the
    engine's scroll stop overshoot by exactly that spacer (core's
    `stop_pos = -(cursor - width) + padding` compensates only for
    `widget.padding`), resting the line head-clipped with dead panel at the
    right. Inter-story spacing rides `MLBGameCard.padding` through that
    same compensation instead. Painted extent and returned advance may
    differ only by glyph bearings + ceil-to-logical rounding (≤ 14 physical
    px). Extent is translation-immune, so held-centering can't mask it —
    hence the oversized canvas (nothing clips)."""
    real = HeadlessBackend(2048, 64).create_canvas()
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    w = render_crawl(canvas, _live_game(), TZ, 0)
    cols = sorted(_lit_cols(real))
    extent = cols[-1] - cols[0] + 1
    assert 0 <= w * 4 - extent <= 14


def test_returns_positive_width_and_draws_at_cursor_zero():
    canvas, real = _bigsign()
    w = render_crawl(canvas, _live_game(), TZ, 0)
    assert w > 64  # live line is wider than bigsign's LOGICAL width (64)
    assert _lit_cols(real)


def test_cursor_offsets_content():
    canvas, real = _bigsign()
    render_crawl(canvas, _live_game(), TZ, 0)
    first = min(_lit_cols(real))
    canvas2, real2 = _bigsign()
    # A small LOGICAL offset (-3 logical = -12 physical at scale 4 — well
    # inside the first segment's own width, so the comparison can't cross
    # into a wholly different glyph's bearing — a large offset can fully
    # cull the first segment and expose the NEXT segment's ink, whose
    # left-side bearing is font-dependent and would make this an
    # inadvertent freetype pin) scrolled left: leftmost lit col moves left
    # or clips at 0.
    render_crawl(canvas2, _live_game(), TZ, -3)
    assert min(_lit_cols(real2)) <= first


def test_positive_cursor_shifts_content_right():
    """Load-bearing engine-scroll contract test: a mutation that ignores
    cursor_pos (x = 0) must FAIL here. A positive LOGICAL offset (15 logical
    = 60 physical at scale 4) keeps the first glyph fully on-canvas (no
    left-edge clipping, no glyph-boundary crossing), so every lit column
    shifts right by exactly the physical equivalent of the offset —
    asserted as a strict >= bound (no exact freetype pin needed; the shift
    is pure translation of whatever ink the font produced at cursor 0)."""
    canvas, real = _bigsign()
    render_crawl(canvas, _live_game(), TZ, 0)
    cols0 = _lit_cols(real)
    canvas2, real2 = _bigsign()
    render_crawl(canvas2, _live_game(), TZ, 15)
    cols15 = _lit_cols(real2)
    assert cols0 != cols15
    assert min(cols15) >= min(cols0) + 50


def test_width_is_cursor_independent():
    canvas, _ = _bigsign()
    w0 = render_crawl(canvas, _live_game(), TZ, 0)
    canvas2, _ = _bigsign()
    w1 = render_crawl(canvas2, _live_game(), TZ, -100)
    assert w0 == w1


def test_final_game_has_no_bases_diamonds():
    canvas, real = _bigsign()
    g = _live_game(state="final", inning=None)
    w = render_crawl(canvas, g, TZ, 0)
    assert w > 0


def test_preview_with_start_time_renders_time_not_ppd():
    """Regression: GameInfo.postpone_tag DEFAULTS to "PPD" (and the parser
    sets it for every game), so a truthiness gate on the tag made every
    ordinary preview render "PPD" instead of its start time. The label
    branch must gate on state == "postponed", not tag truthiness."""
    from datetime import datetime

    start = datetime(2026, 7, 17, 19, 10, tzinfo=TZ)
    common = dict(state="preview", inning=None, away_score=None, home_score=None)
    canvas_p, real_p = _bigsign()
    render_crawl(canvas_p, _live_game(**common, start_time=start), TZ, 0)
    canvas_x, real_x = _bigsign()
    render_crawl(
        canvas_x,
        _live_game(**{**common, "state": "postponed"}, start_time=start),
        TZ,
        0,
    )
    assert _lit_cols(real_p) != _lit_cols(real_x)


def test_y_offset_shifts_content():
    canvas, real = _bigsign()
    render_crawl(canvas, _live_game(), TZ, 0, y_offset=8)
    rows = {y for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}
    canvas2, real2 = _bigsign()
    render_crawl(canvas2, _live_game(), TZ, 0)
    rows2 = {y for x, y in real2._pixels if real2.get_pixel(x, y) != (0, 0, 0)}
    assert min(rows) - min(rows2) == 32


class TestVerticalCentering:
    """Hardware finding (longboi, 2026-07-18): the crawl rendered ~10px low.

    The prototype's ycP treats y as the glyphs' visual top; our hires()
    treats it as the ascent-box top (baseline = y + ascent), so the port
    must back the ascent out. Guard: the lit row band of a text-only
    (final-state) render must center on the panel's vertical middle.
    """

    def _midpoint(self, width):
        real = HeadlessBackend(width, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        g = _live_game(state="final", inning=None)
        render_crawl(canvas, g, TZ, 0)
        rows = sorted({y for (_x, y) in real._pixels})
        return (rows[0] + rows[-1]) / 2

    def test_longboi_crawl_text_band_is_vertically_centered(self):
        assert abs(self._midpoint(512) - 31.5) <= 2.5

    def test_bigsign_crawl_text_band_is_vertically_centered(self):
        assert abs(self._midpoint(256) - 31.5) <= 2.5


class TestHorizontalCentering:
    """Hardware finding (2026-07-18, PR #70 validation): a game line that FITS
    the panel is engine-held — but rendered flush-left, unlike the legacy
    rows which center held content. render_crawl centers when the engine
    will hold (total logical advance + hold_padding <= logical width) and
    keeps the scrolling left-origin otherwise.
    """

    def _mid(self, real):
        cols = sorted({x for (x, _y) in real._pixels})
        return (cols[0] + cols[-1]) / 2

    def test_short_line_centers_on_longboi(self):
        real = HeadlessBackend(512, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        g = _live_game(state="final", inning=None)  # short: fits 512
        render_crawl(canvas, g, TZ, 0, hold_padding=6)
        assert abs(self._mid(real) - 255.5) <= 14  # centered

    def test_long_line_keeps_left_origin(self):
        real = HeadlessBackend(256, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        g = _live_game()  # live line: wider than bigsign, will scroll
        render_crawl(canvas, g, TZ, 0, hold_padding=6)
        cols = sorted({x for (x, _y) in real._pixels})
        assert cols[0] <= 4  # starts at the left edge, not centered

    def test_centering_ignores_cursor_when_held(self):
        real = HeadlessBackend(512, 64).create_canvas()
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        g = _live_game(state="final", inning=None)
        w = render_crawl(canvas, g, TZ, 0, hold_padding=6)
        assert w + 6 <= canvas.width  # sanity: this line genuinely holds
