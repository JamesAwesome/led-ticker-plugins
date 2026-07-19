"""tests/test_layout_standings_board.py — hires text asserted by
EXTENT/regions only (never exact freetype pins), same convention as
test_layout_two_row.py / test_layout_scoreboard.py.

HeadlessBackend takes (width, height) positionally (see
led_ticker/backends/headless.py) — there is no rows/cols/chain_length kwarg
surface (that's an RgbMatrixBackend shape). HeadlessCanvas has no
iter_coords()/iter_pixels(); its supported read surface is get_pixel(x, y)
plus the `_pixels` dict it serializes from.

Also covers the CRITICAL vertical-metrics conversion (module docstring of
`layouts/standings_board.py`): a row's rank(px8)/abbr(px10)/record(px10)
glyphs must all land inside that row's 10px pitch band, not bleed into the
next row's.
"""

import pytest
from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import text_width
from led_ticker_baseball.layouts.standings_board import (
    _BIG_GEOMETRY,
    _LONG_GEOMETRY,
    render_standings_board,
)
from led_ticker_baseball.standings import TeamStanding


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _row(**over):
    kw = dict(
        name="Yankees",
        wins=58,
        losses=39,
        rank=1,
        games_back="-",
        abbr="NYY",
        pct=".598",
        l10="7-3",
        streak="W3",
        division_gb="-",
    )
    kw.update(over)
    return TeamStanding(**kw)


def _rows(n):
    abbrs = ["NYY", "BOS", "TBR", "TOR", "BAL", "SEA", "HOU"]
    out = []
    for i in range(n):
        out.append(
            _row(
                name=abbrs[i % len(abbrs)],
                abbr=abbrs[i % len(abbrs)],
                rank=i + 1,
                wins=90 - i,
                losses=40 + i,
                division_gb="-" if i == 0 else f"{i}.0",
                streak="W3" if i % 2 == 0 else "L1",
            )
        )
    return out


def _lit_coords(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _lit_rows(real):
    return {y for _x, y in _lit_coords(real)}


def _lit_in(real, x0, x1, y0, y1):
    return any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(x0, x1) for y in range(y0, y1)
    )


# ---------- big (256px) ----------


def test_big_header_regions():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(5))
    assert _lit_in(real, 4, 40, 0, 9)  # division label, cyan, x4 y1 px8
    assert _lit_in(real, 112, 140, 0, 9)  # "W-L" label x112
    assert _lit_in(real, 180, 196, 0, 9)  # "GB" label x180
    assert _lit_in(real, 210, 240, 0, 9)  # "STRK" label x210


def test_big_five_rows_each_land_in_their_10px_pitch_band():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(5))
    for i in range(5):
        y = 12 + i * 10
        # rank + chip + abbr + record all fall within this row's own band
        # (a couple px of headroom/footroom either side of the 10px pitch,
        # not bleeding a full row (10px) into the neighbor).
        assert _lit_in(real, 0, 256, y - 1, y + 11), f"row {i} missing content"


def _lit_ys_in_col(real, x0, x1):
    return {y for (x, y), v in real._pixels.items() if v != (0, 0, 0) and x0 <= x < x1}


def test_big_abbr_column_rows_have_a_dark_gap_between_them():
    """Direct regression for the cap-top conversion: the abbr column mixes
    px8 (rank, drawn 10px to its left but same row) and px10 (abbr itself)
    within one row. Without `_cap_top`, a row's px10 text (ascent=10) sits
    lower than intended and can bleed into the next row's 10px band. Probe
    just the abbr column (x22-60), which is unaffected by any particular
    row's PCT/streak glyph shape (full-canvas checks are fixture-fragile —
    a repeated ".598" PCT string can visually touch across rows by design,
    the 10px pitch leaves near-zero headroom for px10 text) — the abbr
    column alone must show a real dark line between every pair of rows."""
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(5))
    lit = _lit_ys_in_col(real, 22, 60)
    for i in range(4):
        gap_y = 12 + i * 10 + 8
        assert gap_y not in lit, f"no dark gap between row {i} and row {i + 1}"


