"""H-Zero — HTTP Prober.

Raw HTTP client for security testing — bypasses the browser layer to send
arbitrary HTTP requests, headers, and payloads directly.
Used alongside (not instead of) the Browser Fleet for API-level security testing.

Supports: custom headers, non-standard methods, parameter fuzzing,
response header inspection, timing analysis, and redirect following.

Scope enforcement is built-in — all requests validated against ScopeEnforcer.
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import structlog

from services.agent.security.scope_enforcer import ScopeEnforcer, ScopeDecision, create_local_scope

logger = structlog.get_logger("h_zero.http_prober")


@dataclass
class HTTPProbeRequest:
    """A raw HTTP probe request."""
    method: str = "GET"
    url: str = ""
    headers: dict = field(default_factory=dict)
    body: Optional[str] = None
    timeout: int = 30
    follow_redirects: bool = False
    verify_ssl: bool = False


@dataclass
class HTTPProbeResponse:
    """Response from a raw HTTP probe."""
    request: HTTPProbeRequest
    status_code: int = 0
    headers: dict = field(default_factory=dict)
    body: str = ""
    body_length: int = 0
    elapsed_ms: float = 0.0
    redirect_chain: list[str] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 400

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    @property
    def is_server_error(self) -> bool:
        return self.status_code >= 500

    def header(self, name: str) -> Optional[str]:
        """Case-insensitive header lookup."""
        name_lower = name.lower()
        for k, v in self.headers.items():
            if k.lower() == name_lower:
                return v
        return None

    def has_header_containing(self, name: str, substring: str) -> bool:
        """Check if a header exists and contains a substring."""
        value = self.header(name)
        return value is not None and substring.lower() in value.lower()

    def body_contains(self, pattern: str) -> bool:
        """Check if response body contains a pattern (case-insensitive)."""
        return pattern.lower() in self.body.lower()

    def body_matches_regex(self, pattern: str) -> bool:
        """Check if response body matches a regex."""
        import re
        return bool(re.search(pattern, self.body, re.IGNORECASE | re.DOTALL))

    def timing_category(self) -> str:
        """Categorize response timing: fast, normal, slow, very_slow."""
        if self.elapsed_ms < 100:
            return "fast"
        if self.elapsed_ms < 1000:
            return "normal"
        if self.elapsed_ms < 5000:
            return "slow"
        return "very_slow"


class HTTPProber:
    """Raw HTTP client for security testing.

    Sends arbitrary HTTP requests directly — no browser, no DOM rendering.
    Used for: API fuzzing, header inspection, parameter manipulation,
    SQLi/XSS payload injection, auth bypass testing.
    """

    DEFAULT_HEADERS = {
        "User-Agent": "H-Zero-Security-Prober/1.0",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
    }

    def __init__(self, session=None, scope: ScopeEnforcer = None):
        self._session = session
        self._scope = scope or create_local_scope()

    async def _get_session(self):
        """Lazy-create HTTP session."""
        if self._session is None:
            import httpx
            self._session = httpx.AsyncClient(
                timeout=30,
                follow_redirects=False,
                verify=False,
            )
        return self._session

    async def probe(self, request: HTTPProbeRequest) -> HTTPProbeResponse:
        """Send a raw HTTP probe and return the full response."""
        # Enforce scope boundaries
        scope_result = self._scope.check(request.url)
        if scope_result.decision != ScopeDecision.ALLOWED:
            logger.warning(f"Scope blocked probe to {request.url}: {scope_result.reason}")
            return HTTPProbeResponse(
                request=request,
                status_code=0,
                error=f"OUT_OF_SCOPE: {scope_result.reason}",
            )

        start = time.monotonic()
        redirects = []

        try:
            session = await self._get_session()

            # Merge headers
            headers = {**self.DEFAULT_HEADERS, **request.headers}

            response = await session.request(
                method=request.method,
                url=request.url,
                headers=headers,
                content=request.body or None,
                follow_redirects=request.follow_redirects,
            )

            elapsed = (time.monotonic() - start) * 1000

            return HTTPProbeResponse(
                request=request,
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text[:50000],  # Cap body at 50KB
                body_length=len(response.content),
                elapsed_ms=elapsed,
                redirect_chain=[str(r.url) for r in response.history],
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return HTTPProbeResponse(
                request=request,
                error=str(e)[:500],
                elapsed_ms=elapsed,
            )

    async def probe_with_payload(
        self,
        url: str,
        method: str = "GET",
        parameter: str = "",
        payload: str = "",
        target_location: str = "query",
        extra_headers: dict = None,
    ) -> HTTPProbeResponse:
        """Send a probe with a security payload at a specific location.

        target_location: query, body, header, path, cookie
        """
        if target_location == "query":
            # Append or replace query parameter
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{parameter}={payload}"

        elif target_location == "body":
            import json as json_mod
            method = method or "POST"
            body = json_mod.dumps({parameter: payload})

        elif target_location == "header":
            extra_headers = extra_headers or {}
            extra_headers[parameter] = payload

        elif target_location == "path":
            # Inject into URL path
            parsed = urlparse(url)
            path = parsed.path.rstrip("/") + f"/{payload}"
            url = f"{parsed.scheme}://{parsed.netloc}{path}"
            if parsed.query:
                url += f"?{parsed.query}"

        body_content = None
        if target_location == "body":
            body_content = json.dumps({parameter: payload})

        request = HTTPProbeRequest(
            method=method,
            url=url,
            headers=extra_headers or {},
            body=body_content,
        )
        return await self.probe(request)

    async def fuzz_parameter(
        self,
        url: str,
        parameter: str,
        payloads: list[str],
        method: str = "GET",
        target_location: str = "query",
        concurrency: int = 5,
    ) -> list[HTTPProbeResponse]:
        """Fuzz a parameter with multiple payloads concurrently."""
        semaphore = asyncio.Semaphore(concurrency)

        async def fuzz_one(payload: str) -> HTTPProbeResponse:
            async with semaphore:
                return await self.probe_with_payload(
                    url=url,
                    method=method,
                    parameter=parameter,
                    payload=payload,
                    target_location=target_location,
                )

        tasks = [fuzz_one(p) for p in payloads]
        return await asyncio.gather(*tasks)

    async def baseline(self, url: str, method: str = "GET") -> HTTPProbeResponse:
        """Send a baseline (clean) request for comparison."""
        request = HTTPProbeRequest(method=method, url=url)
        return await self.probe(request)

    async def discover_endpoints(
        self,
        base_url: str,
        wordlist: list[str],
        extensions: list[str] = None,
    ) -> list[HTTPProbeResponse]:
        """Discover endpoints by fuzzing path segments."""
        ext_list = extensions or ["", "/", ".json", ".html", ".php"]
        urls = []
        for word in wordlist:
            for ext in ext_list:
                urls.append(urljoin(base_url.rstrip("/") + "/", word.lstrip("/") + ext))

        tasks = []
        for url in urls:
            request = HTTPProbeRequest(method="GET", url=url)
            tasks.append(self.probe(request))

        return await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self):
        if self._session:
            await self._session.aclose()
            self._session = None


# Singleton
_prober: Optional[HTTPProber] = None


def get_http_prober() -> HTTPProber:
    global _prober
    if _prober is None:
        _prober = HTTPProber()
    return _prober
