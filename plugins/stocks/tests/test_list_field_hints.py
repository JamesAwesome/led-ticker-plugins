"""`--list-fields stocks.ticker` shows this widget's own `layout` hint.

Core carries no name-keyed hint for plugin-owned field names, so the widget
class supplies `_LIST_FIELD_HINTS` (#93). The advertised enum must equal the
registered layouts, in both directions.
"""

from led_ticker_stocks.layouts import LAYOUTS
from led_ticker_stocks.ticker import StocksTicker


def _list_fields() -> str:
    # Register into core's widget registry the way entry-point discovery
    # would, then drive core's introspection path directly.
    from led_ticker.app.factories import _list_widget_fields
    from led_ticker.widgets import _WIDGET_REGISTRY

    prior = _WIDGET_REGISTRY.get("stocks.ticker")
    _WIDGET_REGISTRY["stocks.ticker"] = StocksTicker
    try:
        return _list_widget_fields("stocks.ticker")
    finally:
        if prior is None:
            _WIDGET_REGISTRY.pop("stocks.ticker", None)
        else:
            _WIDGET_REGISTRY["stocks.ticker"] = prior


def test_layout_hint_matches_registered_layouts():
    display_type = StocksTicker._LIST_FIELD_HINTS["layout"][0]
    advertised = {tok.strip().strip('"') for tok in display_type.split("|")}
    assert advertised == set(LAYOUTS)


def test_list_fields_shows_layout_enum_and_default():
    out = _list_fields()
    assert '"card" | "crawl" | "dashboard"' in out
    assert "chosen by panel width" in out


def test_list_fields_shows_width_thresholds():
    from led_ticker_stocks.layouts import CRAWL_MAX_WIDTH, DASHBOARD_MIN_WIDTH

    assert (CRAWL_MAX_WIDTH, DASHBOARD_MIN_WIDTH) == (160, 400)
    out = _list_fields()
    assert f"crawl <= {CRAWL_MAX_WIDTH} px" in out
    assert f"dashboard >= {DASHBOARD_MIN_WIDTH} px" in out
    assert "160" in out and "400" in out
