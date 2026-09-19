from __future__ import annotations

from app.maritime import DigitrafficAISProvider, MaritimeConfig, ship_type_label

VESSELS = [
    {
        "mmsi": 244730469,
        "name": "TEST VESSEL",
        "callSign": "ABC1",
        "imo": 9272773,
        "shipType": 70,
        "destination": "NLRTM",
        "draught": 79,
        "timestamp": 1789684296181,
    },
    {"mmsi": None, "name": "BROKEN"},
]

LOCATIONS = {
    "type": "FeatureCollection",
    "dataUpdatedTime": "2026-09-18T22:21:49Z",
    "features": [
        {
            "mmsi": 244730469,
            "geometry": {"type": "Point", "coordinates": [21.782078, 57.680797]},
            "properties": {
                "mmsi": 244730469,
                "sog": 7.3,
                "cog": 247.3,
                "heading": 247,
                "navStat": 0,
                "timestampExternal": 1789755304301,
            },
        },
        {"mmsi": 999, "geometry": {"coordinates": []}, "properties": {"timestampExternal": 1}},
    ],
}


def _provider(monkeypatch) -> DigitrafficAISProvider:
    def fake_request(url, *, timeout=60, **kwargs):
        return VESSELS if url.endswith("/vessels") else LOCATIONS

    monkeypatch.setattr("app.maritime.request_json", fake_request)
    return DigitrafficAISProvider(MaritimeConfig(), organization_id="org-1")


def test_maps_vessels_and_positions(monkeypatch):
    batches = list(_provider(monkeypatch).pull())
    vessels = next(batch for batch in batches if batch.table == "vessels")
    positions = next(batch for batch in batches if batch.table == "vessel_positions")

    assert len(vessels.rows) == 1
    vessel = vessels.rows[0]
    assert vessel["mmsi"] == 244730469
    assert vessel["ship_type_label"] == "cargo"
    assert vessel["draught"] == 7.9
    assert vessel["destination"] == "NLRTM"
    assert vessel["last_seen_at"].startswith("2026-")
    assert vessel["organization_id"] == "org-1"

    assert len(positions.rows) == 1
    position = positions.rows[0]
    assert position["latitude"] == 57.680797
    assert position["longitude"] == 21.782078
    assert position["speed_knots"] == 7.3
    assert position["nav_status_label"] == "under way using engine"
    assert vessels.on_conflict == "mmsi"
    assert positions.on_conflict == "source,mmsi,observed_at"


def test_ship_type_labels():
    assert ship_type_label(70) == "cargo"
    assert ship_type_label(80) == "tanker"
    assert ship_type_label(52) == "tug"
    assert ship_type_label(None) is None
