from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from .config import ConnectorSettings
from .persistence import RowSink
from .providers import BaseProvider

log = logging.getLogger("connectors.worker")

CATALOG_TABLE = "external_source_catalog"
RUNS_TABLE = "ingestion_runs"

DATA_SOURCES = ("maritime", "faostat", "openfoodfacts", "usda", "sentinel2")
ALL_SOURCES = DATA_SOURCES + ("enrich",)


@dataclass
class RunReport:
    provider: str
    dataset_code: str
    tables: dict[str, int] = field(default_factory=dict)
    cursor_before: str | None = None
    cursor_after: str | None = None
    status: str = "succeeded"
    error: str | None = None

    @property
    def rows_written(self) -> int:
        return sum(self.tables.values())

    def summary(self) -> str:
        detail = ", ".join(f"{table}={count}" for table, count in sorted(self.tables.items())) or "no rows"
        suffix = f" cursor {self.cursor_before} -> {self.cursor_after}" if self.cursor_after else ""
        return f"{self.provider} [{self.status}] {detail}{suffix}"


def build_provider(name: str, settings: ConnectorSettings, sink: RowSink | None = None) -> BaseProvider:
    organization_id = settings.organization_id

    if name == "faostat":
        from .faostat import FAOSTATConfig, FAOSTATProvider

        return FAOSTATProvider(FAOSTATConfig.from_env(), organization_id=organization_id)

    if name == "openfoodfacts":
        from .openfoodfacts import OpenFoodFactsConfig, OpenFoodFactsProvider

        return OpenFoodFactsProvider(OpenFoodFactsConfig.from_env(), organization_id=organization_id)

    if name == "usda":
        from .usda_fdc import USDAConfig, USDAFoodDataProvider

        return USDAFoodDataProvider(USDAConfig.from_env(), organization_id=organization_id)

    if name == "maritime":
        from .maritime import DigitrafficAISProvider, MaritimeConfig

        return DigitrafficAISProvider(MaritimeConfig.from_env(), organization_id=organization_id)

    if name == "sentinel2":
        from .sentinel2 import Sentinel2Config, Sentinel2Provider

        return Sentinel2Provider(Sentinel2Config.from_env(), organization_id=organization_id)

    if name == "enrich":
        if sink is None:
            raise RuntimeError("enrichment needs a sink to read products from")
        from .enrichment import EnrichmentProvider
        from .openrouter import OpenRouterClient

        client = OpenRouterClient(settings.require_openrouter_key())
        return EnrichmentProvider(sink, client, organization_id=organization_id)

    raise SystemExit(f"unknown source {name!r}; known sources: {', '.join(ALL_SOURCES)}")


def load_cursor(sink: RowSink, provider: str, dataset_code: str) -> str | None:
    rows = sink.select(
        CATALOG_TABLE,
        params={"select": "last_cursor", "provider": f"eq.{provider}", "dataset_code": f"eq.{dataset_code}"},
    )
    return rows[0].get("last_cursor") if rows else None


def save_catalog(sink: RowSink, report: RunReport) -> None:
    sink.upsert(
        CATALOG_TABLE,
        [
            {
                "provider": report.provider,
                "dataset_code": report.dataset_code,
                "last_cursor": report.cursor_after,
                "last_pulled_at": datetime.now(timezone.utc).isoformat(),
                "last_status": report.status,
                "last_row_count": report.rows_written,
            }
        ],
        on_conflict="provider,dataset_code",
    )


def record_run(sink: RowSink, report: RunReport, started_at: datetime) -> None:
    sink.insert(
        RUNS_TABLE,
        [
            {
                "provider": report.provider,
                "dataset_code": report.dataset_code,
                "status": report.status,
                "cursor_before": report.cursor_before,
                "cursor_after": report.cursor_after,
                "rows_written": report.rows_written,
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error_message": report.error,
                "metadata": {"tables": report.tables},
            }
        ],
    )


def run_source(
    name: str,
    settings: ConnectorSettings,
    sink: RowSink,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> RunReport:
    provider = build_provider(name, settings, sink)
    report = RunReport(provider=provider.provider_name, dataset_code=provider.dataset_code)
    records_catalog = getattr(provider, "records_catalog", True)
    started_at = datetime.now(timezone.utc)

    if records_catalog:
        report.cursor_before = load_cursor(sink, report.provider, report.dataset_code)

    try:
        for batch in provider.pull(cursor=report.cursor_before, limit=limit):
            rows = list(batch.rows)
            if not rows:
                continue
            if dry_run:
                report.tables[batch.table] = report.tables.get(batch.table, 0) + len(rows)
                continue
            written = sink.upsert(batch.table, rows, on_conflict=batch.on_conflict)
            report.tables[batch.table] = report.tables.get(batch.table, 0) + written
            log.info("%s: %s rows -> %s", name, written, batch.table)
    except Exception as exc:  # providers raise ProviderUnavailable / FetchError
        report.status = "failed"
        report.error = str(exc)[:500]
        log.exception("%s ingest failed", name)
    finally:
        report.cursor_after = getattr(provider, "cursor_after", None)

    if not dry_run:
        if records_catalog:
            save_catalog(sink, report)
        record_run(sink, report, started_at)
    return report


def build_sink(settings: ConnectorSettings) -> RowSink:
    if settings.supabase_url and settings.supabase_service_role_key:
        from .postgrest_sink import PostgrestSink

        base_url, key = settings.require_postgrest()
        log.info("using PostgREST sink at %s", base_url)
        return PostgrestSink(base_url, key)

    from .postgres_sink import PostgresSink

    log.info("using direct Postgres sink")
    return PostgresSink(settings.require_database_url())


def _expand(sources: Sequence[str]) -> list[str]:
    expanded: list[str] = []
    for source in sources:
        if source == "all":
            expanded.extend(DATA_SOURCES)
        else:
            expanded.append(source)
    return list(dict.fromkeys(expanded))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.worker", description="SentinelStock data connectors")
    parser.add_argument("sources", nargs="*", default=["faostat"], help=f"one or more of: {', '.join(ALL_SOURCES)}, all")
    parser.add_argument("--limit", type=int, default=None, help="maximum rows per source for this run")
    parser.add_argument("--dry-run", action="store_true", help="fetch and count without writing")
    parser.add_argument("--loop", action="store_true", help="keep running on CONNECTOR_POLL_SECONDS")
    parser.add_argument("--once", action="store_true", help="single pass (default)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    settings = ConnectorSettings.from_env()
    sink = build_sink(settings)
    sources = _expand(args.sources or ["faostat"])

    exit_code = 0
    while True:
        for source in sources:
            report = run_source(source, settings, sink, limit=args.limit, dry_run=args.dry_run)
            log.info("run complete :: %s", report.summary())
            if report.status != "succeeded":
                exit_code = 1
        if not args.loop:
            break
        time.sleep(settings.poll_interval_seconds)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
