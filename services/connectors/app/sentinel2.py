from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import env_float, env_int
from .fetch import FetchError, request_json
from .persistence import TableBatch
from .providers import BaseProvider, ProviderUnavailable

log = logging.getLogger("connectors.sentinel2")

# Remote COG reads: skip directory listings and cache range requests.
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("VSI_CACHE", "TRUE")

STAC_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"

# Scene classification values that carry no crop signal (nodata, defective, shadow,
# clouds, snow).
UNUSABLE_SCL = {0, 1, 3, 8, 9, 10, 11}
CLOUD_SCL = {3, 8, 9, 10}

SCENES_TABLE = "satellite_scenes"
SCENES_ON_CONFLICT = "id"
INDEX_TABLE = "crop_index_observations"
INDEX_ON_CONFLICT = "scene_id,aoi_name"
CROP_TABLE = "crop_observations"
CROP_ON_CONFLICT = "region,crop,observation_date,satellite_source"


@dataclass(frozen=True)
class AOI:
    name: str
    crop: str
    bbox: tuple[float, float, float, float]  # min lon, min lat, max lon, max lat


DEFAULT_AOIS = (
    AOI("Iowa Corn Belt", "maize", (-93.60, 41.80, -93.20, 42.10)),
    AOI("Kansas Wheat Belt", "wheat", (-97.60, 38.40, -97.20, 38.70)),
    AOI("Central Valley California", "tomatoes", (-120.50, 36.90, -120.10, 37.20)),
    AOI("Parana Soy Belt", "soybean", (-51.20, -24.50, -50.80, -24.20)),
    AOI("Mato Grosso Soy Belt", "soybean", (-56.20, -13.20, -55.80, -12.90)),
    AOI("Punjab Wheat Belt", "wheat", (74.60, 30.60, 75.00, 30.90)),
    AOI("Nile Delta", "rice", (31.20, 30.80, 31.60, 31.10)),
    AOI("Mekong Delta", "rice", (105.60, 9.90, 106.00, 10.20)),
)


@dataclass(frozen=True)
class Sentinel2Config:
    """Sentinel-2 L2A configuration.

    Scenes come from the free AWS Earth Search STAC API (no credentials); the NDVI
    index is computed from the 10 m red/NIR cloud-optimized GeoTIFFs, masked with the
    20 m scene-classification band.
    """

    aois: tuple[AOI, ...] = DEFAULT_AOIS
    lookback_days: int = 90
    cloud_max: float = 25.0
    max_scenes_per_aoi: int = 6
    ndvi_scenes_per_aoi: int = 2
    compute_ndvi: bool = True
    timeout: int = 120
    window_size: int = 256

    @classmethod
    def from_env(cls) -> "Sentinel2Config":
        return cls(
            aois=env_aois(),
            lookback_days=env_int("SENTINEL_LOOKBACK_DAYS", 90),
            cloud_max=env_float("SENTINEL_CLOUD_MAX", 25.0),
            max_scenes_per_aoi=env_int("SENTINEL_MAX_SCENES_PER_AOI", 6),
            ndvi_scenes_per_aoi=env_int("SENTINEL_NDVI_SCENES_PER_AOI", 2),
            compute_ndvi=os.environ.get("SENTINEL_COMPUTE_NDVI", "1").lower() not in {"0", "false", "no"},
            timeout=env_int("SENTINEL_TIMEOUT_SECONDS", 120),
            window_size=env_int("SENTINEL_WINDOW_SIZE", 256),
        )


def env_aois() -> tuple[AOI, ...]:
    raw = os.environ.get("SENTINEL_AOIS")
    if not raw or not raw.strip():
        return DEFAULT_AOIS
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderUnavailable(f"SENTINEL_AOIS is not valid JSON: {exc}") from exc
    aois = []
    for entry in entries:
        bbox = entry["bbox"]
        aois.append(AOI(str(entry["name"]), str(entry.get("crop", "unknown")), tuple(float(value) for value in bbox)))
    return tuple(aois)


