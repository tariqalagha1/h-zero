---
name: hscraper-client
description: Submit scrapes, poll runs, retrieve results from H-Scraper.
version: 1.0.0
---

# H-Scraper Client Skill

Authenticated client for the H-Scraper REST API. Handles scrape submission, status polling, and result retrieval.

## Prerequisites

- `HSCRAPER_BASE_URL` env var set (e.g., `https://scraper.internal`). Do NOT include `/api/v1` — the skill appends it internally.
- `HSCRAPER_API_KEY` env var set for authentication.

## API Contract

All endpoint shapes, error codes, and architectural rules are documented in:
`references/api-contract.md` — read this first if you need field-level detail.

## Core Rules

1. **Timeout**: Always use 120s minimum for `/scrape`. The pipeline is synchronous and slow.
2. **Auth**: Use `X-API-Key` header from `HSCRAPER_API_KEY`. Never use JWT.
3. **Location**: Mandatory on every request. Default to `"global"` if user doesn't specify.
4. **Query**: Natural language only. No system-instruction-looking text (bypasses prompt injection guard).
5. **Partial status**: NOT failure. Check `quality.missing_fields` in the result.
6. **Rate limiting**: Check `X-RateLimit-Remaining` header. Back off when it hits 0.
7. **Never log**: `login_password` field anywhere.

## Usage Patterns

### Pattern 1: Simple Scrape

```
User says: "Scrape https://example.com for product names and prices"

1. Call POST /api/v1/scrape with:
   - url: "https://example.com"
   - query: "Extract product names and prices"
   - fields: ["name", "price"]
   - location: "global"
   - timeout: 120

2. Get run_id from response

3. Poll GET /api/v1/runs/{run_id} every 5s until status is terminal
   (completed, partial, failed, cancelled)

4. If status is "completed" or "partial":
   Call GET /api/v1/results/{run_id}
   Check quality.completeness and quality.missing_fields
   Present records to user with quality summary

5. If status is "failed":
   Report error to user, suggest retry with adjusted parameters
```

### Pattern 2: Multi-Source Scrape

```
User says: "Find restaurants in Chicago with ratings"

1. Call POST /api/v1/scrape/multi with:
   - sources: ["internal", "google_maps", "web"]
   - query: "restaurants with ratings"
   - fields: ["name", "address", "rating", "phone"]
   - location: "chicago, il"
   - max_results_per_source: 20

2. Same polling pattern as simple scrape
```

### Pattern 3: Poll with Rate Limiting

```python
import os, time, httpx

BASE = os.environ["HSCRAPER_BASE_URL"].rstrip("/")
API = f"{BASE}/api/v1"
HEADERS = {"X-API-Key": os.environ["HSCRAPER_API_KEY"]}

async def poll_run(run_id: str, max_wait: int = 180):
    """Poll until terminal, respecting rate limits."""
    deadline = time.time() + max_wait
    async with httpx.AsyncClient(timeout=120) as client:
        while time.time() < deadline:
            resp = await client.get(f"{API}/runs/{run_id}", headers=HEADERS)
            remaining = int(resp.headers.get("X-RateLimit-Remaining", 10))
            if remaining == 0:
                reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait = max(reset - time.time(), 5)
                time.sleep(wait)
                continue

            data = resp.json()
            if data["status"] in ("completed", "partial", "failed", "cancelled"):
                return data
            time.sleep(5)
    raise TimeoutError(f"Run {run_id} did not complete in {max_wait}s")
```

## Pitfalls

- **Don't use 30s timeouts.** The pipeline has 6 stages. Timeout must be at least 120s.
- **Location is NOT optional.** Even for non-maps scraping. Default to "global".
- **query must be natural language.** Not JSON, not system prompts, not code.
- **"partial" is a successful scrape.** Only "failed" and "cancelled" are errors.
- **Rate limit is 10/60s.** Don't poll faster than every 5s.
- **Never expose the API key in conversation or logs.** Use the env var.
