"""Pixel-identity comparison: core vs plugin price-ticker renderer.

For each fixture × center-flag combination, renders the same inputs through
BOTH renderers onto fresh instrumented stub canvases and compares the ordered
SetPixel call sequences (and their SHA-256 hash).  Exit 0 if every case
matches; exit 1 on any mismatch.

Usage:
    PYTHONPATH=../led-ticker/tests/stubs uv run python tools/compare_render.py
"""

import hashlib
import sys

from rgbmatrix import RGBMatrix, RGBMatrixOptions

from led_ticker.widgets.crypto.coinbase import _draw_price_ticker as core_renderer
from led_ticker_crypto._ticker_render import draw_price_ticker as plugin_renderer

# ---------------------------------------------------------------------------
# Fixtures: (symbol, price_str, change_str)
# ---------------------------------------------------------------------------
FIXTURES = [
    ("BTC", "50000.0000", "2.55%"),
    ("ETH", "3,000.0000", "-1.50%"),
    ("DOGE", "0.1234", "0.00%"),
    ("BTC", "12345678.90", "1.00%"),  # len > 10 → FONT_VALUE_SMALL branch
]


def make_canvas():
    """Return a fresh 160×16 stub canvas with an instrumented SetPixel."""
    opts = RGBMatrixOptions()
    opts.cols = 160
    opts.rows = 16
    canvas = RGBMatrix(options=opts).CreateFrameCanvas()
    calls = []
    orig = canvas.SetPixel

    def rec(x, y, r, g, b):
        calls.append((x, y, r, g, b))
        return orig(x, y, r, g, b)

    canvas.SetPixel = rec
    return canvas, calls


def sha(calls):
    return hashlib.sha256(repr(calls).encode()).hexdigest()


def main():
    total = 0
    mismatches = []

    for fixture in FIXTURES:
        symbol, price_str, change_str = fixture
        for center in (True, False):
            total += 1
            label = f"({symbol!r}, {price_str!r}, {change_str!r}, center={center})"

            # Render through core
            c_core, calls_core = make_canvas()
            core_renderer(
                c_core,
                symbol,
                price_str,
                change_str,
                cursor_pos=0,
                center=center,
                padding=6,
                end_padding=6,
                y_offset=0,
                font_color=None,
                frame_count=0,
            )

            # Render through plugin
            c_plugin, calls_plugin = make_canvas()
            plugin_renderer(
                c_plugin,
                symbol,
                price_str,
                change_str,
                cursor_pos=0,
                center=center,
                padding=6,
                end_padding=6,
                y_offset=0,
                font_color=None,
                frame_count=0,
            )

            if calls_core == calls_plugin:
                print(f"MATCH  {label}  sha={sha(calls_core)[:16]}…")
            else:
                # Find the first differing element
                first_diff = None
                for i, (a, b) in enumerate(zip(calls_core, calls_plugin)):
                    if a != b:
                        first_diff = (i, a, b)
                        break
                if first_diff is None:
                    # One list is a prefix of the other
                    shorter = min(len(calls_core), len(calls_plugin))
                    first_diff = (
                        shorter,
                        calls_core[shorter] if len(calls_core) > shorter else "<end>",
                        calls_plugin[shorter] if len(calls_plugin) > shorter else "<end>",
                    )

                idx, core_px, plugin_px = first_diff
                print(
                    f"DIFF   {label}\n"
                    f"         core   len={len(calls_core)}  sha={sha(calls_core)[:16]}…\n"
                    f"         plugin len={len(calls_plugin)}  sha={sha(calls_plugin)[:16]}…\n"
                    f"         first diff @ index {idx}:\n"
                    f"           core  : {core_px}\n"
                    f"           plugin: {plugin_px}"
                )
                mismatches.append(label)

    print()
    if mismatches:
        print(f"FAILED — {len(mismatches)}/{total} cases differ:")
        for m in mismatches:
            print(f"  {m}")
        sys.exit(1)
    else:
        print(f"ALL {total} CASES IDENTICAL")
        sys.exit(0)


if __name__ == "__main__":
    main()
