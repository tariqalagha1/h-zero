"""H-Zero — Security Module Tests.

Tests for: probe library, audit logger, scope enforcer, HTTP prober,
and adaptive security loop.
"""

import json
import pytest

from services.agent.security.probe_library import (
    ALL_PROBES, PROBES_BY_CATEGORY, ProbeCategory, ProbeSeverity,
    SecurityProbe, get_non_destructive_probes, search_probes,
)
from services.agent.security.audit_logger import (
    AuditEntry, AuditTrail, AuditLogger, AuditOutcome, Severity,
)
from services.agent.security.scope_enforcer import (
    ScopeEnforcer, ScopeDecision, create_local_scope,
)
from services.agent.security.http_prober import (
    HTTPProber, HTTPProbeRequest, HTTPProbeResponse,
)
from services.agent.security.security_loop import (
    AdaptiveSecurityLoop, SecurityAssessmentConfig,
)


# ═══════════════════════════════════════════════════════════════════════════
# Probe Library Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestProbeLibrary:
    """Verify probe catalog integrity and querying."""

    def test_all_probes_have_required_fields(self):
        """Every probe has id, category, severity, name, payload."""
        for probe in ALL_PROBES:
            assert probe.id, f"Probe missing id"
            assert probe.category, f"Probe {probe.id} missing category"
            assert probe.severity, f"Probe {probe.id} missing severity"
            assert probe.name, f"Probe {probe.id} missing name"
            assert probe.description, f"Probe {probe.id} missing description"

    def test_probes_organized_by_category(self):
        """PROBES_BY_CATEGORY contains all probes."""
        total = sum(len(v) for v in PROBES_BY_CATEGORY.values())
        assert total == len(ALL_PROBES)

    def test_sqli_probes_exist(self):
        probes = PROBES_BY_CATEGORY.get(ProbeCategory.SQL_INJECTION, [])
        assert len(probes) >= 3, "Expected at least 3 SQLi probes"

    def test_xss_probes_exist(self):
        probes = PROBES_BY_CATEGORY.get(ProbeCategory.XSS, [])
        assert len(probes) >= 2, "Expected at least 2 XSS probes"

    def test_auth_probes_exist(self):
        probes = PROBES_BY_CATEGORY.get(ProbeCategory.AUTH_BYPASS, [])
        assert len(probes) >= 3, "Expected at least 3 auth bypass probes"

    def test_non_destructive_filter(self):
        """get_non_destructive_probes excludes destructive probes."""
        safe = get_non_destructive_probes()
        for probe in safe:
            assert not probe.is_destructive, f"Probe {probe.id} should be non-destructive"
        assert len(safe) <= len(ALL_PROBES)

    def test_search_probes(self):
        """search_probes returns relevant results."""
        results = search_probes("SQL injection")
        assert len(results) > 0
        assert any("sqli" in r.id.lower() for r in results)

        results = search_probes("nonexistent_xyz_123")
        assert len(results) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Audit Logger Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditLogger:
    """Verify audit trail logging and spec-compliant JSON output."""

    def test_entry_to_dict(self):
        """AuditEntry.to_dict() matches required spec format."""
        entry = AuditEntry(
            iteration_step=1,
            target="http://localhost:8000",
            observation="200 OK, Content-Type: application/json",
            hypothesis="Verbose error messages may disclose internal state",
            probe_executed="GET /api/users?id='",
            outcome=AuditOutcome.REJECTED,
            next_action="Try UNION-based injection",
            severity=Severity.LOW,
        )
        d = entry.to_dict()

        # Spec requires these exact keys
        required_keys = {
            "iteration_step", "target", "observation", "hypothesis",
            "probe_executed", "outcome", "next_action",
        }
        assert required_keys.issubset(d.keys()), f"Missing keys: {required_keys - d.keys()}"
        assert d["iteration_step"] == 1
        assert d["outcome"] == "REJECTED"

    def test_finding_extraction(self):
        """AuditTrail extracts verified vulnerabilities as findings."""
        trail = AuditTrail(run_id="test-1", target_url="http://localhost")
        trail.start()

        trail.add_entry(AuditEntry(
            iteration_step=1, target="http://localhost",
            observation="test", hypothesis="h1", probe_executed="p1",
            outcome=AuditOutcome.REJECTED, next_action="continue",
        ))
        trail.add_entry(AuditEntry(
            iteration_step=2, target="http://localhost",
            observation="SQL error found", hypothesis="SQL injection",
            probe_executed="' OR 1=1", outcome=AuditOutcome.VERIFIED_VULNERABILITY,
            next_action="document", severity=Severity.CRITICAL,
        ))
        trail.add_entry(AuditEntry(
            iteration_step=3, target="http://localhost",
            observation="XSS reflected", hypothesis="XSS",
            probe_executed="<script>alert(1)</script>",
            outcome=AuditOutcome.VERIFIED_VULNERABILITY,
            next_action="document", severity=Severity.HIGH,
        ))

        assert len(trail.entries) == 3
        assert len(trail.findings) == 2

    def test_trail_finalize(self):
        """finalize() produces complete report."""
        trail = AuditTrail(run_id="test-2", target_url="http://localhost:8000")
        trail.start()
        trail.add_entry(AuditEntry(
            iteration_step=1, target="http://localhost:8000",
            observation="obs", hypothesis="hyp", probe_executed="probe",
            outcome=AuditOutcome.VERIFIED_VULNERABILITY,
            next_action="done", severity=Severity.HIGH,
        ))

        report = trail.finalize()
        assert report["run_id"] == "test-2"
        assert "entries" in report
        assert "findings" in report
        assert "summary" in report
        assert report["summary"]["verified_vulnerabilities"] == 1

    def test_audit_logger_singleton(self):
        """AuditLogger tracks multiple trails independently."""
        logger = AuditLogger()
        logger.start_trail("run-a", "http://a.com")
        logger.start_trail("run-b", "http://b.com")

        logger.log("run-a", AuditEntry(
            iteration_step=1, target="http://a.com",
            observation="o", hypothesis="h", probe_executed="p",
            outcome=AuditOutcome.VERIFIED_VULNERABILITY, next_action="n",
        ))

        findings_a = logger.get_findings("run-a")
        findings_b = logger.get_findings("run-b")
        assert len(findings_a) == 1
        assert len(findings_b) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Scope Enforcer Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestScopeEnforcer:
    """Verify scope boundary enforcement."""

    def test_localhost_allowed(self):
        enforcer = create_local_scope()
        assert enforcer.is_allowed("http://localhost:8000")
        assert enforcer.is_allowed("https://localhost/api")
        assert enforcer.is_allowed("http://127.0.0.1:3000")

    def test_docker_network_allowed(self):
        enforcer = create_local_scope()
        assert enforcer.is_allowed("http://172.16.0.5:8080")
        assert enforcer.is_allowed("http://10.0.1.100:5000")

    def test_external_blocked(self):
        enforcer = create_local_scope()
        assert not enforcer.is_allowed("http://google.com")
        assert not enforcer.is_allowed("https://evil.com")
        assert not enforcer.is_allowed("http://1.2.3.4")

    def test_cloud_metadata_blocked(self):
        enforcer = create_local_scope()
        result = enforcer.check("http://169.254.169.254/latest/meta-data/")
        assert result.decision == ScopeDecision.BLOCKED
        assert "metadata" in result.reason.lower()

    def test_custom_domain_allowlist(self):
        enforcer = ScopeEnforcer()
        enforcer.add_allowed_domain("example.com")
        # Also add docker/compose ranges for local IP resolution
        enforcer.add_allowed_subnet("10.0.0.0/8")
        enforcer.add_allowed_subnet("172.16.0.0/12")
        assert enforcer.is_allowed("http://example.com")
        assert enforcer.is_allowed("http://api.example.com")
        assert not enforcer.is_allowed("http://other.com")

    def test_empty_target(self):
        enforcer = create_local_scope()
        result = enforcer.check("")
        assert result.decision == ScopeDecision.INVALID_TARGET

    def test_scope_summary(self):
        enforcer = create_local_scope()
        summary = enforcer.get_scope_summary()
        assert "allowed_domains" in summary
        assert "allowed_subnets" in summary
        assert "always_allowed" in summary
        assert "always_blocked" in summary