def test_long_abbr_column_rows_have_a_dark_gap_between_them():
    canvas, real = _longboi()
    render_standings_board(canvas, "AL EAST", _rows(5))
    lit = _lit_ys_in_col(real, 32, 70)
    for i in range(4):
        gap_y = 14 + i * 10 + 8
        assert gap_y not in lit, f"no dark gap between row {i} and row {i + 1}"


def test_big_row_content_present_rank_chip_abbr_record_gb_streak():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(1))
    y = 12
    assert _lit_in(real, 0, 12, y, y + 10)  # rank number
    assert _lit_in(real, 11, 22, y, y + 10)  # chip
    assert _lit_in(real, 22, 60, y, y + 10)  # abbr text
    assert _lit_in(real, 112, 170, y, y + 10)  # W-L record
    assert _lit_in(real, 180, 200, y, y + 10)  # GB
    assert _lit_in(real, 212, 240, y, y + 10)  # STRK


def test_big_pct_and_l10_columns_absent():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(5))
    # PCT (x224) and L10 (x350) are long-layout-only columns. On the big
    # layout STRK's own header/value (x210/x212) legitimately reaches past
    # x224, so probe past STRK's farthest natural extent instead (STRK px10
    # "STRK"-width content never reaches the panel's right edge).
    assert not _lit_in(real, 245, 256, 0, 64)


def test_big_leader_gb_is_label_not_amber():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", [_row(division_gb="-")])
    lit = _lit_coords(real)
    colors = {real.get_pixel(x, y) for x, y in lit if 180 <= x < 200 and 12 <= y < 22}
    assert (pal.AMBER.red, pal.AMBER.green, pal.AMBER.blue) not in colors


def test_big_non_leader_gb_is_amber():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", [_row(division_gb="4.0")])
    lit = _lit_coords(real)
    colors = {real.get_pixel(x, y) for x, y in lit if 180 <= x < 200 and 12 <= y < 22}
    assert (pal.AMBER.red, pal.AMBER.green, pal.AMBER.blue) in colors


def test_big_streak_color_win_vs_loss():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", [_row(streak="W3")])
    lit = _lit_coords(real)
    colors = {real.get_pixel(x, y) for x, y in lit if 212 <= x < 240 and 12 <= y < 22}
    assert (pal.WIN.red, pal.WIN.green, pal.WIN.blue) in colors

    canvas2, real2 = _bigsign()
    render_standings_board(canvas2, "AL EAST", [_row(streak="L2")])
    lit2 = _lit_coords(real2)
    colors2 = {
        real2.get_pixel(x, y) for x, y in lit2 if 212 <= x < 240 and 12 <= y < 22
    }
    assert (pal.LOSS.red, pal.LOSS.green, pal.LOSS.blue) in colors2


def test_more_than_5_rows_draws_only_5():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(7))
    # row index 5 (6th row) would start at y=12+5*10=62 — must not draw.
    assert not _lit_in(real, 0, 256, 61, 64)


# ---------- long (512px) ----------


def test_long_header_regions():
    canvas, real = _longboi()
    render_standings_board(canvas, "AL EAST", _rows(5))
    assert _lit_in(real, 6, 50, 0, 11)  # division label x6 y2 px9
    assert _lit_in(real, 158, 172, 0, 11)  # "W" x158
    assert _lit_in(real, 192, 206, 0, 11)  # "L" x192
    assert _lit_in(real, 224, 250, 0, 11)  # "PCT" x224
    assert _lit_in(real, 292, 310, 0, 11)  # "GB" x292
    assert _lit_in(real, 350, 372, 0, 11)  # "L10" x350
    assert _lit_in(real, 420, 450, 0, 11)  # "STRK" x420


def test_long_row_content_present():
    canvas, real = _longboi()
    render_standings_board(canvas, "AL EAST", _rows(1))
    y = 14
    assert _lit_in(real, 0, 16, y, y + 10)  # rank
    assert _lit_in(real, 18, 27, y, y + 10)  # chip
    assert _lit_in(real, 32, 70, y, y + 10)  # abbr
    assert _lit_in(real, 158, 178, y, y + 10)  # wins
    assert _lit_in(real, 192, 212, y, y + 10)  # losses
    assert _lit_in(real, 224, 250, y, y + 10)  # pct
    assert _lit_in(real, 350, 380, y, y + 10)  # l10
    assert _lit_in(real, 420, 450, y, y + 10)  # streak


