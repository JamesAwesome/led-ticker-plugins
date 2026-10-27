"""`--list-fields` hints for the plugin-owned `layout` field (#93).

Core carries no name-keyed hint for `layout`, so each widget declares its own
`_LIST_FIELD_HINTS`. The drift guard keeps the advertised enum equal to what
`validate_config` actually accepts, in both directions.
"""

import pytest

from led_ticker_baseball.attendance import (
    _ATTENDANCE_VALID_LAYOUTS,
    MLBAttendanceMonitor,
)
from led_ticker_baseball.promotions import _PROMO_VALID_LAYOUTS, MLBPromotionsMonitor
from led_ticker_baseball.scores import _MLB_VALID_LAYOUTS, MLBScoreMonitor
from led_ticker_baseball.standings import _STANDINGS_VALID_LAYOUTS, MLBStandingsMonitor
from led_ticker_baseball.statcast import _STATCAST_VALID_LAYOUTS, MLBStatcastMonitor

_CASES = [
    (MLBScoreMonitor, _MLB_VALID_LAYOUTS),
    (MLBStandingsMonitor, _STANDINGS_VALID_LAYOUTS),
    (MLBPromotionsMonitor, _PROMO_VALID_LAYOUTS),
    (MLBStatcastMonitor, _STATCAST_VALID_LAYOUTS),
    (MLBAttendanceMonitor, _ATTENDANCE_VALID_LAYOUTS),
]


@pytest.mark.parametrize(
    ("widget_cls", "valid_layouts"), _CASES, ids=lambda v: getattr(v, "__name__", None)
)
def test_layout_hint_matches_validated_enum(widget_cls, valid_layouts):
    display_type, description, default = widget_cls._LIST_FIELD_HINTS["layout"]
    advertised = {tok.strip().strip('"') for tok in display_type.split("|")}
    assert advertised == set(valid_layouts)
    assert description
    assert default == '"auto"'


@pytest.mark.parametrize(
    ("widget_cls", "valid_layouts"), _CASES, ids=lambda v: getattr(v, "__name__", None)
)
def test_list_fields_shows_layout_enum(widget_cls, valid_layouts):
    from led_ticker.app.factories import _list_widget_fields
    from led_ticker.widgets import _WIDGET_REGISTRY

    name = f"baseball.{widget_cls.__name__}"
    _WIDGET_REGISTRY[name] = widget_cls
    try:
        out = _list_widget_fields(name)
    finally:
        _WIDGET_REGISTRY.pop(name, None)
    assert " | ".join(f'"{v}"' for v in valid_layouts) in out
