"""H-Zero — Security Agent Module.

Adaptive security testing agent with:
- Observe → Hypothesize → Synthesize → Evaluate loop
- OWASP Top 10 probe catalog (SQLi, XSS, auth bypass, SSRF, path traversal...)
- Raw HTTP prober for API-level testing
- Strict scope enforcement (IP, subnet, domain allowlist)
- Structured JSON audit logging
- Non-destructive mode
"""

from services.agent.security.security_loop import (
    AdaptiveSecurityLoop,
    SecurityAssessmentConfig,
    get_security_loop,
)
from services.agent.security.probe_library import (
    ALL_PROBES,
    PROBES_BY_CATEGORY,
    SecurityProbe,
    ProbeCategory,
    ProbeSeverity,
    get_non_destructive_probes,
    search_probes,
)
from services.agent.security.audit_logger import (
    AuditEntry,
    AuditTrail,
    AuditLogger,
    AuditOutcome,
    Severity,
    get_audit_logger,
)
from services.agent.security.scope_enforcer import (
    ScopeEnforcer,
    ScopeDecision,
    ScopeResult,
    create_local_scope,
)
from services.agent.security.http_prober import (
    HTTPProber,
    HTTPProbeRequest,
    HTTPProbeResponse,
    get_http_prober,
)