class Sentinel2Provider(BaseProvider):
    provider_name = "sentinel2"
    dataset_code = COLLECTION
    primary_table = SCENES_TABLE

    def __init__(self, config: Sentinel2Config | None = None, *, organization_id: str | None = None, search=None) -> None:
        super().__init__(organization_id=organization_id)
        self._config = config or Sentinel2Config()
        self._search_override = search

    def pull(self, *, cursor: str | None = None, limit: int | None = None):
        self.cursor_after = None
        scenes_per_aoi = limit if limit is not None else self._config.max_scenes_per_aoi

        for aoi in self._config.aois:
            items = self._search(aoi)
            if not items:
                log.info("Sentinel-2: no scenes for %s", aoi.name)
                continue
            items.sort(key=lambda item: (item.get("properties", {}).get("eo:cloud_cover", 100.0), ))
            selected = items[: max(1, min(scenes_per_aoi, self._config.max_scenes_per_aoi))]
            pairs = [(row, item) for item in selected if (row := self._scene_row(aoi, item)) is not None]
            if pairs:
                log.info("Sentinel-2: %s -> %s scenes", aoi.name, len(pairs))
                yield TableBatch(SCENES_TABLE, self.stamp([row for row, _ in pairs]), SCENES_ON_CONFLICT)

            if not self._config.compute_ndvi:
                continue
            index_rows = []
            crop_rows = []
            crop_keys: set[tuple] = set()
            for row, item in pairs[: self._config.ndvi_scenes_per_aoi]:
                stats = compute_ndvi_stats(
                    item.get("assets") or {},
                    aoi.bbox,
                    window_size=self._config.window_size,
                )
                if stats is None:
                    continue
                index_rows.append(
                    {
                        "source": self.provider_name,
                        "scene_id": row["id"],
                        "aoi_name": aoi.name,
                        "crop": aoi.crop,
                        "observed_at": row["acquired_at"],
                        "observation_date": row["acquired_at"][:10],
                        "ndvi_mean": stats["ndvi_mean"],
                        "ndvi_p10": stats["ndvi_p10"],
                        "ndvi_p90": stats["ndvi_p90"],
                        "ndvi_std": stats["ndvi_std"],
                        "red_mean": stats["red_mean"],
                        "nir_mean": stats["nir_mean"],
                        "valid_pixel_percentage": stats["valid_pixel_percentage"],
                        "cloud_pixel_percentage": stats["cloud_pixel_percentage"],
                        "health_score": round(_health(stats["ndvi_mean"]), 5),
                    }
                )
                crop_key = (aoi.name, aoi.crop, row["acquired_at"][:10], COLLECTION)
                if crop_key in crop_keys:
                    # Two scenes can share a date for one AOI; keep the clearest one.
                    continue
                crop_keys.add(crop_key)
                crop_rows.append(
                    {
                        "region": aoi.name,
                        "crop": aoi.crop,
                        "ndvi": stats["ndvi_mean"],
                        "health_score": round(_health(stats["ndvi_mean"]), 5),
                        "cloud_coverage": row["cloud_cover"],
                        "satellite_source": COLLECTION,
                        "observation_date": row["acquired_at"][:10],
                    }
                )
            if index_rows:
                yield TableBatch(INDEX_TABLE, self.stamp(index_rows), INDEX_ON_CONFLICT)
            if crop_rows:
                yield TableBatch(CROP_TABLE, self.stamp(crop_rows), CROP_ON_CONFLICT)

    def _search(self, aoi: AOI) -> list[dict]:
        if self._search_override is not None:
            return self._search_override(aoi)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self._config.lookback_days)
        payload = {
            "collections": [COLLECTION],
            "bbox": list(aoi.bbox),
            "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "limit": 50,
            "query": {"eo:cloud_cover": {"lt": self._config.cloud_max}},
        }
        try:
            response = request_json(STAC_SEARCH_URL, method="POST", payload=payload, timeout=self._config.timeout)
        except FetchError as exc:
            raise ProviderUnavailable(f"Sentinel-2 STAC search failed for {aoi.name}: {exc}") from exc
        features = (response or {}).get("features") or []
        return [feature for feature in features if isinstance(feature, dict)]

    def _scene_row(self, aoi: AOI, item: dict) -> dict | None:
        item_id = item.get("id")
        properties = item.get("properties") or {}
        if not item_id:
            return None
        acquired_at = properties.get("datetime")
        assets = item.get("assets") or {}
        return {
            "id": item_id,
            "source": self.provider_name,
            "collection": item.get("collection") or COLLECTION,
            "platform": properties.get("platform"),
            "aoi_name": aoi.name,
            "crop": aoi.crop,
            "acquired_at": acquired_at,
            "cloud_cover": properties.get("eo:cloud_cover"),
            "mgrs_tile": properties.get("grid:code") or properties.get("s2:tile_id"),
            "epsg": properties.get("proj:epsg"),
            "bbox": item.get("bbox"),
            "geometry": item.get("geometry"),
            "vegetation_percentage": properties.get("s2:vegetation_percentage"),
            "thumbnail_url": (assets.get("thumbnail") or {}).get("href"),
            "assets": {
                name: {
                    "href": asset.get("href"),
                    "type": asset.get("type"),
                    "title": asset.get("title"),
                    "bands": asset.get("raster:bands"),
                }
                for name, asset in assets.items()
                if name in {"red", "nir", "scl", "visual", "thumbnail", "blue", "green", "swir16", "swir22"}
            },
        }


