# H-Zero — Codebase Security Inspection Certificate

**Generated:** 2026-08-06
**Project:** H-Zero v0.1.0
**Inspector:** Adaptive Security Assessor
**Method:** Non-destructive codebase audit against four structural security pillars + adaptive feedback testing

---

## Inspection Certificate

```json
{
  "inspection_certificate": {
    "project_identifier": "h-zero",
    "overall_compliance": "PARTIALLY_COMPLIANT",
    "built_in_checks": {
      "self_reflection_hooks": "PARTIALLY_COMPLIANT",
      "event_driven_listeners": "NON_COMPLIANT",
      "subgoal_discovery_bounds": "PARTIALLY_COMPLIANT",
      "sandbox_isolation_controls": "PARTIALLY_COMPLIANT"
    }
  },
  "execution_trace": [
    {
      "step": 1,
      "target_component": "pyproject.toml — static analysis tooling",
      "observation": "ruff>=0.6.0 and mypy>=1.11.0 in dev dependencies. Ruff configured with rules E,F,I,N,W,UP,B,C4,SIM. No bandit, safety, or dedicated SAST tool in dependencies. No pre-commit hook configuration.",
      "hypothesis": "Static analysis exists at lint/type-check level but lacks security-specific SAST (bandit for Python security patterns, safety for known vulnerabilities in dependencies).",
      "probe_executed": "Read pyproject.toml, searched for 'bandit|safety|sast|pre-commit' across entire codebase. Zero matches for bandit/safety/sast. grep for '.pre-commit-config.yaml' — not found.",
      "outcome": "PARTIALLY_COMPLIANT",
      "remediation_recommended": "Add bandit>=1.7 to dev deps, safety>=3.0 for dependency vulnerability scanning, create .pre-commit-config.yaml with ruff + bandit + safety hooks."
    },
    {
      "step": 2,
      "target_component": "Hermes patch/write_file tool — auto-syntax-check",
      "observation": "Hermes Agent patch() and write_file() tools auto-run syntax checks on .py/.json/.yaml/.toml files. Only NEW errors introduced by the write are surfaced. Verified: all file writes in this session produced 'lint: ok' or specific linter output in their result metadata.",
      "hypothesis": "Pre-execution syntax validation exists for file writes but is limited to syntax only — no semantic security analysis (taint tracking, injection detection) is performed before code enters the repository.",
      "probe_executed": "Reviewed result metadata from all write_file operations in session — consistently shows lint:ok or specific diagnostics. grep for 'sanitiz|validate_input|validate_output|escape' across codebase — only found one escape in dom_actions.py (CSS selector escaping), no systemic input sanitization layer.",
      "outcome": "PARTIALLY_COMPLIANT",
      "remediation_recommended": "Syntax checking is good but insufficient. Add automated security scanning as a post-write hook via Hermes plugin system (post_tool_call hook). Create input sanitization utility in packages/security/ for XSS/SQLi prevention in all route handlers."
    },
    {
      "step": 3,
      "target_component": "CI/CD pipelines — .github/workflows/",
      "observation": "Directory /root/synthera-genesis/.github/ does not exist. No GitHub Actions workflows, no GitLab CI (.gitlab-ci.yml), no Jenkinsfile, no CircleCI config. Zero CI/CD configuration files found in repository.",
      "hypothesis": "No automated pipeline exists to trigger security scans on push, PR, or deploy events. All security verification is manual (developer runs pytest locally).",
      "probe_executed": "search_files for *.yml in .github/ — path not found. search_files for *.yml in repo root excluding .git — only docker-compose.yml, network-policy.yml. grep for 'workflow|action|pipeline|CI|CD' in non-git files — no CI pipeline references found.",
      "outcome": "NON_COMPLIANT",
      "remediation_recommended": "Create .github/workflows/security-scan.yml with: (1) ruff + mypy on push, (2) bandit SAST scan, (3) safety dependency audit, (4) pytest with coverage gate. Add .github/workflows/container-scan.yml with Trivy/Docker Scout for image scanning."
    },
    {
      "step": 4,
      "target_component": "Webhook handler — apps/api/routes/webhooks.py",
      "observation": "Webhook handler exists at /webhooks/{source} supporting pubmed, github, ci_cd sources. Accepts POST with HMAC-SHA256 signature verification. Dispatches events for async processing. Does NOT trigger any security scan on receiving a webhook event.",
      "hypothesis": "Webhook infrastructure exists but is a passive receiver — no reactive security scanning is wired to webhook events (e.g., github push → security scan trigger).",
      "probe_executed": "Read apps/api/routes/webhooks.py — confirms signature verification + event dispatch. grep for 'scan|bandit|safety|lint|audit' in webhooks.py — zero matches. grep for 'trigger|on_push|on_deploy' across services/ — only Temporal workflow triggers found, no security scan triggers.",
      "outcome": "NON_COMPLIANT",
      "remediation_recommended": "Wire github webhook → Temporal SecurityScanWorkflow that runs bandit + safety + pytest. Add on_push_scan activity to mission_control/activities.py. This makes security scanning an event-driven operation rather than manual-only."
    },
    {
      "step": 5,
      "target_component": "Agent tool definitions & network scope — ScopeEnforcer",
      "observation": "ScopeEnforcer (services/agent/security/scope_enforcer.py) exists with IP/subnet/domain allowlists. Auto-allows localhost 127.0.0.0/8, Docker networks 172.16.0.0/12, 10.0.0.0/8, 192.168.0.0/16. Auto-blocks cloud metadata 169.254.169.254/32. AgentRunConfig has allowed_domains/blocked_domains fields.",
      "hypothesis": "Network scope boundaries are well-defined for the security agent but the general web agent (ReActLoop) and browser fleet (BrowserFleet) have NO enforced scope limits. HTTPProber has no built-in scope check — it relies entirely on the caller to enforce scope.",
      "probe_executed": "Read scope_enforcer.py — confirmed. Read browser/fleet.py — navigate() accepts any URL, no scope check. Read agent/loop.py — ReActLoop has no scope enforcement. Read security/http_prober.py — HTTPProber has no scope parameter or check. Scope enforcement exists only in the security assessment path, not universally.",
      "outcome": "PARTIALLY_COMPLIANT",
      "remediation_recommended": "Integrate ScopeEnforcer into BrowserExecutor and HTTPProber at the transport layer so scope is enforced regardless of caller. Add scope parameter to AgentRunConfig and enforce it in ReActLoop.navigate(). Add scope check to BrowserFleet.navigate() before dispatching to sandbox."
    },
    {
      "step": 6,
      "target_component": "Browser sandbox container — Dockerfile.browser + seccomp-browser.json",
      "observation": "Dockerfile.browser: USER browser (non-root), WORKDIR /home/browser. docker-compose: cap_drop ALL, cap_add SYS_ADMIN only, mem_limit 2g, seccomp profile applied. seccomp-browser.json: whitelist-only mode (defaultAction SCMP_ACT_ERRNO), 120+ explicit syscall allowlist.",
      "hypothesis": "Browser sandbox has excellent isolation. Non-root execution, capability dropping, seccomp whitelist, memory limits — all present.",
      "probe_executed": "Read Dockerfile.browser — confirmed USER browser. Read docker-compose browser section — confirmed cap_drop ALL, seccomp, mem limits. Read seccomp-browser.json — confirmed whitelist mode with explicit syscall list. Verified security_check.sh exists for runtime verification.",
      "outcome": "COMPLIANT",
      "remediation_recommended": "Current browser sandbox is well-isolated. Consider adding AppArmor profile for defense-in-depth on Ubuntu hosts."
    },
    {
      "step": 7,
      "target_component": "API/Worker containers — Dockerfile.api + Dockerfile.worker",
      "observation": "Dockerfile.api: FROM python:3.11-slim, runs as root (no USER directive). Dockerfile.worker: FROM python:3.11-slim, runs as root (no USER directive). Neither has USER switch, cap_drop, or seccomp in docker-compose. API/worker are on private-internal network but run with root privileges inside the container.",
      "hypothesis": "API and worker containers run as root — any compromise of these services grants full container root access. This is a significant gap given the browser sandbox already demonstrates the project knows how to do non-root containers.",
      "probe_executed": "Read Dockerfile.api (from earlier session) — FROM python:3.11-slim, COPY + RUN + CMD, no USER. Read Dockerfile.worker — same pattern. docker-compose.yml — api/worker services have no security_opt, no cap_drop, no USER override.",
      "outcome": "NON_COMPLIANT",
      "remediation_recommended": "Add USER 1000 directive to Dockerfile.api and Dockerfile.worker. Add cap_drop ALL to api/worker services in docker-compose. Create non-root user in both Dockerfiles matching the browser sandbox pattern."
    },
    {
      "step": 8,
      "target_component": "Secret management — docker-compose.yml + .env + KeyEncryptionService",
      "observation": "docker-compose.yml: hardcoded passwords (synthera_dev_pwd) for PostgreSQL, Redis, MinIO. SECRET_KEY hardcoded. .env template has plaintext placeholders. However: KeyEncryptionService in llm_gateway.py uses Fernet encryption for API keys. Vault integration module exists (packages/security/vault.py) supporting dynamic credential injection from HashiCorp Vault with env var fallback.",
      "hypothesis": "Secret management has a split posture: API keys are Fernet-encrypted (good), Vault integration exists (good), but docker-compose uses hardcoded dev passwords and no environment variable masking. Production would need Vault or Docker secrets.",
      "probe_executed": "Read docker-compose.yml — confirmed hardcoded passwords. Read packages/security/vault.py — confirmed VaultClient with KV v2 integration, env fallback. Read services/gateway/llm_gateway.py — confirmed KeyEncryptionService with Fernet. .env blocked from reading (credential protection) — confirmed defense-in-depth.",
      "outcome": "PARTIALLY_COMPLIANT",
      "remediation_recommended": "Replace hardcoded passwords in docker-compose.yml with ${VAR} references. Add .env to .gitignore (verify it's already there). Use Docker secrets or Vault for production deployment. Create docker-compose.prod.yml with secrets: block."
    }
  ]
}
```

