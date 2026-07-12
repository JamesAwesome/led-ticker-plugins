from led_ticker_flight.fins import draw_fin, fin_width, js_round
from led_ticker_flight.palette import AIRLINES


def _collect(h, airline):
    pixels = {}

    def set_px(x, y, rgb, b):
        pixels[(x, y)] = (rgb, b)

    draw_fin(set_px, 0, 0, h, airline)
    return pixels


def test_js_round_half_up():
    assert js_round(0.5) == 1
    # banker's round() would give 2 here but 0.5 -> 0; pin the JS behavior
    assert js_round(1.5) == 2
    assert js_round(2.5) == 3
    assert js_round(-0.4) == 0


def test_fin_widths_match_handoff():
    assert fin_width(12) == 10
    assert fin_width(28) == 23
    assert fin_width(32) == 26


def test_fin_h12_geometry():
    al = AIRLINES["UA"]
    px = _collect(12, al)
    # top row (r=0): leftX = js_round(js_round(10*0.52)*(1-0)) = 5 -> cols 5..9 lit
    assert (5, 0) in px and (4, 0) not in px and (9, 0) in px
    # bottom row (r=11): leftX = 0 -> full width
    assert (0, 11) in px
    # accent band: bandTop=js_round(6.0)=6, bandH=max(1,js_round(1.92))=2
    # -> rows 6,7 are c2
    assert px[(9, 6)][0] == al.c2 and px[(9, 7)][0] == al.c2
    assert px[(9, 5)][0] == al.c1 and px[(9, 8)][0] == al.c1


def test_fin_returns_width():
    al = AIRLINES["DL"]
    assert draw_fin(lambda *a: None, 0, 0, 28, al) == 23
