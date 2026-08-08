"""H-Zero — Browser Sandbox Service.

Isolated headless browser instances with anti-detection patches.
Each sandbox runs a single Playwright Chromium instance with stealth mode.
Exposes a simple HTTP API for the ReAct loop to drive browser actions.
"""

import asyncio
import hashlib
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger("h_zero.browser.sandbox")

# ── Anti-Detection Configuration ─────────────────────────────────────────────

STEALTH_CONFIG = {
    "headless": os.environ.get("BROWSER_HEADLESS", "true").lower() == "true",
    "stealth_mode": os.environ.get("BROWSER_STEALTH_MODE", "true").lower() == "true",
    "proxy": {
        "server": os.environ.get("PROXY_URL", ""),
        "username": os.environ.get("PROXY_USERNAME", ""),
        "password": os.environ.get("PROXY_PASSWORD", ""),
    } if os.environ.get("PROXY_URL") else None,
}

# ── Browser Instance ─────────────────────────────────────────────────────────


class BrowserSandbox:
    """Single isolated browser instance with stealth patches."""

    def __init__(self, sandbox_id: str = ""):
        self.id = sandbox_id or f"sandbox-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]}"
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        self._active = False
        self._created_at = datetime.now(timezone.utc).isoformat()
        self._page_count = 0
        self._action_count = 0

    async def start(self) -> dict:
        """Launch browser with anti-detection patches."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-blink-features=AutomationControlled",
            ]

            if STEALTH_CONFIG["proxy"] and STEALTH_CONFIG["proxy"]["server"]:
                launch_args.append(f"--proxy-server={STEALTH_CONFIG['proxy']['server']}")

            self._browser = await self._playwright.chromium.launch(
                headless=STEALTH_CONFIG["headless"],
                args=launch_args,
            )

            # Create context with anti-detection
            context_args = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "geolocation": {"latitude": 40.7128, "longitude": -74.0060},
                "permissions": ["geolocation"],
            }

            if STEALTH_CONFIG["proxy"] and STEALTH_CONFIG["proxy"]["server"]:
                context_args["proxy"] = STEALTH_CONFIG["proxy"]

            self._context = await self._browser.new_context(**context_args)

            # Apply stealth patches
            if STEALTH_CONFIG["stealth_mode"]:
                await self._apply_stealth()

            self._page = await self._context.new_page()
            self._active = True

            logger.info(f"Sandbox {self.id} started")

            return {"id": self.id, "status": "started", "created_at": self._created_at}

        except Exception as e:
            logger.error(f"Sandbox {self.id} start failed: {e}")
            return {"id": self.id, "status": "failed", "error": str(e)[:500]}

    async def _apply_stealth(self):
        """Apply anti-detection patches to all pages."""
        if not self._context:
            return

        await self._context.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => false });

            // Override chrome runtime
            window.chrome = { runtime: {} };

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );

            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
        """)

    async def navigate(self, url: str, timeout: int = 30000) -> dict:
        """Navigate to a URL and return page snapshot."""
        if not self._page:
            return {"error": "No active page"}

        try:
            start = time.monotonic()
            response = await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            load_time = int((time.monotonic() - start) * 1000)

            title = await self._page.title()
            content = await self._page.content()
            text = await self._page.inner_text("body")

            # Extract interactive elements
            interactive = await self._page.evaluate("""() => {
                const elements = document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [onclick]'
                );
                return Array.from(elements).map((el, i) => ({
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    text: (el.textContent || '').trim().slice(0, 100),
                    id: el.id || '',
                    name: el.name || '',
                    href: el.href || '',
                    placeholder: el.placeholder || '',
                    visible: el.offsetParent !== null,
                }));
            }""")

            content_hash = hashlib.sha256(content.encode()).hexdigest()

            self._page_count += 1
            return {
                "url": url,
                "title": title,
                "status": response.status if response else 0,
                "load_time_ms": load_time,
                "content_hash": content_hash,
                "text": text[:5000],
                "interactive_elements": len(interactive),
                "elements": interactive[:200],
            }

        except Exception as e:
            return {"error": str(e)[:500]}

    async def click(self, selector: str = None, index: int = None, text: str = None) -> dict:
        """Click an element by selector, interactive index, or text content."""
        if not self._page:
            return {"error": "No active page"}

        try:
            start = time.monotonic()
            target = None

            if selector:
                target = self._page.locator(selector).first
            elif text:
                target = self._page.get_by_text(text, exact=False).first
            elif index is not None:
                target = self._page.locator(f"[data-hzero-idx='{index}']")
                if not await target.count():
                    # Fallback: click by nth interactive element
                    target = self._page.locator(
                        "a, button, input, select, textarea, [role='button']"
                    ).nth(index)

            if not target:
                return {"error": "No target element found"}

            await target.click(timeout=10000)
            duration = int((time.monotonic() - start) * 1000)

            # Wait for any navigation or network idle
            await self._page.wait_for_load_state("networkidle", timeout=5000)

            self._action_count += 1
            return {"action": "click", "success": True, "duration_ms": duration}

        except Exception as e:
            return {"action": "click", "success": False, "error": str(e)[:300]}

    async def type_text(self, selector: str, value: str) -> dict:
        """Type text into an input field."""
        if not self._page:
            return {"error": "No active page"}

        try:
            start = time.monotonic()
            target = self._page.locator(selector).first
            await target.fill("")
            await target.type(value, delay=50)
            duration = int((time.monotonic() - start) * 1000)

            self._action_count += 1
            return {"action": "type", "selector": selector, "success": True, "duration_ms": duration}

        except Exception as e:
            return {"action": "type", "success": False, "error": str(e)[:300]}

    async def scroll(self, direction: str = "down", amount: int = 300) -> dict:
        """Scroll the page."""
        if not self._page:
            return {"error": "No active page"}

        try:
            delta = amount if direction == "down" else -amount
            await self._page.evaluate(f"window.scrollBy(0, {delta})")
            self._action_count += 1
            return {"action": "scroll", "direction": direction, "amount": amount, "success": True}

        except Exception as e:
            return {"action": "scroll", "success": False, "error": str(e)[:300]}

    async def screenshot(self) -> dict:
        """Take a full-page screenshot."""
        if not self._page:
            return {"error": "No active page"}

        try:
            data = await self._page.screenshot(full_page=True, type="png")
            return {"screenshot": True, "size_bytes": len(data)}
        except Exception as e:
            return {"screenshot": False, "error": str(e)[:300]}

    async def get_dom(self) -> dict:
        """Get current DOM state including accessibility tree."""
        if not self._page:
            return {"error": "No active page"}

        try:
            title = await self._page.title()
            url = self._page.url
            text = await self._page.inner_text("body")
            html = await self._page.content()

            # Extract interactive elements with positions
            elements = await self._page.evaluate("""() => {
                const items = document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [onclick], form'
                );
                return Array.from(items).map((el, i) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        index: i,
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        text: (el.textContent || el.title || el.value || '').trim().slice(0, 150),
                        id: el.id || '',
                        name: el.name || '',
                        href: el.href || '',
                        placeholder: el.placeholder || '',
                        visible: el.offsetParent !== null && rect.width > 0 && rect.height > 0,
                        bounds: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                    };
                });
            }""")

            content_hash = hashlib.sha256(html.encode()).hexdigest()

            return {
                "url": url,
                "title": title,
                "text": text[:10000],
                "html_length": len(html),
                "content_hash": content_hash,
                "interactive_elements": len(elements),
                "elements": elements,
            }

        except Exception as e:
            return {"error": str(e)[:500]}

    async def execute_js(self, script: str) -> dict:
        """Execute arbitrary JavaScript in the page context."""
        if not self._page:
            return {"error": "No active page"}

        try:
            result = await self._page.evaluate(script)
            return {"result": str(result)[:2000]} if result is not None else {"result": None}
        except Exception as e:
            return {"error": str(e)[:500]}

    async def close(self):
        """Gracefully shut down the sandbox."""
        self._active = False
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

    def status(self) -> dict:
        return {
            "id": self.id,
            "active": self._active,
            "page_count": self._page_count,
            "action_count": self._action_count,
            "created_at": self._created_at,
        }


