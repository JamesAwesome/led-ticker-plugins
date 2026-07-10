"""Mutable shared state between the poller and the overlay painter, plus the
open/closed refresh + diagnostic log. Paint reads `is_open`/`frame`; the poller
calls `refresh`."""

import logging

import attrs

from led_ticker_storefront.config import StorefrontConfig
from led_ticker_storefront.schedule import evaluate

POLL_INTERVAL_S = 30.0
_log = logging.getLogger("led_ticker_storefront")


@attrs.define
class StorefrontState:
    config: StorefrontConfig
    is_open: bool = False
    frame: int = 0
    _initialized: bool = False

    def refresh(self, now):
        reason = evaluate(self.config.schedule, now)
        open_now = reason is not None
        changed = (not self._initialized) or (open_now != self.is_open)
        self.is_open = open_now
        self._initialized = True
        if changed:
            tz = now.tzinfo
            tz_str = str(tz) if tz else "local"
            when = now.strftime("%H:%M")
            if open_now:
                _log.info(
                    "storefront: OPEN (matched %s; now %s %s)", reason, when, tz_str
                )
            else:
                _log.info(
                    "storefront: CLOSED (no matching range; now %s %s)", when, tz_str
                )
        return changed
