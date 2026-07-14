"""Manual bitmap glyphs (verbatim from design/led-engine.js GLYPH table)."""

from led_ticker_flight.palette import RGB

GLYPHS: dict[str, tuple[str, ...]] = {
    "up": ("..#..", ".###.", "#####", "..#..", "..#..", "..#..", "..#.."),
    "down": ("..#..", "..#..", "..#..", "..#..", "#####", ".###.", "..#.."),
    "level": ("#####", "#####"),
    "deg": ("###", "#.#", "###"),
    "dot": ("#",),
}


def glyph_size(name: str) -> tuple[int, int]:
    rows = GLYPHS[name]
    return len(rows[0]), len(rows)


def draw_glyph(
    set_px, name: str, x: int, y: int, rgb: RGB, bright: float = 1.0, expand: int = 1
) -> int:
    """Blit a glyph with top-left (x, y), each mask cell expand×expand px."""
    rows = GLYPHS[name]
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            if ch != "#":
                continue
            for dy in range(expand):
                for dx in range(expand):
                    set_px(x + gx * expand + dx, y + gy * expand + dy, rgb, bright)
    return len(rows[0]) * expand
