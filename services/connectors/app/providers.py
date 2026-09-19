from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator, Mapping, Protocol, Sequence

from .persistence import TableBatch


class ProviderUnavailable(RuntimeError):
    """Raised when a connector cannot currently provide data."""


class ExternalDataProvider(Protocol):
    """Adapter seam for external datasets (see docs/architecture/system-architecture.md)."""

    provider_name: str
    dataset_code: str

    def pull(self, *, cursor: str | None = None, limit: int | None = None) -> Iterator[TableBatch]: ...


class AgriculturalProvider(ExternalDataProvider, Protocol):
    """FAOSTAT adapter seam for regional production and commodity statistics."""


class ProductCatalogProvider(ExternalDataProvider, Protocol):
    """Open Food Facts / USDA FoodData Central adapter seam."""


class ShippingDataProvider(ExternalDataProvider, Protocol):
    """Provider-neutral maritime or shipment tracking seam."""


class SatelliteProvider(ExternalDataProvider, Protocol):
    """Sentinel-2 tile and derived-index adapter seam."""


class ConsumerSignalProvider(ExternalDataProvider, Protocol):
    """Privacy-preserving aggregate review/search/sales signal seam."""


class BaseProvider:
    """Shared behaviour for concrete adapters.

    Subclasses implement :meth:`pull` as a generator of :class:`TableBatch` and update
    ``self.cursor_after`` as they page through the source so a run can resume.
    """

    provider_name: str = "unknown"
    dataset_code: str = "unknown"
    primary_table: str = "unknown"

    def __init__(self, *, organization_id: str | None = None) -> None:
        self.organization_id = organization_id
        self.cursor_after: str | None = None

    def pull(self, *, cursor: str | None = None, limit: int | None = None) -> Iterator[TableBatch]:
        raise NotImplementedError

    def stamp(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Attribute rows to the configured organization (``None`` keeps them unowned)."""
        if not self.organization_id:
            return [dict(row) for row in rows]
        return [{**row, "organization_id": self.organization_id} for row in rows]


@dataclass(frozen=True)
class NormalizedShippingEvent:
    shipment_id: str
    provider: str
    vessel_id: str | None
    latitude: float | None
    longitude: float | None
    destination: str
    eta: datetime | None
    status: str
    risk_score: float | None


@dataclass(frozen=True)
class NormalizedSentimentObservation:
    region: str
    product_category: str
    sentiment_score: float
    sentiment_change: float
    demand_signal: float
    confidence: float
    sample_count: int


@dataclass(frozen=True)
class NormalizedCropObservation:
    region: str
    crop: str
    observed_at: datetime
    ndvi: float | None
    health_score: float | None
    stress_score: float | None
    source: str


def validate_aggregate_sentiment(observation: NormalizedSentimentObservation) -> None:
    if observation.sample_count < 0:
        raise ValueError("sample_count must be non-negative")
    for field in ("sentiment_score", "sentiment_change", "demand_signal", "confidence"):
        value = getattr(observation, field)
        if field != "sentiment_change" and not 0 <= value <= 1:
            raise ValueError(f"{field} must be between 0 and 1")


def validate_shipping_event(event: NormalizedShippingEvent) -> None:
    if not event.shipment_id or not event.destination or not event.status:
        raise ValueError("shipping event requires shipment_id, destination, and status")
    if event.risk_score is not None and not 0 <= event.risk_score <= 1:
        raise ValueError("risk_score must be between 0 and 1")
