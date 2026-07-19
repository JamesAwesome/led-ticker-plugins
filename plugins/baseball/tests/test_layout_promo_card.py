"""tests/test_layout_promo_card.py — hires text asserted by EXTENT/region
only (never exact freetype pins), same convention as
test_layout_standings_board.py / test_layout_crawl.py.

HeadlessBackend takes (width, height) positionally; HeadlessCanvas's
supported read surface is get_pixel(x, y) plus the `_pixels` dict, per the
sibling test files' precedent.
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import cap_top, hires, phys_wrap, text_width
from led_ticker_baseball.layouts.promo_card import _promo_sub, render_promo_card
from led_ticker_baseball.promotions import PromoInfo


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


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


def _lit_coords(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _lit_in(real, x0, x1, y0, y1):
    return any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(x0, x1) for y in range(y0, y1)
    )


# ---------- BIG (256px) ----------


def test_big_regions_present():
    canvas, real = _bigsign()
    render_promo_card(canvas, _promo(), 0)
    assert _lit_in(real, 4, 60, 0, 10)  # date, amber, x4 y1 px9
    assert _lit_in(real, 4, 200, 12, 32)  # name band [4,252) y14 px16
    assert _lit_in(real, 4, 16, 35, 47)  # chip x4 y35 h11
    assert _lit_in(real, 19, 100, 33, 48)  # "VS BOS" x19 y35 px12
    assert _lit_in(real, 4, 100, 48, 62)  # sub line x4 y50 px11
    assert _lit_in(real, 150, 252, 48, 62)  # right-anchored time, ends at 252


def test_big_name_outside_band_never_lit():
    canvas, real = _bigsign()
    render_promo_card(canvas, _promo(name="A Reasonably Long Promo Night Name"), 0)
    lit = _lit_coords(real)
    # name band is [4, 252); nothing at y14-30 should escape past x=252
    assert not any(y in range(12, 32) and x >= 252 for x, y in lit)


def test_big_short_name_is_static_across_clocks():
    canvas_a, real_a = _bigsign()
    canvas_b, real_b = _bigsign()
    render_promo_card(canvas_a, _promo(), 0)
    render_promo_card(canvas_b, _promo(), 999_999)
    assert real_a._pixels == real_b._pixels


def test_big_paging_dots_drawn_when_multiple_stories():
    canvas, real = _bigsign()
    render_promo_card(canvas, _promo(), 0, story_index=1, story_total=3)
    # dots sit at (256 - 3*8 - 4, 2) .. spanning a couple px
    assert _lit_in(real, 228, 256, 2, 6)


def test_big_no_paging_dots_when_single_story():
    canvas, real = _bigsign()
    render_promo_card(canvas, _promo(), 0, story_index=0, story_total=1)
    assert not _lit_in(real, 228, 256, 2, 6)


def test_big_sub_never_collides_with_time_worst_case():
    """Regression guard: a long offerType + presentedBy combo must never
    overlap the right-anchored time block. Worst case from the plan:
    'FAN EXPERIENCE · BY NEW ERA' + '12:35 PM'."""
    canvas, real = _bigsign()
    p = _promo(
        offer_type="Fan Experience",
        presented_by="New Era",
        time_label="12:35",
        am_pm="PM",
    )
    render_promo_card(canvas, p, 0)
    tw = text_width(11, "12:35 PM", bold=False)
    time_x = 252 - tw

    # Isolate what the time text ALONE would light up at the same position,
    # so we can tell "that's the time" apart from "the sub line bled into
    # the time's own columns" — both draw on the same row (y50 px11), so a
    # same-row full-canvas scan can't otherwise distinguish the two.
    time_only_real = HeadlessBackend(256, 64).create_canvas()
    time_only_canvas = ScaledCanvas(time_only_real, scale=4, content_height=16)
    time_shim, _ = phys_wrap(time_only_canvas)
    hires(time_shim, "12:35 PM", time_x, cap_top(50, 11), pal.AMBER, 11, bold=False)
    time_only_lit = {xy for xy, v in time_only_real._pixels.items() if v != (0, 0, 0)}

    full_lit_in_time_region = {
        (x, y)
        for (x, y), v in real._pixels.items()
        if v != (0, 0, 0) and x >= time_x and y in range(45, 65)
    }
    # Every pixel at/right of the time's own x-origin must be accounted for
    # by the isolated time-only render — nothing extra (from an overflowing
    # sub line) snuck in.
    assert full_lit_in_time_region <= time_only_lit


def test_big_empty_offer_and_sponsor_never_raises():
    canvas, _real = _bigsign()
    render_promo_card(canvas, PromoInfo(name=""), 0)


def test_big_sponsor_only_has_no_bare_dot():
    """offer_type empty + presented_by set must render 'BY SPONSOR', never
    a bare '· BY SPONSOR' (dc.html's literal promoSub port would do this)."""
    p = _promo(offer_type="", presented_by="New Era")
    assert _promo_sub(p) == "BY NEW ERA"
    assert not _promo_sub(p).startswith("·")


def test_big_y_offset_shifts_content():
    canvas, real = _bigsign()
    render_promo_card(canvas, _promo(), 0)
    rows = {y for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}
    canvas2, real2 = _bigsign()
    render_promo_card(canvas2, _promo(), 0, y_offset=8)
    rows2 = {y for x, y in real2._pixels if real2.get_pixel(x, y) != (0, 0, 0)}
    assert min(rows2) - min(rows) == 32


# ---------- LONG (512px) ----------


def test_long_regions_present():
    canvas, real = _longboi()
    render_promo_card(canvas, _promo(), 0)
    assert _lit_in(real, 6, 60, 2, 20)  # date, x6 y4 px12
    assert _lit_in(real, 6, 300, 16, 44)  # name band [6,300) y18 px22
    assert _lit_in(real, 6, 100, 48, 62)  # "PROMOTION" label x6 y50 px9
    assert _lit_in(real, 308, 322, 6, 25)  # chip rx=308 y8 h13
    assert _lit_in(real, 326, 460, 6, 28)  # "VS BOS" + time, right block
    assert _lit_in(real, 308, 460, 34, 54)  # sub line rx=308 y36 px14


def test_long_name_outside_band_never_lit():
    canvas, real = _longboi()
    render_promo_card(canvas, _promo(name="Hawaiian Shirt & Beach Towel Giveaway"), 0)
    lit = _lit_coords(real)
    # Buffer zone between the name band's right edge (300) and the right
    # info block's left edge (rx=308) must stay dark — proves mask_scroll's
    # hard clip held even for a name much wider than the band. (Can't probe
    # x>=300 wholesale: the right info block itself legitimately paints
    # there, in the same y range.)
    assert not any(300 <= x < 308 for x, y in lit if 16 <= y < 44)
    assert not any(y in range(16, 44) and x < 6 for x, y in lit)


def test_long_long_name_scrolls_across_clocks():
    canvas_a, real_a = _longboi()
    canvas_b, real_b = _longboi()
    long_name = "Hawaiian Shirt & Beach Towel Giveaway"
    render_promo_card(canvas_a, _promo(name=long_name), 0)
    render_promo_card(canvas_b, _promo(name=long_name), 3000)
    name_band_a = {(x, y) for x, y in real_a._pixels if 16 <= y < 44 and 6 <= x < 300}
    name_band_b = {(x, y) for x, y in real_b._pixels if 16 <= y < 44 and 6 <= x < 300}
    assert name_band_a != name_band_b


def test_long_short_name_is_static_across_clocks():
    canvas_a, real_a = _longboi()
    canvas_b, real_b = _longboi()
    render_promo_card(canvas_a, _promo(name="Cap Giveaway"), 0)
    render_promo_card(canvas_b, _promo(name="Cap Giveaway"), 999_999)
    assert real_a._pixels == real_b._pixels


def test_long_paging_dots_drawn_when_multiple_stories():
    canvas, real = _longboi()
    render_promo_card(canvas, _promo(), 0, story_index=0, story_total=4)
    # dots sit at (512 - 4*8 - 6, 64-10) .. spanning a couple px
    assert _lit_in(real, 470, 512, 54, 58)


def test_long_empty_fields_never_raise():
    canvas, _real = _longboi()
    render_promo_card(
        canvas,
        PromoInfo(name=""),
        0,
    )


def test_long_y_offset_shifts_content():
    canvas, real = _longboi()
    render_promo_card(canvas, _promo(), 0)
    rows = {y for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}
    canvas2, real2 = _longboi()
    render_promo_card(canvas2, _promo(), 0, y_offset=8)
    rows2 = {y for x, y in real2._pixels if real2.get_pixel(x, y) != (0, 0, 0)}
    assert min(rows2) - min(rows) == 32