# ── Sandbox HTTP API Server ──────────────────────────────────────────────────

from aiohttp import web

routes = web.RouteTableDef()
_sandbox: Optional[BrowserSandbox] = None


async def get_sandbox() -> BrowserSandbox:
    global _sandbox
    if _sandbox is None or not _sandbox._active:
        _sandbox = BrowserSandbox()
        await _sandbox.start()
    return _sandbox


@routes.get("/health")
async def health(request: web.Request) -> web.Response:
    sandbox = _sandbox
    return web.json_response({
        "status": "healthy" if sandbox and sandbox._active else "starting",
        "sandbox_id": sandbox.id if sandbox else None,
    })


@routes.get("/status")
async def status(request: web.Request) -> web.Response:
    sandbox = await get_sandbox()
    return web.json_response(sandbox.status())


@routes.post("/navigate")
async def navigate(request: web.Request) -> web.Response:
    data = await request.json()
    url = data.get("url", "")
    if not url:
        return web.json_response({"error": "url required"}, status=400)
    sandbox = await get_sandbox()
    result = await sandbox.navigate(url)
    return web.json_response(result)


@routes.post("/click")
async def click(request: web.Request) -> web.Response:
    data = await request.json()
    sandbox = await get_sandbox()
    result = await sandbox.click(
        selector=data.get("selector"),
        index=data.get("index"),
        text=data.get("text"),
    )
    return web.json_response(result)


@routes.post("/type")
async def type_text(request: web.Request) -> web.Response:
    data = await request.json()
    sandbox = await get_sandbox()
    result = await sandbox.type_text(
        selector=data.get("selector", ""),
        value=data.get("value", ""),
    )
    return web.json_response(result)


@routes.post("/scroll")
async def scroll(request: web.Request) -> web.Response:
    data = await request.json()
    sandbox = await get_sandbox()
    result = await sandbox.scroll(
        direction=data.get("direction", "down"),
        amount=data.get("amount", 300),
    )
    return web.json_response(result)


@routes.post("/screenshot")
async def screenshot(request: web.Request) -> web.Response:
    sandbox = await get_sandbox()
    result = await sandbox.screenshot()
    return web.json_response(result)


@routes.get("/dom")
async def get_dom(request: web.Request) -> web.Response:
    sandbox = await get_sandbox()
    result = await sandbox.get_dom()
    return web.json_response(result)


@routes.post("/execute")
async def execute_js(request: web.Request) -> web.Response:
    data = await request.json()
    sandbox = await get_sandbox()
    result = await sandbox.execute_js(data.get("script", ""))
    return web.json_response(result)


@routes.post("/shutdown")
async def shutdown(request: web.Request) -> web.Response:
    sandbox = _sandbox
    if sandbox:
        await sandbox.close()
    return web.json_response({"status": "shutdown"})


def main():
    app = web.Application()
    app.add_routes(routes)

    port = int(os.environ.get("BROWSER_SANDBOX_PORT", "9222"))
    logger.info(f"Browser sandbox API starting on port {port}")

    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
