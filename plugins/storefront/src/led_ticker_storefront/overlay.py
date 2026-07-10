"""Overlay lifecycle: read [storefront], evaluate the schedule on a poll loop,
and paint the active badge every frame. Registered by __init__.register via
api.on_startup(startup) + api.overlay(paint)."""

import asyncio
import logging
from datetime import datetime

from led_ticker.plugin import plugin_config_block, spawn_tracked

from led_ticker_storefront.config import enabled, parse_config
from led_ticker_storefront.render import draw_badge
from led_ticker_storefront.state import POLL_INTERVAL_S, StorefrontState

_log = logging.getLogger("led_ticker_storefront")


class StorefrontOverlay:
    def __init__(self):
        self.state: StorefrontState | None = None

    def _clock(self):
        assert self.state is not None  # only called after startup sets state
        return datetime.now(self.state.config.tz)

    def startup(self, ctx):
        block = plugin_config_block(ctx.config, "storefront")
        if not enabled(block):
            _log.debug("storefront: no [storefront] block; overlay disabled")
            return
        self.state = StorefrontState(config=parse_config(block))
        self.state.refresh(self._clock())  # eager first evaluation
        self._spawn_poller()

    def _spawn_poller(self):
        spawn_tracked(self._poll())

    async def _poll(self):
        assert self.state is not None  # spawned only after startup sets state
        while True:
            await asyncio.sleep(POLL_INTERVAL_S)
            try:
                self.state.refresh(self._clock())
            except Exception:
                _log.exception("storefront: poll refresh failed")

    def paint(self, canvas):
        if self.state is None:
            return
        self.state.frame += 1
        cfg = self.state.config
        badge = cfg.open if self.state.is_open else cfg.closed
        draw_badge(canvas, cfg, badge, self.state.frame)