def _health(ndvi: float | None) -> float:
    if ndvi is None:
        return 0.0
    return max(0.0, min(1.0, (ndvi - 0.1) / 0.8))


def compute_ndvi_stats(assets: dict, bbox: tuple[float, float, float, float], *, window_size: int = 256) -> dict | None:
    """Compute NDVI statistics for an AOI from Sentinel-2 L2A COG assets."""
    try:
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import transform_bounds
        from rasterio.windows import Window, from_bounds
    except ImportError:
        log.warning("rasterio/numpy not installed; skipping NDVI computation")
        return None

    red_asset = assets.get("red") or {}
    nir_asset = assets.get("nir") or {}
    if not red_asset.get("href") or not nir_asset.get("href"):
        return None

    try:
        with rasterio.open(red_asset["href"]) as source:
            window = _window(source, bbox, Window, from_bounds, transform_bounds)
            shape = _out_shape(window, window_size)
            red = source.read(1, window=window, out_shape=shape, resampling=Resampling.average).astype("float32")
            red_scale, red_offset = _scale_offset(red_asset)
        with rasterio.open(nir_asset["href"]) as source:
            window = _window(source, bbox, Window, from_bounds, transform_bounds)
            shape = _out_shape(window, window_size)
            nir = source.read(1, window=window, out_shape=shape, resampling=Resampling.average).astype("float32")
            nir_scale, nir_offset = _scale_offset(nir_asset)
    except Exception as exc:  # rasterio raises a range of GDAL errors for remote reads
        log.warning("NDVI read failed: %s", exc)
        return None

    scl = None
    scl_asset = assets.get("scl") or {}
    if scl_asset.get("href"):
        try:
            with rasterio.open(scl_asset["href"]) as source:
                window = _window(source, bbox, Window, from_bounds, transform_bounds)
                shape = _out_shape(window, window_size)
                scl = source.read(1, window=window, out_shape=(red.shape[0], red.shape[1]), resampling=Resampling.nearest)
        except Exception as exc:
            log.warning("SCL read failed: %s", exc)

    red = red * red_scale + red_offset
    nir = nir * nir_scale + nir_offset

    valid = (red > 0) & (nir > 0)
    cloud_pixels = 0
    total_pixels = int(red.size)
    if scl is not None:
        usable = ~np.isin(scl, list(UNUSABLE_SCL))
        cloud_pixels = int(np.isin(scl, list(CLOUD_SCL)).sum())
        valid = valid & usable

    valid_pixels = int(valid.sum())
    if valid_pixels == 0:
        return None
    ndvi = np.zeros_like(red)
    ndvi[valid] = (nir[valid] - red[valid]) / (nir[valid] + red[valid] + 1e-6)
    values = ndvi[valid]
    return {
        "ndvi_mean": round(float(values.mean()), 5),
        "ndvi_p10": round(float(np.percentile(values, 10)), 5),
        "ndvi_p90": round(float(np.percentile(values, 90)), 5),
        "ndvi_std": round(float(values.std()), 5),
        "red_mean": round(float(red[valid].mean()), 5),
        "nir_mean": round(float(nir[valid].mean()), 5),
        "valid_pixel_percentage": round(100.0 * valid_pixels / total_pixels, 3),
        "cloud_pixel_percentage": round(100.0 * cloud_pixels / total_pixels, 3),
    }


def _window(source, bbox, Window, from_bounds, transform_bounds):
    """Window covering an AOI inside a raster, reprojecting the AOI bounds when needed.

    Sentinel-2 COGs are delivered in the tile's UTM zone, so a WGS84 degree bbox must be
    transformed before it can be compared with the raster transform.
    """
    bounds = bbox
    if source.crs is not None and source.crs.to_epsg() not in (None, 4326):
        bounds = transform_bounds("EPSG:4326", source.crs, *bbox, densify_pts=21)
    window = from_bounds(*bounds, transform=source.transform)
    raster_window = Window(0, 0, source.width, source.height)
    window = window.intersection(raster_window)
    if window.width < 1 or window.height < 1:
        return None
    return window


def _out_shape(window, max_size: int) -> tuple[int, int]:
    largest = max(window.width, window.height)
    scale = min(1.0, max_size / largest) if largest else 1.0
    return (max(1, int(round(window.height * scale))), max(1, int(round(window.width * scale))))


def _scale_offset(asset: dict) -> tuple[float, float]:
    bands = asset.get("raster:bands") or [{}]
    scale = bands[0].get("scale", 1.0) or 1.0
    offset = bands[0].get("offset", 0.0) or 0.0
    return float(scale), float(offset)
