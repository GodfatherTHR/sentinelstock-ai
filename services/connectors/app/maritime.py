from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import env_int
from .fetch import FetchError, request_json
from .persistence import TableBatch
from .providers import BaseProvider, ProviderUnavailable

log = logging.getLogger("connectors.maritime")

VESSELS_URL = "https://meri.digitraffic.fi/api/ais/v1/vessels"
LOCATIONS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"

NAV_STATUS_LABELS = {
    0: "under way using engine",
    1: "at anchor",
    2: "not under command",
    3: "restricted manoeuvrability",
    4: "constrained by draught",
    5: "moored",
    6: "aground",
    7: "fishing",
    8: "under way sailing",
    9: "reserved (hsc)",
    10: "reserved (wig)",
    11: "towing astern",
    12: "pushing ahead",
    13: "reserved",
    14: "ais-sart",
    15: "undefined",
}

VESSELS_TABLE = "vessels"
VESSELS_ON_CONFLICT = "mmsi"
POSITIONS_TABLE = "vessel_positions"
POSITIONS_ON_CONFLICT = "source,mmsi,observed_at"


@dataclass(frozen=True)
class MaritimeConfig:
    """Live AIS snapshot configuration.

    Digitraffic (Fintraffic, Finland) publishes open AIS data under CC BY 4.0 with no
    authentication: vessel particulars plus live positions. The provider is a snapshot
    source, so runs are idempotent on ``(source, mmsi, observed_at)``.
    """

    timeout: int = 60
    batch_rows: int = 1000
    max_vessels: int = 5000

    @classmethod
    def from_env(cls) -> "MaritimeConfig":
        return cls(
            timeout=env_int("AIS_TIMEOUT_SECONDS", 60),
            batch_rows=env_int("AIS_BATCH_ROWS", 1000),
            max_vessels=env_int("AIS_MAX_VESSELS", 5000),
        )


class DigitrafficAISProvider(BaseProvider):
    provider_name = "ship_tracking"
    dataset_code = "digitraffic-ais"
    primary_table = VESSELS_TABLE

    def __init__(self, config: MaritimeConfig | None = None, *, organization_id: str | None = None) -> None:
        super().__init__(organization_id=organization_id)
        self._config = config or MaritimeConfig()

    def pull(self, *, cursor: str | None = None, limit: int | None = None):
        budget = self._config.max_vessels if limit is None else min(limit, self._config.max_vessels)
        self.cursor_after = None

        vessels = self._fetch(VESSELS_URL)
        positions = self._fetch(LOCATIONS_URL)

        vessel_rows = []
        if isinstance(vessels, list):
            for vessel in vessels[:budget]:
                row = self._vessel_row(vessel)
                if row is not None:
                    vessel_rows.append(row)
        if vessel_rows:
            log.info("AIS: %s vessels", len(vessel_rows))
            yield TableBatch(VESSELS_TABLE, self.stamp(vessel_rows), VESSELS_ON_CONFLICT)

        features = positions.get("features") if isinstance(positions, dict) else positions
        position_rows = []
        if isinstance(features, list):
            for feature in features[:budget]:
                row = self._position_row(feature)
                if row is not None:
                    position_rows.append(row)
        if position_rows:
            log.info("AIS: %s live positions", len(position_rows))
            yield TableBatch(POSITIONS_TABLE, self.stamp(position_rows), POSITIONS_ON_CONFLICT)

    def _fetch(self, url: str):
        try:
            return request_json(url, timeout=self._config.timeout)
        except FetchError as exc:
            raise ProviderUnavailable(f"AIS request failed: {exc}") from exc

    def _vessel_row(self, vessel: dict) -> dict | None:
        mmsi = _as_int(vessel.get("mmsi"))
        if mmsi is None:
            return None
        ship_type = _as_int(vessel.get("shipType"))
        return {
            "mmsi": mmsi,
            "source": self.provider_name,
            "name": (vessel.get("name") or "").strip() or None,
            "call_sign": (vessel.get("callSign") or "").strip() or None,
            "imo": _as_int(vessel.get("imo")),
            "ship_type": ship_type,
            "ship_type_label": ship_type_label(ship_type),
            "destination": (vessel.get("destination") or "").strip() or None,
            "draught": _draught_metres(vessel.get("draught")),
            "last_seen_at": _epoch_ms(vessel.get("timestamp")),
            "raw": vessel,
        }

    def _position_row(self, feature: dict) -> dict | None:
        if not isinstance(feature, dict):
            return None
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        observed_at = _epoch_ms(properties.get("timestampExternal"))
        if observed_at is None or len(coordinates) < 2:
            return None
        mmsi = _as_int(properties.get("mmsi") or feature.get("mmsi"))
        if mmsi is None:
            return None
        nav_status = _as_int(properties.get("navStat"))
        return {
            "source": self.provider_name,
            "mmsi": mmsi,
            "observed_at": observed_at,
            "longitude": float(coordinates[0]),
            "latitude": float(coordinates[1]),
            "speed_knots": _as_float(properties.get("sog")),
            "course_degrees": _as_float(properties.get("cog")),
            "heading_degrees": _as_float(properties.get("heading")),
            "nav_status": nav_status,
            "nav_status_label": NAV_STATUS_LABELS.get(nav_status) if nav_status is not None else None,
            "raw": {
                "sog": properties.get("sog"),
                "cog": properties.get("cog"),
                "rot": properties.get("rot"),
                "posAcc": properties.get("posAcc"),
                "raim": properties.get("raim"),
            },
        }


def ship_type_label(code: int | None) -> str | None:
    if code is None:
        return None
    if 30 <= code <= 39:
        return "fishing"
    if 40 <= code <= 49:
        return "high speed craft"
    if code == 52:
        return "tug"
    if code == 53:
        return "port tender"
    if code == 55:
        return "law enforcement"
    if 50 <= code <= 59:
        return "special craft"
    if 60 <= code <= 69:
        return "passenger"
    if 70 <= code <= 79:
        return "cargo"
    if 80 <= code <= 89:
        return "tanker"
    if 90 <= code <= 99:
        return "other"
    return None


def _epoch_ms(value) -> str | None:
    milliseconds = _as_int(value)
    if milliseconds is None or milliseconds <= 0:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat()


def _draught_metres(value) -> float | None:
    raw = _as_int(value)
    if raw is None or raw <= 0:
        return None
    return round(raw / 10, 1)


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
