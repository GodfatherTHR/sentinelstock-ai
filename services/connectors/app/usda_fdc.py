from __future__ import annotations

import csv
import io
import logging
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import env_int, env_tuple
from .fetch import FetchError, download
from .persistence import TableBatch
from .providers import BaseProvider, ProviderUnavailable

log = logging.getLogger("connectors.usda")

# USDA FoodData Central bulk CSV releases (no API key required, unlike the FDC API).
# Foundation and SR Legacy are the reference datasets; the branded-foods release is
# ~3 GB and is intentionally not part of the default ingest.
ARCHIVE_URLS = {
    "foundation": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_csv_2025-12-18.zip",
    "sr_legacy": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip",
}

# Nutrient numbers from USDA nutrient.csv. Keeps the panel to what inventory,
# nutrition, and forecasting features actually use.
DEFAULT_NUTRIENT_CODES = (
    "208",  # Energy (kcal)
    "203",  # Protein
    "204",  # Total lipid (fat)
    "205",  # Carbohydrate, by difference
    "291",  # Fiber, total dietary
    "269",  # Total Sugars
    "307",  # Sodium
    "306",  # Potassium
    "301",  # Calcium
    "303",  # Iron
    "304",  # Magnesium
    "309",  # Zinc
    "320",  # Vitamin A, RAE
    "328",  # Vitamin D (D2 + D3)
    "401",  # Vitamin C
    "601",  # Cholesterol
    "606",  # Fatty acids, total saturated
    "645",  # Fatty acids, total monounsaturated
    "646",  # Fatty acids, total polyunsaturated
    "605",  # Fatty acids, total trans
    "255",  # Water
)

PRODUCTS_TABLE = "food_products"
PRODUCTS_ON_CONFLICT = "source,source_id"
NUTRIENTS_TABLE = "food_nutrients"
NUTRIENTS_ON_CONFLICT = "source,source_id,nutrient_code"


@dataclass(frozen=True)
class USDAConfig:
    datasets: tuple[str, ...] = ("foundation", "sr_legacy")
    nutrient_codes: tuple[str, ...] = DEFAULT_NUTRIENT_CODES
    batch_rows: int = 1000
    max_products: int = 20000
    timeout: int = 300
    cache_dir: str | None = None
    refresh: bool = False

    @classmethod
    def from_env(cls) -> "USDAConfig":
        return cls(
            datasets=env_tuple("USDA_DATASETS", ("foundation", "sr_legacy")),
            nutrient_codes=env_tuple("USDA_NUTRIENT_CODES", DEFAULT_NUTRIENT_CODES),
            batch_rows=env_int("USDA_BATCH_ROWS", 1000),
            max_products=env_int("USDA_MAX_PRODUCTS", 20000),
            timeout=env_int("USDA_TIMEOUT_SECONDS", 300),
            cache_dir=os.environ.get("CONNECTOR_CACHE_DIR"),
            refresh=os.environ.get("USDA_REFRESH", "").lower() in {"1", "true", "yes"},
        )


