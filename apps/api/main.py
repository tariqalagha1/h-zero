"""H-Zero — FastAPI Application.

Lightweight API server for the agent layer.
Routes: agent runs, webhooks, health, security scans.
Depends on H-Scraper for scraping/jobs via the hscraper-* skills.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routes import agents, webhooks

app = FastAPI(
    title="H-Zero",
    description="Autonomous agent layer — ReAct loop, browser fleet, security testing",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(webhooks.router)


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/health/ready")
async def ready():
    return {"status": "ready"}
