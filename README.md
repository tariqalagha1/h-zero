# H-Zero

Autonomous agent layer on H-Scraper.

- **ReAct agent loop** — Plan → Act → Observe → Evaluate for autonomous web interaction
- **Browser fleet** — Headless Playwright sandboxes with anti-detection
- **Security testing** — OWASP probe catalog (26 probes), adaptive Observe→Hypothesize→Synthesize→Evaluate loop
- **Embedding pipeline** — Vector generation and Qdrant storage
- **Verifier** — Transport-layer evidence, deterministic checks
- **H-Scraper skills** — Scrape, jobs, assistant, health

## Architecture

```
h-zero/                    # This project — agent layer
├── services/
│   ├── agent/             # ReAct loop + security testing
│   ├── browser/           # Playwright sandbox fleet
│   └── embedding/         # Vector pipeline
├── packages/security/     # Vault integration
├── infrastructure/        # Docker, Terraform, seccomp
├── tests/                 # E2E + unit tests
└── scripts/               # Health probes, security checks
```

H-Zero depends on H-Scraper for:
- Web scraping (`/api/v1/scrape`)
- Job lifecycle (`/api/v1/jobs`, `/api/v1/runs`)
- AI prompt refinement (`/api/v1/assistant/request-refinement`)
- System health (`/api/v1/health`, `/api/v1/system/capabilities`)

## Quick Start

```bash
pip install -e ".[dev]"
pytest
```

## Environment

```bash
HSCRAPER_BASE_URL=https://scraper.internal  # H-Scraper API
HSCRAPER_API_KEY=...                        # API key for auth
```
