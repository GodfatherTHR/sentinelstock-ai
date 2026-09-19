from __future__ import annotations

from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import urlencode

from .fetch import FetchError, request_json


def chunked(rows: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]], size: int) -> Iterator[list[Mapping[str, Any]]]:
    chunk: list[Mapping[str, Any]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


class PostgrestSink:
    """RowSink implementation backed by the Supabase PostgREST endpoint.

    Uses the service-role key, which bypasses RLS for writes, and needs no database
    password. This is the sink used when ingesting into a hosted Supabase project.
    """

    def __init__(self, base_url: str, service_role_key: str, *, timeout: int = 180) -> None:
        self._base = base_url.rstrip("/") + "/rest/v1"
        self._timeout = timeout
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        }

    def upsert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        on_conflict: str | None = None,
        batch_size: int = 500,
    ) -> int:
        if not rows:
            return 0
        query = {"on_conflict": on_conflict} if on_conflict else {}
        url = f"{self._base}/{table}" + (f"?{urlencode(query)}" if query else "")
        headers = {**self._headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
        written = 0
        for chunk in chunked(rows, batch_size):
            request_json(url, headers=headers, timeout=self._timeout, method="POST", payload=chunk)
            written += len(chunk)
        return written

    def insert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        batch_size: int = 500,
    ) -> int:
        if not rows:
            return 0
        url = f"{self._base}/{table}"
        headers = {**self._headers, "Prefer": "return=minimal"}
        written = 0
        for chunk in chunked(rows, batch_size):
            request_json(url, headers=headers, timeout=self._timeout, method="POST", payload=chunk)
            written += len(chunk)
        return written

    def select(self, table: str, *, params: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
        query: dict[str, str] = {"select": "*"}
        query.update(params or {})
        url = f"{self._base}/{table}?{urlencode(query)}"
        result = request_json(url, headers=self._headers, timeout=self._timeout)
        if result is None:
            return []
        if not isinstance(result, list):
            raise FetchError(f"unexpected PostgREST response for {table}: {result!r}")
        return result
