"""Extract raw Float32 XYZ tiles from an Earth Engine ``ee.Image``."""

from __future__ import annotations

import logging
import time

import ee
import numpy as np

from gee_datatile.geo import ORIGIN_SHIFT, wrap_tile_x, xyz_to_bbox_3857

logger = logging.getLogger(__name__)


class GeeDataTileError(TypeError):
    """Raised when ``get_tile`` is given something other than an ``ee.Image``."""


class GeeTileError(Exception):
    """Base class for tile sampling failures."""


class EmptyTileError(GeeTileError):
    """Tile request succeeded but returned no usable pixels."""


class TileShapeError(GeeTileError):
    """Tile payload has unexpected dimensions or band count."""


def _require_image(image: object) -> ee.Image:
    if isinstance(image, ee.ImageCollection):
        raise GeeDataTileError(
            "get_tile() expects ee.Image, not ee.ImageCollection. "
            "Reduce the collection first with .first(), .mosaic(), or .toBands() "
            "(e.g. NASA/GSFC/MERRA/flx/2 is a collection)."
        )
    if not isinstance(image, ee.Image):
        raise GeeDataTileError(
            f"get_tile() expects ee.Image, got {type(image)!r}."
        )
    return image


def _resize_hwc(arr: np.ndarray, tile_size: int) -> np.ndarray:
    src_h, src_w = arr.shape[:2]
    if src_h == tile_size and src_w == tile_size:
        return arr
    row_idx = np.linspace(0, src_h - 1, tile_size).astype(int)
    col_idx = np.linspace(0, src_w - 1, tile_size).astype(int)
    if arr.ndim == 2:
        return arr[np.ix_(row_idx, col_idx)]
    return arr[np.ix_(row_idx, col_idx, np.arange(arr.shape[2]))]


def _as_hwc(arr: np.ndarray, tile_size: int, expected_bands: int | None) -> np.ndarray:
    if arr.ndim == 3:
        data = arr
    elif arr.ndim == 2:
        data = np.expand_dims(arr, axis=-1)
    elif arr.ndim == 1:
        if expected_bands is None:
            if arr.size % (tile_size * tile_size) != 0:
                raise TileShapeError(
                    f"Flat buffer length {arr.size} is not divisible by "
                    f"{tile_size * tile_size}; pass expected_bands to disambiguate."
                )
            expected_bands = arr.size // (tile_size * tile_size)
        expected = tile_size * tile_size * expected_bands
        if arr.size != expected:
            raise TileShapeError(
                f"Expected {expected} float32 values "
                f"({tile_size}x{tile_size}x{expected_bands}), got {arr.size}."
            )
        data = arr.reshape((tile_size, tile_size, expected_bands))
    else:
        raise TileShapeError(f"Cannot interpret array shape {arr.shape} as a tile.")

    if data.shape[0] != tile_size or data.shape[1] != tile_size:
        raise TileShapeError(
            f"Expected spatial shape ({tile_size}, {tile_size}), got {data.shape[:2]}."
        )
    if expected_bands is not None and data.shape[2] != expected_bands:
        raise TileShapeError(
            f"Expected {expected_bands} bands, got {data.shape[2]}."
        )
    return data


def _parse_compute_pixels(
    raw: object, tile_size: int, expected_bands: int | None
) -> np.ndarray:
    if isinstance(raw, np.ndarray):
        if raw.dtype.names:
            data = np.stack([raw[name] for name in raw.dtype.names], axis=-1)
        else:
            data = raw.astype(np.float32, copy=False)
        return _as_hwc(data, tile_size, expected_bands)

    arr = np.array(raw)
    if arr.dtype.names:
        data = np.stack([arr[name] for name in arr.dtype.names], axis=-1)
        return _as_hwc(data, tile_size, expected_bands)

    raw_bytes = raw if isinstance(raw, (bytes, bytearray, memoryview)) else bytes(raw)
    if not raw_bytes:
        raise EmptyTileError("computePixels returned an empty byte buffer.")
    data = np.frombuffer(raw_bytes, dtype=np.float32)
    return _as_hwc(data, tile_size, expected_bands)


