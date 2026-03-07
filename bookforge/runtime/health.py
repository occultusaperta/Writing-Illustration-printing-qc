from __future__ import annotations

import time
from typing import Any, Dict

import requests


class RuntimeHealthError(RuntimeError):
    pass


def check_http_health(url: str, timeout_s: int = 5) -> Dict[str, Any]:
    resp = requests.get(url, timeout=timeout_s)
    resp.raise_for_status()
    return resp.json() if resp.content else {"status": "unknown"}


def wait_for_health(url: str, *, timeout_s: int = 300, interval_s: float = 5.0) -> Dict[str, Any]:
    started = time.time()
    last_err: Exception | None = None
    while time.time() - started <= timeout_s:
        try:
            return check_http_health(url)
        except Exception as exc:
            last_err = exc
            time.sleep(interval_s)
    raise RuntimeHealthError(f"Runtime health check timed out for {url}: {last_err}")
