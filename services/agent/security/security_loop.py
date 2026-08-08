"""H-Zero — Adaptive Security Testing Loop.

Implements the Observe → Hypothesize → Synthesize → Evaluate cycle
for autonomous security assessment against authorized targets.

Guided by OWASP Top 10, access control models, and input validation boundaries.
Every response, header, error code, and anomaly drives the next probe.
"""

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import Optional

import structlog

from services.agent.security.audit_logger import (
    AuditEntry, AuditLogger, AuditOutcome, Severity, get_audit_logger,
)
from services.agent.security.probe_library import (
    ALL_PROBES, PROBES_BY_CATEGORY, ProbeCategory, SecurityProbe,
    get_non_destructive_probes, search_probes,
)
from services.agent.security.scope_enforcer import (
    ScopeEnforcer, ScopeDecision, create_local_scope,
)
from services.agent.security.http_prober import (
    HTTPProber, HTTPProbeRequest, HTTPProbeResponse, get_http_prober,
)

logger = structlog.get_logger("h_zero.security_loop")

# ── Security Testing System Prompt ──────────────────────────────────────────

SECURITY_SYSTEM_PROMPT = """You are an autonomous security assessment agent operating strictly within an authorized, sandboxed testing environment. Your task is to execute an adaptive, feedback-driven security evaluation against designated target endpoints.

Rather than following a static list of tests, you operate as a dynamic state machine — using every response, error code, and environmental detail to craft tailored, context-aware verification probes.

## Core Execution Loop

For each target endpoint, continuously execute this 4-step loop:

1. OBSERVE & INGEST
   - Parse target responses, HTTP headers, DOM trees, API payloads, and error stack traces.
   - Log all newly discovered parameters, unlisted endpoints, version strings, or routing anomalies.

2. HYPOTHESIZE & PLAN
   - Evaluate findings against OWASP Top 10 security design principles.
   - Formulate a specific hypothesis regarding potential weaknesses.
   - Example: "Verbose error on parameter id suggests unsanitized SQL handling"

3. SYNTHESIZE & PROBE
   - Generate a targeted, context-specific payload tailored to the exact syntax observed.
   - Execute the probe via HTTP requests, API fuzzers, or browser DOM actions.

4. EVALUATE & PIVOT
   - Analyze the server's response to your probe.
   - If vulnerability verified: Document finding, assess severity, evaluate for secondary testing paths.
   - If probe fails: Refine your model of the target and update testing strategy.

## Safety Guardrails

- STRICT SCOPE: Only target assigned IPs, URLs, or localhost. Never probe external domains.
- NON-DESTRUCTIVE: Avoid payloads that write garbage data, drop tables, or alter state.
- DEPTH CAP: Maximum 5 iterations per discovered target asset.
- RESOURCE BUDGET: Stop if token/time/quota limits are reached.

## Available Probe Categories

- sql_injection: SQLi payloads (error-based, boolean, union, time-based)
- xss: Cross-site scripting (reflected, DOM-based, stored, event handler)
- auth_bypass: Authentication bypass, IDOR, JWT attacks, admin exposure
- path_traversal: Directory traversal and file inclusion
- ssrf: Server-side request forgery
- information_disclosure: Error leakage, version disclosure, verbose headers
- cors_misconfiguration: CORS wildcard, origin reflection
- header_injection: CRLF injection
- rate_limiting: Missing rate limit detection

## Response Format

Respond with JSON:
{
  "observation": "What you observed from the last response",
  "hypothesis": "What potential weakness you suspect",
  "probe_category": "category from the list above",
  "probe_payload": "specific payload or empty for auto-selection",
  "target_parameter": "parameter name to target",
  "target_location": "query|body|header|path",
  "confidence": 0.0-1.0,
  "severity_if_verified": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
  "is_done": false,
  "next_target_url": "",
  "reasoning": "Why this probe is appropriate"
}"""


# ── Security Assessment Config ──────────────────────────────────────────────


class SecurityAssessmentConfig:
    """Configuration for a security assessment run."""

    def __init__(
        self,
        run_id: str = "",
        target_urls: list[str] = None,
        categories: list[ProbeCategory] = None,
        max_iterations: int = 20,
        max_per_target: int = 5,
        max_duration_seconds: int = 600,
        non_destructive_only: bool = True,
        allowed_domains: list[str] = None,
        allowed_subnets: list[str] = None,
    ):
        self.run_id = run_id or f"sec-{int(time.time())}"
        self.target_urls = target_urls or []
        self.categories = categories or list(ProbeCategory)
        self.max_iterations = max_iterations
        self.max_per_target = max_per_target
        self.max_duration_seconds = max_duration_seconds
        self.non_destructive_only = non_destructive_only
        self.allowed_domains = allowed_domains or []
        self.allowed_subnets = allowed_subnets or []


