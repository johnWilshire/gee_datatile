"""gee-datatile: sample an Earth Engine ``ee.Image`` into XYZ Float32 tiles.

Core API::

    from gee_datatile import get_tile

    tile = get_tile(ee_image, z, x, y)  # (256, 256, bands) float32
"""

from gee_datatile.tiles import (
    EmptyTileError,
    GeeDataTileError,
    GeeTileError,
    TileShapeError,
    get_tile,
)

__all__ = [
    "EmptyTileError",
    "GeeDataTileError",
    "GeeTileError",
    "TileShapeError",
    "get_tile",
]
__version__ = "0.1.0"
