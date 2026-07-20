from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball import _paint
from led_ticker_baseball import _palette as pal


def _real(w=256, h=64):
    # HeadlessBackend takes (width, height) positionally — see
    # led_ticker/backends/headless.py. There is no rows/cols/chain_length
    # kwarg surface on this backend (that's an RgbMatrixBackend shape).
    return HeadlessBackend(w, h).create_canvas()


def test_js_round_half_up():
    assert _paint.js_round(0.5) == 1
    assert _paint.js_round(1.5) == 2
    assert _paint.js_round(2.5) == 3  # bankers' round() would give 2
    assert _paint.js_round(-0.5) == 0  # JS Math.round(-0.5) is -0 -> 0


def test_phys_wrap_gives_scale1_shim_over_real():
    real = _real()
    wrapped = ScaledCanvas(real, scale=4, content_height=16)
    shim, unwrapped = _paint.phys_wrap(wrapped)
    assert unwrapped is real
    assert shim.scale == 1
    assert shim.height == real.height


def test_hires_returns_positive_advance_and_lights_pixels():
    real = _real()
    shim, _ = _paint.phys_wrap(real)
    w = _paint.hires(shim, "10", 8, 8, pal.IDENT, 20)
    assert w > 0
    assert w == _paint.text_width(20, "10")
    # HeadlessCanvas has no public iter_pixels(); its supported read surface
    # is get_pixel(x, y) plus the `_pixels` dict it serializes from (see
    # led_ticker/backends/headless.py docstring — get_pixel is "the supported
    # backend serialization read"). Sibling plugins (stocks/test_paint.py)
    # already reach into `_pixels` directly for this exact "any lit pixel"
    # check, so we follow that precedent here.
    assert any(v != (0, 0, 0) for v in real._pixels.values())


def test_px_bounds_checked():
    real = _real()
    _paint.px(real, -1, 0, pal.IDENT)  # must not raise
    _paint.px(real, 0, 9999, pal.IDENT)
    _paint.px(real, 3, 3, pal.IDENT)
    assert real.get_pixel(3, 3) == (255, 255, 255)


def test_hires_safe_strips_emoji_and_collapses_space():
    # F1 (final review): a mapped Unicode emoji paints as a hi-res sprite
    # (`draw_text`/`hires`) but measures at the '?' fallback advance
    # (`measure_width`/`text_width`) — the two disagree on width for the
    # exact same string. `_hires_safe` removes the emoji before EITHER call
    # so free-form promo text can't drift between measure and paint.
    assert _paint._hires_safe("STAR WARS NIGHT ⭐") == "STAR WARS NIGHT"
    assert _paint._hires_safe("Pride Night 🌈 Giveaway") == "Pride Night Giveaway"


def test_hires_safe_leaves_plain_and_accented_text_untouched():
    assert _paint._hires_safe("Bobblehead Night") == "Bobblehead Night"
    assert _paint._hires_safe("JOSÉ RAMÍREZ BOBBLEHEAD") == "JOSÉ RAMÍREZ BOBBLEHEAD"
    assert _paint._hires_safe("Fan Experience · BY NEW ERA") == (
        "Fan Experience · BY NEW ERA"
    )


def test_hires_safe_makes_measure_and_paint_agree():
    # Direct repro of the report's measurement: pre-fix, text_width(17, ...)
    # returns 178 while hires()'s painted advance returns 197 for the same
    # raw string. Post-sanitization the two must match exactly.
    real = _real()
    shim, _ = _paint.phys_wrap(real)
    raw = "STAR WARS NIGHT ⭐"
    safe = _paint._hires_safe(raw)
    measured = _paint.text_width(17, safe, bold=True)
    painted = _paint.hires(shim, safe, 0, 0, pal.IDENT, 17, bold=True)
    assert measured == painted


def test_paging_dots_active_vs_dim():
    real = _real()
    _paint.paging_dots(real, 3, 1, 200, 60)
    # active dot (index 1) is IDENT white; others LABEL. Dots are 2x2 blocks
    # on an 8px pitch (step=8, per the brief's self-review note and the
    # "NOTE for implementer" — matches the prototype's pagingDots layout
    # math, `n*8+4` px reserved per call site): dot i occupies columns
    # [x + i*8, x + i*8 + 1]. The brief's own Step-1 draft used offsets
    # (200+2=202, 202+2=204) that land in the GAPS between dots under this
    # geometry (verified empirically: those pixels are unlit) rather than on
    # an actual dot — fixed here to probe the dots' real column positions
    # (dot0 at x=200, dot1/active at x=200+8=208) instead of changing the
    # step/dot-size to fit the stale offsets.
    assert real.get_pixel(200, 60) == (pal.LABEL.red, pal.LABEL.green, pal.LABEL.blue)
    assert real.get_pixel(208, 60) == (255, 255, 255)
