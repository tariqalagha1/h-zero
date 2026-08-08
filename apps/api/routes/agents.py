"""H-Zero — Agent Routes (standalone, no Synthera deps)."""

import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/agents", tags=["Agents"])
_runs: dict[str, dict] = {}


class AgentRunRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    start_url: str = Field(...)
    max_cycles: int = Field(default=20, ge=1, le=100)
    max_duration_seconds: int = Field(default=600, ge=10, le=3600)
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    llm_model: str = Field(default="gpt-4o")
    extract_schema: dict | None = None


class AgentRunResponse(BaseModel):
    run_id: str
    state: str
    goal: str
    start_url: str
    cycles_completed: int
    total_steps: int
    verdict: str | None = None
    errors: list[str] = []
    started_at: str | None = None
    completed_at: str | None = None


@router.post("/run", status_code=201)
async def start_agent_run(request: AgentRunRequest):
    run_id = str(uuid.uuid4())
    _runs[run_id] = {
        "run_id": run_id, "state": "PLANNING", "goal": request.goal,
        "start_url": request.start_url, "cycles_completed": 0,
        "total_steps": 0, "verdict": None, "errors": [],
    }
    return AgentRunResponse(run_id=run_id, state="PLANNING", goal=request.goal,
                            start_url=request.start_url, cycles_completed=0, total_steps=0)


@router.get("/{run_id}")
async def get_agent_run(run_id: str):
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, "Agent run not found")
    return AgentRunResponse(**run)


@router.post("/{run_id}/cancel")
async def cancel_agent_run(run_id: str):
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, "Agent run not found")
    if run["state"] in ("COMPLETED", "FAILED", "CANCELLED"):
        raise HTTPException(400, f"Already terminal: {run['state']}")
    run["state"] = "CANCELLED"
    run["verdict"] = "CANCELLED"
    return {"run_id": run_id, "status": "cancelled"}


@router.get("/", response_model=None)
async def list_agent_runs(
    state: str | None = Query(None),
    limit: int = Query(default=20, le=100),
):
    runs = list(_runs.values())
    if state:
        runs = [r for r in runs if r["state"] == state]
    runs = sorted(runs, key=lambda r: r.get("started_at") or "", reverse=True)
    return [AgentRunResponse(**r) for r in runs[:limit]]
