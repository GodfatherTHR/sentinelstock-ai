from __future__ import annotations

from app.openfoodfacts import OpenFoodFactsConfig, OpenFoodFactsProvider

PRODUCTS = {
    "count": 3,
    "page": 1,
    "products": [
        {
            "code": "1234567890123",
            "product_name": "Oat Flakes",
            "brands": "Acme, Other",
            "categories_tags": ["en:plant-based-foods", "en:breakfast-cereals"],
            "allergens_tags": ["en:gluten", "en:nuts"],
            "countries_tags": ["en:united-states"],
            "ingredients_text": "Oats",
            "nutriscore_grade": "a",
            "nova_group": "3",
            "quantity": "500 g",
            "image_front_url": "https://images.example/1.jpg",
            "nutriments": {"energy-kcal_100g": 380, "salt_100g": 0.01, "unused_100g": 5},
        },
        {"code": "1234567890123", "product_name": "Duplicate Code", "categories_tags": ["en:breakfast-cereals"]},
        {"code": "", "product_name": "Missing barcode", "categories_tags": ["en:breakfast-cereals"]},
    ],
}


def _provider(fetch, **overrides) -> OpenFoodFactsProvider:
    config = OpenFoodFactsConfig(
        categories=("breakfast-cereals",),
        pages_per_category=overrides.pop("pages_per_category", 1),
        page_size=100,
        delay_seconds=0.0,
    )
    return OpenFoodFactsProvider(config, organization_id="org-1", fetch=fetch)


def _rows(provider: OpenFoodFactsProvider) -> list[dict]:
    rows: list[dict] = []
    for batch in provider.pull():
        rows.extend(batch.rows)
    return rows


def test_maps_product_fields_and_drops_invalid_rows():
    rows = _rows(_provider(lambda url, timeout: PRODUCTS))
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "open_food_facts"
    assert row["source_id"] == "1234567890123"
    assert row["brand"] == "Acme"
    assert row["category"] == "breakfast cereals"
    assert row["categories"] == ["plant based foods", "breakfast cereals"]
    assert row["allergens"] == ["gluten", "nuts"]
    assert row["nova_group"] == 3
    assert row["nutriscore_grade"] == "a"
    assert row["organization_id"] == "org-1"
    assert row["source_payload"]["nutriments"] == {"energy-kcal_100g": 380, "salt_100g": 0.01}


def test_batch_targets_food_products_upsert():
    batch = next(iter(_provider(lambda url, timeout: PRODUCTS).pull()))
    assert batch.table == "food_products"
    assert batch.on_conflict == "source,source_id"


def test_pagination_stops_on_short_page_and_tracks_cursor():
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        return PRODUCTS

    provider = _provider(fetch, pages_per_category=3)
    _rows(provider)
    assert len(calls) == 1
    assert provider.cursor_after == "0:2"


def test_offer_request_uses_category_and_fields():
    urls = []

    def fetch(url, timeout):
        urls.append(url)
        return PRODUCTS

    _rows(_provider(fetch))
    assert "categories_tags_en=breakfast-cereals" in urls[0]
    assert "fields=" in urls[0]


def test_throttled_page_is_skipped_without_failing_the_run():
    from app.fetch import FetchError

    def fetch(url, timeout):
        if "categories_tags_en=breakfast-cereals" in url:
            raise FetchError("HTTP 503: page temporarily unavailable")
        return PRODUCTS

    config = OpenFoodFactsConfig(
        categories=("breakfast-cereals", "yogurts"),
        pages_per_category=1,
        delay_seconds=0.0,
    )
    provider = OpenFoodFactsProvider(config, organization_id="org-1", fetch=fetch)

    rows = _rows(provider)

    assert rows, "a throttled category must not stop the remaining categories"
    assert provider.failed_pages == 1


def test_total_failure_still_raises():
    import pytest

    from app.fetch import FetchError
    from app.providers import ProviderUnavailable

    def fetch(url, timeout):
        raise FetchError("HTTP 503: page temporarily unavailable")

    provider = _provider(fetch)
    with pytest.raises(ProviderUnavailable):
        _rows(provider)
