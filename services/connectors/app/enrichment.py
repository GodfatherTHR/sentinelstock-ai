from __future__ import annotations

import json
import logging
import os

from .config import env_int
from .openrouter import DEFAULT_MODELS, OpenRouterClient, OpenRouterError
from .persistence import TableBatch
from .postgrest_sink import chunked
from .providers import BaseProvider, ProviderUnavailable

log = logging.getLogger("connectors.enrichment")

PROMPT_VERSION = "shelf-classification-v1"
PRODUCTS_TABLE = "food_products"
TABLE = "product_enrichment"
ON_CONFLICT = "source,source_id,prompt_version"

SYSTEM_PROMPT = (
    "You classify grocery and food products for a warehouse inventory platform. "
    "Return compact JSON only and never invent facts beyond the name, brand, and category given. "
    "perishability_class must be one of: ambient, chilled, frozen, fresh-produce. "
    "estimated_shelf_life_days must be an integer estimate for unopened storage."
)

USER_TEMPLATE = (
    "Classify each product. Respond with exactly this JSON shape: "
    '{{"items":[{{"source_id":"<id>","shelf_category":"<short shelf category>","department":"<store department>",'
    '"perishability_class":"<ambient|chilled|frozen|fresh-produce>","storage_requirements":"<short text>",'
    '"estimated_shelf_life_days":<integer>}}]}}\n'
    "Products:\n{products}"
)


class EnrichmentProvider(BaseProvider):
    """Classifies ingested food products through OpenRouter and caches the result.

    Enrichment is a transformation over already-ingested reference data, not an external
    dataset, so runs do not write catalog/run records; provenance lives on every
    ``product_enrichment`` row (model + prompt version).
    """

    provider_name = "enrichment"
    dataset_code = PROMPT_VERSION
    primary_table = TABLE
    records_catalog = False

    def __init__(
        self,
        sink,
        client: OpenRouterClient,
        *,
        organization_id: str | None = None,
        model: str | None = None,
        batch_size: int | None = None,
        max_products: int | None = None,
    ) -> None:
        super().__init__(organization_id=organization_id)
        self._sink = sink
        self._client = client
        override = model or os.environ.get("OPENROUTER_MODEL")
        self._models = ([override] if override else []) + [candidate for candidate in DEFAULT_MODELS if candidate != override]
        self._batch_size = batch_size or env_int("ENRICHMENT_BATCH_SIZE", 20)
        self._max_products = max_products or env_int("ENRICHMENT_MAX_PRODUCTS", 200)

    def pull(self, *, cursor: str | None = None, limit: int | None = None):
        self.cursor_after = None
        products = self._pending_products(limit)
        if not products:
            log.info("enrichment: nothing new to classify")
            return
        log.info("enrichment: classifying %s products with %s", len(products), ", ".join(self._models))
        for batch in chunked(products, self._batch_size):
            rows = self._classify(list(batch))
            if rows:
                yield TableBatch(TABLE, self.stamp(rows), ON_CONFLICT)

    def _pending_products(self, limit: int | None) -> list[dict]:
        budget = min(limit or self._max_products, self._max_products)
        params = {
            "select": "source,source_id,name,brand,category",
            "order": "observed_at.desc",
            "limit": str(max(budget * 3, budget)),
        }
        source = os.environ.get("ENRICHMENT_SOURCE")
        if source:
            params["source"] = f"eq.{source}"
        products = self._sink.select(PRODUCTS_TABLE, params=params)
        existing = self._sink.select(
            TABLE,
            params={
                "select": "source,source_id",
                "prompt_version": f"eq.{PROMPT_VERSION}",
                "limit": "10000",
            },
        )
        done = {(row.get("source"), row.get("source_id")) for row in existing}
        pending = [
            product
            for product in products
            if product.get("name") and (product.get("source"), product.get("source_id")) not in done
        ]
        return pending[:budget]

    def _classify(self, batch: list[dict]) -> list[dict]:
        payload = [
            {
                "source_id": product["source_id"],
                "name": product["name"],
                "brand": product.get("brand"),
                "category": product.get("category"),
            }
            for product in batch
        ]
        prompt = USER_TEMPLATE.format(products=json.dumps(payload, ensure_ascii=False))
        last_error: Exception | None = None
        for model in self._models:
            try:
                data = self._client.chat_json(model=model, system=SYSTEM_PROMPT, user=prompt)
            except OpenRouterError as exc:
                last_error = exc
                log.warning("enrichment model %s failed: %s", model, exc)
                continue
            rows = self._rows(data, batch, model)
            if rows:
                return rows
            last_error = OpenRouterError(f"{model}: no usable items in response")
        raise ProviderUnavailable(f"OpenRouter enrichment failed: {last_error}")

    def _rows(self, data: dict, batch: list[dict], model: str) -> list[dict]:
        by_id = {str(product["source_id"]): product for product in batch}
        rows = []
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id") or "")
            product = by_id.get(source_id)
            if product is None:
                continue
            rows.append(
                {
                    "source": product["source"],
                    "source_id": source_id,
                    "shelf_category": _text(item.get("shelf_category")),
                    "department": _text(item.get("department")),
                    "perishability_class": _text(item.get("perishability_class")),
                    "storage_requirements": _text(item.get("storage_requirements")),
                    "estimated_shelf_life_days": _int(item.get("estimated_shelf_life_days")),
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "payload": item,
                }
            )
        return rows


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:200] or None


def _int(value) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if 0 < number < 3650 else None