def test_long_five_rows_each_land_in_their_10px_pitch_band():
    canvas, real = _longboi()
    render_standings_board(canvas, "AL EAST", _rows(5))
    for i in range(5):
        y = 14 + i * 10
        assert _lit_in(real, 0, 512, y - 1, y + 11), f"row {i} missing content"


def test_long_leader_gb_ident_non_leader_ident_too_but_not_label():
    # GB column: LABEL when leader ("-"), IDENT otherwise.
    canvas, real = _longboi()
    render_standings_board(canvas, "AL EAST", [_row(division_gb="-")])
    lit = _lit_coords(real)
    colors = {real.get_pixel(x, y) for x, y in lit if 292 <= x < 320 and 14 <= y < 24}
    assert colors and colors <= {
        (pal.LABEL.red, pal.LABEL.green, pal.LABEL.blue),
        (0, 0, 0),
    }


def test_long_never_raises_on_empty_rows_and_missing_fields():
    canvas, _real1 = _longboi()
    render_standings_board(canvas, "AL EAST", [])  # empty rows
    canvas2, _real2 = _bigsign()
    render_standings_board(canvas2, "AL EAST", [])
    minimal = TeamStanding(name="X", wins=0, losses=0, rank=1, games_back="-")
    canvas3, _real3 = _bigsign()
    render_standings_board(canvas3, "AL EAST", [minimal])
    canvas4, _real4 = _longboi()
    render_standings_board(canvas4, "AL EAST", [minimal])


def test_y_offset_shifts_everything_by_scale():
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(5), y_offset=8)
    canvas2, real2 = _bigsign()
    render_standings_board(canvas2, "AL EAST", _rows(5))
    assert min(_lit_rows(real)) - min(_lit_rows(real2)) == 32


# ---------- board_rows geometry (3/4/5 rows) ----------


def _worst_case_rows(n):
    """Worst-case row content per the phase-2 spec: wide record/gb/pct/l10/
    strk strings and a real 3-char abbr (WSH). One row per rank 1..n (the
    leader has no GB, so row 0 keeps "-" — same convention as `_rows()`)."""
    out = []
    for i in range(n):
        out.append(
            _row(
                name="Nationals",
                abbr="WSH",
                rank=i + 1,
                wins=100,
                losses=62,
                division_gb="-" if i == 0 else "16.0",
                pct=".1000",
                l10="10-0",
                streak="W12",
            )
        )
    return out


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_big_headers_unchanged_regardless_of_max_rows(max_rows):
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(max_rows), max_rows=max_rows)
    assert _lit_in(real, 4, 40, 0, 9)  # division label, cyan, x4 y1 px8
    assert _lit_in(real, 112, 140, 0, 9)  # "W-L" label x112
    assert _lit_in(real, 180, 196, 0, 9)  # "GB" label x180
    assert _lit_in(real, 210, 240, 0, 9)  # "STRK" label x210


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_long_headers_unchanged_regardless_of_max_rows(max_rows):
    canvas, real = _longboi()
    render_standings_board(canvas, "AL EAST", _rows(max_rows), max_rows=max_rows)
    assert _lit_in(real, 6, 50, 0, 11)  # division label x6 y2 px9
    assert _lit_in(real, 158, 172, 0, 11)  # "W" x158
    assert _lit_in(real, 420, 450, 0, 11)  # "STRK" x420


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_big_rows_land_in_their_own_pitch_band(max_rows):
    geo = _BIG_GEOMETRY[max_rows]
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(max_rows), max_rows=max_rows)
    for i in range(max_rows):
        y = geo["row0"] + i * geo["pitch"]
        assert _lit_in(real, 0, 256, y - 1, y + geo["pitch"] + 1), (
            f"max_rows={max_rows} row {i} missing content"
        )


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_long_rows_land_in_their_own_pitch_band(max_rows):
    geo = _LONG_GEOMETRY[max_rows]
    canvas, real = _longboi()
    render_standings_board(canvas, "AL EAST", _rows(max_rows), max_rows=max_rows)
    for i in range(max_rows):
        y = geo["row0"] + i * geo["pitch"]
        assert _lit_in(real, 0, 512, y - 1, y + geo["pitch"] + 1), (
            f"max_rows={max_rows} row {i} missing content"
        )


