"""tests/test_promo_card_dispatch.py — MLBPromoCard scale dispatch.

Mirrors tests/test_card_dispatch.py's shape (MLBGameCard) exactly:
HeadlessBackend(width, height) positional, ScaledCanvas at scale=4 for
bigsign (256 physical) / longboi (512 physical), plain HeadlessCanvas for
scale-1 (smallsign).
"""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas, SegmentMessage, colors

from led_ticker_baseball._promo_card import MLBPromoCard
from led_ticker_baseball.promotions import PromoInfo


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


def _legacy():
    return SegmentMessage(
        [("TOR ", colors.RGB_WHITE), ("Bobblehead Night", colors.RGB_WHITE)],
        center=True,
    )


def _card(layout="auto", **over):
    return MLBPromoCard(
        promo=_promo(),
        story_index=0,
        story_total=1,
        legacy=_legacy(),
        cfg_layout=layout,
        **over,
    )


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _smallsign():
    return HeadlessBackend(160, 16).create_canvas()


def test_auto_on_bigsign_holds_card():
    canvas, real = _bigsign()
    out, cursor = _card().draw(canvas)
    # held: cursor = canvas.width — the WRAPPER's LOGICAL width (256
    # physical // scale 4 = 64) — matches the units the engine's
    # `cursor_pos > canvas.width` hold-vs-scroll check (core ticker.py)
    # actually compares against.
    assert cursor == 64
    assert out is canvas
    assert any(
        real.get_pixel(x, y) != (0, 0, 0) for x in range(4, 60) for y in range(0, 10)
    )


def test_auto_on_longboi_scrolls_crawl():
    canvas, real = _longboi()
    out, cursor = _card().draw(canvas)
    assert cursor > 128  # longboi: 512 physical // scale 4 = 128 logical width


def test_explicit_ticker_on_bigsign_scrolls_crawl():
    canvas, real = _bigsign()
    out, cursor = _card(layout="ticker").draw(canvas)
    assert cursor > 64


def test_explicit_card_on_longboi_holds_card():
    canvas, real = _longboi()
    out, cursor = _card(layout="card").draw(canvas)
    assert cursor == 128


def test_scale1_delegates_to_legacy_verbatim():
    real_a = _smallsign()
    real_b = _smallsign()
    legacy_a = _legacy()
    legacy_b = _legacy()
    card = MLBPromoCard(
        promo=_promo(),
        story_index=0,
        story_total=1,
        legacy=legacy_a,
        cfg_layout="ticker",
    )
    out, cursor = card.draw(real_a)
    _, expected_cursor = legacy_b.draw(real_b)
    assert cursor == expected_cursor
    assert out is real_a


def test_frame_hooks_never_raise_before_first_draw():
    c = _card()
    c.advance_frame()
    c.pause_frame()
    c.resume_frame()
    c.reset_frame()
