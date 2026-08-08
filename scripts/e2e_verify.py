"""H-Zero E2E Verification Script."""
import asyncio, json, sys
sys.path.insert(0, "/root/synthera-genesis")

from services.agent.security.security_loop import AdaptiveSecurityLoop, SecurityAssessmentConfig
from services.agent.security.probe_library import ProbeCategory
from services.agent.state import AgentRunConfig
from services.agent.loop import ReActLoop
from services.embedding.pipeline import EmbeddingPipeline, EmbeddingSource
import httpx

results = {}

async def test_api():
    endpoints = {"/health": 200, "/health/ready": 200, "/docs": 200, "/agents/": 401}
    r = {}
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10) as c:
        for path, exp in endpoints.items():
            resp = await c.get(path)
            r[path] = {"status": resp.status_code, "expected": exp, "match": resp.status_code == exp}
    ok = all(v["match"] for v in r.values())
    print(f"[1/4] {'PASS' if ok else 'FAIL'} API endpoints: {json.dumps(r)}")
    return ok, r

async def test_embedding():
    p = EmbeddingPipeline()
    r = await p.embed_texts(["aspirin reduces cancer risk", "metformin extends lifespan"], source_type=EmbeddingSource.CLAIM_TEXT, source_id="e2e-001")
    ok = len(r.records) == 2 and not r.errors
    print(f"[2/4] {'PASS' if ok else 'FAIL'} Embeddings: {len(r.records)} records, {r.tokens_used} tokens, {r.latency_ms:.0f}ms")
    return ok, {"records": len(r.records), "tokens": r.tokens_used, "ms": r.latency_ms}

async def test_react():
    loop = ReActLoop()
    config = AgentRunConfig(run_id="e2e-react-001", goal="Find research papers about aspirin", start_url="http://localhost:8001/index.html", max_cycles=3, max_duration_seconds=30)
    run = await loop.run(config)
    ok = run.state.value in ("COMPLETED",) and not run.errors
    print(f"[3/4] {'PASS' if ok else 'FAIL'} ReAct: state={run.state.value}, verdict={run.verdict.value if run.verdict else 'N/A'}, cycles={run.current_cycle}, steps={len(run.steps)}")
    return ok, {"state": run.state.value, "verdict": run.verdict.value if run.verdict else None, "cycles": run.current_cycle, "steps": len(run.steps), "errors": run.errors}

async def test_security():
    loop = AdaptiveSecurityLoop()
    config = SecurityAssessmentConfig(run_id="e2e-sec-001", target_urls=["http://localhost:8000"], categories=[ProbeCategory.INFORMATION_DISCLOSURE, ProbeCategory.AUTH_BYPASS, ProbeCategory.CORS_MISCONFIGURATION], max_iterations=6, max_per_target=3, non_destructive_only=True)
    report = await loop.assess(config)
    entries = report.get("entries", [])
    findings = report.get("findings", [])
    s = report.get("summary", {})
    ok = len(entries) > 0 and s.get("total_iterations", 0) > 0
    print(f"[4/4] {'PASS' if ok else 'FAIL'} Security: {s.get('total_iterations')} probes, {s.get('verified_vulnerabilities')} findings")
    return ok, {"iterations": s.get("total_iterations"), "findings": s.get("verified_vulnerabilities"), "summary": s}

async def main():
    print("=== H-Zero E2E Verification ===\n")
    a_ok, a_r = await test_api()
    e_ok, e_r = await test_embedding()
    r_ok, r_r = await test_react()
    s_ok, s_r = await test_security()
    all_ok = a_ok and e_ok and r_ok and s_ok
    print(f"\n{'='*50}\nOVERALL: {'ALL PASSED' if all_ok else 'SOME FAILED'}\n{'='*50}")
    return 0 if all_ok else 1

sys.exit(asyncio.run(main()))
