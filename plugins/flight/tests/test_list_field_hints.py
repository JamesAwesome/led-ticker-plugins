"""`--list-fields flight.overhead` shows this widget's own `layout` hint.

Core carries no name-keyed hint for the plugin-owned `layout` field, so the
widget class supplies `_LIST_FIELD_HINTS` (issue #93).
"""

from led_ticker_flight.widget import _LAYOUTS, OverheadWidget


def _list_fields():
    # Register into core's widget registry the way entry-point discovery
    # would, then drive core's introspection path directly.
    from led_ticker.app.factories import _list_widget_fields
    from led_ticker.widgets import _WIDGET_REGISTRY

    prior = _WIDGET_REGISTRY.get("flight.overhead")
    _WIDGET_REGISTRY["flight.overhead"] = OverheadWidget
    try:
        return _list_widget_fields("flight.overhead")
    finally:
        if prior is None:
            _WIDGET_REGISTRY.pop("flight.overhead", None)
        else:
            _WIDGET_REGISTRY["flight.overhead"] = prior


def test_layout_hint_shows_enum_in_list_fields():
    out = _list_fields()
    assert '"auto" | "ticker" | "hero" | "dashboard"' in out
    assert "scale > 1" in out
    assert "fall back to ticker" in out


def test_layout_hint_matches_validated_enum():
    display_type = OverheadWidget._LIST_FIELD_HINTS["layout"][0]
    advertised = {tok.strip().strip('"') for tok in display_type.split("|")}
    assert advertised == set(_LAYOUTS)
