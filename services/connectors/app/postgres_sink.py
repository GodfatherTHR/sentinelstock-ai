from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

import psycopg

from .postgrest_sink import chunked

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _identifier(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


class PostgresSink:
    """RowSink implementation backed by a direct Postgres connection.

    Requires ``SUPABASE_DB_URL`` (or ``DATABASE_URL``). Useful for local Supabase or a
    self-hosted database; the hosted path uses :class:`~app.postgrest_sink.PostgrestSink`.
    """

    def __init__(self, dsn: str, *, batch_size: int = 500) -> None:
        self._dsn = dsn
        self._batch_size = batch_size
        self._conn: psycopg.Connection | None = None

    def _connect(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._dsn, autocommit=False)
        return self._conn

    def _columns(self, rows: Sequence[Mapping[str, Any]]) -> list[str]:
        return list(dict.fromkeys(key for row in rows for key in row))

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
        table = _identifier(table)
        columns = [_identifier(column) for column in self._columns(rows)]
        conflict_columns = [column.strip() for column in (on_conflict or "").split(",") if column.strip()]
        sql = (
            f"insert into public.{table} ({', '.join(columns)}) "
            f"select {', '.join(columns)} "
            f"from jsonb_populate_recordset(null::public.{table}, %s::jsonb)"
        )
        if conflict_columns:
            targets = ", ".join(_identifier(column) for column in conflict_columns)
            updates = [
                f"{column} = excluded.{column}" for column in columns if column not in conflict_columns
            ]
            action = f"update set {', '.join(updates)}" if updates else "nothing"
            sql += f" on conflict ({targets}) do {action}"

        written = 0
        for chunk in chunked(rows, batch_size or self._batch_size):
            payload = json.dumps([dict(row) for row in chunk], default=str)
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, (payload,))
                    written += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else len(chunk)
                conn.commit()
        return written

    def insert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        batch_size: int = 500,
    ) -> int:
        return self.upsert(table, rows, on_conflict=None, batch_size=batch_size)

    def select(self, table: str, *, params: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
        table = _identifier(table)
        params = params or {}
        columns = params.get("select", "*")
        sql = f"select {columns} from public.{table}"
        if params.get("where"):
            sql += f" where {params['where']}"
        if params.get("order"):
            sql += f" order by {params['order']}"
        if params.get("limit"):
            sql += f" limit {int(params['limit'])}"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                names = [description.name for description in cursor.description or []]
                return [dict(zip(names, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