---

## Summary of Findings

| Pillar | Verdict | Evidence |
|---|---|---|
| **Self-reflection hooks** | PARTIALLY_COMPLIANT | ruff+mypy exist but no bandit/safety SAST. No pre-commit hooks. Syntax-only lint on write. No input sanitization layer. |
| **Event-driven listeners** | NON_COMPLIANT | No .github/workflows/. No CI/CD pipeline. Webhook handler is passive receiver, not security scan trigger. |
| **Subgoal discovery bounds** | PARTIALLY_COMPLIANT | ScopeEnforcer exists but only in security assessment path. Browser fleet and HTTP prober have no universal scope enforcement. |
| **Sandbox isolation** | PARTIALLY_COMPLIANT | Browser container: excellent (non-root, seccomp, cap_drop). API/Worker containers: run as root with no USER directive. Hardcoded passwords in compose. |

### Critical Findings (3)

1. **API/Worker run as root** — `Dockerfile.api` and `Dockerfile.worker` have no `USER` directive. Browser sandbox demonstrates the right pattern but it wasn't applied to other services.

2. **No CI/CD pipeline** — Zero automated security scanning on push/PR. All verification is manual.

3. **Scope enforcement not universal** — `ScopeEnforcer` exists but is only wired into the security assessment path. Browser fleet and HTTP prober accept any URL without scope validation.

### Strengths (3)

1. **Browser sandbox isolation** — Excellent: non-root user, seccomp whitelist, capability dropping, memory limits, dedicated egress network.

2. **API key encryption** — Fernet-based envelope encryption for provider keys, Vault integration module ready for production.

3. **Network segmentation** — Three distinct Docker networks (private-internal, isolated-egress, public) with appropriate access controls.

### Recommended Priority Fixes

1. **CRITICAL**: Add `USER` to api/worker Dockerfiles (1 line each)
2. **HIGH**: Create `.github/workflows/security-scan.yml` with bandit + safety + pytest
3. **HIGH**: Integrate ScopeEnforcer into BrowserFleet.navigate() and HTTPProber
4. **MEDIUM**: Add bandit + safety to dev dependencies
5. **MEDIUM**: Wire webhook handler to trigger security scans on push events
6. **LOW**: Replace hardcoded compose passwords with env var references
