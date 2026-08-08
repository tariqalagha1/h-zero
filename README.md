# H-Zero

Autonomous agent layer on H-Scraper — ReAct loop, browser fleet, security testing, embeddings.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-73%20passed-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)]()

---

## What It Does

H-Zero is an autonomous agent that can:

- **Browse the web** — ReAct loop (Plan → Act → Observe → Evaluate) with Playwright sandboxes
- **Security test** — Adaptive OWASP probe catalog: 24 probes across 10 categories
- **Generate embeddings** — Vector pipeline with Qdrant storage
- **Verify itself** — Transport-layer evidence, deterministic checks, sandbox isolation

It depends on [H-Scraper](https://github.com/tariqalagha1/H-scraper-) for scraping, job lifecycle, and AI prompt refinement.

## Architecture

```
h-zero/
├── services/
│   ├── agent/                 # ReAct loop + security testing
│   │   ├── loop.py            # Plan → Act → Observe → Evaluate engine
│   │   ├── state.py           # Agent state machine
│   │   ├── dom_actions.py     # DOM action parser
│   │   ├── browser_executor.py# Browser fleet interface
│   │   └── security/          # Adaptive security testing
│   │       ├── security_loop.py    # Observe→Hypothesize→Synthesize→Evaluate
│   │       ├── probe_library.py    # 24 probes, 10 OWASP categories
│   │       ├── http_prober.py      # Raw HTTP client with scope enforcement
│   │       ├── audit_logger.py     # Spec-compliant JSON audit trail
│   │       └── scope_enforcer.py   # IP/subnet/domain boundary enforcement
│   ├── browser/               # Playwright sandbox fleet
│   │   ├── sandbox.py         # Isolated browser instance with stealth
│   │   └── fleet.py           # Pool manager with health monitoring
│   ├── embedding/             # Vector generation pipeline
│   │   └── pipeline.py        # Embedding generation + Qdrant storage
│   └── gateway/               # LLM provider abstraction
│       └── llm_gateway.py     # OpenAI, Anthropic, Google (auto-detect)
├── apps/api/                  # FastAPI server
│   ├── main.py                # Application entry point
│   └── routes/
│       ├── agents.py          # /agents/run, /agents/{id}, /agents/
│       └── webhooks.py        # /webhooks/{source} with HMAC validation
├── packages/security/         # Vault integration
├── infrastructure/            # Docker, Terraform, seccomp
│   ├── containers/
│   │   ├── docker-compose.yml      # API + Qdrant + browser fleet
│   │   ├── Dockerfile.api          # Non-root API container
│   │   ├── Dockerfile.browser      # Playwright sandbox
│   │   ├── seccomp-browser.json    # Syscall whitelist
│   │   └── network-policy.yml      # Dual-network zones
│   └── terraform/                  # AWS VPC, subnets, Vault
├── tests/
│   ├── unit/test_security_module.py # 34 security tests
│   └── e2e/                         # Browser, DOM, sandbox tests
├── scripts/                   # Health probes, security checks, E2E scenarios
├── .github/workflows/         # CI/CD security pipeline
└── .hermes/skills/            # H-Scraper agent skills (4)
```

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run tests
pytest                          # 73 passed, 13 skipped

# Start with Docker
docker compose -f infrastructure/containers/docker-compose.yml up -d

# Run the real scenario (requires live infrastructure)
bash scripts/run_scenario.sh
```

## Environment

```bash
# Required — H-Scraper connection
HSCRAPER_BASE_URL=https://scraper.internal
HSCRAPER_API_KEY=your-api-key

# Optional — LLM provider (auto-detected from env)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...

# Optional — Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

## Test Results

```
73 passed, 13 skipped, 0 failed

Breakdown:
  34 security tests (probes, audit, scope, HTTP, evaluation)
  19 DOM parsing tests
  13 agent loop tests  
   6 browser rendering tests (skipped — requires Docker)
   7 sandbox isolation tests (skipped — requires Docker)
   1 HTTP prober test
```

## Security Agent

The adaptive security testing agent implements the full Observe → Hypothesize → Synthesize → Evaluate loop:

| Spec Requirement | Implementation |
|---|---|
| Parse HTTP headers, error traces, DOM | `security_loop.py:_format_baseline_observation()` |
| OWASP-aware hypothesis generation | `security_loop.py:_hypothesize()` with LLM prompt |
| Context-specific payload synthesis | `security_loop.py:_synthesize_and_probe()` + `probe_library.py` |
| Evaluate and pivot | `security_loop.py:_evaluate()` — pattern, timing, error detection |
| Structured audit log | `audit_logger.py:AuditEntry.to_dict()` |
| Scope enforcement | `scope_enforcer.py` — localhost/Docker auto-allow, metadata auto-block |
| Non-destructive | 24/24 probes non-destructive |
| Depth caps | 5 iterations per target, 20 total, 600s budget |

## H-Scraper Skills

Four Hermes Agent skills for interacting with H-Scraper:

| Skill | Purpose |
|---|---|
| `hscraper-client` | Authenticate, submit scrapes, poll status, retrieve results |
| `hscraper-jobs` | Job CRUD, start/cancel/retry runs |
| `hscraper-assistant` | Prompt refinement, scrape type auto-detection |
| `hscraper-health` | System health, diagnostics, capability discovery |

API contract at `.hermes/skills/hscraper-client/references/api-contract.md` — derived from actual Pydantic schemas.

## License

Proprietary. All rights reserved.
