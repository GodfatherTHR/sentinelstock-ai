from __future__ import annotations

import io
import zipfile

import pytest

from app.usda_fdc import USDAConfig, USDAFoodDataProvider

FOOD_CATEGORY_CSV = "id,code,description\n1,0100,Dairy and Egg Products\n"
NUTRIENT_CSV = (
    "id,name,unit_name,nutrient_nbr,rank\n"
    "1003,Protein,G,203,1\n"
    "1087,Calcium Ca,MG,301,2\n"
    "1093,Sodium Na,MG,307,3\n"
    "9999,Unused nutrient,G,999,4\n"
)
FOOD_CSV = (
    "fdc_id,data_type,description,food_category_id,publication_date\n"
    "111,foundation_food,\"Milk, whole, 3.25% milkfat, with added vitamin D\",1,2023-10-26\n"
)
FOOD_NUTRIENT_CSV = (
    "id,fdc_id,nutrient_id,amount\n"
    "1,111,1003,3.15\n"
    "2,111,1087,113\n"
    "3,111,9999,1\n"
    "4,111,1093,\n"
)


def _archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("foundation_csv/food.csv", FOOD_CSV)
        bundle.writestr("foundation_csv/food_category.csv", FOOD_CATEGORY_CSV)
        bundle.writestr("foundation_csv/nutrient.csv", NUTRIENT_CSV)
        bundle.writestr("foundation_csv/food_nutrient.csv", FOOD_NUTRIENT_CSV)
    return buffer.getvalue()


@pytest.fixture
def provider(tmp_path, monkeypatch) -> USDAFoodDataProvider:
    payload = _archive()
    monkeypatch.setattr("app.usda_fdc.download", lambda url, timeout: payload)
    config = USDAConfig(
        datasets=("foundation",),
        nutrient_codes=("203", "301"),
        cache_dir=str(tmp_path),
    )
    return USDAFoodDataProvider(config, organization_id="org-1")


def _batches(provider: USDAFoodDataProvider) -> list:
    return list(provider.pull())


def test_emits_catalog_row_and_filtered_nutrients(provider):
    batches = _batches(provider)
    products = next(batch for batch in batches if batch.table == "food_products")
    nutrients = next(batch for batch in batches if batch.table == "food_nutrients")

    assert len(products.rows) == 1
    product = products.rows[0]
    assert product["source"] == "usda_fooddata"
    assert product["source_id"] == "111"
    assert product["category"] == "Dairy and Egg Products"
    assert product["data_type"] == "foundation_food"
    assert product["organization_id"] == "org-1"
    assert products.on_conflict == "source,source_id"

    assert sorted(row["nutrient_code"] for row in nutrients.rows) == ["203", "301"]
    protein = next(row for row in nutrients.rows if row["nutrient_code"] == "203")
    assert protein["nutrient_name"] == "Protein"
    assert protein["nutrient_unit"] == "G"
    assert protein["amount"] == 3.15
    assert nutrients.on_conflict == "source,source_id,nutrient_code"


def test_cursor_advances_and_resume_skips_products(provider):
    list(provider.pull())
    assert provider.cursor_after == "1"

    resumed = USDAFoodDataProvider(provider._config, organization_id="org-1")
    assert list(resumed.pull(cursor="1")) == []
