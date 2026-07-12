from led_ticker_flight.glyphs import GLYPHS, draw_glyph, glyph_size


def test_glyph_bitmaps_match_prototype():
    # Verbatim from design/led-engine.js GLYPH table
    assert GLYPHS["up"] == (
        "..#..",
        ".###.",
        "#####",
        "..#..",
        "..#..",
        "..#..",
        "..#..",
    )
    assert GLYPHS["down"] == (
        "..#..",
        "..#..",
        "..#..",
        "..#..",
        "#####",
        ".###.",
        "..#..",
    )
    assert GLYPHS["level"] == ("#####", "#####")
    assert GLYPHS["deg"] == ("###", "#.#", "###")
    assert GLYPHS["dot"] == ("#",)


def test_glyph_size():
    assert glyph_size("up") == (5, 7)
    assert glyph_size("deg") == (3, 3)


def test_draw_glyph_pixels_and_expand():
    lit = set()
    w = draw_glyph(lambda x, y, rgb, b: lit.add((x, y)), "deg", 10, 5, (0, 220, 255))
    assert w == 3
    assert (11, 6) not in lit  # the hole in the deg glyph
    assert (10, 5) in lit and (12, 7) in lit
    lit2 = set()
    w2 = draw_glyph(
        lambda x, y, rgb, b: lit2.add((x, y)),
        "dot",
        0,
        0,
        (255, 255, 255),
        expand=4,
    )
    assert w2 == 4
    assert lit2 == {(x, y) for x in range(4) for y in range(4)}
