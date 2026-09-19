from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from typing import Any, Mapping


DEFAULT_USER_AGENT = "SentinelStockAI-Connectors/0.2 (data ingestion; contact: ops@sentinelstock.local)"

# Upstream APIs in this connector set throttle or fail transiently; retry these.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """Raised when an HTTP request fails. Providers convert this to ProviderUnavailable."""


def request_bytes(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: int = 60,
    method: str = "GET",
    data: bytes | None = None,
    retries: int = 0,
    backoff: float = 2.0,
) -> bytes:
    merged = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Encoding": "gzip"}
    if headers:
        merged.update(headers)
    attempt = 0
    while True:
        request = urllib.request.Request(url, headers=merged, method=method, data=data)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    body = gzip.decompress(body)
                return body
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:400]
            if exc.headers.get("Content-Encoding", "").lower() == "gzip":
                try:
                    detail = gzip.decompress(detail)[:400]
                except OSError:
                    pass
            if exc.code in RETRYABLE_STATUS and attempt < retries:
                attempt += 1
                time.sleep(backoff ** attempt)
                continue
            raise FetchError(f"{method} {url} -> HTTP {exc.code}: {detail!r}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                attempt += 1
                time.sleep(backoff ** attempt)
                continue
            raise FetchError(f"{method} {url} -> {exc.reason}") from exc


def request_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: int = 60,
    method: str = "GET",
    payload: Any | None = None,
    retries: int = 0,
    backoff: float = 2.0,
) -> Any:
    merged = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        merged["Content-Type"] = "application/json"
    body = request_bytes(url, headers=merged, timeout=timeout, method=method, data=data, retries=retries, backoff=backoff)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def download(url: str, *, timeout: int = 300, retries: int = 2) -> bytes:
    return request_bytes(url, timeout=timeout, retries=retries)
