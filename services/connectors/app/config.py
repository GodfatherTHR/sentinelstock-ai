from __future__ import annotations

import os
from dataclasses import dataclass

# Organization id created by supabase/seed.sql. External rows are attributed to it so
# org-scoped tables (crop_observations) stay readable through RLS.
DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


@dataclass(frozen=True)
class ConnectorSettings:
    """Infrastructure settings shared by every connector."""

    database_url: str | None
    supabase_url: str | None
    supabase_service_role_key: str | None
    organization_id: str
    openrouter_api_key: str | None
    poll_interval_seconds: int

    @classmethod
    def from_env(cls) -> "ConnectorSettings":
        return cls(
            database_url=os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL"),
            supabase_url=os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL"),
            supabase_service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
            organization_id=os.environ.get("INGEST_ORGANIZATION_ID", DEFAULT_ORGANIZATION_ID),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
            poll_interval_seconds=int(os.environ.get("CONNECTOR_POLL_SECONDS", "3600")),
        )

    def require_database_url(self) -> str:
        url = self.database_url
        if not url:
            raise RuntimeError(
                "SUPABASE_DB_URL (or DATABASE_URL) is not set. Set it locally with "
                "`$env:SUPABASE_DB_URL = 'postgresql://...'` before running the connector."
            )
        return url

    def require_postgrest(self) -> tuple[str, str]:
        """Return ``(base_url, service_role_key)`` for the Supabase PostgREST endpoint.

        Preferred over a direct Postgres DSN because it needs no database password and
        the service role bypasses RLS for writes.
        """
        if not self.supabase_url or not self.supabase_service_role_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set to ingest "
                "through PostgREST (recommended). Alternatively set SUPABASE_DB_URL."
            )
        return self.supabase_url.rstrip("/"), self.supabase_service_role_key

    def require_openrouter_key(self) -> str:
        if not self.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set.")
        return self.openrouter_api_key


def env_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)
