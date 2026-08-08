---
name: hscraper-jobs
description: Manage H-Scraper jobs — create, start, cancel, retry runs.
version: 1.0.0
---

# H-Scraper Jobs Skill

Job lifecycle management for H-Scraper. Create recurring scrape configurations, start runs, monitor progress, cancel or retry.

## Prerequisites

- `HSCRAPER_BASE_URL` env var (domain only, no `/api/v1`)
- `HSCRAPER_API_KEY` env var for authentication
- See `hscraper-client` skill for the shared API contract, rate limiting, and auth rules

## Endpoints Used

| Action | Method | Path |
|--------|--------|------|
| Create job | POST | `/api/v1/jobs` |
| List jobs | GET | `/api/v1/jobs` |
| Get job | GET | `/api/v1/jobs/{id}` |
| Update job | PATCH | `/api/v1/jobs/{id}` |
| Delete job | DELETE | `/api/v1/jobs/{id}` |
| Start run | POST | `/api/v1/jobs/{id}/start` |
| List runs | GET | `/api/v1/runs` |
| Get run | GET | `/api/v1/runs/{id}` |
| Cancel run | POST | `/api/v1/runs/{id}/cancel` |
| Retry run | POST | `/api/v1/runs/{id}/retry` |
| Run logs | GET | `/api/v1/runs/{id}/logs` |
| Run events | GET | `/api/v1/runs/{id}/events` |

## Usage Patterns

### Create a Job and Start a Run

```
User says: "Set up a daily scrape of example.com for prices"

1. POST /api/v1/jobs with:
   { "name": "Daily price check", "url": "https://example.com",
     "query": "Extract product names and prices", "fields": ["name","price"],
     "location": "global", "schedule": "daily" }

2. Tell user the job_id

3. If user wants to run now: POST /api/v1/jobs/{job_id}/start
   Returns run_id — then use hscraper-client skill to poll and retrieve results
```

### Cancel a Run

```
POST /api/v1/runs/{run_id}/cancel
Verify: GET /api/v1/runs/{run_id} → status should be "cancelled"
```

### Retry a Failed Run

```
POST /api/v1/runs/{run_id}/retry
Wait for new run_id in response, then poll as usual.
```

### Monitor Runs

```
GET /api/v1/runs?job_id={job_id}&limit=50
Filter: ?status=failed or ?status=partial
```

## Pitfalls

- **Starting a run queues it, doesn't execute immediately.** Use hscraper-client to poll.
- **Cancelling is best-effort.** A run mid-scrape may still complete.
- **Retry creates a new run.** You get a new run_id.
- **List endpoints support pagination.** Use `?limit=` and check response headers.
