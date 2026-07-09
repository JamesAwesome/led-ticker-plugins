from led_ticker_storefront.config import parse_config
from led_ticker_storefront.render import draw_badge


def _lit(canvas):
    """Set of (x,y) lit pixels on a HeadlessCanvas."""
    lit = set()
    for y in range(canvas.height):
        for x in range(canvas.width):
            if canvas.get_pixel(x, y) != (0, 0, 0):
                lit.add((x, y))
    return lit


def _snapshot(canvas):
    """Full (x, y) -> rgb map, for equality comparisons across canvases."""
    return {
        (x, y): canvas.get_pixel(x, y)
        for y in range(canvas.height)
        for x in range(canvas.width)
    }


def test_horizontal_opaque_draws_in_top_right(real_canvas):
    cfg = parse_config({"font_size": 16, "corner": "top_right",
                        "open": {"text": "OPEN"}, "closed": {"text": "CLOSED"}})
    draw_badge(real_canvas, cfg, cfg.open, frame=0)
    lit = _lit(real_canvas)
    assert lit, "badge drew nothing"
    # anchored to the right half, top half of a 256x64 panel
    assert max(x for x, _ in lit) >= real_canvas.width - 4
    assert min(y for _, y in lit) < real_canvas.height // 2


def test_bottom_left_anchor(real_canvas):
    # Explicit non-black background: the config default (opaque black,
    # (0, 0, 0)) is indistinguishable from "unlit" on a HeadlessCanvas that
    # starts all-black, which would only let us detect glyph ink — and BDF
    # ascent/descent reserves unused headroom above the box bottom for
    # all-caps text with no descenders, so ink-only detection can't tell a
    # correctly bottom-anchored box from one placed several px too high. A
    # visible fill color makes the opaque box itself (which DOES reach the
    # panel's bottom edge) detectable, so the assertion can be tight.
    cfg = parse_config({"font_size": 16, "corner": "bottom_left",
                        "background": [80, 80, 80],
                        "open": {"text": "OPEN"}})
    draw_badge(real_canvas, cfg, cfg.open, frame=0)
    lit = _lit(real_canvas)
    assert min(x for x, _ in lit) <= 3                       # left edge
    assert max(y for _, y in lit) >= real_canvas.height - 2  # box reaches bottom edge


def test_transparent_background_leaves_gaps(real_canvas):
    cfg = parse_config({"font_size": 16, "background": "none",
                        "open": {"text": "OPEN"}})
    draw_badge(real_canvas, cfg, cfg.open, frame=0)
    # Explicit non-black background: the config default (opaque black,
    # (0, 0, 0)) is indistinguishable from "unlit" on a HeadlessCanvas that
    # starts all-black, which would make this comparison vacuous no matter
    # what render.py does. A visible fill color is needed to actually
    # observe "opaque paints a solid box".
    opaque = parse_config({"font_size": 16, "background": [80, 80, 80],
                            "open": {"text": "OPEN"}})
    from led_ticker.plugin import HeadlessCanvas
    c2 = HeadlessCanvas(256, 64)
    draw_badge(c2, opaque, opaque.open, frame=0)
    # opaque fills a solid box -> strictly more lit pixels than transparent glyphs
    assert len(_lit(c2)) > len(_lit(real_canvas))


def test_vertical_stacks_downward(real_canvas):
    cfg = parse_config({"font_size": 16, "corner": "top_left",
                        "open": {"text": "OPEN", "orientation": "vertical"}})
    draw_badge(real_canvas, cfg, cfg.open, frame=0)
    lit = _lit(real_canvas)
    # vertical "OPEN" spans more rows than a single horizontal line
    assert (max(y for _, y in lit) - min(y for _, y in lit)) > 16


def test_block_scaled_bdf_grows_with_font_size(real_canvas):
    from led_ticker.plugin import HeadlessCanvas
    small = HeadlessCanvas(256, 64)
    big = HeadlessCanvas(256, 64)
    draw_badge(small, parse_config({"font_size": 12, "open": {"text": "OPEN"}}),
               parse_config({"font_size": 12, "open": {"text": "OPEN"}}).open, 0)
    draw_badge(big, parse_config({"font_size": 48, "open": {"text": "OPEN"}}),
               parse_config({"font_size": 48, "open": {"text": "OPEN"}}).open, 0)
    small_lit = _lit(small)
    big_lit = _lit(big)
    small_h = max(y for _, y in small_lit) - min(y for _, y in small_lit)
    big_h = max(y for _, y in big_lit) - min(y for _, y in big_lit)
    assert big_h > small_h


def test_animated_color_varies_by_frame(real_canvas):
    from led_ticker.plugin import HeadlessCanvas
    cfg = parse_config({"font_size": 16, "background": "none",
                        "open": {"text": "OPEN", "color": "rainbow"}})
    c0 = HeadlessCanvas(256, 64)
    c1 = HeadlessCanvas(256, 64)
    draw_badge(c0, cfg, cfg.open, frame=0)
    draw_badge(c1, cfg, cfg.open, frame=60)
    # same lit positions, different colors across frames
    assert _snapshot(c0) != _snapshot(c1)


def test_oversized_badge_skips_without_raising(small_canvas, caplog):
    import logging
    cfg = parse_config({"font_size": 200, "open": {"text": "CLOSED"}})
    with caplog.at_level(logging.WARNING, logger="led_ticker_storefront"):
        draw_badge(small_canvas, cfg, cfg.open, frame=0)   # must not raise
    assert not _lit(small_canvas)
