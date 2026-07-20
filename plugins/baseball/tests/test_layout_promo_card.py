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
    assert _lit_in(real, 6, 300, 2, 20)  # date, x6 y4 px12
    assert _lit_in(real, 6, 300, 16, 46)  # name band [6,300) y21 px26
    assert _lit_in(real, 6, 100, 48, 62)  # "PROMOTION" label x6 y50 px9
    assert _lit_in(real, 308, 320, 6, 22)  # chip rx=308 y8 h11
    assert _lit_in(real, 322, 440, 6, 26)  # "VS BOS" px14, right block
    assert _lit_in(real, 440, 507, 2, 26)  # time px12, right-anchored at 506
    assert _lit_in(real, 308, 460, 34, 52)  # sub line px12, left at rx y36


def test_long_time_right_anchored():
    """Hardware finding (longboi, 2026-07-20): the prototype left-flows the
    time after "VS OPP" (`promoLongCard` dc.html ~548), which strands ~50
    physical px of dead panel at the right edge — glaring when the cyan sub
    line below is empty (live promos are sparse; `presented_by`/`offer_type`
    are often missing). Deliberate deviation from the prototype: the time is
    right-anchored at `width - 6` (margin mirroring the left column's x=6 and
    the BIG layout's own `252 - tw` anchor)."""
    canvas, real = _longboi()
    render_promo_card(canvas, _promo(), 0)
    lit = _lit_coords(real)
    # Time occupies the top band hard against the right margin (old
    # left-flowed position topped out near x=432)...
    assert any(x >= 470 for x, y in lit if y < 30)
    # ...and respects the 6px right margin (paging dots are off at
    # story_total=1; nothing may cross x=506).
    assert not any(x > 506 for x, _y in lit)


def test_long_left_column_gaps_consistent():
    """Hardware feedback (longboi, 2026-07-20, round 2): the left column's
    vertical rhythm was date -> 5px gap -> name -> 15px gap -> PROMOTION.
    The name marquee is now px26 seated so both gaps land within a couple
    of px of each other. Asserted RELATIVELY (gap difference, not absolute
    rows) so freetype cap-height variance across platforms can't flake it."""
    canvas, real = _longboi()
    render_promo_card(canvas, _promo(), 0)
    lit = _lit_coords(real)
    left = {(x, y) for x, y in lit if x < 300}
    date_rows = sorted(y for _x, y in left if y < 16)
    name_rows = sorted(y for _x, y in left if 16 <= y < 46)
    label_rows = sorted(y for _x, y in left if y >= 46)
    gap_above = name_rows[0] - date_rows[-1] - 1
    gap_below = label_rows[0] - name_rows[-1] - 1
    assert abs(gap_above - gap_below) <= 3, (
        f"date->name gap {gap_above} vs name->PROMOTION gap {gap_below}"
    )


def test_long_right_block_sizes_reduced():
    """Hardware feedback (longboi, 2026-07-20, round 3): round 2's packing
    of the right block against the time was rolled back — the block sits
    at the prototype's fixed rx=308 with the sub left-aligned under the
    chip — and the right side is instead one size notch SMALLER (chip
    h13->11, VS px16->14, time px14->12, sub px14->12) so it reads as a
    quieter info column next to the px26 marquee. Guard: "VS OPP" (violet,
    px14) must render SHORTER than the px26 name's cap band — relative,
    freetype-safe."""
    canvas, real = _longboi()
    render_promo_card(canvas, _promo(), 0)
    violet = (pal.VIOLET.red, pal.VIOLET.green, pal.VIOLET.blue)
    vs_rows = sorted(y for (x, y), v in real._pixels.items() if v == violet)
    vs_cols = sorted(x for (x, y), v in real._pixels.items() if v == violet)
    assert vs_cols[0] >= 320  # block anchored at rx=308 (chip first, then VS)
    vs_cap = vs_rows[-1] - vs_rows[0] + 1
    assert vs_cap <= 11  # px14 cap ~10 rows; px16 measured 12


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


def test_long_no_sub_extends_name_band_full_width():
    """Hardware feedback (longboi, 2026-07-20, round 4): when the cyan sub
    line is EMPTY (offer_type and presented_by both missing — the norm for
    PHI and a few other clubs), the rows under the right block are dead
    space, so the name marquee's clip band extends from [6,300) to the
    full [6,506). The name rows (~21..40) pass below the chip/VS/time
    block (top ~20 rows), so nothing collides. With a sub line present the
    band stays [6,300)."""
    canvas, real = _longboi()
    render_promo_card(
        canvas,
        _promo(name="Chick-fil-A Phillies Big Chain", offer_type="", presented_by=""),
        0,
    )
    lit = _lit_coords(real)
    name_rows = range(21, 46)
    # Band extended: name pixels land beyond the sub-present band edge (300)
    assert any(x >= 320 for x, y in lit if y in name_rows)
    # ...but the clip (and the 6px margin) still hold at 506.
    assert not any(x > 506 for x, _y in lit)

    # Sub present -> band stays [6,300): no name pixels at/right of 300
    # (the sub itself sits at x>=308 but on rows 36+ — probe rows 21..34).
    canvas_b, real_b = _longboi()
    render_promo_card(canvas_b, _promo(name="Chick-fil-A Phillies Big Chain"), 0)
    lit_b = _lit_coords(real_b)
    assert not any(x >= 300 for x, y in lit_b if 21 <= y < 35)


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


