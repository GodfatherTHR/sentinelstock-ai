from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .config import env_int, env_float, env_tuple
from .fetch import FetchError, request_json
from .persistence import TableBatch
from .providers import BaseProvider, ProviderUnavailable

log = logging.getLogger("connectors.openfoodfacts")

SEARCH_URL = "https://world.openfoodfacts.org/api/v2/search"

DEFAULT_CATEGORIES = (
    "breakfast-cereals",
    "yogurts",
    "coffees",
    "chocolates",
    "plant-based-milks",
    "pastas",
    "olive-oils",
    "fruit-juices",
    "biscuits",
    "cheeses",
    "rices",
    "teas",
)

DEFAULT_FIELDS = (
    "code",
    "product_name",
    "generic_name",
    "brands",
    "categories_tags",
    "allergens_tags",
    "labels_tags",
    "countries_tags",
    "ingredients_text",
    "nutriscore_grade",
    "nova_group",
    "quantity",
    "serving_size",
    "image_front_url",
    "nutriments",
    "completeness",
)

NUTRIMENT_KEYS = (
    "energy-kcal_100g",
    "fat_100g",
    "saturated-fat_100g",
    "carbohydrates_100g",
    "sugars_100g",
    "fiber_100g",
    "proteins_100g",
    "salt_100g",
    "sodium_100g",
)

TABLE = "food_products"
ON_CONFLICT = "source,source_id"


@dataclass(frozen=True)
class OpenFoodFactsConfig:
    categories: tuple[str, ...] = DEFAULT_CATEGORIES
    pages_per_category: int = 3
    page_size: int = 100
    timeout: int = 60
    delay_seconds: float = 6.0

    @classmethod
    def from_env(cls) -> "OpenFoodFactsConfig":
        return cls(
            categories=env_tuple("OFF_CATEGORIES", DEFAULT_CATEGORIES),
            pages_per_category=env_int("OFF_PAGES_PER_CATEGORY", 3),
            page_size=env_int("OFF_PAGE_SIZE", 100),
            timeout=env_int("OFF_TIMEOUT_SECONDS", 60),
            delay_seconds=env_float("OFF_DELAY_SECONDS", 6.0),
        )


def fetch_search(url: str, timeout: int):
    """Search-endpoint reader with retries; Open Food Facts throttles search hard."""
    return request_json(url, timeout=timeout, retries=3, backoff=2.0)


class OpenFoodFactsProvider(BaseProvider):
    """Adapter for the Open Food Facts search API.

    The full Open Food Facts dump is ~10 GB, so the connector pages the search API by
    category and keeps the fields the platform uses (ingredients, allergens, nutrition
    grade). Runs are idempotent: products upsert on ``(source, source_id)``.
    """

    provider_name = "open_food_facts"
    dataset_code = "search-api"
    primary_table = TABLE

    def __init__(
        self,
        config: OpenFoodFactsConfig | None = None,
        *,
        organization_id: str | None = None,
        fetch=None,
    ) -> None:
        super().__init__(organization_id=organization_id)
        self._config = config or OpenFoodFactsConfig()
        self._fetch = fetch or fetch_search
        self.seen_codes: set[str] = set()
        self.failed_pages = 0

    def pull(self, *, cursor: str | None = None, limit: int | None = None):
        start_category, start_page = _parse_cursor(cursor)
        emitted = 0
        budget = limit if limit is not None else None
        self.cursor_after = f"{start_category}:{start_page}"

        for category_index in range(start_category, len(self._config.categories)):
            category = self._config.categories[category_index]
            first_page = start_page if category_index == start_category else 1
            for page in range(first_page, self._config.pages_per_category + 1):
                try:
                    products = self._search(category, page)
                except ProviderUnavailable as exc:
                    # Partial catalogs beat no catalog: skip the page, keep the category.
                    self.failed_pages += 1
                    log.warning("OFF %s page %s unavailable: %s", category, page, exc)
                    break
                self.cursor_after = f"{category_index}:{page + 1}"
                if not products:
                    break
                rows = []
                for product in products:
                    row = self._to_row(product)
                    if row is None or row["source_id"] in self.seen_codes:
                        continue
                    self.seen_codes.add(row["source_id"])
                    rows.append(row)
                if rows:
                    emitted += len(rows)
                    yield TableBatch(TABLE, self.stamp(rows), ON_CONFLICT)
                if budget is not None and emitted >= budget:
                    return
                if len(products) < self._config.page_size:
                    break
                time.sleep(self._config.delay_seconds)
            start_page = 1

        if emitted == 0 and self.failed_pages:
            raise ProviderUnavailable(f"Open Food Facts returned no products ({self.failed_pages} pages failed)")

    def _search(self, category: str, page: int) -> list[dict]:
        params = {
            "categories_tags_en": category,
            "fields": ",".join(DEFAULT_FIELDS),
            "page_size": str(self._config.page_size),
            "page": str(page),
        }
        query = "&".join(f"{key}={value}" for key, value in params.items())
        url = f"{SEARCH_URL}?{query}"
        try:
            payload = self._fetch(url, timeout=self._config.timeout)
        except FetchError as exc:
            raise ProviderUnavailable(f"Open Food Facts request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProviderUnavailable(f"unexpected Open Food Facts payload: {payload!r}")
        products = payload.get("products") or []
        log.info(
            "OFF %s page %s: %s of %s products",
            category,
            page,
            len(products),
            payload.get("count"),
        )
        return products

    def _to_row(self, product: dict) -> dict | None:
        code = str(product.get("code") or "").strip()
        name = (product.get("product_name") or product.get("generic_name") or "").strip()
        if not code or not name:
            return None
        categories = _clean_tags(product.get("categories_tags"))
        payload = {
            "countries": _clean_tags(product.get("countries_tags"))[:10],
            "labels": _clean_tags(product.get("labels_tags"))[:10],
            "completeness": product.get("completeness"),
            "nutriments": {
                key: product["nutriments"][key]
                for key in NUTRIMENT_KEYS
                if isinstance(product.get("nutriments"), dict) and product["nutriments"].get(key) is not None
            },
        }
        return {
            "source": self.provider_name,
            "source_id": code,
            "name": name[:500],
            "brand": _first_brand(product.get("brands")),
            "category": categories[-1] if categories else None,
            "categories": categories or None,
            "barcode": code,
            "ingredients_text": (product.get("ingredients_text") or "").strip() or None,
            "allergens": _clean_tags(product.get("allergens_tags")) or None,
            "quantity": (product.get("quantity") or "").strip() or None,
            "serving_size": (product.get("serving_size") or "").strip() or None,
            "nutriscore_grade": (product.get("nutriscore_grade") or "").strip().lower() or None,
            "nova_group": _as_int(product.get("nova_group")),
            "image_url": (product.get("image_front_url") or "").strip() or None,
            "source_payload": payload,
        }


def _parse_cursor(cursor: str | None) -> tuple[int, int]:
    if not cursor:
        return 0, 1
    try:
        category, page = cursor.split(":", 1)
        return int(category), max(1, int(page))
    except ValueError:
        return 0, 1


def _clean_tags(tags) -> list[str]:
    if not isinstance(tags, list):
        return []
    cleaned = []
    for tag in tags:
        text = str(tag).strip()
        if not text:
            continue
        if ":" in text:
            text = text.split(":", 1)[1]
        text = text.replace("-", " ").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _first_brand(brands) -> str | None:
    if not isinstance(brands, str) or not brands.strip():
        return None
    return brands.split(",")[0].strip()[:200] or None


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