# ═══════════════════════════════════════════════════════════════════════════
# HTTP Prober Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestHTTPProber:
    """Verify HTTP prober request/response handling."""

    def test_probe_request_defaults(self):
        req = HTTPProbeRequest(url="http://localhost/test")
        assert req.method == "GET"
        assert req.timeout == 30
        assert not req.follow_redirects

    def test_probe_response_properties(self):
        resp = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"),
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"ok": true}',
            elapsed_ms=45.2,
        )
        assert resp.is_success
        assert not resp.is_error
        assert resp.header("content-type") == "application/json"
        assert resp.timing_category() == "fast"

    def test_probe_response_error_detection(self):
        resp = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"),
            status_code=500,
            body="Internal Server Error",
            elapsed_ms=50,
        )
        assert resp.is_error
        assert resp.is_server_error

    def test_probe_response_body_match(self):
        resp = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"),
            status_code=200,
            body="SQL syntax error near SELECT",
        )
        assert resp.body_contains("SQL syntax")
        assert resp.body_matches_regex(r"SQL.*error")

    def test_probe_response_timing(self):
        assert HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://x"), status_code=200,
            elapsed_ms=50,
        ).timing_category() == "fast"

        assert HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://x"), status_code=200,
            elapsed_ms=500,
        ).timing_category() == "normal"

        assert HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://x"), status_code=200,
            elapsed_ms=3000,
        ).timing_category() == "slow"