# ── Adaptive Security Loop ──────────────────────────────────────────────────


class AdaptiveSecurityLoop:
    """The core autonomous security testing loop.

    For each target:
    1. Baseline: send clean request, observe normal behavior
    2. Categorize: classify the target (API, web app, static)
    3. Probe cycle: observe → hypothesize → synthesize → evaluate
    4. Pivot: use findings to discover secondary attack paths
    """

    def __init__(
        self,
        prober: HTTPProber = None,
        scope: ScopeEnforcer = None,
        audit: AuditLogger = None,
        gateway=None,
    ):
        self._prober = prober or get_http_prober()
        self._scope = scope or create_local_scope()
        self._audit = audit or get_audit_logger()
        self._gateway = gateway

    async def assess(self, config: SecurityAssessmentConfig) -> dict:
        """Run a full adaptive security assessment."""
        trail = self._audit.start_trail(config.run_id, config.target_urls[0] if config.target_urls else "")

        iteration = 0
        per_target_count: dict[str, int] = {}
        findings: list[AuditEntry] = []
        start_time = time.time()

        logger.info(f"Security assessment {config.run_id} started: {len(config.target_urls)} targets")

        for target_url in config.target_urls:
            # Scope check
            scope_result = self._scope.check(target_url)
            if scope_result.decision != ScopeDecision.ALLOWED:
                logger.warning(f"Target {target_url} out of scope: {scope_result.reason}")
                self._audit.log(config.run_id, AuditEntry(
                    iteration_step=iteration,
                    target=target_url,
                    observation=f"OUT_OF_SCOPE: {scope_result.reason}",
                    hypothesis="",
                    probe_executed="",
                    outcome=AuditOutcome.REJECTED,
                    next_action="Skip target",
                ))
                continue

            # Initialize per-target counter
            per_target_count[target_url] = 0

            # ── Step 1: Baseline ──
            baseline = await self._prober.baseline(target_url)
            logger.info(f"Baseline for {target_url}: {baseline.status_code} ({baseline.elapsed_ms:.0f}ms)")

            # ── Step 2: Auto-categorize target ──
            target_profile = self._categorize_target(baseline)
            logger.info(f"Target profile: {target_profile}")

            # ── Step 3: Adaptive probe cycle ──
            last_observation = self._format_baseline_observation(baseline, target_profile)

            while iteration < config.max_iterations and per_target_count[target_url] < config.max_per_target:
                # Time budget check
                if time.time() - start_time > config.max_duration_seconds:
                    logger.info(f"Time budget exhausted at iteration {iteration}")
                    break

                iteration += 1
                per_target_count[target_url] += 1

                # ── HYPOTHESIZE ──
                hypothesis = await self._hypothesize(
                    target_url, baseline, last_observation, iteration,
                    per_target_count[target_url], config,
                )

                if hypothesis.get("is_done"):
                    logger.info(f"Assessment complete for {target_url} at iteration {iteration}")
                    break

                # ── SYNTHESIZE & PROBE ──
                probe_result = await self._synthesize_and_probe(
                    target_url, hypothesis, config,
                )

                # ── EVALUATE ──
                evaluation = await self._evaluate(
                    target_url, hypothesis, probe_result, baseline,
                )

                # ── Log audit entry ──
                entry = AuditEntry(
                    iteration_step=iteration,
                    target=target_url,
                    observation=last_observation[:500],
                    hypothesis=hypothesis.get("hypothesis", "")[:300],
                    probe_executed=f"{hypothesis.get('probe_category','')}: {hypothesis.get('probe_payload','baseline')[:200]}",
                    outcome=evaluation.get("outcome", AuditOutcome.REQUIRES_FURTHER_PROBING),
                    severity=evaluation.get("severity"),
                    next_action=evaluation.get("next_action", "Continue probing"),
                    evidence={
                        "status_code": probe_result.status_code,
                        "response_time_ms": probe_result.elapsed_ms,
                        "response_preview": probe_result.body[:500],
                        "headers_of_interest": self._extract_security_headers(probe_result),
                    },
                )
                self._audit.log(config.run_id, entry)

                if evaluation.get("outcome") == AuditOutcome.VERIFIED_VULNERABILITY:
                    findings.append(entry)

                # Update observation for next iteration
                last_observation = self._format_probe_observation(probe_result, evaluation)

                # Pivot: if vulnerability found, explore secondary paths
                if evaluation.get("pivot_target"):
                    pivot_url = evaluation["pivot_target"]
                    if self._scope.is_allowed(pivot_url):
                        if pivot_url not in per_target_count:
                            per_target_count[pivot_url] = 0
                            config.target_urls.append(pivot_url)
                            logger.info(f"Pivoting to secondary target: {pivot_url}")

        # Finalize audit trail
        report = self._audit.finalize(config.run_id)
        logger.info(f"Assessment {config.run_id} complete: {len(findings)} findings in {iteration} iterations")

        return report or {"run_id": config.run_id, "findings": [], "summary": {}}

    # ── Target Categorization ────────────────────────────────────────────

    def _categorize_target(self, baseline: HTTPProbeResponse) -> dict:
        """Auto-categorize the target based on baseline response."""
        content_type = baseline.header("Content-Type") or ""
        server = baseline.header("Server") or ""
        body = baseline.body[:2000]

        is_api = any(t in content_type for t in ("application/json", "application/xml", "text/xml"))
        is_html = "text/html" in content_type
        has_auth = baseline.status_code in (401, 403)
        has_error_page = baseline.status_code >= 400

        return {
            "type": "api" if is_api else "web_app" if is_html else "unknown",
            "content_type": content_type,
            "server": server,
            "is_protected": has_auth,
            "has_error_page": has_error_page,
            "technologies": self._detect_technologies(server, body),
        }

    def _detect_technologies(self, server_header: str, body: str) -> list[str]:
        """Detect likely technologies from headers and body."""
        tech = []
        if "nginx" in server_header.lower():
            tech.append("nginx")
        if "apache" in server_header.lower():
            tech.append("apache")
        if "express" in server_header.lower():
            tech.append("express")
        if "django" in body.lower() or "csrftoken" in body.lower():
            tech.append("django")
        if "rails" in body.lower():
            tech.append("rails")
        if "react" in body.lower():
            tech.append("react")
        if "fastapi" in server_header.lower() or "uvicorn" in server_header.lower():
            tech.append("fastapi")
        return tech

    # ── Hypothesis Generation ────────────────────────────────────────────

    async def _hypothesize(
        self, target_url: str, baseline: HTTPProbeResponse,
        last_observation: str, iteration: int, per_target: int,
        config: SecurityAssessmentConfig,
    ) -> dict:
        """Generate a security hypothesis based on observations."""

        # For iteration 1: auto-select probes based on target categorization
        if iteration == 1:
            return self._auto_select_initial_probes(target_url, baseline, config)

        # Use LLM for adaptive hypothesis if available
        if self._gateway and iteration > 1:
            try:
                return await self._llm_hypothesize(target_url, baseline, last_observation, config)
            except Exception as e:
                logger.error(f"LLM hypothesis failed: {e}")

        # Fallback: rotate through remaining probe categories
        return self._fallback_hypothesis(target_url, iteration, per_target, config)

    def _auto_select_initial_probes(self, target_url: str, baseline: HTTPProbeResponse,
                                    config: SecurityAssessmentConfig) -> dict:
        """Auto-select the most appropriate initial probes based on target profile."""
        probes = get_non_destructive_probes() if config.non_destructive_only else ALL_PROBES

        # Start with information disclosure — lowest risk, highest value
        info_probes = [p for p in probes if p.category == ProbeCategory.INFORMATION_DISCLOSURE]
        if info_probes:
            probe = info_probes[0]
            return {
                "observation": f"Baseline: {baseline.status_code}, Content-Type: {baseline.header('Content-Type')}",
                "hypothesis": "Server may leak version or error information",
                "probe_category": ProbeCategory.INFORMATION_DISCLOSURE.value,
                "probe_payload": probe.payload,
                "target_parameter": probe.target_parameter,
                "target_location": probe.target_location,
                "confidence": 0.7,
                "severity_if_verified": Severity.LOW.value,
                "is_done": False,
                "next_target_url": "",
                "reasoning": "Information disclosure is low-risk and provides valuable reconnaissance",
                "probe_id": probe.id,
            }

        # Fallback: first available probe
        if probes:
            probe = probes[0]
            return {
                "observation": f"Baseline status: {baseline.status_code}",
                "hypothesis": f"Target may be vulnerable to {probe.category.value}",
                "probe_category": probe.category.value,
                "probe_payload": probe.payload,
                "target_parameter": probe.target_parameter,
                "target_location": probe.target_location,
                "confidence": 0.3,
                "severity_if_verified": probe.severity.value,
                "is_done": False,
                "next_target_url": "",
                "reasoning": f"Testing {probe.category.value} as initial probe",
                "probe_id": probe.id,
            }

        return {"is_done": True, "reasoning": "No probes available"}

    async def _llm_hypothesize(self, target_url: str, baseline: HTTPProbeResponse,
                               last_observation: str, config) -> dict:
        """Use LLM to generate adaptive security hypothesis."""
        from services.gateway.llm_gateway import LLMRequest, TaskType

        request = LLMRequest(
            messages=[
                {"role": "system", "content": SECURITY_SYSTEM_PROMPT},
                {"role": "user", "content": f"""Target: {target_url}
Baseline: {baseline.status_code} ({baseline.elapsed_ms:.0f}ms)
Content-Type: {baseline.header('Content-Type')}
Server: {baseline.header('Server')}

Last observation: {last_observation[:2000]}

Available probe categories: {[c.value for c in config.categories]}

What is your hypothesis and next probe? Respond with JSON only."""},
            ],
            task_type=TaskType.GENERAL,
            response_format={"type": "json_object"},
        )
        response = await self._gateway.generate(request)

        if response.content and not response.error:
            hypothesis = json.loads(response.content)
            hypothesis.setdefault("is_done", False)
            hypothesis.setdefault("probe_category", "information_disclosure")
            hypothesis.setdefault("confidence", 0.5)
            return hypothesis

        return {"is_done": True, "reasoning": "LLM unavailable"}

    def _fallback_hypothesis(self, target_url: str, iteration: int,
                             per_target: int, config) -> dict:
        """Fallback: cycle through probe categories."""
        categories = [c for c in config.categories if c in PROBES_BY_CATEGORY]
        if not categories:
            return {"is_done": True}

        cat_idx = (iteration - 1) % len(categories)
        category = categories[cat_idx]
        probes = PROBES_BY_CATEGORY.get(category, [])

        if config.non_destructive_only:
            probes = [p for p in probes if not p.is_destructive]

        if not probes:
            return {"is_done": True}

        probe = probes[(iteration - 1) % len(probes)]
        return {
            "observation": f"Iteration {iteration}/{config.max_per_target} per target",
            "hypothesis": f"Testing {category.value} vulnerabilities",
            "probe_category": category.value,
            "probe_payload": probe.payload,
            "target_parameter": probe.target_parameter,
            "target_location": probe.target_location,
            "confidence": 0.3,
            "severity_if_verified": probe.severity.value,
            "is_done": per_target >= config.max_per_target,
            "next_target_url": "",
            "reasoning": f"Systematic {category.value} testing",
            "probe_id": probe.id,
        }

    # ── Probe Synthesis & Execution ─────────────────────────────────────

    async def _synthesize_and_probe(
        self, target_url: str, hypothesis: dict, config,
    ) -> HTTPProbeResponse:
        """Execute a security probe based on the hypothesis."""
        probe_category = hypothesis.get("probe_category", "")
        payload = hypothesis.get("probe_payload", "")
        parameter = hypothesis.get("target_parameter", "id")
        location = hypothesis.get("target_location", "query")

        # Look up the probe from the library for metadata
        probe_id = hypothesis.get("probe_id")
        if probe_id:
            for p in ALL_PROBES:
                if p.id == probe_id:
                    payload = p.payload
                    parameter = p.target_parameter or parameter
                    location = p.target_location or location
                    break

        try:
            result = await self._prober.probe_with_payload(
                url=target_url,
                parameter=parameter,
                payload=payload,
                target_location=location,
            )
            logger.info(
                f"Probe {hypothesis.get('probe_category','?')} → "
                f"{result.status_code} ({result.elapsed_ms:.0f}ms)"
            )
            return result
        except Exception as e:
            logger.error(f"Probe failed: {e}")
            return HTTPProbeResponse(
                request=HTTPProbeRequest(url=target_url),
                error=str(e)[:500],
            )

    # ── Evaluation ───────────────────────────────────────────────────────

    async def _evaluate(
        self, target_url: str, hypothesis: dict,
        probe_result: HTTPProbeResponse, baseline: HTTPProbeResponse,
    ) -> dict:
        """Evaluate probe result against hypothesis."""
        probe_category = hypothesis.get("probe_category", "")
        payload = hypothesis.get("probe_payload", "")

        # Find the probe definition for expected behavior
        probe_def = None
        probe_id = hypothesis.get("probe_id")
        if probe_id:
            for p in ALL_PROBES:
                if p.id == probe_id:
                    probe_def = p
                    break

        # Check for vulnerability indicators
        is_vulnerable = False
        evidence = ""

        if probe_def and probe_def.expected_vulnerable_response:
            if probe_result.body_matches_regex(probe_def.expected_vulnerable_response):
                is_vulnerable = True
                evidence = f"Response matched vulnerability pattern: {probe_def.expected_vulnerable_response[:100]}"

        # Timing-based detection (for blind/time-based injections)
        if probe_category == "sql_injection" and "SLEEP" in payload.upper():
            if probe_result.elapsed_ms > baseline.elapsed_ms * 3:
                is_vulnerable = True
                evidence = f"Time-based detection: {probe_result.elapsed_ms:.0f}ms vs baseline {baseline.elapsed_ms:.0f}ms"

        # Error-based detection
        error_patterns = [
            r"SQL syntax.*MySQL", r"PostgreSQL.*ERROR", r"ORA-\d{5}",
            r"Microsoft OLE DB", r"ODBC Driver", r"sqlite3\.Error",
            r"Traceback \(most recent call last\)", r"stack trace",
            r"at line \d+", r"Exception in", r"File \".*\", line \d+",
        ]
        for pattern in error_patterns:
            if probe_result.body_matches_regex(pattern):
                is_vulnerable = True
                evidence = f"Error disclosure: matched pattern '{pattern}'"
                break

        # 401/403 on auth bypass = properly protected
        if probe_category == "auth_bypass" and probe_result.status_code in (401, 403):
            is_vulnerable = False
            evidence = "Properly rejected unauthorized access"

        outcome = AuditOutcome.VERIFIED_VULNERABILITY if is_vulnerable else AuditOutcome.REJECTED
        severity = Severity(hypothesis.get("severity_if_verified", "LOW")) if is_vulnerable else None

        return {
            "outcome": outcome,
            "severity": severity,
            "is_vulnerable": is_vulnerable,
            "evidence": evidence or "No vulnerability indicators detected",
            "next_action": "Document finding and explore secondary paths" if is_vulnerable else "Continue probing other categories",
            "pivot_target": self._suggest_pivot(target_url, probe_category, is_vulnerable),
        }

    def _suggest_pivot(self, target_url: str, category: str, is_vulnerable: bool) -> Optional[str]:
        """Suggest a secondary testing path if vulnerability was found."""
        if not is_vulnerable:
            return None
        # If SQLi found, try API endpoints
        if category == "sql_injection":
            return target_url.rstrip("/") + "/api"
        # If auth bypass found, try admin
        if category == "auth_bypass":
            return target_url.rstrip("/") + "/admin"
        return None

    # ── Observation Formatting ───────────────────────────────────────────

    def _format_baseline_observation(self, baseline: HTTPProbeResponse, profile: dict) -> str:
        """Format baseline response for observation logging."""
        parts = [
            f"Status: {baseline.status_code}",
            f"Content-Type: {baseline.header('Content-Type') or 'unknown'}",
            f"Server: {baseline.header('Server') or 'not disclosed'}",
            f"Response time: {baseline.elapsed_ms:.0f}ms",
            f"Body length: {baseline.body_length} bytes",
            f"Target type: {profile['type']}",
        ]
        if profile["technologies"]:
            parts.append(f"Technologies: {', '.join(profile['technologies'])}")
        if profile["is_protected"]:
            parts.append("Target requires authentication")
        return " | ".join(parts)

    def _format_probe_observation(self, response: HTTPProbeResponse, evaluation: dict) -> str:
        """Format probe response for the next observation."""
        parts = [
            f"Status: {response.status_code}",
            f"Time: {response.elapsed_ms:.0f}ms",
            f"Verdict: {evaluation.get('outcome','?')}",
        ]
        if response.error:
            parts.append(f"Error: {response.error[:100]}")
        if evaluation.get("evidence"):
            parts.append(f"Evidence: {evaluation['evidence'][:200]}")
        return " | ".join(parts)

    def _extract_security_headers(self, response: HTTPProbeResponse) -> dict:
        """Extract security-relevant headers from a response."""
        security_headers = [
            "Content-Security-Policy", "X-Content-Type-Options",
            "X-Frame-Options", "X-XSS-Protection",
            "Strict-Transport-Security", "Access-Control-Allow-Origin",
            "Access-Control-Allow-Credentials", "Server",
            "X-Powered-By", "X-AspNet-Version", "X-AspNetMvc-Version",
        ]
        return {h: response.header(h) for h in security_headers if response.header(h)}


# Singleton
_loop: Optional[AdaptiveSecurityLoop] = None


def get_security_loop() -> AdaptiveSecurityLoop:
    global _loop
    if _loop is None:
        _loop = AdaptiveSecurityLoop()
    return _loop
