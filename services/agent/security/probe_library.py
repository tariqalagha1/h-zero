"""H-Zero — Security Probe Library.

Catalog of security test payloads organized by vulnerability class.
Each probe is tagged with: category, severity, payload, expected behavior,
and non-destructive flag.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProbeCategory(str, Enum):
    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    AUTH_BYPASS = "auth_bypass"
    IDOR = "idor"                       # Insecure Direct Object Reference
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    SSRF = "ssrf"
    XXE = "xxe"
    INFORMATION_DISCLOSURE = "information_disclosure"
    RATE_LIMITING = "rate_limiting"
    HEADER_INJECTION = "header_injection"
    OPEN_REDIRECT = "open_redirect"
    CORS_MISCONFIGURATION = "cors_misconfiguration"


class ProbeSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class SecurityProbe:
    """A single security probe with payload and expected behavior."""
    id: str
    category: ProbeCategory
    severity: ProbeSeverity
    name: str
    description: str
    payload: str
    target_parameter: str = ""          # URL param, header name, form field
    target_location: str = "query"      # query, body, header, path, cookie
    http_method: str = "GET"
    is_destructive: bool = False        # True for probes that could modify state
    expected_vulnerable_response: str = ""  # Pattern indicating vulnerability
    expected_safe_response: str = ""        # Pattern indicating proper handling
    owasp_reference: str = ""           # OWASP category reference
    remediation: str = ""               # Brief fix guidance


# ── SQL Injection Probes ────────────────────────────────────────────────────

SQLI_PROBES = [
    SecurityProbe(
        id="sqli-001",
        category=ProbeCategory.SQL_INJECTION,
        severity=ProbeSeverity.CRITICAL,
        name="Basic single-quote error trigger",
        description="Single quote to trigger SQL syntax error in unescaped input",
        payload="'",
        target_parameter="id",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="SQL syntax|mysql_fetch|PostgreSQL|sqlite|ORA-|Microsoft OLE DB|unclosed quotation",
        expected_safe_response="",
        owasp_reference="A03:2021 – Injection",
        remediation="Use parameterized queries / prepared statements",
    ),
    SecurityProbe(
        id="sqli-002",
        category=ProbeCategory.SQL_INJECTION,
        severity=ProbeSeverity.CRITICAL,
        name="Boolean-based blind injection",
        description="OR 1=1 to test for boolean-based SQL injection",
        payload="' OR '1'='1",
        target_parameter="id",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="",
        expected_safe_response="",
        owasp_reference="A03:2021 – Injection",
        remediation="Use parameterized queries",
    ),
    SecurityProbe(
        id="sqli-003",
        category=ProbeCategory.SQL_INJECTION,
        severity=ProbeSeverity.CRITICAL,
        name="Union-based injection probe",
        description="UNION SELECT to test for column enumeration",
        payload="' UNION SELECT NULL--",
        target_parameter="id",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="UNION|column|The used SELECT statements",
        expected_safe_response="",
        owasp_reference="A03:2021 – Injection",
        remediation="Use parameterized queries",
    ),
    SecurityProbe(
        id="sqli-004",
        category=ProbeCategory.SQL_INJECTION,
        severity=ProbeSeverity.CRITICAL,
        name="Time-based blind injection",
        description="SLEEP/WAITFOR payload to detect blind SQL injection",
        payload="' OR SLEEP(1)--",
        target_parameter="id",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="",  # Detected by response timing
        expected_safe_response="",
        owasp_reference="A03:2021 – Injection",
        remediation="Use parameterized queries and input validation",
    ),
    SecurityProbe(
        id="sqli-005",
        category=ProbeCategory.SQL_INJECTION,
        severity=ProbeSeverity.HIGH,
        name="Stacked query injection",
        description="Semicolon to test for stacked query execution",
        payload="'; SELECT 1;--",
        target_parameter="id",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="",
        expected_safe_response="",
        owasp_reference="A03:2021 – Injection",
        remediation="Disable multiple statements in database connection",
    ),
]

# ── XSS Probes ──────────────────────────────────────────────────────────────

XSS_PROBES = [
    SecurityProbe(
        id="xss-001",
        category=ProbeCategory.XSS,
        severity=ProbeSeverity.HIGH,
        name="Basic reflected XSS",
        description="Script tag to test for unescaped HTML output",
        payload='<script>alert("XSS")</script>',
        target_parameter="q",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response='<script>alert("XSS")</script>',
        expected_safe_response="&lt;script&gt;",
        owasp_reference="A03:2021 – Injection",
        remediation="HTML-encode all user-controlled output",
    ),
    SecurityProbe(
        id="xss-002",
        category=ProbeCategory.XSS,
        severity=ProbeSeverity.HIGH,
        name="Event handler XSS",
        description="Event handler injection in HTML attributes",
        payload='"><svg onload=alert(1)>',
        target_parameter="q",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response='<svg onload=alert',
        expected_safe_response="&quot;&gt;&lt;svg",
        owasp_reference="A03:2021 – Injection",
        remediation="HTML-encode attributes and validate input",
    ),
    SecurityProbe(
        id="xss-003",
        category=ProbeCategory.XSS,
        severity=ProbeSeverity.MEDIUM,
        name="DOM-based XSS probe",
        description="javascript: protocol to test URL-based DOM injection",
        payload="javascript:alert(1)",
        target_parameter="redirect",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="javascript:",
        expected_safe_response="",
        owasp_reference="A03:2021 – Injection",
        remediation="Validate and sanitize URL parameters",
    ),
    SecurityProbe(
        id="xss-004",
        category=ProbeCategory.XSS,
        severity=ProbeSeverity.MEDIUM,
        name="Img tag XSS",
        description="Image tag with onerror handler",
        payload='<img src=x onerror=alert(1)>',
        target_parameter="q",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response='<img src=x onerror=alert',
        expected_safe_response="&lt;img",
        owasp_reference="A03:2021 – Injection",
        remediation="HTML-encode user input",
    ),
]

# ── Authentication & Authorization Probes ───────────────────────────────────

AUTH_PROBES = [
    SecurityProbe(
        id="auth-001",
        category=ProbeCategory.AUTH_BYPASS,
        severity=ProbeSeverity.CRITICAL,
        name="Missing authentication check",
        description="Access protected endpoint without auth token",
        payload="",
        target_parameter="",
        target_location="header",
        http_method="GET",
        is_destructive=False,
        expected_vulnerable_response="",  # 200 on protected endpoint = vulnerable
        expected_safe_response="401|403",
        owasp_reference="A01:2021 – Broken Access Control",
        remediation="Enforce authentication middleware on all protected routes",
    ),
    SecurityProbe(
        id="auth-002",
        category=ProbeCategory.AUTH_BYPASS,
        severity=ProbeSeverity.HIGH,
        name="JWT none algorithm attack",
        description="JWT with alg=none to bypass signature verification",
        payload='{"alg":"none","typ":"JWT"}',
        target_parameter="Authorization",
        target_location="header",
        http_method="GET",
        is_destructive=False,
        expected_vulnerable_response="",  # 200 with forged token
        expected_safe_response="401",
        owasp_reference="A01:2021 – Broken Access Control",
        remediation="Reject tokens with alg=none; enforce allowed algorithms",
    ),
    SecurityProbe(
        id="auth-003",
        category=ProbeCategory.IDOR,
        severity=ProbeSeverity.HIGH,
        name="Insecure Direct Object Reference",
        description="Access another user's resource by ID manipulation",
        payload="",  # Dynamic — set at runtime
        target_parameter="user_id",
        target_location="path",
        http_method="GET",
        is_destructive=False,
        expected_vulnerable_response="",
        expected_safe_response="403|404",
        owasp_reference="A01:2021 – Broken Access Control",
        remediation="Verify ownership of requested resources server-side",
    ),
    SecurityProbe(
        id="auth-004",
        category=ProbeCategory.AUTH_BYPASS,
        severity=ProbeSeverity.CRITICAL,
        name="Admin endpoint exposure",
        description="Access admin endpoints without admin role",
        payload="",
        target_parameter="",
        target_location="path",
        http_method="GET",
        is_destructive=False,
        expected_vulnerable_response="",  # 200 = admin exposed
        expected_safe_response="401|403|404",
        owasp_reference="A01:2021 – Broken Access Control",
        remediation="Enforce role-based access control on admin routes",
    ),
]

# ── Path Traversal & File Inclusion ────────────────────────────────────────

PATH_PROBES = [
    SecurityProbe(
        id="path-001",
        category=ProbeCategory.PATH_TRAVERSAL,
        severity=ProbeSeverity.HIGH,
        name="Basic path traversal",
        description="Dot-dot-slash to access files outside web root",
        payload="../../../etc/passwd",
        target_parameter="file",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="root:x:0:0:",
        expected_safe_response="",
        owasp_reference="A01:2021 – Broken Access Control",
        remediation="Canonicalize paths and enforce base directory",
    ),
    SecurityProbe(
        id="path-002",
        category=ProbeCategory.PATH_TRAVERSAL,
        severity=ProbeSeverity.MEDIUM,
        name="URL-encoded traversal",
        description="URL-encoded dot-dot-slash to bypass filters",
        payload="%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        target_parameter="file",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="root:x:0:0:",
        expected_safe_response="",
        owasp_reference="A01:2021 – Broken Access Control",
        remediation="Validate and canonicalize paths before file access",
    ),
]

# ── SSRF Probes ────────────────────────────────────────────────────────────

SSRF_PROBES = [
    SecurityProbe(
        id="ssrf-001",
        category=ProbeCategory.SSRF,
        severity=ProbeSeverity.CRITICAL,
        name="Internal service probe via SSRF",
        description="Attempt to access internal services through URL parameter",
        payload="http://169.254.169.254/latest/meta-data/",
        target_parameter="url",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="ami-id|instance-id",
        expected_safe_response="",
        owasp_reference="A10:2021 – SSRF",
        remediation="Block requests to internal/private IP ranges; validate and allowlist URLs",
    ),
    SecurityProbe(
        id="ssrf-002",
        category=ProbeCategory.SSRF,
        severity=ProbeSeverity.HIGH,
        name="Localhost SSRF",
        description="Attempt to access localhost services",
        payload="http://localhost:5432",
        target_parameter="url",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="",  # Any response suggests internal access
        expected_safe_response="",
        owasp_reference="A10:2021 – SSRF",
        remediation="Block requests to loopback addresses (127.0.0.0/8, ::1)",
    ),
]

# ── Information Disclosure ─────────────────────────────────────────────────

DISCLOSURE_PROBES = [
    SecurityProbe(
        id="info-001",
        category=ProbeCategory.INFORMATION_DISCLOSURE,
        severity=ProbeSeverity.MEDIUM,
        name="Verbose error disclosure",
        description="Trigger error to check for stack trace leakage",
        payload="%00",
        target_parameter="id",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="Traceback|stack trace|at line|Exception in|File \"",
        expected_safe_response="",
        owasp_reference="A05:2021 – Security Misconfiguration",
        remediation="Configure custom error pages; disable debug mode in production",
    ),
    SecurityProbe(
        id="info-002",
        category=ProbeCategory.INFORMATION_DISCLOSURE,
        severity=ProbeSeverity.LOW,
        name="Server header disclosure",
        description="Check for verbose Server/X-Powered-By headers",
        payload="",
        target_parameter="",
        target_location="header",
        http_method="HEAD",
        is_destructive=False,
        expected_vulnerable_response="Server: Apache|X-Powered-By|X-AspNet-Version",
        expected_safe_response="",
        owasp_reference="A05:2021 – Security Misconfiguration",
        remediation="Remove or minimize Server/X-Powered-By headers",
    ),
    SecurityProbe(
        id="info-003",
        category=ProbeCategory.INFORMATION_DISCLOSURE,
        severity=ProbeSeverity.MEDIUM,
        name="API version disclosure",
        description="Check for API version leaks in error responses",
        payload="",
        target_parameter="",
        target_location="header",
        is_destructive=False,
        expected_vulnerable_response="version|v\\d+\\.\\d+",
        expected_safe_response="",
        owasp_reference="A05:2021 – Security Misconfiguration",
        remediation="Remove version information from API responses",
    ),
]

# ── CORS Misconfiguration ─────────────────────────────────────────────────

CORS_PROBES = [
    SecurityProbe(
        id="cors-001",
        category=ProbeCategory.CORS_MISCONFIGURATION,
        severity=ProbeSeverity.HIGH,
        name="Wildcard CORS with credentials",
        description="Check if Access-Control-Allow-Origin: * is used with credentials",
        payload="",
        target_parameter="Origin",
        target_location="header",
        is_destructive=False,
        expected_vulnerable_response="Access-Control-Allow-Origin: *\n.*Access-Control-Allow-Credentials: true",
        expected_safe_response="",
        owasp_reference="A05:2021 – Security Misconfiguration",
        remediation="Never use wildcard origin with credentials; use explicit allowlist",
    ),
    SecurityProbe(
        id="cors-002",
        category=ProbeCategory.CORS_MISCONFIGURATION,
        severity=ProbeSeverity.MEDIUM,
        name="Origin reflection",
        description="Check if server echoes arbitrary Origin header",
        payload="https://evil.com",
        target_parameter="Origin",
        target_location="header",
        is_destructive=False,
        expected_vulnerable_response="Access-Control-Allow-Origin: https://evil.com",
        expected_safe_response="",
        owasp_reference="A05:2021 – Security Misconfiguration",
        remediation="Validate origin against an explicit allowlist",
    ),
]

# ── Header Injection ──────────────────────────────────────────────────────

HEADER_PROBES = [
    SecurityProbe(
        id="head-001",
        category=ProbeCategory.HEADER_INJECTION,
        severity=ProbeSeverity.HIGH,
        name="CRLF header injection",
        description="Carriage return + line feed to inject HTTP headers",
        payload="test\r\nSet-Cookie: injected=true",
        target_parameter="redirect",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="Set-Cookie: injected=true",
        expected_safe_response="",
        owasp_reference="A03:2021 – Injection",
        remediation="Strip CR/LF characters from user input before header construction",
    ),
]

# ── Rate Limiting ──────────────────────────────────────────────────────────

RATE_PROBES = [
    SecurityProbe(
        id="rate-001",
        category=ProbeCategory.RATE_LIMITING,
        severity=ProbeSeverity.LOW,
        name="Missing rate limiting",
        description="Rapid requests to check for rate limiting",
        payload="",  # Detected by sending many requests
        target_parameter="",
        target_location="query",
        is_destructive=False,
        expected_vulnerable_response="",  # All 200s = no rate limit
        expected_safe_response="429|503",
        owasp_reference="A05:2021 – Security Misconfiguration",
        remediation="Implement rate limiting per IP/user/endpoint",
    ),
]

# ── Complete Catalog ──────────────────────────────────────────────────────

ALL_PROBES = (
    SQLI_PROBES + XSS_PROBES + AUTH_PROBES + PATH_PROBES +
    SSRF_PROBES + DISCLOSURE_PROBES + CORS_PROBES + HEADER_PROBES + RATE_PROBES
)

PROBES_BY_CATEGORY: dict[ProbeCategory, list[SecurityProbe]] = {}
for probe in ALL_PROBES:
    PROBES_BY_CATEGORY.setdefault(probe.category, []).append(probe)


def get_probes_by_category(category: ProbeCategory) -> list[SecurityProbe]:
    return PROBES_BY_CATEGORY.get(category, [])


def get_non_destructive_probes() -> list[SecurityProbe]:
    return [p for p in ALL_PROBES if not p.is_destructive]


def search_probes(keyword: str) -> list[SecurityProbe]:
    """Search probes by name, description, or OWASP reference."""
    kw = keyword.lower()
    return [
        p for p in ALL_PROBES
        if kw in p.name.lower() or kw in p.description.lower() or kw in p.owasp_reference.lower()
    ]
