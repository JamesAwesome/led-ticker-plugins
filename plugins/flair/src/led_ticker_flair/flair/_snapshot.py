"""Geometry of the live canvas + a geometry-keyed snapshot cache, shared by
flair.interlock and flair.blinds (laser keeps its own copy).

``Geometry`` is in REAL pixels. ``SnapshotCache.take`` draws a widget into
one of two reusable ``Raster`` slots (``snapshot_into`` handles the
ScaledCanvas wrapping); rasters are re-allocated only when the geometry
changes.
"""

from dataclasses import dataclass
from typing import Any

from led_ticker.plugin import is_scaled, unwrap_to_real

from ._raster import Raster, snapshot_into


@dataclass(frozen=True)
class Geometry:
    width: int
    height: int
    scale: int
    y_offset_real: int
    content_h_real: int


def geometry_of(canvas: Any) -> Geometry:
    if is_scaled(canvas):
        real = unwrap_to_real(canvas)
        return Geometry(
            real.width,
            real.height,
            canvas.scale,
            canvas.y_offset_real,
            canvas.content_height * canvas.scale,
        )
    return Geometry(canvas.width, canvas.height, 1, 0, canvas.height)


class SnapshotCache:
    def __init__(self) -> None:
        self._rasters: list[Raster | None] = [None, None]
        self._key: Geometry | None = None

    def take(self, canvas: Any, widget: Any, cursor_pos: int, slot: int) -> Raster:
        geo = geometry_of(canvas)
        if self._key != geo:
            self._rasters = [None, None]
            self._key = geo
        raster = self._rasters[slot]
        if raster is None:
            raster = Raster(geo.width, geo.height)
            self._rasters[slot] = raster
        snapshot_into(raster, canvas, widget, cursor_pos)
        return raster
