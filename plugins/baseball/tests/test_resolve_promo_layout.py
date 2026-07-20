"""tests/test_resolve_promo_layout.py — spec table: scale <= 1 -> "legacy"
always (regardless of cfg_layout); auto @ scale>1 -> "card" (<400 phys) /
"ticker" (>=400 phys); explicit "ticker"/"card" pass through unchanged at
scale>1. Mirrors tests/test_resolve_layout.py's shape for the scores
sibling."""

from led_ticker_baseball.layouts import resolve_promo_layout


def test_scale1_is_always_legacy():
    assert resolve_promo_layout("auto", 1, 160) == "legacy"
    assert resolve_promo_layout("ticker", 1, 160) == "legacy"
    assert resolve_promo_layout("card", 1, 160) == "legacy"


def test_auto_bigsign_is_card():
    assert resolve_promo_layout("auto", 4, 256) == "card"


def test_auto_longboi_is_ticker():
    assert resolve_promo_layout("auto", 4, 512) == "ticker"


def test_explicit_names_pass_through_at_scale_gt_1():
    assert resolve_promo_layout("ticker", 4, 256) == "ticker"
    assert resolve_promo_layout("card", 4, 256) == "card"
    assert resolve_promo_layout("ticker", 4, 512) == "ticker"
    assert resolve_promo_layout("card", 4, 512) == "card"


def test_width_threshold_boundary():
    # < 400 -> card, >= 400 -> ticker (matches promo_card.py's own
    # _WIDE_MIN_W threshold for the BIG-vs-LONG geometry split).
    assert resolve_promo_layout("auto", 4, 399) == "card"
    assert resolve_promo_layout("auto", 4, 400) == "ticker"