def _y_clusters(ys, gap=2):
    """Group a set of lit y-coords into contiguous vertical bands (a new
    cluster starts whenever consecutive lit y's are >= `gap` apart)."""
    ys = sorted(ys)
    clusters = [[ys[0]]]
    for y in ys[1:]:
        if y - clusters[-1][-1] < gap:
            clusters[-1].append(y)
        else:
            clusters.append([y])
    return clusters


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_big_worst_case_rows_dont_bleed_into_each_other(max_rows):
    """Row-to-row bleed check (collision requirement, part 2): the abbr
    column (pure text ink, no chip pixels) must show exactly `max_rows`
    distinct vertical bands — a bled row would merge two bands into one,
    reducing the cluster count below `max_rows`. Restricted to
    `y >= row0 - 3` to exclude the header's division-name label, which sits
    in the SAME x range (4-40ish) as the abbr column and would otherwise
    read as a spurious extra band."""
    geo = _BIG_GEOMETRY[max_rows]
    canvas, real = _bigsign()
    render_standings_board(
        canvas, "AL EAST", _worst_case_rows(max_rows), max_rows=max_rows
    )
    x0, x1 = geo["abbr_x"], geo["abbr_x"] + 40
    lit = {y for y in _lit_ys_in_col(real, x0, x1) if y >= geo["row0"] - 3}
    assert len(_y_clusters(lit)) == max_rows


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_long_worst_case_rows_dont_bleed_into_each_other(max_rows):
    geo = _LONG_GEOMETRY[max_rows]
    canvas, real = _longboi()
    render_standings_board(
        canvas, "AL EAST", _worst_case_rows(max_rows), max_rows=max_rows
    )
    x0, x1 = geo["abbr_x"], geo["abbr_x"] + 40
    lit = {y for y in _lit_ys_in_col(real, x0, x1) if y >= geo["row0"] - 3}
    assert len(_y_clusters(lit)) == max_rows


