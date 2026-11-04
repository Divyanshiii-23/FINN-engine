"""Polite HTTP client: retries with backoff, per-host spacing, raw payload capture.

Every response body is written under data/raw/<source>/ with its URL and fetch
time, so any feed item can be traced back to the exact bytes it came from.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from ..models import FetchLog

# A browser-like UA is needed by the exchanges; it carries no personal data.
# Hosts whose documents FINN downloads on the strength of exchange data. A URL that
# arrives inside an exchange payload is untrusted input: fetching any host it names
# would let a crafted filing make the server request internal addresses.
EXCHANGE_HOSTS = ("bseindia.com", "nseindia.com")


def host_allowed(url: str, hosts: tuple[str, ...] = EXCHANGE_HOSTS) -> bool:
    u = urlparse(url)
    h = (u.hostname or "").lower()
    return u.scheme == "https" and any(h == d or h.endswith("." + d) for d in hosts)


UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


class HttpClient:
    def __init__(self, raw_dir: Path, min_interval_s: float = 1.0, timeout_s: float = 20.0, retries: int = 2):
        self.raw_dir = raw_dir
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*"})
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.retries = retries
        self._last: dict[str, float] = {}

    def _space(self, url: str) -> None:
        host = urlparse(url).netloc
        wait = self.min_interval_s - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def _save(self, source: str, url: str, body: bytes, suffix: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        h = hashlib.sha1(url.encode() + body[:4096]).hexdigest()[:16]
        d = self.raw_dir / source / day
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{h}{suffix}"
        path.write_bytes(body)
        (d / f"{h}.meta.json").write_text(json.dumps({"url": url, "fetched_at": datetime.now(timezone.utc).isoformat()}))
        return str(path)

    def get(
        self,
        source: str,
        target: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expect: str = "json",
        max_bytes: int = 25_000_000,
        hosts: tuple[str, ...] | None = None,
    ) -> tuple[Any, FetchLog]:
        """Returns (parsed body or None, log). Never raises for network errors.

        With `hosts`, the URL and every redirect it takes must stay on those hosts (https only)."""
        last_err: str | None = None
        status: int | None = None
        if hosts is not None and not host_allowed(url, hosts):
            return None, FetchLog(source=source, target=target, url=url, ok=False, error="host not allowed", fetched_at=_now())
        for attempt in range(self.retries + 1):
            self._space(url)
            try:
                r = self._fetch(url, params, headers, expect == "bytes", hosts)
                status = r.status_code
                if r.status_code == 0:
                    last_err = "redirected to a host that is not allowed"
                    break
                if r.status_code in (401, 403, 404, 410):
                    last_err = f"HTTP {r.status_code}"
                    break  # not retryable
                if r.status_code >= 500 or r.status_code == 429:
                    last_err = f"HTTP {r.status_code}"
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if expect == "bytes":
                    body = r.raw.read(max_bytes + 1, decode_content=True)
                    if len(body) > max_bytes:
                        last_err = f"file larger than {max_bytes} bytes"
                        break
                    path = self._save(source, r.url, body, ".pdf")
                    return body, FetchLog(source=source, target=target, url=r.url, ok=True, status=status, fetched_at=_now(), raw_path=path)
                body = r.content
                path = self._save(source, r.url, body, ".json")
                try:
                    data = r.json()
                except ValueError:
                    last_err = "response was not JSON"
                    break
                return data, FetchLog(source=source, target=target, url=r.url, ok=True, status=status, fetched_at=_now(), raw_path=path)
            except requests.RequestException as e:
                last_err = f"{type(e).__name__}: {str(e)[:160]}"
                time.sleep(1.0 * (attempt + 1))
        return None, FetchLog(source=source, target=target, url=url, ok=False, status=status, error=last_err, fetched_at=_now())


    def _fetch(self, url, params, headers, stream, hosts):
        if hosts is None:
            return self.session.get(url, params=params, headers=headers, timeout=self.timeout_s, stream=stream)
        for _ in range(6):
            r = self.session.get(url, params=params, headers=headers, timeout=self.timeout_s, stream=stream, allow_redirects=False)
            if not r.is_redirect:
                return r
            url, params = requests.compat.urljoin(r.url, r.headers.get("location", "")), None
            if not host_allowed(url, hosts):
                r.close()
                bad = requests.Response()
                bad.status_code, bad.url = 0, url
                return bad
        return r


def _now() -> datetime:
    return datetime.now(timezone.utc)
