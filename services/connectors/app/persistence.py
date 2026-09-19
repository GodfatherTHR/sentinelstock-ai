from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class TableBatch:
    """Rows destined for a single table.

    ``on_conflict`` names the conflict target for an upsert (PostgREST ``on_conflict``
    parameter / Postgres ``on conflict (...)`` clause). When it is ``None`` the rows are
    inserted as-is.
    """

    table: str
    rows: Sequence[Mapping[str, Any]]
    on_conflict: str | None = None


class RowSink(Protocol):
    """Write/read seam shared by the PostgREST and Postgres sinks."""

    def upsert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        on_conflict: str | None = None,
        batch_size: int = 500,
    ) -> int: ...

    def insert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        batch_size: int = 500,
    ) -> int: ...

    def select(
        self,
        table: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]: ...