class USDAFoodDataProvider(BaseProvider):
    """Adapter for USDA FoodData Central bulk CSV releases.

    Emits catalog rows (``food_products``) and the selected nutrient panel
    (``food_nutrients``) for foundation foods and SR Legacy foods.
    """

    provider_name = "usda_fooddata"
    dataset_code = "foundation+sr_legacy"
    primary_table = PRODUCTS_TABLE

    def __init__(self, config: USDAConfig | None = None, *, organization_id: str | None = None) -> None:
        super().__init__(organization_id=organization_id)
        self._config = config or USDAConfig()
        self._nutrient_filter = set(self._config.nutrient_codes)

    def pull(self, *, cursor: str | None = None, limit: int | None = None):
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        budget = self._config.max_products if limit is None else min(limit, self._config.max_products)
        self.cursor_after = str(offset)
        emitted = 0
        skipped = 0
        # Keyed by upsert key so a page can never contain two rows for the same target row.
        product_rows: dict[str, dict] = {}
        nutrient_rows: dict[tuple[str, str], dict] = {}

        for dataset in self._config.datasets:
            if dataset not in ARCHIVE_URLS:
                raise ProviderUnavailable(f"unknown USDA dataset {dataset!r}")
            tables = self._read_dataset(dataset)
            categories = tables["categories"]
            nutrients = tables["nutrients"]
            log.info(
                "USDA %s: %s foods, %s nutrient rows, %s selected nutrients",
                dataset,
                len(tables["foods"]),
                len(tables["food_nutrients"]),
                len(self._nutrient_filter),
            )
            for food in tables["foods"]:
                if skipped < offset:
                    skipped += 1
                    continue
                fdc_id = str(food["fdc_id"])
                product_rows[fdc_id] = {
                    "source": self.provider_name,
                    "source_id": fdc_id,
                    "name": (food.get("description") or "").strip()[:500] or f"FDC {fdc_id}",
                    "category": categories.get(str(food.get("food_category_id"))),
                    "data_type": food.get("data_type"),
                    "source_payload": {
                        "dataset": dataset,
                        "publication_date": food.get("publication_date"),
                        "food_category_id": food.get("food_category_id"),
                    },
                }
                for nutrient in nutrients.get(fdc_id, ()):
                    nutrient_rows[(fdc_id, nutrient["code"])] = {
                        "source": self.provider_name,
                        "source_id": fdc_id,
                        "nutrient_code": nutrient["code"],
                        "nutrient_name": nutrient["name"],
                        "nutrient_unit": nutrient["unit"],
                        "amount": nutrient["amount"],
                    }

                emitted += 1
                self.cursor_after = str(skipped + emitted)
                if len(product_rows) >= self._config.batch_rows:
                    log.info("USDA %s: flushing %s products and %s nutrients", dataset, len(product_rows), len(nutrient_rows))
                    yield TableBatch(PRODUCTS_TABLE, self.stamp(list(product_rows.values())), PRODUCTS_ON_CONFLICT)
                    if nutrient_rows:
                        yield TableBatch(NUTRIENTS_TABLE, self.stamp(list(nutrient_rows.values())), NUTRIENTS_ON_CONFLICT)
                    product_rows, nutrient_rows = {}, {}
                if emitted >= budget:
                    log.info("USDA %s: product budget %s reached; resumes at cursor %s", dataset, budget, self.cursor_after)
                    break
            if emitted >= budget:
                break

        if product_rows:
            yield TableBatch(PRODUCTS_TABLE, self.stamp(list(product_rows.values())), PRODUCTS_ON_CONFLICT)
        if nutrient_rows:
            yield TableBatch(NUTRIENTS_TABLE, self.stamp(list(nutrient_rows.values())), NUTRIENTS_ON_CONFLICT)

    def _read_dataset(self, dataset: str) -> dict:
        archive = self._ensure_archive(dataset)
        with zipfile.ZipFile(archive) as bundle:
            members = {_basename(name): name for name in bundle.namelist() if name.lower().endswith(".csv")}
            required = ("food.csv", "food_category.csv", "nutrient.csv", "food_nutrient.csv")
            missing = [name for name in required if name not in members]
            if missing:
                raise ProviderUnavailable(f"USDA {dataset} archive is missing {', '.join(missing)}")

            categories = {}
            with _open_member(bundle, members["food_category.csv"]) as handle:
                for row in csv.DictReader(handle):
                    categories[str(row.get("id"))] = (row.get("description") or "").strip() or None

            nutrient_lookup = {}
            with _open_member(bundle, members["nutrient.csv"]) as handle:
                for row in csv.DictReader(handle):
                    code = str(row.get("nutrient_nbr") or "").strip()
                    if code in self._nutrient_filter:
                        nutrient_lookup[str(row.get("id"))] = {
                            "code": code,
                            "name": (row.get("name") or "").strip(),
                            "unit": (row.get("unit_name") or "").strip(),
                        }

            nutrients: dict[str, list[dict]] = {}
            with _open_member(bundle, members["food_nutrient.csv"]) as handle:
                for row in csv.DictReader(handle):
                    definition = nutrient_lookup.get(str(row.get("nutrient_id")))
                    if definition is None:
                        continue
                    amount = _as_float(row.get("amount"))
                    if amount is None:
                        continue
                    nutrients.setdefault(str(row.get("fdc_id")), []).append({**definition, "amount": amount})

            foods = []
            with _open_member(bundle, members["food.csv"]) as handle:
                for row in csv.DictReader(handle):
                    foods.append(row)

        return {"categories": categories, "nutrients": nutrients, "food_nutrients": nutrients, "foods": foods}

    def _ensure_archive(self, dataset: str) -> Path:
        cache_dir = Path(self._config.cache_dir or os.path.join(tempfile.gettempdir(), "sentinelstock-connectors"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / Path(unquote(urlparse(ARCHIVE_URLS[dataset]).path)).name
        if target.exists() and not self._config.refresh:
            return target
        log.info("USDA %s: downloading %s", dataset, ARCHIVE_URLS[dataset])
        try:
            payload = download(ARCHIVE_URLS[dataset], timeout=self._config.timeout)
        except FetchError as exc:
            raise ProviderUnavailable(f"USDA archive download failed: {exc}") from exc
        target.write_bytes(payload)
        return target


def _open_member(bundle: zipfile.ZipFile, member: str):
    return io.TextIOWrapper(bundle.open(member), encoding="utf-8-sig", errors="replace", newline="")


def _basename(member: str) -> str:
    return member.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _as_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
