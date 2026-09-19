from __future__ import annotations

import csv
import io
import logging
import os
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import env_int, env_tuple
from .fetch import FetchError, download
from .persistence import TableBatch
from .providers import BaseProvider, ProviderUnavailable

log = logging.getLogger("connectors.faostat")

# FAOSTAT's fenixservices REST API is not reliably available, so connectors read the
# official bulk archives instead. Each archive is one normalized CSV: one row per
# area/item/element/year with codes, labels, unit, value, and flag.
ARCHIVE_URLS = {
    "FBS": "https://bulks-faostat.fao.org/production/FoodBalanceSheets_E_All_Data_(Normalized).zip",
    "QCL": "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip",
}

DEFAULT_AREA_FILTERS = (
    "united states of america",
    "brazil",
    "china, mainland",
    "india",
    "canada",
    "mexico",
    "argentina",
    "ukraine",
    "france",
    "netherlands",
    "viet nam",
    "indonesia",
    "australia",
    "bangladesh",
)

DEFAULT_ELEMENT_LABELS = {
    "FBS": (
        "production",
        "import quantity",
        "export quantity",
        "domestic supply quantity",
        "food supply quantity (tonnes)",
        "stock variation",
        "feed",
        "losses",
        "seed",
    ),
    "QCL": (
        "area harvested",
        "production",
        "yield",
        "stocks",
        "producing animals/slaughtered",
        "yield/carcass weight",
    ),
}

FALLBACK_ELEMENT_LABELS = ("production", "import quantity", "export quantity", "area harvested", "yield", "stocks")

TABLE = "agricultural_observations"
ON_CONFLICT = "provider,dataset_code,region_code,item_code,element_code,year"


@dataclass(frozen=True)
class FAOSTATConfig:
    """FAOSTAT bulk-archive configuration.

    The archives are national statistics, so a run filters to the areas, years, and
    elements the platform actually uses rather than loading the full multi-million row
    history.
    """

    dataset_code: str = "FBS"
    year_from: int = 2021
    area_filters: tuple[str, ...] = DEFAULT_AREA_FILTERS
    element_labels: tuple[str, ...] = ()
    batch_rows: int = 1000
    max_rows: int = 150000
    timeout: int = 600
    cache_dir: str | None = None
    refresh: bool = False

    @classmethod
    def from_env(cls, dataset_code: str | None = None) -> "FAOSTATConfig":
        dataset = (dataset_code or os.environ.get("FAOSTAT_DATASET", "FBS")).upper()
        return cls(
            dataset_code=dataset,
            year_from=env_int("FAOSTAT_YEAR_FROM", 2021),
            area_filters=env_tuple("FAOSTAT_AREA_FILTERS", DEFAULT_AREA_FILTERS),
            element_labels=env_tuple(
                "FAOSTAT_ELEMENT_LABELS",
                DEFAULT_ELEMENT_LABELS.get(dataset, FALLBACK_ELEMENT_LABELS),
            ),
            batch_rows=env_int("FAOSTAT_BATCH_ROWS", 1000),
            max_rows=env_int("FAOSTAT_MAX_ROWS", 150000),
            timeout=env_int("FAOSTAT_TIMEOUT_SECONDS", 600),
            cache_dir=os.environ.get("CONNECTOR_CACHE_DIR"),
            refresh=os.environ.get("FAOSTAT_REFRESH", "").lower() in {"1", "true", "yes"},
        )


