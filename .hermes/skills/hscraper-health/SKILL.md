---
name: hscraper-health
description: Check H-Scraper health, diagnostics, and capabilities.
version: 1.0.0
---

# H-Scraper Health Skill

System health monitoring, diagnostics, and capability discovery for H-Scraper.

## Prerequisites

- `HSCRAPER_BASE_URL` env var (domain only, no `/api/v1`)
- `HSCRAPER_API_KEY` env var for authenticated endpoints
- See `hscraper-client` skill for shared API contract and auth rules

## Endpoints

| Action | Method | Path | Auth |
|--------|--------|------|------|
| Basic health | GET | `/api/v1/health` | No |
| Full health | GET | `/api/v1/health/full` | Yes |
| Capabilities | GET | `/api/v1/system/capabilities` | No |
| Diagnostics | GET | `/api/v1/system/diagnostics` | Yes |

## Response Shapes

### GET /api/v1/health (no auth) — Quick liveness check
```json
{ "status": "healthy", "version": "1.2.0" }
```

### GET /api/v1/health/full (auth) — Service-level detail
```json
{
  "status": "healthy",
  "services": {
    "database": { "status": "connected", "latency_ms": 2.3 },
    "redis": { "status": "connected", "latency_ms": 0.8 },
    "playwright": { "status": "ready", "browsers": ["chromium"] },
    "openai": { "status": "available", "models": ["gpt-4o","gpt-4o-mini"] },
    "celery": { "status": "running", "active_workers": 4 }
  },
  "uptime_seconds": 86400,
  "version": "1.2.0"
}
```

### GET /api/v1/system/capabilities (no auth) — Feature manifest
```json
{
  "version": "1.2.0",
  "scrape_types": ["structured","maps","search","listings","news","social","custom"],
  "export_formats": ["csv","json","xlsx"],
  "max_pages_per_scrape": 50,
  "max_concurrent_jobs": 10,
  "features": { "multi_source":true, "ai_refinement":true, "vector_search":true, "maps_integration":true }
}
```

## Usage Patterns

### Pre-Flight Check
```
Before any scrape: GET /api/v1/health → confirm "healthy"
If unhealthy: report down services, don't submit
```

### Diagnose Failures
```
Scrape keeps failing:
1. GET /api/v1/health/full
2. Report degraded services:
   - database latency high → "Database is slow, retry later"
   - playwright not ready → "Browser engine down, web scraping will fail"
   - celery no workers → "Runs will queue but never execute"
```

### Discover Capabilities
```
User asks "What can H-Scraper do?"
→ GET /api/v1/system/capabilities
→ Validate requests: "Max 50 pages, exports in csv/json/xlsx"
```

## Pitfalls

- **Don't build your own health poll loop.** Use /health and /health/full.
- **Degraded ≠ dead.** OpenAI down → assistant still works (heuristic). Playwright down → only web scraping fails.
- **Check once per session, not before every request.**
