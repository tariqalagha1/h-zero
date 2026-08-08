"""H-Zero — E2E Browser Rendering Test.

Verifies that the headless browser fleet correctly renders pages,
parses DOM elements, and identifies interactive components.
"""

import asyncio
import json
import os
import sys
import pytest


# Skip if no browser available
pytestmark = pytest.mark.skipif(
    not os.environ.get("BROWSER_SANDBOX_URL"),
    reason="BROWSER_SANDBOX_URL not set — browser fleet not running",
)


MOCK_SITE_URL = os.environ.get("MOCK_SITE_URL", "http://localhost:8001")
SANDBOX_URL = os.environ.get("BROWSER_SANDBOX_URL", "http://localhost:9222")


class TestBrowserRendering:
    """Verify browser sandbox correctly renders and parses web pages."""

    async def test_sandbox_health(self):
        """Test sandbox health endpoint."""
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{SANDBOX_URL}/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] in ("healthy", "starting")

    async def test_navigate_and_render(self):
        """Test navigating to a URL and getting page content."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            # Navigate to mock site
            r = await client.post(
                f"{SANDBOX_URL}/navigate",
                json={"url": f"{MOCK_SITE_URL}/index.html"},
            )
            assert r.status_code == 200
            data = r.json()

            # Verify basic rendering
            assert "error" not in data, f"Navigation failed: {data}"
            assert data.get("title") == "H-Zero Test Site — Scientific Discovery Platform"
            assert data.get("status") == 200
            assert data.get("load_time_ms", 0) >= 0

            # Verify interactive elements found
            assert data.get("interactive_elements", 0) > 0, "No interactive elements found"

            elements = data.get("elements", [])
            assert len(elements) > 0, "Element list is empty"

    async def test_dom_extraction(self):
        """Test full DOM extraction with accessibility tree."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            # Navigate first
            await client.post(
                f"{SANDBOX_URL}/navigate",
                json={"url": f"{MOCK_SITE_URL}/index.html"},
            )

            # Get DOM
            r = await client.get(f"{SANDBOX_URL}/dom")
            assert r.status_code == 200
            data = r.json()

            assert "error" not in data
            assert data.get("title") is not None
            assert data.get("text") is not None, "No page text extracted"
            assert data.get("html_length", 0) > 100, "HTML content suspiciously small"

            # Verify key page elements
            text = data.get("text", "")
            assert "H-Zero Test Site" in text, "Title not found in extracted text"
            assert "Search" in text or "search" in text.lower(), "Search not found"

            # Verify elements array
            elements = data.get("elements", [])
            assert len(elements) > 0, "No interactive elements in DOM"

            # Check element structure
            for el in elements[:5]:
                assert "tag" in el, f"Element missing tag: {el}"
                assert "index" in el, f"Element missing index: {el}"

    async def test_click_interaction(self):
        """Test clicking an element on the page."""
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            # Navigate to mock site
            await client.post(
                f"{SANDBOX_URL}/navigate",
                json={"url": f"{MOCK_SITE_URL}/index.html"},
            )

            # Click search button by text
            r = await client.post(
                f"{SANDBOX_URL}/click",
                json={"text": "Search"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data.get("success") is True or "error" not in data

    async def test_type_and_search(self):
        """Test typing into an input and searching."""
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            # Navigate
            await client.post(
                f"{SANDBOX_URL}/navigate",
                json={"url": f"{MOCK_SITE_URL}/index.html"},
            )

            # Type into search box
            r = await client.post(
                f"{SANDBOX_URL}/type",
                json={"selector": "#search-input", "value": "aspirin"},
            )
            assert r.status_code == 200

            # Click search
            r = await client.post(
                f"{SANDBOX_URL}/click",
                json={"selector": "#search-btn"},
            )
            assert r.status_code == 200

            # Wait for results
            await asyncio.sleep(1)

            # Get DOM to verify results
            r = await client.get(f"{SANDBOX_URL}/dom")
            data = r.json()

            text = data.get("text", "")
            assert "aspirin" in text.lower(), "Search results not visible in DOM"

    async def test_page_text_contains_expected(self):
        """Test that extracted page text contains expected content."""
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{SANDBOX_URL}/navigate",
                json={"url": f"{MOCK_SITE_URL}/index.html"},
            )
            r = await client.get(f"{SANDBOX_URL}/dom")
            data = r.json()

            text = data.get("text", "")
            # Verify key structural elements visible
            assert "Welcome" in text
            assert "Research" in text or "research" in text.lower()
            assert "form" in text.lower() or "Submit" in text