class TestEmojiSanitization:
    """F1 (final review): the name always routes through `_mask.mask_scroll`,
    whose offscreen mask canvas is sized from the MEASURED width
    (`text_width`, low-res-emoji-width fallback for a MAPPED Unicode emoji —
    `_paint.text_width`'s scale=1 probe isn't a `ScaledCanvas`, so
    `measure_width` can't take the hi-res branch) — but the actual paint
    (`hires()`, whose shim IS a real `ScaledCanvas`) draws the SAME mapped
    emoji as a much wider hi-res sprite, so the sprite's trailing pixels
    (and any letters after it) get cropped by the offscreen canvas edge, and
    `mask.w` itself understates the name's true width. Sanitizing the emoji
    out before either call means an emoji-bearing name must render
    BYTE-IDENTICAL to the same name with the emoji (and its trailing space)
    removed — a cropped/truncated mask would show up as a mismatch here.
    Uses '⭐' throughout: it IS in core's `_UNICODE_EMOJI_MAP` (-> hi-res
    "star") — an unmapped emoji is already stripped uniformly by core on
    both the measure and paint side, so it wouldn't exercise this drift.
    """

    def test_big_emoji_name_matches_sanitized_plain_name(self):
        canvas_a, real_a = _bigsign()
        render_promo_card(canvas_a, _promo(name="Cap Giveaway"), 0)
        canvas_b, real_b = _bigsign()
        render_promo_card(canvas_b, _promo(name="Cap Giveaway ⭐"), 0)
        assert real_a._pixels == real_b._pixels

    def test_long_emoji_name_matches_sanitized_plain_name(self):
        canvas_a, real_a = _longboi()
        render_promo_card(canvas_a, _promo(name="Cap Giveaway"), 0)
        canvas_b, real_b = _longboi()
        render_promo_card(canvas_b, _promo(name="Cap Giveaway ⭐"), 0)
        assert real_a._pixels == real_b._pixels

    def test_long_overflowing_emoji_name_feeds_sanitized_text_to_scroll(
        self, monkeypatch
    ):
        """The scrolling (overflow) branch is where a cropped mask would
        actually lose the name's tail. A full-render byte comparison at an
        arbitrary clock isn't reliable here (whether the scrolled window
        happens to overlap the cropped tail depends on the clock value and
        both variants' periods) — so instead assert directly on what text
        reaches `_mask.mask_scroll`: it must be the sanitized name, with no
        emoji left in it, matching the `_promo_card` module's own call
        target (patched by NAME so the layout's `from ... import
        mask_scroll` binding is what's replaced)."""
        import led_ticker_baseball.layouts.promo_card as promo_card_mod

        captured: dict[str, str] = {}

        def _spy(real, text, x0, x1, y, color, size, clock_ms, **kw):
            captured["text"] = text

        monkeypatch.setattr(promo_card_mod, "mask_scroll", _spy)
        canvas, _real = _longboi()
        long_name = "Hawaiian Shirt & Beach Towel Giveaway"
        render_promo_card(canvas, _promo(name=f"{long_name} ⭐"), 3000)
        assert captured["text"] == long_name.upper()
        assert "⭐" not in captured["text"]

    def test_emoji_sub_matches_sanitized_plain_sub(self):
        canvas_a, real_a = _longboi()
        render_promo_card(canvas_a, _promo(presented_by="New Era"), 0)
        canvas_b, real_b = _longboi()
        render_promo_card(canvas_b, _promo(presented_by="New Era ⭐"), 0)
        assert real_a._pixels == real_b._pixels

    def test_promo_sub_strips_emoji(self):
        p = _promo(offer_type="Giveaway ⭐", presented_by="Chase")
        assert "⭐" not in _promo_sub(p)


def test_long_y_offset_shifts_content():
    canvas, real = _longboi()
    render_promo_card(canvas, _promo(), 0)
    rows = {y for x, y in real._pixels if real.get_pixel(x, y) != (0, 0, 0)}
    canvas2, real2 = _longboi()
    render_promo_card(canvas2, _promo(), 0, y_offset=8)
    rows2 = {y for x, y in real2._pixels if real2.get_pixel(x, y) != (0, 0, 0)}
    assert min(rows2) - min(rows) == 32
