"""tests/test_resolve_layout.py — spec table: auto @ scale1 -> ticker;
auto @ scale>1 -> two_row (<400 phys) / scoreboard (>=400); explicit names
pass through (scale dispatch happens in the story's draw, not here) — WITH
one guard: explicit "scoreboard" at scale>1 below the 400px threshold
degrades to "two_row" (final-review Finding 3 — the physical scoreboard's
hardcoded anchors assume >=400 phys px and would otherwise silently clip
the whole home side on a narrower panel)."""

from led_ticker_baseball.layouts import VALID_LAYOUTS, resolve_layout


def test_auto_scale1_is_ticker():
    assert resolve_layout("auto", 1, 160) == "ticker"


def test_auto_bigsign_is_two_row():
    assert resolve_layout("auto", 4, 256) == "two_row"


def test_auto_longboi_is_scoreboard():
    assert resolve_layout("auto", 4, 512) == "scoreboard"


def test_explicit_names_pass_through():
    for name in ("ticker", "scoreboard", "two_row"):
        assert resolve_layout(name, 1, 160) == name
    # At scale>1 on a >=400px (longboi) panel, every explicit name passes
    # through unchanged — including "scoreboard" (its native size).
    for name in ("ticker", "scoreboard", "two_row"):
        assert resolve_layout(name, 4, 512) == name


def test_explicit_scoreboard_degrades_below_min_width():
    """Finding 3: the physical scoreboard's hardcoded anchors (home name/
    score/dashes at 504, live cluster from x=176) assume a >=400 phys-px
    panel. Explicit `layout = "scoreboard"` on a narrower panel (bigsign,
    256 phys px) used to reach that renderer anyway and silently clip the
    entire home side. Now it degrades to "two_row" instead — same landing
    spot "auto" already picks for that panel."""
    assert resolve_layout("scoreboard", 4, 256) == "two_row"


def test_explicit_two_row_and_ticker_unaffected_by_width_guard():
    # Only "scoreboard" gets the degrade guard — "two_row" and "ticker"
    # always mean what they say, at any width.
    assert resolve_layout("two_row", 4, 256) == "two_row"
    assert resolve_layout("two_row", 4, 512) == "two_row"
    assert resolve_layout("ticker", 4, 256) == "ticker"
    assert resolve_layout("ticker", 4, 512) == "ticker"


def test_valid_layouts_tuple():
    assert VALID_LAYOUTS == ("auto", "ticker", "scoreboard", "two_row")
