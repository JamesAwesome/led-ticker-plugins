"""Mutable shared state between the poller and the overlay painter, plus the
open/closed refresh + diagnostic log. Paint reads `is_open`/`frame`; the poller
calls `refresh`."""

import logging
from datetime import timedelta

import attrs

from led_ticker_storefront.config import StorefrontConfig
from led_ticker_storefront.schedule import evaluate, next_change

POLL_INTERVAL_S = 30.0
_log = logging.getLogger("led_ticker_storefront")


@attrs.define
class StorefrontState:
    config: StorefrontConfig
    is_open: bool = False
    frame: int = 0
    _initialized: bool = False

    def refresh(self, now):
        exceptions = getattr(self.config, "exceptions", None)
        reason = evaluate(self.config.schedule, now, exceptions)
        open_now = reason is not None
        changed = (not self._initialized) or (open_now != self.is_open)
        self.is_open = open_now
        self._initialized = True
        if changed:
            tz = now.tzinfo
            tz_str = str(tz) if tz else "local"
            when = now.strftime("%H:%M")
            clause = ""
            nc = next_change(self.config.schedule, now, exceptions)
            if nc is not None:
                word = "closes" if open_now else "opens"
                if nc.date() == now.date():
                    suffix = ""
                elif nc.date() == now.date() + timedelta(days=1):
                    suffix = " tomorrow"
                else:
                    suffix = f" {nc.strftime('%a')}"
                clause = f"; {word} {nc.strftime('%H:%M')}{suffix}"
            if open_now:
                _log.info(
                    "storefront: OPEN (matched %s%s; now %s %s)",
                    reason,
                    clause,
                    when,
                    tz_str,
                )
            else:
                _log.info(
                    "storefront: CLOSED (no matching range%s; now %s %s)",
                    clause,
                    when,
                    tz_str,
                )
        return changed
