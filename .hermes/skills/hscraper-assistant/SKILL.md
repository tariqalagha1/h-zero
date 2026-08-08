---
name: hscraper-assistant
description: Refine scrape queries and detect types via H-Scraper AI.
version: 1.0.0
---

# H-Scraper Assistant Skill

AI-powered prompt refinement and scrape type auto-detection for H-Scraper.

## Prerequisites

- `HSCRAPER_BASE_URL` env var (domain only, no `/api/v1`)
- `HSCRAPER_API_KEY` env var for authentication (required for refinement, not for types)
- See `hscraper-client` skill for shared API contract and auth rules

## Key Facts

- The assistant endpoint **always works**. OpenAI is primary, deterministic heuristic is fallback.
- Check the `source` field in the response: "openai" vs "heuristic"
- `/scraping-types` requires **no authentication**
- Refinement is optional — skip it if the user's query is already well-formed

## Endpoints Used

### POST /api/v1/assistant/request-refinement

```json
// Request
{ "raw_query": "get me pizza places", "target_site": "yelp.com" }

// Response
{
  "refined_query": "Extract pizza restaurant names, addresses, phone numbers, ratings, and price ranges",
  "suggested_fields": ["name", "address", "phone", "rating", "price_range"],
  "suggested_scrape_type": "maps",
  "source": "openai",
  "confidence": 0.92
}
```

### GET /api/v1/scraping-types (no auth)

Response: `{ "types": ["structured","maps","search","listings","news","social","custom"], "descriptions": {...} }`

## Usage Patterns

### Refine User Query Before Scraping

```
User says: "Find pizza places in Chicago"

1. If query is vague: call POST /api/v1/assistant/request-refinement
   with raw_query = user's exact words, target_site = "google.com"

2. Use refined_query as the query field in /scrape, suggested_fields as fields,
   suggested_scrape_type as scrape_type

3. Tell user: "I've refined your query to: [refined_query] (source: [source])"
   Then proceed with /scrape via hscraper-client skill
```

### Detect Scrape Types

```
1. Call GET /api/v1/scraping-types (no auth)
2. Present types to user
3. If unsure, call /assistant/request-refinement for auto-suggestion
```

### Skip When Query is Good

If user says "Extract product names, prices, and SKUs from example.com/products" —
skip refinement, go straight to /scrape. Only use assistant for vague inputs.

## Pitfalls

- **Don't refine already-good queries.** Only call for vague inputs.
- **source field tells you which engine ran.** "heuristic" still produces usable results.
- **Confidence below 0.5 → warn user.** Results may be approximate.
- **Don't check OpenAI availability first.** Just call — it always returns something.
