from __future__ import annotations

from app.config import ConnectorSettings
from app.persistence import TableBatch
from app.worker import run_source


class FakeSink:
    def __init__(self, cursor: str | None = None) -> None:
        self.upserts: list[tuple[str, list, str | None]] = []
        self.inserts: list[tuple[str, list]] = []
        self.cursor = cursor

    def upsert(self, table, rows, *, on_conflict=None, batch_size=500):
        rows = list(rows)
        self.upserts.append((table, rows, on_conflict))
        return len(rows)

    def insert(self, table, rows, *, batch_size=500):
        rows = list(rows)
        self.inserts.append((table, rows))
        return len(rows)

    def select(self, table, *, params=None):
        if table == "external_source_catalog":
            return [{"last_cursor": self.cursor}] if self.cursor is not None else []
        return []


class StubProvider:
    provider_name = "stub"
    dataset_code = "v1"
    primary_table = "stub_table"
    records_catalog = True

    def __init__(self, batches, cursor_after="7", error: Exception | None = None) -> None:
        self._batches = batches
        self._error = error
        self.cursor_after = cursor_after
        self.seen_cursor = None

    def pull(self, *, cursor=None, limit=None):
        self.seen_cursor = cursor
        if self._error is not None:
            raise self._error
        yield from self._batches


def settings() -> ConnectorSettings:
    return ConnectorSettings(
        database_url=None,
        supabase_url=None,
        supabase_service_role_key=None,
        organization_id="org-1",
        openrouter_api_key=None,
        poll_interval_seconds=1,
    )


def _install(monkeypatch, provider: StubProvider) -> None:
    monkeypatch.setattr("app.worker.build_provider", lambda name, settings, sink: provider)


def test_run_source_upserts_batches_and_updates_catalog(monkeypatch):
    provider = StubProvider([TableBatch("stub_table", [{"a": 1}, {"a": 2}], "a")])
    _install(monkeypatch, provider)
    sink = FakeSink()

    report = run_source("stub", settings(), sink)

    assert report.status == "succeeded"
    assert report.rows_written == 2
    assert report.cursor_after == "7"
    assert sink.upserts[0][0] == "stub_table"
    assert sink.upserts[0][2] == "a"

    catalog = next(entry for entry in sink.upserts if entry[0] == "external_source_catalog")
    assert catalog[1][0]["last_cursor"] == "7"
    assert catalog[2] == "provider,dataset_code"

    runs = next(entry for entry in sink.inserts if entry[0] == "ingestion_runs")
    assert runs[1][0]["status"] == "succeeded"
    assert runs[1][0]["rows_written"] == 2


def test_run_source_reads_cursor_from_catalog(monkeypatch):
    provider = StubProvider([TableBatch("stub_table", [{"a": 1}], "a")])
    _install(monkeypatch, provider)
    sink = FakeSink(cursor="42")

    run_source("stub", settings(), sink)

    assert provider.seen_cursor == "42"


def test_failed_run_is_recorded_with_error(monkeypatch):
    provider = StubProvider([], error=RuntimeError("upstream down"))
    _install(monkeypatch, provider)
    sink = FakeSink()

    report = run_source("stub", settings(), sink)

    assert report.status == "failed"
    assert "upstream down" in (report.error or "")
    runs = next(entry for entry in sink.inserts if entry[0] == "ingestion_runs")
    assert runs[1][0]["status"] == "failed"
    catalog = next(entry for entry in sink.upserts if entry[0] == "external_source_catalog")
    assert catalog[1][0]["last_status"] == "failed"


def test_dry_run_counts_without_writing(monkeypatch):
    provider = StubProvider([TableBatch("stub_table", [{"a": 1}, {"a": 2}], "a")])
    _install(monkeypatch, provider)
    sink = FakeSink()

    report = run_source("stub", settings(), sink, dry_run=True)

    assert report.rows_written == 2
    assert sink.upserts == []
    assert sink.inserts == []