def _validate_tile_data(data: np.ndarray, z: int, x: int, y: int) -> np.ndarray:
    if not np.isfinite(data).any():
        raise EmptyTileError(
            f"Tile z={z} x={x} y={y} contains no finite pixel values."
        )
    return data


def get_tile(
    image: ee.Image,
    z: int,
    x: int,
    y: int,
    *,
    tile_size: int = 256,
    crs: str = "EPSG:3857",
    expected_bands: int | None = None,
) -> np.ndarray:
    """Sample an Earth Engine image into a Web Mercator XYZ DataTile.

    Parameters
    ----------
    image:
        A computed ``ee.Image`` (not an ``ee.ImageCollection``).
    z, x, y:
        Standard XYZ tile indices (same as OpenLayers / OSM).
    tile_size:
        Output width and height in pixels.
    crs:
        Grid CRS. Default ``EPSG:3857`` matches web-map clients.
    expected_bands:
        If set, validate the returned band dimension. Recommended when you
        know the band count (e.g. 24 hourly ``toBands()`` stack).

    Returns
    -------
    numpy.ndarray
        C-contiguous ``float32`` array with shape ``(tile_size, tile_size, bands)``.

    Raises
    ------
    GeeDataTileError
        If ``image`` is not an ``ee.Image``.
    EmptyTileError
        If sampling returns no usable pixels.
    TileShapeError
        If the payload shape or band count is wrong.
    """
    image = _require_image(image).toFloat()
    x = wrap_tile_x(z, x)
    n = 1 << int(z)
    if y < 0 or y >= n:
        raise ValueError(f"Tile y={y} is outside 0..{n - 1} at zoom {z}")

    min_x, min_y, max_x, max_y = xyz_to_bbox_3857(z, x, y)
    min_x = max(min_x, -ORIGIN_SHIFT)
    max_x = min(max_x, ORIGIN_SHIFT)
    min_y = max(min_y, -ORIGIN_SHIFT)
    max_y = min(max_y, ORIGIN_SHIFT)
    if min_x >= max_x or min_y >= max_y:
        raise ValueError(f"Tile z={z} x={x} y={y} has empty mercator bounds")

    scale_x = (max_x - min_x) / tile_size
    scale_y = (max_y - min_y) / tile_size
    request = {
        "expression": image,
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": tile_size, "height": tile_size},
            "affineTransform": {
                "scaleX": scale_x,
                "shearX": 0,
                "translateX": min_x,
                "shearY": 0,
                "scaleY": -scale_y,
                "translateY": max_y,
            },
            "crsCode": crs,
        },
    }

    last_err: Exception | None = None
    raw = None
    for attempt in range(4):
        try:
            raw = ee.data.computePixels(request)
            last_err = None
            break
        except Exception as err:
            last_err = err
            logger.warning(
                "computePixels z=%s x=%s y=%s attempt %s failed: %s",
                z, x, y, attempt + 1, err,
            )
            time.sleep(0.2 * (2**attempt))
    if last_err is not None or raw is None:
        raise GeeTileError(
            f"computePixels failed for z={z} x={x} y={y}: {last_err}"
        ) from last_err

    data = _parse_compute_pixels(raw, tile_size, expected_bands)
    if data.shape[0] != tile_size or data.shape[1] != tile_size:
        data = _resize_hwc(data, tile_size)
    _validate_tile_data(data, z, x, y)
    data = np.ascontiguousarray(
        np.nan_to_num(data.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    )

    logger.debug(
        "tile z=%s x=%s y=%s shape=%s min=%.4f max=%.4f",
        z, x, y, data.shape, float(np.min(data)), float(np.max(data)),
    )
    return data
