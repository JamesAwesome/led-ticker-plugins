"""tests/test_resolve_statcast_layout.py — spec table: scale <= 1 -> "legacy"
always (regardless of cfg_layout); auto @ scale>1 -> "big" (<400 phys) /
"long" (>=400 phys); explicit "big"/"long" pass through unchanged at scale>1.
Mirrors tests/test_resolve_promo_layout.py's shape for the statcast
sibling."""

from led_ticker_baseball import _palette as pal
from led_ticker_baseball.layouts import resolve_statcast_layout
from led_ticker_baseball.trajectory import res_color


def test_scale_one_is_legacy():
    assert resolve_statcast_layout("auto", 1, 160) == "legacy"


def test_auto_big_vs_long_by_width():
    assert resolve_statcast_layout("auto", 4, 256) == "big"
    assert resolve_statcast_layout("auto", 4, 512) == "long"


def test_explicit_layout_respected_at_scale_gt_1():
    assert resolve_statcast_layout("long", 4, 512) == "long"
    assert resolve_statcast_layout("big", 4, 512) == "big"


def test_explicit_long_degrades_on_narrow_panel():
    """render_statcast_long draws its columns/trajectory out to x~502, mostly
    off a 256px bigsign. Mirror resolve_layout's Finding-3 degrade guard: an
    explicit long on a <400px panel degrades to big rather than render near-
    blank."""
    assert resolve_statcast_layout("long", 4, 256) == "big"


def test_res_color_maps_outcome():
    assert res_color("HOME RUN") == pal.WIN
    assert res_color("FLY OUT") == pal.LOSS
    assert res_color("DOUBLE") == pal.AMBER
