"""Demo FastAPI app: build an ee.Image, then sample XYZ tiles via gee_datatile."""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import ee
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import backend.config as config
from gee_datatile import (
    EmptyTileError,
    GeeDataTileError,
    GeeTileError,
    TileShapeError,
    get_tile,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gee_datatile_demo")

app = FastAPI(title="GEE DataTile Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_gee_initialized = False


def init_gee() -> None:
    global _gee_initialized
    if _gee_initialized:
        return
    opt_url = config.GEE_OPT_URL or "https://earthengine-highvolume.googleapis.com"
    if config.GEE_SERVICE_ACCOUNT and config.GEE_KEY_FILE:
        credentials = ee.ServiceAccountCredentials(
            config.GEE_SERVICE_ACCOUNT, config.GEE_KEY_FILE
        )
        ee.Initialize(credentials, project=config.GEE_PROJECT or None, opt_url=opt_url)
        logger.info("GEE initialized with service account (opt_url=%s)", opt_url)
    else:
        ee.Initialize(project=config.GEE_PROJECT or None, opt_url=opt_url)
        logger.info("GEE initialized with default credentials (opt_url=%s)", opt_url)
    _gee_initialized = True


@app.on_event("startup")
def startup_event() -> None:
    init_gee()


def build_ee_image(
    dataset_id: str,
    band_list: list[str],
    date_str: str | None,
    end_date_str: str | None,
    stack: bool,
    stack_count: int,
) -> ee.Image:
    """Reduce a catalog ImageCollection to a single ee.Image for get_tile()."""
    collection = ee.ImageCollection(dataset_id)
    if date_str:
        start_ee = ee.Date(date_str)
        end_ee = ee.Date(end_date_str) if end_date_str else start_ee.advance(1, "day")
        collection = collection.filterDate(start_ee, end_ee)

    collection = collection.select(band_list)

    if stack:
        stacked = collection.sort("system:time_start").limit(stack_count)
        count = stacked.size().getInfo()
        if count == 0:
            raise EmptyTileError(
                f"No images in {dataset_id} for date range {date_str}..{end_date_str}."
            )
        if count < stack_count:
            raise TileShapeError(
                f"Expected {stack_count} hourly images, found {count} in date range."
            )
        return ee.Image(stacked.toBands())

    count = collection.size().getInfo()
    if count == 0:
        raise EmptyTileError(
            f"No images in {dataset_id} for date range {date_str}..{end_date_str}."
        )
    return ee.Image(collection.first())


@app.get("/tiles/{z}/{x}/{y}")
def tile_route(
    z: int,
    x: int,
    y: int,
    dataset: str = Query(
        "MODIS/061/MOD13Q1",
        description="Earth Engine ImageCollection ID",
    ),
    bands: str = Query("NDVI", description="Comma-separated band names"),
    date: str | None = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str | None = Query(None, description="End date YYYY-MM-DD (default start+1 day)"),
    stack: bool = Query(False, description="Stack timesteps with toBands() before tiling"),
    stack_count: int = Query(24, ge=1, le=48),
):
    init_gee()
    band_list = [b.strip() for b in bands.split(",") if b.strip()]
    if not band_list:
        raise HTTPException(status_code=400, detail="At least one band is required")

    expected_bands = stack_count if stack else len(band_list)
    logger.info(
        "[demo] z=%s x=%s y=%s dataset=%s bands=%s date=%s..%s stack=%s expected_bands=%s",
        z, x, y, dataset, band_list, date, end_date, stack, expected_bands,
    )
    try:
        image = build_ee_image(
            dataset, band_list, date, end_date, stack, stack_count
        )
        array = get_tile(
            image,
            z,
            x,
            y,
            tile_size=config.TILE_SIZE,
            expected_bands=expected_bands,
        )
        logger.info(
            "[demo] tile shape=%s min=%.4f max=%.4f",
            array.shape, float(array.min()), float(array.max()),
        )
        band_n = array.shape[2] if array.ndim == 3 else 1
        return Response(
            content=array.tobytes(),
            media_type="application/octet-stream",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
                "X-Tile-Bands": str(band_n),
            },
        )
    except EmptyTileError as err:
        logger.warning("empty tile z=%s x=%s y=%s: %s", z, x, y, err)
        raise HTTPException(status_code=404, detail=str(err)) from err
    except (GeeDataTileError, TileShapeError, ValueError) as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    except GeeTileError as err:
        logger.error("gee tile error z=%s x=%s y=%s: %s", z, x, y, err)
        raise HTTPException(status_code=502, detail=str(err)) from err
    except Exception as err:
        logger.error("tile z=%s x=%s y=%s failed: %s", z, x, y, err)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(err)) from err


@app.exception_handler(HTTPException)
def http_exception_handler(_request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app" if (root_dir / "backend").exists() else "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
