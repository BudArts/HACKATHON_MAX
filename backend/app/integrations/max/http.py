from __future__ import annotations

import ssl
from pathlib import Path
from typing import Any

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)


class MaxApiError(Exception):
    def __init__(self, operation: str, status_code: int, detail: Any = None) -> None:
        super().__init__(f"MAX API {operation} -> HTTP {status_code}")
        self.operation = operation
        self.status_code = status_code
        self.detail = detail

    @property
    def code(self) -> str | None:
        if isinstance(self.detail, dict):
            value = self.detail.get("code") or self.detail.get("message")
            return str(value) if value is not None else None
        return None

    @property
    def retryable(self) -> bool:
        return self.status_code in {408, 425, 429, 500, 502, 503, 504}


def ssl_verify(ca_bundle: str, verify_ssl: bool = True) -> ssl.SSLContext | bool:
    if not verify_ssl:
        return False
    if not ca_bundle:
        return True
    path = Path(ca_bundle)
    if not path.is_file() or "BEGIN CERTIFICATE" not in path.read_text(encoding="utf-8", errors="ignore"):
        return True
    context = ssl.create_default_context()
    try:
        context.load_verify_locations(cafile=str(path))
    except ssl.SSLError as exc:
        log.warning("ca_bundle_invalid", path=str(path), error=str(exc))
        return True
    return context


def make_client(ca_bundle: str, timeout: float, verify_ssl: bool = True) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
        verify=ssl_verify(ca_bundle, verify_ssl),
        limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )


def raise_for_status_detail(response: httpx.Response, operation: str) -> None:
    if response.is_success:
        return
    detail: Any
    try:
        detail = response.json()
    except ValueError:
        detail = response.text[:500]
    raise MaxApiError(operation, response.status_code, detail)