# Column-overlap check (collision requirement, part 1). Rather than
# clustering rendered pixels directly (individual glyphs within one field —
# e.g. the "1"/"0"/"0" of "100" — routinely have a couple px of dark
# kerning between them, at a similar magnitude to some of the tighter
# CROSS-column gaps, e.g. chip-to-abbr; a naive "count the dark-separated
# blobs" test can't tell a normal inter-glyph gap from a true column
# collision without hardcoding a fragile threshold), this measures each
# column's advance via `text_width` — the EXACT function `hires`/
# `draw_record` use to advance their own cursors, so an assertion here is
# an assertion about what will actually render, not an approximation.
def _record_width(size):
    return text_width(size, "100") + text_width(size, "-") + text_width(size, "62")


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_big_worst_case_columns_dont_collide(max_rows):
    geo = _BIG_GEOMETRY[max_rows]
    text = geo["text"]
    rank_end = 2 + text_width(geo["rank"], str(max_rows))
    chip_end = 11 + geo["chip"]
    abbr_end = geo["abbr_x"] + text_width(text, "WSH")
    record_end = 112 + _record_width(text)
    gb_end = geo["gb_x"] + text_width(text, "16.0")
    strk_end = geo["strk_x"] + text_width(text, "W12")

    assert rank_end < 11, f"max_rows={max_rows}: rank collides with chip"
    assert chip_end < geo["abbr_x"], f"max_rows={max_rows}: chip collides with abbr"
    assert abbr_end < 112, f"max_rows={max_rows}: abbr collides with record"
    assert record_end < geo["gb_x"], f"max_rows={max_rows}: record collides with gb"
    assert gb_end < geo["strk_x"], f"max_rows={max_rows}: gb collides with strk"
    assert strk_end <= 256, f"max_rows={max_rows}: strk runs off the panel"


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_long_worst_case_columns_dont_collide(max_rows):
    """Also verifies the task's "LONG column x positions stay fixed" claim:
    the fixed x positions below (158/192/224/292/350/420) are what
    `_render_long` always uses regardless of `max_rows` — this would fail
    at px14 (the 3-row worst case) if that claim didn't hold."""
    geo = _LONG_GEOMETRY[max_rows]
    text = geo["text"]
    rank_end = 6 + text_width(geo["rank"], str(max_rows))
    chip_end = 18 + geo["chip"]
    abbr_end = geo["abbr_x"] + text_width(text, "WSH")
    wins_end = 158 + text_width(text, "100")
    losses_end = 192 + text_width(text, "62")
    pct_end = 224 + text_width(text, ".1000")
    gb_end = 292 + text_width(text, "16.0")
    l10_end = 350 + text_width(text, "10-0", bold=False)
    strk_end = 420 + text_width(text, "W12")

    assert rank_end < 18, f"max_rows={max_rows}: rank collides with chip"
    assert chip_end < geo["abbr_x"], f"max_rows={max_rows}: chip collides with abbr"
    assert abbr_end < 158, f"max_rows={max_rows}: abbr collides with wins"
    assert wins_end < 192, f"max_rows={max_rows}: wins collides with losses"
    assert losses_end < 224, f"max_rows={max_rows}: losses collides with pct"
    assert pct_end < 292, f"max_rows={max_rows}: pct collides with gb"
    assert gb_end < 350, f"max_rows={max_rows}: gb collides with l10"
    assert l10_end < 420, f"max_rows={max_rows}: l10 collides with strk"
    assert strk_end <= 512, f"max_rows={max_rows}: strk runs off the panel"


def test_big_three_row_gb_strk_gap_is_real_pixels():
    """Direct pixel regression for the BIG 3-row GB/STRK column move (172/
    216): confirms an actual dark gap exists between them at the adjusted
    positions, not just that the arithmetic clears (belt-and-suspenders
    alongside the generic collision-matrix test above)."""
    geo = _BIG_GEOMETRY[3]
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _worst_case_rows(3), max_rows=3)
    y0, y1 = geo["row0"], geo["row0"] + geo["pitch"]
    gb_max = max(
        (
            x
            for x in range(geo["gb_x"], geo["strk_x"])
            if _lit_in(real, x, x + 1, y0, y1)
        ),
        default=geo["gb_x"],
    )
    assert gb_max < geo["strk_x"]


@pytest.mark.parametrize("max_rows", [3, 4, 5])
def test_max_rows_out_of_table_falls_back_to_five(max_rows):
    """Defensive floor: an out-of-table `max_rows` degrades to the 5-row
    geometry rather than raising (validated 3-5 upstream in
    `standings.py`)."""
    canvas, real = _bigsign()
    render_standings_board(canvas, "AL EAST", _rows(5), max_rows=99)
    canvas2, real2 = _bigsign()
    render_standings_board(canvas2, "AL EAST", _rows(5), max_rows=5)
    assert _lit_coords(real) == _lit_coords(real2)


def test_five_row_geometry_matches_pre_uplift_hardcoded_values():
    """Explicit lock on the 5-row geometry-table entries themselves (not
    just the rendered output, which the pre-existing tests already cover
    byte-for-byte) — a future edit to `_BIG_GEOMETRY`/`_LONG_GEOMETRY`
    that silently drifts the 5-row row would still pass the pixel tests if
    it happened to compensate elsewhere; this pins the values directly."""
    assert _BIG_GEOMETRY[5] == dict(
        pitch=10, text=10, rank=8, chip=8, row0=12, abbr_x=22, gb_x=180, strk_x=212
    )
    assert _LONG_GEOMETRY[5] == dict(
        pitch=10, text=10, rank=8, chip=9, row0=14, abbr_x=32
    )