class FAOSTATProvider(BaseProvider):
    """Adapter implementing the external data seam against FAOSTAT bulk archives."""

    provider_name = "faostat"
    primary_table = TABLE

    def __init__(self, config: FAOSTATConfig | None = None, *, organization_id: str | None = None) -> None:
        super().__init__(organization_id=organization_id)
        self._config = config or FAOSTATConfig()
        self.dataset_code = self._config.dataset_code
        self._elements = {label.strip().lower() for label in self._config.element_labels}
        self.stats: Counter[str] = Counter()
        self.skipped_elements: Counter[str] = Counter()
        self.archive_name = Path(unquote(urlparse(self._archive_url()).path)).name

    def _archive_url(self) -> str:
        try:
            return ARCHIVE_URLS[self.dataset_code]
        except KeyError as exc:
            raise ProviderUnavailable(
                f"unknown FAOSTAT dataset {self.dataset_code!r}; known: {', '.join(sorted(ARCHIVE_URLS))}"
            ) from exc

    def pull(self, *, cursor: str | None = None, limit: int | None = None):
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        budget = self._config.max_rows if limit is None else min(limit, self._config.max_rows)
        self.cursor_after = str(offset)

        archive = self._ensure_archive()
        batch: list[dict] = []
        consumed = 0
        emitted = 0

        with zipfile.ZipFile(archive) as bundle:
            member = self._csv_member(bundle)
            with bundle.open(member) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
                reader = csv.reader(text)
                try:
                    header = next(reader)
                except StopIteration:
                    return
                index = self._header_index(header)
                for cells in reader:
                    row = self._row(cells, index)
                    if row is None:
                        continue
                    consumed += 1
                    if consumed <= offset:
                        continue
                    batch.append(row)
                    emitted += 1
                    self.cursor_after = str(consumed)
                    if len(batch) >= self._config.batch_rows:
                        yield TableBatch(TABLE, self.stamp(batch), ON_CONFLICT)
                        batch = []
                    if emitted >= budget:
                        log.info("FAOSTAT %s: row budget %s reached; resumes at cursor %s", self.dataset_code, budget, self.cursor_after)
                        break
        if batch:
            yield TableBatch(TABLE, self.stamp(batch), ON_CONFLICT)

        skipped = ", ".join(f"{label or '(blank)'}={count}" for label, count in self.skipped_elements.most_common(3))
        log.info(
            "FAOSTAT %s: kept %s rows (skipped %s rows; top unselected elements: %s)",
            self.dataset_code,
            emitted,
            sum(self.stats.values()),
            skipped or "none",
        )

    def _ensure_archive(self) -> Path:
        cache_dir = Path(self._config.cache_dir or os.path.join(tempfile.gettempdir(), "sentinelstock-connectors"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / self.archive_name
        if target.exists() and not self._config.refresh:
            log.info("FAOSTAT %s: using cached archive %s", self.dataset_code, target)
            return target
        url = self._archive_url()
        log.info("FAOSTAT %s: downloading %s", self.dataset_code, url)
        try:
            payload = download(url, timeout=self._config.timeout)
        except FetchError as exc:
            raise ProviderUnavailable(f"FAOSTAT archive download failed: {exc}") from exc
        target.write_bytes(payload)
        log.info("FAOSTAT %s: cached %s (%.1f MB)", self.dataset_code, target, len(payload) / 1_048_576)
        return target

    @staticmethod
    def _csv_member(bundle: zipfile.ZipFile) -> str:
        members = [name for name in bundle.namelist() if name.lower().endswith(".csv")]
        if not members:
            raise ProviderUnavailable("FAOSTAT archive does not contain a CSV file")
        return max(members, key=lambda name: bundle.getinfo(name).file_size)

    @staticmethod
    def _header_index(header: list[str]) -> dict[str, int]:
        normalized = [cell.strip().strip('"').lower() for cell in header]

        def find(*names: str) -> int:
            for name in names:
                if name in normalized:
                    return normalized.index(name)
            return -1

        return {
            "area_code": find("area code"),
            "area": find("area"),
            "item_code": find("item code"),
            "item": find("item"),
            "element_code": find("element code"),
            "element": find("element"),
            "year_code": find("year code"),
            "year": find("year"),
            "unit": find("unit"),
            "value": find("value"),
            "flag": find("flag"),
        }

    def _row(self, cells: list[str], index: dict[str, int]) -> dict | None:
        def cell(key: str) -> str:
            position = index[key]
            if position < 0 or position >= len(cells):
                return ""
            return cells[position].strip().strip('"')

        area = cell("area")
        normalized_area = area.lower()
        if self._config.area_filters and not any(fragment in normalized_area for fragment in self._config.area_filters):
            self.stats["skipped_area"] += 1
            return None

        element = cell("element")
        if self._elements and element.strip().lower() not in self._elements:
            self.skipped_elements[element] += 1
            return None

        year = _parse_year(cell("year_code") or cell("year"))
        if year is None or year < self._config.year_from:
            self.stats["skipped_year"] += 1
            return None

        raw_value = cell("value")
        if not raw_value:
            self.stats["skipped_empty_value"] += 1
            return None
        try:
            value = float(raw_value.replace(",", ""))
        except ValueError:
            self.stats["skipped_non_numeric"] += 1
            return None

        item = cell("item")
        region_code = cell("area_code") or area
        item_code = cell("item_code") or item
        element_code = cell("element_code") or element
        if not region_code or not item_code or not element_code:
            self.stats["skipped_missing_code"] += 1
            return None

        return {
            "provider": self.provider_name,
            "dataset_code": self.dataset_code,
            "region_code": region_code,
            "region_label": area or None,
            "item_code": item_code,
            "item_label": item or None,
            "element_code": element_code,
            "element_label": element or None,
            "year": year,
            "value": value,
            "unit": cell("unit") or None,
            "flag": cell("flag") or None,
            "source_payload": {"archive": self.archive_name, "element": element},
        }


def _parse_year(raw: str) -> int | None:
    digits = ""
    for character in raw:
        if character.isdigit():
            digits += character
            if len(digits) == 4:
                return int(digits)
        else:
            digits = ""
    return None
