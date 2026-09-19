from __future__ import annotations

from types import SimpleNamespace

from app.sentinel2 import AOI, Sentinel2Config, Sentinel2Provider, _health, _out_shape

ITEMS = [
    {
        "id": "S2C_TILE_20260629_0_L2A",
        "collection": "sentinel-2-l2a",
        "bbox": [-97.6, 38.4, -97.2, 38.7],
        "geometry": {"type": "Polygon", "coordinates": []},
        "properties": {
            "datetime": "2026-06-29T17:12:05.902000Z",
            "platform": "sentinel-2c",
            "eo:cloud_cover": 8.48,
            "grid:code": "MGRS-14SPB",
            "proj:epsg": 32614,
            "s2:vegetation_percentage": 76.2,
        },
        "assets": {
            "red": {"href": "https://example/B04.tif", "type": "image/tiff", "raster:bands": [{"scale": 0.0001, "offset": -0.1}]},
            "thumbnail": {"href": "https://example/preview.jpg", "type": "image/jpeg"},
        },
    },
    {
        "id": "S2C_TILE_20260619_0_L2A",
        "collection": "sentinel-2-l2a",
        "bbox": [-97.6, 38.4, -97.2, 38.7],
        "properties": {"datetime": "2026-06-19T17:12:05.902000Z", "eo:cloud_cover": 2.1},
        "assets": {"red": {"href": "https://example/B04b.tif", "type": "image/tiff"}},
    },
]


def test_scenes_are_ranked_by_cloud_cover_and_skip_ndvi():
    config = Sentinel2Config(
        aois=(AOI("Test AOI", "wheat", (-97.6, 38.4, -97.2, 38.7)),),
        max_scenes_per_aoi=2,
        compute_ndvi=False,
    )
    provider = Sentinel2Provider(config, organization_id="org-1", search=lambda aoi: list(ITEMS))

    batches = list(provider.pull())

    assert len(batches) == 1
    assert batches[0].table == "satellite_scenes"
    assert batches[0].on_conflict == "id"
    rows = batches[0].rows
    assert [row["id"] for row in rows] == ["S2C_TILE_20260619_0_L2A", "S2C_TILE_20260629_0_L2A"]
    scene = rows[1]
    assert scene["aoi_name"] == "Test AOI"
    assert scene["crop"] == "wheat"
    assert scene["acquired_at"] == "2026-06-29T17:12:05.902000Z"
    assert scene["cloud_cover"] == 8.48
    assert scene["organization_id"] == "org-1"
    assert scene["assets"]["red"]["href"] == "https://example/B04.tif"
    assert "thumbnail" in scene["assets"]


def test_scene_limit_respects_configured_maximum():
    config = Sentinel2Config(
        aois=(AOI("Test AOI", "wheat", (-97.6, 38.4, -97.2, 38.7)),),
        max_scenes_per_aoi=1,
        compute_ndvi=False,
    )
    provider = Sentinel2Provider(config, search=lambda aoi: list(ITEMS))
    rows = list(provider.pull())[0].rows
    assert len(rows) == 1


def test_out_shape_scales_longest_side():
    window = SimpleNamespace(width=1000.0, height=500.0)
    assert _out_shape(window, 256) == (128, 256)
    small = SimpleNamespace(width=100.0, height=50.0)
    assert _out_shape(small, 256) == (50, 100)


def test_health_score_maps_ndvi_to_unit_range():
    assert _health(0.1) == 0.0
    assert _health(0.5) == 0.5
    assert _health(0.9) == 1.0
    assert _health(None) == 0.0


SAME_DAY_ITEMS = [
    {
        "id": "S2C_TILE_20260629_A",
        "collection": "sentinel-2-l2a",
        "properties": {"datetime": "2026-06-29T17:12:05Z", "eo:cloud_cover": 4.0},
        "assets": {},
    },
    {
        "id": "S2C_TILE_20260629_B",
        "collection": "sentinel-2-l2a",
        "properties": {"datetime": "2026-06-29T10:04:00Z", "eo:cloud_cover": 9.0},
        "assets": {},
    },
]

FAKE_STATS = {
    "ndvi_mean": 0.62,
    "ndvi_p10": 0.41,
    "ndvi_p90": 0.83,
    "ndvi_std": 0.1,
    "red_mean": 0.05,
    "nir_mean": 0.31,
    "valid_pixel_percentage": 95.0,
    "cloud_pixel_percentage": 2.0,
}


def test_same_day_scenes_collapse_to_one_crop_observation(monkeypatch):
    """crop_observations is keyed by day: two scenes on one date must not collide in a batch."""
    monkeypatch.setattr("app.sentinel2.compute_ndvi_stats", lambda assets, bbox, window_size=256: dict(FAKE_STATS))
    config = Sentinel2Config(
        aois=(AOI("Test AOI", "wheat", (-97.6, 38.4, -97.2, 38.7)),),
        max_scenes_per_aoi=2,
        ndvi_scenes_per_aoi=2,
        compute_ndvi=True,
    )
    provider = Sentinel2Provider(config, organization_id="org-1", search=lambda aoi: list(SAME_DAY_ITEMS))

    batches = {batch.table: batch for batch in provider.pull()}

    assert len(batches["crop_index_observations"].rows) == 2
    assert len(batches["crop_observations"].rows) == 1
    crop = batches["crop_observations"].rows[0]
    assert crop["region"] == "Test AOI"
    assert crop["observation_date"] == "2026-06-29"
    assert crop["ndvi"] == 0.62
    assert crop["satellite_source"] == "sentinel-2-l2a"
