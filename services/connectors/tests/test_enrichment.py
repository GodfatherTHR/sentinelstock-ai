from __future__ import annotations

import pytest

from app.enrichment import PROMPT_VERSION, EnrichmentProvider
from app.openrouter import OpenRouterError
from app.providers import ProviderUnavailable

PRODUCTS = [
    {"source": "usda_fooddata", "source_id": "111", "name": "Milk, whole", "brand": None, "category": "Dairy and Egg Products"},
    {"source": "open_food_facts", "source_id": "123", "name": "Oat Flakes", "brand": "Acme", "category": "breakfast cereals"},
    {"source": "open_food_facts", "source_id": "456", "name": "Coffee Beans", "brand": "Roaster", "category": "coffees"},
]

RESPONSE = {
    "items": [
        {
            "source_id": "111",
            "shelf_category": "dairy",
            "department": "chilled dairy",
            "perishability_class": "chilled",
            "storage_requirements": "2-4C",
            "estimated_shelf_life_days": 14,
        },
        {
            "source_id": "123",
            "shelf_category": "breakfast cereal",
            "department": "dry grocery",
            "perishability_class": "ambient",
            "storage_requirements": "cool dry place",
            "estimated_shelf_life_days": 300,
        },
        {"source_id": "unknown-id", "shelf_category": "ignored"},
    ]
}


class FakeSink:
    def __init__(self, products, existing=()):
        self._products = products
        self._existing = list(existing)

    def select(self, table, *, params=None):
        if table == "food_products":
            return self._products
        if table == "product_enrichment":
            return [{"source": source, "source_id": source_id} for source, source_id in self._existing]
        return []

    def upsert(self, *args, **kwargs):
        raise AssertionError("enrichment provider should not write directly")

    def insert(self, *args, **kwargs):
        raise AssertionError("enrichment provider should not write directly")


class FakeClient:
    def __init__(self, responses, models=None):
        self._responses = responses
        self.calls: list[str] = []

    def chat_json(self, *, model, system, user):
        self.calls.append(model)
        result = self._responses.get(model)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise OpenRouterError(f"{model}: no response configured")
        return result


def _rows(provider: EnrichmentProvider) -> list[dict]:
    rows: list[dict] = []
    for batch in provider.pull():
        rows.extend(batch.rows)
    return rows


def test_classifies_products_and_skips_already_enriched():
    sink = FakeSink(PRODUCTS, existing=[("open_food_facts", "456")])
    client = FakeClient({"deepseek/deepseek-v4-flash-0731:free": RESPONSE})
    provider = EnrichmentProvider(sink, client, organization_id="org-1", model="deepseek/deepseek-v4-flash-0731:free")

    rows = _rows(provider)

    assert {row["source_id"] for row in rows} == {"111", "123"}
    assert all(row["prompt_version"] == PROMPT_VERSION for row in rows)
    assert rows[0]["source"] == "usda_fooddata"
    assert rows[0]["perishability_class"] == "chilled"
    assert rows[0]["estimated_shelf_life_days"] == 14
    assert rows[0]["organization_id"] == "org-1"


def test_batch_carries_upsert_target():
    sink = FakeSink(PRODUCTS)
    client = FakeClient({"deepseek/deepseek-v4-flash-0731:free": RESPONSE})
    provider = EnrichmentProvider(sink, client, model="deepseek/deepseek-v4-flash-0731:free")
    batch = next(iter(provider.pull()))
    assert batch.table == "product_enrichment"
    assert batch.on_conflict == "source,source_id,prompt_version"


def test_falls_back_to_next_model():
    sink = FakeSink(PRODUCTS)
    client = FakeClient(
        {
            "deepseek/deepseek-v4-flash-0731:free": OpenRouterError("rate limited"),
            "qwen/qwen3.8-27b:free": RESPONSE,
        }
    )
    provider = EnrichmentProvider(sink, client)
    rows = _rows(provider)
    assert rows
    assert client.calls == ["deepseek/deepseek-v4-flash-0731:free", "qwen/qwen3.8-27b:free"]


def test_all_models_failing_raises_provider_unavailable():
    sink = FakeSink(PRODUCTS)
    client = FakeClient({})
    provider = EnrichmentProvider(sink, client)
    with pytest.raises(ProviderUnavailable):
        _rows(provider)
