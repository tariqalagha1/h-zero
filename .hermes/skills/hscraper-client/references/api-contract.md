# H-Scraper API Contract v1.2.0

> Derived from actual Pydantic v2 schemas in `backend/app/schemas/scrape.py` and
> `backend/app/api/v1/`. This is the authoritative reference for all agent interactions.

## Base URL

```
HSCRAPER_BASE_URL=https://scraper.internal
API base: {HSCRAPER_BASE_URL}/api/v1/
```

**Do NOT include `/api/v1` in the env var.** Skills append it internally.

## Authentication

Dual mode:

### 1. API Key (preferred for agents)
```
Header: X-API-Key: {API_KEY}
```
System-level `API_KEY` env var on the server. Set `HSCRAPER_API_KEY` on the agent side.

### 2. JWT (for human users)
```
POST /api/v1/auth/login
Body: { "username": "...", "password": "..." }
Returns: { "access_token": "...", "token_type": "bearer" }
```

**Agents use API Key auth exclusively.** JWT is for web UI accounts.

## Rate Limiting

- 10 req / 60s per key. Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## HTTP Timeouts

- `/scrape` is synchronous (6-stage pipeline). **Minimum timeout: 120 seconds.**

---

## Endpoint Groups

### Core Scraping

#### POST /api/v1/scrape
Submit a scrape. Multi-source via `sources` field. No separate `/scrape/multi` endpoint.

```json
// Request (ScrapeRequest Pydantic model)
{
  "workspace_type": "url",
  "url": "https://example.com",
  "query": "extract product names, prices, and descriptions",
  "fields": ["name", "price", "description"],
  "location": "global",
  "limit": 50,
  "sources": ["internal"],
  "strict_extraction": true,
  "required_fields": [],
  "minimum_completeness": 0
}
```

Fields (from actual schema):
- `workspace_type` (str) — "url" or "maps". Default "url".
- `url` (str, optional, max 2000) — target URL
- `login_url` / `login_username` / `login_password` — for authenticated scraping (optional)
- `query` (str, required, max 500) — natural language extraction intent. Goes through prompt injection guard (normalize_and_validate_prompt).
- `fields` (list[str], required, max 50 items) — fields to extract
- `location` (str, required, max 200) — mandatory even for non-maps
- `limit` (int, 1-100, default 50) — target records. Aliased with `target_records`.
- `sources` (list[str], default ["internal"]) — allowed: "internal", "google_maps", "web"
- `strict_extraction` (bool, default True)
- `required_fields` (list[str], optional) — fields that MUST be present
- `minimum_completeness` (int, 0-100, default 0)
- `request_id` (str, optional) — idempotency key

Response (ScrapeResponse):
```json
{
  "request_id": "uuid-or-user-provided",
  "status": "completed",
  "execution_time": 42.3,
  "total": 15,
  "data": [
    { "name": "...", "price": "...", "description": "..." }
  ],
  "sources": [{ "name": "internal", "count": 10 }, { "name": "web", "count": 5 }],
  "errors": [],
  "quality": {
    "duplicates_removed": 3,
    "coverage": 0.95,
    "confidence": 0.88,
    "missing_fields": { "price": 2, "description": 1 },
    "sources_used": ["internal", "web"],
    "sources_skipped": [],
    "execution_order": ["internal", "web"],
    "cross_source_duplicates_removed": 1,
    "source_reliability": { "internal": 0.9, "web": 0.7 },
    "fallback_used": false,
    "retries_triggered": []
  }
}
```

Key differences from earlier spec:
- **No `/scrape/multi`** endpoint. Multi-source is built into `/scrape` via `sources` field.
- Field is `limit` (not `max_pages`), range 1-100, default 50.
- `workspace_type` is "url" or "maps" — not `scrape_type`.
- Response is synchronous — returns data immediately, not a queued `run_id`.
- Response has `data` not `records`, `execution_time` not `duration_seconds`.

### Endpoints (all under /api/v1/)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | /scrape | API Key | Primary endpoint. Multi-source via sources field. |
| POST | /assistant/request-refinement | API Key | Prompt refinement. OpenAI→heuristic fallback. |
| GET | /scraping-types | None | List available workspace types. |
| POST | /jobs | API Key | Create recurring job config. |
| GET | /jobs | API Key | List jobs. |
| GET | /jobs/{id} | API Key | Get job config. |
| PATCH | /jobs/{id} | API Key | Update job. |
| DELETE | /jobs/{id} | API Key | Delete job. |
| POST | /jobs/{id}/start | API Key | Queue a run. |
| GET | /runs | API Key | List runs. |
| GET | /runs/{id} | API Key | Run detail. |
| POST | /runs/{id}/cancel | API Key | Cancel run. |
| POST | /runs/{id}/retry | API Key | Retry failed run. |
| GET | /results/{id} | API Key | Retrieve stored results. |
| POST | /exports | API Key | Generate export (csv/json/xlsx). |
| GET | /exports | API Key | List exports. |
| GET | /system/capabilities | None | Capabilities manifest. |
| GET | /system/diagnostics | API Key | Full system health. |
| GET | /health | None | Basic liveness. |
| GET | /health/full | API Key | Service-level health. |
| POST | /auth/register | None | Register user. |
| POST | /auth/login | None | JWT login. |
| POST | /api-keys | JWT | Create API key. |
| GET | /api-keys | JWT | List keys. |
| DELETE | /api-keys/{id} | JWT | Revoke key. |

## Error Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Validation error |
| 401 | Unauthorized |
| 404 | Not found |
| 409 | Conflict |
| 422 | Unprocessable |
| 429 | Rate limited |
| 500 | Server error |
| 503 | Service unavailable (health check failed) |

## Architectural Rules

1. **Timeout**: Minimum 120s. Scrape is synchronous and slow.
2. **Auth**: `X-API-Key` header. Skip JWT.
3. **Location**: Mandatory on every scrape. No default — user must provide.
4. **Query**: Max 500 chars. Goes through prompt injection guard. Natural language only.
5. **Partial results**: Check `quality.missing_fields`. Not failure.
6. **Rate limiting**: Read `X-RateLimit-Remaining`. Back off at 0.
7. **Assistant**: Always returns. Check `source` field.
8. **Never log**: `login_password` field.
9. **Never hardcode**: `/api/v1` in base URL env var.
10. **No JWT**: API key is purpose-built for agents.