# ═══════════════════════════════════════════════════════════════════════════
# Security Loop Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurityAssessmentConfig:
    """Verify config validation."""

    def test_defaults(self):
        config = SecurityAssessmentConfig()
        assert config.max_iterations == 20
        assert config.max_per_target == 5
        assert config.max_duration_seconds == 600
        assert config.non_destructive_only is True

    def test_custom_limits(self):
        config = SecurityAssessmentConfig(
            run_id="test",
            target_urls=["http://localhost"],
            max_iterations=10,
            max_per_target=3,
            non_destructive_only=False,
        )
        assert config.max_iterations == 10
        assert config.max_per_target == 3
        assert not config.non_destructive_only


class TestTargetCategorization:
    """Verify target profiling from baseline responses."""

    def setup_method(self):
        self.loop = AdaptiveSecurityLoop()

    def test_api_detection(self):
        baseline = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost/api"),
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"users": []}',
        )
        profile = self.loop._categorize_target(baseline)
        assert profile["type"] == "api"

    def test_web_app_detection(self):
        baseline = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"),
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            body="<html><body>Test</body></html>",
        )
        profile = self.loop._categorize_target(baseline)
        assert profile["type"] == "web_app"

    def test_protected_detection(self):
        baseline = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost/admin"),
            status_code=401,
            headers={"Content-Type": "text/html"},
            body="Unauthorized",
        )
        profile = self.loop._categorize_target(baseline)
        assert profile["is_protected"] is True

    def test_technology_detection(self):
        baseline = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"),
            status_code=200,
            headers={"Content-Type": "text/html", "Server": "nginx/1.24"},
            body="<html>...django...csrftoken...</html>",
        )
        profile = self.loop._categorize_target(baseline)
        assert "nginx" in profile["technologies"]
        assert "django" in profile["technologies"]


class TestObservationFormatting:
    """Verify observation formatting for audit trail."""

    def setup_method(self):
        self.loop = AdaptiveSecurityLoop()

    def test_baseline_format(self):
        baseline = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"),
            status_code=200,
            headers={"Content-Type": "application/json", "Server": "uvicorn"},
            body='{"status": "ok"}',
            body_length=16,
            elapsed_ms=12.5,
        )
        profile = {"type": "api", "technologies": ["fastapi"], "is_protected": False}
        obs = self.loop._format_baseline_observation(baseline, profile)
        assert "200" in obs
        assert "uvicorn" in obs
        assert "api" in obs

    def test_security_header_extraction(self):
        response = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"),
            status_code=200,
            headers={
                "Content-Security-Policy": "default-src 'self'",
                "X-Content-Type-Options": "nosniff",
                "Server": "nginx",
            },
        )
        headers = self.loop._extract_security_headers(response)
        assert "Content-Security-Policy" in headers
        assert headers["X-Content-Type-Options"] == "nosniff"


class TestProbeEvaluation:
    """Verify vulnerability evaluation logic."""

    def setup_method(self):
        self.loop = AdaptiveSecurityLoop()

    async def test_sqli_error_detection(self):
        baseline = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"), status_code=200,
        )
        probe_result = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost?id='"), status_code=500,
            body="PostgreSQL ERROR: syntax error at or near",
        )
        hypothesis = {
            "probe_category": "sql_injection",
            "probe_payload": "'",
            "probe_id": "sqli-001",
            "severity_if_verified": "CRITICAL",
        }
        eval_result = await self.loop._evaluate(
            "http://localhost", hypothesis, probe_result, baseline,
        )
        assert eval_result["outcome"] == AuditOutcome.VERIFIED_VULNERABILITY

    async def test_safe_response_not_vulnerable(self):
        baseline = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost"), status_code=200,
        )
        probe_result = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost?id='"), status_code=200,
            body="No results found for your query",
        )
        hypothesis = {
            "probe_category": "sql_injection",
            "probe_payload": "'",
            "severity_if_verified": "CRITICAL",
        }
        eval_result = await self.loop._evaluate(
            "http://localhost", hypothesis, probe_result, baseline,
        )
        assert eval_result["outcome"] == AuditOutcome.REJECTED

    async def test_auth_bypass_blocked(self):
        baseline = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost/admin"), status_code=401,
        )
        probe_result = HTTPProbeResponse(
            request=HTTPProbeRequest(url="http://localhost/admin"), status_code=403,
        )
        hypothesis = {
            "probe_category": "auth_bypass",
            "probe_payload": "",
            "severity_if_verified": "HIGH",
        }
        eval_result = await self.loop._evaluate(
            "http://localhost/admin", hypothesis, probe_result, baseline,
        )
        # 403 = properly blocked, not vulnerable
        assert eval_result["outcome"] == AuditOutcome.REJECTED
