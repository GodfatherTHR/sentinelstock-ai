from __future__ import annotations

import io
import zipfile

import pytest

from app.faostat import FAOSTATConfig, FAOSTATProvider, _parse_year
from app.providers import ProviderUnavailable

FBS_CSV = (
    "Area Code,Area,Item Code,Item,Element Code,Element,Year Code,Year,Unit,Value,Flag,Note\n"
    "231,United States of America,2511,Wheat,5510,Production,2023,2023,t,45000000,O,\n"
    "231,United States of America,2511,Wheat,5611,Import Quantity,2023,2023,t,3000000,O,\n"
    "231,United States of America,2511,Wheat,5911,Export Quantity,2023,2023,t,20000000,O,\n"
    "231,United States of America,2511,Wheat,664,Food supply quantity (kg/capita/yr),2023,2023,kg,120,O,\n"
    "231,United States of America,2511,Wheat,5510,Production,2015,2015,t,100,O,\n"
    "171,Bangladesh,2511,Wheat,5510,Production,2023,2023,t,1100000,O,\n"
)


def _archive_bytes(csv_text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("FoodBalanceSheets_E_All_Data_(Normalized).csv", csv_text)
    return buffer.getvalue()


@pytest.fixture
def provider(tmp_path, monkeypatch) -> FAOSTATProvider:
    payload = _archive_bytes(FBS_CSV)
    monkeypatch.setattr("app.faostat.download", lambda url, timeout: payload)
    config = FAOSTATConfig(
        dataset_code="FBS",
        year_from=2021,
        area_filters=("united states", "bangladesh"),
        element_labels=("production", "import quantity", "export quantity"),
        cache_dir=str(tmp_path),
    )
    return FAOSTATProvider(config, organization_id="org-1")


def _rows(provider: FAOSTATProvider, **kwargs) -> list[dict]:
    rows: list[dict] = []
    for batch in provider.pull(**kwargs):
        rows.extend(batch.rows)
    return rows


def test_filters_areas_years_and_elements(provider):
    rows = _rows(provider)
    assert len(rows) == 4
    assert {row["region_label"] for row in rows} == {"United States of America", "Bangladesh"}
    assert all(row["element_label"] != "Food supply quantity (kg/capita/yr)" for row in rows)
    assert all(row["year"] >= 2021 for row in rows)


def test_maps_faostat_columns_to_observations(provider):
    row = next(row for row in _rows(provider) if row["element_label"] == "Production" and row["region_code"] == "231")
    assert row["provider"] == "faostat"
    assert row["dataset_code"] == "FBS"
    assert row["region_code"] == "231"
    assert row["item_code"] == "2511"
    assert row["item_label"] == "Wheat"
    assert row["element_code"] == "5510"
    assert row["year"] == 2023
    assert row["value"] == 45_000_000.0
    assert row["unit"] == "t"
    assert row["flag"] == "O"
    assert row["organization_id"] == "org-1"
    assert row["source_payload"]["element"] == "Production"


def test_resume_skips_already_consumed_rows(provider):
    rows = _rows(provider, cursor="2")
    assert len(rows) == 2
    assert provider.cursor_after == "4"


def test_limit_stops_run_early_and_keeps_cursor(provider):
    rows = _rows(provider, limit=2)
    assert len(rows) == 2
    assert provider.cursor_after == "2"


def test_batch_carries_upsert_target(provider):
    batch = next(iter(provider.pull()))
    assert batch.table == "agricultural_observations"
    assert batch.on_conflict == "provider,dataset_code,region_code,item_code,element_code,year"


def test_unknown_dataset_is_rejected():
    with pytest.raises(ProviderUnavailable):
        FAOSTATProvider(FAOSTATConfig(dataset_code="NOPE"))


def test_parse_year_handles_year_ranges():
    assert _parse_year("2023") == 2023
    assert _parse_year("2023-2024") == 2023
    assert _parse_year("n/a") is None
